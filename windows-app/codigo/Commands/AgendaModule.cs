using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Threading.Tasks;
using Jarvis.Core;

namespace Jarvis.Commands
{
    // Agenda desde uno o varios enlaces iCal privados (Google Calendar: Configuración › tu calendario ›
    // «Dirección secreta en formato iCal»; Outlook: Calendario › Compartir › Publicar › ICS).
    public sealed class AgendaModule
    {
        readonly Engine E;
        static readonly HttpClient Http = Net.Create(TimeSpan.FromSeconds(20));
        static readonly CultureInfo Es = CultureInfo.GetCultureInfo("es-ES");
        List<CalEvent> _events = new List<CalEvent>();
        DateTime _loadedAt = DateTime.MinValue, _lastTry = DateTime.MinValue, _lastCheck = DateTime.MinValue;
        string _loadedFor = "";
        bool _loading;
        string _error = "";
        readonly HashSet<string> _alerted = new HashSet<string>();

        public AgendaModule(Engine e) { E = e; }
        string Sir => E.Sir;

        static string CacheFile => Path.Combine(Settings.Folder, "agenda.ics");

        List<string> Urls() => (E.S.CalendarUrl ?? "")
            .Split(new[] { ' ', '\n', '\r', ';', ',' }, StringSplitOptions.RemoveEmptyEntries)
            .Select(u => u.Trim())
            .Where(u => u.StartsWith("http", StringComparison.OrdinalIgnoreCase) || u.StartsWith("webcal", StringComparison.OrdinalIgnoreCase))
            .Select(u => u.StartsWith("webcal", StringComparison.OrdinalIgnoreCase) ? "https" + u.Substring(6) : u)
            .ToList();

        public bool Configured => Urls().Count > 0;

        public async Task Refresh(bool force = false)
        {
            var urls = Urls();
            string key = string.Join("|", urls);
            if (urls.Count == 0)
            {
                _events = new List<CalEvent>();
                return;
            }
            if (_loading) return;
            if (!force && key == _loadedFor && (DateTime.Now - _loadedAt).TotalMinutes < 15) return;
            if (!force && (DateTime.Now - _lastTry).TotalMinutes < 2 && key == _loadedFor) return;
            _loading = true;
            _lastTry = DateTime.Now;
            try
            {
                var texts = new List<string>();
                foreach (var u in urls)
                {
                    try { texts.Add(await Http.GetStringAsync(u)); }
                    catch (Exception ex)
                    {
                        _error = ex.Message;
                        Log.Write("Agenda (" + Text.Preview(u, 40) + "): " + ex.Message);
                    }
                }
                string all;
                if (texts.Count > 0)
                {
                    all = string.Join("\n", texts);
                    try { File.WriteAllText(CacheFile, all); } catch { }
                    _error = "";
                }
                else all = File.Exists(CacheFile) ? File.ReadAllText(CacheFile) : "";
                var from = DateTime.Today.AddDays(-1);
                _events = await Task.Run(() => ICal.Parse(all, from, DateTime.Today.AddDays(62)));
                _loadedAt = DateTime.Now;
                _loadedFor = key;
                Log.Write("Agenda: " + _events.Count + " eventos en los próximos dos meses.");
            }
            catch (Exception ex)
            {
                _error = ex.Message;
                Log.Write("Agenda: " + ex);
            }
            finally { _loading = false; }
        }

        // ---------------------------------------------------------------- textos

        static string When(CalEvent e) => e.AllDay ? "todo el día" : "a " + TimeModule.SayTime(e.Start);

        static string Describe(CalEvent e, bool withDay = false)
        {
            string t = (withDay ? TimeModule.SayDay(e.Start) + ", " : "") + When(e) + ": " + e.Summary;
            if (e.Location != "" && e.Location.Length < 60) t += ", en " + e.Location;
            return t;
        }

        IEnumerable<CalEvent> On(DateTime day) => _events.Where(e => e.AllDay ? e.Start.Date <= day.Date && e.End.Date > day.Date : e.Start.Date == day.Date);

        string DaySummary(DateTime day, string label, bool onlyRemaining)
        {
            var list = On(day).Where(e => !onlyRemaining || e.AllDay || e.End > DateTime.Now).ToList();
            if (list.Count == 0) return label == "hoy" && onlyRemaining && On(day).Any() ? "No le queda nada más hoy" + Sir + "." : "No tiene nada " + label + Sir + ".";
            var parts = list.Take(6).Select(e => Describe(e)).ToList();
            string head = list.Count == 1 ? Text.Capitalize(label) + " tiene una cosa: " : Text.Capitalize(label) + " tiene " + list.Count + " cosas: ";
            string more = list.Count > 6 ? " Y " + (list.Count - 6) + " más." : "";
            return head + string.Join("; ", parts) + "." + more;
        }

        public string TodayBrief()
        {
            if (!Configured || _events.Count == 0 && _loadedAt == DateTime.MinValue) return "";
            var today = On(DateTime.Today).Where(e => e.AllDay || e.End > DateTime.Now).ToList();
            if (today.Count == 0) return "Hoy no tiene nada en la agenda.";
            return (today.Count == 1 ? "Hoy tiene una cosa: " : "Hoy tiene " + today.Count + " cosas. ") +
                   (today.Count == 1 ? Describe(today[0]) + "." : "La primera, " + Describe(today[0]) + ".");
        }

        // ---------------------------------------------------------------- órdenes

        public async Task<string> TryAsync(Cmd c)
        {
            string s = c.Join(0);
            bool agendaWord = c.HasAny("agenda", "calendario", "citas", "cita", "reunion", "reuniones", "eventos", "evento", "compromisos", "planes");
            bool briefing = Text.IsOneOf(s, "resumen del dia", "informe del dia", "como viene el dia", "que me espera hoy", "dame el resumen del dia", "briefing", "ponme al dia", "pon al dia");
            bool goodMorning = Text.IsOneOf(s, "buenos dias", "buen dia") && DateTime.Now.Hour < 13;
            bool ask = agendaWord || briefing ||
                       Text.IsOneOf(s, "que tengo hoy", "que tengo manana", "que tengo pasado manana", "tengo algo hoy", "tengo algo manana", "que tengo esta semana",
                                    "que tengo la semana que viene", "que tengo ahora", "que me toca", "que me toca hoy", "que tengo despues", "que sigue") ||
                       (c.W(0) == "que" && c.W(1) == "tengo" && c.Size <= 4 && c.HasAny("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"));
            if (!ask && !goodMorning) return null;
            if (agendaWord && c.HasAny("abre", "abrir", "muestra", "ensename") && !c.HasAny("que", "cuando")) return null; // «abre el calendario» → programa

            if (!Configured)
            {
                if (goodMorning) return null;
                if (briefing) return await Brief(false);
                return "Aún no tengo acceso a su agenda" + Sir + ". En mis ajustes, pestaña Agenda, pegue la dirección secreta iCal de su calendario de Google u Outlook.";
            }
            if (c.HasAny("actualiza", "recarga", "sincroniza", "refresca"))
            {
                await Refresh(true);
                return _error != "" && _events.Count == 0 ? "No pude descargar la agenda: " + _error : "Agenda actualizada: " + Text.Plural(_events.Count(e => e.Start >= DateTime.Today), "evento próximo", "eventos próximos") + ".";
            }
            await Refresh();
            if (_events.Count == 0 && _error != "") return "No pude leer su agenda. Revise el enlace en los ajustes" + Sir + ".";

            if (briefing || goodMorning) return await Brief(goodMorning);

            // próxima
            if (c.HasAny("proxima", "proximo", "siguiente", "despues", "sigue", "ahora") || c.Contains("cuando es mi"))
            {
                var now = DateTime.Now;
                var cur = _events.FirstOrDefault(e => !e.AllDay && e.Start <= now && e.End > now);
                var next = _events.FirstOrDefault(e => !e.AllDay && e.Start > now);
                string r = "";
                if (cur != null && (c.Has("ahora") || s.Contains("me toca"))) r = "Ahora mismo: " + cur.Summary + ", hasta " + TimeModule.SayTime(cur.End) + ". ";
                if (next == null) return r == "" ? "No tiene nada más programado" + Sir + "." : r;
                var left = next.Start - now;
                return r + "Lo siguiente es " + next.Summary + ", " + TimeModule.SayDay(next.Start) + " a " + TimeModule.SayTime(next.Start) +
                       (left.TotalHours < 6 ? ", dentro de " + TimeModule.SayDuration(left) : "") + (next.Location != "" ? ", en " + next.Location : "") + ".";
            }
            if (c.HasAny("semana"))
            {
                var start = DateTime.Today;
                int days = c.Contains("semana que viene") || c.Contains("proxima semana") ? 7 : 7 - (((int)start.DayOfWeek + 6) % 7);
                if (c.Contains("semana que viene") || c.Contains("proxima semana")) start = start.AddDays(7 - (((int)start.DayOfWeek + 6) % 7));
                var list = _events.Where(e => e.Start.Date >= start && e.Start.Date < start.AddDays(days) && (e.AllDay || e.End > DateTime.Now)).ToList();
                if (list.Count == 0) return "No tiene nada esa semana" + Sir + ".";
                E.Host.Show(string.Join("\n", list.Select(e => e.Start.ToString("ddd d", Es) + " · " + (e.AllDay ? "todo el día" : e.Start.ToString("HH:mm")) + " · " + e.Summary)));
                return "Tiene " + list.Count + " eventos. " + string.Join("; ", list.Take(4).Select(e => Describe(e, true))) + (list.Count > 4 ? "; y más en el panel." : ".");
            }
            DateTime day = DateTime.Today;
            string label = "hoy";
            if (c.Contains("pasado manana")) { day = day.AddDays(2); label = "pasado mañana"; }
            else if (c.Has("manana")) { day = day.AddDays(1); label = "mañana"; }
            else
            {
                string[] names = { "domingo", "lunes", "martes", "miercoles", "jueves", "viernes", "sabado" };
                int k = c.FindAny(names);
                if (k >= 0)
                {
                    int wd = Array.IndexOf(names, c.W(k));
                    int diff = (wd - (int)DateTime.Today.DayOfWeek + 7) % 7;
                    if (diff == 0 && !c.Has("hoy")) diff = 7;
                    day = DateTime.Today.AddDays(diff);
                    label = "el " + day.ToString("dddd", Es);
                }
            }
            string res = DaySummary(day, label, day == DateTime.Today);
            var full = On(day).ToList();
            if (full.Count > 0) E.Host.Show(string.Join("\n", full.Select(e => (e.AllDay ? "Todo el día" : e.Start.ToString("HH:mm") + "–" + e.End.ToString("HH:mm")) + " · " + e.Summary + (e.Location != "" ? " (" + e.Location + ")" : ""))));
            return res;
        }

        // «Buenos días»: saludo, hora, el tiempo (si hay ciudad), agenda y avisos pendientes.
        public async Task<string> Brief(bool greeting)
        {
            var parts = new List<string>();
            int h = DateTime.Now.Hour;
            if (greeting) parts.Add((h < 12 ? "Buenos días" : "Buenas tardes") + Sir + ".");
            string t = TimeModule.SayTime(DateTime.Now);
            parts.Add((t.StartsWith("la una") ? "Es " : "Son ") + t + ", " + DateTime.Now.ToString("dddd d 'de' MMMM", Es) + ".");
            if (E.S.City.Trim() != "")
            {
                try
                {
                    string w = await E.Info.TryAsync(Cmd.Parse("qué tiempo hace"));
                    if (!string.IsNullOrEmpty(w) && !w.StartsWith("No ")) parts.Add(w);
                }
                catch { }
            }
            string ag = TodayBrief();
            if (ag != "") parts.Add(ag);
            var rem = E.Time.Pending.Where(a => a.When.Date == DateTime.Today).ToList();
            if (rem.Count > 0) parts.Add("Además tiene " + Text.Plural(rem.Count, "aviso", "avisos") + " para hoy.");
            return string.Join(" ", parts);
        }

        // ---------------------------------------------------------------- avisos antes de cada evento

        public void Tick()
        {
            if ((DateTime.Now - _lastCheck).TotalSeconds < 20) return;
            _lastCheck = DateTime.Now;
            if (!Configured) return;
            _ = Refresh();
            int mins = E.S.CalendarAlertMinutes;
            if (mins <= 0) return;
            var now = DateTime.Now;
            foreach (var e in _events.Where(e => !e.AllDay && e.Start > now && e.Start <= now.AddMinutes(mins)).ToList())
            {
                string key = e.Uid + "|" + e.Start.ToString("yyyyMMddHHmm");
                if (!_alerted.Add(key)) continue;
                int left = (int)Math.Round((e.Start - now).TotalMinutes);
                string msg = (left <= 1 ? "Ahora empieza " : "En " + Text.Plural(left, "minuto", "minutos") + ": ") + e.Summary + (e.Location != "" ? ", en " + e.Location : "") + ".";
                E.Host.Notify(E.S.Name + " · agenda", msg);
                E.Integrations?.Mirror("Agenda", msg);
                E.Host.Say(msg);
            }
        }
    }
}
