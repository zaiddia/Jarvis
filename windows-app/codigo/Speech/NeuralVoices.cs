using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Jarvis.Core;

namespace Jarvis.Speech
{
    // Whisper (entender) y Piper (hablar), instalados con «instalar-voces-jarvis.bat» en %LOCALAPPDATA%\JarvisVoz.
    public static class NeuralVoices
    {
        public static string Dir => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "JarvisVoz");
        public static string WhisperExe { get; private set; } = "";
        public static string WhisperModel { get; private set; } = "";
        public static string PiperExe { get; private set; } = "";
        public static string PiperVoice { get; private set; } = "";
        public static int PiperSpeakers { get; private set; } = 1;

        public static readonly string[] KnownVoices =
        {
            "es_MX-ald-medium", "es_ES-davefx-medium", "es_ES-sharvard-medium", "es_MX-claude-high", "es_AR-daniela-high", "es_ES-carlfm-x_low"
        };

        public static void Locate(Settings s)
        {
            WhisperExe = WhisperModel = PiperExe = PiperVoice = "";
            string exe = Path.Combine(Dir, "whisper", "whisper-cli.exe");
            if (File.Exists(exe))
            {
                string m = Path.Combine(Dir, "modelos");
                var order = new System.Collections.Generic.List<string>();
                if (s.WhisperModel == "turbo") order.Add("ggml-large-v3-turbo-q5_0.bin");
                else if (s.WhisperModel == "small") order.AddRange(new[] { "ggml-small-q5_1.bin", "ggml-small.bin" });
                else if (s.WhisperModel == "base") order.AddRange(new[] { "ggml-base-q5_1.bin", "ggml-base.bin" });
                order.AddRange(new[] { "ggml-large-v3-turbo-q5_0.bin", "ggml-small-q5_1.bin", "ggml-small.bin", "ggml-base-q5_1.bin", "ggml-base.bin" });
                string found = order.Select(f => Path.Combine(m, f)).FirstOrDefault(File.Exists);
                if (found != null)
                {
                    WhisperExe = exe;
                    WhisperModel = found;
                }
            }
            exe = Path.Combine(Dir, "piper", "piper.exe");
            if (File.Exists(exe))
            {
                string v = Path.Combine(Dir, "voces");
                var order = new System.Collections.Generic.List<string>();
                if (!string.IsNullOrWhiteSpace(s.PiperVoice)) order.Add(s.PiperVoice.Trim().Replace(".onnx", ""));
                if (s.IsViernes) order.AddRange(new[] { "es_MX-claude-high", "es_AR-daniela-high" });
                order.AddRange(KnownVoices);
                string found = order.Select(f => Path.Combine(v, f + ".onnx")).FirstOrDefault(f => File.Exists(f) && File.Exists(f + ".json"));
                if (found == null && Directory.Exists(v)) found = Directory.GetFiles(v, "*.onnx").FirstOrDefault();
                if (found != null)
                {
                    PiperExe = exe;
                    PiperVoice = found;
                    PiperSpeakers = 1;
                    try
                    {
                        string json = File.ReadAllText(found + ".json");
                        int k = json.IndexOf("\"num_speakers\"", StringComparison.Ordinal);
                        if (k >= 0)
                        {
                            int colon = json.IndexOf(':', k);
                            string num = new string(json.Skip(colon + 1).SkipWhile(char.IsWhiteSpace).TakeWhile(char.IsDigit).ToArray());
                            if (int.TryParse(num, out int n)) PiperSpeakers = Math.Max(1, n);
                        }
                    }
                    catch { }
                }
            }
        }

        public static bool WhisperReady(Settings s) => s.SpeechEngine == "whisper" && WhisperExe != "";
        public static bool PiperReady(Settings s) => s.VoiceEngine == "neural" && PiperExe != "";
        public static string VoiceStem => Path.GetFileNameWithoutExtension(PiperVoice);

        public static string TempDir
        {
            get
            {
                string d = Path.Combine(Path.GetTempPath(), "JarvisVoz");
                Directory.CreateDirectory(d);
                return d;
            }
        }

        // ---------------------------------------------------------------- Whisper

        static int _wavNo;

        // Transcribe un WAV (el audio que ya entregó el reconocedor de Windows). "" si no hubo texto.
        public static async Task<string> TranscribeAsync(byte[] wav, CancellationToken ct = default)
        {
            if (WhisperExe == "" || wav == null || wav.Length < 8000) return "";
            string file = Path.Combine(TempDir, "orden-" + Interlocked.Increment(ref _wavNo) + ".wav");
            try
            {
                await File.WriteAllBytesAsync(file, wav, ct);
                int threads = Math.Clamp(Environment.ProcessorCount / 2, 2, 8);
                string prompt = "Jarvis, abre Spotify. Sube el volumen. Busca en YouTube. Recuérdame mañana a las ocho.";
                var psi = new ProcessStartInfo(WhisperExe)
                {
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    StandardOutputEncoding = Encoding.UTF8,
                };
                foreach (var a in new[] { "-m", WhisperModel, "-f", file, "-l", "es", "-nt", "-np", "-sns", "-bs", "1", "-bo", "1", "-nf",
                                          "-t", threads.ToString(), "--prompt", prompt })
                    psi.ArgumentList.Add(a);
                using var p = Process.Start(psi);
                if (p == null) return "";
                try { p.PriorityClass = ProcessPriorityClass.BelowNormal; } catch { }
                var stdout = p.StandardOutput.ReadToEndAsync();
                _ = p.StandardError.ReadToEndAsync();
                using var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct);
                timeout.CancelAfter(TimeSpan.FromSeconds(30));
                try { await p.WaitForExitAsync(timeout.Token); }
                catch (OperationCanceledException)
                {
                    try { p.Kill(true); } catch { }
                    return "";
                }
                return Clean(await stdout);
            }
            catch (Exception e)
            {
                Log.Write("Whisper: " + e.Message);
                return "";
            }
            finally
            {
                try { File.Delete(file); } catch { }
            }
        }

        // Whisper inventa frases típicas cuando hay silencio o ruido.
        public static string Clean(string t)
        {
            var sb = new StringBuilder();
            int depth = 0;
            foreach (char c in t ?? "")
            {
                if (c == '[' || c == '(') depth++;
                else if ((c == ']' || c == ')') && depth > 0) depth--;
                else if (depth == 0 && c != '♪') sb.Append(c);
            }
            string o = sb.ToString().Trim();
            string s = Text.Squash(o);
            if (s == "") return "";
            foreach (var bad in new[] { "amara org", "subtitulos realizados", "subtitulado por", "gracias por ver", "suscribete al canal", "musica de fondo" })
                if (s.Contains(bad)) return "";
            if (Text.IsOneOf(s, "gracias", "muchas gracias", "adios", "musica", "aplausos", "risas")) return "";
            return o;
        }
    }
}
