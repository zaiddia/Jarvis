using System;
using System.Windows.Media;

namespace Jarvis.Ui
{
    public enum HudState { Idle, Listening, Thinking, Speaking, Error, Muted }

    // Colores del panel por tema y por estado.
    public sealed class Theme
    {
        public Color Accent, Accent2, Back, Text, Dim;

        public static Theme Get(string name)
        {
            switch ((name ?? "").ToLowerInvariant())
            {
                case "mark3":
                    return new Theme { Accent = C(0xFF, 0x4A, 0x3D), Accent2 = C(0xFF, 0xC3, 0x4A), Back = C(0x1A, 0x08, 0x08), Text = C(0xFF, 0xF1, 0xE6), Dim = C(0xC9, 0x9A, 0x8A) };
                case "verde":
                    return new Theme { Accent = C(0x3D, 0xFF, 0xA8), Accent2 = C(0x9D, 0xFF, 0x5C), Back = C(0x04, 0x16, 0x10), Text = C(0xE6, 0xFF, 0xF4), Dim = C(0x84, 0xC4, 0xA8) };
                case "morado":
                    return new Theme { Accent = C(0xB2, 0x6B, 0xFF), Accent2 = C(0xFF, 0x6B, 0xD6), Back = C(0x10, 0x07, 0x1E), Text = C(0xF3, 0xEA, 0xFF), Dim = C(0xAE, 0x9A, 0xCC) };
                case "grafito":
                    return new Theme { Accent = C(0xC8, 0xD3, 0xDD), Accent2 = C(0x7F, 0xD8, 0xFF), Back = C(0x0E, 0x10, 0x13), Text = C(0xF2, 0xF5, 0xF7), Dim = C(0x93, 0x9C, 0xA6) };
                default:
                    return new Theme { Accent = C(0x2F, 0xB8, 0xFF), Accent2 = C(0x6B, 0xF2, 0xFF), Back = C(0x04, 0x0E, 0x1A), Text = C(0xE8, 0xF6, 0xFF), Dim = C(0x86, 0xA9, 0xC2) };
            }
        }

        public Color For(HudState s) => s switch
        {
            HudState.Listening => C(0x37, 0xF0, 0xFF),
            HudState.Thinking => C(0xFF, 0xB8, 0x2E),
            HudState.Speaking => Accent,
            HudState.Error => C(0xFF, 0x3B, 0x4E),
            HudState.Muted => C(0x6E, 0x78, 0x84),
            _ => Mix(Accent, C(0x50, 0x60, 0x70), 0.35),
        };

        public static string Label(HudState s, bool viernes) => s switch
        {
            HudState.Listening => "ESCUCHANDO",
            HudState.Thinking => "PROCESANDO",
            HudState.Speaking => "RESPONDIENDO",
            HudState.Error => "ATENCIÓN",
            HudState.Muted => "EN SILENCIO",
            _ => "EN ESPERA",
        };

        public static Color C(byte r, byte g, byte b, byte a = 255) => Color.FromArgb(a, r, g, b);

        public static Color Mix(Color a, Color b, double t)
        {
            t = Math.Clamp(t, 0, 1);
            return Color.FromArgb((byte)(a.A + (b.A - a.A) * t), (byte)(a.R + (b.R - a.R) * t), (byte)(a.G + (b.G - a.G) * t), (byte)(a.B + (b.B - a.B) * t));
        }

        public static Color WithAlpha(Color c, double a) => Color.FromArgb((byte)Math.Clamp(a * 255, 0, 255), c.R, c.G, c.B);
    }
}
