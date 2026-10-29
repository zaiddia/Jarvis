using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using System.Xml.Linq;
using Jarvis.Core;
using Jarvis.Speech;

namespace Jarvis.Commands
{
    // Órdenes nuevas: volumen por aplicación, brillo, modo oscuro, ventana siempre encima, contraseñas,
    // fechas, divisas, noticias, IP pública, conexión, programas que más consumen, limpieza y más.
    public sealed class ExtraModule
    {
        readonly Engine E;
        static readonly HttpClient Http = Net.Create(TimeSpan.FromSeconds(12));
        static readonly CultureInfo Es = CultureInfo.GetCultureInfo("es-ES");
        public ExtraModule(Engine e) { E = e; }
        string Sir => E.Sir;

        public string Try(Cmd c)
        {
            return AppVolume(c) ?? DarkMode(c) ?? OnTop(c) ?? Password(c) ?? Dates(c) ?? Typing(c) ?? Clipboard(c) ?? Files(c) ?? Maintenance(c);
        }

        public async Task<string> TryAsync(Cmd c)
        {
            return await Brightness(c) ?? await Currency(c) ?? await News(c) ?? await Network(c) ?? await TopProcesses(c);
        }

        // ---------------------------------------------------------------- «pon música de Shakira», «quiero escuchar salsa»

        string Music(Cmd c)
        {
            string q = null;
            if ((c.W(0) == "pon" || c.W(0) == "reproduce") && c.HasAny("musica", "canciones", "cancion", "temas", "algo") && (c.Has("de") || c.Has("para")))
            {
                int k = c.Find("de");
                if (k < 0) k = c.Find("para");
                q = c.OrigFrom(k + 1);
                if (c.W(k - 1) == "algo") q = c.OrigFrom(k + 1);
                if (c.Has("para")) q = "música para " + c.OrigFrom(c.Find("para") + 1);
            }
            else if (c.W(0) == "escuchar" && c.Size > 1) q = c.OrigFrom(1);
            else if (c.W(0) == "pon" && c.Size >= 2 && c.Size <= 4 && Text.IsOneOf(c.W(1), "salsa", "vallenato", "reggaeton", "rock", "jazz", "pop", "bachata", "merengue", "cumbia", "baladas", "clasica", "lofi", "electronica", "boleros", "rancheras", "tango", "champeta"))
                q = c.OrigFrom(1);
            if (string.IsNullOrWhiteSpace(q) || c.HasAny("youtube", "spotify")) return null;   // con «en YouTube/Spotify» lo hace la búsqueda normal
            q = q.Trim(' ', '.', '?');
            if (Text.IsOneOf(Text.Squash(q), "musica", "la musica", "", "fondo", "musica de fondo")) return null;   // «pon algo de música»: que suene lo que había
            if (E.Apps.HasApp("spotify"))
                return E.Apps.OpenUrl("spotify:search:" + Uri.EscapeDataString(q), TalkModule.Pick("Le busco " + q + " en Spotify.", "Abriendo " + q + " en Spotify."));
            return E.Apps.OpenUrl("https://www.youtube.com/results?search_query=" + Uri.EscapeDataString(q + " música"), "Le busco " + q + " en YouTube.");
        }

        // ---------------------------------------------------------------- volumen de una aplicación

        static readonly Dictionary<string, string[]> AppProcs = new Dictionary<string, string[]>
        {
            ["spotify"] = new[] { "spotify" }, ["chrome"] = new[] { "chrome" }, ["google chrome"] = new[] { "chrome" }, ["edge"] = new[] { "msedge" },
            ["firefox"] = new[] { "firefox" }, ["navegador"] = new[] { "chrome", "msedge", "firefox", "opera", "brave" }, ["youtube"] = new[] { "chrome", "msedge", "firefox", "opera", "brave" },
            ["discord"] = new[] { "discord" }, ["teams"] = new[] { "ms-teams", "teams" }, ["zoom"] = new[] { "zoom" }, ["vlc"] = new[] { "vlc" },
            ["whatsapp"] = new[] { "whatsapp" }, ["netflix"] = new[] { "netflix", "chrome", "msedge" }, ["juego"] = new string[0], ["steam"] = new[] { "steam", "steamwebhelper" },
            ["musica"] = new[] { "spotify", "music", "groove", "vlc", "itunes" }, ["reproductor"] = new[] { "microsoft.media.player", "wmplayer", "vlc" },
        };

        string AppVolume(Cmd c)
        {
            int de = -1;
            for (int i = 0; i + 1 < c.Size; i++)
                if ((c.W(i) == "de" || c.W(i) == "en" || c.W(i) == "a") && (c.W(i - 1) == "volumen" || c.W(i - 1) == "sonido" || c.HasAny("silencia", "mutea", "desmutea")))
                {
                    de = i;
                    break;
                }
            if (de < 0)
            {
                // «silencia Spotify», «mutea Chrome»
                if (Text.IsOneOf(c.W(0), "silencia", "mutea", "desmutea") && c.Size == 2 && AppProcs.ContainsKey(c.W(1))) de = 0;
                else return null;
            }
            string app = c.Join(de + 1);
            foreach (var art in new[] { "el ", "la ", "los " }) if (app.StartsWith(art)) app = app.Substring(art.Length);
            int num = c.FindNumber(de + 1);
            string appName = num > 0 ? c.Join(de + 1, num).Replace(" al", "").Replace(" a", "").Trim() : app;
            foreach (var art in new[] { "el ", "la ", "los " }) if (appName.StartsWith(art)) appName = appName.Substring(art.Length);
            string[] procs = AppProcs.TryGetValue(appName, out var p) ? p : new[] { appName.Replace(" ", "") };
            if (procs.Length == 0 || appName == "" || appName == "equipo" || appName == "sistema" || appName == "todo") return null;
            string label = Text.Capitalize(appName);

            bool up = c.HasAny("sube", "subir", "aumenta", "subele", "mas");
            bool down = c.HasAny("baja", "bajar", "reduce", "bajale", "menos");
            float r;
            if (c.HasAny("silencia", "mutea", "calla"))
                r = Ducker.SetAppVolume(procs, v => v, true);
            else if (c.HasAny("desmutea") || c.Contains("quita el silencio"))
                r = Ducker.SetAppVolume(procs, v => v, false);
            else if (num > 0 && !up && !down)
            {
                float target = Math.Clamp(Text.ParseNumber(c.W(num)), 0, 100) / 100f;
                r = Ducker.SetAppVolume(procs, v => target, false);
            }
            else if (up || down)
            {
                float step = (num > 0 ? Text.ParseNumber(c.W(num)) : E.S.VolumeStep * 1.5f) / 100f;
                r = Ducker.SetAppVolume(procs, v => v + (up ? step : -step), up ? false : (bool?)null);
            }
            else return null;
            if (r < 0)
            {
                var playing = Ducker.AppsWithSound();
                return label + " no está sonando ahora" + Sir + "." + (playing.Count > 0 ? " Tienen sonido: " + string.Join(", ", playing.Take(5)) + "." : "");
            }
            if (c.HasAny("silencia", "mutea", "calla")) return label + " silenciado.";
            return "Volumen de " + label + " al " + (int)Math.Round(r * 100) + ".";
        }

        // ---------------------------------------------------------------- modo oscuro

        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint msg, IntPtr wParam, string lParam, uint flags, uint timeout, out IntPtr result);

        string DarkMode(Cmd c)
        {
            bool dark = c.Contains("modo oscuro") || c.Contains("tema oscuro") || c.Contains("modo noche");
            bool light = c.Contains("modo claro") || c.Contains("tema claro") || c.Contains("modo dia");
            if (!dark && !light) return null;
            if (c.HasAny("desactiva", "quita", "apaga")) { dark = !dark; light = !light; }
            if (dark && light) return null;
            try
            {
                using var k = Microsoft.Win32.Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize");
                int v = dark ? 0 : 1;
                k.SetValue("AppsUseLightTheme", v, Microsoft.Win32.RegistryValueKind.DWord);
                k.SetValue("SystemUsesLightTheme", v, Microsoft.Win32.RegistryValueKind.DWord);
                SendMessageTimeout((IntPtr)0xFFFF, 0x001A, IntPtr.Zero, "ImmersiveColorSet", 0x2, 3000, out _);
                return dark ? "Modo oscuro activado" + Sir + "." : "Modo claro activado" + Sir + ".";
            }
            catch (Exception e)
            {
                Log.Write("Modo oscuro: " + e.Message);
                return "No pude cambiar el tema.";
            }
        }

        // ---------------------------------------------------------------- ventana siempre encima

        [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern IntPtr FindWindow(string cls, string title);
        [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
        [DllImport("user32.dll")] static extern int GetWindowLong(IntPtr h, int index);

        string OnTop(Cmd c)
        {
            bool on = c.Contains("siempre encima") || c.Contains("siempre visible") || c.Contains("siempre delante") || c.Contains("fija esta ventana") || c.Contains("fija la ventana");
            if (!on) return null;
            IntPtr w = E.Host.TargetWindow;
            if (w == IntPtr.Zero) return "No sé qué ventana" + Sir + ".";
            bool already = (GetWindowLong(w, -20) & 0x8) != 0;
            bool turnOff = c.HasAny("quita", "desactiva", "deja", "suelta") || c.Contains("ya no");
            if (turnOff && !already) return "Esa ventana no estaba fijada" + Sir + ".";
            bool top = !turnOff;
            SetWindowPos(w, top ? new IntPtr(-1) : new IntPtr(-2), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010);
            string title = Text.Preview(Native.WindowTitle(w), 40);
            return top ? (title != "" ? "«" + title + "» queda siempre encima." : "Ventana fijada encima.") : "La ventana ya no está fijada.";
        }

        // ---------------------------------------------------------------- contraseña

        string Password(Cmd c)
        {
            if (!(c.HasAny("contrasena", "clave", "password") && c.HasAny("genera", "crea", "dame", "inventa", "hazme", "haz", "nueva", "segura"))) return null;
            if (c.HasAny("api", "wifi")) return null;
            int n = c.FindNumber(0);
            int len = n >= 0 ? Math.Clamp(Text.ParseNumber(c.W(n)), 8, 64) : 18;
            const string lower = "abcdefghijkmnpqrstuvwxyz", upper = "ABCDEFGHJKLMNPQRSTUVWXYZ", digits = "23456789", sym = "!#$%&*+-=?@_";
            string all = lower + upper + digits + (c.Contains("sin simbolos") ? "" : sym);
            var chars = new List<char>
            {
                lower[RandomNumberGenerator.GetInt32(lower.Length)], upper[RandomNumberGenerator.GetInt32(upper.Length)],
                digits[RandomNumberGenerator.GetInt32(digits.Length)],
            };
            if (!c.Contains("sin simbolos")) chars.Add(sym[RandomNumberGenerator.GetInt32(sym.Length)]);
            while (chars.Count < len) chars.Add(all[RandomNumberGenerator.GetInt32(all.Length)]);
            for (int i = chars.Count - 1; i > 0; i--)
            {
                int j = RandomNumberGenerator.GetInt32(i + 1);
                (chars[i], chars[j]) = (chars[j], chars[i]);
            }
            string pass = new string(chars.ToArray());
            E.Host.SetClipboard(pass);
            E.Host.Show(pass);
            return "Contraseña de " + len + " caracteres copiada al portapapeles" + Sir + ". No la digo en voz alta.";
        }

        // ---------------------------------------------------------------- fechas

        static readonly string[] Months = { "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre" };

        // «el 15 de marzo [de 2027]»
        static bool ParseDate(Cmd c, out DateTime d)
        {
            d = DateTime.MinValue;
            for (int i = 0; i + 2 < c.Size; i++)
            {
                int day = Text.ParseNumber(c.W(i), true);
                if (day < 1 || day > 31 || c.W(i + 1) != "de") continue;
                int m = Array.IndexOf(Months, c.W(i + 2) == "setiembre" ? "septiembre" : c.W(i + 2));
                if (m < 0) continue;
                int year = DateTime.Today.Year;
                bool yearGiven = false;
                if (c.W(i + 3) == "de" && int.TryParse(c.W(i + 4), out int y) && y > 1900 && y < 3000) { year = y; yearGiven = true; }
                if (day > DateTime.DaysInMonth(year, m + 1)) return false;
                d = new DateTime(year, m + 1, day);
                if (!yearGiven && d < DateTime.Today && (c.HasAny("falta", "faltan", "sera", "cae", "queda", "quedan"))) d = d.AddYears(1);
                return true;
            }
            return false;
        }

        string Dates(Cmd c)
        {
            // «qué día será dentro de 45 días», «qué fecha fue hace 3 semanas»
            int k = c.Find("dentro");
            int h = c.Find("hace");
            if ((k >= 0 || h >= 0) && c.HasAny("dia", "fecha") && c.HasAny("que", "cual") && !c.HasAny("tiempo", "calor", "frio"))
            {
                int from = Math.Max(k, h) + 1;
                int n = c.FindNumber(from, true);
                if (n >= 0)
                {
                    int v = Text.ParseNumber(c.W(n), true);
                    string unit = c.W(n + 1);
                    int sign = h >= 0 && (k < 0 || h > k) ? -1 : 1;
                    DateTime t = unit.StartsWith("semana") ? DateTime.Today.AddDays(7 * v * sign)
                               : unit.StartsWith("mes") ? DateTime.Today.AddMonths(v * sign)
                               : unit.StartsWith("ano") ? DateTime.Today.AddYears(v * sign)
                               : DateTime.Today.AddDays(v * sign);
                    return (sign > 0 ? "Será " : "Fue ") + t.ToString("dddd d 'de' MMMM 'de' yyyy", Es) + ".";
                }
            }
            if (!ParseDate(c, out var d)) return null;
            if (c.HasAny("falta", "faltan", "quedan", "queda") || c.Contains("cuantos dias"))
            {
                int days = (int)(d - DateTime.Today).TotalDays;
                if (days == 0) return "Es hoy" + Sir + ".";
                if (days < 0) return "Eso fue hace " + Text.Plural(-days, "día", "días") + ".";
                return "Faltan " + Text.Plural(days, "día", "días") + (days > 60 ? ", unas " + (days / 7) + " semanas" : "") + ".";
            }
            if (c.HasAny("dia", "cae", "que") && (c.Contains("que dia") || c.Has("cae") || c.Contains("dia de la semana")))
            {
                string wd = d.ToString("dddd", Es);
                bool past = d < DateTime.Today;
                return Text.Capitalize(d.ToString("d 'de' MMMM 'de' yyyy", Es)) + (past ? " fue " : d == DateTime.Today ? " es " : " será ") + wd + ".";
            }
            return null;
        }

        // ---------------------------------------------------------------- escribir cosas útiles

        string Typing(Cmd c)
        {
            if (c.W(0) != "escribe" && c.W(0) != "teclea") return null;
            string s = c.Join(1);
            string text = s switch
            {
                "la fecha" or "la fecha de hoy" or "fecha" => DateTime.Now.ToString("d 'de' MMMM 'de' yyyy", Es),
                "la fecha corta" => DateTime.Now.ToString("dd/MM/yyyy"),
                "la hora" or "hora" => DateTime.Now.ToString("HH:mm"),
                "la fecha y la hora" or "fecha y hora" => DateTime.Now.ToString("dd/MM/yyyy HH:mm"),
                "mi correo" or "mi email" => Store.Get("mi-correo", ""),
                _ => null,
            };
            if (text == null) return null;
            if (text == "") return "No sé su correo. Diga «mi correo es…» y lo recordaré.";
            IntPtr w = E.Host.TargetWindow;
            E.Host.HidePanel();
            new Thread(() =>
            {
                Thread.Sleep(250);
                if (w != IntPtr.Zero) Native.SetForegroundWindow(w);
                Thread.Sleep(150);
                Native.TypeText(text);
            }) { IsBackground = true }.Start();
            return "";
        }

        // ---------------------------------------------------------------- portapapeles

        string Clipboard(Cmd c)
        {
            // «mi correo es ana@…» (para «escribe mi correo»)
            if (c.Contains("mi correo es") || c.Contains("mi email es"))
            {
                var m = System.Text.RegularExpressions.Regex.Match(c.Orig, @"[\w.+-]+@[\w-]+(\.[\w-]+)+");
                if (!m.Success) return "No entendí la dirección. Escríbamela en el panel" + Sir + ".";
                Store.Set("mi-correo", m.Value);
                return "Recordaré su correo: " + m.Value + ".";
            }
            if ((c.W(0) == "copia" || c.W(0) == "guarda") && (c.Contains("en el portapapeles") || c.Contains("al portapapeles")))
            {
                int k = c.Find("portapapeles");
                string text = k + 1 < c.Size ? c.OrigFrom(k + 1).Trim(' ', ':', ',') : c.OrigFrom(1, Math.Max(1, k - 2));
                if (text == "") return null;
                E.Host.SetClipboard(text);
                return "Copiado" + Sir + ".";
            }
            if (Text.IsOneOf(c.Join(0), "vacia el portapapeles", "borra el portapapeles", "limpia el portapapeles"))
            {
                E.Host.SetClipboard("");
                return "Portapapeles vacío.";
            }
            if (c.Contains("cuantas palabras") && c.Has("portapapeles") || Text.IsOneOf(c.Join(0), "cuenta las palabras", "cuantas palabras he copiado"))
            {
                string t = E.Host.ClipboardText();
                if (t == "") return "El portapapeles está vacío.";
                return "Son " + Text.Plural(Text.CountWords(t), "palabra", "palabras") + " y " + Text.Plural(t.Length, "carácter", "caracteres") + ".";
            }
            if (c.Contains("pasa a mayusculas") || c.Contains("ponlo en mayusculas") || c.Contains("convierte a mayusculas"))
                return Transform(t => t.ToUpper(Es), "en mayúsculas");
            if (c.Contains("pasa a minusculas") || c.Contains("ponlo en minusculas") || c.Contains("convierte a minusculas"))
                return Transform(t => t.ToLower(Es), "en minúsculas");
            return null;
        }

        string Transform(Func<string, string> f, string what)
        {
            string t = E.Host.ClipboardText();
            if (t == "") return "Primero copie el texto" + Sir + ".";
            E.Host.SetClipboard(f(t));
            return "Texto del portapapeles " + what + ". Ya puede pegarlo.";
        }

        // ---------------------------------------------------------------- archivos de JARVIS

        string Files(Cmd c)
        {
            if (!(c.Has("captura") && c.HasAny("abre", "ensename", "muestra", "muestrame", "ultima", "ver"))) return null;
            if (c.HasAny("haz", "toma", "hacer")) return null;
            string file = E.LastFile;
            if (file == "" || !File.Exists(file))
            {
                string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyPictures), "Capturas de JARVIS");
                file = Directory.Exists(dir) ? new DirectoryInfo(dir).GetFiles("*.png").OrderByDescending(f => f.LastWriteTimeUtc).FirstOrDefault()?.FullName ?? "" : "";
            }
            if (file == "") return "Aún no hay capturas" + Sir + ". Diga «haz una captura».";
            try { Process.Start(new ProcessStartInfo(file) { UseShellExecute = true }); }
            catch { return "No pude abrirla."; }
            return "Aquí está.";
        }

        // ---------------------------------------------------------------- mantenimiento

        string Maintenance(Cmd c)
        {
            string s = c.Join(0);
            if (c.HasAny("temporales", "temporal") && c.HasAny("limpia", "borra", "elimina", "vacia", "limpiar"))
            {
                E.Ask("¿Borro los archivos temporales de más de un día" + Sir + "?", yes =>
                {
                    if (!yes) return "De acuerdo, no toco nada.";
                    long freed = 0;
                    int count = 0;
                    var limit = DateTime.Now.AddDays(-1);
                    try
                    {
                        foreach (var f in new DirectoryInfo(Path.GetTempPath()).EnumerateFiles("*", new EnumerationOptions { RecurseSubdirectories = true, IgnoreInaccessible = true }))
                        {
                            try
                            {
                                if (f.LastWriteTime > limit) continue;
                                long len = f.Length;
                                f.Delete();
                                freed += len;
                                count++;
                            }
                            catch { }
                        }
                    }
                    catch { }
                    return count == 0 ? "No había temporales que borrar." : "Borrados " + count + " archivos temporales: " + Text.Num(freed / 1048576.0, 0) + " megas liberados.";
                });
                return "¿Borro los archivos temporales de más de un día" + Sir + "?";
            }
            if (Text.IsOneOf(s, "reinicia el explorador", "reinicia el explorador de windows", "reinicia la barra de tareas", "arregla la barra de tareas"))
            {
                E.Ask("¿Reinicio el Explorador de Windows? Se cerrarán las carpetas abiertas.", yes =>
                {
                    if (!yes) return "Cancelado.";
                    new Thread(() =>
                    {
                        Thread.Sleep(1500);
                        // Primero se le pide que salga por las buenas (lo mismo que «Salir del Explorador» del menú
                        // de la barra de tareas): guarda su estado. Solo si no sale en 6 segundos, se le cierra a la fuerza.
                        IntPtr tray = FindWindow("Shell_TrayWnd", null);
                        if (tray != IntPtr.Zero) Native.PostMessage(tray, 0x5B4, IntPtr.Zero, IntPtr.Zero);
                        for (int i = 0; i < 30 && Process.GetProcessesByName("explorer").Length > 0; i++) Thread.Sleep(200);
                        foreach (var p in Process.GetProcessesByName("explorer"))
                        {
                            try { if (!p.WaitForExit(0)) p.Kill(); } catch { }
                            p.Dispose();
                        }
                        Thread.Sleep(800);
                        if (Process.GetProcessesByName("explorer").Length == 0) Process.Start(new ProcessStartInfo("explorer.exe") { UseShellExecute = true });
                    }) { IsBackground = true }.Start();
                    return "Reiniciando el Explorador.";
                });
                return "¿Reinicio el Explorador de Windows? Se cerrarán las carpetas abiertas.";
            }
            return null;
        }

        // ---------------------------------------------------------------- brillo (portátiles y pantallas compatibles)

        // WMI directo (System.Management): sin abrir PowerShell, más rápido y sin pasar texto a otro proceso.
        static int GetBrightness()
        {
            try
            {
                using var q = new System.Management.ManagementObjectSearcher("root\\WMI", "SELECT CurrentBrightness FROM WmiMonitorBrightness");
                foreach (System.Management.ManagementObject m in q.Get())
                    using (m) return Convert.ToInt32(m["CurrentBrightness"]);
            }
            catch (Exception e) { Log.Write("Brillo (leer): " + e.Message); }
            return -1;
        }

        static bool SetBrightness(int pct)
        {
            bool any = false;
            try
            {
                using var q = new System.Management.ManagementObjectSearcher("root\\WMI", "SELECT * FROM WmiMonitorBrightnessMethods");
                foreach (System.Management.ManagementObject m in q.Get())
                    using (m)
                    {
                        m.InvokeMethod("WmiSetBrightness", new object[] { (uint)1, (byte)Math.Clamp(pct, 0, 100) });
                        any = true;
                    }
            }
            catch (Exception e) { Log.Write("Brillo (cambiar): " + e.Message); }
            return any;
        }

        async Task<string> Brightness(Cmd c)
        {
            if (!c.Has("brillo")) return null;
            if (c.HasAny("abre", "ajustes", "configuracion")) return null;
            int now = await Task.Run(() => GetBrightness());
            if (now < 0)
            {
                Process.Start(new ProcessStartInfo("ms-settings:display") { UseShellExecute = true });
                return "Esta pantalla no deja cambiar el brillo desde Windows" + Sir + ". Le abro los ajustes de pantalla; en monitores externos se cambia con sus botones.";
            }
            int n = c.FindNumber(0);
            bool up = c.HasAny("sube", "aumenta", "mas", "subele"), down = c.HasAny("baja", "reduce", "menos", "bajale");
            int target;
            if (c.HasAny("maximo", "tope", "todo") && !down) target = 100;
            else if (c.HasAny("minimo")) target = 5;
            else if (n >= 0 && !up && !down) target = Text.ParseNumber(c.W(n));
            else if (up || down)
            {
                int step = n >= 0 ? Text.ParseNumber(c.W(n)) : c.HasAny("poco", "poquito") ? 10 : 20;
                target = now + (up ? step : -step);
            }
            else return "El brillo está al " + now + " por ciento.";
            target = Math.Clamp(target, 0, 100);
            int value = target;
            bool ok = await Task.Run(() => SetBrightness(value));
            return ok ? "Brillo al " + target + "." : "No pude cambiar el brillo" + Sir + ".";
        }

        // ---------------------------------------------------------------- divisas

        static readonly Dictionary<string, string> CurrencyWords = new Dictionary<string, string>
        {
            ["dolar"] = "USD", ["dolares"] = "USD", ["euro"] = "EUR", ["euros"] = "EUR", ["yen"] = "JPY", ["yenes"] = "JPY",
            ["reales"] = "BRL", ["soles"] = "PEN", ["francos"] = "CHF",
            ["yuan"] = "CNY", ["yuanes"] = "CNY", ["esterlina"] = "GBP", ["esterlinas"] = "GBP", ["bolivares"] = "VES", ["bolivar"] = "VES",
        };

        static string LocalPeso()
        {
            try
            {
                string iso = RegionInfo.CurrentRegion.ISOCurrencySymbol;
                if (new[] { "COP", "MXN", "ARS", "CLP", "UYU", "DOP", "CUP", "PHP" }.Contains(iso)) return iso;
            }
            catch { }
            return "COP";
        }

        static string CodeAt(Cmd c, int i)
        {
            string w = c.W(i);
            if (w == "peso" || w == "pesos")
            {
                string n = c.W(i + 1);
                return n.StartsWith("mexican") ? "MXN" : n.StartsWith("argentin") ? "ARS" : n.StartsWith("chilen") ? "CLP" : n.StartsWith("colombian") ? "COP" :
                       n.StartsWith("uruguay") ? "UYU" : n.StartsWith("dominican") ? "DOP" : LocalPeso();
            }
            if (w == "libra" || w == "libras") return c.W(i + 1).StartsWith("esterlin") ? "GBP" : null;
            // Palabras con otro sentido: solo con el apellido de la moneda.
            if (w == "sol") return c.W(i + 1).StartsWith("peruano") ? "PEN" : null;
            if (w == "real") return c.W(i + 1).StartsWith("brasilen") ? "BRL" : null;
            if (w == "franco") return c.W(i + 1).StartsWith("suizo") ? "CHF" : null;
            if (w == "dolar" || w == "dolares")
            {
                string n = c.W(i + 1);
                if (n.StartsWith("canadiense")) return "CAD";
                if (n.StartsWith("australian")) return "AUD";
                return "USD";
            }
            return CurrencyWords.TryGetValue(w, out var code) ? code : null;
        }

        static string CurrencyName(string code, bool plural) => code switch
        {
            "USD" => plural ? "dólares" : "dólar", "EUR" => plural ? "euros" : "euro", "GBP" => plural ? "libras esterlinas" : "libra esterlina",
            "JPY" => plural ? "yenes" : "yen", "BRL" => plural ? "reales" : "real", "PEN" => plural ? "soles" : "sol", "CHF" => plural ? "francos suizos" : "franco suizo",
            "CNY" => plural ? "yuanes" : "yuan", "CAD" => plural ? "dólares canadienses" : "dólar canadiense", "AUD" => plural ? "dólares australianos" : "dólar australiano",
            "MXN" => plural ? "pesos mexicanos" : "peso mexicano", "ARS" => plural ? "pesos argentinos" : "peso argentino", "CLP" => plural ? "pesos chilenos" : "peso chileno",
            "COP" => plural ? "pesos colombianos" : "peso colombiano", "UYU" => plural ? "pesos uruguayos" : "peso uruguayo", "VES" => plural ? "bolívares" : "bolívar",
            _ => code,
        };

        static readonly Dictionary<string, (DateTime at, JsonElement rates)> RateCache = new Dictionary<string, (DateTime, JsonElement)>();

        static async Task<double> Rate(string from, string to)
        {
            if (!RateCache.TryGetValue(from, out var entry) || (DateTime.Now - entry.at).TotalHours > 3)
            {
                using var doc = JsonDocument.Parse(await Http.GetStringAsync("https://open.er-api.com/v6/latest/" + from));
                entry = (DateTime.Now, doc.RootElement.GetProperty("rates").Clone());
                RateCache[from] = entry;
            }
            return entry.rates.TryGetProperty(to, out var r) ? r.GetDouble() : double.NaN;
        }

        async Task<string> Currency(Cmd c)
        {
            var codes = new List<(int idx, string code)>();
            for (int i = 0; i < c.Size; i++)
            {
                string code = CodeAt(c, i);
                if (code != null && (codes.Count == 0 || codes[^1].idx != i - 1 || codes[^1].code != code)) codes.Add((i, code));
            }
            if (codes.Count == 0) return null;
            int ni = c.FindNumber(0, true);
            bool priceQ = c.HasAny("precio", "cotizacion", "vale", "cambio", "cuanto", "cuantos", "cuantas", "convierte", "pasa", "tasa", "valor") ||
                          (c.Has("esta") && c.HasAny("como", "a")) || (ni >= 0 && c.HasAny("son", "en", "a"));
            if (!priceQ) return null;
            double amount = 1;
            if (ni >= 0)
            {
                // «100 dólares», «2,5 millones»
                string raw = c.Orig.Substring(c.T[ni].B, c.T[ni].E - c.T[ni].B);
                if (!Text.TryParseDecimal(raw, out amount)) amount = Text.ParseNumber(c.W(ni), true);
                if (c.W(ni + 1) == "mil") amount *= 1000;
                if (c.W(ni + 1) == "millon" || c.W(ni + 1) == "millones" || c.W(ni + 2) == "millones") amount *= 1000000;
            }
            string from, to;
            if (codes.Count >= 2)
            {
                // El que va justo después del número es el origen («cuántos pesos son 100 dólares»).
                var src = ni >= 0 ? codes.OrderBy(x => Math.Abs(x.idx - ni - 1)).First() : codes[0];
                from = src.code;
                to = codes.First(x => x.code != from).code;
                if (to == from) return null;
            }
            else
            {
                from = codes[0].code;
                to = from == LocalPeso() ? "USD" : LocalPeso();
            }
            try
            {
                double r = await Rate(from, to);
                if (double.IsNaN(r)) return "No tengo la cotización de esa moneda.";
                double v = amount * r;
                string vs = Math.Abs(v) >= 100 ? Text.Num(Math.Round(v), 0) : Text.Num(v, 2);
                return Calc.Format(amount) + " " + CurrencyName(from, amount != 1) + " son unos " + vs + " " + CurrencyName(to, true) + ".";
            }
            catch (Exception e)
            {
                Log.Write("Divisas: " + e.Message);
                return "No pude consultar el cambio. Revise la conexión" + Sir + ".";
            }
        }

        // ---------------------------------------------------------------- noticias

        async Task<string> News(Cmd c)
        {
            if (!c.HasAny("noticias", "titulares", "noticia")) return null;
            if (c.HasAny("abre") && !c.HasAny("lee", "dime")) return null;
            string region = "CO";
            try { region = RegionInfo.CurrentRegion.TwoLetterISORegionName; } catch { }
            string topic = "";
            int de = c.Find("de");
            if (de < 0) de = c.Find("sobre");
            if (de >= 0 && de + 1 < c.Size && !Text.IsOneOf(c.W(de + 1), "hoy", "ahora", "ultima", "ultimas", "dia")) topic = c.OrigFrom(de + 1).Trim('?', '.', ' ');
            if (topic.StartsWith("la ") || topic.StartsWith("el ")) topic = topic.Substring(3);
            string q = "hl=es-419&gl=" + region + "&ceid=" + region + ":es-419";
            string url = topic == "" ? "https://news.google.com/rss?" + q : "https://news.google.com/rss/search?q=" + Uri.EscapeDataString(topic) + "&" + q;
            try
            {
                var xml = XDocument.Parse(await Http.GetStringAsync(url));
                var items = xml.Descendants("item").Take(10).Select(i => (string)i.Element("title") ?? "").Where(t => t != "").ToList();
                if (items.Count == 0) return "No encontré noticias" + (topic != "" ? " de " + topic : "") + ".";
                string Clean(string t)
                {
                    int k = t.LastIndexOf(" - ", StringComparison.Ordinal);
                    return k > 20 ? t.Substring(0, k) : t;
                }
                E.Host.Show(string.Join("\n", items.Select(t => "• " + t)));
                return (topic == "" ? "Los titulares" : "Noticias de " + topic) + ": " + string.Join(". ", items.Take(4).Select(Clean)) + ".";
            }
            catch (Exception e)
            {
                Log.Write("Noticias: " + e.Message);
                return "No pude traer las noticias" + Sir + ".";
            }
        }

        // ---------------------------------------------------------------- red

        async Task<string> Network(Cmd c)
        {
            string s = c.Join(0);
            if (c.Contains("ip publica") || c.Contains("ip externa") || c.Contains("mi ip de internet"))
            {
                try { return "Su IP pública es " + (await Http.GetStringAsync("https://api.ipify.org")).Trim() + "."; }
                catch { return "No pude averiguarla: parece que no hay internet."; }
            }
            if (Text.IsOneOf(s, "tengo internet", "hay internet", "funciona internet", "funciona el internet", "estoy conectado", "hay conexion", "tengo conexion", "como va internet", "como va el internet"))
            {
                var sw = Stopwatch.StartNew();
                try
                {
                    using var res = await Http.GetAsync("http://www.msftconnecttest.com/connecttest.txt");
                    sw.Stop();
                    if (!res.IsSuccessStatusCode) return "Hay red, pero algo bloquea internet" + Sir + ".";
                    long ms = sw.ElapsedMilliseconds;
                    return "Sí, hay internet" + Sir + (ms < 150 ? ", y responde rápido." : ms < 600 ? "." : ", aunque va lento.");
                }
                catch
                {
                    return "No hay internet ahora mismo" + Sir + ".";
                }
            }
            return null;
        }

        // ---------------------------------------------------------------- programas que más consumen

        async Task<string> TopProcesses(Cmd c)
        {
            bool mem = c.HasAny("memoria", "ram");
            bool cpu = c.HasAny("procesador", "cpu");
            bool ask = (c.Contains("que programa") || c.Contains("que programas") || c.Contains("que aplicacion") || c.Contains("que esta consumiendo") || c.Contains("que consume")) &&
                       (c.HasAny("consume", "gasta", "usa", "come", "consumiendo", "chupa", "ocupa", "pesa") || mem || cpu);
            if (!ask) return null;
            if (mem && !cpu)
            {
                var top = Process.GetProcesses().Select(p => { try { return (name: p.ProcessName, mem: p.WorkingSet64); } catch { return (name: "", mem: 0L); } finally { p.Dispose(); } })
                    .Where(x => x.name != "" && x.name != "Idle" && x.name != "System" && x.name != "Memory Compression")
                    .GroupBy(x => x.name).Select(g => (name: g.Key, mem: g.Sum(x => x.mem))).OrderByDescending(x => x.mem).Take(3).ToList();
                return "Lo que más memoria usa: " + string.Join(", ", top.Select(t => t.name + " con " + Text.Num(t.mem / 1048576.0, 0) + " megas")) + ".";
            }
            // CPU: dos muestras separadas medio segundo.
            var first = new Dictionary<int, (string name, TimeSpan t)>();
            foreach (var p in Process.GetProcesses())
            {
                try { first[p.Id] = (p.ProcessName, p.TotalProcessorTime); } catch { }
                finally { p.Dispose(); }
            }
            var sw = Stopwatch.StartNew();
            await Task.Delay(600);
            var usage = new Dictionary<string, double>();
            foreach (var p in Process.GetProcesses())
            {
                try
                {
                    if (first.TryGetValue(p.Id, out var f) && f.name == p.ProcessName && f.name != "Idle")
                    {
                        double pct = (p.TotalProcessorTime - f.t).TotalMilliseconds / sw.Elapsed.TotalMilliseconds / Environment.ProcessorCount * 100;
                        usage[f.name] = usage.TryGetValue(f.name, out var u) ? u + pct : pct;
                    }
                }
                catch { }
                finally { p.Dispose(); }
            }
            var topCpu = usage.OrderByDescending(x => x.Value).Take(3).Where(x => x.Value >= 0.5).ToList();
            if (topCpu.Count == 0) return "Ningún programa está usando el procesador de forma notable" + Sir + ".";
            return "Lo que más procesador usa: " + string.Join(", ", topCpu.Select(t => t.Key + " al " + Math.Round(t.Value) + " por ciento")) + ".";
        }
    }
}
