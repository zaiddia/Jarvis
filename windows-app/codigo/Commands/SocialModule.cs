using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;
using Jarvis.Core;

namespace Jarvis.Commands
{
    // Charla con sentido: cómo se siente el usuario, adivinanzas, trabalenguas, ánimo, deletrear,
    // y Wikipedia para saber qué es algo (sin IA o cuando se pide expresamente).
    public sealed class SocialModule
    {
        readonly Engine E;
        static readonly HttpClient Http = Net.Create(TimeSpan.FromSeconds(10));
        public SocialModule(Engine e) { E = e; }
        string Sir => E.Sir;
        static string Pick(params string[] o) => TalkModule.Pick(o);

        bool AiReady => E.S.AiProvider == "ollama" || E.S.ApiKey.Trim() != "" || (E.S.AiProvider == "openai" && E.S.ApiUrl.Trim() != "");

        // ---------------------------------------------------------------- cómo se siente

        public string Try(Cmd c)
        {
            string s = c.Join(0);
            // ¿Está respondiendo a la adivinanza?
            if (_riddleAnswer != null && DateTime.Now < _riddleUntil && !Text.IsOneOf(s, "me rindo", "no se", "cual es la respuesta", "dime la respuesta"))
            {
                var key = Text.Squash(_riddleAnswer).Split(' ').Where(w => w.Length > 3).ToList();
                string ans = _riddleAnswer;
                if (key.Any(w => s.Contains(w)))
                {
                    _riddleAnswer = null;
                    return Pick("¡Correcto! Era " + ans + ".", "¡Muy bien" + Sir + "! " + Text.Capitalize(ans) + ".", "Exacto, " + ans + ". Es usted bueno con esto.");
                }
                if (c.Size <= 4)
                {
                    _riddleAnswer = null;
                    return "Casi, pero no. Era " + ans + ". ¿Otra?";
                }
            }
            // «estoy cansado», «me siento triste», «tengo hambre»…
            string feel = s.StartsWith("estoy ") ? s.Substring(6) : s.StartsWith("siento ") ? s.Substring(7) : s.StartsWith("me siento ") ? s.Substring(10) : s.StartsWith("ando ") ? s.Substring(5) : "";
            feel = feel.Replace("muy ", "").Replace("un poco ", "").Replace("bastante ", "").Trim();
            if (feel != "" && Text.CountWords(feel) <= 3)
            {
                string r = Feeling(feel);
                if (r != null) return r;
            }
            if (Text.IsOneOf(s, "tengo hambre", "que hambre", "me muero de hambre"))
                return Pick("¿Le busco recetas o un domicilio cerca" + Sir + "?", "Hora de un buen bocado. ¿Quiere que le busque algo rápido de preparar?");
            if (Text.IsOneOf(s, "tengo sueno", "que sueno", "me muero de sueno"))
                return Pick("Quizá sea buen momento para un descanso. ¿Le pongo una alarma para una siesta de veinte minutos?", "Un café o una siesta corta. Si quiere, le aviso en veinte minutos.");
            if (Text.IsOneOf(s, "tengo frio", "que frio", "hace frio aqui"))
                return "Abríguese bien" + Sir + ". ¿Quiere que le diga el tiempo de hoy?";
            if (Text.IsOneOf(s, "tengo calor", "que calor", "hace calor aqui"))
                return "Un vaso de agua fría no vendría mal. ¿Le digo la temperatura de afuera?";
            if (Text.IsOneOf(s, "buenas noches", "me voy a dormir", "me voy a acostar", "hasta manana") && DateTime.Now.Hour >= 19)
                return Pick("Que descanse" + Sir + ". ¿Le pongo una alarma para mañana?", "Buenas noches" + Sir + ". Aquí estaré mañana.");
            if (Text.IsOneOf(s, "lo siento", "perdon", "disculpa", "perdoname", "me equivoque"))
                return Pick("No pasa nada" + Sir + ".", "Tranquilo, sin problema.", "Todo bien. ¿Seguimos?");
            if (Text.IsOneOf(s, "no te entiendo", "no me entiendes", "no entiendes nada", "eres tonto", "eres tonta", "que torpe"))
                return "Disculpe" + Sir + ", a veces el micrófono me juega malas pasadas. Pruebe a decirlo de otra forma, más cerca del micrófono, o escríbamelo con " + E.S.Hotkey + ".";
            if (Text.IsOneOf(s, "estas ahi jarvis", "estas ahi viernes", "sigues despierto", "sigues despierta", "estas despierto", "estas despierta"))
                return Pick("Siempre" + Sir + ".", "Aquí sigo.");
            if (Text.IsOneOf(s, "cuantos anos tienes", "que edad tienes", "cuando naciste"))
                return "Mi versión actual nació en 2026" + Sir + ". En años de inteligencia artificial, eso ya es bastante experiencia.";
            if (Text.IsOneOf(s, "tienes sentimientos", "eres real", "estas vivo", "estas viva", "eres humano", "eres humana"))
                return "Soy un programa, pero uno que se toma muy en serio cuidarle" + Sir + ".";
            if (Text.IsOneOf(s, "que haces", "que estas haciendo", "en que andas"))
                return Pick("Vigilando que todo funcione en su equipo. ¿Necesita algo?", "Esperando sus órdenes" + Sir + ".");

            // ---- entretenimiento
            if (c.HasAny("adivinanza", "adivinanzas", "acertijo", "acertijos"))
                return Riddle();
            if (c.HasAny("trabalenguas"))
                return TalkModule.PickFresh("trabalenguas", Twisters);
            if (c.Contains("frase motivadora") || c.Contains("frase de motivacion") || c.Contains("animame") || c.Contains("dame animo") || c.Contains("motivame") || c.Contains("una frase bonita"))
                return TalkModule.PickFresh("animo", Motivation);
            if (c.Contains("dame un consejo") || c.Contains("un consejo") && c.HasAny("dame", "dime"))
                return TalkModule.PickFresh("consejos", Tips);
            if (Text.IsOneOf(s, "cual es la respuesta", "no se", "me rindo", "dime la respuesta", "cual era") && _riddleAnswer != null)
            {
                string a = _riddleAnswer;
                _riddleAnswer = null;
                return "La respuesta es: " + a + ".";
            }

            // ---- deletrear: «cómo se escribe ferrocarril», «deletrea Bogotá»
            int k = -1;
            if (c.Contains("como se escribe")) k = c.Find("escribe") + 1;
            else if (c.W(0) == "deletrea" || c.W(0) == "deletreame") k = 1;
            if (k > 0 && k < c.Size)
            {
                string word = c.OrigFrom(k).Trim(' ', '?', '¿', '.', '«', '»');
                if (word != "" && Text.CountWords(word) <= 3)
                {
                    var letters = word.Where(ch => !char.IsWhiteSpace(ch)).Select(ch => char.ToUpper(ch).ToString());
                    E.Host.Show(word + "\n" + string.Join(" · ", letters));
                    return Text.Capitalize(word) + " se escribe: " + string.Join(", ", letters) + ".";
                }
            }
            return null;
        }

        string Feeling(string f)
        {
            if (Text.IsOneOf(f, "cansado", "cansada", "agotado", "agotada", "muerto", "muerta", "rendido", "rendida"))
                return Pick("Ha sido un día largo, ¿verdad? Tómese un respiro" + Sir + ". Si quiere, le pongo música tranquila.",
                            "Descansar también es productivo. ¿Le aviso en quince minutos para retomar?");
            if (Text.IsOneOf(f, "triste", "mal", "deprimido", "deprimida", "bajoneado", "bajoneada", "desanimado", "desanimada", "solo", "sola"))
                return Pick("Lamento oír eso" + Sir + ". Si quiere hablar, aquí estoy; y si le ayuda, le pongo su música favorita o le cuento algo para distraerse.",
                            "Siento que esté así. A veces ayuda salir a caminar un poco o llamar a alguien de confianza. ¿Quiere que le acompañe con algo de música?");
            if (Text.IsOneOf(f, "estresado", "estresada", "nervioso", "nerviosa", "ansioso", "ansiosa", "agobiado", "agobiada"))
                return "Respire hondo conmigo" + Sir + ": inspire contando hasta cuatro, sostenga cuatro y suelte en cuatro. ¿Le pongo un temporizador de cinco minutos para una pausa?";
            if (Text.IsOneOf(f, "feliz", "contento", "contenta", "alegre", "bien", "de maravilla", "genial", "excelente", "super bien"))
                return Pick("¡Me alegra mucho" + Sir + "! ¿Celebramos con algo de música?", "Qué buena noticia. Así da gusto trabajar.");
            if (Text.IsOneOf(f, "aburrido", "aburrida"))
                return Pick("Puedo contarle un chiste, una adivinanza o un dato curioso. Usted elige.", "¿Una adivinanza? Diga «cuéntame una adivinanza».");
            if (Text.IsOneOf(f, "enfermo", "enferma", "resfriado", "resfriada"))
                return "Cuídese mucho" + Sir + ". Beba líquidos y descanse; si quiere, le recuerdo tomar la medicina.";
            if (Text.IsOneOf(f, "enojado", "enojada", "molesto", "molesta", "bravo", "brava", "furioso", "furiosa"))
                return "Entiendo" + Sir + ". Respire un momento; si quiere desahogarse, le escucho.";
            return null;
        }

        static readonly (string q, string a)[] Riddles =
        {
            ("Blanco por dentro, verde por fuera. Si quieres que te lo diga, espera.", "la pera"),
            ("Tiene dientes y no come, tiene cabeza y no es hombre.", "el ajo"),
            ("Oro parece, plata no es. ¿Qué es?", "el plátano"),
            ("Cuanto más le quitas, más grande es.", "un agujero"),
            ("Vuela sin alas, silba sin boca, pega sin manos y no se ve.", "el viento"),
            ("Tiene agujas y no sabe coser, tiene números y no sabe leer.", "el reloj"),
            ("Mientras más se seca, más se moja.", "la toalla"),
            ("Lleva su casa a cuestas y deja un camino de plata.", "el caracol"),
            ("Si me nombras, desaparezco.", "el silencio"),
            ("Tiene ojos y no ve, tiene agua y no la bebe, tiene carne y no la come, tiene barba y no es hombre.", "el coco"),
            ("Una señorita muy aseñorada, siempre va en coche y siempre está mojada.", "la lengua"),
            ("Cien amigos tengo, todos en una tabla; si no los tocas, no te dicen nada.", "las teclas del piano"),
        };

        string _riddleAnswer;
        DateTime _riddleUntil;

        string Riddle()
        {
            var used = Store.Get("adivinanzas", new List<int>());
            var free = Enumerable.Range(0, Riddles.Length).Where(i => !used.Contains(i)).ToList();
            if (free.Count == 0) { used.Clear(); free = Enumerable.Range(0, Riddles.Length).ToList(); }
            int k = free[new Random().Next(free.Count)];
            used.Add(k);
            Store.Set("adivinanzas", used);
            _riddleAnswer = Riddles[k].a;
            _riddleUntil = DateTime.Now.AddMinutes(2);
            E.ExpectReply();
            return Riddles[k].q + " Si se rinde, diga «me rindo».";
        }

        static readonly string[] Twisters =
        {
            "Tres tristes tigres tragaban trigo en un trigal.",
            "Pablito clavó un clavito. ¿Qué clavito clavó Pablito?",
            "El perro de San Roque no tiene rabo porque Ramón Rodríguez se lo ha robado.",
            "Como poco coco como, poco coco compro.",
            "Erre con erre cigarro, erre con erre barril, rápido ruedan los carros cargados de azúcar del ferrocarril.",
            "Pepe Pecas pica papas con un pico, con un pico pica papas Pepe Pecas.",
            "Si Pancha plancha con cuatro planchas, ¿con cuántas planchas plancha Pancha?",
        };

        static readonly string[] Motivation =
        {
            "No tiene que ser perfecto; tiene que estar hecho. Paso a paso se llega lejos.",
            "Cada experto fue alguna vez un principiante. Siga adelante.",
            "La disciplina es elegir entre lo que quiere ahora y lo que más quiere.",
            "Hoy es un buen día para avanzar un poco. Un poco ya es mucho.",
            "Los grandes cambios empiezan con decisiones pequeñas.",
            "Usted ha superado días difíciles antes; este no será la excepción.",
            "El éxito es la suma de pequeños esfuerzos repetidos día tras día.",
        };

        static readonly string[] Tips =
        {
            "Cada hora, levántese un par de minutos y mire a lo lejos: su espalda y sus ojos se lo agradecerán.",
            "Divida las tareas grandes en pasos de veinticinco minutos. Puedo ponerle un pomodoro si quiere.",
            "Beba agua con frecuencia; muchas veces el cansancio es solo sed.",
            "Antes de dormir, aleje las pantallas media hora: descansará mejor.",
            "Apunte las tres cosas más importantes del día y empiece por la más difícil.",
            "Haga copias de seguridad de sus archivos importantes; el día que las necesite, lo agradecerá.",
        };

        // ---------------------------------------------------------------- Wikipedia

        public async Task<string> TryAsync(Cmd c)
        {
            string s = c.Join(0);
            bool explicitWiki = c.Has("wikipedia") && !c.HasAny("abre", "busca", "buscame", "abreme");
            string topic = null;
            if (explicitWiki)
            {
                int k = c.Find("de");
                if (k < 0) k = c.Find("sobre");
                topic = k >= 0 ? c.OrigFrom(k + 1) : null;
                if (topic == null)
                {
                    var words = c.T.Select(t => t.W).ToList();
                    int w = words.IndexOf("wikipedia");
                    topic = w + 1 < c.Size ? c.OrigFrom(w + 1) : null;
                }
            }
            else if (!AiReady)
            {
                // Sin IA: «¿qué es la fotosíntesis?», «¿quién fue Simón Bolívar?»
                foreach (var pre in new[] { "que es un ", "que es una ", "que es el ", "que es la ", "que es ", "que son los ", "que son las ", "que son ",
                                            "quien es ", "quien fue ", "quienes son ", "quienes fueron ", "dime de ", "dime sobre ", "hablame de ", "hablame sobre " })
                    if (s.StartsWith(pre))
                    {
                        topic = c.OrigFrom(Text.CountWords(pre.Trim()));
                        break;
                    }
            }
            if (string.IsNullOrWhiteSpace(topic)) return null;
            topic = topic.Trim(' ', '?', '¿', '.', '!', '¡');
            foreach (var art in new[] { "el ", "la ", "los ", "las ", "un ", "una " })
                if (topic.StartsWith(art, StringComparison.OrdinalIgnoreCase)) topic = topic.Substring(art.Length);
            if (topic.Length < 2) return null;
            try
            {
                string search = "https://es.wikipedia.org/w/api.php?action=opensearch&limit=1&namespace=0&format=json&search=" + Uri.EscapeDataString(topic);
                using var sdoc = JsonDocument.Parse(await Http.GetStringAsync(search));
                var titles = sdoc.RootElement[1];
                if (titles.GetArrayLength() == 0) return explicitWiki ? "No encuentro «" + topic + "» en Wikipedia" + Sir + "." : null;
                string title = titles[0].GetString();
                string url = "https://es.wikipedia.org/api/rest_v1/page/summary/" + Uri.EscapeDataString(title.Replace(' ', '_'));
                using var doc = JsonDocument.Parse(await Http.GetStringAsync(url));
                string extract = doc.RootElement.TryGetProperty("extract", out var ex) ? ex.GetString() ?? "" : "";
                if (extract == "") return null;
                E.Host.Show(title + "\n\n" + extract);
                // Las dos primeras frases, para decirlo en voz alta.
                var sentences = System.Text.RegularExpressions.Regex.Split(extract, @"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡])");
                string spoken = string.Join(" ", sentences.Take(2));
                if (spoken.Length > 420) spoken = spoken.Substring(0, 420) + "…";
                return "Según Wikipedia: " + spoken;
            }
            catch (Exception e)
            {
                Log.Write("Wikipedia: " + e.Message);
                return explicitWiki ? "No pude consultar Wikipedia ahora" + Sir + "." : null;
            }
        }
    }
}
