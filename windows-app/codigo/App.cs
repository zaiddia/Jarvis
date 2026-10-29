using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Threading;
using Jarvis.Ai;
using Jarvis.Commands;
using Jarvis.Core;
using Jarvis.Speech;
using Jarvis.Ui;

namespace Jarvis
{
    public static class Program
    {
        [STAThread]
        public static void Main(string[] args)
        {
            using var mutex = new Mutex(true, "Local\\JARVIS-Asistente", out bool first);
            using var showSignal = new EventWaitHandle(false, EventResetMode.AutoReset, "Local\\JARVIS-Mostrar");
            if (!first)
            {
                // Ya hay un JARVIS abierto: que se muestre ese.
                showSignal.Set();
                return;
            }
            var app = new Application { ShutdownMode = ShutdownMode.OnExplicitShutdown };
            app.DispatcherUnhandledException += (o, e) =>
            {
                Log.Write("Error no controlado: " + e.Exception);
                e.Handled = true;
            };
            AppDomain.CurrentDomain.UnhandledException += (o, e) => Log.Write("Error fatal: " + e.ExceptionObject);
            TaskScheduler.UnobservedTaskException += (o, e) =>
            {
                Log.Write("Tarea con error: " + e.Exception?.GetBaseException().Message);
                e.SetObserved();
            };
            var jarvis = new JarvisApp(app, showSignal, args);
            app.Startup += (o, e) => jarvis.Start();
            app.Run();
        }
    }

    // El asistente: une la escucha, la voz, el motor de órdenes, la IA, el panel y la bandeja.
    public sealed class JarvisApp : IHost
    {
        readonly Application _app;
        readonly EventWaitHandle _showSignal;
        readonly string[] _args;
        Settings _s;
        Speaker _speaker;
        ISpeechInput _listener = new FailedInput("sin iniciar");
        Engine _engine;
        AiClient _ai;
        HudWindow _hud;
        SettingsWindow _settingsWin;
        System.Windows.Forms.NotifyIcon _tray;
        System.Windows.Forms.ToolStripMenuItem _listenItem;
        HwndSource _msg;
        readonly DispatcherTimer _tick = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
        readonly DispatcherTimer _meter = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(45) };
        CancellationTokenSource _turn;
        IntPtr _target;
        bool _listening = true;
        bool _speaking;
        const int HotkeyId = 0x4A41;

        public JarvisApp(Application app, EventWaitHandle showSignal, string[] args)
        {
            _app = app;
            _showSignal = showSignal;
            _args = args;
        }

        public Settings Settings => _s;
        Dispatcher UI => _app.Dispatcher;

        public void Start()
        {
            _s = Settings.Load();
            NeuralVoices.Locate(_s);
            Log.Write("JARVIS " + typeof(JarvisApp).Assembly.GetName().Version + " iniciado. Whisper: " + (NeuralVoices.WhisperExe != "" ? NeuralVoices.WhisperModel : "no") +
                      ". Piper: " + (NeuralVoices.PiperExe != "" ? NeuralVoices.PiperVoice : "no"));

            if (LocalAi.IsLocal(_s)) _ = LocalAi.Warm(_s);   // Ollama: averigua qué modelo usar y lo carga ya
            _engine = new Engine(this);
            _ai = new AiClient(() => _s, _engine);
            _speaker = new Speaker(_s);
            _speaker.Started += () => UI.BeginInvoke(new Action(OnSpeakStart));
            _speaker.Finished += () => UI.BeginInvoke(new Action(OnSpeakEnd));

            _hud = new HudWindow(_s);
            _hud.Submitted += t => _ = Process(t, false);
            _hud.Dismissed += () =>
            {
                StopSpeaking();
                _listener?.Sleep();
            };
            _hud.MicToggleRequested += () => SetListening(!_listening);
            _hud.SettingsRequested += OpenSettings;
            _hud.QuitRequested += () =>
            {
                StopSpeaking();
                _hud.HideHud();
                Shutdown();
            };

            StartListening();
            // Si la última vez se cerró con el volumen de otras apps bajado, se devuelve.
            DuckQueue(Ducker.Restore);

            CreateTray();
            RegisterHotkey();
            ApplyStartup();

            _tick.Tick += (o, e) => OnTick();
            _tick.Start();
            _meter.Tick += (o, e) =>
            {
                if (_speaking) _hud.SetLevel(Math.Min(1, AudioDevices.OutputPeak() * 1.6));
            };
            _meter.Start();
            _ptt.Tick += (o, e) => PollPushToTalk();
            _ptt.Start();

            // Señal de una segunda copia: mostrar el panel.
            ThreadPool.RegisterWaitForSingleObject(_showSignal, (st, to) => UI.BeginInvoke(new Action(() => ShowPanel(true))), null, -1, false);

            if (_s.GreetOnStart && !_args.Contains("--silencio"))
            {
                int h = DateTime.Now.Hour;
                string g = h < 6 ? "Buenas noches" : h < 12 ? "Buenos días" : h < 20 ? "Buenas tardes" : "Buenas noches";
                string msg = g + Sir() + ". " + (_s.IsViernes ? "VIERNES en línea." : "Todos los sistemas en línea.");
                if (_listener.Running) msg += " Diga «" + _s.WakeWord + "» cuando me necesite.";
                else msg += " Pulse " + _s.Hotkey + " para escribirme.";
                Respond(msg, show: true);
            }
            if (!_listener.Running && _s.VoiceInput)
            {
                Notify(_s.Name, "No puedo escuchar: " + _listener.Status + ". Puede escribirme con " + _s.Hotkey + ", o abrir «Diagnóstico de voz» en el menú de la bandeja.");
                _hud.SetHeard("");
                ShowPanel(false);
                _hud.SetState(HudState.Error);
                _hud.SetReply("No puedo escuchar: " + _listener.Status + ".\nClic derecho en mi icono › Diagnóstico de voz.");
                _hud.HideLater(20);
            }
        }

        string Sir() => _s.Treatment.Trim() == "" ? "" : ", " + _s.Treatment.Trim();

        // (Re)crea la escucha con el mejor reconocedor disponible: el moderno de Windows o el clásico.
        string _listenKey = "";

        // Solo lo que obliga a reiniciar la escucha (cambiar la voz o el tema no la toca).
        string ListenKey() => string.Join("|", _listening, _s.VoiceInput, _s.Recognizer, _s.RecognizerLanguage, _s.SpeechEngine, _s.WhisperModel, _s.EndSilenceMs,
                                          _s.Recognizer == "clasico" ? _s.WakeWord : "");

        void StartListening()
        {
            _listenKey = ListenKey();
            var old = _listener;
            _listener = new FailedInput("escucha desactivada");
            try { old?.Dispose(); } catch { }
            if (!_listening || !_s.VoiceInput) return;
            var input = SpeechInput.Create(_s, out string why);
            input.Woke += () => UI.BeginInvoke(new Action(OnWake));
            input.EchoCheck = IsEcho;
            input.Heard += t => UI.BeginInvoke(new Action(() => _ = Process(t, true)));
            input.Partial += t => UI.BeginInvoke(new Action(() =>
            {
                if (_hud.IsVisible && !_speaking && _turn == null && t.Trim() != "") _hud.SetHeard(t + "…");
            }));
            input.Level += v => UI.BeginInvoke(new Action(() => { if (!_speaking) _hud.SetLevel(Math.Min(1, v / 60.0)); }));
            input.AwakeChanged += on => UI.BeginInvoke(new Action(() =>
            {
                if (on || _speaking || _turn != null || _pttDown) return;
                Unduck();
                _hud.SetState(_listening ? HudState.Idle : HudState.Muted);
                if (!_hud.Busy) _hud.HideLater(3);
            }));
            _listener = input;
            if (_speaking) input.Pause();   // si está hablando, que no se oiga a sí misma
            Log.Write("Escucha: " + (input.Running ? "en marcha (" + input.RecognizerName + ")" : input.Status) + (why != "" && input.Running ? " — el moderno no: " + why : ""));
            UpdateListenItem();
        }

        // ---------------------------------------------------------------- diagnóstico de voz

        public void ReloadSettings() => UI.BeginInvoke(new Action(() =>
        {
            _s = Settings.Load();
            ApplySettings();
        }));

        public void ShowVoiceDiagnostics() => UI.BeginInvoke(new Action(async () =>
        {
            ShowPanel(false);
            _hud.SetHeard("");
            _hud.SetState(HudState.Thinking);
            _hud.SetReply("Revisando el micrófono y el reconocimiento de voz…");
            var input = _listener;
            var items = await Task.Run(() => VoiceDiagnostics.Run(_s, input));
            _hud.SetReply(string.Join("\n", items.Select(i => (i.Ok ? "✓ " : "✗ ") + i.Text)));
            var bad = items.FirstOrDefault(i => !i.Ok && i.Fix != "");
            _hud.SetState(bad == null ? HudState.Idle : HudState.Error);
            if (CanSpeak) SpeakOut(VoiceDiagnostics.Summary(items) + (bad != null ? " Le abro los ajustes de Windows donde se arregla." : ""));
            if (bad != null)
                try { System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(bad.Fix) { UseShellExecute = true }); } catch { }
            _hud.HideLater(40);
        }));

        // ---------------------------------------------------------------- turnos

        // ---------------------------------------------------------------- bajar el volumen de las demás apps

        readonly object _duckLock = new object();
        Task _duckChain = Task.CompletedTask;
        bool _isDucked;

        void DuckQueue(Action a)
        {
            lock (_duckLock) _duckChain = _duckChain.ContinueWith(_ => { try { a(); } catch (Exception e) { Log.Write("Volumen: " + e.Message); } });
        }

        void Duck()
        {
            if (!_s.DuckAudio || _isDucked) return;
            _isDucked = true;
            int level = _s.DuckLevel;
            DuckQueue(() => Ducker.Duck(level));
        }

        void Unduck()
        {
            if (!_isDucked) return;
            _isDucked = false;
            DuckQueue(Ducker.Restore);
        }

        // ---------------------------------------------------------------- tecla para hablar (mantener pulsada)

        readonly DispatcherTimer _ptt = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(40) };
        bool _pttDown;

        void PollPushToTalk()
        {
            if (string.IsNullOrWhiteSpace(_s.PushToTalkKey) || !Native.ParseHotkey(_s.PushToTalkKey, out uint mods, out uint vk))
            {
                if (_pttDown) PushToTalkUp();
                return;
            }
            bool Down(int k) => (Native.GetAsyncKeyState(k) & 0x8000) != 0;
            bool down = Down((int)vk);
            if ((mods & Native.MOD_CONTROL) != 0) down &= Down(0x11);
            if ((mods & Native.MOD_ALT) != 0) down &= Down(0x12);
            if ((mods & Native.MOD_SHIFT) != 0) down &= Down(0x10);
            if ((mods & Native.MOD_WIN) != 0) down &= Down(0x5B) || Down(0x5C);
            if (down && !_pttDown) PushToTalkDown();
            else if (!down && _pttDown) PushToTalkUp();
        }

        void PushToTalkDown()
        {
            _pttDown = true;
            StopSpeaking();
            _turn?.Cancel();
            ShowPanel(false);
            _hud.SetHeard("");
            if (!_listening || !_listener.Running)
            {
                _hud.SetState(HudState.Error);
                _hud.SetReply("No puedo escuchar: " + (_listener.Status == "" ? "la escucha está desactivada" : _listener.Status) + ".");
                return;
            }
            _hud.SetReply("Le escucho" + Sir() + "… suelte la tecla al terminar.");
            _hud.SetState(HudState.Listening);
            _listener.Listen(120);
            Duck();
            if (_s.UiSounds) Chirp.Play(true);
        }

        void PushToTalkUp()
        {
            _pttDown = false;
            // Unos segundos de margen para que llegue el final de la frase.
            if (_listener.Running && _listener.Awake) _listener.Listen(Math.Max(2.5, _s.EndSilenceMs / 1000.0 + 1.8));
        }

        void OnWake()
        {
            Duck();
            StopSpeaking();
            ShowPanel(false);
            _hud.SetHeard("");
            _hud.SetReply("");
            _hud.SetState(HudState.Listening);
            if (_s.UiSounds) Chirp.Play(true);
        }

        async Task Process(string text, bool fromVoice)
        {
            text = (text ?? "").Trim();
            if (text == "") return;
            _turn?.Cancel();
            var cts = _turn = new CancellationTokenSource();
            StopSpeaking();
            ShowPanel(false);
            _hud.SetHeard(text);
            _hud.SetReply("");
            _hud.SetState(HudState.Thinking);
            Log.Write("Orden: " + text);
            try
            {
                Reply local = null;
                bool aiFirst = !_s.LocalFirst && _ai.Ready;
                if (!aiFirst) local = await _engine.HandleAsync(text);
                else
                {
                    // Incluso con la IA primero, «para», «cállate» y las respuestas sí/no son locales.
                    var c = Cmd.Parse(text);
                    if (c.Size <= 2) local = await _engine.HandleAsync(text);
                }
                Log.Write(local != null ? "  → lo atiende " + (_engine.LastHandler == "" ? "el motor" : _engine.LastHandler) : "  → a la IA");
                if (cts.IsCancellationRequested) return;
                byte[] screen = null;
                if (local != null && local.ScreenQuestion != null)
                {
                    // «¿Qué hay en mi pantalla?»: captura (sin el panel) y se la pasa a la IA.
                    _hud.SetReply("Mirando la pantalla…");
                    IntPtr target = _target;
                    try { screen = await Task.Run(() => VisionModule.CaptureJpeg(target)); }
                    catch (Exception e)
                    {
                        Log.Write("Captura para la IA: " + e.Message);
                        Respond("No pude capturar la pantalla" + Sir() + ".", error: true);
                        return;
                    }
                    text = local.ScreenQuestion;
                    local = null;
                    _hud.SetReply("");
                }
                if (local != null)
                {
                    if (local.Silent)
                    {
                        _hud.SetReply("✓");
                        Finish(local.KeepListening);
                    }
                    else Respond(local.Say, keepListening: local.KeepListening);
                    return;
                }
                if (!_ai.Ready)
                {
                    string[] tips = { "«abre Spotify»", "«¿qué tiempo hace?»", "«pon un temporizador de cinco minutos»", "«sube el volumen»", "«¿qué tengo hoy?»", "«cuéntame un chiste»" };
                    var rnd = new Random();
                    var two = tips.OrderBy(_ => rnd.Next()).Take(2).ToArray();
                    Respond("No le entendí del todo" + Sir() + ". Puede decirme, por ejemplo, " + two[0] + " o " + two[1] +
                            ". Si conecta una IA en mis ajustes, como Ollama, entenderé cualquier cosa.", keepListening: true);
                    return;
                }
                int streamed = 0;
                bool stream = _s.StreamAi && CanSpeak;
                string window = _s.SendContext ? Native.WindowTitle(_target) : "";
                // Cada frase se cuenta en el momento (no dentro de la cola de la ventana): antes, al terminar,
                // a veces aún no se habían contado, se volvía a decir la respuesta entera y sonaba duplicada.
                string answer = await _ai.AskAsync(text, window, sentence =>
                {
                    if (cts.IsCancellationRequested) return;
                    Interlocked.Increment(ref streamed);
                    OnUi(() =>
                    {
                        if (cts.IsCancellationRequested) return;
                        _hud.AppendReply(sentence);
                        if (stream) SpeakOut(sentence);
                    });
                }, cts.Token, screen);
                if (cts.IsCancellationRequested) return;
                _engine.LastReply = answer;
                if (Volatile.Read(ref streamed) == 0) Respond(answer == "" ? "Hecho" + Sir() + "." : answer);
                else
                {
                    _hud.SetReply(answer);
                    if (!stream) Respond(answer, alreadyShown: true);
                    else if (!_speaker.Busy) Finish(answer.TrimEnd().EndsWith("?"));
                    else _pendingKeep = answer.TrimEnd().EndsWith("?");
                }
            }
            catch (Exception e)
            {
                Log.Write("Turno: " + e);
                Respond("Algo ha fallado" + Sir() + ": " + e.Message, error: true);
            }
            finally
            {
                if (_turn == cts) _turn = null;
            }
        }

        bool _pendingKeep;

        bool CanSpeak
        {
            get
            {
                if (!_s.VoiceOutput) return false;
                if (!_s.AutoQuiet) return true;
                // 2 = pantalla completa ocupada, 3 = juego Direct3D, 4 = presentación
                if (Native.SHQueryUserNotificationState(out int st) == 0 && (st == 2 || st == 3 || st == 4)) return false;
                // En una llamada (otra app usa el micrófono) contesta solo en el panel.
                return !Native.MicInUseByOthers();
            }
        }

        void Respond(string text, bool keepListening = false, bool show = true, bool error = false, bool alreadyShown = false)
        {
            if (!alreadyShown) _hud.SetReply(text);
            if (show) ShowPanel(false);
            _pendingKeep = keepListening || text.TrimEnd().EndsWith("?");
            if (CanSpeak && text.Trim() != "")
            {
                if (error) _hud.SetState(HudState.Error);
                SpeakOut(text);
            }
            else
            {
                _hud.SetState(error ? HudState.Error : HudState.Idle);
                Finish(_pendingKeep, Math.Clamp(text.Length / 14.0, 5, 20));
            }
        }

        void OnSpeakStart()
        {
            _speaking = true;
            Duck();
            _listener.Pause();
            _hud.SetState(HudState.Speaking);
        }

        // En la ventana: directamente si ya se está en ella, en cola si se viene de otro hilo (sin reordenar).
        void OnUi(Action a)
        {
            if (UI.CheckAccess()) a();
            else UI.BeginInvoke(a);
        }

        DateTime _saidUntil = DateTime.MinValue;

        void OnSpeakEnd()
        {
            _speaking = false;
            // Lo dicho se recuerda unos segundos más: el reconocedor puede entregar tarde su propio eco.
            _saidUntil = DateTime.Now.AddSeconds(5);
            _listener.Resume();
            _hud.SetLevel(0);
            if (_turn != null) return; // la IA sigue escribiendo
            Finish(_pendingKeep);
        }

        // Al terminar de responder: seguir escuchando un momento o recoger el panel.
        void Finish(bool keepListening, double hideAfter = 7)
        {
            _hud.SetLevel(0);
            bool listen = _listening && _listener.Running && (keepListening || _s.FollowUp);
            if (listen)
            {
                _listener.Listen(keepListening ? Math.Max(10, _s.FollowUpSeconds) : _s.FollowUpSeconds);   // conversación: sin repetir el nombre
                _hud.SetState(HudState.Listening);
                if (_s.UiSounds && keepListening) Chirp.Play(true);
            }
            else
            {
                _hud.SetState(_listening ? HudState.Idle : HudState.Muted);
                Unduck();
            }
            if (!_hud.Busy) _hud.HideLater(listen ? Math.Max(hideAfter, _s.FollowUpSeconds + 1) : hideAfter);
        }

        // ---------------------------------------------------------------- IHost

        public void Say(string text) => UI.BeginInvoke(new Action(() =>
        {
            ShowPanel(false);
            _hud.SetHeard("");
            if (_s.UiSounds) Chirp.Play(false);
            Respond(text);
        }));

        public void Show(string text) => UI.BeginInvoke(new Action(() =>
        {
            ShowPanel(false);
            _hud.SetReply(text);
        }));

        public void Notify(string title, string text) => UI.BeginInvoke(new Action(() =>
        {
            try { _tray?.ShowBalloonTip(6000, title, text, System.Windows.Forms.ToolTipIcon.None); } catch { }
        }));

        public void StopSpeaking()
        {
            _speaker?.Stop();
            _speaking = false;
        }

        public void OpenSettings() => UI.BeginInvoke(new Action(() =>
        {
            if (_settingsWin != null)
            {
                _settingsWin.Activate();
                return;
            }
            _settingsWin = new SettingsWindow(_s);
            _settingsWin.TestAi = async tmp =>
            {
                var probe = new AiClient(() => tmp, _engine);
                return await probe.TestAsync();
            };
            _settingsWin.TestVoice = (tmp, phrase) =>
            {
                // Prueba con los ajustes sin guardar; al cerrar la ventana se vuelve a los guardados.
                StopSpeaking();
                NeuralVoices.Locate(tmp);
                _speaker.Update(tmp);
                _speaker.Speak(phrase);
            };
            _settingsWin.RunDiagnostics = ShowVoiceDiagnostics;
            _settingsWin.Saved += ns =>
            {
                _s = ns;
                _s.Save();
                ApplySettings();
            };
            _settingsWin.Closed += (o, e) =>
            {
                _settingsWin = null;
                NeuralVoices.Locate(_s);
                _speaker.Update(_s);
            };
            _settingsWin.Show();
            _settingsWin.Activate();
        }));

        public void ApplySettings() => UI.BeginInvoke(new Action(() =>
        {
            _s.Save();
            if (LocalAi.IsLocal(_s)) _ = LocalAi.Warm(_s);
            NeuralVoices.Locate(_s);
            _speaker.Update(_s);
            _hud.Apply(_s);
            if (ListenKey() != _listenKey || (!_listener.Running && _listening && _s.VoiceInput)) StartListening();
            else _listener.UseSettings(_s);
            RegisterHotkey();
            ApplyStartup();
            if (_tray != null) _tray.Text = _s.Name;
            UpdateListenItem();
        }));

        public void Quit() => UI.BeginInvoke(new Action(() =>
        {
            Task.Delay(1800).ContinueWith(_ => UI.BeginInvoke(new Action(Shutdown)));
        }));

        void Shutdown()
        {
            try
            {
                _tick.Stop();
                _meter.Stop();
                _ptt.Stop();
                try { _duckChain.Wait(1500); } catch { }
                Ducker.Restore();
                _listener?.Dispose();
                _speaker?.Dispose();
                if (_msg != null) Native.UnregisterHotKey(_msg.Handle, HotkeyId);
                if (_tray != null)
                {
                    _tray.Visible = false;
                    _tray.Dispose();
                }
            }
            catch { }
            _app.Shutdown();
        }

        public void SetListening(bool on) => UI.BeginInvoke(new Action(() =>
        {
            _listening = on;
            StartListening();
            _hud.SetState(on ? HudState.Idle : HudState.Muted);
            UpdateListenItem();
        }));

        public bool Listening => _listening && _listener != null && _listener.Running;

        public string ClipboardText()
        {
            string Get()
            {
                try { return Clipboard.ContainsText() ? Clipboard.GetText() : ""; }
                catch { return ""; }
            }
            if (UI.CheckAccess()) return Get();
            // Desde otro hilo, con un tope: si la ventana estuviera ocupada, no se queda esperando para siempre.
            try { return UI.Invoke(new Func<string>(Get), DispatcherPriority.Send, CancellationToken.None, TimeSpan.FromSeconds(3)) ?? ""; }
            catch (Exception e)
            {
                Log.Write("Portapapeles: " + e.Message);
                return "";
            }
        }

        public void SetClipboard(string text) => UI.BeginInvoke(new Action(() =>
        {
            try { Clipboard.SetText(text ?? ""); } catch { }
        }));

        public void HidePanel() => UI.BeginInvoke(new Action(() => _hud.HideLater(2.5)));

        public IntPtr TargetWindow => _target;

        // ---------------------------------------------------------------- panel, bandeja, atajo

        void ShowPanel(bool activate)
        {
            if (!_hud.IsVisible) _target = CurrentTarget();
            _hud.ShowHud(activate);
        }

        IntPtr CurrentTarget()
        {
            IntPtr fg = Native.GetForegroundWindow();
            return IsOurs(fg) ? _target : fg;
        }

        bool IsOurs(IntPtr h)
        {
            if (h == IntPtr.Zero) return true;
            Native.GetWindowThreadProcessId(h, out uint pid);
            return pid == (uint)Environment.ProcessId;
        }

        void OnTick()
        {
            IntPtr fg = Native.GetForegroundWindow();
            if (!IsOurs(fg) && Native.WindowClass(fg) != "Shell_TrayWnd") _target = fg;
            try { _engine.Tick(); }
            catch (Exception e) { Log.Write("Avisos: " + e.Message); }
            // Si la escucha se cayó (micrófono desconectado, Windows la cortó…), se vuelve a montar sola cada 20 segundos.
            bool down = _listening && _s.VoiceInput && !_listener.Running;
            if (!down) _notListeningSince = DateTime.MaxValue;
            else if (_notListeningSince == DateTime.MaxValue) _notListeningSince = DateTime.Now;
            if (down && (DateTime.Now - _notListeningSince).TotalSeconds > 15 && (DateTime.Now - _lastListenRetry).TotalSeconds > 20)
            {
                _lastListenRetry = DateTime.Now;
                Log.Write("La escucha no está en marcha (" + _listener.Status + "): la reinicio.");
                StartListening();
                if (_listener.Running) _hud.SetMic(true);
            }
            // ¿También está activo el mod JARVIS de Windhawk? Entonces responden los dos (respuestas duplicadas).
            if ((DateTime.Now - _modCheckAt).TotalSeconds > 30)
            {
                _modCheckAt = DateTime.Now;
                bool mod = FindWindow("WindhawkJarvisHud", null) != IntPtr.Zero;
                if (mod && !_modWarned)
                {
                    _modWarned = true;
                    string m = "Ojo" + Sir() + ": el mod JARVIS de Windhawk también está activo, así que le respondemos los dos y se oyen respuestas duplicadas. " +
                               "Desactívelo en Windhawk (o cierre este programa si prefiere el mod).";
                    Log.Write("Detectado el mod JARVIS de Windhawk en marcha.");
                    Notify(_s.Name, m);
                    Say(m);
                }
                if (!mod) _modWarned = false;
            }
            // Red de seguridad: si la voz terminó y no llegó el aviso, el micrófono no se queda en pausa.
            if (_speaker != null && !_speaker.Busy)
            {
                if (_speaking && ++_stuckTicks >= 2)
                {
                    Log.Write("La voz terminó sin avisar: reanudo la escucha.");
                    _stuckTicks = 0;
                    OnSpeakEnd();
                }
                else if (!_speaking) _listener.Resume();
            }
            else _stuckTicks = 0;
        }

        int _stuckTicks;
        DateTime _modCheckAt = DateTime.MinValue;
        bool _modWarned;
        [System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
        static extern IntPtr FindWindow(string cls, string title);
        DateTime _lastListenRetry = DateTime.Now;
        DateTime _notListeningSince = DateTime.MaxValue;

        // Lo que está diciendo ahora (para no confundir su propia voz con una orden).
        readonly System.Text.StringBuilder _saying = new System.Text.StringBuilder();
        readonly object _sayingLock = new object();

        void SpeakOut(string text)
        {
            Saying(text);
            _speaker.Speak(text);
        }

        void Saying(string text)
        {
            lock (_sayingLock)
            {
                if (!_speaking && DateTime.Now > _saidUntil) _saying.Clear();   // lo de antes ya no cuenta
                if (_saying.Length > 4000) _saying.Clear();
                _saying.Append(' ').Append(Text.Squash(text));
            }
        }

        // Antes bastaba con que las palabras oídas aparecieran sueltas en lo último que dijo: «Jarvis» a secas
        // justo después de «diga Jarvis cuando me necesite», o «sí, pon la música» tras «¿quiere que ponga música?»,
        // se tomaban por eco y se tiraban. Ahora el nombre no cuenta, se comparan palabras enteras y,
        // una vez callada, solo es eco si repite literalmente un trozo de lo que dijo.
        bool IsEcho(string heard)
        {
            if (!_speaking && DateTime.Now > _saidUntil) return false;
            string h = Text.Squash(WakeWords.Strip(heard ?? "", _s, out _));
            var words = h.Split(' ', StringSplitOptions.RemoveEmptyEntries);
            int big = words.Count(w => w.Length > 3);
            if (big == 0) return false;                     // solo el nombre o palabras cortas: es usted
            lock (_sayingLock)
            {
                string said = " " + _saying.ToString() + " ";
                if (_speaking)
                {
                    var saidWords = new System.Collections.Generic.HashSet<string>(said.Split(' ', StringSplitOptions.RemoveEmptyEntries));
                    int inside = words.Count(w => w.Length > 3 && saidWords.Contains(w));
                    return big >= 2 && inside >= Math.Ceiling(big * 0.75);
                }
                return words.Length >= 3 && said.Contains(" " + string.Join(" ", words) + " ");
            }
        }

        void CreateTray()
        {
            _tray = new System.Windows.Forms.NotifyIcon { Text = _s.Name, Visible = true };
            try { _tray.Icon = System.Drawing.Icon.ExtractAssociatedIcon(Environment.ProcessPath); }
            catch { _tray.Icon = System.Drawing.SystemIcons.Application; }
            var menu = new System.Windows.Forms.ContextMenuStrip();
            menu.Items.Add("Mostrar panel (" + _s.Hotkey + ")", null, (o, e) => ShowPanel(true));
            _listenItem = new System.Windows.Forms.ToolStripMenuItem("Escuchar", null, (o, e) => SetListening(!_listening));
            menu.Items.Add(_listenItem);
            menu.Items.Add("Reiniciar la escucha", null, (o, e) =>
            {
                _listening = true;
                StartListening();
                UpdateListenItem();
                Notify(_s.Name, _listener.Running ? "Escuchando de nuevo." : "No puedo escuchar: " + _listener.Status);
            });
            menu.Items.Add("Diagnóstico de voz", null, (o, e) => ShowVoiceDiagnostics());
            menu.Items.Add(new System.Windows.Forms.ToolStripSeparator());
            menu.Items.Add("Ajustes…", null, (o, e) => OpenSettings());
            menu.Items.Add(new System.Windows.Forms.ToolStripSeparator());
            menu.Items.Add("Salir", null, (o, e) => Shutdown());
            _tray.ContextMenuStrip = menu;
            _tray.MouseClick += (o, e) =>
            {
                if (e.Button == System.Windows.Forms.MouseButtons.Left) UI.BeginInvoke(new Action(() => ShowPanel(true)));
            };
            UpdateListenItem();
        }

        void UpdateListenItem()
        {
            _hud?.SetMic(_listening && _s.VoiceInput);
            if (_listenItem == null) return;
            _listenItem.Checked = _listening && _s.VoiceInput;
            _listenItem.Enabled = _s.VoiceInput;
            _listenItem.Text = _s.VoiceInput ? "Escuchar «" + _s.WakeWord + "»" : "Escuchar (desactivado en ajustes)";
        }

        void RegisterHotkey()
        {
            if (_msg == null)
            {
                var p = new HwndSourceParameters("JARVIS-atajos") { Width = 0, Height = 0, WindowStyle = 0, ParentWindow = new IntPtr(-3) };
                _msg = new HwndSource(p);
                _msg.AddHook(WndProc);
            }
            Native.UnregisterHotKey(_msg.Handle, HotkeyId);
            if (!Native.ParseHotkey(_s.Hotkey, out uint mods, out uint vk))
            {
                Log.Write("Atajo no válido: " + _s.Hotkey);
                return;
            }
            if (!Native.RegisterHotKey(_msg.Handle, HotkeyId, mods | Native.MOD_NOREPEAT, vk))
            {
                Log.Write("El atajo " + _s.Hotkey + " ya lo usa otro programa.");
                Notify(_s.Name, "El atajo " + _s.Hotkey + " ya lo usa otro programa. Cámbielo en los ajustes.");
            }
        }

        IntPtr WndProc(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
        {
            if (msg == (int)Native.WM_HOTKEY && wParam.ToInt32() == HotkeyId)
            {
                handled = true;
                OnHotkey();
            }
            return IntPtr.Zero;
        }

        void OnHotkey()
        {
            if (_hud.IsVisible && _hud.IsActive)
            {
                StopSpeaking();
                _listener.Sleep();
                _hud.HideHud();
                return;
            }
            _target = CurrentTarget();
            StopSpeaking();
            _hud.ShowHud(true);
            _hud.SetHeard("");
            if (_listener.Running)
            {
                _listener.Listen(8);
                Duck();
                _hud.SetState(HudState.Listening);
                _hud.SetReply("Le escucho" + Sir() + ". También puede escribir.");
                if (_s.UiSounds) Chirp.Play(true);
            }
            else
            {
                _hud.SetState(HudState.Idle);
                _hud.SetReply("Escriba su orden" + Sir() + ".");
            }
        }

        void ApplyStartup()
        {
            try
            {
                using var key = Microsoft.Win32.Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Run", true);
                if (key == null) return;
                if (_s.StartWithWindows) key.SetValue("JARVIS", "\"" + Environment.ProcessPath + "\" --inicio");
                else if (key.GetValue("JARVIS") != null) key.DeleteValue("JARVIS");
            }
            catch (Exception e)
            {
                Log.Write("Inicio con Windows: " + e.Message);
            }
        }
    }

    // Pitidos cortos al empezar a escuchar y al avisar (generados en memoria).
    static class Chirp
    {
        static byte[] _up, _down;

        static byte[] Make(double f0, double f1, int ms)
        {
            const int rate = 22050;
            int n = rate * ms / 1000;
            using var ms2 = new MemoryStream();
            using var w = new BinaryWriter(ms2);
            w.Write(Encoding.ASCII.GetBytes("RIFF"));
            w.Write(36 + n * 2);
            w.Write(Encoding.ASCII.GetBytes("WAVEfmt "));
            w.Write(16);
            w.Write((short)1);
            w.Write((short)1);
            w.Write(rate);
            w.Write(rate * 2);
            w.Write((short)2);
            w.Write((short)16);
            w.Write(Encoding.ASCII.GetBytes("data"));
            w.Write(n * 2);
            double phase = 0;
            for (int i = 0; i < n; i++)
            {
                double t = (double)i / n;
                double f = f0 + (f1 - f0) * t;
                phase += 2 * Math.PI * f / rate;
                double env = Math.Min(1, t * 12) * Math.Pow(1 - t, 1.6);
                double v = (Math.Sin(phase) * 0.7 + Math.Sin(phase * 2) * 0.18) * env * 0.32;
                w.Write((short)(v * short.MaxValue));
            }
            w.Flush();
            return ms2.ToArray();
        }

        public static void Play(bool up)
        {
            try
            {
                var data = up ? (_up ??= Make(880, 1480, 110)) : (_down ??= Make(1320, 780, 140));
                var p = new System.Media.SoundPlayer(new MemoryStream(data));
                p.Play();
            }
            catch { }
        }
    }
}
