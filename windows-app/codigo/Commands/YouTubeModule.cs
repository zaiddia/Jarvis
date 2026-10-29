using System;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using Jarvis.Core;

namespace Jarvis.Commands
{
    // «Pon un video de Karol G», «reproduce Despacito en YouTube», «pon música de Juanes»:
    // busca en YouTube y abre directamente el primer video (empieza a sonar solo).
    public sealed class YouTubeModule
    {
        readonly Engine E;
        static readonly HttpClient Http = CreateHttp();
        public YouTubeModule(Engine e) { E = e; }
        string Sir => E.Sir;

        static HttpClient CreateHttp()
        {
            var h = Net.Create(TimeSpan.FromSeconds(10));
            h.DefaultRequestHeaders.Add("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36");
            h.DefaultRequestHeaders.Add("Accept-Language", "es-419,es;q=0.9");
            return h;
        }

        static readonly string[] Generic = { "musica", "la musica", "algo", "algo de musica", "musica de fondo", "un video", "videos", "un poco de musica", "" };

        // Qué hay que poner. null si la orden no es de este tipo.
        static string Query(Cmd c, out bool music, out bool ytMusic)
        {
            music = false;
            ytMusic = c.Contains("youtube music");
            string w0 = c.W(0);
            if (c.HasAny("spotify", "netflix")) return null;   // otros servicios: los atiende la búsqueda normal
            bool playVerb = Text.IsOneOf(w0, "pon", "reproduce", "ponme", "quiero", "escuchar", "ver", "busca", "toca", "suena", "dale");
            if (!playVerb) return null;
            int from = 1;
            if (w0 == "quiero" && Text.IsOneOf(c.W(1), "ver", "escuchar", "oir")) from = 2;
            if (w0 == "busca" && !(c.Has("reproduce") || c.Has("pon") || c.Contains("y ponlo"))) return null;   // «busca X en YouTube» solo busca
            bool youtube = c.Has("youtube");
            // «pon un video de X», «pon el video de X», «pon videos de X»
            int vid = c.FindAny(new[] { "video", "videos", "videoclip", "cancion", "canciones", "tema", "temas", "musica", "concierto", "disco", "album", "playlist", "mix" }, from);
            // «reproduce Despacito», «quiero escuchar a Juanes»: lo que sigue es lo que hay que poner.
            if (vid < 0 && !youtube && (w0 == "reproduce" || from == 2) && c.Size > from) youtube = true;
            if (vid < 0 && !youtube && !Text.IsOneOf(w0, "escuchar", "ver"))
            {
                // «pon salsa», «pon vallenato»: géneros
                if (c.Size >= 2 && c.Size <= 4 && Text.IsOneOf(c.W(from), "salsa", "vallenato", "reggaeton", "rock", "jazz", "pop", "bachata", "merengue", "cumbia",
                                                              "baladas", "clasica", "lofi", "electronica", "boleros", "rancheras", "tango", "champeta", "rap", "trap", "regional"))
                {
                    music = true;
                    return c.OrigFrom(from) + " mix";
                }
                return null;
            }
            music = vid >= 0 && Text.IsOneOf(c.W(vid), "cancion", "canciones", "tema", "temas", "musica", "disco", "album", "playlist", "mix");
            int end = c.Size;
            for (int i = c.Size - 2; i >= from; i--)
                if (c.W(i) == "en" && (c.W(i + 1) == "youtube")) { end = i; break; }
            int start = from;
            if (vid >= 0 && vid < end)
            {
                start = vid + 1;
                if (Text.IsOneOf(c.W(start), "de", "del", "llamado", "llamada", "que", "se", "sobre")) start++;
                if (c.W(start - 1) == "se" && c.W(start) == "llama") start++;
                // «pon la canción Despacito»: lo que va después; «pon música de Juanes»: el artista
            }
            while (start < end && Text.IsOneOf(c.W(start), "el", "la", "los", "las", "un", "una", "algo", "de"))
                start++;
            if (start >= end) return null;
            string q = c.OrigFrom(start, end).Trim(' ', '.', '?', '¿');
            if (Text.IsOneOf(Text.Squash(q), Generic)) return null;
            if (Text.IsOneOf(Text.Squash(q), "anterior", "siguiente", "otra", "otra vez", "de nuevo", "pausa", "la musica", "musica")) return null;
            if (q.StartsWith("a ", StringComparison.OrdinalIgnoreCase)) q = q.Substring(2);   // «escuchar a Juanes»
            if (vid >= 0 && c.W(vid).StartsWith("video") == false && music && !q.ToLowerInvariant().Contains("mix") && c.W(vid) == "musica") q += " canciones";
            if (c.HasAny("ultimo", "nuevo", "reciente")) q += " último video";
            return q;
        }

        public async Task<string> TryAsync(Cmd c)
        {
            string q = Query(c, out bool music, out bool ytMusic);
            if (q == null) return null;
            var (id, title) = await FirstVideo(q, E.S.YouTubeApiKey);
            if (id == null)
            {
                E.Apps.OpenUrl("https://www.youtube.com/results?search_query=" + Uri.EscapeDataString(q), "");
                return "No pude abrir el video directamente; le dejo la búsqueda de «" + q + "» en YouTube.";
            }
            string url = (ytMusic ? "https://music.youtube.com/watch?v=" : "https://www.youtube.com/watch?v=") + id + "&autoplay=1";
            E.Apps.OpenUrl(url, "");
            string t = title != null ? Text.Preview(title, 70) : q;
            return TalkModule.Pick("Reproduciendo «" + t + "».", "Ahí va: «" + t + "».", "Le pongo «" + t + "»" + Sir + ".");
        }

        // El primer video de la búsqueda (sin anuncios ni listas). Con clave de API, la búsqueda oficial;
        // si no, el bloque «ytInitialData» de la página y, como último recurso, una búsqueda simple en el HTML.
        public static async Task<(string id, string title)> FirstVideo(string query, string apiKey = "")
        {
            if (!string.IsNullOrWhiteSpace(apiKey))
            {
                try
                {
                    string api = "https://www.googleapis.com/youtube/v3/search?part=snippet&type=video&maxResults=1&safeSearch=none&q=" +
                                 Uri.EscapeDataString(query) + "&key=" + Uri.EscapeDataString(apiKey.Trim());
                    using var doc = JsonDocument.Parse(await Http.GetStringAsync(api));
                    var items = doc.RootElement.GetProperty("items");
                    if (items.GetArrayLength() > 0)
                    {
                        var it = items[0];
                        string id = it.GetProperty("id").GetProperty("videoId").GetString();
                        string title = WebUtility.HtmlDecode(it.GetProperty("snippet").GetProperty("title").GetString() ?? "");
                        if (!string.IsNullOrEmpty(id)) return (id, title);
                    }
                }
                catch (Exception e) { Log.Write("YouTube (API): " + e.Message + " — pruebo sin la API."); }
            }
            try
            {
                using var req = new HttpRequestMessage(HttpMethod.Get, "https://www.youtube.com/results?search_query=" + Uri.EscapeDataString(query) + "&sp=EgIQAQ%253D%253D");
                // Evita la página de consentimiento de cookies (en algunos países aparece antes de los resultados).
                req.Headers.TryAddWithoutValidation("Cookie", "CONSENT=YES+1; SOCS=CAI");
                using var res = await Http.SendAsync(req);
                string html = await res.Content.ReadAsStringAsync();

                // 1) El JSON con los resultados que trae la página.
                var found = FromInitialData(html);
                if (found.id != null) return found;

                // 2) Respaldo: el primer «videoRenderer» del HTML.
                var m = Regex.Match(html, "\"videoRenderer\"\\s*:\\s*\\{\\s*\"videoId\"\\s*:\\s*\"([A-Za-z0-9_-]{11})\"");
                if (!m.Success) m = Regex.Match(html, "\"videoId\"\\s*:\\s*\"([A-Za-z0-9_-]{11})\"");
                if (!m.Success) m = Regex.Match(html, "/watch\\?v=([A-Za-z0-9_-]{11})");
                if (!m.Success)
                {
                    Log.Write("YouTube: la página no trajo resultados reconocibles (¿cambió su formato?).");
                    return (null, null);
                }
                string vid = m.Groups[1].Value;
                string ttl = null;
                var t = Regex.Match(html.Substring(m.Index, Math.Min(4000, html.Length - m.Index)), "\"title\"\\s*:\\s*\\{\\s*\"runs\"\\s*:\\s*\\[\\s*\\{\\s*\"text\"\\s*:\\s*\"((?:[^\"\\\\]|\\\\.)*)\"");
                if (t.Success) ttl = Regex.Unescape(t.Groups[1].Value);
                return (vid, ttl);
            }
            catch (Exception e)
            {
                Log.Write("YouTube: " + e.Message);
                return (null, null);
            }
        }

        // Busca «var ytInitialData = {…};» y recorre el JSON hasta el primer video.
        static (string id, string title) FromInitialData(string html)
        {
            try
            {
                int k = html.IndexOf("ytInitialData", StringComparison.Ordinal);
                if (k < 0) return (null, null);
                int start = html.IndexOf('{', k);
                if (start < 0) return (null, null);
                // Hasta la llave que cierra (contando llaves, respetando las cadenas).
                int depth = 0, end = -1;
                bool inStr = false, esc = false;
                for (int i = start; i < html.Length; i++)
                {
                    char ch = html[i];
                    if (inStr)
                    {
                        if (esc) esc = false;
                        else if (ch == '\\') esc = true;
                        else if (ch == '"') inStr = false;
                        continue;
                    }
                    if (ch == '"') inStr = true;
                    else if (ch == '{') depth++;
                    else if (ch == '}' && --depth == 0) { end = i; break; }
                }
                if (end < 0) return (null, null);
                using var doc = JsonDocument.Parse(html.AsMemory(start, end - start + 1));
                return Walk(doc.RootElement, 0);
            }
            catch (Exception e)
            {
                Log.Write("YouTube (ytInitialData): " + e.Message);
                return (null, null);
            }
        }

        static (string id, string title) Walk(JsonElement e, int depth)
        {
            if (depth > 40) return (null, null);
            if (e.ValueKind == JsonValueKind.Object)
            {
                if (e.TryGetProperty("videoRenderer", out var vr) && vr.TryGetProperty("videoId", out var id))
                {
                    string title = null;
                    if (vr.TryGetProperty("title", out var t))
                    {
                        if (t.TryGetProperty("runs", out var runs) && runs.GetArrayLength() > 0 && runs[0].TryGetProperty("text", out var tx)) title = tx.GetString();
                        else if (t.TryGetProperty("simpleText", out var st)) title = st.GetString();
                    }
                    return (id.GetString(), title);
                }
                foreach (var p in e.EnumerateObject())
                {
                    var r = Walk(p.Value, depth + 1);
                    if (r.id != null) return r;
                }
            }
            else if (e.ValueKind == JsonValueKind.Array)
                foreach (var x in e.EnumerateArray())
                {
                    var r = Walk(x, depth + 1);
                    if (r.id != null) return r;
                }
            return (null, null);
        }
    }
}
