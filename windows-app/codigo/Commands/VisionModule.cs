using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;
using Jarvis.Core;

namespace Jarvis.Commands
{
    // «¿Qué hay en mi pantalla?», «mira esto y dime qué error es»: una captura para que la IA la vea.
    // Solo se hace cuando se pide; el panel de JARVIS no sale en la captura.
    public sealed class VisionModule
    {
        readonly Engine E;
        public VisionModule(Engine e) { E = e; }

        static readonly string[] Phrases =
        {
            "que hay en mi pantalla", "que hay en la pantalla", "que ves", "que ves en mi pantalla", "que ves en la pantalla", "mira la pantalla",
            "mira mi pantalla", "mira esto", "lee la pantalla", "leeme la pantalla", "que pone aqui", "que pone en la pantalla", "que dice la pantalla",
            "que dice aqui", "describe la pantalla", "describe lo que ves", "que es esto", "explicame esto", "ayudame con esto", "resume la pantalla",
            "resume esto que estoy viendo", "que estoy viendo", "analiza la pantalla", "revisa la pantalla", "echa un vistazo", "echale un vistazo",
        };

        static readonly string[] Starts = { "mira esto", "mira la pantalla", "mira mi pantalla", "echa un vistazo", "echale un vistazo", "fijate en la pantalla", "lee la pantalla", "mirando la pantalla" };

        public string Try(Cmd c)
        {
            string s = c.Join(0);
            bool hit = Phrases.Contains(s) || Starts.Any(p => s.StartsWith(p + " "));
            if (!hit && c.Has("pantalla") && c.HasAny("mira", "lee", "leeme", "analiza", "describe", "resume", "explica", "explicame", "traduce", "ves", "revisa", "dime"))
                hit = c.HasAny("en", "de", "la", "mi") && !c.HasAny("apaga", "brillo", "captura", "graba", "bloquea", "pantallazo");
            if (!hit) return null;
            if (E.S.ApiKey.Trim() == "" && E.S.AiProvider != "ollama" && !(E.S.AiProvider == "openai" && E.S.ApiUrl.Trim() != ""))
                return "Para mirar la pantalla necesito una clave de IA" + E.Sir + ". Póngala en mis ajustes, en Inteligencia.";
            string q = c.Orig.Trim();
            if (Phrases.Contains(s)) q = s.Contains("lee") ? "Lee en voz alta lo importante que pone en la pantalla." :
                                        s.Contains("resume") ? "Resume lo que hay en la pantalla." :
                                        "Describe brevemente qué hay en la pantalla y si hay algo que deba saber.";
            E.ScreenQuestion = q;
            return "";
        }

        // Captura del monitor donde está la ventana activa, reducida a 1568 px como mucho, en JPEG.
        public static byte[] CaptureJpeg(IntPtr target)
        {
            var screen = target != IntPtr.Zero ? System.Windows.Forms.Screen.FromHandle(target) : System.Windows.Forms.Screen.PrimaryScreen;
            var b = screen.Bounds;
            using var full = new Bitmap(b.Width, b.Height);
            using (var g = Graphics.FromImage(full)) g.CopyFromScreen(b.Left, b.Top, 0, 0, full.Size);
            double scale = Math.Min(1.0, 1568.0 / Math.Max(b.Width, b.Height));
            int w = Math.Max(1, (int)(b.Width * scale)), h = Math.Max(1, (int)(b.Height * scale));
            using var small = new Bitmap(w, h, PixelFormat.Format24bppRgb);   // JPEG no usa transparencia
            using (var g = Graphics.FromImage(small))
            {
                g.InterpolationMode = System.Drawing.Drawing2D.InterpolationMode.HighQualityBicubic;
                g.DrawImage(full, 0, 0, w, h);
            }
            var codec = ImageCodecInfo.GetImageEncoders().FirstOrDefault(x => x.FormatID == ImageFormat.Jpeg.Guid);
            if (codec == null) throw new InvalidOperationException("Windows no tiene el codificador JPEG");
            using var ps = new EncoderParameters(1);
            ps.Param[0] = new EncoderParameter(System.Drawing.Imaging.Encoder.Quality, 80L);
            using var ms = new MemoryStream();
            small.Save(ms, codec, ps);
            return ms.ToArray();
        }
    }
}
