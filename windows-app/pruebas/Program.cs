using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using Jarvis.Commands;
using Jarvis.Core;
#if COMPLETO
using Jarvis.Speech;
#endif

namespace Jarvis.Pruebas
{
    // Pruebas automáticas de JARVIS. Lee frases.txt y comprueba cada línea:
    //   frase -> palabras    cómo queda la orden tras quitar cortesías y normalizar los verbos
    //   frase = texto        la cuenta debe contener ese texto («cuánto es 25 por 4 = 100»)
    //   frase => Módulo      qué parte de JARVIS la atiende (IA = ninguna: se la pasa a la IA). Solo en Windows.
    //   frase ~> resto       quita el nombre de llamada («oye Jarvis pon música ~> pon música»). Solo en Windows.
    //   frase ++ a | b       se parte en varias órdenes seguidas. Solo en Windows.
    // Varias respuestas válidas se separan con «|». Devuelve 1 si alguna falla (así GitHub marca el error).
    public static class Program
    {
        static int _ok, _fail, _skip;
        static readonly List<string> Failures = new List<string>();

        public static async Task<int> Main(string[] args)
        {
            Console.OutputEncoding = Encoding.UTF8;
            string file = args.Length > 0 ? args[0] : Path.Combine(AppContext.BaseDirectory, "frases.txt");
            var lines = File.ReadAllLines(file, Encoding.UTF8);
#if COMPLETO
            var host = new FakeHost();
            var engine = new Engine(host);
            Console.WriteLine("Pruebas completas (motor de órdenes de Windows).");
#else
            Console.WriteLine("Pruebas básicas (texto y cuentas). El motor completo se prueba en Windows.");
#endif
            int n = 0;
            foreach (var raw in lines)
            {
                n++;
                string line = raw.Trim();
                if (line == "" || line.StartsWith("#")) continue;
                try
                {
                    if (Split(line, "=>", out var a, out var b))
                    {
#if COMPLETO
                        await Route(engine, n, a, b);
#else
                        _skip++;
#endif
                    }
                    else if (Split(line, "~>", out a, out b))
                    {
#if COMPLETO
                        string rest = WakeWords.Strip(a, host.Settings, out bool had);
                        Check(n, a, Text.Squash(rest), b, had ? "" : " (no reconoció el nombre)");
#else
                        _skip++;
#endif
                    }
                    else if (Split(line, "++", out a, out b))
                    {
#if COMPLETO
                        var parts = Engine.SplitChain(a).Select(Text.Squash);
                        Check(n, a, string.Join(" | ", parts), string.Join(" | ", b.Split('|').Select(Text.Squash)), "", exact: true);
#else
                        _skip++;
#endif
                    }
                    else if (Split(line, "->", out a, out b))
                        Check(n, a, Cmd.Parse(a).Join(0), b);
                    else if (Split(line, "=", out a, out b))
                    {
                        string r = Calc.Answer(a, "") ?? "(no la entendió como cuenta)";
                        bool good = b.Split('|').Any(x => Text.Squash(r).Contains(Text.Squash(x)) || r.Contains(x.Trim()));
                        Report(n, good, a, r, b);
                    }
                    else
                    {
                        Report(n, false, line, "línea sin «->», «=», «=>», «~>» ni «++»", "");
                    }
                }
                catch (Exception e)
                {
                    Report(n, false, line, "excepción: " + e.GetType().Name + ": " + e.Message, "");
                }
            }

            Console.WriteLine();
            Console.WriteLine($"Correctas: {_ok}   Fallidas: {_fail}" + (_skip > 0 ? $"   Solo en Windows: {_skip}" : ""));
            if (Failures.Count > 0)
            {
                Console.WriteLine();
                Console.WriteLine("FALLOS:");
                foreach (var f in Failures) Console.WriteLine(f);
            }
            // En GitHub, un resumen visible en la página de la compilación.
            string summary = Environment.GetEnvironmentVariable("GITHUB_STEP_SUMMARY");
            if (!string.IsNullOrEmpty(summary))
            {
                var sb = new StringBuilder();
                sb.AppendLine("### Pruebas de comprensión: " + _ok + " correctas, " + _fail + " fallidas");
                if (Failures.Count > 0)
                {
                    sb.AppendLine("```");
                    foreach (var f in Failures) sb.AppendLine(f);
                    sb.AppendLine("```");
                }
                File.AppendAllText(summary, sb.ToString());
            }
            return _fail > 0 ? 1 : 0;
        }

        static bool Split(string line, string sep, out string a, out string b)
        {
            int k = line.IndexOf(" " + sep + " ", StringComparison.Ordinal);
            if (k < 0) { a = b = null; return false; }
            a = line.Substring(0, k).Trim();
            b = line.Substring(k + sep.Length + 2).Trim();
            return true;
        }

        static void Check(int n, string input, string got, string expected, string note = "", bool exact = false)
        {
            var options = expected.Split('|').Select(x => x.Trim()).ToList();
            bool good = exact ? got == expected : options.Contains(got);
            Report(n, good, input, got + note, expected);
        }

        static void Report(int n, bool good, string input, string got, string expected)
        {
            if (good) { _ok++; return; }
            _fail++;
            Failures.Add($"  línea {n}: «{input}»\n      esperaba: {expected}\n      obtuve:   {got}");
        }

#if COMPLETO
        static async Task Route(Engine engine, int n, string phrase, string expected)
        {
            var task = engine.HandleAsync(phrase);
            if (await Task.WhenAny(task, Task.Delay(TimeSpan.FromSeconds(40))) != task)
            {
                Report(n, false, phrase, "tardó más de 40 s", expected);
                return;
            }
            var reply = await task;
            string who = reply == null ? "IA" : (engine.LastHandler == "" ? "Motor" : engine.LastHandler);
            var options = expected.Split('|').Select(x => x.Trim()).ToList();
            bool good = options.Any(o => o == who || (o.EndsWith("*") && who.StartsWith(o.TrimEnd('*'))));
            string said = reply == null ? "" : " — «" + Text.Preview(reply.Say, 70) + "»";
            Report(n, good, phrase, who + said, expected);
        }

        // Una «aplicación» de mentira: el motor cree que hay ventana, bandeja y voz, pero no hace nada.
        sealed class FakeHost : IHost
        {
            public Settings Settings { get; } = new Settings();
            public void Say(string text) { }
            public void Show(string text) { }
            public void Notify(string title, string text) { }
            public void StopSpeaking() { }
            public void OpenSettings() { }
            public void Quit() { }
            public void SetListening(bool on) => Listening = on;
            public bool Listening { get; private set; } = true;
            public string ClipboardText() => "texto de prueba";
            public void SetClipboard(string text) { }
            public void HidePanel() { }
            public void ApplySettings() { }
            public IntPtr TargetWindow => IntPtr.Zero;
            public void ShowVoiceDiagnostics() { }
            public void ReloadSettings() { }
        }
#endif
    }
}
