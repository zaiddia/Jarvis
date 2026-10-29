using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net.Http;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using Jarvis.Core;

namespace Jarvis.Commands
{
    // Integraciones: casa inteligente (Home Assistant), avisos al celular (ntfy), traducción, criptomonedas,
    // el tiempo de varios días, pomodoro, resumen diario automático, emisoras de radio y copias de seguridad.
    public sealed class IntegrationsModule
    {
        readonly Engine E;
        static readonly HttpClient Http = Net.Create(TimeSpan.FromSeconds(12));
        static readonly CultureInfo Es = CultureInfo.GetCultureInfo("es-ES");
        public IntegrationsModule(Engine e) { E = e; }
        string Sir => E.Sir;
        Settings S => E.S;
        static string Pick(params string[] o) => TalkModule.Pick(o);

        bool AiReady => S.AiProvider == "ollama" || S.ApiKey.Trim() != "" || (S.AiProvider == "openai" && S.ApiUrl.Trim() != "");

        public string Try(Cmd c) => Pomodoro(c) ?? Backup(c);

        public async Task<string> TryAsync(Cmd c)
        {
            return await Phone(c) ?? await Home(c) ?? await Crypto(c) ?? await Translate(c) ?? await Forecast(c) ?? await Radio(c);
        }

        // ================================================================ avisos al celular (ntfy)

        public bool PhoneReady => S.NtfyTopic.Trim() != "";

        public async Task<bool> PushPhone(string title, string text)
        {
            if (!PhoneReady) return false;
            try
            {
                string server = S.NtfyServer.Trim() == "" ? "https://ntfy.sh" : S.NtfyServer.Trim().TrimEnd('/');
                using var req = new HttpRequestMessage(HttpMethod.Post, server + "/" + Uri.EscapeDataString(S.NtfyTopic.Trim()));
                req.Content = new StringContent(text, Encoding.UTF8, "text/plain");
                // Las cabeceras HTTP no admiten tildes: el título se manda codificado (ntfy lo entiende).
                req.Headers.TryAddWithoutValidation("Title", "=?UTF-8?B?" + Convert.ToBase64String(Encoding.UTF8.GetBytes(title)) + "?=");
                req.Headers.TryAddWithoutValidation("Tags", "robot");
                using var res = await Http.SendAsync(req);
                return res.IsSuccessStatusCode;
            }
            catch (Exception e)
            {
                Log.Write("ntfy: " + e.Message);
                return false;
            }
        }

        // Los recordatorios, alarmas y avisos de agenda también al celular (si está activado).
        public void Mirror(string title, string text)
        {
            if (PhoneReady && S.PhoneReminders) _ = PushPhone(title, text);
        }

        async Task<string> Phone(Cmd c)
        {
            bool phone = c.HasAny("celular", "movil", "telefono", "cel");
            if (!phone || !c.HasAny("manda", "mandame", "envia", "enviame", "envie", "mande", "pasa", "pasame", "avisame", "escribeme", "notificame", "recuerdame"))
            {
                if (phone && c.HasAny("prueba", "probar") && c.HasAny("aviso", "notificacion", "avisos", "notificaciones"))
                    return await PushPhone(S.Name, "Prueba de avisos: si lee esto, funciona.") ? "Le he mandado una prueba al celular" + Sir + "." : "No pude mandarla. Revise el tema de ntfy en mis ajustes.";
                return null;
            }
            if (!PhoneReady)
                return "Para mandarle cosas al celular, instale la app gratuita ntfy en el teléfono, suscríbase a un tema con un nombre difícil de adivinar y escríbalo en mis ajustes, pestaña Integraciones.";
            string msg = null, title = S.Name;
            // «manda la lista de la compra al celular»
            int li = c.Find("lista");
            if (li >= 0)
            {
                string name = c.W(li + 1) == "de" ? (Text.IsOneOf(c.W(li + 2), "la", "las", "los") ? c.W(li + 3) : c.W(li + 2)) : "compra";
                var list = Store.Get("lista-" + name, new List<string>());
                if (list.Count == 0) return "La lista de " + name + " está vacía" + Sir + ".";
                title = "Lista de " + name;
                msg = string.Join("\n", list.Select(x => "• " + x));
            }
            else if (c.HasAny("notas"))
            {
                var notes = InfoModule.NoteList;
                if (notes.Count == 0) return "No tiene notas.";
                title = "Notas";
                msg = string.Join("\n", notes.TakeLast(15));
            }
            else if (c.Contains("lo que copie") || c.Contains("lo que he copiado") || c.Has("portapapeles"))
            {
                msg = E.Host.ClipboardText();
                if (msg == "") return "El portapapeles está vacío.";
            }
            else
            {
                // «mándame al celular que compre pan», «envíame un mensaje al celular diciendo…»
                int k = c.FindAny(new[] { "que", "diciendo", "dice", "con" });
                int cel = c.FindAny(new[] { "celular", "movil", "telefono", "cel" });
                if (k >= 0 && k > cel) msg = c.OrigFrom(k + 1);
                else if (k >= 0 && k < cel) msg = c.OrigFrom(k + 1, cel - 1 > k ? cel - 1 : cel);
                if (string.IsNullOrWhiteSpace(msg)) return "¿Qué le mando al celular" + Sir + "?";
            }
            return await PushPhone(title, msg) ? Pick("Enviado al celular.", "Listo, ya lo tiene en el teléfono" + Sir + ".") : "No pude enviarlo al celular. Revise la conexión o el tema de ntfy.";
        }

        // ================================================================ casa inteligente (Home Assistant)

        public bool HomeReady => S.HaUrl.Trim() != "" && S.HaToken.Trim() != "";

        sealed class Entity
        {
            public string Id = "", Name = "", Domain = "", State = "", Unit = "";
        }

        List<Entity> _entities = new List<Entity>();
        DateTime _entitiesAt = DateTime.MinValue;

        HttpRequestMessage HaRequest(HttpMethod m, string path)
        {
            var req = new HttpRequestMessage(m, S.HaUrl.Trim().TrimEnd('/') + path);
            req.Headers.Add("Authorization", "Bearer " + S.HaToken.Trim());
            return req;
        }

        async Task<List<Entity>> States(bool force = false)
        {
            if (!force && (DateTime.Now - _entitiesAt).TotalSeconds < 45 && _entities.Count > 0) return _entities;
            using var req = HaRequest(HttpMethod.Get, "/api/states");
            using var res = await Http.SendAsync(req);
            if (!res.IsSuccessStatusCode) throw new HttpRequestException("Home Assistant respondió " + (int)res.StatusCode);
            using var doc = JsonDocument.Parse(await res.Content.ReadAsStringAsync());
            var list = new List<Entity>();
            foreach (var e in doc.RootElement.EnumerateArray())
            {
                string id = e.GetProperty("entity_id").GetString() ?? "";
                var attr = e.TryGetProperty("attributes", out var a) ? a : default;
                string name = attr.ValueKind == JsonValueKind.Object && attr.TryGetProperty("friendly_name", out var fn) ? fn.GetString() ?? id : id;
                string unit = attr.ValueKind == JsonValueKind.Object && attr.TryGetProperty("unit_of_measurement", out var u) ? u.GetString() ?? "" : "";
                list.Add(new Entity { Id = id, Name = name, Domain = id.Split('.')[0], State = e.GetProperty("state").GetString() ?? "", Unit = unit });
            }
            _entities = list;
            _entitiesAt = DateTime.Now;
            return list;
        }

        static readonly Dictionary<string, string[]> DeviceWords = new Dictionary<string, string[]>
        {
            ["light"] = new[] { "luz", "luces", "lampara", "lamparas", "foco", "focos", "bombillo", "bombillos", "bombilla", "bombillas", "led", "tira" },
            ["switch"] = new[] { "enchufe", "enchufes", "interruptor", "toma", "tomacorriente", "regleta" },
            ["fan"] = new[] { "ventilador", "ventiladores", "abanico" },
            ["cover"] = new[] { "persiana", "persianas", "cortina", "cortinas", "garaje", "porton", "toldo" },
            ["climate"] = new[] { "aire", "calefaccion", "termostato", "clima" },
            ["media_player"] = new[] { "tele", "televisor", "television", "tv", "parlante", "altavoz", "bocina" },
            ["scene"] = new[] { "escena", "ambiente" },
            ["script"] = new[] { "rutina", "script" },
            ["vacuum"] = new[] { "aspiradora", "robot" },
            ["lock"] = new[] { "cerradura", "puerta" },
        };

        static readonly string[] Stop = { "la", "el", "los", "las", "de", "del", "en", "mi", "mis", "todas", "todos", "toda", "todo", "a", "al", "por", "favor", "un", "una", "porcentaje", "ciento" };

        async Task<string> Home(Cmd c)
        {
            if (!HomeReady) return null;
            string w0 = c.W(0);
            bool on = Text.IsOneOf(w0, "activa", "enciende", "prende", "abre", "sube");
            bool off = Text.IsOneOf(w0, "apaga", "desactiva", "cierra", "baja");
            bool toggle = Text.IsOneOf(w0, "alterna", "cambia");
            bool ask = c.HasAny("esta", "estan", "como", "cual", "cuanto", "temperatura", "humedad", "que") && !on && !off;
            if (!on && !off && !toggle && !ask) return null;

            string domainHint = DeviceWords.FirstOrDefault(kv => kv.Value.Any(c.Has)).Key;
            // Sin decir qué aparato, solo «enciende/apaga X» puede ser de la casa (no «abre Spotify», «sube el volumen»).
            if (domainHint == null && !Text.IsOneOf(w0, "activa", "apaga", "desactiva", "alterna") && !ask) return null;
            if (domainHint == null && ask && !c.HasAny("temperatura", "humedad")) return null;
            bool all = c.HasAny("todas", "todos", "toda", "todo");
            List<Entity> ents;
            // Sin palabra de dispositivo («luz», «ventilador»…) solo se mira lo ya conocido, sin esperar a la red:
            // así «abre Spotify» o «sube el volumen» no se retrasan.
            if (domainHint == null)
            {
                if ((DateTime.Now - _entitiesAt).TotalMinutes > 5) _ = States().ContinueWith(t => { _ = t.Exception; });
                if (_entities.Count == 0) return null;
                ents = _entities;
            }
            else try { ents = await States(); }
            catch (Exception e)
            {
                if (domainHint == null) return null;
                Log.Write("Home Assistant: " + e.Message);
                return "No pude hablar con Home Assistant" + Sir + ". Revise la dirección y el token en Integraciones.";
            }
            var words = c.T.Skip(1).Select(t => t.W).Where(w => !Stop.Contains(w) && w.Length > 1).ToList();
            if (domainHint != null) words = words.Where(w => !DeviceWords[domainHint].Contains(w)).ToList();
            var pool = ents.Where(e => domainHint == null ? DeviceWords.ContainsKey(e.Domain) || e.Domain == "input_boolean" || (ask && e.Domain == "sensor") : e.Domain == domainHint).ToList();
            if (ask && (c.HasAny("temperatura", "humedad")))
                pool = ents.Where(e => e.Domain == "sensor" && (Text.Squash(e.Name).Contains(c.Has("humedad") ? "humedad" : "temperatura") || e.Unit == (c.Has("humedad") ? "%" : "°C"))).ToList();

            // Puntuación: cuántas palabras de la orden aparecen en el nombre del dispositivo.
            List<Entity> chosen;
            if (all && domainHint != null && words.Count == 0) chosen = pool;
            else
            {
                var scored = pool.Select(e =>
                {
                    string n = Text.Squash(e.Name);
                    int hits = words.Count(w => (" " + n + " ").Contains(" " + w + " ") || (w.Length >= 4 && n.Contains(w)));
                    return (e, hits, full: hits > 0 && hits == words.Count);
                }).Where(x => x.hits > 0).OrderByDescending(x => x.hits).ThenBy(x => x.e.Name.Length).ToList();
                if (scored.Count == 0)
                {
                    if (domainHint == null) return null;   // no era para la casa
                    if (pool.Count == 1) chosen = pool;
                    else if (words.Count == 0 && pool.Count > 0)
                        return "¿Cuál" + Sir + "? Tengo: " + string.Join(", ", pool.Take(6).Select(e => e.Name)) + ".";
                    else return "No encuentro ese dispositivo en Home Assistant" + Sir + ".";
                }
                else
                {
                    int best = scored[0].hits;
                    chosen = all ? scored.Where(x => x.hits == best).Select(x => x.e).ToList() : new List<Entity> { scored[0].e };
                    if (domainHint == null && !scored[0].full && words.Count > 1) return null;   // poca coincidencia: mejor no tocar nada
                }
            }
            if (chosen.Count == 0) return null;

            if (ask)
            {
                var e = chosen[0];
                string st = e.State switch { "on" => "encendido", "off" => "apagado", "open" => "abierto", "closed" => "cerrado", "unavailable" => "sin conexión", _ => e.State };
                return e.Name + ": " + st + (e.Unit != "" ? " " + e.Unit.Replace("°C", "grados") : "") + ".";
            }

            // Brillo o posición: «pon la luz de la sala al 40», «sube la persiana al 50»
            int ni = c.FindNumber(1);
            int? pct = ni >= 0 ? Math.Clamp(Text.ParseNumber(c.W(ni)), 0, 100) : (int?)null;
            int done = 0;
            foreach (var e in chosen.Take(30))
            {
                string svc;
                var body = new Dictionary<string, object> { ["entity_id"] = e.Id };
                switch (e.Domain)
                {
                    case "scene":
                    case "script":
                        svc = e.Domain + "/turn_on";
                        break;
                    case "cover":
                        svc = pct.HasValue ? "cover/set_cover_position" : on ? "cover/open_cover" : off ? "cover/close_cover" : "cover/toggle";
                        if (pct.HasValue) body["position"] = pct.Value;
                        break;
                    case "lock":
                        svc = on ? "lock/unlock" : "lock/lock";
                        if (on) return "Por seguridad no abro cerraduras por voz" + Sir + ". Hágalo desde la app de Home Assistant.";
                        break;
                    case "vacuum":
                        svc = on ? "vacuum/start" : "vacuum/return_to_base";
                        break;
                    case "climate":
                        if (pct.HasValue) { svc = "climate/set_temperature"; body["temperature"] = pct.Value; }
                        else svc = on ? "climate/turn_on" : "climate/turn_off";
                        break;
                    case "light":
                        svc = off && !pct.HasValue ? "light/turn_off" : toggle ? "light/toggle" : "light/turn_on";
                        if (pct.HasValue) body["brightness_pct"] = pct.Value;
                        break;
                    default:
                        svc = e.Domain + (toggle ? "/toggle" : off ? "/turn_off" : "/turn_on");
                        break;
                }
                try
                {
                    using var req = HaRequest(HttpMethod.Post, "/api/services/" + svc);
                    req.Content = new StringContent(JsonSerializer.Serialize(body), Encoding.UTF8, "application/json");
                    using var res = await Http.SendAsync(req);
                    if (res.IsSuccessStatusCode) done++;
                    else Log.Write("Home Assistant " + svc + ": " + (int)res.StatusCode);
                }
                catch (Exception ex) { Log.Write("Home Assistant: " + ex.Message); }
            }
            _entitiesAt = DateTime.MinValue;
            if (done == 0) return "Home Assistant no aceptó la orden" + Sir + ".";
            string what = chosen.Count == 1 ? chosen[0].Name : chosen.Count + " dispositivos";
            if (chosen[0].Domain == "scene") return "Escena «" + chosen[0].Name + "» activada.";
            if (pct.HasValue) return what + " al " + pct.Value + (chosen[0].Domain == "climate" ? " grados." : " por ciento.");
            return Pick(what + (off ? " apagado." : toggle ? " cambiado." : " encendido."), "Listo: " + what + (off ? " apagado." : " encendido."));
        }

        // ================================================================ criptomonedas

        static readonly Dictionary<string, (string id, string name)> Coins = new Dictionary<string, (string, string)>
        {
            ["bitcoin"] = ("bitcoin", "el bitcoin"), ["btc"] = ("bitcoin", "el bitcoin"), ["ethereum"] = ("ethereum", "el ethereum"), ["ether"] = ("ethereum", "el ethereum"),
            ["solana"] = ("solana", "solana"), ["dogecoin"] = ("dogecoin", "dogecoin"), ["cardano"] = ("cardano", "cardano"), ["xrp"] = ("ripple", "XRP"),
            ["ripple"] = ("ripple", "XRP"), ["litecoin"] = ("litecoin", "litecoin"), ["usdt"] = ("tether", "el tether"), ["tether"] = ("tether", "el tether"),
            ["bnb"] = ("binancecoin", "BNB"), ["polkadot"] = ("polkadot", "polkadot"),
        };

        async Task<string> Crypto(Cmd c)
        {
            var coin = c.T.Select(t => t.W).FirstOrDefault(Coins.ContainsKey);
            if (coin == null) return null;
            if (!c.HasAny("precio", "vale", "cuesta", "esta", "cotizacion", "como", "cuanto", "valor", "cotiza", "sube", "baja", "va")) return null;
            var (id, name) = Coins[coin];
            try
            {
                string url = "https://api.coingecko.com/api/v3/simple/price?ids=" + id + "&vs_currencies=usd,cop&include_24hr_change=true";
                using var doc = JsonDocument.Parse(await Http.GetStringAsync(url));
                var d = doc.RootElement.GetProperty(id);
                double usd = d.GetProperty("usd").GetDouble();
                double cop = d.TryGetProperty("cop", out var cv) ? cv.GetDouble() : 0;
                double ch = d.TryGetProperty("usd_24h_change", out var chv) && chv.ValueKind == JsonValueKind.Number ? chv.GetDouble() : 0;
                string r = Text.Capitalize(name) + " está en " + Text.Num(usd >= 100 ? Math.Round(usd) : usd, usd >= 100 ? 0 : 4) + " dólares";
                if (cop > 0) r += ", unos " + Text.Num(Math.Round(cop), 0) + " pesos";
                if (Math.Abs(ch) >= 0.1) r += ". En las últimas veinticuatro horas " + (ch > 0 ? "ha subido" : "ha bajado") + " un " + Text.Num(Math.Abs(ch), 1) + " por ciento";
                return r + ".";
            }
            catch (Exception e)
            {
                Log.Write("Cripto: " + e.Message);
                return "No pude consultar el precio ahora" + Sir + ".";
            }
        }

        // ================================================================ traducción (sin IA: MyMemory)

        static readonly Dictionary<string, string> Langs = new Dictionary<string, string>
        {
            ["ingles"] = "en", ["frances"] = "fr", ["aleman"] = "de", ["italiano"] = "it", ["portugues"] = "pt", ["japones"] = "ja", ["chino"] = "zh-CN",
            ["ruso"] = "ru", ["coreano"] = "ko", ["arabe"] = "ar", ["holandes"] = "nl", ["catalan"] = "ca", ["espanol"] = "es", ["castellano"] = "es",
        };

        async Task<string> Translate(Cmd c)
        {
            if (AiReady) return null;   // con IA, la traducción la hace la IA (mejor y con contexto)
            int al = -1;
            string lang = null;
            for (int i = c.Size - 1; i >= 1; i--)
                if ((c.W(i - 1) == "al" || c.W(i - 1) == "en" || c.W(i - 1) == "a") && Langs.TryGetValue(c.W(i), out lang)) { al = i - 1; break; }
            if (lang == null) return null;
            string text = null;
            if (c.W(0) == "traduce") text = c.OrigFrom(1, al);
            else if (c.Contains("como se dice")) text = c.OrigFrom(c.Find("dice") + 1, al);
            if (string.IsNullOrWhiteSpace(text)) return null;
            text = text.Trim(' ', '«', '»', '"', '?', '¿');
            if (Text.IsOneOf(Text.Squash(text), "esto", "eso", "lo que copie", "lo copiado")) text = E.Host.ClipboardText();
            if (text == "") return "¿Qué traduzco" + Sir + "?";
            string from = lang == "es" ? "en" : "es";
            try
            {
                string url = "https://api.mymemory.translated.net/get?q=" + Uri.EscapeDataString(text.Length > 450 ? text.Substring(0, 450) : text) + "&langpair=" + from + "|" + lang;
                using var doc = JsonDocument.Parse(await Http.GetStringAsync(url));
                string t = doc.RootElement.GetProperty("responseData").GetProperty("translatedText").GetString() ?? "";
                if (t == "") return "No pude traducirlo.";
                E.Host.Show(text + "\n→ " + t);
                return "Se dice: " + t + ".";
            }
            catch (Exception e)
            {
                Log.Write("Traducción: " + e.Message);
                return "No pude conectar con el traductor" + Sir + ".";
            }
        }

        // ================================================================ el tiempo de varios días

        static string Sky(int code) => code switch
        {
            0 => "despejado", 1 => "casi despejado", 2 => "parcialmente nublado", 3 => "nublado", 45 or 48 => "con niebla",
            51 or 53 or 55 or 56 or 57 => "con llovizna", 61 or 63 or 80 or 81 => "con lluvia", 65 or 82 => "con lluvia fuerte",
            71 or 73 or 75 or 77 or 85 or 86 => "con nieve", 95 or 96 or 99 => "con tormenta", _ => "variable",
        };

        async Task<string> Forecast(Cmd c)
        {
            if (!c.HasAny("tiempo", "clima", "pronostico", "llover", "lluvia", "llovera")) return null;
            bool weekend = c.Contains("fin de semana");
            bool week = c.Contains("esta semana") || c.Contains("la semana") || c.Contains("proximos dias") || c.Contains("siguientes dias") || c.Contains("para la semana");
            if (!weekend && !week) return null;
            string city = S.City.Trim();
            int en = c.Find("en");
            if (en >= 0 && en + 1 < c.Size && !Text.IsOneOf(c.W(en + 1), "el", "la", "esta", "los")) city = c.OrigFrom(en + 1).Trim('?', '.');
            if (city == "") return "¿De qué ciudad" + Sir + "? Póngala en mis ajustes o dígame «el tiempo del fin de semana en Medellín».";
            try
            {
                var p = await InfoModule.Geocode(city);
                if (p == null) return "No encuentro «" + city + "».";
                string inv(double v) => v.ToString(CultureInfo.InvariantCulture);
                string url = "https://api.open-meteo.com/v1/forecast?latitude=" + inv(p.Lat) + "&longitude=" + inv(p.Lon) +
                             "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max&timezone=auto&forecast_days=7";
                using var doc = JsonDocument.Parse(await Http.GetStringAsync(url));
                var d = doc.RootElement.GetProperty("daily");
                var days = d.GetProperty("time").EnumerateArray().Select(x => DateTime.Parse(x.GetString(), CultureInfo.InvariantCulture)).ToList();
                var parts = new List<string>();
                var lines = new List<string>();
                for (int i = 0; i < days.Count; i++)
                {
                    var day = days[i];
                    bool take = weekend ? (day.DayOfWeek == DayOfWeek.Saturday || day.DayOfWeek == DayOfWeek.Sunday) : i < 5;
                    int max = (int)Math.Round(d.GetProperty("temperature_2m_max")[i].GetDouble());
                    int min = (int)Math.Round(d.GetProperty("temperature_2m_min")[i].GetDouble());
                    var rp = d.GetProperty("precipitation_probability_max")[i];
                    int rain = rp.ValueKind == JsonValueKind.Number ? rp.GetInt32() : 0;
                    string sky = Sky(d.GetProperty("weather_code")[i].GetInt32());
                    lines.Add(day.ToString("ddd d", Es) + " · " + sky + " · " + min + "–" + max + "°" + (rain >= 20 ? " · lluvia " + rain + "%" : ""));
                    if (!take) continue;
                    string label = i == 0 ? "hoy" : i == 1 ? "mañana" : "el " + day.ToString("dddd", Es);
                    parts.Add(label + " " + sky + ", entre " + min + " y " + max + (rain >= 40 ? ", con " + rain + " por ciento de lluvia" : ""));
                }
                E.Host.Show(p.Name + "\n" + string.Join("\n", lines));
                if (parts.Count == 0) return "No tengo el pronóstico de esos días todavía.";
                return "En " + p.Name + ": " + string.Join("; ", parts) + ".";
            }
            catch (Exception e)
            {
                Log.Write("Pronóstico: " + e.Message);
                return "No pude consultar el pronóstico" + Sir + ".";
            }
        }

        // ================================================================ radio (radio-browser.info)

        async Task<string> Radio(Cmd c)
        {
            int r = c.FindAny(new[] { "radio", "emisora", "estacion" });
            if (r < 0) return null;
            if (!(c.HasAny("pon", "reproduce", "sintoniza", "escuchar", "activa", "abre") || r == 0)) return null;
            if (c.HasAny("apaga", "quita", "para")) return null;
            string name = r + 1 < c.Size ? c.OrigFrom(r + 1).Trim(' ', '.', '?') : "";
            foreach (var art in new[] { "de ", "la ", "el " }) if (name.StartsWith(art, StringComparison.OrdinalIgnoreCase)) name = name.Substring(art.Length);
            string country = S.RadioCountry.Trim() == "" ? "CO" : S.RadioCountry.Trim().ToUpperInvariant();
            try
            {
                string url = name == ""
                    ? "https://de1.api.radio-browser.info/json/stations/search?countrycode=" + country + "&order=clickcount&reverse=true&limit=1&hidebroken=true"
                    : "https://de1.api.radio-browser.info/json/stations/search?name=" + Uri.EscapeDataString(name) + "&order=clickcount&reverse=true&limit=5&hidebroken=true";
                using var req = new HttpRequestMessage(HttpMethod.Get, url);
                req.Headers.TryAddWithoutValidation("User-Agent", "JARVIS-Windows/3.8");
                using var res = await Http.SendAsync(req);
                using var doc = JsonDocument.Parse(await res.Content.ReadAsStringAsync());
                var all = doc.RootElement.EnumerateArray().ToList();
                if (all.Count == 0) return "No encuentro la emisora «" + name + "»" + Sir + ".";
                // Mejor una del país del usuario si la hay.
                var st = all.FirstOrDefault(x => x.TryGetProperty("countrycode", out var cc) && cc.GetString() == country);
                if (st.ValueKind != JsonValueKind.Object) st = all[0];
                string stream = st.TryGetProperty("url_resolved", out var u) && (u.GetString() ?? "") != "" ? u.GetString() : st.GetProperty("url").GetString();
                string label = st.GetProperty("name").GetString()?.Trim() ?? name;
                E.Apps.OpenUrl(stream, "");
                return Pick("Sintonizando " + label + ".", "Le pongo " + label + Sir + ".");
            }
            catch (Exception e)
            {
                Log.Write("Radio: " + e.Message);
                return "No pude conectar con el buscador de emisoras" + Sir + ".";
            }
        }

        // ================================================================ pomodoro

        string Pomodoro(Cmd c)
        {
            if (!c.Has("pomodoro") && !c.Contains("modo concentracion") && !c.Contains("modo enfoque")) return null;
            if (c.HasAny("para", "cancela", "deten", "quita", "termina", "desactiva", "apaga"))
            {
                int n = E.Time.RemoveAlarms(a => a.Text.StartsWith("pomodoro"));
                return n > 0 ? "Pomodoro cancelado." : "No había ningún pomodoro en marcha.";
            }
            if (c.HasAny("cuanto", "queda", "falta"))
            {
                var p = E.Time.Pending.Where(a => a.Text.StartsWith("pomodoro")).OrderBy(a => a.When).FirstOrDefault();
                return p == null ? "No hay pomodoro en marcha." : "Quedan " + TimeModule.SayDuration(p.When - DateTime.Now) + (p.Text.Contains("descanso") ? " de trabajo." : " de descanso.");
            }
            int mins = 25;
            int ni = c.FindNumber(0);
            if (ni >= 0) mins = Math.Clamp(Text.ParseNumber(c.W(ni)), 5, 120);
            int rest = mins >= 45 ? 10 : 5;
            E.Time.RemoveAlarms(a => a.Text.StartsWith("pomodoro"));
            var now = DateTime.Now;
            E.Time.AddAlarm(new Alarm { Id = now.Ticks, Kind = "timer", When = now.AddMinutes(mins), Seconds = mins * 60, Text = "pomodoro: a descansar " + rest + " minutos" });
            E.Time.AddAlarm(new Alarm { Id = now.Ticks + 1, Kind = "timer", When = now.AddMinutes(mins + rest), Seconds = rest * 60, Text = "pomodoro: fin del descanso, de vuelta al trabajo" });
            return "Pomodoro en marcha: " + mins + " minutos de concentración y " + rest + " de descanso. Le aviso" + Sir + ".";
        }

        // ================================================================ copias de seguridad de JARVIS (sus ajustes y datos)

        static string BackupDir => Path.Combine(Settings.Folder, "copias");

        string Backup(Cmd c)
        {
            bool make = c.Contains("copia de seguridad") && c.HasAny("haz", "crea", "guarda", "genera", "hacer");
            bool restore = c.Contains("copia de seguridad") && c.HasAny("restaura", "recupera", "restaurar", "recuperar", "vuelve");
            if (!make && !restore) return null;
            Directory.CreateDirectory(BackupDir);
            if (make)
            {
                string file = Path.Combine(BackupDir, "jarvis-" + DateTime.Now.ToString("yyyy-MM-dd_HH-mm") + ".zip");
                using (var zip = ZipFile.Open(file, ZipArchiveMode.Create))
                    foreach (var f in new[] { Settings.FilePath, Store.FilePath, Path.Combine(Settings.Folder, "agenda.ics") })
                        if (File.Exists(f)) zip.CreateEntryFromFile(f, Path.GetFileName(f));
                var old = new DirectoryInfo(BackupDir).GetFiles("jarvis-*.zip").OrderByDescending(f => f.CreationTimeUtc).Skip(15).ToList();
                foreach (var o in old) try { o.Delete(); } catch { }
                return "Copia de seguridad hecha" + Sir + ": ajustes, recordatorios, notas, listas y memoria.";
            }
            var last = new DirectoryInfo(BackupDir).GetFiles("jarvis-*.zip").OrderByDescending(f => f.CreationTimeUtc).FirstOrDefault();
            if (last == null) return "No hay ninguna copia de seguridad todavía. Diga «haz una copia de seguridad».";
            string when = last.CreationTime.ToString("d 'de' MMMM 'a las' HH:mm", Es);
            E.Ask("¿Restauro la copia del " + when + "? Se reemplazarán los ajustes y datos actuales.", yes =>
            {
                if (!yes) return "Cancelado.";
                try
                {
                    using var zip = ZipFile.OpenRead(last.FullName);
                    foreach (var en in zip.Entries)
                    {
                        string target = Path.Combine(Settings.Folder, Path.GetFileName(en.FullName));
                        if (target.EndsWith(".json") || target.EndsWith(".ics")) en.ExtractToFile(target, true);
                    }
                    Store.Reload();
                    E.Host.ReloadSettings();
                    return "Copia restaurada" + Sir + ".";
                }
                catch (Exception ex)
                {
                    return "No pude restaurarla: " + ex.Message;
                }
            });
            return "¿Restauro la copia del " + when + "? Se reemplazarán los ajustes y datos actuales.";
        }

        // ================================================================ resumen del día automático

        [StructLayout(LayoutKind.Sequential)] struct LASTINPUTINFO { public uint cbSize, dwTime; }
        [DllImport("user32.dll")] static extern bool GetLastInputInfo(ref LASTINPUTINFO i);

        static double IdleSeconds()
        {
            var li = new LASTINPUTINFO { cbSize = (uint)Marshal.SizeOf<LASTINPUTINFO>() };
            if (!GetLastInputInfo(ref li)) return 0;
            return ((uint)Environment.TickCount - li.dwTime) / 1000.0;
        }

        DateTime _lastTick;
        bool _briefing;

        public void Tick()
        {
            if ((DateTime.Now - _lastTick).TotalSeconds < 30) return;
            _lastTick = DateTime.Now;
            if (_briefing || !TimeSpan.TryParse(S.BriefingTime.Trim(), CultureInfo.InvariantCulture, out var at)) return;
            var today = DateTime.Today.ToString("yyyy-MM-dd");
            if (Store.Get("resumen-dia", "") == today) return;
            if (DateTime.Now.TimeOfDay < at || DateTime.Now.TimeOfDay > at.Add(TimeSpan.FromHours(4))) return;
            if (IdleSeconds() > 120) return;   // espera a que el usuario esté delante
            Store.Set("resumen-dia", today);
            _briefing = true;
            _ = Task.Run(async () =>
            {
                try
                {
                    string brief = await E.Agenda.Brief(true);
                    E.Host.Say(brief);
                    Mirror("Resumen del día", brief);
                }
                catch (Exception e) { Log.Write("Resumen del día: " + e.Message); }
                finally { _briefing = false; }
            });
        }
    }
}
