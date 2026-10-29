using System;
using System.IO;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Jarvis.Commands;
using Jarvis.Core;
using Jarvis.Ui;

namespace Jarvis
{
    // Control desde el celular con ntfy (gratis): el usuario escribe en un canal secreto de la app ntfy
    // («pon música», «¿qué tiempo hace?», «¿terminó la descarga?») y JARVIS contesta en el mismo canal.
    // El canal tiene un nombre aleatorio largo (quien no lo sepa no puede mandar nada) y lo que podría hacer daño
    // a distancia (apagar, cerrar programas, escribir, borrar datos) no se hace desde el celular (Engine.RemoteBlocked).
    public sealed partial class JarvisApp
    {
        static readonly HttpClient RemoteHttp = Net.Create(Timeout.InfiniteTimeSpan);
        CancellationTokenSource _remoteCts;
        string _remoteKey = "";
        bool _remoteOnline;
        DateTime _remoteLast = DateTime.MinValue;
        const string ReplyTitle = "JARVIS";

        public bool RemoteOnline => _remoteOnline;

        static string RemoteServer(Settings s) => s.NtfyServer.Trim() == "" ? "https://ntfy.sh" : s.NtfyServer.Trim().TrimEnd('/');

        // Un nombre que no se puede adivinar: «jarvis-» y 24 letras y números al azar.
        public static string NewRemoteTopic()
        {
            const string abc = "abcdefghijkmnpqrstuvwxyz23456789";
            var sb = new StringBuilder("jarvis-");
            foreach (byte b in RandomNumberGenerator.GetBytes(24)) sb.Append(abc[b % abc.Length]);
            return sb.ToString();
        }

        // Al arrancar y al guardar ajustes: enciende, apaga o reinicia la escucha del canal.
        void ApplyRemote()
        {
            bool on = _s.RemoteControl && _s.RemoteTopic.Trim().Length >= 16;
            string key = on ? RemoteServer(_s) + "/" + _s.RemoteTopic.Trim() : "";
            if (key == _remoteKey) return;
            _remoteKey = key;
            _remoteCts?.Cancel();
            _remoteCts = null;
            _remoteOnline = false;
            if (!on)
            {
                if (_s.RemoteControl) Log.Write("Control desde el celular: falta el nombre del canal.");
                return;
            }
            _remoteCts = new CancellationTokenSource();
            _ = RemoteLoop(RemoteServer(_s), _s.RemoteTopic.Trim(), _remoteCts.Token);
        }

        async Task RemoteLoop(string server, string topic, CancellationToken ct)
        {
            // Solo lo que llegue desde ahora (no órdenes viejas guardadas en el servidor).
            string since = DateTimeOffset.UtcNow.ToUnixTimeSeconds().ToString();
            int fails = 0;
            Log.Write("Control desde el celular: escuchando el canal en " + server + ".");
            while (!ct.IsCancellationRequested)
            {
                try
                {
                    using var conn = CancellationTokenSource.CreateLinkedTokenSource(ct);
                    conn.CancelAfter(TimeSpan.FromSeconds(120));   // ntfy manda «keepalive» cada 45 s: si no llega nada, se reconecta
                    using var req = new HttpRequestMessage(HttpMethod.Get, server + "/" + Uri.EscapeDataString(topic) + "/json?since=" + Uri.EscapeDataString(since));
                    using var res = await RemoteHttp.SendAsync(req, HttpCompletionOption.ResponseHeadersRead, conn.Token);
                    res.EnsureSuccessStatusCode();
                    _remoteOnline = true;
                    fails = 0;
                    using var stream = await res.Content.ReadAsStreamAsync(conn.Token);
                    using var reader = new StreamReader(stream, Encoding.UTF8);
                    string line;
                    while ((line = await reader.ReadLineAsync(conn.Token)) != null)
                    {
                        conn.CancelAfter(TimeSpan.FromSeconds(120));
                        if (line.Trim() == "") continue;
                        using var doc = JsonDocument.Parse(line);
                        var e = doc.RootElement;
                        if (Get(e, "event") != "message") continue;
                        string id = Get(e, "id");
                        if (id != "") since = id;
                        // Sus propias respuestas llegan por el mismo canal: se ignoran.
                        if (Get(e, "title") == ReplyTitle) continue;
                        if (e.TryGetProperty("tags", out var tags) && tags.ValueKind == JsonValueKind.Array && tags.ToString().Contains("jarvis")) continue;
                        string text = Get(e, "message").Trim();
                        if (text == "") continue;
                        UI.BeginInvoke(new Action(() => _ = FromPhone(text, server, topic)));
                    }
                }
                catch (OperationCanceledException) when (ct.IsCancellationRequested) { break; }
                catch (Exception e)
                {
                    _remoteOnline = false;
                    fails++;
                    if (fails == 1 || fails % 10 == 0) Log.Write("Control desde el celular: sin conexión con ntfy (" + e.GetBaseException().Message + "). Reintento.");
                    try { await Task.Delay(TimeSpan.FromSeconds(Math.Min(60, 2 << Math.Min(fails, 5))), ct); } catch { break; }
                }
            }
            _remoteOnline = false;
        }

        static string Get(JsonElement e, string name) => e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() ?? "" : "";

        async Task FromPhone(string text, string server, string topic)
        {
            if (text.Length > 500) text = text.Substring(0, 500);
            // Como mucho una orden cada segundo y medio (por si algo manda muchas seguidas).
            if ((DateTime.Now - _remoteLast).TotalSeconds < 1.5)
            {
                await Reply(server, topic, "Despacio: una orden cada vez, por favor.");
                return;
            }
            _remoteLast = DateTime.Now;
            Log.Write("Celular: " + text);
            string reply;
            Engine.FromPhone = true;   // vale para esta orden y para lo que pida la IA al contestarla
            try
            {
                var local = await _engine.HandleAsync(text);
                byte[] screen = null;
                string ask = text;
                if (local != null && local.ScreenQuestion != null)
                {
                    IntPtr target = _target;
                    try { screen = await Task.Run(() => VisionModule.CaptureJpeg(target)); } catch { }
                    ask = local.ScreenQuestion;
                    local = null;
                }
                if (local != null) reply = local.Silent || local.Say.Trim() == "" ? "Hecho." : local.Say;
                else if (_ai.Ready)
                {
                    using var cts = new CancellationTokenSource(TimeSpan.FromMinutes(2));
                    reply = await _ai.AskAsync(ask, "", null, cts.Token, screen);
                    if (reply.Trim() == "") reply = "Hecho.";
                }
                else reply = "No entendí «" + text + "». Pruebe con órdenes como «pon música», «¿qué tiempo hace?» o «recuérdame en 10 minutos llamar a mamá».";
            }
            catch (Exception e)
            {
                Log.Write("Orden del celular: " + e);
                reply = "Algo falló: " + e.GetBaseException().Message;
            }
            finally
            {
                Engine.FromPhone = false;
            }
            Log.Write("  → al celular: " + Text.Preview(reply, 120));
            await Reply(server, topic, reply);
            // En el equipo, solo una línea discreta en el panel si está abierto (sin hablar: quien manda está lejos).
            if (_hud.IsVisible && _turn == null && !_speaking) _hud.SetReply("📱 " + text + "\n" + reply);
        }

        static async Task Reply(string server, string topic, string text)
        {
            try
            {
                using var req = new HttpRequestMessage(HttpMethod.Post, server + "/" + Uri.EscapeDataString(topic));
                req.Headers.TryAddWithoutValidation("Title", ReplyTitle);
                req.Headers.TryAddWithoutValidation("Tags", "jarvis,robot");
                req.Content = new StringContent(text, Encoding.UTF8, "text/plain");
                using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(15));
                using var res = await RemoteHttp.SendAsync(req, cts.Token);
                if (!res.IsSuccessStatusCode) Log.Write("Respuesta al celular: ntfy respondió " + (int)res.StatusCode);
            }
            catch (Exception e)
            {
                Log.Write("Respuesta al celular: " + e.GetBaseException().Message);
            }
        }
    }
}
