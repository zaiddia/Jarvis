using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;

namespace Jarvis.Core
{
    // Una orden propia: una frase que dispara varias órdenes («modo cine» → baja el brillo, abre Netflix…).
    public sealed class Protocol
    {
        public string Phrase { get; set; } = "";
        public List<string> Steps { get; set; } = new List<string>();
        // Cuándo se lanza sola: «07:30», «07:30 lun-vie», «al iniciar», «al volver»; vacío = solo con la frase.
        public string When { get; set; } = "";
    }

    // Ajustes de JARVIS. Se guardan en %APPDATA%\JARVIS\ajustes.json.
    public sealed class Settings
    {
        // General
        public string Persona { get; set; } = "jarvis";        // jarvis | viernes
        public string Treatment { get; set; } = "señor";
        public string WakeWord { get; set; } = "Jarvis";
        public string Hotkey { get; set; } = "Ctrl+Alt+J";
        public string PushToTalkKey { get; set; } = "";        // mantener pulsada para hablar (p. ej. F8)
        public string City { get; set; } = "";
        public bool StartWithWindows { get; set; } = true;
        public bool GreetOnStart { get; set; } = true;
        public bool FollowUp { get; set; } = true;
        public int FollowUpSeconds { get; set; } = 10;          // cuánto sigue escuchando tras responder (sin repetir el nombre)
        public bool SpeakConfirmations { get; set; } = true;   // decir «listo», «pausado»… al hacer algo
        public bool BargeIn { get; set; } = true;              // interrumpirla llamándola por su nombre mientras habla

        // Integraciones
        public string HaUrl { get; set; } = "";                 // Home Assistant, p. ej. http://homeassistant.local:8123
        public string HaToken { get; set; } = "";               // token de larga duración
        public string NtfyTopic { get; set; } = "";             // tema de ntfy para avisos al celular
        public string NtfyServer { get; set; } = "";            // vacío = https://ntfy.sh
        public bool PhoneReminders { get; set; } = true;        // recordatorios y avisos también al celular
        public bool RemoteControl { get; set; } = false;        // recibir órdenes desde el celular (ntfy)
        public string RemoteTopic { get; set; } = "";           // canal secreto para esas órdenes (se genera solo; se guarda cifrado)
        public bool AutoUpdate { get; set; } = true;            // buscar versiones nuevas en GitHub y avisar
        public string UpdateRepo { get; set; } = "zaiddia/Jarvis";
        public string BriefingTime { get; set; } = "";          // «07:30»: resumen del día automático (vacío = no)
        public string RadioCountry { get; set; } = "CO";        // país preferido para las emisoras
        public string YouTubeApiKey { get; set; } = "";         // opcional: búsqueda oficial de YouTube (Google Cloud, API de YouTube Data v3)
        public string Sensitivity { get; set; } = "normal";    // alta | normal | baja

        // Voz (escuchar)
        public bool VoiceInput { get; set; } = true;
        public string SpeechEngine { get; set; } = "whisper";  // whisper | windows
        public string Recognizer { get; set; } = "auto";        // auto | moderno | clasico
        public string RecognizerLanguage { get; set; } = "";    // vacío = el mejor español disponible
        public string WhisperModel { get; set; } = "auto";      // auto | turbo | small | base
        public int EndSilenceMs { get; set; } = 700;            // silencio que marca el final de la frase

        // Voz (hablar)
        public bool VoiceOutput { get; set; } = true;
        public string VoiceEngine { get; set; } = "neural";     // cloud | neural | windows
        public string PiperVoice { get; set; } = "";
        public int PiperSpeaker { get; set; } = 0;
        public int VoiceRate { get; set; } = 0;                 // -10…10
        public string WindowsVoice { get; set; } = "";
        public string CloudProvider { get; set; } = "openai";   // openai | elevenlabs | azure | gemini
        public string CloudKey { get; set; } = "";
        public string CloudVoice { get; set; } = "";
        public string CloudRegion { get; set; } = "";
        public string CloudModel { get; set; } = "";
        public string CloudStyle { get; set; } =
            "Habla como JARVIS, el mayordomo digital de Iron Man: voz masculina grave y serena, muy educada, ritmo ágil y un leve toque de ironía británica. En español neutro.";

        // IA
        public string AiProvider { get; set; } = "anthropic";   // anthropic | openai | gemini | ollama
        public string ApiKey { get; set; } = "";
        public Dictionary<string, string> ApiKeys { get; set; } = new Dictionary<string, string>();   // la clave de cada proveedor, para cambiar sin volver a pegarla
        public string Model { get; set; } = "";
        public string ApiUrl { get; set; } = "";
        public bool SendContext { get; set; } = true;
        public bool LocalFirst { get; set; } = true;
        public bool StreamAi { get; set; } = true;

        // Panel
        public string Theme { get; set; } = "azul";             // azul | mark3 | verde | morado | grafito
        public bool Glass { get; set; } = true;
        public int GlassOpacity { get; set; } = 70;
        public bool BootAnimation { get; set; } = true;
        public string Position { get; set; } = "abajo-derecha"; // abajo-derecha | arriba-derecha | centro

        // Ambiente
        public bool DuckAudio { get; set; } = true;
        public int DuckLevel { get; set; } = 25;
        public bool AutoQuiet { get; set; } = true;
        public bool UiSounds { get; set; } = true;

        // Otros
        public string SearchEngine { get; set; } = "google";
        public int VolumeStep { get; set; } = 10;
        public bool ConfirmPower { get; set; } = true;
        public List<Protocol> Protocols { get; set; } = new List<Protocol>();

        // Agenda (enlace iCal privado de Google Calendar, Outlook…)
        public string CalendarUrl { get; set; } = "";
        public int CalendarAlertMinutes { get; set; } = 10;

        // Avisos del sistema (batería, disco lleno, programas colgados)
        public bool SystemAlerts { get; set; } = true;

        // ------------------------------------------------------------------

        [JsonIgnore] public bool IsViernes => string.Equals(Persona, "viernes", StringComparison.OrdinalIgnoreCase);
        [JsonIgnore] public string Name => IsViernes ? "VIERNES" : "JARVIS";
        [JsonIgnore] public string Title => IsViernes ? "V.I.E.R.N.E.S." : "J.A.R.V.I.S.";

        public static string Folder
        {
            get
            {
                string f = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "JARVIS");
                Directory.CreateDirectory(f);
                return f;
            }
        }

        public static string FilePath => Path.Combine(Folder, "ajustes.json");

        static readonly JsonSerializerOptions Options = new JsonSerializerOptions
        {
            WriteIndented = true,
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
            ReadCommentHandling = JsonCommentHandling.Skip,
            AllowTrailingCommas = true,
        };

        public static Settings Load()
        {
            try
            {
                if (File.Exists(FilePath))
                {
                    var s = JsonSerializer.Deserialize<Settings>(File.ReadAllText(FilePath), Options);
                    if (s != null)
                    {
                        bool plain = s.DecryptSecrets();
                        s.Normalized();
                        if (plain) s.Save();   // ajustes antiguos con claves sin cifrar: se cifran ya
                        return s;
                    }
                }
            }
            catch (Exception e)
            {
                Log.Write("No pude leer los ajustes: " + e.Message);
                // No se pierde nada: el archivo dañado se aparta antes de crear uno nuevo.
                try { File.Copy(FilePath, FilePath + ".danado-" + DateTime.Now.ToString("yyyyMMdd-HHmmss"), true); } catch { }
            }
            var d = new Settings();
            d.Save();
            return d;
        }

        public void Save()
        {
            try
            {
                // Las claves se guardan cifradas con DPAPI: solo su usuario de Windows en este equipo puede leerlas.
                var node = JsonSerializer.SerializeToNode(this, Options).AsObject();
                foreach (var k in new[] { "apiKey", "cloudKey", "haToken", "youTubeApiKey", "remoteTopic" })
                    if (node[k] is JsonValue v && v.TryGetValue(out string plain)) node[k] = Protect(plain);
                if (node["apiKeys"] is JsonObject keys)
                    foreach (var name in keys.Select(kv => kv.Key).ToList())
                        if (keys[name] is JsonValue kv2 && kv2.TryGetValue(out string plain)) keys[name] = Protect(plain);
                // Escritura segura: primero a un temporal y luego se reemplaza (un corte de luz no deja el archivo a medias).
                string tmp = FilePath + ".tmp";
                File.WriteAllText(tmp, node.ToJsonString(Options), Encoding.UTF8);
                File.Move(tmp, FilePath, true);
            }
            catch (Exception e)
            {
                Log.Write("No pude guardar los ajustes: " + e.Message);
            }
        }

        // ---------------------------------------------------------------- claves cifradas (DPAPI)

        const string EncPrefix = "dpapi:";

        static string Protect(string text)
        {
            if (string.IsNullOrEmpty(text) || text.StartsWith(EncPrefix)) return text ?? "";
            try
            {
                byte[] enc = ProtectedData.Protect(Encoding.UTF8.GetBytes(text), Entropy, DataProtectionScope.CurrentUser);
                return EncPrefix + Convert.ToBase64String(enc);
            }
            catch (Exception e)
            {
                Log.Write("No pude cifrar una clave: " + e.Message);
                return text;
            }
        }

        static string Unprotect(string text, ref bool plain)
        {
            if (string.IsNullOrEmpty(text)) return "";
            if (!text.StartsWith(EncPrefix))
            {
                plain = true;   // venía sin cifrar (versión anterior)
                return text;
            }
            try
            {
                byte[] raw = ProtectedData.Unprotect(Convert.FromBase64String(text.Substring(EncPrefix.Length)), Entropy, DataProtectionScope.CurrentUser);
                return Encoding.UTF8.GetString(raw);
            }
            catch (Exception e)
            {
                // Pasa si se copia ajustes.json a otro equipo u otro usuario: hay que volver a poner la clave.
                Log.Write("No pude descifrar una clave guardada (¿ajustes de otro equipo o usuario?): " + e.Message);
                return "";
            }
        }

        static readonly byte[] Entropy = Encoding.UTF8.GetBytes("JARVIS-ajustes-v1");

        // Devuelve true si había alguna clave sin cifrar.
        bool DecryptSecrets()
        {
            bool plain = false;
            ApiKey = Unprotect(ApiKey, ref plain);
            CloudKey = Unprotect(CloudKey, ref plain);
            HaToken = Unprotect(HaToken, ref plain);
            YouTubeApiKey = Unprotect(YouTubeApiKey, ref plain);
            RemoteTopic = Unprotect(RemoteTopic, ref plain);
            if (ApiKeys != null)
                foreach (var k in ApiKeys.Keys.ToList()) ApiKeys[k] = Unprotect(ApiKeys[k], ref plain);
            return plain;
        }

        Settings Normalized()
        {
            if (string.IsNullOrWhiteSpace(WakeWord)) WakeWord = IsViernes ? "Viernes" : "Jarvis";
            if (string.IsNullOrWhiteSpace(Hotkey)) Hotkey = "Ctrl+Alt+J";
            VoiceRate = Math.Clamp(VoiceRate, -10, 10);
            GlassOpacity = Math.Clamp(GlassOpacity, 20, 98);
            DuckLevel = Math.Clamp(DuckLevel, 0, 90);
            EndSilenceMs = Math.Clamp(EndSilenceMs, 300, 2500);
            FollowUpSeconds = Math.Clamp(FollowUpSeconds, 3, 60);
            VolumeStep = Math.Clamp(VolumeStep, 1, 50);
            Protocols ??= new List<Protocol>();
            ApiKeys ??= new Dictionary<string, string>();
            if (ApiKey.Trim() != "" && !ApiKeys.ContainsKey(AiProvider)) ApiKeys[AiProvider] = ApiKey.Trim();
            CalendarAlertMinutes = Math.Clamp(CalendarAlertMinutes, 0, 120);
            return this;
        }

        // Cambia de proveedor de IA recuperando su clave guardada (y el modelo por defecto si el actual era de otro).
        public void SwitchAi(string provider)
        {
            if (ApiKey.Trim() != "") ApiKeys[AiProvider] = ApiKey.Trim();
            bool modelWasDefault = string.IsNullOrWhiteSpace(Model) || Model.Trim() == DefaultModel;
            AiProvider = provider;
            ApiKey = ApiKeys.TryGetValue(provider, out var k) ? k : "";
            if (!modelWasDefault)
            {
                string m = Model.Trim().ToLowerInvariant();
                bool fits = provider == "anthropic" ? m.StartsWith("claude") : provider == "gemini" ? m.StartsWith("gemini")
                          : provider == "ollama" ? !m.StartsWith("claude") && !m.StartsWith("gemini-") && !m.StartsWith("gpt-")
                          : !m.StartsWith("claude") && !m.StartsWith("gemini");
                if (!fits) Model = "";
            }
            else Model = "";
        }

        public string DefaultModel => AiProvider == "anthropic" ? "claude-haiku-5-5" : AiProvider == "gemini" ? "gemini-3.8-flash"
                                    : Jarvis.Ai.LocalAi.IsLocal(this) ? (Jarvis.Ai.LocalAi.DetectedModel ?? "llama3.2") : "gpt-5-mini";
        public string EffectiveModel => string.IsNullOrWhiteSpace(Model) ? DefaultModel : Model.Trim();
    }
}
