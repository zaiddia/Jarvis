using System;
using System.Linq;
using System.Threading.Tasks;
using Jarvis.Core;
using Windows.Media.Control;

namespace Jarvis.Commands
{
    // Música y vídeo con los controles multimedia de Windows (Spotify, YouTube en el navegador, Música…):
    // saber qué suena, reproducir o pausar de verdad (no alternar), aleatorio y repetir.
    public sealed class MediaModule
    {
        readonly Engine E;
        public MediaModule(Engine e) { E = e; }
        string Sir => E.Sir;

        static GlobalSystemMediaTransportControlsSessionManager _mgr;

        public static async Task<GlobalSystemMediaTransportControlsSession> Session()
        {
            try
            {
                _mgr ??= await GlobalSystemMediaTransportControlsSessionManager.RequestAsync();
                var cur = _mgr.GetCurrentSession();
                if (cur != null) return cur;
                return _mgr.GetSessions().FirstOrDefault();
            }
            catch (Exception e)
            {
                Log.Write("Multimedia: " + e.Message);
                return null;
            }
        }

        static string AppName(GlobalSystemMediaTransportControlsSession s)
        {
            string id = (s.SourceAppUserModelId ?? "").ToLowerInvariant();
            if (id.Contains("spotify")) return "Spotify";
            if (id.Contains("chrome")) return "Chrome";
            if (id.Contains("msedge")) return "Edge";
            if (id.Contains("firefox")) return "Firefox";
            if (id.Contains("zunemusic") || id.Contains("media")) return "Reproductor multimedia";
            if (id.Contains("vlc")) return "VLC";
            return "";
        }

        static bool Playing(GlobalSystemMediaTransportControlsSession s) =>
            s.GetPlaybackInfo()?.PlaybackStatus == GlobalSystemMediaTransportControlsSessionPlaybackStatus.Playing;

        public async Task<string> TryAsync(Cmd c)
        {
            string s = c.Join(0);

            bool askWhat = Text.IsOneOf(s, "que suena", "que esta sonando", "que cancion es", "que cancion es esta", "que cancion suena", "como se llama esta cancion",
                                        "quien canta", "quien canta esto", "quien canta esta cancion", "que estoy escuchando", "que musica suena", "que es esto que suena",
                                        "que video es", "que se esta reproduciendo");
            bool play = Text.IsOneOf(s, "reproduce", "continua", "sigue", "reanuda", "play", "dale play", "reanuda la musica", "continua la musica", "pon la musica",
                                     "sigue la musica", "reproduce la musica", "quita la pausa", "reanudalo", "pon musica", "musica", "pon algo de musica");
            bool pause = Text.IsOneOf(s, "pausa", "pausa la musica", "pon pausa", "para la musica", "deten la musica", "pausa el video", "pausa la cancion", "pausalo",
                                      "para el video", "pausa spotify");
            bool shuffle = c.HasAny("aleatorio", "aleatoria", "mezcla", "shuffle") && c.HasAny("activa", "pon", "modo", "desactiva", "quita", "mezcla");
            bool repeat = (c.HasAny("repite", "repetir", "bucle") && c.HasAny("cancion", "tema", "lista", "todo", "bucle")) || c.Contains("quita la repeticion");
            if (!askWhat && !play && !pause && !shuffle && !repeat) return null;

            var ses = await Session();
            if (ses == null)
            {
                if (play)
                {
                    // Nada abierto: lanzar Spotify si está instalado.
                    var r = await E.HandleAsync("abre spotify");
                    return r?.Say ?? "No hay nada reproduciéndose" + Sir + ".";
                }
                if (askWhat) return "Ahora mismo no suena nada" + Sir + ".";
                return null; // que lo intente con las teclas multimedia
            }
            try
            {
                if (askWhat)
                {
                    var p = await ses.TryGetMediaPropertiesAsync();
                    if (p == null || string.IsNullOrWhiteSpace(p.Title)) return "No sé qué está sonando" + Sir + ".";
                    string app = AppName(ses);
                    string who = !string.IsNullOrWhiteSpace(p.Artist) ? ", de " + p.Artist : "";
                    string state = Playing(ses) ? "Suena" : "En pausa";
                    return state + " «" + p.Title + "»" + who + (app != "" ? ", en " + app : "") + ".";
                }
                if (play)
                {
                    if (Playing(ses)) return "Ya está sonando" + Sir + ".";
                    await ses.TryPlayAsync();
                    return "";
                }
                if (pause)
                {
                    if (!Playing(ses)) return "Ya estaba en pausa.";
                    await ses.TryPauseAsync();
                    return "";
                }
                if (shuffle)
                {
                    bool on = !c.HasAny("desactiva", "quita");
                    bool ok = await ses.TryChangeShuffleActiveAsync(on);
                    return ok ? (on ? "Modo aleatorio activado." : "Modo aleatorio desactivado.") : "Esta aplicación no deja cambiar el modo aleatorio.";
                }
                if (repeat)
                {
                    var mode = c.Contains("quita la repeticion") || c.HasAny("desactiva", "quita")
                        ? Windows.Media.MediaPlaybackAutoRepeatMode.None
                        : c.HasAny("lista", "todo") ? Windows.Media.MediaPlaybackAutoRepeatMode.List : Windows.Media.MediaPlaybackAutoRepeatMode.Track;
                    bool ok = await ses.TryChangeAutoRepeatModeAsync(mode);
                    if (!ok) return "Esta aplicación no deja cambiar la repetición.";
                    return mode == Windows.Media.MediaPlaybackAutoRepeatMode.None ? "Sin repetición." : mode == Windows.Media.MediaPlaybackAutoRepeatMode.Track ? "Repetiré esta canción." : "Repetiré la lista.";
                }
            }
            catch (Exception e)
            {
                Log.Write("Multimedia: " + e.Message);
            }
            return null;
        }

        // Para el informe del día y la IA: «Suena X de Y».
        public static async Task<string> NowPlaying()
        {
            var ses = await Session();
            if (ses == null || !Playing(ses)) return "";
            try
            {
                var p = await ses.TryGetMediaPropertiesAsync();
                if (p == null || string.IsNullOrWhiteSpace(p.Title)) return "";
                return p.Title + (string.IsNullOrWhiteSpace(p.Artist) ? "" : " de " + p.Artist);
            }
            catch { return ""; }
        }
    }
}
