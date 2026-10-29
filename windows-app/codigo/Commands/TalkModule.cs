using System;
using System.Collections.Generic;
using System.Linq;
using Jarvis.Core;

namespace Jarvis.Commands
{
    // Control del asistente y conversación corta (saludos, chistes, monedas…).
    public sealed class TalkModule
    {
        readonly Engine E;
        static readonly Random Rnd = new Random();
        public TalkModule(Engine e) { E = e; }

        string Sir => E.Sir;

        public static string Pick(params string[] options) => options[Rnd.Next(options.Length)];

        // Elige sin repetir hasta agotar la lista (se recuerda entre sesiones).
        public static string PickFresh(string key, IReadOnlyList<string> list)
        {
            var used = Store.Get(key, new List<int>());
            var free = Enumerable.Range(0, list.Count).Where(i => !used.Contains(i)).ToList();
            if (free.Count == 0)
            {
                used.Clear();
                free = Enumerable.Range(0, list.Count).ToList();
            }
            int k = free[Rnd.Next(free.Count)];
            used.Add(k);
            Store.Set(key, used);
            return list[k];
        }

        public string Ack() => Pick("Hecho" + Sir + ".", "Listo.", "Enseguida" + Sir + ".", "Hecho.", "A la orden" + Sir + ".");

        public string Control(Cmd c)
        {
            string s = c.Join(0);
            if (Text.IsOneOf(s, "callate", "silencio", "para", "basta", "deten", "detente", "stop", "shh", "ya esta", "suficiente", "calla", "para de hablar", "deja de hablar"))
            {
                E.Host.StopSpeaking();
                return Engine.Quiet;
            }
            if (Text.IsOneOf(s, "cancela", "cancelar", "nada", "olvidalo", "dejalo", "no importa", "nada nada", "ninguna"))
                return Pick("De acuerdo.", "Entendido" + Sir + ".", "Sin problema.");
            if (Text.IsOneOf(s, "deja de escuchar", "no escuches", "desactiva el microfono", "modo silencio", "no me escuches", "duermete", "a dormir", "descansa"))
            {
                E.Host.SetListening(false);
                return "Dejo de escuchar" + Sir + ". Pulse " + E.S.Hotkey + " cuando me necesite.";
            }
            if (Text.IsOneOf(s, "escucha", "vuelve a escuchar", "activa el microfono", "despierta", "escuchame"))
            {
                E.Host.SetListening(true);
                return "Le escucho" + Sir + ".";
            }
            if (Text.IsOneOf(s, "adios", "hasta luego", "chao", "nos vemos", "hasta pronto", "eso es todo", "gracias eso es todo", "nada mas", "es todo"))
            {
                E.Host.HidePanel();
                return Pick("Aquí estaré" + Sir + ".", "Hasta luego" + Sir + ".", "Cuando me necesite" + Sir + ".");
            }
            if (Text.IsOneOf(s, "abre los ajustes", "abre tus ajustes", "abre la configuracion", "tus ajustes", "configuracion de jarvis", "ajustes de jarvis",
                             "abre la configuracion de jarvis", "abre tu configuracion", "configurate", "ajustes"))
            {
                E.Host.OpenSettings();
                return "Abro mis ajustes" + Sir + ".";
            }
            if (Text.IsOneOf(s, "cierrate", "apagate", "sal", "cierra jarvis", "apaga jarvis", "salir de jarvis", "cierra viernes", "apaga viernes"))
            {
                E.Ask("¿Quiere que me cierre del todo" + Sir + "?", yes =>
                {
                    if (!yes) return "Sigo aquí.";
                    E.Host.Quit();
                    return "Hasta pronto" + Sir + ".";
                });
                return "¿Quiere que me cierre del todo" + Sir + "?";
            }
            if (Text.IsOneOf(s, "ayuda", "que puedes hacer", "que sabes hacer", "como funcionas", "que te puedo pedir", "que puedo decirte", "que mas puedes hacer", "dime que sabes hacer"))
            {
                E.Host.Show(
                    "• Programas, páginas, carpetas y ajustes de Windows: «abre Spotify», «cierra Chrome»\n" +
                    "• Volumen y música: «sube el volumen», «baja Spotify», «¿qué suena?», «pon salsa»\n" +
                    "• Hora, fecha, el tiempo, noticias, monedas: «¿va a llover?», «¿cuántos pesos son 50 dólares?»\n" +
                    "• Temporizadores, alarmas y recordatorios, también repetidos: «recuérdame todos los días a las 8 la pastilla»\n" +
                    "• Agenda: «¿qué tengo hoy?»  · Notas y listas: «añade leche a la lista de la compra»\n" +
                    "• Ventanas y equipo: «minimiza», «modo oscuro», «sube el brillo», «bloquea el equipo»\n" +
                    "• Cuentas, conversiones, fechas: «¿qué día cae el 25 de diciembre?»\n" +
                    "• Charla: chistes, adivinanzas, trabalenguas, ánimo, «¿cómo se escribe…?», Wikipedia\n" +
                    "• YouTube y radio: «pon un video de Karol G», «pon la emisora La Mega»\n" +
                    "• Casa (Home Assistant): «enciende la luz de la sala», «apaga todas las luces»\n" +
                    "• Celular (ntfy): «mándame al celular la lista de la compra»  · «precio del bitcoin», «pomodoro»\n" +
                    "• Memoria: cuénteme «mi hermana se llama Ana» o «me gusta el vallenato» y lo recordaré · «¿qué sabes de mí?»\n" +
                    "• Rutinas: varias órdenes con una frase o solas a una hora (Ajustes › Rutinas) · «¿qué rutinas tengo?»\n" +
                    "• Si algo falla: «prueba completa» revisa micrófono, voz, IA e internet\n" +
                    "• Con IA (Ollama, Gemini, Claude…): cualquier pregunta, mirar la pantalla y crear rutinas hablando");
                return "Un montón de cosas" + Sir + ": abrir programas, controlar la música y el volumen, recordatorios y alarmas, el tiempo, su agenda, " +
                       "noticias, cuentas, ventanas, y conversar. Le dejo la lista en el panel. Pídamelo como le salga, con sus palabras.";
            }
            if (c.Contains("cambia a viernes") || c.Contains("activa a viernes") || c.Contains("quiero a viernes") || c.Join(0) == "a viernes" || c.Contains("modo viernes"))
                return SwitchPersona("viernes");
            if (c.Contains("cambia a jarvis") || c.Contains("vuelve jarvis") || c.Contains("quiero a jarvis") || c.Join(0) == "a jarvis" || c.Contains("modo jarvis"))
                return SwitchPersona("jarvis");
            if (Text.IsOneOf(s, "prueba completa", "haz una prueba completa", "haz la prueba completa", "revisa todo", "revisalo todo", "diagnostico completo",
                             "haz un diagnostico", "diagnosticate", "autodiagnostico", "chequeo completo", "revisa el sistema", "revisa tus sistemas", "comprueba todo",
                             "como estan tus sistemas", "estado de tus sistemas", "revisa que todo funcione", "prueba todo"))
            {
                E.Host.ShowSystemCheck();
                return Pick("Hago una prueba completa de mis sistemas" + Sir + ".", "Revisando todos los sistemas.", "Comprobando todo, un momento.");
            }
            if (Text.IsOneOf(s, "diagnostico de voz", "diagnostico del microfono", "prueba el microfono", "revisa el microfono", "no me oyes bien",
                             "por que no me oyes", "por que no me entiendes", "revisa la escucha", "prueba la escucha"))
            {
                E.Host.ShowVoiceDiagnostics();
                return Engine.Quiet;
            }
                        // Cambiar de inteligencia artificial: «usa Gemini», «cambia a Claude», «qué IA usas»
            if (Text.IsOneOf(s, "que ia usas", "que inteligencia usas", "que modelo usas", "que ia eres", "con que ia funcionas", "que modelo eres"))
            {
                string name = E.S.AiProvider == "gemini" ? "Gemini" : E.S.AiProvider == "ollama" ? "Ollama, en este equipo" : E.S.AiProvider == "openai" ? (E.S.ApiUrl.Trim() != "" ? "un servidor propio" : "OpenAI") : "Claude";
                return E.S.ApiKey.Trim() == "" && E.S.ApiUrl.Trim() == "" && E.S.AiProvider != "ollama" ? "Ahora mismo no tengo IA configurada" + Sir + "." : "Uso " + name + ", con el modelo " + E.S.EffectiveModel + ".";
            }
            if ((c.HasAny("usa", "cambia", "pasa", "pon", "activa") || c.Contains("quiero usar") || c.W(0) == "usar") && c.HasAny("gemini", "claude", "anthropic", "openai", "chatgpt", "gpt", "ollama", "local") && c.Size <= 6 && !c.Has("voz"))
            {
                string target = c.Has("gemini") ? "gemini" : c.HasAny("claude", "anthropic") ? "anthropic" : c.HasAny("ollama", "local") ? "ollama" : "openai";
                string label = target == "gemini" ? "Gemini" : target == "anthropic" ? "Claude" : target == "ollama" ? "Ollama" : "OpenAI";
                if (E.S.AiProvider == target) return "Ya estoy usando " + label + Sir + ".";
                if (target != "ollama" && (!E.S.ApiKeys.TryGetValue(target, out var k) || k.Trim() == ""))
                    if (!(target == "openai" && E.S.ApiUrl.Trim() != ""))
                    {
                        E.Host.OpenSettings();
                        return "No tengo clave de " + label + Sir + ". Le abro los ajustes: pestaña Inteligencia.";
                    }
                E.S.SwitchAi(target);
                E.Host.ApplySettings();
                return "Hecho. Ahora pienso con " + label + " (" + E.S.EffectiveModel + ").";
            }
            if (c.Contains("que voces tienes") || c.Contains("que voces hay") || c.Contains("lista de voces"))
            {
                var v = InstalledVoices();
                if (v.Count == 0) return "Solo tengo la voz de Windows" + (E.S.VoiceEngine == "cloud" ? " y la de la nube" : "") + ". Instale las voces neuronales para tener más.";
                return "Tengo estas voces: " + string.Join(", ", v.Select(VoiceLabel)) + ". Diga «cambia la voz a» y el nombre.";
            }
            if (c.Contains("cambia la voz") || c.Contains("usa la voz") || c.Contains("pon la voz") || c.Contains("cambia de voz") || c.Contains("otra voz"))
            {
                if (c.Has("windows"))
                {
                    E.S.VoiceEngine = "windows";
                    E.Host.ApplySettings();
                    return "Uso la voz de Windows.";
                }
                if (c.HasAny("nube", "openai", "elevenlabs", "azure", "gemini", "google"))
                {
                    if (c.HasAny("gemini", "google")) E.S.CloudProvider = "gemini";
                    else if (c.Has("openai")) E.S.CloudProvider = "openai";
                    else if (c.Has("elevenlabs")) E.S.CloudProvider = "elevenlabs";
                    else if (c.Has("azure")) E.S.CloudProvider = "azure";
                    E.S.VoiceEngine = "cloud";
                    E.Host.ApplySettings();
                    return "Uso la voz en la nube.";
                }
                var v = InstalledVoices();
                if (v.Count == 0) return "No hay voces neuronales instaladas" + Sir + ".";
                string pick = v.FirstOrDefault(x => c.T.Any(t => t.W.Length >= 3 && Text.Squash(x).Contains(t.W) && !Text.IsOneOf(t.W, "voz", "cambia", "pon", "usa", "la", "de", "mujer", "hombre")));
                bool woman = c.HasAny("mujer", "femenina", "chica");
                bool man = c.HasAny("hombre", "masculina", "chico");
                if (pick == null && woman) pick = v.FirstOrDefault(x => x.Contains("claude") || x.Contains("daniela") || x.Contains("sharvard"));
                if (pick == null && man) pick = v.FirstOrDefault(x => x.Contains("ald") || x.Contains("davefx") || x.Contains("carlfm") || x.Contains("sharvard"));
                if (pick == null)
                {
                    // «otra voz»: la siguiente de la lista
                    int cur = v.FindIndex(x => x == E.S.PiperVoice);
                    pick = v[(cur + 1) % v.Count];
                }
                E.S.PiperVoice = pick;
                E.S.VoiceEngine = "neural";
                if (pick.Contains("sharvard")) E.S.PiperSpeaker = woman ? 1 : 0;
                E.Host.ApplySettings();
                return "Así sueno ahora, con la voz de " + VoiceLabel(pick) + ".";
            }
            if (c.Contains("habla mas rapido") || c.Contains("mas rapido"))
                return Rate(+2);
            if (c.Contains("habla mas despacio") || c.Contains("mas despacio") || c.Contains("mas lento") || c.Contains("habla mas lento"))
                return Rate(-2);
            // «Me llamo Laura», «mi nombre es Andrés»
            if ((c.W(0) == "llamo" && c.Size >= 2 && c.Size <= 4) || c.Contains("mi nombre es"))
            {
                int k = c.W(0) == "llamo" ? 0 : c.Find("es");
                string name = c.OrigFrom(k + 1).Trim(' ', '.', ',');
                if (name != "" && Text.CountWords(name) <= 3)
                {
                    E.S.Treatment = Text.Capitalize(name);
                    E.S.Save();
                    return Pick("Mucho gusto, " + E.S.Treatment + ". Lo recordaré.", (E.S.IsViernes ? "Encantada" : "Encantado") + " de conocerle, " + E.S.Treatment + ".");
                }
            }
            if (c.Has("llamame"))
            {
                int k = c.Find("llamame");
                string name = c.OrigFrom(k + 1).Trim(' ', '.', ',');
                if (name != "")
                {
                    E.S.Treatment = name;
                    E.S.Save();
                    return "De acuerdo, " + name + ".";
                }
            }
            return null;
        }

        static List<string> InstalledVoices()
        {
            string dir = System.IO.Path.Combine(Jarvis.Speech.NeuralVoices.Dir, "voces");
            if (!System.IO.Directory.Exists(dir)) return new List<string>();
            return System.IO.Directory.GetFiles(dir, "*.onnx").Select(f => System.IO.Path.GetFileNameWithoutExtension(f)).OrderBy(x => x).ToList();
        }

        static string VoiceLabel(string stem)
        {
            var parts = stem.Split('-');
            string name = parts.Length > 1 ? Text.Capitalize(parts[1]) : stem;
            string country = stem.StartsWith("es_MX") ? "mexicana" : stem.StartsWith("es_AR") ? "argentina" : "española";
            return name + " (" + country + ")";
        }

        string SwitchPersona(string p)
        {
            E.S.Persona = p;
            if (Text.Squash(E.S.WakeWord) == "jarvis" || Text.Squash(E.S.WakeWord) == "viernes")
                E.S.WakeWord = p == "viernes" ? "Viernes" : "Jarvis";
            E.S.Save();
            E.Host.ApplySettings();
            return p == "viernes" ? "Aquí VIERNES. Llámeme por mi nombre cuando quiera." : "JARVIS de vuelta" + Sir + ".";
        }

        string Rate(int d)
        {
            E.S.VoiceRate = Math.Clamp(E.S.VoiceRate + d, -10, 10);
            E.S.Save();
            E.Host.ApplySettings();
            return d > 0 ? "Así, más rápido." : "Así, más despacio.";
        }

        static readonly string[] Jokes =
        {
            "¿Por qué el libro de matemáticas estaba triste? Porque tenía demasiados problemas.",
            "¿Qué le dice un bit al otro? Nos vemos en el bus.",
            "Fui a comprar un antivirus y me pidieron la receta.",
            "¿Cuál es el colmo de un informático? Que su mujer le pida espacio y le formatee el disco.",
            "Mi contraseña es «incorrecta». Así, cuando la olvido, el sistema me la recuerda.",
            "¿Por qué los programadores confunden Halloween con Navidad? Porque 31 en octal es 25 en decimal.",
            "Le pregunté a Windows si podía actualizarse más tarde. Me dijo que sí, en cinco minutos.",
            "¿Qué hace una abeja en el gimnasio? Zumba.",
            "Había una vez un pollito que se llamaba Pepito. Le pisó un camión y ya no se llamaba.",
            "¿Cómo se despiden los químicos? Ácido un placer.",
            "¿Qué le dijo un semáforo a otro? No me mires, que me estoy cambiando.",
            "Doctor, veo doble. Siéntese en esa camilla. ¿En cuál de las dos?",
            "¿Por qué la impresora no habla con nadie? Porque está atascada.",
            "Mi jefe me dijo que trabajara como si no hubiera mañana. Así que hoy no he ido.",
            "Un byte entra en un bar y pide ocho cervezas. El camarero le dice: ¿algo más? Y responde: no, con esto voy completo.",
        };

        static readonly string[] Facts =
        {
            "El primer error informático fue literalmente un bicho: una polilla atrapada en un relé de la computadora Mark II, en 1947.",
            "Un rayo es unas cinco veces más caliente que la superficie del Sol.",
            "Los pulpos tienen tres corazones y sangre azul.",
            "La miel no se estropea: se ha encontrado miel comestible de hace más de tres mil años en tumbas egipcias.",
            "En Venus un día dura más que un año.",
            "El cerebro humano consume alrededor del veinte por ciento de la energía del cuerpo.",
            "La Torre Eiffel puede crecer unos quince centímetros en verano por la dilatación del hierro.",
            "Hay más estrellas en el universo que granos de arena en todas las playas de la Tierra.",
            "El corazón de una ballena azul es tan grande como un coche pequeño.",
            "El primer mensaje enviado por internet, en 1969, fue «LO»: el sistema se colgó antes de terminar «LOGIN».",
        };

        public string Chat(Cmd c)
        {
            string s = c.Join(0);
            string name = E.S.Name;
            if (Text.IsOneOf(s, "hola", "buenas", "hey", "que tal", "buenos dias", "buenas tardes", "buenas noches", "hola " + Text.Squash(name)))
            {
                int h = DateTime.Now.Hour;
                string g = h < 12 ? "Buenos días" : h < 20 ? "Buenas tardes" : "Buenas noches";
                return Pick(g + Sir + ". ¿En qué le ayudo?", g + Sir + ".", "Hola" + Sir + ". Dígame.");
            }
            if (Text.IsOneOf(s, "gracias", "muchas gracias", "te lo agradezco", "genial gracias", "perfecto gracias", "buen trabajo", "bien hecho", "eres el mejor", "eres la mejor"))
                return Pick("Para eso estoy" + Sir + ".", "Un placer" + Sir + ".", "Siempre a su servicio.", "No hay de qué.");
            if (Text.IsOneOf(s, "como estas", "que tal estas", "como te encuentras", "como vas", "todo bien", "como andas"))
                return Pick("Todos los sistemas funcionando" + Sir + ". ¿Y usted?", "Perfectamente, gracias. ¿En qué le ayudo?", "Al cien por cien" + Sir + ".");
            if (Text.IsOneOf(s, "quien eres", "como te llamas", "que eres", "presentate"))
                return E.S.IsViernes
                    ? "Soy VIERNES, su asistente personal. Puedo manejar el equipo por voz y responder lo que necesite."
                    : "Soy JARVIS, Just A Rather Very Intelligent System. Su asistente personal" + Sir + ".";
            if (Text.IsOneOf(s, "como me llamo", "quien soy", "sabes quien soy", "sabes mi nombre"))
                return E.T == "" ? "No me ha dicho su nombre. Diga «llámame» y su nombre." : "Usted es " + E.T + ".";
            if (Text.IsOneOf(s, "estas ahi", "me oyes", "me escuchas", "oyes", "escuchas", "me escuchas bien", "escuchas bien", "sigues ahi", "hola estas ahi"))
                return Pick("Aquí estoy" + Sir + ".", "Siempre" + Sir + ".", "Le escucho.");
            if (Text.IsOneOf(s, "te quiero", "te amo", "eres genial", "me caes bien", "caes bien"))
                return Pick("Yo también le aprecio" + Sir + ". Dentro de lo que un programa puede.", "Lo tendré en cuenta en mi próxima actualización.");
            if (Text.IsOneOf(s, "me aburro", "aburro", "estoy aburrido", "estoy aburrida", "que aburrimiento"))
                return Pick("Puedo contarle un chiste, un dato curioso o lanzar una moneda. Usted elige.", "¿Un chiste? ¿Un dato curioso? Pídamelo.");

            if (c.HasAny("chiste", "chistes") || c.Contains("algo gracioso") || c.Contains("hazme reir") || c.Contains("haz reir"))
                return PickFresh("chistes", Jokes);
            if (c.Contains("dato curioso") || c.Contains("algo interesante") || c.Contains("sabias que") || c.Contains("una curiosidad"))
                return PickFresh("datos", Facts);
            if (c.Has("moneda") && c.HasAny("lanza", "tira", "lanzar", "tirar", "echa"))
                return Rnd.Next(2) == 0 ? "Cara." : "Sello.";
            if (c.HasAny("dado", "dados") && c.HasAny("lanza", "tira", "lanzar", "tirar", "echa"))
            {
                int n = c.FindNumber(0, true) is int k && k >= 0 && c.W(k + 1).StartsWith("dado") ? Math.Clamp(Text.ParseNumber(c.W(k), true), 1, 6) : 1;
                var vals = Enumerable.Range(0, n).Select(_ => Rnd.Next(1, 7)).ToList();
                return n == 1 ? "Ha salido un " + vals[0] + "." : "Han salido " + string.Join(", ", vals) + ". Suman " + vals.Sum() + ".";
            }
            if (c.Contains("numero aleatorio") || c.Contains("numero al azar") || (c.Has("numero") && c.Has("entre") && c.HasAny("dime", "dame", "elige", "piensa")))
            {
                int a = 1, b = 100;
                int i = c.Find("entre");
                if (i >= 0)
                {
                    int n1 = c.FindNumber(i + 1, true), n2 = n1 >= 0 ? c.FindNumber(n1 + 1, true) : -1;
                    if (n1 >= 0 && n2 >= 0)
                    {
                        a = Text.ParseNumber(c.W(n1), true);
                        b = Text.ParseNumber(c.W(n2), true);
                    }
                }
                if (a > b) (a, b) = (b, a);
                return "El " + Rnd.Next(a, b + 1) + ".";
            }
            // «elige entre pizza o hamburguesa»
            if ((c.W(0) == "elige" || c.W(0) == "escoge" || c.Contains("que prefieres")) && (c.Has("o") || c.Has("u")))
            {
                int i = c.Find("entre");
                string rest = i >= 0 ? c.OrigFrom(i + 1) : c.OrigFrom(1);
                var opts = rest.Split(new[] { " o ", " u ", ", " }, StringSplitOptions.RemoveEmptyEntries).Select(x => x.Trim(' ', '.', '?', '¿')).Where(x => x != "").ToList();
                if (opts.Count >= 2) return Pick("Elijo ", "Me quedo con ", "Sin duda, ") + opts[Rnd.Next(opts.Count)] + ".";
            }
            return null;
        }
    }
}
