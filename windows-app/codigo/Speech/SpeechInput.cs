using System;
using System.Linq;
using Jarvis.Core;

namespace Jarvis.Speech
{
    // Lo que la aplicación necesita de «la escucha», sea cual sea el reconocedor de Windows que se use.
    public interface ISpeechInput : IDisposable
    {
        event Action Woke;                 // dijo solo «Jarvis»: espera la orden
        event Action<string> Heard;        // una orden completa (sin el nombre)
        event Action<string> Partial;      // lo que va entendiendo mientras habla
        event Action<int> Level;           // nivel del micrófono 0…100
        event Action<bool> AwakeChanged;
        string Status { get; }
        bool Running { get; }
        bool Awake { get; }
        string RecognizerName { get; }
        bool Start();
        void Stop();
        void Update(Settings s);
        void UseSettings(Settings s);      // cambia los ajustes sin reiniciar la escucha
        Func<string, bool> EchoCheck { get; set; }   // ¿esto que oyó es su propia voz?
        void Pause();
        void Resume();
        void Listen(double seconds);
        void Sleep();
    }

    public static class SpeechInput
    {
        // «auto»: el reconocimiento moderno de Windows (el de dictado, entiende el español de verdad);
        // si no está disponible, el clásico (con Whisper si está instalado).
        public static ISpeechInput Create(Settings s, out string why)
        {
            why = "";
            string mode = (s.Recognizer ?? "auto").ToLowerInvariant();
            if (mode != "clasico")
            {
                var modern = new ModernListener(s);
                if (modern.Start()) return modern;
                why = modern.Status;
                Log.Write("Reconocimiento moderno no disponible: " + why);
                modern.Dispose();
                if (mode == "moderno") return new FailedInput(why);
            }
            var classic = new Listener(s);
            if (classic.Start()) return classic;
            why = why == "" ? classic.Status : why + ". Y el clásico: " + classic.Status;
            classic.Dispose();
            return new FailedInput(why);
        }
    }

    // Cuando no se puede escuchar: no hace nada, pero dice por qué.
    public sealed class FailedInput : ISpeechInput
    {
        public FailedInput(string why) { Status = why; }
#pragma warning disable CS0067
        public event Action Woke;
        public event Action<string> Heard;
        public event Action<string> Partial;
        public event Action<int> Level;
        public event Action<bool> AwakeChanged;
#pragma warning restore CS0067
        public string Status { get; }
        public bool Running => false;
        public bool Awake => false;
        public string RecognizerName => "";
        public bool Start() => false;
        public void Stop() { }
        public void Update(Settings s) { }
        public void UseSettings(Settings s) { }
        public Func<string, bool> EchoCheck { get; set; }
        public void Pause() { }
        public void Resume() { }
        public void Listen(double seconds) { }
        public void Sleep() { }
        public void Dispose() { }
    }

    // Reconocer el nombre de la llamada aunque el dictado lo escriba «Yarvis», «Jarbis», «Charvis»…
    public static class WakeWords
    {
        // Los nombres a los que responde: el elegido y, siempre, «Jarvis» y «Viernes»
        // (al cambiar a VIERNES antes dejaba de responder a «Jarvis» y parecía que el micrófono no iba).
        public static string[] Names(Settings s)
        {
            var list = new System.Collections.Generic.List<string>();
            foreach (var n in new[] { s.WakeWord, "Jarvis", "Viernes" })
                if (!string.IsNullOrWhiteSpace(n) && !list.Any(x => Text.Squash(x) == Text.Squash(n))) list.Add(n.Trim());
            return list.ToArray();
        }

        public static string Strip(string text, Settings s, out bool had)
        {
            foreach (var n in Names(s))
            {
                string r = Strip(text, n, out had);
                if (had) return r;
            }
            had = false;
            return text;
        }

        public static string Strip(string text, string wakeWord, out bool had)
        {
            had = false;
            string wake = Text.Squash(wakeWord);
            var words = (text ?? "").Split(new[] { ' ', ',' }, StringSplitOptions.RemoveEmptyEntries).ToList();
            for (int i = 0; i < Math.Min(3, words.Count); i++)
            {
                string w = Text.Squash(words[i]);
                if (Similar(w, wake))
                {
                    had = true;
                    return string.Join(" ", words.Skip(i + 1)).Trim(' ', ',', '.');
                }
                // «Jar vis»: el dictado a veces lo parte en dos.
                if (i + 1 < words.Count && Similar(w + Text.Squash(words[i + 1]), wake))
                {
                    had = true;
                    return string.Join(" ", words.Skip(i + 2)).Trim(' ', ',', '.');
                }
                if (!Text.IsOneOf(w, "oye", "hola", "hey", "ey", "ok", "okay", "vale", "buenos", "buenas", "dias", "tardes", "noches", "a", "e")) break;
            }
            // «…, Jarvis» al final (pero «el viernes» es un día, no VIERNES).
            if (words.Count > 1 && Similar(Text.Squash(words[^1]), wake) &&
                !Text.IsOneOf(Text.Squash(words[^2]), "el", "este", "proximo", "cada", "del", "los", "hasta", "para"))
            {
                had = true;
                return string.Join(" ", words.Take(words.Count - 1)).Trim(' ', ',', '.');
            }
            return text;
        }

        public static bool Similar(string a, string b)
        {
            a = (a ?? "").Replace(" ", "");
            if (a == b) return true;
            if (b == "jarvis" && Text.IsOneOf(a, "yarvis", "jarbis", "yarbis", "charvis", "jarvi", "jarvys", "jervis", "jarvez", "harvis", "garvis", "javis", "jarviz", "llarvis")) return true;
            if (b == "viernes" && Text.IsOneOf(a, "bierness", "biernes", "viernez")) return true;
            if (Math.Abs(a.Length - b.Length) > 2 || a.Length < 4) return false;
            var d = new int[a.Length + 1, b.Length + 1];
            for (int i = 0; i <= a.Length; i++) d[i, 0] = i;
            for (int j = 0; j <= b.Length; j++) d[0, j] = j;
            for (int i = 1; i <= a.Length; i++)
                for (int j = 1; j <= b.Length; j++)
                    d[i, j] = Math.Min(Math.Min(d[i - 1, j] + 1, d[i, j - 1] + 1), d[i - 1, j - 1] + (a[i - 1] == b[j - 1] ? 0 : 1));
            return d[a.Length, b.Length] <= (b.Length >= 6 ? 2 : 1);
        }
    }
}
