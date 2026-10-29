using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;
using Jarvis.Core;

namespace Jarvis.Commands
{
    // Abrir y cerrar programas, páginas, carpetas, búsquedas y ajustes de Windows.
    public sealed class AppsModule
    {
        readonly Engine E;
        public AppsModule(Engine e)
        {
            E = e;
            new Thread(() => Index()) { IsBackground = true, Priority = ThreadPriority.BelowNormal }.Start();
        }
        string Sir => E.Sir;

        // ---------------------------------------------------------------- índice del menú Inicio

        sealed class Entry
        {
            public string Name = "", Key = "", Path = "";
        }

        List<Entry> _apps = new List<Entry>();
        DateTime _indexedAt = DateTime.MinValue;

        void Index()
        {
            try
            {
                var roots = new[]
                {
                    Environment.GetFolderPath(Environment.SpecialFolder.CommonStartMenu),
                    Environment.GetFolderPath(Environment.SpecialFolder.StartMenu),
                    Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
                    Environment.GetFolderPath(Environment.SpecialFolder.CommonDesktopDirectory),
                };
                var list = new List<Entry>();
                foreach (var r in roots.Where(Directory.Exists))
                {
                    IEnumerable<string> files;
                    try { files = Directory.EnumerateFiles(r, "*.*", new EnumerationOptions { RecurseSubdirectories = true, IgnoreInaccessible = true }); }
                    catch { continue; }
                    foreach (var f in files)
                    {
                        string ext = System.IO.Path.GetExtension(f).ToLowerInvariant();
                        if (ext != ".lnk" && ext != ".url" && ext != ".appref-ms") continue;
                        string name = System.IO.Path.GetFileNameWithoutExtension(f);
                        string key = Text.Squash(name);
                        if (key.Contains("uninstall") || key.Contains("desinstalar") || key.Contains("readme") || key.Contains("leame") || key.Contains("help") || key == "") continue;
                        if (list.Any(x => x.Key == key)) continue;
                        list.Add(new Entry { Name = name, Key = key, Path = f });
                    }
                }
                _apps = list;
                _indexedAt = DateTime.Now;
                Log.Write("Menú Inicio: " + list.Count + " programas.");
            }
            catch (Exception e)
            {
                Log.Write("Índice de programas: " + e.Message);
            }
        }

        public bool HasApp(string name) => FindApp(name, true) != null;

        public string OpenUrl(string target, string msg) => Launch(target, msg);

        Entry FindApp(string query, bool exactOnly = false)
        {
            if ((DateTime.Now - _indexedAt).TotalMinutes > 30) new Thread(() => Index()) { IsBackground = true }.Start();
            string q = Text.Squash(query);
            if (q == "") return null;
            var apps = _apps;
            var exact = apps.FirstOrDefault(a => a.Key == q);
            if (exact != null || exactOnly) return exact;
            var starts = apps.Where(a => a.Key.StartsWith(q + " ") || a.Key.StartsWith(q)).OrderBy(a => a.Key.Length).FirstOrDefault();
            if (starts != null) return starts;
            var words = q.Split(' ');
            var all = apps.Where(a => words.All(w => (" " + a.Key + " ").Contains(" " + w))).OrderBy(a => a.Key.Length).FirstOrDefault();
            if (all != null) return all;
            if (q.Length >= 4)
            {
                var inside = apps.Where(a => a.Key.Replace(" ", "").Contains(q.Replace(" ", ""))).OrderBy(a => a.Key.Length).FirstOrDefault();
                if (inside != null) return inside;
            }
            return null;
        }

        // ---------------------------------------------------------------- tablas

        static readonly Dictionary<string, string> Sites = new Dictionary<string, string>
        {
            ["youtube"] = "https://www.youtube.com", ["google"] = "https://www.google.com", ["gmail"] = "https://mail.google.com",
            ["correo"] = "https://mail.google.com", ["facebook"] = "https://www.facebook.com", ["instagram"] = "https://www.instagram.com",
            ["twitter"] = "https://x.com", ["x"] = "https://x.com", ["whatsapp"] = "https://web.whatsapp.com", ["whatsapp web"] = "https://web.whatsapp.com",
            ["netflix"] = "https://www.netflix.com", ["amazon"] = "https://www.amazon.com", ["wikipedia"] = "https://es.wikipedia.org",
            ["chatgpt"] = "https://chatgpt.com", ["claude"] = "https://claude.ai", ["github"] = "https://github.com", ["linkedin"] = "https://www.linkedin.com",
            ["outlook"] = "https://outlook.live.com", ["hotmail"] = "https://outlook.live.com", ["drive"] = "https://drive.google.com",
            ["google drive"] = "https://drive.google.com", ["maps"] = "https://maps.google.com", ["google maps"] = "https://maps.google.com",
            ["mapas"] = "https://maps.google.com", ["traductor"] = "https://translate.google.com", ["tiktok"] = "https://www.tiktok.com",
            ["twitch"] = "https://www.twitch.tv", ["reddit"] = "https://www.reddit.com", ["mercado libre"] = "https://www.mercadolibre.com",
            ["prime video"] = "https://www.primevideo.com", ["disney plus"] = "https://www.disneyplus.com", ["disney"] = "https://www.disneyplus.com",
            ["spotify web"] = "https://open.spotify.com", ["calendario de google"] = "https://calendar.google.com", ["google calendar"] = "https://calendar.google.com",
            ["google fotos"] = "https://photos.google.com", ["pinterest"] = "https://www.pinterest.com", ["telegram"] = "https://web.telegram.org",
            ["el tiempo"] = "https://www.eltiempo.es", ["youtube music"] = "https://music.youtube.com", ["canva"] = "https://www.canva.com",
        };

        static readonly Dictionary<string, string> Builtin = new Dictionary<string, string>
        {
            ["calculadora"] = "calc.exe", ["bloc de notas"] = "notepad.exe", ["notepad"] = "notepad.exe", ["notas"] = "notepad.exe",
            ["explorador"] = "explorer.exe", ["explorador de archivos"] = "explorer.exe", ["archivos"] = "explorer.exe", ["mis archivos"] = "explorer.exe",
            ["paint"] = "mspaint.exe", ["administrador de tareas"] = "taskmgr.exe", ["panel de control"] = "control.exe",
            ["simbolo del sistema"] = "cmd.exe", ["consola"] = "cmd.exe", ["terminal"] = "wt.exe", ["powershell"] = "powershell.exe",
            ["configuracion"] = "ms-settings:", ["ajustes de windows"] = "ms-settings:", ["configuracion de windows"] = "ms-settings:",
            ["tienda"] = "ms-windows-store:", ["microsoft store"] = "ms-windows-store:", ["fotos"] = "ms-photos:", ["camara"] = "microsoft.windows.camera:",
            ["reloj"] = "ms-clock:", ["alarmas de windows"] = "ms-clock:", ["recortes"] = "ms-screenclip:", ["herramienta de recortes"] = "ms-screenclip:",
            ["xbox"] = "xbox:", ["editor del registro"] = "regedit.exe", ["teclado en pantalla"] = "osk.exe", ["lupa"] = "magnify.exe",
            ["monitor de recursos"] = "resmon.exe", ["visor de eventos"] = "eventvwr.msc", ["administrador de dispositivos"] = "devmgmt.msc",
            ["mapa de caracteres"] = "charmap.exe", ["wordpad"] = "write.exe", ["emojis"] = "emoji",
        };

        static readonly Dictionary<string, string> SettingsPages = new Dictionary<string, string>
        {
            ["wifi"] = "ms-settings:network-wifi", ["red"] = "ms-settings:network", ["internet"] = "ms-settings:network", ["bluetooth"] = "ms-settings:bluetooth",
            ["sonido"] = "ms-settings:sound", ["audio"] = "ms-settings:sound", ["pantalla"] = "ms-settings:display", ["brillo"] = "ms-settings:display",
            ["actualizaciones"] = "ms-settings:windowsupdate", ["windows update"] = "ms-settings:windowsupdate", ["fondo"] = "ms-settings:personalization-background",
            ["fondo de pantalla"] = "ms-settings:personalization-background", ["temas"] = "ms-settings:themes", ["colores"] = "ms-settings:colors",
            ["aplicaciones"] = "ms-settings:appsfeatures", ["programas"] = "ms-settings:appsfeatures", ["inicio"] = "ms-settings:startupapps",
            ["energia"] = "ms-settings:powersleep", ["bateria"] = "ms-settings:batterysaver", ["almacenamiento"] = "ms-settings:storagesense",
            ["impresoras"] = "ms-settings:printers", ["raton"] = "ms-settings:mousetouchpad", ["mouse"] = "ms-settings:mousetouchpad",
            ["teclado"] = "ms-settings:typing", ["idioma"] = "ms-settings:regionlanguage", ["voz"] = "ms-settings:speech", ["fecha y hora"] = "ms-settings:dateandtime",
            ["hora"] = "ms-settings:dateandtime", ["privacidad"] = "ms-settings:privacy", ["microfono"] = "ms-settings:privacy-microphone",
            ["camara"] = "ms-settings:privacy-webcam", ["notificaciones"] = "ms-settings:notifications", ["cuentas"] = "ms-settings:yourinfo",
            ["vpn"] = "ms-settings:network-vpn", ["modo avion"] = "ms-settings:network-airplanemode", ["proyectar"] = "ms-settings:project",
            ["seguridad"] = "windowsdefender:", ["antivirus"] = "windowsdefender:", ["luz nocturna"] = "ms-settings:nightlight",
        };

        static readonly Dictionary<string, Environment.SpecialFolder> Folders = new Dictionary<string, Environment.SpecialFolder>
        {
            ["documentos"] = Environment.SpecialFolder.MyDocuments, ["mis documentos"] = Environment.SpecialFolder.MyDocuments,
            ["imagenes"] = Environment.SpecialFolder.MyPictures, ["fotos"] = Environment.SpecialFolder.MyPictures, ["mis imagenes"] = Environment.SpecialFolder.MyPictures,
            ["musica"] = Environment.SpecialFolder.MyMusic, ["mi musica"] = Environment.SpecialFolder.MyMusic,
            ["videos"] = Environment.SpecialFolder.MyVideos, ["mis videos"] = Environment.SpecialFolder.MyVideos,
            ["escritorio"] = Environment.SpecialFolder.DesktopDirectory,
        };

        // ---------------------------------------------------------------- órdenes

        static readonly string[] OpenVerbs = { "abre", "abrir", "abreme", "lanza", "inicia", "ejecuta", "arranca", "entra", "ve", "vamos", "llevame", "muestrame", "ensename", "pon", "accede" };
        static readonly string[] CloseVerbs = { "cierra", "cerrar", "cierrame", "mata", "termina", "finaliza", "sal" };

        public string Try(Cmd c)
        {
            return Search(c) ?? Open(c) ?? Close(c);
        }

        // Lo que sigue al verbo sin artículos: «abre el bloc de notas» → «bloc de notas».
        static int SkipArticles(Cmd c, int i)
        {
            while (i < c.Size && Text.IsOneOf(c.W(i), "el", "la", "los", "las", "mi", "mis", "a", "al", "en", "un", "una", "programa", "aplicacion", "app", "pagina", "web", "de", "sitio"))
            {
                if (c.W(i) == "de" && i > 0 && c.W(i - 1) != "pagina" && c.W(i - 1) != "sitio") break;
                i++;
            }
            return i;
        }

        string Open(Cmd c)
        {
            int v = Array.IndexOf(OpenVerbs, c.W(0));
            if (v < 0) return null;
            string verb = c.W(0);
            int i = 1;
            if (verb == "entra" || verb == "ve" || verb == "vamos" || verb == "llevame" || verb == "accede")
                while (i < c.Size && Text.IsOneOf(c.W(i), "a", "al", "en", "la", "el")) i++;
            i = SkipArticles(c, i);
            if (i >= c.Size) return null;
            string what = c.Join(i);
            string orig = c.OrigFrom(i);
            // «lanza una moneda», «tira los dados»: es un juego, no un programa.
            if (Text.IsOneOf(what, "moneda", "una moneda", "dado", "un dado", "dados", "los dados", "dos dados") || what.EndsWith(" dados")) return null;

            // «pon» solo para música/vídeo o «pon el bloc de notas» (si existe el programa)
            if (verb == "pon" && FindApp(what, true) == null && !Sites.ContainsKey(what)) return null;
            if ((verb == "muestrame" || verb == "ensename") && !Folders.ContainsKey(what) && !what.StartsWith("carpeta") && !Sites.ContainsKey(what)) return null;

            // carpetas
            if (what.StartsWith("carpeta ")) what = what.Substring(8).Replace("de ", "").Trim();
            if (what == "descargas" || what == "mis descargas" || what == "la de descargas")
                return Launch(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads"), "Abro Descargas.");
            if (Folders.TryGetValue(what, out var sf))
                return Launch(Environment.GetFolderPath(sf), "Abro " + orig + ".");
            if (what == "papelera" || what == "papelera de reciclaje") return Launch("shell:RecycleBinFolder", "");
            if (what == "este equipo" || what == "mi pc" || what == "mi equipo") return Launch("shell:MyComputerFolder", "");
            if (what.Length == 1 && char.IsLetter(what[0]) || what.StartsWith("disco ") && what.Length == 7)
            {
                string drive = char.ToUpper(what[^1]) + ":\\";
                if (Directory.Exists(drive)) return Launch(drive, "Abro el disco " + char.ToUpper(what[^1]) + ".");
            }

            // ajustes de Windows: «abre la configuración del wifi», «abre los ajustes de bluetooth»
            if (what.StartsWith("configuracion de ") || what.StartsWith("configuracion del ") || what.StartsWith("ajustes de ") || what.StartsWith("ajustes del ") ||
                what.StartsWith("opciones de ") || what.StartsWith("opciones del "))
            {
                string page = what.Substring(what.IndexOf(' ') + 1);
                page = page.StartsWith("de ") ? page.Substring(3) : page.StartsWith("del ") ? page.Substring(4) : page;
                page = page.StartsWith("la ") ? page.Substring(3) : page.StartsWith("el ") ? page.Substring(3) : page;
                if (SettingsPages.TryGetValue(page, out string uri)) return Launch(uri, "Abro los ajustes de " + page + ".");
            }

            if (what == "emojis") { Native.SendKeys(0x5B, 0xBE); return ""; }

            // el programa con ese nombre exacto gana (Spotify, WhatsApp instalados)
            var app = FindApp(what, true);
            if (app != null) return Launch(app.Path, Opened(app.Name));
            if (Builtin.TryGetValue(what, out string exe)) return Launch(exe, Opened(orig));
            if (Sites.TryGetValue(what, out string url)) return Launch(url, Opened(orig));
            // direcciones dichas: «abre elpais punto com»
            string dom = what.Replace(" punto ", ".").Replace(" ", "");
            if (dom.Contains('.') && !dom.EndsWith(".") && dom.Split('.').Last().Length >= 2 && dom.Split('.').Last().Length <= 6)
                return Launch("https://" + dom, "Abro " + dom + ".");
            app = FindApp(what);
            if (app != null) return Launch(app.Path, Opened(app.Name));
            if (verb == "abre" || verb == "abrir" || verb == "abreme" || verb == "lanza" || verb == "inicia" || verb == "ejecuta" || verb == "arranca")
                return "No encuentro «" + orig + "» en este equipo" + Sir + ". ¿Quiere que lo busque en internet? Diga «busca " + orig + "».";
            return null;
        }

        string Opened(string name) => TalkModule.Pick("Abriendo " + name + ".", "Abro " + name + Sir + ".", name + ", en marcha.");

        string Launch(string target, string msg)
        {
            try
            {
                Process.Start(new ProcessStartInfo(target) { UseShellExecute = true });
                return msg;
            }
            catch (Exception e)
            {
                Log.Write("Abrir «" + target + "»: " + e.Message);
                return "No he podido abrirlo" + Sir + ".";
            }
        }

        string Close(Cmd c)
        {
            if (Array.IndexOf(CloseVerbs, c.W(0)) < 0 || c.Size < 2) return null;
            if (c.W(0) == "sal" && c.W(1) != "de") return null;
            int i = SkipArticles(c, c.W(1) == "de" ? 2 : 1);
            if (i >= c.Size) return null;
            string what = c.Join(i);
            if (Text.IsOneOf(what, "sesion", "la sesion")) return null;
            string key = what.Replace(" ", "");
            var aliases = new Dictionary<string, string[]>
            {
                ["navegador"] = new[] { "chrome", "msedge", "firefox", "opera", "brave" }, ["chrome"] = new[] { "chrome" }, ["edge"] = new[] { "msedge" },
                ["word"] = new[] { "winword" }, ["excel"] = new[] { "excel" }, ["powerpoint"] = new[] { "powerpnt" }, ["blocdenotas"] = new[] { "notepad" },
                ["calculadora"] = new[] { "calculatorapp", "calculator" }, ["explorador"] = new[] { "explorer" }, ["teams"] = new[] { "ms-teams", "teams" },
                ["whatsapp"] = new[] { "whatsapp", "whatsapp.root" }, ["administradordetareas"] = new[] { "taskmgr" }, ["paint"] = new[] { "mspaint" },
            };
            var names = aliases.TryGetValue(key, out var al) ? al : new[] { key };
            int closed = 0;
            foreach (var p in Process.GetProcesses())
            {
                try
                {
                    string pn = p.ProcessName.ToLowerInvariant();
                    bool match = names.Any(n => pn == n || (n.Length >= 4 && pn.StartsWith(n)));
                    if (!match && key.Length >= 4 && p.MainWindowHandle != IntPtr.Zero)
                        match = Text.Squash(p.MainWindowTitle).Replace(" ", "").EndsWith(key) || Text.Squash(p.MainWindowTitle).Replace(" ", "").Contains(key) && key.Length >= 6;
                    if (!match) continue;
                    if (pn == "explorer")
                    {
                        // No matar el escritorio: cerrar solo las ventanas de carpetas.
                        CloseExplorerWindows();
                        closed++;
                        break;
                    }
                    if (p.MainWindowHandle != IntPtr.Zero && p.CloseMainWindow()) closed++;
                }
                catch { }
                finally { p.Dispose(); }
            }
            if (closed == 0) return "No veo «" + c.OrigFrom(i) + "» abierto" + Sir + ".";
            return TalkModule.Pick("Cerrado.", "Cierro " + c.OrigFrom(i) + ".", "Hecho" + Sir + ".");
        }

        static void CloseExplorerWindows()
        {
            var list = new List<IntPtr>();
            Native.EnumWindows((h, l) =>
            {
                if (Native.IsWindowVisible(h) && Native.WindowClass(h) == "CabinetWClass") list.Add(h);
                return true;
            }, IntPtr.Zero);
            foreach (var h in list) Native.PostMessage(h, Native.WM_CLOSE, IntPtr.Zero, IntPtr.Zero);
        }

        // ---------------------------------------------------------------- búsquedas

        string Search(Cmd c)
        {
            string w0 = c.W(0);
            bool searchVerb = Text.IsOneOf(w0, "busca", "buscar", "buscame", "googlea", "investiga");
            bool playVerb = Text.IsOneOf(w0, "pon", "reproduce", "ponme", "quiero");
            int en = -1;
            for (int i = c.Size - 2; i >= 1; i--)
                if (c.W(i) == "en" && Text.IsOneOf(c.Join(i + 1), "youtube", "google", "wikipedia", "spotify", "amazon", "maps", "google maps", "el mapa", "mapas", "mercado libre", "imagenes", "google imagenes", "netflix", "twitter", "x", "tiktok", "github"))
                {
                    en = i;
                    break;
                }
            if (!searchVerb && !(playVerb && en > 0))
            {
                // «cómo llegar a …»
                if (c.Contains("como llegar a") || c.Contains("como llego a") || c.Contains("ruta a") || c.Contains("ruta hasta"))
                {
                    int k = c.Find("a", 1);
                    if (c.Has("hasta")) k = c.Find("hasta");
                    string dest = c.OrigFrom(k + 1);
                    if (dest != "") return Launch("https://www.google.com/maps/dir/?api=1&destination=" + Uri.EscapeDataString(dest), "Le muestro la ruta a " + dest + ".");
                }
                return null;
            }
            int from = 1;
            while (from < c.Size && Text.IsOneOf(c.W(from), "en", "google", "internet", "la", "web", "informacion", "sobre", "de", "acerca", "que", "a", "me"))
            {
                if (c.W(from) == "en" && from + 1 < c.Size && !Text.IsOneOf(c.W(from + 1), "google", "internet", "la", "web")) break;
                from++;
            }
            int to = en > 0 ? en : c.Size;
            string where = en > 0 ? c.Join(en + 1) : "google";
            // «busca en youtube gatos»
            if (en < 0 && c.W(1) == "en" && Text.IsOneOf(c.W(2), "youtube", "wikipedia", "spotify", "amazon", "maps"))
            {
                where = c.W(2);
                from = 3;
            }
            if (from >= to) return searchVerb ? "¿Qué busco" + Sir + "?" : null;
            string q = c.OrigFrom(from, to).Trim(' ', '?', '.');
            if (q == "") return null;
            string e = Uri.EscapeDataString(q);
            switch (where)
            {
                case "youtube":
                    return Launch("https://www.youtube.com/results?search_query=" + e, playVerb ? "Busco " + q + " en YouTube." : "Busco en YouTube: " + q + ".");
                case "wikipedia":
                    return Launch("https://es.wikipedia.org/w/index.php?search=" + e, "Busco " + q + " en Wikipedia.");
                case "spotify":
                    return Launch("spotify:search:" + e, "Busco " + q + " en Spotify.");
                case "amazon":
                    return Launch("https://www.amazon.com/s?k=" + e, "Busco " + q + " en Amazon.");
                case "mercado libre":
                    return Launch("https://listado.mercadolibre.com/" + e, "Busco " + q + " en Mercado Libre.");
                case "maps": case "google maps": case "el mapa": case "mapas":
                    return Launch("https://www.google.com/maps/search/" + e, "Le muestro " + q + " en el mapa.");
                case "imagenes": case "google imagenes":
                    return Launch("https://www.google.com/search?tbm=isch&q=" + e, "Busco imágenes de " + q + ".");
                case "netflix":
                    return Launch("https://www.netflix.com/search?q=" + e, "Busco " + q + " en Netflix.");
                case "github":
                    return Launch("https://github.com/search?q=" + e, "Busco " + q + " en GitHub.");
                case "tiktok":
                    return Launch("https://www.tiktok.com/search?q=" + e, "Busco " + q + " en TikTok.");
                case "twitter": case "x":
                    return Launch("https://x.com/search?q=" + e, "Busco " + q + " en X.");
            }
            string engine = E.S.SearchEngine switch
            {
                "bing" => "https://www.bing.com/search?q=",
                "duckduckgo" => "https://duckduckgo.com/?q=",
                _ => "https://www.google.com/search?q=",
            };
            return Launch(engine + e, "Buscando " + q + ".");
        }
    }
}
