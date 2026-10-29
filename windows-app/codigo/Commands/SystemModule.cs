using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;
using Jarvis.Core;
using Jarvis.Speech;

namespace Jarvis.Commands
{
    // Volumen, música, ventanas, energía, capturas y estado del equipo.
    public sealed class SystemModule
    {
        readonly Engine E;
        public SystemModule(Engine e) { E = e; }
        string Sir => E.Sir;
        string Ack() => E.Talk.Ack();

        const ushort VK_LWIN = 0x5B, VK_CONTROL = 0x11, VK_MENU = 0x12, VK_SHIFT = 0x10, VK_TAB = 0x09, VK_SNAPSHOT = 0x2C;
        const ushort VK_MEDIA_PLAY_PAUSE = 0xB3, VK_MEDIA_NEXT = 0xB0, VK_MEDIA_PREV = 0xB1, VK_MEDIA_STOP = 0xB2;

        static readonly string[] Up = { "sube", "subir", "aumenta", "aumentar", "mas", "subele", "alto" };
        static readonly string[] Down = { "baja", "bajar", "disminuye", "reduce", "menos", "bajale", "bajo" };

        public string Try(Cmd c)
        {
            string s = c.Join(0);
            return Volume(c, s) ?? Media(c, s) ?? Windows(c, s) ?? Power(c, s) ?? Tools(c, s) ?? Status(c, s);
        }

        // ---------------------------------------------------------------- volumen

        string Volume(Cmd c, string s)
        {
            bool vol = c.HasAny("volumen", "sonido", "audio");
            if (Text.IsOneOf(s, "silencio total", "silencia", "silencia el sonido", "mutea", "mute", "quita el sonido", "silencia el equipo", "silencia el volumen", "pon en silencio", "silencia todo"))
                return AudioDevices.SetMute(true) ? Engine.Quiet : "No encuentro el dispositivo de sonido" + Sir + ".";
            if (Text.IsOneOf(s, "quita el silencio", "activa el sonido", "desmutea", "unmute", "pon sonido", "devuelve el sonido", "reactiva el sonido"))
                return AudioDevices.SetMute(false) ? Ack() : "No encuentro el dispositivo de sonido" + Sir + ".";
            if (c.Has("microfono") && c.HasAny("silencia", "mutea", "apaga", "desactiva", "cierra"))
                return AudioDevices.SetMute(true, true) ? "Micrófono silenciado. Ya no podré oírle hasta que lo active desde Windows o con el atajo" + Sir + "." : "No encuentro el micrófono.";
            if (c.Has("microfono") && c.HasAny("activa", "enciende", "desmutea", "abre"))
                return AudioDevices.SetMute(false, true) ? "Micrófono activado." : "No encuentro el micrófono.";
            if (!vol && !(c.W(0) == "sube" || c.W(0) == "baja") ) return null;
            if (!vol && c.Size > 3) return null; // «baja la persiana del salón» no es volumen
            if (!vol && c.Size > 1 && !c.HasAny("poco", "poquito", "mucho", "bastante", "un", "mas", "a", "al") && c.FindNumber(0) < 0) return null;
            if (vol && c.HasAny("cual", "como", "que", "cuanto", "esta") && !c.HasAny(Up) && !c.HasAny(Down) && c.FindNumber(0) < 0)
            {
                float v = AudioDevices.GetVolume();
                bool muted = AudioDevices.GetMute() == true;
                return v < 0 ? "No encuentro el dispositivo de sonido." : "El volumen está al " + (int)Math.Round(v * 100) + " por ciento" + (muted ? ", pero silenciado" : "") + ".";
            }
            float cur = AudioDevices.GetVolume();
            if (cur < 0) return "No encuentro el dispositivo de sonido" + Sir + ".";
            int ni = c.FindNumber(0);
            int step = E.S.VolumeStep;
            if (c.HasAny("maximo", "tope", "todo") && !c.HasAny(Down)) return SetVol(100);
            if (c.HasAny("minimo") ) return SetVol(5);
            if (ni >= 0)
            {
                int n = Text.ParseNumber(c.W(ni));
                if (c.HasAny(Up) && (c.W(ni + 1) == "puntos" || c.W(ni + 1) == "por" || c.Has("en"))) return SetVol((int)Math.Round(cur * 100) + n);
                if (c.HasAny(Down) && (c.W(ni + 1) == "puntos" || c.W(ni + 1) == "por" || c.Has("en"))) return SetVol((int)Math.Round(cur * 100) - n);
                return SetVol(n);
            }
            if (c.HasAny("mucho", "bastante")) step *= 2;
            if (c.HasAny("poco", "poquito", "poquitito")) step = Math.Max(2, step / 2);
            if (c.HasAny(Up)) return SetVol((int)Math.Round(cur * 100) + step);
            if (c.HasAny(Down)) return SetVol((int)Math.Round(cur * 100) - step);
            if (c.Has("medio") || c.Has("mitad")) return SetVol(50);
            return null;
        }

        string SetVol(int pct)
        {
            pct = Math.Clamp(pct, 0, 100);
            AudioDevices.SetVolume(pct / 100f);
            return "Volumen al " + pct + ".";
        }

        // ---------------------------------------------------------------- música (teclas multimedia: valen para Spotify, YouTube, etc.)

        string Media(Cmd c, string s)
        {
            bool music = c.HasAny("musica", "cancion", "tema", "video", "spotify", "reproduccion", "podcast");
            if (Text.IsOneOf(s, "pausa", "pausa la musica", "pon pausa", "para la musica", "deten la musica", "pausa el video", "pausa la cancion", "pausalo", "para el video", "pausa spotify"))
                return Key(VK_MEDIA_PLAY_PAUSE);
            if (Text.IsOneOf(s, "reproduce", "continua", "sigue", "reanuda", "play", "dale play", "reanuda la musica", "continua la musica", "pon la musica", "sigue la musica", "reproduce la musica", "quita la pausa", "reanudalo"))
                return Key(VK_MEDIA_PLAY_PAUSE);
            if (Text.IsOneOf(s, "siguiente", "siguiente cancion", "pasa la cancion", "salta la cancion", "otra cancion", "cambia la cancion", "proxima cancion", "siguiente tema", "salta", "pasa", "siguiente video"))
                return Key(VK_MEDIA_NEXT);
            if (Text.IsOneOf(s, "anterior", "cancion anterior", "la anterior", "vuelve a la anterior", "tema anterior", "regresa la cancion", "video anterior", "pon la anterior"))
            {
                Native.SendKeys(VK_MEDIA_PREV);
                Thread.Sleep(80);
                return Key(VK_MEDIA_PREV);
            }
            if (music && c.HasAny("deten", "para", "stop") && c.Size <= 3) return Key(VK_MEDIA_STOP);
            if (c.Contains("repite la cancion") || c.Contains("desde el principio")) return Key(VK_MEDIA_PREV);
            return null;
        }

        static string Key(ushort vk)
        {
            Native.SendKeys(vk);
            return "";
        }

        // ---------------------------------------------------------------- ventanas

        string Windows(Cmd c, string s)
        {
            IntPtr w = E.Host.TargetWindow;
            bool thisWin = c.HasAny("ventana", "esto", "eso", "esta", "programa", "aplicacion") || c.Size == 1;
            if (Text.IsOneOf(s, "muestra el escritorio", "ve al escritorio", "escritorio", "minimiza todo", "minimiza todas las ventanas", "esconde todo", "ensename el escritorio", "muestrame el escritorio"))
            {
                Native.SendKeys(VK_LWIN, (ushort)'D');
                return "";
            }
            if (Text.IsOneOf(s, "cambia de ventana", "siguiente ventana", "otra ventana", "cambia de programa", "alt tab"))
            {
                Native.SendKeys(VK_MENU, VK_TAB);
                return "";
            }
            if (Text.IsOneOf(s, "vista de tareas", "muestra las ventanas", "todas las ventanas", "ensename las ventanas", "muestrame las ventanas"))
            {
                Native.SendKeys(VK_LWIN, VK_TAB);
                return "";
            }
            if (Text.IsOneOf(s, "nuevo escritorio", "crea un escritorio", "abre un escritorio nuevo"))
            {
                Native.SendKeys(VK_LWIN, VK_CONTROL, (ushort)'D');
                return "";
            }
            if (!thisWin || w == IntPtr.Zero || c.HasAny("pestana", "pestanas", "sesion")) return null;
            if (c.W(0) == "minimiza" || c.W(0) == "minimizar" || c.Contains("esconde esta ventana"))
            {
                Native.ShowWindow(w, Native.SW_MINIMIZE);
                return "";
            }
            if (c.W(0) == "maximiza" || c.W(0) == "maximizar" || c.Contains("pantalla completa") && c.Has("ventana"))
            {
                Native.ShowWindow(w, Native.SW_MAXIMIZE);
                return "";
            }
            if (c.W(0) == "restaura")
            {
                Native.ShowWindow(w, Native.SW_RESTORE);
                return "";
            }
            if ((c.W(0) == "cierra" || c.W(0) == "cerrar" || c.W(0) == "cierralo" || c.W(0) == "cierrala") && (c.Size <= 3))
            {
                string title = Native.WindowTitle(w);
                Native.PostMessage(w, Native.WM_CLOSE, IntPtr.Zero, IntPtr.Zero);
                return title == "" ? "" : "Cierro " + Text.Preview(title, 40) + ".";
            }
            if (c.Contains("pon a la izquierda") || c.Contains("mueve a la izquierda") || c.Contains("ventana a la izquierda"))
            {
                Native.SetForegroundWindow(w);
                Thread.Sleep(60);
                Native.SendKeys(VK_LWIN, 0x25);
                return "";
            }
            if (c.Contains("pon a la derecha") || c.Contains("mueve a la derecha") || c.Contains("ventana a la derecha"))
            {
                Native.SetForegroundWindow(w);
                Thread.Sleep(60);
                Native.SendKeys(VK_LWIN, 0x27);
                return "";
            }
            return null;
        }

        // ---------------------------------------------------------------- energía

        string Power(Cmd c, string s)
        {
            bool pc = c.HasAny("equipo", "ordenador", "computador", "computadora", "pc", "sistema", "maquina", "portatil") || c.Size == 1;
            if (Text.IsOneOf(s, "bloquea", "bloquea el equipo", "bloquea la pantalla", "bloquea el pc", "bloquea el ordenador", "bloquea la computadora", "bloquealo", "bloquea la sesion"))
            {
                Native.LockWorkStation();
                return "";
            }
            if (Text.IsOneOf(s, "apaga la pantalla", "apaga el monitor", "apaga las pantallas", "apaga los monitores"))
            {
                // Hay que esperar a que se suelte la voz/teclado o la pantalla se vuelve a encender.
                new Thread(() =>
                {
                    Thread.Sleep(1200);
                    Native.SendMessage((IntPtr)0xFFFF, Native.WM_SYSCOMMAND, (IntPtr)Native.SC_MONITORPOWER, (IntPtr)2);
                }) { IsBackground = true }.Start();
                return "Apago la pantalla" + Sir + ".";
            }
            if (!pc) return null;
            if (c.W(0) == "suspende" || c.W(0) == "suspender" || (c.W(0) == "pon" && c.HasAny("suspension", "reposo")) || Text.IsOneOf(s, "a dormir el equipo", "duerme el equipo", "suspende el equipo"))
                return Confirm("¿Suspendo el equipo" + Sir + "?", () => Native.SetSuspendState(false, false, false), "Suspendiendo.");
            if (c.W(0) == "hiberna" || c.W(0) == "hibernar")
                return Confirm("¿Hiberno el equipo" + Sir + "?", () => Native.SetSuspendState(true, false, false), "Hibernando.");
            if ((c.W(0) == "apaga" || c.W(0) == "apagar") && (c.Size <= 4 || c.Has("en")) && !c.HasAny("pantalla", "monitor", "luz", "luces", "musica", "wifi"))
            {
                if (c.Has("en") && TimeModule.ParseDuration(c, 0, out int secs, out _, out _))
                {
                    Run("shutdown", "/s /t " + secs);
                    return "El equipo se apagará dentro de " + TimeModule.SayDuration(TimeSpan.FromSeconds(secs)) + ". Diga «cancela el apagado» si cambia de idea.";
                }
                return Confirm("¿Seguro que apago el equipo" + Sir + "?", () => Run("shutdown", "/s /t 5"), "Apagando el equipo. Hasta pronto" + Sir + ".");
            }
            if (c.W(0) == "reinicia" || c.W(0) == "reiniciar" || c.W(0) == "reinicialo")
                return Confirm("¿Seguro que reinicio el equipo" + Sir + "?", () => Run("shutdown", "/r /t 5"), "Reiniciando. Vuelvo enseguida.");
            if (c.Contains("cierra la sesion") || c.Contains("cerrar sesion") || c.Contains("cierra sesion"))
                return Confirm("¿Cierro la sesión de Windows" + Sir + "?", () => Run("shutdown", "/l"), "Cerrando la sesión.");
            if (c.Contains("cancela el apagado") || c.Contains("no apagues") || c.Contains("cancela el reinicio"))
            {
                Run("shutdown", "/a");
                return "Apagado cancelado" + Sir + ".";
            }
            return null;
        }

        string Confirm(string question, Action act, string done)
        {
            if (!E.S.ConfirmPower)
            {
                Delayed(act);
                return done;
            }
            E.Ask(question, yes =>
            {
                if (!yes) return "Cancelado.";
                Delayed(act);
                return done;
            });
            return question;
        }

        // Da tiempo a que termine de decirlo.
        static void Delayed(Action a) => new Thread(() => { Thread.Sleep(2500); try { a(); } catch { } }) { IsBackground = true }.Start();

        static void Run(string exe, string args)
        {
            try { Process.Start(new ProcessStartInfo(exe, args) { CreateNoWindow = true, UseShellExecute = false }); }
            catch (Exception e) { Log.Write(exe + ": " + e.Message); }
        }

        // ---------------------------------------------------------------- herramientas

        string Tools(Cmd c, string s)
        {
            if (c.HasAny("captura", "pantallazo", "screenshot") || c.Contains("foto de la pantalla"))
            {
                if (c.HasAny("recorte", "recorta", "zona", "parte", "region", "trozo"))
                {
                    Native.SendKeys(VK_LWIN, VK_SHIFT, (ushort)'S');
                    return "Elija la zona" + Sir + ".";
                }
                return Screenshot();
            }
            if (c.Contains("vacia la papelera") || c.Contains("vaciar la papelera") || c.Contains("limpia la papelera"))
            {
                int hr = Native.SHEmptyRecycleBin(IntPtr.Zero, null, 0x7);
                return hr == 0 ? "Papelera vacía" + Sir + "." : "La papelera ya estaba vacía.";
            }
            // Dictado: «escribe hola qué tal»
            if ((c.W(0) == "escribe" || c.W(0) == "teclea" || c.W(0) == "dicta") && c.Size > 1)
            {
                string t = c.OrigFrom(1);
                IntPtr w = E.Host.TargetWindow;
                E.Host.HidePanel();
                new Thread(() =>
                {
                    Thread.Sleep(250);
                    if (w != IntPtr.Zero) Native.SetForegroundWindow(w);
                    Thread.Sleep(150);
                    Native.TypeText(t);
                }) { IsBackground = true }.Start();
                return "";
            }
            if (Text.IsOneOf(s, "copia", "copialo", "copia esto"))
                return SendTo(VK_CONTROL, (ushort)'C');
            if (Text.IsOneOf(s, "pega", "pegalo", "pega esto", "pega aqui"))
                return SendTo(VK_CONTROL, (ushort)'V');
            if (Text.IsOneOf(s, "deshaz", "deshacer", "deshazlo", "control z"))
                return SendTo(VK_CONTROL, (ushort)'Z');
            if (Text.IsOneOf(s, "guarda", "guardalo", "guarda el archivo", "guarda esto"))
                return SendTo(VK_CONTROL, (ushort)'S');
            if (Text.IsOneOf(s, "selecciona todo", "seleccionalo todo"))
                return SendTo(VK_CONTROL, (ushort)'A');
            if (Text.IsOneOf(s, "nueva pestana", "abre una pestana", "abre una nueva pestana"))
                return SendTo(VK_CONTROL, (ushort)'T');
            if (Text.IsOneOf(s, "cierra la pestana", "cierra esta pestana", "cierra pestana"))
                return SendTo(VK_CONTROL, (ushort)'W');
            if (Text.IsOneOf(s, "recarga", "recarga la pagina", "actualiza la pagina", "refresca"))
                return SendTo(0x74);
            if (Text.IsOneOf(s, "graba la pantalla", "empieza a grabar", "graba esto", "deja de grabar", "para la grabacion", "detén la grabacion"))
            {
                Native.SendKeys(VK_LWIN, VK_MENU, (ushort)'R');
                return "";
            }
            if (c.Contains("lee el portapapeles") || c.Contains("que hay en el portapapeles") || c.Contains("que he copiado") || c.Contains("lee lo que he copiado"))
            {
                string t = E.Host.ClipboardText();
                return t == "" ? "El portapapeles está vacío" + Sir + "." : Text.Preview(t, 600);
            }
            return null;
        }

        string SendTo(params ushort[] keys)
        {
            IntPtr w = E.Host.TargetWindow;
            new Thread(() =>
            {
                if (w != IntPtr.Zero) Native.SetForegroundWindow(w);
                Thread.Sleep(120);
                Native.SendKeys(keys);
            }) { IsBackground = true }.Start();
            return "";
        }

        string Screenshot()
        {
            try
            {
                string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyPictures), "Capturas de JARVIS");
                Directory.CreateDirectory(dir);
                string file = Path.Combine(dir, "Captura " + DateTime.Now.ToString("yyyy-MM-dd HH.mm.ss") + ".png");
                var b = System.Windows.Forms.SystemInformation.VirtualScreen;
                using (var bmp = new System.Drawing.Bitmap(b.Width, b.Height))
                {
                    using (var g = System.Drawing.Graphics.FromImage(bmp))
                        g.CopyFromScreen(b.Left, b.Top, 0, 0, bmp.Size);
                    bmp.Save(file, System.Drawing.Imaging.ImageFormat.Png);
                }
                E.LastFile = file;
                return "Captura guardada en Imágenes" + Sir + ".";
            }
            catch (Exception e)
            {
                Log.Write("Captura: " + e.Message);
                Native.SendKeys(VK_LWIN, VK_SNAPSHOT);
                return "Captura hecha con Windows" + Sir + ".";
            }
        }

        // ---------------------------------------------------------------- estado del equipo

        string Status(Cmd c, string s)
        {
            if (c.Has("bateria") || c.Contains("cuanta carga") || c.Contains("estoy enchufado"))
            {
                if (!Native.GetSystemPowerStatus(out var p) || p.BatteryFlag == 128 || p.BatteryLifePercent == 255)
                    return "Este equipo no tiene batería" + Sir + ", está conectado a la corriente.";
                string r = "Batería al " + p.BatteryLifePercent + " por ciento";
                if (p.ACLineStatus == 1) r += (p.BatteryLifePercent >= 100 ? ", cargada y enchufada" : ", cargando");
                else if (p.BatteryLifeTime > 0) r += ", quedan unas " + TimeModule.SayDuration(TimeSpan.FromSeconds(p.BatteryLifeTime));
                return r + ".";
            }
            if (c.HasAny("ram") || c.Contains("memoria del equipo") || c.Contains("cuanta memoria"))
            {
                var m = new Native.MEMORYSTATUSEX { dwLength = (uint)System.Runtime.InteropServices.Marshal.SizeOf<Native.MEMORYSTATUSEX>() };
                Native.GlobalMemoryStatusEx(ref m);
                double total = m.ullTotalPhys / 1073741824.0, free = m.ullAvailPhys / 1073741824.0;
                return "Memoria en uso al " + m.dwMemoryLoad + " por ciento: libres " + Text.Num(free, 1) + " de " + Text.Num(total, 0) + " gigas.";
            }
            if (c.HasAny("procesador", "cpu") && c.HasAny("uso", "como", "cuanto", "carga", "esta", "estado"))
                return "El procesador está al " + CpuLoad() + " por ciento.";
            if (c.HasAny("disco", "espacio", "almacenamiento") && c.HasAny("cuanto", "libre", "queda", "espacio", "como"))
            {
                var parts = DriveInfo.GetDrives().Where(d => d.IsReady && d.DriveType == DriveType.Fixed)
                    .Select(d => "en " + d.Name.TrimEnd('\\', ':') + " quedan " + Text.Num(d.AvailableFreeSpace / 1073741824.0, 0) + " gigas de " + Text.Num(d.TotalSize / 1073741824.0, 0))
                    .ToList();
                return parts.Count == 0 ? "No encuentro discos." : Text.Capitalize(string.Join("; ", parts)) + ".";
            }
            if (c.Contains("cuanto tiempo lleva encendido") || c.Contains("tiempo encendido") || c.Contains("cuando encendi"))
                return "El equipo lleva encendido " + TimeModule.SayDuration(TimeSpan.FromMilliseconds(Environment.TickCount64)) + ".";
            if (c.Contains("estado del sistema") || c.Contains("como esta el equipo") || c.Contains("diagnostico") || c.Contains("informe del sistema"))
            {
                var m = new Native.MEMORYSTATUSEX { dwLength = (uint)System.Runtime.InteropServices.Marshal.SizeOf<Native.MEMORYSTATUSEX>() };
                Native.GlobalMemoryStatusEx(ref m);
                string bat = Native.GetSystemPowerStatus(out var p) && p.BatteryLifePercent != 255 && p.BatteryFlag != 128 ? ", batería al " + p.BatteryLifePercent : "";
                return "Procesador al " + CpuLoad() + ", memoria al " + m.dwMemoryLoad + bat + ". Todo en orden" + Sir + ".";
            }
            if (c.Contains("mi ip") || c.Contains("direccion ip"))
            {
                var ips = System.Net.NetworkInformation.NetworkInterface.GetAllNetworkInterfaces()
                    .Where(n => n.OperationalStatus == System.Net.NetworkInformation.OperationalStatus.Up && n.NetworkInterfaceType != System.Net.NetworkInformation.NetworkInterfaceType.Loopback)
                    .SelectMany(n => n.GetIPProperties().UnicastAddresses)
                    .Where(a => a.Address.AddressFamily == System.Net.Sockets.AddressFamily.InterNetwork)
                    .Select(a => a.Address.ToString()).ToList();
                return ips.Count == 0 ? "No estoy conectado a ninguna red." : "Su IP local es " + ips[0] + ".";
            }
            if (c.Contains("version de jarvis") || c.Contains("que version eres") || c.Contains("tu version"))
                return E.S.Name + " versión " + typeof(SystemModule).Assembly.GetName().Version.ToString(3) + ".";
            return null;
        }

        public static int CpuLoad()
        {
            Native.GetSystemTimes(out long i1, out long k1, out long u1);
            Thread.Sleep(250);
            Native.GetSystemTimes(out long i2, out long k2, out long u2);
            long idle = i2 - i1, total = (k2 - k1) + (u2 - u1);
            return total <= 0 ? 0 : (int)Math.Round(100.0 * (total - idle) / total);
        }
    }
}
