using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text;

namespace Jarvis.Core
{
    // Utilidades de texto en español: sin tildes, en minúsculas, números en palabras…
    public static class Text
    {
        public static char Fold(char c)
        {
            switch (c)
            {
                case 'á': case 'à': case 'ä': case 'â': case 'ã': return 'a';
                case 'é': case 'è': case 'ë': case 'ê': return 'e';
                case 'í': case 'ì': case 'ï': case 'î': return 'i';
                case 'ó': case 'ò': case 'ö': case 'ô': case 'õ': return 'o';
                case 'ú': case 'ù': case 'ü': case 'û': return 'u';
                case 'ñ': return 'n';
                case 'ç': return 'c';
            }
            return c;
        }

        // Minúsculas y sin tildes, conservando la longitud (las posiciones casan con el original).
        public static string FoldText(string s)
        {
            var sb = new StringBuilder(s.Length);
            foreach (char ch in s) sb.Append(Fold(char.ToLowerInvariant(ch)));
            return sb.ToString();
        }

        // Como FoldText, pero los signos pasan a espacio.
        public static string Normalize(string s)
        {
            var sb = new StringBuilder(s.Length);
            foreach (char ch in s)
            {
                char c = Fold(char.ToLowerInvariant(ch));
                bool keep = (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || (c > 127 && char.IsLetter(c));
                sb.Append(keep ? c : ' ');
            }
            return sb.ToString();
        }

        // Normaliza y deja un solo espacio entre palabras.
        public static string Squash(string s) => string.Join(" ", Normalize(s ?? "").Split(' ', StringSplitOptions.RemoveEmptyEntries));

        public static bool IsOneOf(string w, params string[] list) => list.Contains(w);

        public static string Capitalize(string s) => string.IsNullOrEmpty(s) ? s : char.ToUpper(s[0]) + s.Substring(1);

        public static string Plural(int n, string one, string many) => n + " " + (n == 1 ? one : many);

        public static string Two(int v) => v < 10 ? "0" + v : v.ToString();

        static readonly Dictionary<string, int> Words = new Dictionary<string, int>
        {
            ["cero"] = 0, ["dos"] = 2, ["tres"] = 3, ["cuatro"] = 4, ["cinco"] = 5, ["seis"] = 6, ["siete"] = 7,
            ["ocho"] = 8, ["nueve"] = 9, ["diez"] = 10, ["once"] = 11, ["doce"] = 12, ["trece"] = 13, ["catorce"] = 14,
            ["quince"] = 15, ["dieciseis"] = 16, ["diecisiete"] = 17, ["dieciocho"] = 18, ["diecinueve"] = 19,
            ["veinte"] = 20, ["veintiuno"] = 21, ["veintiun"] = 21, ["veintiuna"] = 21, ["veintidos"] = 22, ["veintitres"] = 23,
            ["veinticuatro"] = 24, ["veinticinco"] = 25, ["veintiseis"] = 26, ["veintisiete"] = 27, ["veintiocho"] = 28,
            ["veintinueve"] = 29, ["treinta"] = 30, ["cuarenta"] = 40, ["cincuenta"] = 50, ["sesenta"] = 60, ["setenta"] = 70,
            ["ochenta"] = 80, ["noventa"] = 90, ["cien"] = 100, ["doscientos"] = 200, ["trescientos"] = 300,
            ["cuatrocientos"] = 400, ["quinientos"] = 500, ["seiscientos"] = 600, ["setecientos"] = 700,
            ["ochocientos"] = 800, ["novecientos"] = 900, ["maximo"] = 100, ["tope"] = 100, ["minimo"] = 0,
        };

        // «25», «veinticinco», «un/una/uno» (si allowUn). -1 si no es un número.
        public static int ParseNumber(string w, bool allowUn = false)
        {
            if (string.IsNullOrEmpty(w)) return -1;
            if (w.All(char.IsDigit)) return w.Length > 6 ? -1 : int.Parse(w, CultureInfo.InvariantCulture);
            if (allowUn && (w == "un" || w == "uno" || w == "una")) return 1;
            return Words.TryGetValue(w, out int n) ? n : -1;
        }

        // Número con decimales en texto: «3,5», «1.000», «1.234,5».
        public static bool TryParseDecimal(string s, out double value)
        {
            value = 0;
            if (string.IsNullOrWhiteSpace(s)) return false;
            string t = s.Trim();
            int comma = t.LastIndexOf(','), dot = t.LastIndexOf('.');
            if (comma >= 0 && dot >= 0)
            {
                if (comma > dot) t = t.Replace(".", "").Replace(',', '.');
                else t = t.Replace(",", "");
            }
            else if (comma >= 0) t = (t.Length - comma - 1 == 3 && t.IndexOf(',') == comma && comma <= 3) ? t.Replace(",", "") : t.Replace(',', '.');
            else if (dot >= 0 && t.Length - dot - 1 == 3 && t.Count(ch => ch == '.') >= 1 && t.Split('.').Skip(1).All(p => p.Length == 3)) t = t.Replace(".", "");
            return double.TryParse(t, NumberStyles.Float, CultureInfo.InvariantCulture, out value);
        }

        // 1234.5 → «1.234,5» (como se escribe en español).
        public static string Num(double v, int maxDecimals = 2)
        {
            var nf = (NumberFormatInfo)CultureInfo.GetCultureInfo("es-CO").NumberFormat.Clone();
            nf.NumberDecimalSeparator = ",";
            nf.NumberGroupSeparator = ".";
            string fmt = "#,0." + new string('#', Math.Max(0, maxDecimals));
            if (Math.Abs(v) < 10000 && Math.Abs(v - Math.Round(v)) < 1e-9) return ((long)Math.Round(v)).ToString(CultureInfo.InvariantCulture);
            return v.ToString(fmt, nf);
        }

        public static int CountWords(string s) => s.Split((char[])null, StringSplitOptions.RemoveEmptyEntries).Length;

        public static string Preview(string s, int n = 70)
        {
            string t = (s ?? "").Replace('\r', ' ').Replace('\n', ' ').Replace('\t', ' ').Trim();
            return t.Length > n ? t.Substring(0, n) + "…" : t;
        }
    }

    // Una palabra de la orden: normalizada y su posición en el texto original.
    public struct Tok
    {
        public string W;
        public int B, E;
    }

    // La orden ya partida en palabras.
    public sealed class Cmd
    {
        public string Orig = "";
        public List<Tok> T = new List<Tok>();

        public int Size => T.Count;
        public string W(int i) => i >= 0 && i < T.Count ? T[i].W : "";
        public int Find(string w, int from = 0)
        {
            for (int i = Math.Max(0, from); i < T.Count; i++) if (T[i].W == w) return i;
            return -1;
        }
        public bool Has(string w) => Find(w) >= 0;
        public bool HasAny(params string[] ws) => ws.Any(Has);
        public int FindAny(string[] ws, int from = 0)
        {
            for (int i = Math.Max(0, from); i < T.Count; i++) if (ws.Contains(T[i].W)) return i;
            return -1;
        }
        public string Join(int from, int to = -1)
        {
            if (to < 0 || to > T.Count) to = T.Count;
            return string.Join(" ", T.Skip(from).Take(Math.Max(0, to - from)).Select(t => t.W));
        }
        // El trozo del texto original (con mayúsculas y tildes).
        public string OrigFrom(int from, int to = -1)
        {
            if (to < 0 || to > T.Count) to = T.Count;
            if (from < 0 || from >= to) return "";
            int b = T[from].B, e = T[to - 1].E;
            return Orig.Substring(b, Math.Min(e, Orig.Length) - b).Trim();
        }
        public int FindNumber(int from, bool allowUn = false)
        {
            for (int i = Math.Max(0, from); i < T.Count; i++) if (Text.ParseNumber(T[i].W, allowUn) >= 0) return i;
            return -1;
        }
        public string All => " " + Join(0) + " ";
        public bool Contains(string phrase) => All.Contains(" " + phrase + " ");

        public Cmd Clone() => new Cmd { Orig = Orig, T = new List<Tok>(T) };

        static readonly string[] LeadFillers =
        {
            "oye", "hey", "ey", "hola", "porfa", "porfavor", "porfis", "please", "puedes", "podrias", "puede", "podria", "quiero",
            "quisiera", "necesito", "me", "gustaria", "vale", "bueno", "oiga", "mire", "parce", "parcero", "mijo", "mija", "amigo", "amiga",
            "ahora", "entonces", "pues", "y", "ok", "okay", "listo", "dale", "eh", "mmm", "em", "luego", "despues", "tambien",
        };

        // Frases de cortesía de varias palabras al principio («me haces el favor de…», «será que…»).
        static readonly string[][] LeadPhrases =
        {
            new[] { "me", "haces", "el", "favor", "de" }, new[] { "hazme", "el", "favor", "de" }, new[] { "haz", "el", "favor", "de" },
            new[] { "hagame", "el", "favor", "de" }, new[] { "me", "hace", "el", "favor", "de" }, new[] { "sera", "que", "puedes" },
            new[] { "sera", "que", "me" }, new[] { "sera", "que" }, new[] { "seria", "posible" }, new[] { "es", "posible" }, new[] { "te", "pido", "que" },
            new[] { "le", "pido", "que" }, new[] { "ayudame", "a" }, new[] { "me", "ayudas", "a" }, new[] { "me", "ayudarias", "a" },
            new[] { "por", "fa" }, new[] { "por", "fis" }, new[] { "tu", "puedes" }, new[] { "usted", "puede" }, new[] { "vas", "a" }, new[] { "vamos", "a" },
            new[] { "lo", "que", "quiero", "es" }, new[] { "una", "pregunta" }, new[] { "una", "cosa" },
        };

        // Cómo se dice de verdad → la forma que entiende el motor («ábreme», «me pones», «podrías cerrar» → «abre», «pon», «cierra»).
        static readonly Dictionary<string, string> Canon = BuildCanon();

        static Dictionary<string, string> BuildCanon()
        {
            var d = new Dictionary<string, string>();
            void Map(string to, params string[] from)
            {
                foreach (var f in from) d[f] = to;
            }
            Map("abre", "abreme", "abrime", "abrir", "abrirme", "abres", "abris", "abra", "abrame", "abrela", "abrelo");
            Map("pon", "ponme", "poneme", "poner", "ponerme", "pones", "ponga", "pongame", "colocame", "coloca", "colocar", "coloque", "ponle", "ponerle");
            Map("cierra", "cierrame", "cerrar", "cerrarme", "cierras", "cierre", "cierrela", "cierrelo");
            Map("sube", "subeme", "subele", "subir", "subirle", "subes", "suba", "subale", "subemele");
            Map("baja", "bajame", "bajale", "bajar", "bajarle", "bajas", "baje", "bajele", "bajamele");
            Map("busca", "buscame", "buscar", "buscarme", "buscas", "busque", "busqueme", "buscale");
            Map("reproduce", "reproduceme", "reproducir", "reproduces", "reproduzca");
            Map("pausa", "pausar", "pausas", "pause", "pausame", "pausalo", "pausala");
            Map("apaga", "apagar", "apagas", "apague", "apagame");
            Map("bloquea", "bloquear", "bloqueas", "bloquee", "bloqueame");
            Map("silencia", "silenciar", "silencias", "silencie", "mutear", "mutealo");
            Map("quita", "quitar", "quitame", "quitas", "quite", "quitale");
            Map("muestrame", "mostrar", "mostrarme", "muestras", "muestre", "muestreme", "ensenar", "ensenarme", "ensename", "enseneme");
            Map("dime", "decir", "decirme", "dices", "dirias", "diga", "digame", "regalame", "regaleme", "regalas", "regala", "cuentame", "contarme", "cuentas");
            Map("minimiza", "minimizar", "minimizas", "minimice", "minimizame");
            Map("maximiza", "maximizar", "maximizas", "maximice", "maximizame");
            Map("escribe", "escribir", "escribeme", "escribes", "escriba", "escribirme");
            Map("toma", "tomar", "tome");
            Map("anota", "anotar", "anotame", "anote");
            Map("apunta", "apuntar", "apuntame", "apunte");
            Map("recuerdame", "recordarme", "recuerdeme", "recordar");
            Map("avisame", "avisarme", "aviseme", "avisas", "avisa");
            Map("despiertame", "despertarme", "despierteme");
            Map("lanza", "lanzar", "lanzame", "lance");
            Map("inicia", "iniciar", "iniciame", "inicie");
            Map("ejecuta", "ejecutar", "ejecutame", "ejecute");
            Map("llevame", "llevarme", "lleveme");
            Map("activa", "activar", "activame", "active", "prende", "prender", "prendeme", "enciende", "encender");
            Map("desactiva", "desactivar", "desactive");
            Map("limpia", "limpiar", "limpiame", "limpie");
            Map("vacia", "vaciar", "vaciame", "vacie");
            Map("calcula", "calcular", "calculame", "calcule");
            Map("traduce", "traducir", "traduceme", "traduzca");
            Map("genera", "generar", "generame", "genere");
            Map("lee", "leer", "leeme", "lea", "leame");
            Map("haz", "hacer", "hazme", "haga", "hagame");
            Map("cambia", "cambiar", "cambiame", "cambie");
            Map("guarda", "guardar", "guardame", "guarde");
            Map("copia", "copiar", "copiame", "copie");
            Map("pega", "pegar", "pegame", "pegue");
            Map("elige", "elegir", "escoger", "escoge", "escojas");
            Map("cuenta", "contar");
            Map("reinicia", "reiniciar", "reinicie");
            Map("suspende", "suspender", "suspenda");
            Map("salta", "saltar", "saltate");
            Map("siguiente", "proxima", "proximo");
            // Subjuntivo tras «quiero que…», «necesito que…»: «que me recuerdes», «que apagues».
            d["abras"] = "abre";
            d["pongas"] = "pon";
            d["cierres"] = "cierra";
            d["subas"] = "sube";
            d["bajes"] = "baja";
            d["busques"] = "busca";
            d["reproduzcas"] = "reproduce";
            d["pauses"] = "pausa";
            d["apagues"] = "apaga";
            d["bloquees"] = "bloquea";
            d["silencies"] = "silencia";
            d["quites"] = "quita";
            d["muestres"] = "muestrame";
            d["digas"] = "dime";
            d["minimices"] = "minimiza";
            d["maximices"] = "maximiza";
            d["escribas"] = "escribe";
            d["tomes"] = "toma";
            d["anotes"] = "anota";
            d["apuntes"] = "apunta";
            d["recuerdes"] = "recuerdame";
            d["avises"] = "avisame";
            d["despiertes"] = "despiertame";
            d["lances"] = "lanza";
            d["inicies"] = "inicia";
            d["ejecutes"] = "ejecuta";
            d["lleves"] = "llevame";
            d["actives"] = "activa";
            d["desactives"] = "desactiva";
            d["limpies"] = "limpia";
            d["vacies"] = "vacia";
            d["calcules"] = "calcula";
            d["traduzcas"] = "traduce";
            d["generes"] = "genera";
            d["leas"] = "lee";
            d["hagas"] = "haz";
            d["cambies"] = "cambia";
            d["guardes"] = "guarda";
            d["copies"] = "copia";
            d["pegues"] = "pega";
            d["reinicies"] = "reinicia";
            d["suspendas"] = "suspende";
            d["cuentes"] = "dime";
            d["prendas"] = "activa";
            // De usted («¿me pone…?», «¿me dice…?») y subjuntivo pasado («quisiera que pusieras música»).
            d["pone"] = "pon";
            d["dice"] = "dime";
            foreach (var (to, forms) in new[]
            {
                ("pon", new[] { "pusieras", "pusiera" }), ("abre", new[] { "abrieras", "abriera" }), ("cierra", new[] { "cerraras", "cerrara" }),
                ("sube", new[] { "subieras", "subiera" }), ("baja", new[] { "bajaras", "bajara" }), ("busca", new[] { "buscaras", "buscara" }),
                ("apaga", new[] { "apagaras", "apagara" }), ("recuerdame", new[] { "recordaras", "recordara" }), ("dime", new[] { "dijeras", "dijera" }),
                ("reproduce", new[] { "reprodujeras", "reprodujera" }), ("avisame", new[] { "avisaras", "avisara" }), ("muestrame", new[] { "mostraras", "mostrara" }),
            })
                foreach (var f in forms) d[f] = to;
            return d;
        }

        static void Canonize(List<Tok> t, int i)
        {
            if (i < 0 || i >= t.Count) return;
            if (Canon.TryGetValue(t[i].W, out string to)) t[i] = new Tok { W = to, B = t[i].B, E = t[i].E };
        }

        public static Cmd Parse(string text)
        {
            var c = new Cmd { Orig = text ?? "" };
            string n = Text.Normalize(c.Orig);
            int i = 0;
            while (i < n.Length)
            {
                while (i < n.Length && n[i] == ' ') i++;
                int b = i;
                while (i < n.Length && n[i] != ' ') i++;
                if (i > b) c.T.Add(new Tok { W = n.Substring(b, i - b), B = b, E = i });
            }
            MergeNumbers(c.T);
            // Cortesías y muletillas al principio y al final.
            bool changed = true;
            while (changed && c.T.Count > 1)
            {
                changed = false;
                if (c.T.Count > 2 && c.T[0].W == "por" && c.T[1].W == "favor") { c.T.RemoveRange(0, 2); changed = true; continue; }
                foreach (var ph in LeadPhrases)
                {
                    if (c.T.Count <= ph.Length) continue;
                    bool m = true;
                    for (int k = 0; k < ph.Length && m; k++) m = c.T[k].W == ph[k];
                    if (!m) continue;
                    c.T.RemoveRange(0, ph.Length);
                    changed = true;
                    break;
                }
                if (changed) continue;
                string w = c.T[0].W;
                if (LeadFillers.Contains(w))
                {
                    c.T.RemoveAt(0);
                    changed = true;
                    if ((w == "quiero" || w == "quisiera" || w == "necesito" || w == "gustaria") && c.T.Count > 1 && c.T[0].W == "que") c.T.RemoveAt(0);
                }
            }
            changed = true;
            while (changed && c.T.Count > 1)
            {
                changed = false;
                int s = c.T.Count;
                if (s > 2 && c.T[s - 2].W == "por" && c.T[s - 1].W == "favor") { c.T.RemoveRange(s - 2, 2); changed = true; continue; }
                // «gracias» al final se quita solo si queda una orden («abre Spotify, gracias»): «muchas gracias» o «perfecto, gracias» se quedan enteras.
                if (c.T[s - 1].W == "gracias" && s > 2 && !Text.IsOneOf(c.T[s - 2].W, "muchas", "mil", "muchisimas")) { c.T.RemoveAt(s - 1); changed = true; }
                else if (Text.IsOneOf(c.T[s - 1].W, "porfa", "porfis", "please", "ya", "parce", "porfavor", "pues", "si", "listo", "ok")) { c.T.RemoveAt(s - 1); changed = true; }
                else if (s > 2 && c.T[s - 2].W == "por" && (c.T[s - 1].W == "fa" || c.T[s - 1].W == "fis")) { c.T.RemoveRange(s - 2, 2); changed = true; }
            }
            // Formas coloquiales del verbo, al principio y tras «y», «luego»… (para las órdenes encadenadas).
            Canonize(c.T, 0);
            for (int k = 1; k + 1 < c.T.Count; k++)
                if (Text.IsOneOf(c.T[k].W, "y", "luego", "despues", "tambien", "e")) Canonize(c.T, k + 1);
            // «me pones la música» → tras quitar «me», «pones» ya es «pon»; «la puedes abrir» → «abre la»
            return c;
        }

        // «treinta y cinco» → «35», «ciento veinte» → «120».
        static void MergeNumbers(List<Tok> t)
        {
            int Unit(string w) => (w == "un" || w == "uno" || w == "una") ? 1 : (!char.IsDigit(w[0]) && Text.ParseNumber(w) is int n && n >= 1 && n <= 9) ? n : -1;
            int Tens(string w) => (!char.IsDigit(w[0]) && w != "maximo" && w != "tope" && Text.ParseNumber(w) is int n && n >= 30 && n <= 90 && n % 10 == 0) ? n : -1;
            for (int i = 0; i + 2 < t.Count; i++)
            {
                int d = Tens(t[i].W), u = t[i + 1].W == "y" ? Unit(t[i + 2].W) : -1;
                if (d > 0 && u > 0)
                {
                    t[i] = new Tok { W = (d + u).ToString(), B = t[i].B, E = t[i + 2].E };
                    t.RemoveRange(i + 1, 2);
                }
            }
            for (int i = 0; i + 1 < t.Count; i++)
            {
                string w = t[i].W;
                int h = w == "ciento" ? 100 : (!char.IsDigit(w[0]) ? Text.ParseNumber(w) : -1);
                if (h < 100 || h % 100 != 0 || h > 900 || w == "cien") continue;
                int r = Text.ParseNumber(t[i + 1].W, true);
                if (r >= 1 && r <= 99 && !Text.IsOneOf(t[i + 1].W, "maximo", "tope", "minimo"))
                {
                    t[i] = new Tok { W = (h + r).ToString(), B = t[i].B, E = t[i + 1].E };
                    t.RemoveAt(i + 1);
                }
            }
        }
    }
}
