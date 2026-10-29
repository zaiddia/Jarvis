using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Threading;
using Jarvis.Core;

namespace Jarvis
{
    // Actualización automática desde las Releases de GitHub (las que publica la compilación automática).
    // Busca al arrancar y cada 12 horas; avisa una vez por versión. «Actualízate» la descarga, comprueba su huella,
    // cambia los archivos del programa cuando JARVIS se cierra y lo vuelve a abrir. Ajustes y datos no se tocan.
    public sealed partial class JarvisApp
    {
        static readonly HttpClient UpdateHttp = CreateUpdateHttp();
        Releases.Info _update;
        DateTime _nextUpdateCheck = DateTime.Now.AddMinutes(1);
        bool _updating;

        static HttpClient CreateUpdateHttp()
        {
            var h = Net.Create(TimeSpan.FromMinutes(10));
            h.DefaultRequestHeaders.UserAgent.ParseAdd("JARVIS-Windows");   // GitHub exige un User-Agent
            h.DefaultRequestHeaders.Accept.ParseAdd("application/vnd.github+json");
            return h;
        }

        static Version Current => Releases.ParseVersion(typeof(JarvisApp).Assembly.GetName().Version?.ToString(3) ?? "0.0.0");

        // Cada segundo (desde OnTick): ¿toca mirar si hay versión nueva?
        void UpdateTick()
        {
            if (!_s.AutoUpdate || _updating || DateTime.Now < _nextUpdateCheck) return;
            _nextUpdateCheck = DateTime.Now.AddHours(12);
            _ = CheckUpdate(announce: true);
        }

        async Task<Releases.Info> CheckUpdate(bool announce)
        {
            try
            {
                string repo = (_s.UpdateRepo ?? "").Trim().Trim('/');
                if (repo.Count(ch => ch == '/') != 1) repo = "zaiddia/Jarvis";
                string json = await UpdateHttp.GetStringAsync("https://api.github.com/repos/" + repo + "/releases?per_page=30");
                var info = Releases.Newest(json);
                _update = info != null && Releases.IsNewer(info.Version, Current) ? info : null;
                Log.Write("Actualizaciones: tengo la " + Current + (info != null ? ", la última publicada es la " + info.Version : ", no encuentro versiones publicadas") + ".");
                if (_update != null && announce)
                {
                    string v = _update.Version.ToString(3);
                    if (Store.Get("aviso-version", "") != v)
                    {
                        Store.Set("aviso-version", v);
                        string msg = "Hay una versión nueva de " + _s.Name + ": la " + v + ". Diga «actualízate» cuando quiera y me instalo en un momento.";
                        UI.BeginInvoke(new Action(() => Notify(_s.Name, msg)));
                        UI.BeginInvoke(new Action(() =>
                        {
                            if (_turn == null && !_speaking && CanSpeak) Say(msg);
                        }));
                    }
                }
                return _update;
            }
            catch (Exception e)
            {
                Log.Write("Actualizaciones: no pude consultar GitHub: " + e.GetBaseException().Message);
                throw;
            }
        }

        // Para el motor («actualízate», «¿hay versión nueva?») y los ajustes.
        public async Task<string> Updates(bool install)
        {
            if (_updating) return "Ya me estoy actualizando" + Sir() + ".";
            Releases.Info info;
            try { info = await CheckUpdate(announce: false); }
            catch { return "No pude consultar si hay versión nueva. ¿Hay internet?"; }
            string cur = Current.ToString(3);
            if (info == null) return "Estoy al día" + Sir() + ": tengo la versión " + cur + ", la más reciente.";
            if (!install) return "Tengo la versión " + cur + " y ya está la " + info.Version.ToString(3) + ". Diga «actualízate» y me instalo.";
            _ = Install(info);
            return "Descargo la versión " + info.Version.ToString(3) + ". En cuanto esté, me reinicio" + Sir() + ".";
        }

        async Task Install(Releases.Info info)
        {
            if (_updating) return;
            _updating = true;
            string dir = Path.Combine(Path.GetTempPath(), "JARVIS-actualizacion", info.Version.ToString(3));
            try
            {
                if (Directory.Exists(dir)) Directory.Delete(dir, true);
                Directory.CreateDirectory(dir);
                string zip = Path.Combine(dir, "paquete.zip");

                // Descarga, enseñando el avance en el panel.
                using (var res = await UpdateHttp.GetAsync(info.Url, HttpCompletionOption.ResponseHeadersRead))
                {
                    res.EnsureSuccessStatusCode();
                    long total = res.Content.Headers.ContentLength ?? info.Size;
                    using var src = await res.Content.ReadAsStreamAsync();
                    using var dst = File.Create(zip);
                    var buf = new byte[81920];
                    long got = 0;
                    int last = -1, n;
                    while ((n = await src.ReadAsync(buf)) > 0)
                    {
                        await dst.WriteAsync(buf.AsMemory(0, n));
                        got += n;
                        int pct = total > 0 ? (int)(got * 100 / total) : -1;
                        if (pct / 10 != last / 10)
                        {
                            last = pct;
                            UI.BeginInvoke(new Action(() => _hud.SetReply("Descargando la versión " + info.Version.ToString(3) + (pct >= 0 ? "… " + pct + " %" : "…"))));
                        }
                    }
                }

                // Que sea exactamente lo publicado.
                var fi = new FileInfo(zip);
                if (info.Size > 0 && fi.Length != info.Size) throw new Exception("la descarga quedó incompleta (" + fi.Length + " de " + info.Size + " bytes)");
                if (info.Sha256 != "")
                {
                    string hash;
                    using (var fs = File.OpenRead(zip)) hash = Convert.ToHexString(SHA256.HashData(fs)).ToLowerInvariant();
                    if (hash != info.Sha256) throw new Exception("la huella del archivo no coincide con la publicada; no lo instalo");
                }

                string unpack = Path.Combine(dir, "contenido");
                ZipFile.ExtractToDirectory(zip, unpack, true);
                string exe = Directory.GetFiles(unpack, "Jarvis.exe", SearchOption.AllDirectories)
                                      .FirstOrDefault(p => string.Equals(Path.GetFileName(Path.GetDirectoryName(p)), "programa", StringComparison.OrdinalIgnoreCase));
                if (exe == null) throw new Exception("el paquete no trae programa\\Jarvis.exe");
                string from = Path.GetDirectoryName(exe);
                string to = AppContext.BaseDirectory.TrimEnd('\\', '/');

                // Un pequeño script cambia los archivos cuando este JARVIS ya se ha cerrado y abre el nuevo.
                int pid = Environment.ProcessId;
                string script = Path.Combine(dir, "actualizar.cmd");
                var sb = new StringBuilder();
                sb.Append("@echo off\r\nchcp 65001 >nul\r\nset n=0\r\n");
                sb.Append(":espera\r\n");
                sb.Append("tasklist /fi \"PID eq " + pid + "\" 2>nul | find \"" + pid + "\" >nul\r\n");
                sb.Append("if errorlevel 1 goto copia\r\n");
                sb.Append("set /a n+=1\r\nif %n% geq 30 goto copia\r\ntimeout /t 1 /nobreak >nul\r\ngoto espera\r\n");
                sb.Append(":copia\r\n");
                sb.Append("robocopy \"" + from + "\" \"" + to + "\" /e /r:5 /w:1 /njh /njs /nfl /ndl /np >nul\r\n");
                sb.Append("start \"\" \"" + Path.Combine(to, "Jarvis.exe") + "\" --actualizado\r\n");
                File.WriteAllText(script, sb.ToString(), new UTF8Encoding(false));

                Log.Write("Actualización: instalo la " + info.Version + " desde " + from + " en " + to);
                UI.BeginInvoke(new Action(() =>
                {
                    _hud.SetReply("Instalando la versión " + info.Version.ToString(3) + ". Vuelvo en unos segundos.");
                    System.Diagnostics.Process.Start(new ProcessStartInfo("cmd.exe", "/c \"" + script + "\"") { CreateNoWindow = true, UseShellExecute = false, WindowStyle = ProcessWindowStyle.Hidden });
                    Task.Delay(1200).ContinueWith(_ => UI.BeginInvoke(new Action(Shutdown)));
                }));
            }
            catch (Exception e)
            {
                _updating = false;
                Log.Write("Actualización fallida: " + e);
                Say("No pude actualizarme: " + e.GetBaseException().Message + ". Puede descargarla a mano en GitHub, en Releases.");
            }
        }

        // Tras reiniciarse con la versión nueva.
        void AfterUpdate()
        {
            if (!_args.Contains("--actualizado")) return;
            string v = Current.ToString(3);
            Log.Write("Actualizado a la " + v + ".");
            Task.Delay(2500).ContinueWith(_ => Say("Listo" + Sir() + ": ya estoy en la versión " + v + "."));
            try { Directory.Delete(Path.Combine(Path.GetTempPath(), "JARVIS-actualizacion"), true); } catch { }
        }
    }
}
