using System;
using System.Linq;
using System.Text.Json;

namespace Jarvis.Core
{
    // Lee la lista de Releases de GitHub y elige la versión más nueva de JARVIS para Windows.
    // En el mismo repositorio hay Releases de otros proyectos (el JARVIS de Python): solo cuentan las «windows-v…».
    public static class Releases
    {
        public const string TagPrefix = "windows-v";

        public sealed class Info
        {
            public Version Version;
            public string Tag = "", Page = "", Url = "", AssetName = "", Sha256 = "", Notes = "";
            public long Size;
        }

        // «4.1.0» o «windows-v4.1.0» → 4.1.0 (siempre con tres partes, para comparar bien).
        public static Version ParseVersion(string s)
        {
            s = (s ?? "").Trim();
            if (s.StartsWith(TagPrefix, StringComparison.OrdinalIgnoreCase)) s = s.Substring(TagPrefix.Length);
            if (s.StartsWith("v", StringComparison.OrdinalIgnoreCase)) s = s.Substring(1);
            int dash = s.IndexOfAny(new[] { '-', '+', ' ' });
            if (dash > 0) s = s.Substring(0, dash);
            if (!Version.TryParse(s.Contains('.') ? s : s + ".0", out var v)) return null;
            return new Version(v.Major, Math.Max(0, v.Minor), Math.Max(0, v.Build));
        }

        public static bool IsNewer(Version candidate, Version current)
        {
            if (candidate == null) return false;
            if (current == null) return true;
            var c = new Version(current.Major, Math.Max(0, current.Minor), Math.Max(0, current.Build));
            return candidate > c;
        }

        // La Release más nueva con su zip, o null. «json» es la respuesta de /repos/{dueño}/{repo}/releases.
        public static Info Newest(string json)
        {
            using var doc = JsonDocument.Parse(json);
            if (doc.RootElement.ValueKind != JsonValueKind.Array) return null;
            Info best = null;
            foreach (var r in doc.RootElement.EnumerateArray())
            {
                if (Bool(r, "draft") || Bool(r, "prerelease")) continue;
                string tag = Str(r, "tag_name");
                if (!tag.StartsWith(TagPrefix, StringComparison.OrdinalIgnoreCase)) continue;
                var v = ParseVersion(tag);
                if (v == null || (best != null && v <= best.Version)) continue;
                if (!r.TryGetProperty("assets", out var assets) || assets.ValueKind != JsonValueKind.Array) continue;
                var zip = assets.EnumerateArray().FirstOrDefault(a =>
                {
                    string n = Str(a, "name");
                    return n.StartsWith("JARVIS-", StringComparison.OrdinalIgnoreCase) && n.EndsWith(".zip", StringComparison.OrdinalIgnoreCase);
                });
                if (zip.ValueKind != JsonValueKind.Object) continue;
                string digest = Str(zip, "digest");   // «sha256:…» (GitHub lo añade a cada archivo)
                best = new Info
                {
                    Version = v,
                    Tag = tag,
                    Page = Str(r, "html_url"),
                    Notes = Str(r, "body"),
                    Url = Str(zip, "browser_download_url"),
                    AssetName = Str(zip, "name"),
                    Size = zip.TryGetProperty("size", out var sz) && sz.ValueKind == JsonValueKind.Number ? sz.GetInt64() : 0,
                    Sha256 = digest.StartsWith("sha256:", StringComparison.OrdinalIgnoreCase) ? digest.Substring(7).ToLowerInvariant() : "",
                };
            }
            return best == null || best.Url == "" ? null : best;
        }

        static string Str(JsonElement e, string name) =>
            e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() ?? "" : "";

        static bool Bool(JsonElement e, string name) =>
            e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.True;
    }
}
