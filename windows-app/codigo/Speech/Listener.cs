using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Speech.Recognition;
using System.Threading;
using System.Threading.Tasks;
using Jarvis.Core;

namespace Jarvis.Speech
{
    // Escucha con el reconocimiento de voz de Windows. Si Whisper está instalado, cada frase que
    // entrega Windows se vuelve a transcribir con Whisper, que entiende mucho mejor el español.
    public sealed class Listener : ISpeechInput
    {
        SpeechRecognitionEngine _engine;
        Settings _s;
        Grammar _wakeOnly, _wakeAndCommand, _free;
        DateTime _awakeUntil = DateTime.MinValue;
        int _paused;
        DateTime _resumeAt = DateTime.MinValue;

        public event Action Woke;                    // dijo solo «Jarvis»: espera la orden
        public event Action<string> Heard;           // una orden completa
        public event Action<int> Level;              // nivel del micrófono 0…100 (para el reactor)
        public event Action<bool> AwakeChanged;
        public event Action<string> Partial;
        public string Status { get; private set; } = "";
        public bool Running { get; private set; }
        public bool Awake => DateTime.Now < _awakeUntil;
        public string RecognizerName { get; private set; } = "";

        public Listener(Settings s) { _s = s; }

        public bool Start()
        {
            Stop();
            if (!_s.VoiceInput)
            {
                Status = "escucha desactivada";
                return false;
            }
            Status = "";
            try
            {
                var all = SpeechRecognitionEngine.InstalledRecognizers();
                var info = all.FirstOrDefault(r => r.Culture.TwoLetterISOLanguageName == "es");
                if (info == null)
                {
                    // Antes se usaba el reconocedor en inglés y no entendía nada: mejor decirlo claro.
                    Status = all.Count == 0
                        ? "Windows no tiene el reconocimiento de voz clásico instalado"
                        : "el reconocimiento clásico de Windows solo está en " + string.Join(", ", all.Select(r => r.Culture.Name)) + ", no en español";
                    Log.Write("Escucha clásica: " + Status);
                    return false;
                }
                RecognizerName = "Windows clásico, " + info.Culture.Name + (NeuralVoices.WhisperReady(_s) ? " + Whisper" : "");
                _engine = new SpeechRecognitionEngine(info);
                _engine.SetInputToDefaultAudioDevice();
                BuildGrammars(info.Culture);
                _engine.SpeechRecognized += OnRecognized;
                _engine.AudioLevelUpdated += (o, e) => Level?.Invoke(e.AudioLevel);
                _engine.SpeechHypothesized += (o, e) =>
                {
                    if (Volatile.Read(ref _paused) == 1 || !Awake) return;
                    Partial?.Invoke(StripWake(e.Result?.Text ?? "", out _));
                };
                _engine.BabbleTimeout = TimeSpan.FromSeconds(0);
                _engine.EndSilenceTimeout = TimeSpan.FromMilliseconds(_s.EndSilenceMs);
                _engine.EndSilenceTimeoutAmbiguous = TimeSpan.FromMilliseconds(_s.EndSilenceMs + 250);
                _engine.RecognizeAsync(RecognizeMode.Multiple);
                Running = true;
                Status = "escuchando";
                return true;
            }
            catch (InvalidOperationException)
            {
                Status = "no hay micrófono disponible";
            }
            catch (Exception e)
            {
                Status = "no pude empezar a escuchar: " + e.Message;
            }
            Log.Write("Escucha: " + Status);
            Stop();
            return false;
        }

        void BuildGrammars(CultureInfo culture)
        {
            var wake = new Choices();
            foreach (var w in WakeWords.Names(_s))
                foreach (var p in new[] { w, "oye " + w, "hola " + w, "hey " + w, "ok " + w }) wake.Add(p);

            var g1 = new GrammarBuilder(wake) { Culture = culture };
            _wakeOnly = new Grammar(g1) { Name = "despertar", Priority = 10 };

            var g2 = new GrammarBuilder(wake) { Culture = culture };
            g2.AppendDictation();
            _wakeAndCommand = new Grammar(g2) { Name = "orden", Priority = 5 };

            _free = new DictationGrammar { Name = "libre", Enabled = false };

            _engine.LoadGrammar(_wakeOnly);
            _engine.LoadGrammar(_wakeAndCommand);
            _engine.LoadGrammar(_free);
        }

        public void Stop()
        {
            Running = false;
            if (_engine == null) return;
            try { _engine.RecognizeAsyncCancel(); } catch { }
            try { _engine.Dispose(); } catch { }
            _engine = null;
        }

        public void UseSettings(Settings s) => _s = s;
        public Func<string, bool> EchoCheck { get; set; }

        public void Update(Settings s)
        {
            _s = s;
            Start();
        }

        // Mientras JARVIS habla no se escucha a sí mismo.
        public void Pause()
        {
            Interlocked.Exchange(ref _paused, 1);
        }

        public void Resume()
        {
            // Solo si estaba en pausa (se puede llamar de más sin perder lo que se dice).
            if (Interlocked.Exchange(ref _paused, 0) == 1) _resumeAt = DateTime.Now.AddMilliseconds(350);
        }

        // Tras una respuesta, unos segundos para seguir hablando sin repetir «Jarvis».
        public void Listen(double seconds)
        {
            _awakeUntil = DateTime.Now.AddSeconds(seconds);
            SetFree(true);
            AwakeChanged?.Invoke(true);
            Task.Delay(TimeSpan.FromSeconds(seconds + 0.2)).ContinueWith(_ =>
            {
                if (!Awake)
                {
                    SetFree(false);
                    AwakeChanged?.Invoke(false);
                }
            });
        }

        public void Sleep()
        {
            _awakeUntil = DateTime.MinValue;
            SetFree(false);
            AwakeChanged?.Invoke(false);
        }

        void SetFree(bool on)
        {
            try
            {
                if (_free != null && _free.Enabled != on) _free.Enabled = on;
            }
            catch { }
        }

        float MinConfidence(bool free) => (_s.Sensitivity == "alta" ? 0.35f : _s.Sensitivity == "baja" ? 0.7f : 0.5f) - (free ? 0.15f : 0f);

        async void OnRecognized(object sender, SpeechRecognizedEventArgs e)
        {
            try
            {
                if (Volatile.Read(ref _paused) == 1 || DateTime.Now < _resumeAt) return;
                var r = e.Result;
                bool free = r.Grammar == _free;
                if (r.Confidence < MinConfidence(free)) return;
                if (free && !Awake) return;
                if (EchoCheck?.Invoke(r.Text ?? "") == true) return;   // su propia voz, entregada tarde

                string text = r.Text ?? "";
                byte[] audio = null;
                if (NeuralVoices.WhisperReady(_s) && r.Audio != null)
                {
                    using var ms = new MemoryStream();
                    r.Audio.WriteToWaveStream(ms);
                    audio = ms.ToArray();
                }

                if (r.Grammar == _wakeOnly)
                {
                    _awakeUntil = DateTime.Now.AddSeconds(7);
                    SetFree(true);
                    Woke?.Invoke();
                    AwakeChanged?.Invoke(true);
                    _ = Task.Delay(7200).ContinueWith(_ =>
                    {
                        if (!Awake)
                        {
                            SetFree(false);
                            AwakeChanged?.Invoke(false);
                        }
                    });
                    return;
                }

                if (audio != null)
                {
                    string better = await NeuralVoices.TranscribeAsync(audio);
                    if (better != "") text = better;
                }

                if (!free)
                {
                    // Se oyó «Jarvis …»: confirmar que de verdad dijo el nombre (Whisper lo escribe) y quitarlo.
                    string rest = StripWake(text, out bool hadWake);
                    if (!hadWake && audio != null && r.Confidence < 0.8f) return;
                    text = rest;
                }
                else
                {
                    text = StripWake(text, out _);
                }
                text = text.Trim(' ', ',', '.', '¿', '?', '¡', '!');
                if (Text.Squash(text) == "")
                {
                    Woke?.Invoke();
                    Listen(7);
                    return;
                }
                _awakeUntil = DateTime.MinValue;
                SetFree(false);
                AwakeChanged?.Invoke(false);
                Heard?.Invoke(text);
            }
            catch (Exception ex)
            {
                Log.Write("Escucha: " + ex.Message);
            }
        }

        // Quita «oye Jarvis,» del principio (o del final: «… Jarvis»).
        public string StripWake(string text, out bool had) => WakeWords.Strip(text, _s, out had);

        // «yarvis», «jarbis», «charvis»… Whisper a veces escribe el nombre así.
        static bool Similar(string a, string b)
        {
            if (a == b) return true;
            if (Math.Abs(a.Length - b.Length) > 2 || a.Length < 4) return false;
            var d = new int[a.Length + 1, b.Length + 1];
            for (int i = 0; i <= a.Length; i++) d[i, 0] = i;
            for (int j = 0; j <= b.Length; j++) d[0, j] = j;
            for (int i = 1; i <= a.Length; i++)
                for (int j = 1; j <= b.Length; j++)
                    d[i, j] = Math.Min(Math.Min(d[i - 1, j] + 1, d[i, j - 1] + 1), d[i - 1, j - 1] + (a[i - 1] == b[j - 1] ? 0 : 1));
            return d[a.Length, b.Length] <= (b.Length >= 6 ? 2 : 1);
        }

        public void Dispose() => Stop();
    }
}
