using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Jarvis.Core;
using Windows.Globalization;
using Windows.Media.SpeechRecognition;

namespace Jarvis.Speech
{
    // Escucha con el reconocimiento de voz moderno de Windows 10/11 (el mismo del dictado con Win+H).
    // Entiende español de México, EE. UU. o España y acentos latinos mucho mejor que el clásico.
    // Necesita «Reconocimiento de voz en línea» activado en Configuración › Privacidad › Voz.
    public sealed class ModernListener : ISpeechInput
    {
        Settings _s;
        SpeechRecognizer _rec;
        readonly object _lock = new object();
        bool _wanted;                 // debe seguir escuchando (se reinicia sola si se corta)
        int _restarts;
        DateTime _lastRestart = DateTime.MinValue;
        DateTime _lastResume = DateTime.MinValue;   // cuándo terminó de hablar por última vez
        DateTime _phraseStart = DateTime.MinValue;  // cuándo empezó la frase actual (primera hipótesis)
        int _ignored, _logged;
        DateTime _awakeUntil = DateTime.MinValue;
        int _paused;
        DateTime _resumeAt = DateTime.MinValue;
        bool _wokeThisPhrase;
        Timer _meter;

        public event Action Woke;
        public event Action<string> Heard;
        public event Action<string> Partial;
        public event Action<int> Level;
        public event Action<bool> AwakeChanged;
        public string Status { get; private set; } = "";
        public bool Running { get; private set; }
        public bool Awake => DateTime.Now < _awakeUntil;
        public string RecognizerName { get; private set; } = "";

        public ModernListener(Settings s) { _s = s; }

        static string[] Candidates(Settings s)
        {
            var list = new System.Collections.Generic.List<string>();
            if (!string.IsNullOrWhiteSpace(s.RecognizerLanguage)) list.Add(s.RecognizerLanguage.Trim());
            string ui = System.Globalization.CultureInfo.CurrentUICulture.Name;
            if (ui.StartsWith("es")) list.Add(ui);
            list.AddRange(new[] { "es-MX", "es-US", "es-ES", "es-419" });
            return list.Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
        }

        public static string[] SpanishLanguages()
        {
            try { return SpeechRecognizer.SupportedTopicLanguages.Where(l => l.LanguageTag.StartsWith("es")).Select(l => l.LanguageTag).ToArray(); }
            catch { return new string[0]; }
        }

        public bool Start()
        {
            Stop();
            if (!_s.VoiceInput)
            {
                Status = "escucha desactivada";
                return false;
            }
            Status = "";
            // Dos intentos: justo al reiniciar, la sesión anterior puede tener aún el micrófono.
            for (int attempt = 0; attempt < 2; attempt++)
            {
                try
                {
                    // En un hilo aparte (MTA): las operaciones de WinRT no se bloquean con el hilo de la ventana.
                    var t = Task.Run(StartAsync);
                    if (!t.Wait(TimeSpan.FromSeconds(10)))
                    {
                        Status = "el reconocimiento de voz de Windows no responde";
                        return false;
                    }
                    if (t.Result) return true;
                    return false;   // fallo claro (idioma, privacidad): no sirve repetir
                }
                catch (Exception e)
                {
                    Status = Explain(e.GetBaseException());
                    Log.Write("Escucha moderna (intento " + (attempt + 1) + "): " + e.GetBaseException().Message);
                    uint hr = (uint)e.GetBaseException().HResult;
                    if (hr == 0x80045509 || hr == 0x80070005 || hr == 0x8004503A) return false;
                    Thread.Sleep(1200);
                }
            }
            return false;
        }

        static string Explain(Exception e)
        {
            uint hr = (uint)e.HResult;
            if (hr == 0x80045509) return "falta activar «Reconocimiento de voz en línea» (Configuración › Privacidad y seguridad › Voz)";
            if (hr == 0x80070005) return "Windows no deja usar el micrófono a las aplicaciones de escritorio (Configuración › Privacidad › Micrófono)";
            if (hr == 0x8004503A) return "el idioma de voz en español no está instalado (Configuración › Hora e idioma › Voz)";
            if (hr == 0x80045503 || hr == 0x80045504) return "no se encuentra el micrófono";
            return "no pude empezar a escuchar (" + e.Message.Trim() + ")";
        }

        async Task<bool> StartAsync()
        {
            var supported = SpeechRecognizer.SupportedTopicLanguages.Select(l => l.LanguageTag).ToList();
            string tag = Candidates(_s).FirstOrDefault(c => supported.Any(x => x.Equals(c, StringComparison.OrdinalIgnoreCase)))
                         ?? supported.FirstOrDefault(x => x.StartsWith("es", StringComparison.OrdinalIgnoreCase));
            if (tag == null)
            {
                Status = "no hay reconocimiento de voz en español en Windows (Configuración › Hora e idioma › Idioma: añada Español (México) con «Reconocimiento de voz»)";
                Log.Write("Escucha moderna: idiomas disponibles: " + string.Join(", ", supported));
                return false;
            }
            var rec = new SpeechRecognizer(new Language(tag));
            rec.Constraints.Add(new SpeechRecognitionTopicConstraint(SpeechRecognitionScenario.Dictation, "dictado"));
            var compiled = await rec.CompileConstraintsAsync();
            if (compiled.Status != SpeechRecognitionResultStatus.Success)
            {
                Status = compiled.Status == SpeechRecognitionResultStatus.TopicLanguageNotSupported
                    ? "el dictado en " + tag + " no está disponible en este Windows"
                    : compiled.Status == SpeechRecognitionResultStatus.NetworkFailure
                        ? "el reconocimiento de voz de Windows necesita internet"
                        : "no pude preparar el reconocimiento (" + compiled.Status + ")";
                rec.Dispose();
                return false;
            }
            rec.Timeouts.EndSilenceTimeout = TimeSpan.FromMilliseconds(Math.Max(500, _s.EndSilenceMs));
            rec.Timeouts.BabbleTimeout = TimeSpan.Zero;
            rec.Timeouts.InitialSilenceTimeout = TimeSpan.FromMinutes(10);   // un rato en silencio no debe cortar la escucha
            rec.ContinuousRecognitionSession.AutoStopSilenceTimeout = TimeSpan.FromHours(12);
            rec.ContinuousRecognitionSession.ResultGenerated += OnResult;
            rec.ContinuousRecognitionSession.Completed += OnCompleted;
            rec.HypothesisGenerated += OnHypothesis;
            await rec.ContinuousRecognitionSession.StartAsync();
            lock (_lock)
            {
                _rec = rec;
                _wanted = true;
            }
            RecognizerName = "Windows moderno, " + tag;
            Running = true;
            Status = "escuchando";
            _meter ??= new Timer(_ => Level?.Invoke((int)(AudioDevices.InputPeak() * 100)), null, 60, 60);
            return true;
        }

        void OnCompleted(SpeechContinuousRecognitionSession sender, SpeechContinuousRecognitionCompletedEventArgs args)
        {
            Log.Write("Escucha moderna: la sesión terminó (" + args.Status + ")");
            bool again;
            lock (_lock) again = _wanted;
            if (!again) return;
            Running = false;
            _wokeThisPhrase = false;
            _phraseStart = DateTime.MinValue;
            // Antes, tras 200 reinicios (los cortes por silencio también cuentan) dejaba de escuchar para siempre:
            // ahora nunca se rinde; solo espera más entre intentos si falla seguido.
            if ((DateTime.Now - _lastRestart).TotalMinutes > 2) _restarts = 0;
            _lastRestart = DateTime.Now;
            _restarts++;
            int delay = args.Status == SpeechRecognitionResultStatus.NetworkFailure ? 5000 : args.Status == SpeechRecognitionResultStatus.MicrophoneUnavailable ? 4000 : 800;
            delay = Math.Min(30000, delay * Math.Max(1, _restarts / 3));
            if (args.Status == SpeechRecognitionResultStatus.NetworkFailure) Status = "sin internet: el reconocimiento de voz se reanudará solo";
            if (args.Status == SpeechRecognitionResultStatus.MicrophoneUnavailable) Status = "no encuentro el micrófono";
            Task.Delay(delay).ContinueWith(async _ =>
            {
                lock (_lock) if (!_wanted) return;
                try
                {
                    await _rec.ContinuousRecognitionSession.StartAsync();
                    Running = true;
                    Status = "escuchando";
                }
                catch (Exception e)
                {
                    Log.Write("Escucha moderna (reinicio): " + e.Message);
                    OnCompleted(sender, args);
                }
            });
        }

        // Mientras habla, solo se le puede interrumpir llamándola por su nombre (y no con su propio eco).
        bool BargeInAllowed(string text, out bool had)
        {
            WakeWords.Strip(text, _s, out had);
            return had && _s.BargeIn && !(EchoCheck?.Invoke(text) ?? false);
        }

        public Func<string, bool> EchoCheck { get; set; }

        void OnHypothesis(SpeechRecognizer sender, SpeechRecognitionHypothesisGeneratedEventArgs args)
        {
            string t = args.Hypothesis?.Text ?? "";
            if (t == "") return;
            if (_phraseStart == DateTime.MinValue) _phraseStart = DateTime.Now;
            if (Volatile.Read(ref _paused) == 1 || DateTime.Now < _resumeAt)
            {
                if (!BargeInAllowed(t, out _)) return;
                if (!_wokeThisPhrase)
                {
                    _wokeThisPhrase = true;
                    Woke?.Invoke();   // se calla y escucha
                }
                return;
            }
            if (Awake)
            {
                Partial?.Invoke(WakeWords.Strip(t, _s, out _));
                return;
            }
            // En cuanto se oye el nombre, el panel ya muestra que escucha.
            string rest = WakeWords.Strip(t, _s, out bool had);
            if (!had) return;
            if (!_wokeThisPhrase)
            {
                _wokeThisPhrase = true;
                Woke?.Invoke();
            }
            if (rest != "") Partial?.Invoke(rest);
        }

        void OnResult(SpeechContinuousRecognitionSession sender, SpeechContinuousRecognitionResultGeneratedEventArgs args)
        {
            bool woke = _wokeThisPhrase;
            _wokeThisPhrase = false;
            DateTime started = _phraseStart;
            _phraseStart = DateTime.MinValue;
            try
            {
                var r = args.Result;
                if (r == null || r.Status != SpeechRecognitionResultStatus.Success) return;
                string text = (r.Text ?? "").Trim();
                if (text == "") return;
                // Una frase que empezó mientras hablaba (el reconocedor la entrega tarde) es casi siempre su propia voz.
                // Se mide con el reloj propio (la primera hipótesis de la frase): la hora «PhraseStartTime» de Windows
                // no es fiable y, si venía mal, tiraba todo lo que se decía después de que JARVIS hablara.
                bool startedWhileSpeaking = started != DateTime.MinValue && _lastResume != DateTime.MinValue && (_lastResume - started).TotalMilliseconds > 150;
                bool paused = Volatile.Read(ref _paused) == 1 || DateTime.Now < _resumeAt;
                // Si ya se calló y la frase lleva el nombre, es usted aunque haya empezado a hablar un poco antes.
                if (!paused && startedWhileSpeaking) { WakeWords.Strip(text, _s, out bool named); paused = !named; }
                if (paused && !BargeInAllowed(text, out _))
                {
                    Trace("mientras yo hablaba", text);
                    return;
                }
                if (EchoCheck?.Invoke(text) == true)
                {
                    Trace("mi propio eco", text);
                    return;
                }
                string rest = WakeWords.Strip(text, _s, out bool had);
                // Con el nombre dicho se acepta aunque Windows no esté seguro (acentos, ruido).
                bool lowConf = r.Confidence == SpeechRecognitionConfidence.Rejected ||
                               (r.Confidence == SpeechRecognitionConfidence.Low && _s.Sensitivity == "baja");
                if (!Awake && !had)
                {
                    if (lowConf) { Trace("poco clara y sin el nombre", text); return; }
                    if (++_ignored % 20 == 1) Log.Write("Escucha: oigo frases sin «" + _s.WakeWord + "» y las ignoro (normal si habla con otra persona). Ej.: «" + Text.Preview(text, 60) + "»");
                    return;
                }
                if (_logged < 30) { _logged++; Log.Write("Escucha: oí «" + Text.Preview(text, 80) + "»"); }
                rest = rest.Trim(' ', ',', '.', '¿', '?', '¡', '!');
                if (Text.Squash(rest) == "")
                {
                    if (!woke) Woke?.Invoke();
                    Listen(7);
                    return;
                }
                _awakeUntil = DateTime.MinValue;
                AwakeChanged?.Invoke(false);
                Heard?.Invoke(rest);
            }
            catch (Exception e)
            {
                Log.Write("Escucha moderna: " + e.Message);
            }
        }

        public void Stop()
        {
            SpeechRecognizer rec;
            lock (_lock)
            {
                _wanted = false;
                rec = _rec;
                _rec = null;
            }
            Running = false;
            _meter?.Dispose();
            _meter = null;
            if (rec == null) return;
            try
            {
                rec.ContinuousRecognitionSession.ResultGenerated -= OnResult;
                rec.ContinuousRecognitionSession.Completed -= OnCompleted;
                rec.HypothesisGenerated -= OnHypothesis;
                Task.Run(async () =>
                {
                    try { await rec.ContinuousRecognitionSession.CancelAsync(); } catch { }
                    rec.Dispose();
                }).Wait(3000);
            }
            catch { }
        }

        // Por qué se descartó una frase (las primeras, para el diagnóstico sin llenar el registro).
        int _traced;
        void Trace(string why, string text)
        {
            if (_traced++ < 40) Log.Write("Escucha: descarto «" + Text.Preview(text, 60) + "» (" + why + ").");
        }

        public void UseSettings(Settings s) => _s = s;

        public void Update(Settings s)
        {
            _s = s;
            Start();
        }

        public void Pause() => Interlocked.Exchange(ref _paused, 1);

        public void Resume()
        {
            // Solo si estaba en pausa (se puede llamar de más sin perder lo que se dice).
            if (Interlocked.Exchange(ref _paused, 0) == 1)
            {
                _resumeAt = DateTime.Now.AddMilliseconds(400);
                _lastResume = DateTime.Now;
            }
        }

        public void Listen(double seconds)
        {
            _awakeUntil = DateTime.Now.AddSeconds(seconds);
            AwakeChanged?.Invoke(true);
            Task.Delay(TimeSpan.FromSeconds(seconds + 0.2)).ContinueWith(_ =>
            {
                if (!Awake) AwakeChanged?.Invoke(false);
            });
        }

        public void Sleep()
        {
            _awakeUntil = DateTime.MinValue;
            AwakeChanged?.Invoke(false);
        }

        public void Dispose() => Stop();
    }
}
