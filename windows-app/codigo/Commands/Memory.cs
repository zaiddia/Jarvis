using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using Jarvis.Core;

namespace Jarvis.Commands
{
    // Memoria a largo plazo: lo que el usuario cuenta de sí mismo («mi hermana se llama Ana», «me gusta el vallenato»,
    // «las llaves están en el cajón»). Se guarda en datos.json («memoria») y sobrevive a reinicios.
    // Un dato nuevo sobre lo mismo sustituye al viejo: «mi hermana se llama Laura» corrige a «… Ana».
    public static class Memory
    {
        const string Key = "memoria";
        const int Max = 300;

        public static List<string> All() => Store.Get(Key, new List<string>());

        public static void Save(IEnumerable<string> facts) =>
            Store.Set(Key, facts.Select(f => (f ?? "").Trim()).Where(f => f != "").Distinct(StringComparer.OrdinalIgnoreCase).TakeLast(Max).ToList());

        public static void Clear() => Store.Set(Key, new List<string>());

        // Devuelve true si corrigió un dato que ya tenía.
        public static bool Add(string fact)
        {
            fact = Text.Capitalize((fact ?? "").Trim().TrimEnd('.', ' '));
            if (fact == "") return false;
            var list = All();
            string topic = Topic(fact);
            int removed = topic == "" ? 0 : list.RemoveAll(f => Topic(f) == topic);
            list.RemoveAll(f => Text.Squash(f) == Text.Squash(fact));
            list.Add(fact);
            Save(list);
            return removed > 0;
        }

        // Quita los datos que hablan de eso. Devuelve cuántos quitó.
        public static int Forget(string what)
        {
            string w = Text.Squash(what);
            if (w == "") return 0;
            var keys = Words(w);
            var list = All();
            int n = list.RemoveAll(f =>
            {
                string sf = Text.Squash(f);
                return sf.Contains(w) || w.Contains(sf) || (keys.Count > 0 && keys.All(k => Words(sf).Contains(k)));
            });
            if (n > 0) Save(list);
            return n;
        }

        // «De qué trata» un dato, para sustituir el viejo: «mi hermana se llama Ana» → «mi hermana»,
        // «las llaves están en el cajón» → «las llaves», «vivo en Cali» → «vivo en». Vacío = no sustituye a nada.
        static readonly Regex TopicRx = new Regex(@"^(?<t>(mi|mis|el|la|los|las|nuestro|nuestra) [a-z ]{2,40}?) (se llama|se llaman|es|son|esta|estan|queda|quedan|cumple|cumplen|nacio|vive|viven|trabaja)\b", RegexOptions.Compiled);

        static string Topic(string fact)
        {
            string s = Text.Squash(fact);
            var m = TopicRx.Match(s);
            if (m.Success) return m.Groups["t"].Value;
            foreach (var p in new[] { "vivo en", "trabajo en", "trabajo como", "trabajo de", "estudio en", "estudio", "me llamo", "mi nombre es", "soy de" })
                if (s.StartsWith(p + " ")) return p;
            return "";
        }

        static readonly HashSet<string> Stop = new HashSet<string>
        {
            "que", "como", "cual", "cuales", "donde", "cuando", "quien", "quienes", "para", "porque", "esta", "estan", "este", "esto", "eso",
            "tengo", "tiene", "dije", "dijo", "sabes", "recuerdas", "acuerdas", "llama", "llaman", "deje", "puse", "sobre", "algo", "tambien", "pero",
        };

        static List<string> Words(string squashed) => squashed.Split(' ', StringSplitOptions.RemoveEmptyEntries).Where(w => w.Length > 3 && !Stop.Contains(w)).ToList();

        static bool Near(string a, string b) => a == b || (a.Length > 4 && b.Length > 4 && a.Substring(0, 5) == b.Substring(0, 5));

        // Lo que conviene que la IA tenga presente para esta pregunta: lo relacionado y lo más reciente.
        public static List<string> Relevant(string question, int related = 20, int recent = 12)
        {
            var all = All();
            if (all.Count <= related + recent) return all;
            var q = Words(Text.Squash(question ?? ""));
            var rel = all.Select((f, i) => (f, i, score: Words(Text.Squash(f)).Count(w => q.Any(x => Near(x, w)))))
                         .Where(x => x.score > 0).OrderByDescending(x => x.score).ThenByDescending(x => x.i).Take(related).Select(x => x.f);
            return rel.Concat(all.TakeLast(recent)).Distinct().ToList();
        }

        // El dato que contesta una pregunta («¿cómo se llama mi hermana?»), o null.
        public static string Find(string question)
        {
            var keys = Words(Text.Squash(question));
            if (keys.Count == 0) return null;
            return All().LastOrDefault(f =>
            {
                var fw = Words(Text.Squash(f));
                return keys.All(k => fw.Any(w => Near(k, w)));
            });
        }

        // «Mi hermana se llama Ana» → «Su hermana se llama Ana» (para decírselo al usuario).
        static readonly Dictionary<string, string> Second = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["mi"] = "su", ["mis"] = "sus", ["me"] = "le", ["yo"] = "usted", ["soy"] = "es", ["estoy"] = "está", ["vivo"] = "vive",
            ["trabajo"] = "trabaja", ["estudio"] = "estudia", ["tengo"] = "tiene", ["conmigo"] = "con usted", ["dejé"] = "dejó", ["deje"] = "dejó",
            ["puse"] = "puso", ["prefiero"] = "prefiere", ["odio"] = "odia", ["llamo"] = "llama", ["nací"] = "nació",
        };

        public static string ToSecondPerson(string fact)
        {
            var words = (fact ?? "").Split(' ');
            for (int i = 0; i < words.Length; i++)
            {
                string w = words[i], core = w.Trim(',', '.', ';', ':');
                if (core == "") continue;
                // «trabajo» o «estudio» solo como verbo, al principio («mi trabajo es…» no cambia).
                if ((core.Equals("trabajo", StringComparison.OrdinalIgnoreCase) || core.Equals("estudio", StringComparison.OrdinalIgnoreCase)) && i > 0) continue;
                if (Second.TryGetValue(core, out var to))
                {
                    if (char.IsUpper(core[0])) to = Text.Capitalize(to);
                    words[i] = w.Replace(core, to);
                }
            }
            return string.Join(" ", words);
        }
    }
}
