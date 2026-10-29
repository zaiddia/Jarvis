using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Jarvis.Core;

namespace Jarvis.Commands
{
    // Lo que el motor necesita de la aplicación (ventana, bandeja, voz).
    public interface IHost
    {
        Settings Settings { get; }
        void Say(string text);                 // decir algo fuera de turno (un recordatorio que vence)
        void Show(string text);                // mostrar en el panel sin decirlo
        void Notify(string title, string text);
        void StopSpeaking();
        void OpenSettings();
        void Quit();
        void SetListening(bool on);
        bool Listening { get; }
        string ClipboardText();
        void SetClipboard(string text);
        void HidePanel();
        void ApplySettings();         // guardar y aplicar ajustes cambiados por voz
        IntPtr TargetWindow { get; }  // la última ventana activa que no es de JARVIS
        void ShowVoiceDiagnostics();  // revisar micrófono y reconocimiento de voz
        void ReloadSettings();        // volver a leer ajustes.json (tras restaurar una copia)
        void ShowSystemCheck();       // «prueba completa»: micrófono, voz, IA, internet e integraciones
    }

    public sealed class Reply
    {
        public string Say = "";
        public bool Silent;          // no decir nada (la acción ya se nota)
        public bool KeepListening;   // espera respuesta (una pregunta)
        public string ScreenQuestion; // hay que mirar la pantalla y preguntar esto a la IA
        public static Reply Of(string s) => new Reply { Say = s ?? "" };
    }

    // Motor de órdenes en español. Lo que no entiende lo devuelve como null y lo contesta la IA.
    public sealed class Engine
    {
        public readonly IHost Host;
        public Settings S => Host.Settings;

        // Todas las órdenes, en orden de prioridad (las síncronas se envuelven).
        readonly List<Func<Cmd, Task<string>>> _handlers = new List<Func<Cmd, Task<string>>>();
        readonly List<string> _names = new List<string>();
        void Add(string name, Func<Cmd, Task<string>> h) { _names.Add(name); _handlers.Add(h); }

        // Qué módulo atendió la última orden («Time», «YouTube»…; «» si nadie: la contesta la IA).
        // Lo usan las pruebas automáticas y el registro, para saber por qué se entendió algo como se entendió.
        public string LastHandler { get; private set; } = "";
        static Func<Cmd, Task<string>> Sync(Func<Cmd, string> f) => c => Task.FromResult(f(c));

        public readonly AppsModule Apps;
        public readonly SystemModule Sys;
        public readonly TimeModule Time;
        public readonly InfoModule Info;
        public readonly TalkModule Talk;
        public readonly MediaModule Media;
        public readonly AgendaModule Agenda;
        public readonly VisionModule Vision;
        public readonly WatchModule Watch;
        public readonly ExtraModule Extra;
        public readonly SocialModule Social;
        public readonly YouTubeModule YouTube;
        public readonly IntegrationsModule Integrations;
        public readonly RoutinesModule Routines;

        // Una pregunta pendiente («¿Seguro que quiere apagar?»).
        string _question;
        Func<bool, string> _onAnswer;
        DateTime _questionUntil;

        public string LastCommand { get; private set; } = "";
        public string LastReply { get; set; } = "";
        public bool KeepListening { get; private set; }
        public string LastFile = "";   // la última captura o archivo creado
        public string ScreenQuestion;  // lo pone VisionModule: la IA debe mirar la pantalla

        public Engine(IHost host)
        {
            Host = host;
            Talk = new TalkModule(this);
            Time = new TimeModule(this);
            Sys = new SystemModule(this);
            Info = new InfoModule(this);
            Apps = new AppsModule(this);
            Media = new MediaModule(this);
            Agenda = new AgendaModule(this);
            Vision = new VisionModule(this);
            Watch = new WatchModule(this);
            Extra = new ExtraModule(this);
            Social = new SocialModule(this);
            YouTube = new YouTubeModule(this);
            Integrations = new IntegrationsModule(this);
            Routines = new RoutinesModule(this);

            // El orden importa: lo más concreto primero.
            Add("Talk.Control", Sync(Talk.Control));
            Add("Rutinas", Sync(Routines.Try));      // «qué rutinas tengo», «borra la rutina…»
            Add("Vision", Sync(Vision.Try));
            Add("Time", Sync(Time.Try));
            Add("Integrations", Sync(Integrations.Try));  // pomodoro, copias de seguridad
            Add("Extra", Sync(Extra.Try));         // volumen por app, modo oscuro, contraseñas, fechas…
            Add("Agenda", Agenda.TryAsync);
            Add("Media", Media.TryAsync);          // antes que las teclas multimedia
            Add("Integrations", Integrations.TryAsync);   // casa, celular, cripto, traducción, pronóstico, radio
            Add("YouTube", YouTube.TryAsync);        // «pon un video de…»: lo abre y suena solo
            Add("Extra", Extra.TryAsync);          // brillo, divisas, noticias, red, consumo
            Add("Sys", Sync(Sys.Try));
            Add("Info", Sync(Info.Try));
            Add("Info", Info.TryAsync);
            Add("Social", Sync(Social.Try));         // cómo se siente, adivinanzas, deletrear…
            Add("Social", Social.TryAsync);          // Wikipedia
            Add("Apps", Sync(Apps.Try));
            Add("Talk.Chat", Sync(Talk.Chat));
        }

        public string T => S.Treatment.Trim() == "" ? "" : S.Treatment.Trim();
        // «, señor» o nada.
        public string Sir => T == "" ? "" : ", " + T;

        // La respuesta es una pregunta: seguir escuchando sin que tenga que decir el nombre.
        public void ExpectReply() => KeepListening = true;

        public void Ask(string question, Func<bool, string> onAnswer)
        {
            _question = question;
            _onAnswer = onAnswer;
            _questionUntil = DateTime.Now.AddSeconds(25);
            KeepListening = true;
        }

        static readonly string[] Yes = { "si", "claro", "dale", "hazlo", "adelante", "confirmo", "afirmativo", "correcto", "por supuesto", "venga", "ok", "vale", "sip" };
        static readonly string[] No = { "no", "cancela", "cancelar", "dejalo", "olvidalo", "nada", "negativo", "mejor no", "para", "espera" };

        // Devuelve null si no es una orden conocida.
        public async Task<Reply> HandleAsync(string text)
        {
            KeepListening = false;
            ScreenQuestion = null;
            string sq = Text.Squash(text);
            if (sq == "") return null;

            if (_onAnswer != null)
            {
                var cb = _onAnswer;
                bool fresh = DateTime.Now < _questionUntil;
                _onAnswer = null;
                _question = null;
                if (fresh)
                {
                    string first = sq.Split(' ')[0];
                    if (Yes.Contains(sq) || Yes.Contains(first) || sq.StartsWith("si ")) return Done(cb(true));
                    if (No.Contains(sq) || No.Contains(first)) return Done(cb(false));
                }
            }

            // «otra vez», «repite eso»
            if (Text.IsOneOf(sq, "otra vez", "de nuevo", "repitelo", "hazlo otra vez", "hazlo de nuevo", "otra") && LastCommand != "")
                text = LastCommand;
            if (Text.IsOneOf(sq, "que dijiste", "que has dicho", "repite", "repite eso", "no te entendi", "como dijiste", "perdon que", "que"))
                return Reply.Of(LastReply == "" ? "Aún no he dicho nada" + Sir + "." : LastReply);

            string r = await RunProtocol(sq);
            if (r == null) r = await RunOne(text);
            if (r == null)
            {
                // «abre Spotify y sube el volumen»: varias órdenes seguidas.
                var parts = SplitChain(text);
                if (parts.Count > 1)
                {
                    var outs = new List<string>();
                    foreach (var p in parts)
                    {
                        string o = await RunOne(p);
                        if (o == null) return null;   // si una no se entiende, todo a la IA
                        outs.Add(o);
                    }
                    r = string.Join(" ", outs.Where(o => o != "" && o != Quiet).Select(o => o.TrimEnd('.') + "."));
                }
            }
            if (r == null) return null;
            if (!sq.StartsWith("otra vez")) LastCommand = text;
            return Done(r, text);
        }

        // Para órdenes que no deben contestar nada (cállate, silenciar…): ni siquiera «listo».
        public const string Quiet = "\u0001";

        Reply Done(string r, string text = null)
        {
            bool quiet = r == Quiet || ScreenQuestion != null;
            if (r == Quiet) r = "";
            // Una acción hecha en silencio se confirma con una frase corta, como lo haría una persona.
            if (!quiet && string.IsNullOrEmpty(r) && S.SpeakConfirmations) r = AckFor(text);
            var rep = new Reply { Say = r ?? "", Silent = string.IsNullOrEmpty(r), KeepListening = KeepListening, ScreenQuestion = ScreenQuestion };
            ScreenQuestion = null;
            if (!rep.Silent) LastReply = rep.Say;
            return rep;
        }

        static readonly System.Random Rnd = new System.Random();
        string P(params string[] o) => o[Rnd.Next(o.Length)];

        // «Pausado», «Abriendo», «Copiado»… según lo que se pidió; si no, un «listo» variado.
        public string AckFor(string text)
        {
            var c = Cmd.Parse(text ?? "");
            string w = c.W(0), all = c.Join(0);
            string sir = Sir;
            if (Text.IsOneOf(w, "pausa", "pausalo", "para", "deten") || all.Contains("pon pausa")) return P("En pausa.", "Pausado" + sir + ".", "Listo, en pausa.");
            if (Text.IsOneOf(w, "reproduce", "continua", "sigue", "reanuda", "play", "reanudalo", "dale") || all.Contains("quita la pausa")) return P("Reproduciendo.", "Ahí va.", "Sonando" + sir + ".");
            if (Text.IsOneOf(w, "siguiente", "pasa", "salta", "proxima", "otra") || all.Contains("siguiente")) return P("Siguiente.", "Pasando a la siguiente.", "Ahí va la siguiente.");
            if (Text.IsOneOf(w, "anterior", "vuelve", "regresa") || all.Contains("anterior")) return P("La anterior.", "Volviendo a la anterior.");
            if (Text.IsOneOf(w, "minimiza", "minimizar", "esconde")) return P("Minimizada.", "Listo, minimizada.");
            if (Text.IsOneOf(w, "maximiza", "maximizar")) return P("Maximizada.", "A pantalla completa.");
            if (w == "restaura") return "Restaurada.";
            if (all.Contains("escritorio")) return P("Aquí tiene el escritorio.", "Escritorio despejado.");
            if (all.Contains("ventana") && Text.IsOneOf(w, "cambia", "siguiente", "otra")) return "Cambiando de ventana.";
            if (Text.IsOneOf(w, "copia", "copialo")) return P("Copiado.", "Copiado al portapapeles.");
            if (Text.IsOneOf(w, "pega", "pegalo")) return "Pegado.";
            if (Text.IsOneOf(w, "guarda", "guardalo")) return "Guardado.";
            if (Text.IsOneOf(w, "deshaz", "deshacer", "deshazlo")) return "Deshecho.";
            if (Text.IsOneOf(w, "selecciona", "seleccionalo")) return "Todo seleccionado.";
            if (all.Contains("pestana")) return w == "cierra" ? "Pestaña cerrada." : "Nueva pestaña.";
            if (Text.IsOneOf(w, "recarga", "actualiza", "refresca")) return "Recargando.";
            if (Text.IsOneOf(w, "escribe", "teclea", "dicta")) return P("Escrito.", "Listo, ya está escrito.");
            if (Text.IsOneOf(w, "bloquea", "bloquealo")) return P("Bloqueando el equipo.", "Equipo bloqueado. Hasta ahora" + sir + ".");
            if (all.Contains("graba")) return "Grabación en marcha.";
            if (Text.IsOneOf(w, "cierra", "cierralo", "cierrala", "cerrar")) return P("Cerrado.", "Listo, cerrado.");
            if (Text.IsOneOf(w, "abre", "abrir", "lanza", "inicia", "ejecuta", "abreme")) return P("Abriendo.", "En marcha.");
            if (Text.IsOneOf(w, "sube", "baja")) return P("Hecho.", "Así está mejor.", "Listo.");
            return Talk.Ack();
        }

        // Protocolos: una frase propia que lanza varias órdenes («protocolo trabajo»: abre Outlook, abre Teams, di buenos días).
        async Task<string> RunProtocol(string sq)
        {
            if (S.Protocols == null || S.Protocols.Count == 0) return null;
            string bare = sq;
            foreach (var pre in new[] { "activa el protocolo ", "inicia el protocolo ", "ejecuta el protocolo ", "protocolo ", "modo " })
                if (bare.StartsWith(pre)) { bare = bare.Substring(pre.Length); break; }
            var p = S.Protocols.FirstOrDefault(x => Text.Squash(x.Phrase) != "" &&
                    (Text.Squash(x.Phrase) == sq || Text.Squash(x.Phrase) == bare || Text.Squash(x.Phrase) == "protocolo " + bare));
            if (p == null) return null;
            string r = await RunRoutine(p);
            LastHandler = "Rutinas";
            return r;
        }

        // Lanza los pasos de una rutina (con su frase o sola, a su hora). Devuelve lo que hay que decir.
        public async Task<string> RunRoutine(Protocol p)
        {
            var said = new List<string>();
            foreach (string raw in p.Steps)
            {
                string step = (raw ?? "").Trim();
                if (step == "") continue;
                var c = Cmd.Parse(step);
                if (c.W(0) == "di" || c.W(0) == "dime" || c.W(0) == "decir")
                {
                    said.Add(c.OrigFrom(1));
                    continue;
                }
                if (c.W(0) == "espera" && Text.ParseNumber(c.W(1), true) is int n && n > 0)
                {
                    await Task.Delay(TimeSpan.FromSeconds(Math.Min(n, 60)));
                    continue;
                }
                string o = await RunOne(step);
                if (o == null) Log.Write("Protocolo «" + p.Phrase + "»: no entendí el paso «" + step + "»");
                else if (o != "" && o != Quiet && p.Steps.Count <= 3) said.Add(o);
            }
            return said.Count > 0 ? string.Join(" ", said.Select(x => x.TrimEnd('.') + ".")) : "Rutina «" + p.Phrase + "» completada" + Sir + ".";
        }

        async Task<string> RunOne(string text)
        {
            var c = Cmd.Parse(text);
            LastHandler = "";
            if (c.Size == 0) return null;
            for (int i = 0; i < _handlers.Count; i++)
            {
                try
                {
                    string r = await _handlers[i](c);
                    if (r != null)
                    {
                        LastHandler = _names[i];
                        return r;
                    }
                }
                catch (Exception e)
                {
                    LastHandler = _names[i];
                    Log.Write("Orden «" + text + "» (" + _names[i] + "): " + e);
                    return "Algo falló al hacerlo" + Sir + ".";
                }
            }
            return null;
        }

        static readonly string[] ChainVerbs =
        {
            "abre", "abrir", "cierra", "cerrar", "sube", "baja", "pon", "silencia", "quita", "minimiza", "maximiza", "busca",
            "bloquea", "apaga", "reinicia", "pausa", "reanuda", "siguiente", "anterior", "dime", "toma", "haz", "vacia", "muestra",
            "recuerdame", "avisame", "despiertame", "lanza", "inicia", "ejecuta", "escribe", "activa", "desactiva", "mutea", "para", "deten",
        };

        // Parte en «y» o comas, solo donde empieza otra orden.
        internal static List<string> SplitChain(string text)
        {
            var c = Cmd.Parse(text);
            var o = new List<string>();
            if (c.Size < 4) return o;
            int start = 0;
            for (int i = 1; i + 1 < c.Size; i++)
            {
                bool sep = c.W(i) == "y" || c.W(i) == "luego" || c.W(i) == "despues";
                int next = i + 1;
                if (c.W(i) == "y" && (c.W(i + 1) == "luego" || c.W(i + 1) == "despues")) next = i + 2;
                if (sep && ChainVerbs.Contains(c.W(next)) && i > start)
                {
                    o.Add(c.OrigFrom(start, i));
                    start = next;
                    i = next;
                }
            }
            if (o.Count == 0) return o;
            o.Add(c.OrigFrom(start));
            return o.Where(p => p.Trim() != "").ToList();
        }

        // Cada segundo: recordatorios y temporizadores que vencen.
        public void Tick()
        {
            Time.Tick();
            Agenda.Tick();
            Watch.Tick();
            Integrations.Tick();
            Routines.Tick();
        }
    }
}
