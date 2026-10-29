using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using Jarvis.Core;

namespace Jarvis.Commands
{
    public sealed class Alarm
    {
        public long Id { get; set; }
        public string Kind { get; set; } = "timer";   // timer | alarm | reminder
        public DateTime When { get; set; }
        public string Text { get; set; } = "";
        public int Seconds { get; set; }               // duración (temporizador)
        public string Repeat { get; set; } = "";       // "" | daily | weekdays | weekends | w0…w6 (cada domingo…sábado)
    }

    // Hora, fecha, temporizadores, alarmas, recordatorios y cronómetro.
    public sealed class TimeModule
    {
        readonly Engine E;
        static readonly CultureInfo Es = CultureInfo.GetCultureInfo("es-ES");
        DateTime? _chrono;
        public TimeModule(Engine e) { E = e; }
        string Sir => E.Sir;

        List<Alarm> Load() => Store.Get("avisos", new List<Alarm>());

        public void AddAlarm(Alarm a)
        {
            var list = Load();
            list.Add(a);
            Save(list);
        }

        public int RemoveAlarms(Func<Alarm, bool> which)
        {
            var list = Load();
            int n = list.RemoveAll(a => which(a));
            Save(list);
            return n;
        }
        void Save(List<Alarm> a) => Store.Set("avisos", a.OrderBy(x => x.When).ToList());

        public IReadOnlyList<Alarm> Pending => Load();

        // ---------------------------------------------------------------- textos de hora y duración

        public static string SayTime(DateTime t)
        {
            int h = t.Hour % 12;
            if (h == 0) h = 12;
            string part = t.Hour < 6 ? "de la madrugada" : t.Hour < 12 ? "de la mañana" : t.Hour < 13 ? "del mediodía" : t.Hour < 20 ? "de la tarde" : "de la noche";
            string art = h == 1 ? "la" : "las";
            string min = t.Minute == 0 ? "en punto" : t.Minute == 15 ? "y cuarto" : t.Minute == 30 ? "y media" : "y " + t.Minute;
            return art + " " + (h == 1 ? "una" : h.ToString()) + " " + min + " " + part;
        }

        public static string SayDuration(TimeSpan d)
        {
            int total = (int)Math.Round(d.TotalSeconds);
            if (total < 60) return Text.Plural(Math.Max(total, 1), "segundo", "segundos");
            int days = total / 86400, h = total % 86400 / 3600, m = total % 3600 / 60, s = total % 60;
            var p = new List<string>();
            if (days > 0) p.Add(Text.Plural(days, "día", "días"));
            if (h > 0) p.Add(Text.Plural(h, "hora", "horas"));
            if (m > 0) p.Add(Text.Plural(m, "minuto", "minutos"));
            if (s > 0 && days == 0 && h == 0 && m < 10) p.Add(Text.Plural(s, "segundo", "segundos"));
            return p.Count == 1 ? p[0] : string.Join(", ", p.Take(p.Count - 1)) + " y " + p[^1];
        }

        public static string SayDay(DateTime d)
        {
            var today = DateTime.Today;
            if (d.Date == today) return "hoy";
            if (d.Date == today.AddDays(1)) return "mañana";
            if (d.Date == today.AddDays(2)) return "pasado mañana";
            if ((d.Date - today).TotalDays < 7 && d.Date > today) return "el " + d.ToString("dddd", Es);
            return "el " + d.ToString("dddd d 'de' MMMM", Es);
        }

        // ---------------------------------------------------------------- análisis de «en 5 minutos», «a las 7 y media», «mañana»

        static int UnitSeconds(string w)
        {
            if (w.StartsWith("segundo") || w == "seg") return 1;
            if (w.StartsWith("minuto") || w == "min") return 60;
            if (w.StartsWith("hora")) return 3600;
            if (w == "dia" || w == "dias") return 86400;
            return 0;
        }

        // Duración desde from: «5 minutos», «una hora y media», «media hora», «un cuarto de hora», «1 hora 20 minutos».
        public static bool ParseDuration(Cmd c, int from, out int seconds, out int start, out int end)
        {
            seconds = 0;
            start = end = -1;
            for (int i = Math.Max(0, from); i < c.Size; i++)
            {
                int total = 0, j = i;
                bool any = false;
                while (j < c.Size)
                {
                    if (c.W(j) == "media" && c.W(j + 1).StartsWith("hora")) { total += 1800; j += 2; any = true; continue; }
                    if ((c.W(j) == "un" || c.W(j) == "1") && c.W(j + 1) == "cuarto" && c.W(j + 2) == "de" && c.W(j + 3).StartsWith("hora")) { total += 900; j += 4; any = true; continue; }
                    if (c.W(j) == "cuarto" && c.W(j + 1) == "de" && c.W(j + 2).StartsWith("hora")) { total += 900; j += 3; any = true; continue; }
                    int n = Text.ParseNumber(c.W(j), true);
                    int u = n >= 0 ? UnitSeconds(c.W(j + 1)) : 0;
                    if (n >= 0 && u > 0)
                    {
                        total += n * u;
                        j += 2;
                        any = true;
                        if (c.W(j) == "y" && (c.W(j + 1) == "media" || c.W(j + 1) == "medio")) { total += u / 2; j += 2; }
                        else if (c.W(j) == "y" && c.W(j + 1) == "cuarto") { total += u / 4; j += 2; }
                        if (c.W(j) == "y" && Text.ParseNumber(c.W(j + 1), true) >= 0 && UnitSeconds(c.W(j + 2)) > 0) j++;
                        continue;
                    }
                    break;
                }
                if (any && total > 0)
                {
                    seconds = total;
                    start = i;
                    end = j;
                    return true;
                }
            }
            return false;
        }

        static readonly string[] Weekdays = { "domingo", "lunes", "martes", "miercoles", "jueves", "viernes", "sabado" };

        // «mañana a las 7 y media de la tarde», «el lunes a las 9», «a las 19 30», «a mediodía».
        public static bool ParseClock(Cmd c, int from, out DateTime when, out int start, out int end)
        {
            when = DateTime.MinValue;
            start = end = -1;
            DateTime day = DateTime.Today;
            bool dayGiven = false;
            int dayIdx = -1, dayEnd = -1;
            for (int i = Math.Max(0, from); i < c.Size; i++)
            {
                if (c.W(i) == "pasado" && c.W(i + 1) == "manana") { day = DateTime.Today.AddDays(2); dayGiven = true; dayIdx = i; dayEnd = i + 2; break; }
                if (c.W(i) == "manana" && !(c.W(i - 1) == "la" && c.W(i - 2) == "de")) { day = DateTime.Today.AddDays(1); dayGiven = true; dayIdx = i; dayEnd = i + 1; break; }
                if (c.W(i) == "hoy" || c.W(i) == "esta" && (c.W(i + 1) == "tarde" || c.W(i + 1) == "noche")) { dayGiven = true; dayIdx = i; dayEnd = i + 1; break; }
                int wd = Array.IndexOf(Weekdays, c.W(i));
                if (wd >= 0 && (c.W(i - 1) == "el" || c.W(i - 1) == "este" || c.W(i - 1) == "proximo"))
                {
                    int diff = (wd - (int)DateTime.Today.DayOfWeek + 7) % 7;
                    if (diff == 0) diff = 7;
                    day = DateTime.Today.AddDays(diff);
                    dayGiven = true;
                    dayIdx = i - 1;
                    dayEnd = i + 1;
                    break;
                }
            }
            for (int i = Math.Max(0, from); i < c.Size; i++)
            {
                int h = -1, m = 0, j;
                if (c.W(i) == "a" && (c.W(i + 1) == "mediodia" || c.W(i + 1) == "medianoche"))
                {
                    h = c.W(i + 1) == "mediodia" ? 12 : 0;
                    j = i + 2;
                }
                else if (c.W(i) == "a" && (c.W(i + 1) == "las" || c.W(i + 1) == "la"))
                {
                    h = Text.ParseNumber(c.W(i + 2), true);
                    if (h < 0 || h > 24) continue;
                    j = i + 3;
                    if (c.W(j) == "y" && c.W(j + 1) == "media") { m = 30; j += 2; }
                    else if (c.W(j) == "y" && c.W(j + 1) == "cuarto") { m = 15; j += 2; }
                    else if (c.W(j) == "menos" && c.W(j + 1) == "cuarto") { m = -15; j += 2; }
                    else if (c.W(j) == "y" && Text.ParseNumber(c.W(j + 1)) is int mm && mm >= 0 && mm < 60) { m = mm; j += 2; }
                    else if (Text.ParseNumber(c.W(j)) is int m2 && m2 >= 0 && m2 < 60 && c.W(j).Length == 2) { m = m2; j += 1; }
                    else if (c.W(j) == "menos" && Text.ParseNumber(c.W(j + 1)) is int m3 && m3 > 0 && m3 < 60) { m = -m3; j += 2; }
                    if (c.W(j) == "en" && c.W(j + 1) == "punto") j += 2;
                    bool pm = false, am = false;
                    if (c.W(j) == "de" && c.W(j + 1) == "la" && (c.W(j + 2) == "tarde" || c.W(j + 2) == "noche")) { pm = true; j += 3; }
                    else if (c.W(j) == "de" && c.W(j + 1) == "la" && (c.W(j + 2) == "manana" || c.W(j + 2) == "madrugada")) { am = true; j += 3; }
                    else if (c.W(j) == "del" && c.W(j + 1) == "mediodia") { j += 2; }
                    else if (c.W(j) == "pm" || c.W(j) == "p" && c.W(j + 1) == "m") { pm = true; j += c.W(j) == "pm" ? 1 : 2; }
                    else if (c.W(j) == "am" || c.W(j) == "a" && c.W(j + 1) == "m") { am = true; j += c.W(j) == "am" ? 1 : 2; }
                    if (pm && h < 12) h += 12;
                    if (am && h == 12) h = 0;
                    if (h == 24) h = 0;
                    // «a las 3» sin decir mañana/tarde: la próxima vez que lleguen esas horas.
                    if (!pm && !am && h >= 1 && h <= 11 && !dayGiven)
                    {
                        var t1 = DateTime.Today.AddHours(h).AddMinutes(m);
                        if (t1 <= DateTime.Now && t1.AddHours(12) > DateTime.Now) h += 12;
                    }
                    if (c.W(i - 1) == "esta" || (dayIdx >= 0 && c.W(dayIdx) == "esta" && c.W(dayIdx + 1) is string pp && (pp == "tarde" || pp == "noche")))
                        if (h < 12) h += 12;
                }
                else continue;
                var t = day.AddHours(h).AddMinutes(m);
                if (!dayGiven && t <= DateTime.Now) t = t.AddDays(1);
                when = t;
                start = dayIdx >= 0 ? Math.Min(i, dayIdx) : i;
                end = Math.Max(j, dayEnd);
                return true;
            }
            return false;
        }

        // ---------------------------------------------------------------- órdenes

        public string Try(Cmd c)
        {
            string s = c.Join(0);

            if (Text.IsOneOf(s, "que hora es", "hora", "la hora", "dime la hora", "que horas son", "me dices la hora", "dices la hora", "sabes que hora es", "que hora tenemos"))
                return Text.Capitalize(SayTime(DateTime.Now).Replace("la una", "Es la una").Replace("las ", "Son las ")) + ".";
            if (Text.IsOneOf(s, "que dia es hoy", "que dia es", "fecha", "la fecha", "que fecha es hoy", "que fecha es", "dime la fecha", "a que estamos hoy", "a cuanto estamos", "en que dia estamos"))
                return "Hoy es " + DateTime.Now.ToString("dddd d 'de' MMMM 'de' yyyy", Es) + ".";
            if (Text.IsOneOf(s, "que dia es manana", "que fecha es manana"))
                return "Mañana es " + DateTime.Now.AddDays(1).ToString("dddd d 'de' MMMM", Es) + ".";
            if (c.Contains("en que mes estamos") || s == "que mes es")
                return "Estamos en " + DateTime.Now.ToString("MMMM", Es) + ".";
            if (c.Contains("en que ano estamos") || s == "que ano es")
                return "Estamos en " + DateTime.Now.Year + ".";
            if (c.Contains("que semana es") || c.Contains("numero de semana"))
                return "Es la semana " + ISOWeek.GetWeekOfYear(DateTime.Now) + " del año.";
            // «¿cuánto falta para las cinco?»
            if ((c.Contains("cuanto falta para") || c.Contains("cuanto queda para") || c.Contains("cuanto falta pa")) && c.HasAny("las", "la", "mediodia", "medianoche") &&
                ParseClock(c, 0, out DateTime target, out _, out _))
            {
                var left = target - DateTime.Now;
                return left.TotalSeconds < 60 ? "Ya casi" + Sir + ": menos de un minuto." : "Faltan " + SayDuration(left) + " para " + SayTime(target) + ".";
            }
            if (c.Contains("cuantos dias faltan para") || c.Contains("cuanto falta para"))
            {
                string r = DaysUntil(c);
                if (r != null) return r;
            }

            // ---- cronómetro
            if (c.Has("cronometro"))
            {
                if (c.HasAny("inicia", "empieza", "arranca", "pon", "activa", "comienza", "iniciar"))
                {
                    _chrono = DateTime.Now;
                    return "Cronómetro en marcha.";
                }
                if (_chrono == null) return "No hay ningún cronómetro en marcha" + Sir + ".";
                var d = DateTime.Now - _chrono.Value;
                if (c.HasAny("para", "deten", "detén", "termina", "apaga", "pausa", "parar", "stop"))
                {
                    _chrono = null;
                    return "Cronómetro detenido en " + SayDuration(d) + ".";
                }
                return "Lleva " + SayDuration(d) + ".";
            }

            // ---- consultar y cancelar
            if (c.HasAny("temporizador", "temporizadores", "alarma", "alarmas", "recordatorio", "recordatorios", "avisos", "pendientes"))
            {
                string r = Manage(c);
                if (r != null) return r;
            }

            // ---- temporizador: «pon un temporizador de 5 minutos», «temporizador 10 minutos para la pasta»
            if (c.HasAny("temporizador", "cuenta", "timer") || (c.HasAny("avisame", "despiertame", "recuerdame", "dime") && c.Has("en") && !c.Has("las")))
            {
                if (ParseDuration(c, 0, out int secs, out int ds, out int de))
                {
                    string about = About(c, de, ds);
                    bool remind = c.HasAny("recuerdame") || (c.Has("avisame") && about != "");
                    var a = new Alarm
                    {
                        Id = DateTime.Now.Ticks,
                        Kind = remind ? "reminder" : "timer",
                        When = DateTime.Now.AddSeconds(secs),
                        Seconds = secs,
                        Text = about,
                    };
                    var list = Load();
                    list.Add(a);
                    Save(list);
                    if (remind) return "Se lo recordaré dentro de " + SayDuration(TimeSpan.FromSeconds(secs)) + Sir + ".";
                    return "Temporizador de " + SayDuration(TimeSpan.FromSeconds(secs)) + (about != "" ? " para " + about : "") + ".";
                }
            }

            // ---- alarma: «pon una alarma a las 7», «despiértame mañana a las 6 y media»
            if (c.HasAny("alarma", "despiertame", "despertador") || ((c.HasAny("recuerdame", "avisame", "recordar", "recuerda")) && (c.Has("las") || c.Has("manana") || c.HasAny("mediodia", "medianoche"))))
            {
                if (ParseClock(c, 0, out DateTime when, out int cs, out int ce))
                {
                    bool remind = c.HasAny("recuerdame", "avisame", "recordar", "recuerda") && !c.Has("alarma");
                    string repeat = ParseRepeat(c);
                    string about = StripRepeatWords(About(c, ce, cs));
                    if (remind && about == "") return "¿Qué quiere que le recuerde" + Sir + "?";
                    if (repeat != "") when = NextOccurrence(when.AddDays(-1), repeat, when.TimeOfDay);
                    var list = Load();
                    list.Add(new Alarm { Id = DateTime.Now.Ticks, Kind = remind ? "reminder" : "alarm", When = when, Text = about, Repeat = repeat });
                    Save(list);
                    string whenText = repeat != "" ? RepeatText(repeat) + " a " + SayTime(when) : SayDay(when) + " a " + SayTime(when);
                    return remind ? "Le recordaré " + about + " " + whenText + "." : "Alarma puesta " + (repeat != "" ? "" : "para ") + whenText + Sir + ".";
                }
                if (c.HasAny("alarma", "despiertame")) return "¿A qué hora" + Sir + "?";
            }
            return null;
        }

        // ---------------------------------------------------------------- repeticiones («todos los días», «de lunes a viernes», «cada martes»)

        static string ParseRepeat(Cmd c)
        {
            if (c.Contains("todos los dias") || c.Contains("cada dia") || c.HasAny("diario", "diariamente") || c.Contains("todas las mananas") || c.Contains("todas las noches") || c.Contains("todas las tardes"))
                return "daily";
            if (c.Contains("entre semana") || c.Contains("de lunes a viernes") || c.Contains("dias laborables") || c.Contains("dias de semana") || c.Contains("dias habiles"))
                return "weekdays";
            if (c.Contains("fines de semana") || c.Contains("fin de semana") && c.HasAny("cada", "todos"))
                return "weekends";
            for (int i = 1; i < c.Size; i++)
            {
                string w = c.W(i);
                string sing = w.EndsWith("s") && w != "lunes" && w != "martes" && w != "miercoles" && w != "jueves" && w != "viernes" ? w.Substring(0, w.Length - 1) : w;
                int d = Array.IndexOf(Weekdays, sing);
                if (d >= 0 && (c.W(i - 1) == "cada" || (c.W(i - 1) == "los" && c.W(i - 2) == "todos"))) return "w" + d;
            }
            return "";
        }

        static string StripRepeatWords(string t)
        {
            string o = System.Text.RegularExpressions.Regex.Replace(t ?? "",
                @"\b(todos los d[ií]as|cada d[ií]a|diariamente|a diario|todas las (ma[ñn]anas|noches|tardes)|entre semana|de lunes a viernes|d[ií]as (laborables|de semana|h[áa]biles)|(todos )?los fines de semana|cada fin de semana|(todos los|cada) (lunes|martes|mi[ée]rcoles|jueves|viernes|s[áa]bados?|domingos?))\b",
                "", System.Text.RegularExpressions.RegexOptions.IgnoreCase);
            return System.Text.RegularExpressions.Regex.Replace(o, @"\s+", " ").Trim(' ', ',', '.');
        }

        static bool Matches(DateTime d, string repeat) => repeat switch
        {
            "daily" => true,
            "weekdays" => d.DayOfWeek != DayOfWeek.Saturday && d.DayOfWeek != DayOfWeek.Sunday,
            "weekends" => d.DayOfWeek == DayOfWeek.Saturday || d.DayOfWeek == DayOfWeek.Sunday,
            _ => repeat.StartsWith("w") && int.TryParse(repeat.Substring(1), out int wd) && (int)d.DayOfWeek == wd,
        };

        // La próxima vez (después de «after») que toca, a esa hora.
        static DateTime NextOccurrence(DateTime after, string repeat, TimeSpan time)
        {
            var d = after.Date;
            for (int i = 0; i < 15; i++, d = d.AddDays(1))
            {
                var t = d + time;
                if (t > after && t > DateTime.Now && Matches(d, repeat)) return t;
            }
            return after.AddDays(1);
        }

        static string RepeatText(string r) => r switch
        {
            "daily" => "todos los días",
            "weekdays" => "de lunes a viernes",
            "weekends" => "los fines de semana",
            _ => r.StartsWith("w") && int.TryParse(r.Substring(1), out int d) ? "cada " + CultureInfo.GetCultureInfo("es-ES").DateTimeFormat.GetDayName((DayOfWeek)d) : "",
        };

        // Lo que hay que recordar: lo que queda fuera de la hora o duración («llamar a mamá»).
        static string About(Cmd c, int afterTime, int timeStart)
        {
            string[] intro = { "recuerdame", "avisame", "recordar", "recuerda", "pon", "un", "una", "temporizador", "alarma", "de", "para", "que", "dentro", "en", "despiertame", "me", "tengo", "debo", "hay" };
            string tail = afterTime >= 0 && afterTime < c.Size ? c.OrigFrom(afterTime) : "";
            string head = "";
            if (timeStart > 0)
            {
                int k = 0;
                while (k < timeStart && intro.Contains(c.W(k))) k++;
                int e = timeStart;
                while (e > k && Text.IsOneOf(c.W(e - 1), "en", "dentro", "de", "a", "para", "el", "las", "la")) e--;
                if (e > k) head = c.OrigFrom(k, e);
            }
            string t = (tail != "" ? tail : head).Trim(' ', '.', ',');
            var tc = Cmd.Parse(t);
            int s0 = 0;
            while (s0 < tc.Size && Text.IsOneOf(tc.W(s0), "que", "para", "de", "a")) s0++;
            if (s0 > 0) t = tc.OrigFrom(s0);
            if (Text.IsOneOf(Text.Squash(t), "temporizador", "alarma", "minutos", "")) return "";
            return t;
        }

        string Manage(Cmd c)
        {
            // «pon un temporizador de 5 minutos para la pasta» es crear, no consultar.
            if (!c.HasAny("cancela", "quita", "borra", "elimina", "anula", "cancelar", "borrar") &&
                (ParseDuration(c, 0, out _, out _, out _) || ParseClock(c, 0, out _, out _, out _))) return null;
            var list = Load();
            bool timers = c.HasAny("temporizador", "temporizadores");
            bool alarms = c.HasAny("alarma", "alarmas");
            bool rem = c.HasAny("recordatorio", "recordatorios", "avisos", "pendientes");
            string kind = timers ? "timer" : alarms ? "alarm" : "reminder";
            var mine = list.Where(a => rem && !timers && !alarms ? true : a.Kind == kind).ToList();
            string noun = timers ? "temporizador" : alarms ? "alarma" : "recordatorio";

            if (c.HasAny("cancela", "quita", "borra", "elimina", "apaga", "deten", "anula", "cancelar", "borrar") || c.W(0) == "para")
            {
                if (mine.Count == 0) return "No hay ningún " + (alarms ? "alarma" : noun) + " pendiente.";
                bool all = c.HasAny("todos", "todas") || mine.Count == 1;
                var gone = all ? mine : new List<Alarm> { mine.OrderBy(a => a.When).First() };
                foreach (var g in gone) list.RemoveAll(a => a.Id == g.Id);
                Save(list);
                return gone.Count == 1 ? Text.Capitalize(noun == "alarma" ? "alarma cancelada." : noun + " cancelado.") : "Cancelados " + gone.Count + ".";
            }
            if (c.HasAny("cuanto", "queda", "falta", "faltan", "quedan") && mine.Count > 0)
            {
                var n = mine.OrderBy(a => a.When).First();
                return "Quedan " + SayDuration(n.When - DateTime.Now) + (n.Text != "" ? " para " + n.Text : "") + ".";
            }
            if (c.HasAny("que", "cuales", "tengo", "hay", "lista", "dime", "muestra", "cuantos", "cuantas"))
            {
                if (mine.Count == 0) return "No tiene " + (timers ? "temporizadores" : alarms ? "alarmas" : "recordatorios") + " pendientes" + Sir + ".";
                var parts = mine.OrderBy(a => a.When).Take(5).Select(Describe).ToList();
                return (mine.Count == 1 ? "Tiene uno: " : "Tiene " + mine.Count + ": ") + string.Join("; ", parts) + ".";
            }
            return null;
        }

        static string Describe(Alarm a)
        {
            if (a.Kind == "timer") return "temporizador" + (a.Text != "" ? " de " + a.Text : "") + ", quedan " + SayDuration(a.When - DateTime.Now);
            string when = a.Repeat != "" ? RepeatText(a.Repeat) + " a " + SayTime(a.When) : SayDay(a.When) + " a " + SayTime(a.When);
            if (a.Kind == "alarm") return "alarma " + when;
            return a.Text + ", " + when;
        }

        string DaysUntil(Cmd c)
        {
            var today = DateTime.Today;
            var fixedDays = new Dictionary<string, (int m, int d)>
            {
                ["navidad"] = (12, 25), ["nochebuena"] = (12, 24), ["ano nuevo"] = (1, 1), ["fin de ano"] = (12, 31), ["nochevieja"] = (12, 31),
                ["halloween"] = (10, 31), ["san valentin"] = (2, 14), ["reyes"] = (1, 6),
            };
            foreach (var kv in fixedDays)
            {
                if (!c.Contains(kv.Key)) continue;
                var d = new DateTime(today.Year, kv.Value.m, kv.Value.d);
                if (d < today) d = d.AddYears(1);
                int n = (int)(d - today).TotalDays;
                return n == 0 ? "¡Es hoy" + Sir + "!" : "Faltan " + Text.Plural(n, "día", "días") + ".";
            }
            int wd = c.FindAny(Weekdays);
            if (wd >= 0)
            {
                int diff = ((Array.IndexOf(Weekdays, c.W(wd)) - (int)today.DayOfWeek) + 7) % 7;
                if (diff == 0) diff = 7;
                return "Faltan " + Text.Plural(diff, "día", "días") + ".";
            }
            if (c.Contains("fin de semana"))
            {
                int diff = ((6 - (int)today.DayOfWeek) + 7) % 7;
                return diff == 0 ? "Ya es fin de semana" + Sir + "." : "Faltan " + Text.Plural(diff, "día", "días") + " para el sábado.";
            }
            return null;
        }

        // ---------------------------------------------------------------- cada segundo

        public void Tick()
        {
            var list = Load();
            var due = list.Where(a => a.When <= DateTime.Now).ToList();
            if (due.Count == 0) return;
            foreach (var a in due)
            {
                list.RemoveAll(x => x.Id == a.Id);
                // Las que se repiten vuelven a la lista para la próxima vez.
                if (a.Repeat != "")
                    list.Add(new Alarm { Id = DateTime.Now.Ticks + list.Count, Kind = a.Kind, Text = a.Text, Repeat = a.Repeat, When = NextOccurrence(a.When, a.Repeat, a.When.TimeOfDay) });
                bool late = DateTime.Now - a.When > TimeSpan.FromMinutes(10);
                string msg = a.Kind == "timer"
                    ? "Ha terminado el temporizador" + (a.Text != "" ? " de " + a.Text : "") + Sir + "."
                    : a.Kind == "alarm"
                        ? (SayTime(DateTime.Now).StartsWith("la una") ? "Es " : "Son ") + SayTime(DateTime.Now) + Sir + ". Su alarma."
                        : (late ? "Tenía un recordatorio de " + SayTime(a.When) + ": " : "Le recuerdo" + Sir + ": ") + a.Text + ".";
                E.Host.Notify(E.S.Name, msg);
                E.Integrations?.Mirror(E.S.Name, msg);   // también al celular, si está activado
                E.Host.Say(msg);
            }
            Save(list);
        }
    }
}
