using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using Jarvis.Ai;
using Jarvis.Core;
using Jarvis.Speech;
using Jarvis.Ui;

namespace Jarvis
{
    // «Prueba completa»: revisa todo lo que necesita JARVIS y dice qué falla y cómo arreglarlo.
    public sealed partial class JarvisApp
    {
        CheckWindow _checkWin;
        bool _checking;
        static readonly HttpClient CheckHttp = Net.Create(TimeSpan.FromSeconds(12));

        public void ShowSystemCheck() => UI.BeginInvoke(new Action(() =>
        {
            if (_checkWin == null)
            {
                _checkWin = new CheckWindow(_s.Name) { Version = typeof(JarvisApp).Assembly.GetName().Version?.ToString(3) ?? "" };
                _checkWin.RunAgain += () => _ = RunChecks(false);
                _checkWin.Closed += (o, e) => _checkWin = null;
                _checkWin.Show();
            }
            _checkWin.Activate();
            _ = RunChecks(true);
        }));

        static Action Open(string target) => () => System.Diagnostics.Process.Start(new ProcessStartInfo(target) { UseShellExecute = true });

        async Task RunChecks(bool speak)
        {
            if (_checking || _checkWin == null) return;
            _checking = true;
            var w = _checkWin;
            w.Begin();
            void Add(CheckItem it) { if (_checkWin == w) w.Add(it); }
            try
            {
                // ---- micrófono y escucha (lo mismo que el diagnóstico de voz)
                const string G1 = "Micrófono y escucha";
                var input = _listener;
                var voice = await Task.Run(() => VoiceDiagnostics.Run(_s, input));
                foreach (var v in voice)
                    Add(new CheckItem
                    {
                        Group = G1,
                        State = v.Ok ? CheckState.Ok : CheckState.Fail,
                        Text = v.Text,
                        FixLabel = v.Ok || v.Fix == "" ? "" : "Abrir ajustes",
                        Fix = v.Ok || v.Fix == "" ? null : Open(v.Fix),
                    });
                if (!_listening) Add(new CheckItem { Group = G1, State = CheckState.Warn, Text = "La escucha está apagada a propósito (botón del micrófono o «deja de escuchar»).", FixLabel = "Encender", Fix = () => SetListening(true) });
                if (input != null && !input.Running && _listening && _s.VoiceInput)
                    Add(new CheckItem { Group = G1, State = CheckState.Fail, Text = "La escucha no arrancó: " + input.Status + ".", FixLabel = "Reintentar", Fix = () => UI.BeginInvoke(new Action(StartListening)) });

                // ---- voz
                const string G2 = "Voz";
                if (!_s.VoiceOutput) Add(new CheckItem { Group = G2, State = CheckState.Warn, Text = "La voz está desactivada: solo contesta en el panel.", FixLabel = "Ajustes", Fix = OpenSettings });
                float vol = AudioDevices.GetVolume();
                Add(CheckItem.Of(G2, vol >= 0, "Hay altavoces o auriculares predeterminados.", "Windows no tiene ningún dispositivo de sonido de salida.", "Abrir sonido", Open("ms-settings:sound")));
                if (vol >= 0)
                {
                    bool muted = AudioDevices.GetMute() == true;
                    Add(CheckItem.Of(G2, !muted && vol >= 0.1f, "Volumen del equipo al " + (int)Math.Round(vol * 100) + " %.",
                        muted ? "El sonido del equipo está silenciado: no me oirá." : "El volumen del equipo está muy bajo (" + (int)Math.Round(vol * 100) + " %).",
                        "Subir", () => { AudioDevices.SetMute(false); if (AudioDevices.GetVolume() < 0.3f) AudioDevices.SetVolume(0.5f); }, onlyWarn: true));
                }
                Add(new CheckItem { Group = G2, State = CheckState.Info, Text = "Hablo con la voz " + _speaker.EngineName + "." });
                if (_s.VoiceEngine == "neural" && NeuralVoices.PiperExe == "")
                {
                    string inst = Path.Combine(AppContext.BaseDirectory, "instalar-voces.bat");
                    Add(new CheckItem
                    {
                        Group = G2, State = CheckState.Warn, Text = "Eligió la voz neuronal, pero Piper no está instalado: uso la voz de Windows.",
                        FixLabel = File.Exists(inst) ? "Instalar voces" : "", Fix = File.Exists(inst) ? (Action)(() => System.Diagnostics.Process.Start(new ProcessStartInfo(inst) { UseShellExecute = true, WorkingDirectory = AppContext.BaseDirectory })) : null,
                    });
                }
                if (_s.VoiceEngine == "cloud" && !_speaker.CloudReady)
                    Add(new CheckItem { Group = G2, State = CheckState.Fail, Text = "Eligió una voz en la nube, pero falta su clave (o la región, en Azure).", FixLabel = "Ajustes", Fix = OpenSettings });
                if (_speaker.LastError != "")
                    Add(new CheckItem { Group = G2, State = CheckState.Warn, Text = "Último error de la voz: " + Text.Preview(_speaker.LastError, 140) });

                // ---- internet
                const string G3 = "Internet";
                bool online = false;
                var sw = Stopwatch.StartNew();
                try
                {
                    using var res = await CheckHttp.GetAsync("https://www.gstatic.com/generate_204");
                    online = (int)res.StatusCode < 400;
                }
                catch { }
                Add(CheckItem.Of(G3, online, "Conectado (" + sw.ElapsedMilliseconds + " ms).", "Sin conexión a internet: no funcionan el reconocimiento moderno, la IA en la nube, el tiempo ni YouTube.",
                    "Abrir red", Open("ms-settings:network")));

                // ---- inteligencia artificial
                const string G4 = "Inteligencia artificial";
                if (!_ai.Ready)
                    Add(new CheckItem { Group = G4, State = CheckState.Warn, Text = "Sin IA conectada: entiendo las órdenes, pero no conversaciones ni frases nuevas. Conecte Ollama (gratis, en este equipo) o una clave de Gemini, Claude u OpenAI.", FixLabel = "Ajustes", Fix = OpenSettings });
                else
                {
                    if (LocalAi.IsLocal(_s))
                    {
                        List<string> models = null;
                        try { models = await LocalAi.ListModels(_s); } catch { }
                        Add(CheckItem.Of(G4, models != null && models.Count > 0,
                            "Servidor local en " + LocalAi.BaseUrl(_s) + " con " + (models?.Count ?? 0) + " modelos: " + string.Join(", ", (models ?? new List<string>()).Take(4)) + ".",
                            models == null ? "No encuentro Ollama en " + LocalAi.BaseUrl(_s) + ". Ábralo o ejecute «ollama serve»." : "Ollama no tiene ningún modelo. Instale uno, por ejemplo con «ollama pull qwen3».",
                            models == null ? "Descargar Ollama" : "", models == null ? Open("https://ollama.com/download") : null));
                    }
                    var t = Stopwatch.StartNew();
                    var probe = _ai.TestAsync();
                    bool done = await Task.WhenAny(probe, Task.Delay(TimeSpan.FromSeconds(60))) == probe;
                    string reply = done ? await probe : "";
                    bool ok = done && _ai.LastOk;
                    Add(CheckItem.Of(G4, ok, "Responde " + _ai.ProviderLabel + " en " + t.Elapsed.TotalSeconds.ToString("0.0") + " s.",
                        !done ? "La IA no respondió en un minuto (" + _ai.ProviderLabel + ")." : "La IA falla: " + Text.Preview(reply, 160), "Ajustes", OpenSettings));
                    if (ok && t.Elapsed.TotalSeconds > 8)
                        Add(new CheckItem { Group = G4, State = CheckState.Warn, Text = "La IA tarda bastante en contestar. Con Ollama, pruebe un modelo más pequeño (qwen3:4b o llama3.2)." });
                }

                // ---- integraciones (solo las configuradas)
                const string G5 = "Integraciones";
                if (_s.HaUrl.Trim() != "")
                {
                    string msg; bool ok = false;
                    try
                    {
                        using var req = new HttpRequestMessage(HttpMethod.Get, _s.HaUrl.Trim().TrimEnd('/') + "/api/");
                        req.Headers.TryAddWithoutValidation("Authorization", "Bearer " + _s.HaToken.Trim());
                        using var res = await CheckHttp.SendAsync(req);
                        ok = res.IsSuccessStatusCode;
                        msg = (int)res.StatusCode == 401 ? "Home Assistant rechaza el token." : "Home Assistant respondió " + (int)res.StatusCode + ".";
                    }
                    catch (Exception e) { msg = "No llego a Home Assistant en " + _s.HaUrl.Trim() + " (" + e.GetBaseException().Message + ")."; }
                    Add(CheckItem.Of(G5, ok, "Home Assistant conectado.", msg, "Ajustes", OpenSettings));
                }
                if (_s.NtfyTopic.Trim() != "")
                {
                    bool ok = false;
                    string server = _s.NtfyServer.Trim() == "" ? "https://ntfy.sh" : _s.NtfyServer.Trim().TrimEnd('/');
                    try { using var res = await CheckHttp.GetAsync(server + "/v1/health"); ok = res.IsSuccessStatusCode; } catch { }
                    Add(CheckItem.Of(G5, ok, "Avisos al celular (ntfy) disponibles.", "No llego al servidor de ntfy (" + server + ").", "Ajustes", OpenSettings));
                }
                if (_s.CalendarUrl.Trim() != "")
                {
                    bool ok = false; string why = "";
                    string first = _s.CalendarUrl.Split(new[] { '\n', ';', ' ' }, StringSplitOptions.RemoveEmptyEntries).FirstOrDefault() ?? "";
                    try
                    {
                        string body = await CheckHttp.GetStringAsync(first.Trim().Replace("webcal://", "https://"));
                        ok = body.Contains("BEGIN:VCALENDAR");
                        if (!ok) why = "el enlace no es un calendario iCal";
                    }
                    catch (Exception e) { why = e.GetBaseException().Message; }
                    Add(CheckItem.Of(G5, ok, "Agenda conectada.", "No puedo leer la agenda: " + why + ".", "Ajustes", OpenSettings));
                }
                if (_s.HaUrl.Trim() == "" && _s.NtfyTopic.Trim() == "" && _s.CalendarUrl.Trim() == "")
                    Add(new CheckItem { Group = G5, State = CheckState.Info, Text = "Ninguna configurada (agenda, Home Assistant, avisos al celular). Son opcionales." });

                // ---- equipo
                const string G6 = "Equipo";
                bool mod = FindWindow("WindhawkJarvisHud", null) != IntPtr.Zero;
                Add(CheckItem.Of(G6, !mod, "El mod JARVIS de Windhawk no está activo (bien: no hay respuestas duplicadas).",
                    "El mod JARVIS de Windhawk también está activo: responderemos los dos. Desactívelo en Windhawk."));
                if (Native.MicInUseByOthers())
                    Add(new CheckItem { Group = G6, State = CheckState.Info, Text = "Otra aplicación está usando el micrófono (¿una llamada?): mientras dure, contesto solo en el panel." });
                Add(new CheckItem { Group = G6, State = CheckState.Info, Text = "JARVIS " + _checkWin?.Version + (_s.StartWithWindows ? ", arranca con Windows." : ", no arranca con Windows.") + " Registro: " + Path.Combine(Settings.Folder, "jarvis.log") });
            }
            catch (Exception e)
            {
                Log.Write("Prueba completa: " + e);
                Add(new CheckItem { Group = "Error", State = CheckState.Fail, Text = "La prueba se interrumpió: " + e.Message });
            }
            finally
            {
                _checking = false;
            }
            if (_checkWin != w) return;
            w.Done();
            var bad = w.Items.Where(i => i.State == CheckState.Fail).ToList();
            var warn = w.Items.Where(i => i.State == CheckState.Warn).ToList();
            string summary = bad.Count == 0 && warn.Count == 0 ? "Prueba completa: todo en orden" + Sir() + "."
                : bad.Count > 0 ? "Encontré " + (bad.Count == 1 ? "un problema" : bad.Count + " problemas") + ". " + bad[0].Text + (bad.Count > 1 ? " Los demás están en la ventana." : "")
                : "Todo funciona, con " + (warn.Count == 1 ? "un aviso" : warn.Count + " avisos") + ": " + warn[0].Text;
            Log.Write("Prueba completa: " + bad.Count + " problemas, " + warn.Count + " avisos.");
            if (speak && CanSpeak) SpeakOut(summary);
        }
    }
}
