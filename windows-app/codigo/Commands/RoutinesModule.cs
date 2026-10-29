using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using Jarvis.Core;

namespace Jarvis.Commands
{
    // Rutinas: protocolos que, además de lanzarse con su frase, se lanzan solos
    // a una hora («07:30 lun-vie»), al iniciar JARVIS («al iniciar») o al volver al equipo tras un rato fuera («al volver»).
    // Se escriben en Ajustes › Rutinas o se le piden a la IA («cada mañana dime el tiempo y mi agenda»).
    public sealed class RoutinesModule
    {
        readonly Engine E;
        public RoutinesModule(Engine e) { E = e; }
        Settings S => E.S;
        string Sir => E.Sir;

        // ---------------------------------------------------------------- cuándo

        public enum Kind { None, Time, Startup, Return }

        public sealed class Schedule
        {
            public Kind Kind;
            public TimeSpan At;
            public bool[] Days = Enumerable.Repeat(true, 7).ToArray();   // 0 = lunes … 6 = domingo
            public bool Valid => Kind != Kind.None;

            public override string ToString()
            {
                if (Kind == Kind.Startup) return "al iniciar";
                if (Kind == Kind.Return) return "al volver";
                if (Kind != Kind.Time) return "";
                string t = At.Hours.ToString("00") + ":" + At.Minutes.ToString("00");
                return Days.All(d => d) ? t : t + " " + DaysText(Days);
            }
        }

        static readonly string[] DayNames = { "lun", "mar", "mie", "jue", "vie", "sab", "dom" };

        static string DaysText(bool[] d)
        {
            if (d.Take(5).All(x => x) && !d[5] && !d[6]) return "lun-vie";
            if (!d.Take(5).Any(x => x) && d[5] && d[6]) return "sab,dom";
            return string.Join(",", DayNames.Where((n, i) => d[i]));
        }

        static int DayIndex(string w)
        {
            w = Text.Squash(w);
            if (w.Length < 2) return -1;
            if (w.StartsWith("mi")) return 2;   // miércoles (antes que «ma»)
            for (int i = 0; i < 7; i++) if (w.StartsWith(DayNames[i].Substring(0, Math.Min(3, w.Length)))) return i;
            return -1;
        }

        static readonly Regex Clock = new Regex(@"(?<h>\d{1,2})(?:[:.h](?<m>\d{2}))?\s*(?<ap>am|pm|a\.?\s?m\.?|p\.?\s?m\.?|de la manana|de la tarde|de la noche|de la madrugada)?", RegexOptions.Compiled);

        public static Schedule Parse(string when)
        {
            var sc = new Schedule();
            string w = Text.FoldText((when ?? "").Trim());
            if (w == "") return sc;
            if (Regex.IsMatch(w, @"\b(al )?(iniciar|inicio|encender|arrancar|arranque|prender|empezar)\b")) { sc.Kind = Kind.Startup; return sc; }
            if (Regex.IsMatch(w, @"\b(al )?(volver|regresar|regreso|vuelta)\b")) { sc.Kind = Kind.Return; return sc; }
            var m = Clock.Match(w);
            if (!m.Success) return sc;
            int h = int.Parse(m.Groups["h"].Value, CultureInfo.InvariantCulture);
            int min = m.Groups["m"].Success ? int.Parse(m.Groups["m"].Value, CultureInfo.InvariantCulture) : 0;
            string ap = m.Groups["ap"].Value.Replace(".", "").Replace(" ", "");
            if ((ap.StartsWith("p") || ap.Contains("tarde") || ap.Contains("noche")) && h < 12) h += 12;
            if ((ap.StartsWith("a") || ap.Contains("madrugada") || ap.Contains("manana") || ap.Contains("noche")) && h == 12) h = 0;   // «12 de la noche» = 00:00
            if (h > 23 || min > 59) return sc;
            sc.Kind = Kind.Time;
            sc.At = new TimeSpan(h, min, 0);
            string rest = w.Remove(m.Index, m.Length);
            if (Regex.IsMatch(rest, @"entre semana|laborables|lunes a viernes|lun\s*-\s*vie|dias de trabajo"))
                sc.Days = new[] { true, true, true, true, true, false, false };
            else if (Regex.IsMatch(rest, @"fin(es)? de semana|sab(ado)?s?\s*(,|y)\s*dom"))
                sc.Days = new[] { false, false, false, false, false, true, true };
            else
            {
                var range = Regex.Match(rest, @"\b(?<a>[a-z]{3,9})\s*(-|a)\s*(?<b>[a-z]{3,9})\b");
                int ra = range.Success ? DayIndex(range.Groups["a"].Value) : -1, rb = range.Success ? DayIndex(range.Groups["b"].Value) : -1;
                if (ra >= 0 && rb >= 0)
                {
                    sc.Days = new bool[7];
                    for (int i = ra; ; i = (i + 1) % 7) { sc.Days[i] = true; if (i == rb) break; }
                }
                else
                {
                    var listed = Regex.Matches(rest, @"[a-z]{3,9}").Select(x => DayIndex(x.Value)).Where(i => i >= 0).Distinct().ToList();
                    // «los lunes», «martes y jueves»; «todos los días» o nada = cada día
                    if (listed.Count > 0 && !rest.Contains("todos los dias") && !rest.Contains("diario"))
                    {
                        sc.Days = new bool[7];
                        foreach (int i in listed) sc.Days[i] = true;
                    }
                }
            }
            return sc;
        }

        // ---------------------------------------------------------------- crear, ver y borrar

        public string Create(string phrase, string when, string steps)
        {
            phrase = (phrase ?? "").Trim().Trim('«', '»', '"', '.');
            var list = (steps ?? "").Split(new[] { ';', '\n' }, StringSplitOptions.RemoveEmptyEntries).Select(x => x.Trim().Trim('«', '»', '"')).Where(x => x != "").ToList();
            if (phrase == "" || list.Count == 0) return "Faltan la frase o los pasos de la rutina.";
            var sc = Parse(when);
            if ((when ?? "").Trim() != "" && !sc.Valid)
                return "No entendí cuándo debe lanzarse («" + when + "»). Usa por ejemplo «07:30», «07:30 lun-vie», «al iniciar» o «al volver».";
            var all = S.Protocols ?? new List<Protocol>();
            bool existed = all.RemoveAll(p => Text.Squash(p.Phrase) == Text.Squash(phrase)) > 0;
            all.Add(new Protocol { Phrase = phrase, Steps = list, When = sc.ToString() });
            S.Protocols = all;
            E.Host.ApplySettings();
            Log.Write("Rutina «" + phrase + "» " + (existed ? "cambiada" : "creada") + " (" + (sc.Valid ? sc.ToString() : "solo con la frase") + "): " + string.Join("; ", list));
            return "Rutina «" + phrase + "» " + (existed ? "actualizada" : "creada") + (sc.Valid ? ", se lanzará " + Say(sc) : ", se lanza diciendo su frase") + ".";
        }

        static string Say(Schedule sc)
        {
            if (sc.Kind == Kind.Startup) return "al iniciar el equipo";
            if (sc.Kind == Kind.Return) return "cuando vuelva al equipo tras un rato fuera";
            string t = "a las " + sc.At.Hours + (sc.At.Minutes > 0 ? ":" + sc.At.Minutes.ToString("00") : "");
            string d = sc.Days.All(x => x) ? " todos los días" : DaysText(sc.Days) == "lun-vie" ? " de lunes a viernes" : DaysText(sc.Days) == "sab,dom" ? " los fines de semana" : " (" + DaysText(sc.Days) + ")";
            return t + d;
        }

        public string Describe() => string.Join("; ", (S.Protocols ?? new List<Protocol>()).Select(p =>
            "«" + p.Phrase + "»" + (Parse(p.When).Valid ? " (" + Parse(p.When) + ")" : "") + ": " + string.Join(", ", p.Steps)));

        public string Try(Cmd c)
        {
            string s = c.Join(0);
            bool word = c.HasAny("rutina", "rutinas", "protocolo", "protocolos");
            if (!word) return null;
            var all = S.Protocols ?? new List<Protocol>();
            if (Text.IsOneOf(s, "que rutinas tengo", "cuales son mis rutinas", "mis rutinas", "dime mis rutinas", "que protocolos tengo", "cuales son mis protocolos",
                             "lista de rutinas", "muestrame mis rutinas", "que rutinas hay", "rutinas"))
            {
                if (all.Count == 0)
                    return "Aún no tiene rutinas" + Sir + ". " + (AiReady()
                        ? "Pídamela así: «cada mañana a las 7 dime el tiempo y mi agenda»."
                        : "Créelas en mis ajustes, pestaña Rutinas.");
                E.Host.Show("Rutinas:\n" + string.Join("\n", all.Select(p => "• " + p.Phrase + (Parse(p.When).Valid ? "  [" + Parse(p.When) + "]" : "") + ": " + string.Join("; ", p.Steps))));
                return "Tiene " + Text.Plural(all.Count, "rutina", "rutinas") + ": " + string.Join(", ", all.Select(p => p.Phrase + (Parse(p.When).Valid ? " (" + Say(Parse(p.When)) + ")" : ""))) + ".";
            }
            if (Text.IsOneOf(c.W(0), "borra", "elimina", "quita", "cancela", "desactiva") && c.HasAny("rutina", "protocolo"))
            {
                int k = Math.Max(c.Find("rutina"), c.Find("protocolo")) + 1;
                while (k < c.Size && Text.IsOneOf(c.W(k), "de", "del", "la", "el")) k++;
                string name = c.Join(k);
                var p = all.FirstOrDefault(x => Text.Squash(x.Phrase) == name || Text.Squash(x.Phrase).Contains(name) && name.Length > 3);
                if (p == null) return name == "" ? "¿Qué rutina borro" + Sir + "?" : "No tengo ninguna rutina llamada «" + name + "».";
                E.Ask("¿Borro la rutina «" + p.Phrase + "»" + Sir + "?", yes =>
                {
                    if (!yes) return "La dejo como está.";
                    all.Remove(p);
                    S.Protocols = all;
                    E.Host.ApplySettings();
                    return "Rutina borrada.";
                });
                return "¿Borro la rutina «" + p.Phrase + "»" + Sir + "?";
            }
            // «crea una rutina…»: sin IA no hay quien entienda los pasos; con IA, que la cree ella.
            if (Text.IsOneOf(c.W(0), "crea", "haz", "nueva", "programa", "configura", "anade", "agrega") && !AiReady())
                return "Las rutinas se crean en mis ajustes, en la pestaña Rutinas: una por línea, por ejemplo «buenos días [07:30 lun-vie]: dime el tiempo; qué tengo hoy». " +
                       "Si conecta una IA, me las puede pedir hablando.";
            return null;
        }

        bool AiReady() => S.AiProvider == "ollama" || S.ApiKey.Trim() != "" || (S.AiProvider == "openai" && S.ApiUrl.Trim() != "");

        // ---------------------------------------------------------------- lanzarlas solas

        DateTime _lastMinute = DateTime.MinValue;
        double _maxIdle;
        DateTime _lastReturn = DateTime.MinValue;
        bool _running;

        Dictionary<string, string> Done => Store.Get("rutinas-hechas", new Dictionary<string, string>());

        void MarkDone(Protocol p)
        {
            var d = Done;
            d[Text.Squash(p.Phrase)] = DateTime.Now.ToString("yyyy-MM-dd HH:mm", CultureInfo.InvariantCulture);
            Store.Set("rutinas-hechas", d);
        }

        bool DoneToday(Protocol p) =>
            Done.TryGetValue(Text.Squash(p.Phrase), out var at) && at.StartsWith(DateTime.Now.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture));

        // Cada segundo (desde Engine.Tick).
        public void Tick()
        {
            var all = S.Protocols;
            if (all == null || all.Count == 0) return;
            var now = DateTime.Now;

            // A su hora (una vez por minuto basta; si el equipo estaba dormido justo entonces, en los 10 minutos siguientes).
            if ((now - _lastMinute).TotalSeconds >= 30)
            {
                _lastMinute = now;
                int day = ((int)now.DayOfWeek + 6) % 7;
                foreach (var p in all.ToList())
                {
                    var sc = Parse(p.When);
                    if (sc.Kind != Kind.Time || !sc.Days[day] || DoneToday(p)) continue;
                    var due = now.Date + sc.At;
                    if (now >= due && now < due.AddMinutes(10)) Launch(p, "a su hora");
                }
            }

            // Al volver: estuvo 10 minutos o más sin tocar el equipo y ahora lo usa (como mucho una vez cada hora).
            if (all.Any(p => Parse(p.When).Kind == Kind.Return))
            {
                double idle = Native.IdleSeconds();
                if (idle > _maxIdle) _maxIdle = idle;
                if (idle < 3)
                {
                    if (_maxIdle >= 600 && (now - _lastReturn).TotalMinutes >= 60)
                    {
                        _lastReturn = now;
                        foreach (var p in all.Where(p => Parse(p.When).Kind == Kind.Return).ToList()) Launch(p, "al volver");
                    }
                    _maxIdle = 0;
                }
            }
        }

        // Al iniciar JARVIS (normalmente, al encender el equipo).
        public void OnStartup()
        {
            foreach (var p in (S.Protocols ?? new List<Protocol>()).Where(p => Parse(p.When).Kind == Kind.Startup).ToList())
                Launch(p, "al iniciar");
        }

        async void Launch(Protocol p, string why)
        {
            if (_running) return;   // una rutina larga no se solapa con otra
            _running = true;
            MarkDone(p);
            try
            {
                Log.Write("Rutina «" + p.Phrase + "» (" + why + ")");
                string r = await E.RunRoutine(p);
                if (!string.IsNullOrWhiteSpace(r)) E.Host.Say(r);
            }
            catch (Exception e)
            {
                Log.Write("Rutina «" + p.Phrase + "»: " + e.Message);
            }
            finally
            {
                _running = false;
            }
        }
    }
}
