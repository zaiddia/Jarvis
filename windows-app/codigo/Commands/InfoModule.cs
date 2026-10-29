using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;
using Jarvis.Core;

namespace Jarvis.Commands
{
    // Cuentas, conversiones, memoria, notas, listas, tiempo atmosférico y hora en otras ciudades.
    public sealed class InfoModule
    {
        readonly Engine E;
        static readonly HttpClient Http = Net.Create(TimeSpan.FromSeconds(10));
        public InfoModule(Engine e) { E = e; }
        string Sir => E.Sir;

        public string Try(Cmd c)
        {
            string calc = Calc.Answer(c.Orig, Sir);
            if (calc != null) return calc;
            return Convert(c) ?? Memory(c) ?? Notes(c) ?? Lists(c);
        }

        // ---------------------------------------------------------------- conversiones

        static readonly (string[] names, string kind, double factor, string sing, string plur)[] Units =
        {
            (new[] { "kilometro", "kilometros", "km" }, "len", 1000, "kilómetro", "kilómetros"),
            (new[] { "metro", "metros" }, "len", 1, "metro", "metros"),
            (new[] { "centimetro", "centimetros", "cm" }, "len", 0.01, "centímetro", "centímetros"),
            (new[] { "milla", "millas" }, "len", 1609.344, "milla", "millas"),
            (new[] { "pie", "pies" }, "len", 0.3048, "pie", "pies"),
            (new[] { "pulgada", "pulgadas" }, "len", 0.0254, "pulgada", "pulgadas"),
            (new[] { "yarda", "yardas" }, "len", 0.9144, "yarda", "yardas"),
            (new[] { "kilo", "kilos", "kilogramo", "kilogramos", "kg" }, "mass", 1000, "kilo", "kilos"),
            (new[] { "gramo", "gramos", "g" }, "mass", 1, "gramo", "gramos"),
            (new[] { "libra", "libras" }, "mass", 453.59237, "libra", "libras"),
            (new[] { "onza", "onzas" }, "mass", 28.349523, "onza", "onzas"),
            (new[] { "litro", "litros" }, "vol", 1, "litro", "litros"),
            (new[] { "mililitro", "mililitros", "ml" }, "vol", 0.001, "mililitro", "mililitros"),
            (new[] { "galon", "galones" }, "vol", 3.785411784, "galón", "galones"),
            (new[] { "taza", "tazas" }, "vol", 0.24, "taza", "tazas"),
            (new[] { "celsius", "centigrados" }, "temp", 0, "grado Celsius", "grados Celsius"),
            (new[] { "fahrenheit" }, "temp", 1, "grado Fahrenheit", "grados Fahrenheit"),
            (new[] { "kelvin" }, "temp", 2, "kelvin", "kelvin"),
            (new[] { "hora", "horas" }, "time", 3600, "hora", "horas"),
            (new[] { "minuto", "minutos" }, "time", 60, "minuto", "minutos"),
            (new[] { "segundo", "segundos" }, "time", 1, "segundo", "segundos"),
            (new[] { "dia", "dias" }, "time", 86400, "día", "días"),
            (new[] { "semana", "semanas" }, "time", 604800, "semana", "semanas"),
            (new[] { "megabyte", "megabytes", "megas", "mb" }, "data", 1 << 20, "mega", "megas"),
            (new[] { "gigabyte", "gigabytes", "gigas", "gb" }, "data", 1 << 30, "giga", "gigas"),
            (new[] { "terabyte", "terabytes", "teras", "tb" }, "data", 1099511627776.0, "tera", "teras"),
            (new[] { "kilobyte", "kilobytes", "kb" }, "data", 1024, "kilobyte", "kilobytes"),
        };

        static int UnitAt(Cmd c, int i)
        {
            string w = c.W(i);
            if (w == "grados" || w == "grado") w = c.W(i + 1);
            for (int k = 0; k < Units.Length; k++) if (Units[k].names.Contains(w)) return k;
            return -1;
        }

        string Convert(Cmd c)
        {
            // «cuántas millas son 10 kilómetros», «pasa 30 grados celsius a fahrenheit», «10 libras en kilos»
            int a = c.FindAny(new[] { "a", "en" });
            int num = -1;
            double value = 0;
            for (int i = 0; i < c.Size; i++)
            {
                if (c.W(i).All(char.IsDigit) || Text.ParseNumber(c.W(i), true) >= 0)
                {
                    // número con decimales del original («3,5 kilos»)
                    string raw = c.Orig.Substring(c.T[i].B, Math.Min(c.Orig.Length, c.T[i].E + 4) - c.T[i].B).Split(' ')[0];
                    if (!Text.TryParseDecimal(raw.TrimEnd(',', '.'), out value)) value = Text.ParseNumber(c.W(i), true);
                    if (c.W(i + 1) == "y" && (c.W(i + 2) == "medio" || c.W(i + 2) == "media")) value += 0.5;
                    num = i;
                    break;
                }
            }
            if (num < 0) return null;
            int from = -1, to = -1, fromIdx = -1;
            for (int i = num + 1; i < Math.Min(c.Size, num + 4); i++)
            {
                from = UnitAt(c, i);
                if (from >= 0) { fromIdx = i; break; }
            }
            if (from < 0) return null;
            // destino: antes del número («cuántas millas son…») o después de «a/en»
            for (int i = 0; i < num; i++)
            {
                int u = UnitAt(c, i);
                if (u >= 0 && u != from) { to = u; break; }
            }
            if (to < 0)
                for (int i = fromIdx + 1; i < c.Size; i++)
                {
                    if (c.W(i) != "a" && c.W(i) != "en" && c.W(i) != "son") continue;
                    for (int j = i + 1; j < Math.Min(c.Size, i + 3); j++)
                    {
                        int u = UnitAt(c, j);
                        if (u >= 0 && u != from) { to = u; break; }
                    }
                    if (to >= 0) break;
                }
            if (to < 0 || Units[to].kind != Units[from].kind) return null;
            _ = a;
            var f = Units[from];
            var t = Units[to];
            double r;
            if (f.kind == "temp")
            {
                double cel = f.factor == 0 ? value : f.factor == 1 ? (value - 32) * 5 / 9 : value - 273.15;
                r = t.factor == 0 ? cel : t.factor == 1 ? cel * 9 / 5 + 32 : cel + 273.15;
            }
            else r = value * f.factor / t.factor;
            string vs = Calc.Format(value), rs = Calc.Format(Math.Round(r, Math.Abs(r) < 10 ? 2 : 1));
            return vs + " " + (value == 1 ? f.sing : f.plur) + " son " + rs + " " + (Math.Abs(r - 1) < 1e-9 ? t.sing : t.plur) + ".";
        }

        // ---------------------------------------------------------------- memoria: «recuerda que mi coche es azul»

        public static List<string> Facts => Store.Get("memoria", new List<string>());

        string Memory(Cmd c)
        {
            if ((c.W(0) == "recuerda" || c.W(0) == "memoriza" || c.W(0) == "apunta" && c.W(1) == "que" || c.W(0) == "guarda" && c.W(1) == "que") && c.W(1) == "que" && c.Size > 2)
            {
                string fact = c.OrigFrom(2).Trim(' ', '.');
                var f = Facts;
                f.Add(Text.Capitalize(fact));
                Store.Set("memoria", f.TakeLast(200).ToList());
                return TalkModule.Pick("Lo recordaré" + Sir + ".", "Anotado en mi memoria.", "Entendido, no lo olvidaré.");
            }
            if (c.Contains("que recuerdas") || c.Contains("que sabes de mi") || c.Contains("que tienes en la memoria") || c.Contains("que te he dicho"))
            {
                var f = Facts;
                if (f.Count == 0) return "Aún no me ha pedido recordar nada. Diga «recuerda que…» y lo guardo.";
                return "Recuerdo esto: " + string.Join(". ", f.TakeLast(8)) + ".";
            }
            if ((c.W(0) == "olvida" || c.W(0) == "borra") && (c.Has("memoria") || c.Contains("todo lo que") || c.Has("recuerdas")))
            {
                Store.Set("memoria", new List<string>());
                return "Memoria borrada" + Sir + ".";
            }
            if (c.W(0) == "olvida" && c.W(1) == "que" && c.Size > 2)
            {
                string what = Text.Squash(c.OrigFrom(2));
                var f = Facts;
                int n = f.RemoveAll(x => Text.Squash(x).Contains(what) || what.Contains(Text.Squash(x)));
                Store.Set("memoria", f);
                return n > 0 ? "Olvidado." : "No tenía eso en la memoria.";
            }
            // Preguntas que la memoria contesta: «¿dónde dejé las llaves?»
            if (c.HasAny("donde", "cual", "cuando", "que", "quien", "como") && c.Size >= 3)
            {
                var keys = c.T.Select(t => t.W).Where(w => w.Length > 3 && !Text.IsOneOf(w, "donde", "cual", "cuando", "como", "quien", "esta", "estan", "deje", "tengo", "dije")).ToList();
                if (keys.Count > 0)
                {
                    var hit = Facts.LastOrDefault(f => keys.All(k => Text.Squash(f).Contains(k)) && (c.Contains("deje") || c.Contains("mi ") || c.All.Contains(" mi ") || c.Has("mis")));
                    if (hit != null) return "Me dijo: " + hit + ".";
                }
            }
            return null;
        }

        // ---------------------------------------------------------------- notas: «toma nota: …», «lee mis notas»

        public static List<string> NoteList => Store.Get("notas", new List<string>());

        string Notes(Cmd c)
        {
            bool take = (c.W(0) == "toma" || c.W(0) == "tomar") && c.W(1) == "nota" || c.W(0) == "anota" || c.W(0) == "apunta" || c.Contains("crea una nota") || c.Contains("nueva nota");
            if (take)
            {
                int k = c.FindAny(new[] { "nota", "anota", "apunta" });
                int s0 = k + 1;
                while (s0 < c.Size && Text.IsOneOf(c.W(s0), "de", "que", "esto", "lo", "siguiente", "una", "nueva")) s0++;
                string text = s0 < c.Size ? c.OrigFrom(s0).Trim(' ', ':', '.') : "";
                if (text == "") return "¿Qué anoto" + Sir + "? Diga «toma nota» seguido del texto.";
                var n = NoteList;
                n.Add(DateTime.Now.ToString("dd/MM HH:mm") + " · " + Text.Capitalize(text));
                Store.Set("notas", n);
                return "Anotado" + Sir + ".";
            }
            if (c.Has("notas") && c.HasAny("lee", "leeme", "dime", "cuales", "que", "muestra", "tengo"))
            {
                var n = NoteList;
                if (n.Count == 0) return "No tiene notas" + Sir + ".";
                E.Host.Show(string.Join("\n", n.TakeLast(15)));
                return (n.Count == 1 ? "Tiene una nota: " : "Tiene " + n.Count + " notas. Las últimas: ") +
                       string.Join(". ", n.TakeLast(3).Select(x => x.Contains(" · ") ? x.Substring(x.IndexOf(" · ") + 3) : x)) + ".";
            }
            if (c.Has("notas") && c.HasAny("borra", "elimina", "limpia", "vacia"))
            {
                Store.Set("notas", new List<string>());
                return "Notas borradas.";
            }
            if (c.Contains("borra la ultima nota") || c.Contains("elimina la ultima nota"))
            {
                var n = NoteList;
                if (n.Count == 0) return "No hay notas.";
                n.RemoveAt(n.Count - 1);
                Store.Set("notas", n);
                return "Última nota borrada.";
            }
            return null;
        }

        // ---------------------------------------------------------------- listas: «añade leche a la lista de la compra»

        string Lists(Cmd c)
        {
            int li = c.Find("lista");
            if (li < 0) return null;
            string name = "compra";
            int de = li + 1;
            if (c.W(de) == "de")
            {
                int s0 = de + 1;
                if (c.W(s0) == "la" || c.W(s0) == "las" || c.W(s0) == "los") s0++;
                if (s0 < c.Size) name = c.W(s0);
            }
            if (name == "tareas" || name == "pendientes") name = "tareas";
            string key = "lista-" + name;
            var list = Store.Get(key, new List<string>());
            string label = name == "compra" ? "la lista de la compra" : "la lista de " + name;

            if (c.HasAny("anade", "agrega", "apunta", "mete", "pon", "incluye") && li > 1)
            {
                int s0 = 1;
                int e = li;
                while (e > s0 && Text.IsOneOf(c.W(e - 1), "a", "en", "la", "mi", "al")) e--;
                string items = c.OrigFrom(s0, e);
                var parts = items.Split(new[] { ",", " y ", " e " }, StringSplitOptions.RemoveEmptyEntries).Select(x => x.Trim(' ', '.')).Where(x => x != "").ToList();
                if (parts.Count == 0) return "¿Qué añado" + Sir + "?";
                list.AddRange(parts.Where(p => !list.Any(x => Text.Squash(x) == Text.Squash(p))));
                Store.Set(key, list);
                return "Añadido a " + label + ".";
            }
            if (c.HasAny("quita", "borra", "elimina", "saca", "tacha") && li > 1)
            {
                string items = Text.Squash(c.OrigFrom(1, li));
                int n = list.RemoveAll(x => items.Contains(Text.Squash(x)));
                Store.Set(key, list);
                return n > 0 ? "Quitado de " + label + "." : "Eso no estaba en " + label + ".";
            }
            if (c.HasAny("vacia", "limpia", "borra") && (c.Has("toda") || li <= 2))
            {
                Store.Set(key, new List<string>());
                return Text.Capitalize(label) + " está vacía.";
            }
            if (c.HasAny("lee", "leeme", "dime", "que", "muestra", "tengo", "hay", "cual"))
            {
                if (list.Count == 0) return Text.Capitalize(label) + " está vacía" + Sir + ".";
                E.Host.Show(string.Join("\n", list.Select(x => "• " + x)));
                return "En " + label + " hay: " + string.Join(", ", list) + ".";
            }
            return null;
        }

        // ---------------------------------------------------------------- con internet

        public async Task<string> TryAsync(Cmd c)
        {
            if (c.HasAny("tiempo", "clima", "temperatura", "llover", "lluvia", "llueve", "llovera", "calor", "frio", "paraguas", "sol", "pronostico", "grados") &&
                !c.Has("temporizador") && !c.Contains("cuanto tiempo") && !c.Contains("tiempo encendido") && !c.Contains("tiempo lleva"))
            {
                bool weatherish = c.HasAny("hace", "que", "como", "va", "llover", "llueve", "llovera", "pronostico", "dime", "temperatura", "clima", "paraguas", "esta") || c.Size <= 3;
                if (weatherish) return await Weather(c);
            }
            if (c.Has("hora") && (c.Has("en") || c.Has("de")) && c.HasAny("que", "dime", "cual"))
            {
                int k = c.Find("en");
                if (k > c.Find("hora") && k + 1 < c.Size) return await CityTime(c.OrigFrom(k + 1));
            }
            return null;
        }

        public sealed class Place
        {
            public string Name = "";
            public double Lat, Lon;
        }

        static readonly Dictionary<string, Place> PlaceCache = new Dictionary<string, Place>();

        public static async Task<Place> Geocode(string name)
        {
            string key = Text.Squash(name);
            if (key == "") return null;
            if (PlaceCache.TryGetValue(key, out var p)) return p;
            string url = "https://geocoding-api.open-meteo.com/v1/search?count=1&language=es&format=json&name=" + Uri.EscapeDataString(name.Trim());
            using var doc = JsonDocument.Parse(await Http.GetStringAsync(url));
            if (!doc.RootElement.TryGetProperty("results", out var res) || res.GetArrayLength() == 0) return null;
            var r = res[0];
            p = new Place
            {
                Name = r.GetProperty("name").GetString() ?? name,
                Lat = r.GetProperty("latitude").GetDouble(),
                Lon = r.GetProperty("longitude").GetDouble(),
            };
            PlaceCache[key] = p;
            return p;
        }

        static string Where(Cmd c)
        {
            int k = -1;
            for (int i = 0; i < c.Size; i++)
                if (c.W(i) == "en" && i + 1 < c.Size && !Text.IsOneOf(c.W(i + 1), "la", "el", "este", "esta", "casa", "punto"))
                    k = i;
            if (k < 0) return "";
            int e = c.Size;
            for (int j = k + 1; j < c.Size; j++)
                if (Text.IsOneOf(c.W(j), "hoy", "manana", "ahora", "esta", "este", "el", "la", "pasado")) { e = j; break; }
            return c.OrigFrom(k + 1, e).Trim(' ', '?', '.');
        }

        static string Sky(int code) => code switch
        {
            0 => "despejado",
            1 => "mayormente despejado",
            2 => "parcialmente nublado",
            3 => "nublado",
            45 or 48 => "con niebla",
            51 or 53 or 55 => "con llovizna",
            56 or 57 => "con llovizna helada",
            61 => "con lluvia débil",
            63 => "con lluvia",
            65 => "con lluvia fuerte",
            66 or 67 => "con lluvia helada",
            71 or 73 or 75 or 77 => "con nieve",
            80 or 81 => "con chubascos",
            82 => "con chubascos fuertes",
            85 or 86 => "con chubascos de nieve",
            95 or 96 or 99 => "con tormenta",
            _ => "variable",
        };

        async Task<string> Weather(Cmd c)
        {
            string city = Where(c);
            if (city == "") city = E.S.City.Trim();
            if (city == "") return "¿De qué ciudad" + Sir + "? Puede decirme «el tiempo en Bogotá» o poner su ciudad en los ajustes.";
            try
            {
                var p = await Geocode(city);
                if (p == null) return "No encuentro la ciudad «" + city + "».";
                string inv(double d) => d.ToString(CultureInfo.InvariantCulture);
                string url = "https://api.open-meteo.com/v1/forecast?latitude=" + inv(p.Lat) + "&longitude=" + inv(p.Lon) +
                             "&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,precipitation" +
                             "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max&timezone=auto&forecast_days=3";
                using var doc = JsonDocument.Parse(await Http.GetStringAsync(url));
                var root = doc.RootElement;
                var cur = root.GetProperty("current");
                var daily = root.GetProperty("daily");
                int day = c.Has("manana") ? 1 : c.Contains("pasado manana") ? 2 : 0;
                if (c.Contains("pasado manana")) day = 2;
                int max = (int)Math.Round(daily.GetProperty("temperature_2m_max")[day].GetDouble());
                int min = (int)Math.Round(daily.GetProperty("temperature_2m_min")[day].GetDouble());
                int rain = daily.GetProperty("precipitation_probability_max")[day].ValueKind == JsonValueKind.Number ? daily.GetProperty("precipitation_probability_max")[day].GetInt32() : 0;
                int dcode = daily.GetProperty("weather_code")[day].GetInt32();

                bool askRain = c.HasAny("llover", "lluvia", "llueve", "llovera", "paraguas");
                if (day > 0)
                {
                    string when = day == 1 ? "Mañana" : "Pasado mañana";
                    string r0 = when + " en " + p.Name + ": " + Sky(dcode) + ", entre " + min + " y " + max + " grados";
                    r0 += rain >= 20 ? ", con un " + rain + " por ciento de probabilidad de lluvia." : ", sin lluvia prevista.";
                    if (askRain) r0 = (rain >= 50 ? "Sí, probablemente. " : rain >= 25 ? "Puede que sí. " : "No parece. ") + r0;
                    return r0;
                }
                int t = (int)Math.Round(cur.GetProperty("temperature_2m").GetDouble());
                int feel = (int)Math.Round(cur.GetProperty("apparent_temperature").GetDouble());
                int code = cur.GetProperty("weather_code").GetInt32();
                double wind = cur.GetProperty("wind_speed_10m").GetDouble();
                string r = "En " + p.Name + " hace " + t + " grados, " + Sky(code);
                if (Math.Abs(feel - t) >= 3) r += ", con sensación de " + feel;
                r += ". Hoy entre " + min + " y " + max;
                r += rain >= 20 ? ", y un " + rain + " por ciento de probabilidad de lluvia." : ".";
                if (wind >= 35) r += " Hay viento fuerte.";
                if (askRain) r = (rain >= 50 ? "Sí, lleve paraguas" + Sir + ". " : rain >= 25 ? "Quizá; mejor lleve paraguas. " : "No parece que vaya a llover. ") + r;
                return r;
            }
            catch (Exception e)
            {
                Log.Write("Tiempo: " + e.Message);
                return "No pude consultar el tiempo. Revise la conexión a internet" + Sir + ".";
            }
        }

        async Task<string> CityTime(string city)
        {
            try
            {
                var p = await Geocode(city.Trim(' ', '?'));
                if (p == null) return "No encuentro «" + city + "».";
                string inv(double d) => d.ToString(CultureInfo.InvariantCulture);
                string url = "https://api.open-meteo.com/v1/forecast?latitude=" + inv(p.Lat) + "&longitude=" + inv(p.Lon) + "&current=temperature_2m&timezone=auto&forecast_days=1";
                using var doc = JsonDocument.Parse(await Http.GetStringAsync(url));
                int off = doc.RootElement.GetProperty("utc_offset_seconds").GetInt32();
                var there = DateTime.UtcNow.AddSeconds(off);
                double diff = (off - TimeZoneInfo.Local.GetUtcOffset(DateTime.Now).TotalSeconds) / 3600.0;
                string d = Math.Abs(diff) < 0.01 ? "la misma hora que aquí" :
                           Text.Num(Math.Abs(diff), 1) + (Math.Abs(diff) == 1 ? " hora " : " horas ") + (diff > 0 ? "más" : "menos") + " que aquí";
                string dayNote = there.Date != DateTime.Now.Date ? (there.Date > DateTime.Now.Date ? ", ya es mañana" : ", todavía es ayer") : "";
                string st = TimeModule.SayTime(there);
                return "En " + p.Name + (st.StartsWith("la una") ? " es " : " son ") + st + dayNote + "; " + d + ".";
            }
            catch (Exception e)
            {
                Log.Write("Hora mundial: " + e.Message);
                return "No pude consultar la hora de esa ciudad.";
            }
        }
    }
}
