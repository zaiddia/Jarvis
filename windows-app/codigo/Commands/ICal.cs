using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text;

namespace Jarvis.Commands
{
    public sealed class CalEvent
    {
        public string Uid = "", Summary = "", Location = "";
        public DateTime Start, End;      // hora local del equipo
        public bool AllDay;
    }

    // Lector de calendarios iCal (.ics): Google Calendar, Outlook, iCloud…
    // Entiende eventos repetidos (RRULE), excepciones (EXDATE), cambios de una sola repetición (RECURRENCE-ID) y zonas horarias.
    public static class ICal
    {
        sealed class Prop
        {
            public string Name = "", Value = "";
            public Dictionary<string, string> P = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        }

        sealed class Raw
        {
            public List<Prop> Props = new List<Prop>();
            public Prop Get(string n) => Props.FirstOrDefault(p => p.Name == n);
            public IEnumerable<Prop> All(string n) => Props.Where(p => p.Name == n);
        }

        static IEnumerable<string> Unfold(string text)
        {
            var lines = text.Replace("\r\n", "\n").Replace('\r', '\n').Split('\n');
            var cur = new StringBuilder();
            foreach (var l in lines)
            {
                if (l.Length > 0 && (l[0] == ' ' || l[0] == '\t')) { cur.Append(l, 1, l.Length - 1); continue; }
                if (cur.Length > 0) yield return cur.ToString();
                cur.Clear();
                cur.Append(l);
            }
            if (cur.Length > 0) yield return cur.ToString();
        }

        static Prop ParseLine(string line)
        {
            int colon = -1;
            bool q = false;
            for (int i = 0; i < line.Length; i++)
            {
                if (line[i] == '"') q = !q;
                else if (line[i] == ':' && !q) { colon = i; break; }
            }
            if (colon < 0) return null;
            var head = line.Substring(0, colon).Split(';');
            var p = new Prop { Name = head[0].Trim().ToUpperInvariant(), Value = line.Substring(colon + 1) };
            for (int i = 1; i < head.Length; i++)
            {
                int eq = head[i].IndexOf('=');
                if (eq > 0) p.P[head[i].Substring(0, eq)] = head[i].Substring(eq + 1).Trim('"');
            }
            return p;
        }

        static string Unescape(string v) => v.Replace("\\n", " ").Replace("\\N", " ").Replace("\\,", ",").Replace("\\;", ";").Replace("\\\\", "\\").Trim();

        static TimeZoneInfo Zone(string id)
        {
            if (string.IsNullOrWhiteSpace(id)) return null;
            id = id.Trim().Trim('"');
            try { return TimeZoneInfo.FindSystemTimeZoneById(id); } catch { }
            try
            {
                if (TimeZoneInfo.TryConvertIanaIdToWindowsId(id, out string win)) return TimeZoneInfo.FindSystemTimeZoneById(win);
            }
            catch { }
            return null;
        }

        // Fecha en «hora de pared» de su zona: kind = Utc, zona concreta o flotante (null = hora local).
        struct Stamp
        {
            public DateTime Wall;
            public bool Utc, DateOnly;
            public TimeZoneInfo Tz;

            public DateTime ToLocal(DateTime wall)
            {
                if (DateOnly) return wall.Date;
                if (Utc) return DateTime.SpecifyKind(wall, DateTimeKind.Utc).ToLocalTime();
                if (Tz != null)
                {
                    try { return TimeZoneInfo.ConvertTime(DateTime.SpecifyKind(wall, DateTimeKind.Unspecified), Tz, TimeZoneInfo.Local); }
                    catch { return wall; }
                }
                return wall;
            }
        }

        static bool ParseStamp(Prop p, out Stamp s)
        {
            s = default;
            if (p == null) return false;
            string v = p.Value.Trim();
            if (v.Contains(',')) v = v.Split(',')[0];
            bool dateOnly = (p.P.TryGetValue("VALUE", out var val) && val.Equals("DATE", StringComparison.OrdinalIgnoreCase)) || v.Length == 8;
            if (dateOnly)
            {
                if (!DateTime.TryParseExact(v.Substring(0, Math.Min(8, v.Length)), "yyyyMMdd", CultureInfo.InvariantCulture, DateTimeStyles.None, out var d)) return false;
                s = new Stamp { Wall = d, DateOnly = true };
                return true;
            }
            bool utc = v.EndsWith("Z");
            string core = utc ? v.Substring(0, v.Length - 1) : v;
            if (!DateTime.TryParseExact(core, new[] { "yyyyMMdd'T'HHmmss", "yyyyMMdd'T'HHmm" }, CultureInfo.InvariantCulture, DateTimeStyles.None, out var t)) return false;
            s = new Stamp { Wall = t, Utc = utc, Tz = utc ? null : Zone(p.P.TryGetValue("TZID", out var tz) ? tz : null) };
            return true;
        }

        static IEnumerable<DateTime> Stamps(Prop p, Stamp like)
        {
            foreach (var part in p.Value.Split(','))
            {
                var one = new Prop { Name = p.Name, Value = part, P = p.P };
                if (ParseStamp(one, out var s)) yield return s.ToLocal(s.Wall);
            }
        }

        static TimeSpan ParseDuration(string v)
        {
            v = (v ?? "").Trim().ToUpperInvariant();
            bool neg = v.StartsWith("-");
            v = v.TrimStart('-', '+');
            if (!v.StartsWith("P")) return TimeSpan.Zero;
            var t = TimeSpan.Zero;
            int num = 0;
            bool time = false;
            foreach (char ch in v.Substring(1))
            {
                if (char.IsDigit(ch)) { num = num * 10 + (ch - '0'); continue; }
                switch (ch)
                {
                    case 'T': time = true; break;
                    case 'W': t += TimeSpan.FromDays(7 * num); break;
                    case 'D': t += TimeSpan.FromDays(num); break;
                    case 'H': t += TimeSpan.FromHours(num); break;
                    case 'M': t += time ? TimeSpan.FromMinutes(num) : TimeSpan.FromDays(30 * num); break;
                    case 'S': t += TimeSpan.FromSeconds(num); break;
                }
                num = 0;
            }
            return neg ? -t : t;
        }

        static readonly string[] Days = { "SU", "MO", "TU", "WE", "TH", "FR", "SA" };

        // Repeticiones (en hora de pared) desde start, hasta «to».
        static IEnumerable<DateTime> Repeat(DateTime start, string rule, DateTime to, Func<DateTime, DateTime> toLocal)
        {
            var r = rule.Split(';').Select(x => x.Split('=')).Where(x => x.Length == 2).ToDictionary(x => x[0].ToUpperInvariant(), x => x[1].ToUpperInvariant());
            string freq = r.TryGetValue("FREQ", out var f) ? f : "";
            int interval = r.TryGetValue("INTERVAL", out var iv) && int.TryParse(iv, out int ivn) && ivn > 0 ? ivn : 1;
            int count = r.TryGetValue("COUNT", out var cn) && int.TryParse(cn, out int cnn) ? cnn : int.MaxValue;
            DateTime until = DateTime.MaxValue;
            if (r.TryGetValue("UNTIL", out var un))
            {
                var up = new Prop { Name = "UNTIL", Value = un };
                if (ParseStamp(up, out var us)) until = us.DateOnly ? us.Wall.AddDays(1).AddTicks(-1) : us.Utc ? DateTime.SpecifyKind(us.Wall, DateTimeKind.Utc).ToLocalTime() : us.Wall;
            }
            var byDay = r.TryGetValue("BYDAY", out var bd) ? bd.Split(',').Where(x => x.Length >= 2).ToList() : new List<string>();
            var byMonthDay = r.TryGetValue("BYMONTHDAY", out var bmd) ? bmd.Split(',').Select(x => int.TryParse(x, out int n) ? n : 0).Where(n => n != 0).ToList() : new List<int>();
            var byMonth = r.TryGetValue("BYMONTH", out var bm) ? bm.Split(',').Select(x => int.TryParse(x, out int n) ? n : 0).Where(n => n > 0).ToList() : new List<int>();

            int emitted = 0;
            var tod = start.TimeOfDay;
            for (int period = 0; period < 40000; period++)
            {
                var cands = new List<DateTime>();
                switch (freq)
                {
                    case "DAILY":
                        cands.Add(start.AddDays((double)period * interval));
                        break;
                    case "WEEKLY":
                    {
                        var weekStart = start.Date.AddDays(-(((int)start.DayOfWeek + 6) % 7)).AddDays(7.0 * period * interval);
                        if (byDay.Count == 0) cands.Add(start.AddDays(7.0 * period * interval));
                        else
                            foreach (var d in byDay)
                            {
                                int wd = Array.IndexOf(Days, d.Substring(d.Length - 2));
                                if (wd < 0) continue;
                                cands.Add(weekStart.AddDays((wd + 6) % 7) + tod);
                            }
                        break;
                    }
                    case "MONTHLY":
                    {
                        var m = new DateTime(start.Year, start.Month, 1).AddMonths(period * interval);
                        int dim = DateTime.DaysInMonth(m.Year, m.Month);
                        if (byMonthDay.Count > 0)
                        {
                            foreach (int md in byMonthDay)
                            {
                                int day = md > 0 ? md : dim + md + 1;
                                if (day >= 1 && day <= dim) cands.Add(m.AddDays(day - 1) + tod);
                            }
                        }
                        else if (byDay.Count > 0)
                        {
                            foreach (var d in byDay)
                            {
                                int wd = Array.IndexOf(Days, d.Substring(d.Length - 2));
                                if (wd < 0) continue;
                                int.TryParse(d.Substring(0, d.Length - 2), out int nth);
                                var all = Enumerable.Range(0, dim).Select(i => m.AddDays(i)).Where(x => (int)x.DayOfWeek == wd).ToList();
                                if (nth == 0) cands.AddRange(all.Select(x => x + tod));
                                else if (nth > 0 && nth <= all.Count) cands.Add(all[nth - 1] + tod);
                                else if (nth < 0 && -nth <= all.Count) cands.Add(all[all.Count + nth] + tod);
                            }
                        }
                        else if (start.Day <= dim) cands.Add(m.AddDays(start.Day - 1) + tod);
                        break;
                    }
                    case "YEARLY":
                    {
                        int y = start.Year + period * interval;
                        var months = byMonth.Count > 0 ? byMonth : new List<int> { start.Month };
                        foreach (int mo in months)
                        {
                            int dim = DateTime.DaysInMonth(y, mo);
                            if (byMonthDay.Count > 0)
                                foreach (int md in byMonthDay)
                                {
                                    int day = md > 0 ? md : dim + md + 1;
                                    if (day >= 1 && day <= dim) cands.Add(new DateTime(y, mo, day) + tod);
                                }
                            else if (start.Day <= dim) cands.Add(new DateTime(y, mo, start.Day) + tod);
                        }
                        break;
                    }
                    default:
                        yield break;
                }
                bool any = false;
                foreach (var c in cands.OrderBy(x => x))
                {
                    if (c < start) continue;
                    if (byMonth.Count > 0 && freq != "YEARLY" && !byMonth.Contains(c.Month)) continue;
                    if (c > until || emitted >= count) yield break;
                    if (toLocal(c) > to) yield break;
                    emitted++;
                    any = true;
                    yield return c;
                }
                if (!any && cands.Count > 0 && cands.Min() > until) yield break;
            }
        }

        public static List<CalEvent> Parse(string ics, DateTime from, DateTime to)
        {
            var raws = new List<Raw>();
            Raw cur = null;
            int depth = 0;
            foreach (var line in Unfold(ics ?? ""))
            {
                if (line.StartsWith("BEGIN:VEVENT", StringComparison.OrdinalIgnoreCase)) { cur = new Raw(); depth = 0; continue; }
                if (cur == null) continue;
                if (line.StartsWith("BEGIN:", StringComparison.OrdinalIgnoreCase)) { depth++; continue; }   // VALARM dentro del evento
                if (line.StartsWith("END:", StringComparison.OrdinalIgnoreCase))
                {
                    if (depth > 0) { depth--; continue; }
                    raws.Add(cur);
                    cur = null;
                    continue;
                }
                if (depth > 0) continue;
                var p = ParseLine(line);
                if (p != null) cur.Props.Add(p);
            }

            var outList = new List<CalEvent>();
            // Repeticiones cambiadas a mano: UID + hora original → se sustituye.
            var overrides = new HashSet<string>();
            foreach (var r in raws)
            {
                var rid = r.Get("RECURRENCE-ID");
                if (rid != null && ParseStamp(rid, out var rs)) overrides.Add((r.Get("UID")?.Value ?? "") + "|" + rs.ToLocal(rs.Wall).ToString("yyyyMMddHHmm"));
            }

            foreach (var r in raws)
            {
                if ((r.Get("STATUS")?.Value ?? "").Trim().Equals("CANCELLED", StringComparison.OrdinalIgnoreCase)) continue;
                if (!ParseStamp(r.Get("DTSTART"), out var st)) continue;
                string uid = r.Get("UID")?.Value ?? Guid.NewGuid().ToString();
                string summary = Unescape(r.Get("SUMMARY")?.Value ?? "(sin título)");
                string location = Unescape(r.Get("LOCATION")?.Value ?? "");
                TimeSpan dur;
                if (ParseStamp(r.Get("DTEND"), out var en)) dur = en.Wall - st.Wall;
                else if (r.Get("DURATION") != null) dur = ParseDuration(r.Get("DURATION").Value);
                else dur = st.DateOnly ? TimeSpan.FromDays(1) : TimeSpan.Zero;
                if (dur < TimeSpan.Zero) dur = TimeSpan.Zero;

                var ex = new HashSet<string>();
                foreach (var e in r.All("EXDATE"))
                    foreach (var d in Stamps(e, st)) ex.Add(d.ToString("yyyyMMddHHmm"));

                bool isOverride = r.Get("RECURRENCE-ID") != null;
                var rule = r.Get("RRULE")?.Value;
                IEnumerable<DateTime> walls = rule != null && !isOverride
                    ? Repeat(st.Wall, rule, to, w => st.ToLocal(w))
                    : new[] { st.Wall };
                foreach (var w in walls)
                {
                    var s = st.ToLocal(w);
                    var e = st.DateOnly ? s.Add(dur) : st.ToLocal(w + dur);
                    string key = s.ToString("yyyyMMddHHmm");
                    if (ex.Contains(key)) continue;
                    if (!isOverride && rule != null && overrides.Contains(uid + "|" + key)) continue;
                    if (e < from && !(e == s && s >= from)) continue;
                    if (s > to) continue;
                    outList.Add(new CalEvent { Uid = uid, Summary = summary, Location = location, Start = s, End = e, AllDay = st.DateOnly });
                }
            }
            return outList.OrderBy(e => e.Start).ThenBy(e => e.Summary).ToList();
        }
    }
}
