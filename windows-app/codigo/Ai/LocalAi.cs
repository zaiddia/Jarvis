using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;
using Jarvis.Core;

namespace Jarvis.Ai
{
    // IA en el propio equipo: Ollama (o LM Studio y otros compatibles con OpenAI).
    // Arregla la dirección se escriba como se escriba y averigua qué modelos hay instalados.
    public static class LocalAi
    {
        static readonly HttpClient Http = Net.Create(TimeSpan.FromSeconds(6));
        public static string DetectedModel { get; private set; }
        public static List<string> Installed { get; private set; } = new List<string>();
        static string _detectedFor = "";

        public static bool IsOllama(Settings s) => s.AiProvider == "ollama" || (s.AiProvider == "openai" && s.ApiUrl.Contains(":11434"));
        public static bool IsLocal(Settings s) => s.AiProvider == "ollama" || (s.AiProvider == "openai" && s.ApiUrl.Trim() != "");

        // «localhost:11434», «http://localhost:11434», «…/v1», «…/v1/chat/completions» → «http://localhost:11434/v1»
        public static string BaseUrl(Settings s)
        {
            string u = s.ApiUrl.Trim();
            if (u == "") u = s.AiProvider == "ollama" ? "http://127.0.0.1:11434/v1" : "https://api.openai.com/v1";
            if (!u.Contains("://")) u = "http://" + u;
            u = u.TrimEnd('/');
            if (u.EndsWith("/chat/completions", StringComparison.OrdinalIgnoreCase)) u = u.Substring(0, u.Length - "/chat/completions".Length).TrimEnd('/');
            // Sin ruta: Ollama y LM Studio sirven la interfaz de OpenAI en /v1.
            int scheme = u.IndexOf("://", StringComparison.Ordinal) + 3;
            if (u.IndexOf('/', scheme) < 0) u += "/v1";
            return u;
        }

        public static string ChatUrl(Settings s) => BaseUrl(s) + "/chat/completions";

        static string Root(Settings s)
        {
            string b = BaseUrl(s);
            return b.EndsWith("/v1") ? b.Substring(0, b.Length - 3) : b;
        }

        // Modelos instalados, el preferido primero. Lanza HttpRequestException si no hay servidor.
        public static async Task<List<string>> ListModels(Settings s)
        {
            var names = new List<string>();
            if (IsOllama(s))
            {
                try
                {
                    using var doc = JsonDocument.Parse(await Http.GetStringAsync(Root(s) + "/api/tags"));
                    if (doc.RootElement.TryGetProperty("models", out var ms))
                        foreach (var m in ms.EnumerateArray())
                            if (m.TryGetProperty("name", out var n)) names.Add(n.GetString() ?? "");
                }
                catch (HttpRequestException) { throw; }
                catch (Exception e) { Log.Write("Ollama /api/tags: " + e.Message); }
            }
            if (names.Count == 0)
            {
                using var req = new HttpRequestMessage(HttpMethod.Get, BaseUrl(s) + "/models");
                if (s.ApiKey.Trim() != "") req.Headers.Add("Authorization", "Bearer " + s.ApiKey.Trim());
                using var res = await Http.SendAsync(req);
                if (res.IsSuccessStatusCode)
                {
                    using var doc = JsonDocument.Parse(await res.Content.ReadAsStringAsync());
                    if (doc.RootElement.TryGetProperty("data", out var ms))
                        foreach (var m in ms.EnumerateArray())
                            if (m.TryGetProperty("id", out var n)) names.Add(n.GetString() ?? "");
                }
            }
            names = names.Where(n => n != "" && !n.Contains("embed", StringComparison.OrdinalIgnoreCase) && !n.Contains("whisper", StringComparison.OrdinalIgnoreCase)).Distinct().ToList();
            string[] pref = { "qwen3", "qwen2.5", "gemma3", "llama3.2", "llama3.1", "llama3", "mistral", "gemma", "phi" };
            names = names.OrderBy(n =>
            {
                int i = Array.FindIndex(pref, p => n.StartsWith(p, StringComparison.OrdinalIgnoreCase));
                return i < 0 ? 99 : i;
            }).ToList();
            Installed = names;
            DetectedModel = names.FirstOrDefault();
            _detectedFor = BaseUrl(s);
            if (DetectedModel != null) Log.Write("IA local: " + names.Count + " modelos; uso " + DetectedModel);
            return names;
        }

        // El modelo a usar: el escrito en ajustes o el primero instalado.
        public static async Task<string> ModelFor(Settings s)
        {
            if (!string.IsNullOrWhiteSpace(s.Model)) return s.Model.Trim();
            if (DetectedModel == null || _detectedFor != BaseUrl(s))
            {
                try { await ListModels(s); }
                catch (Exception e) { Log.Write("IA local: no pude leer los modelos: " + e.Message); }
            }
            return DetectedModel ?? "llama3.2";
        }

        static readonly HttpClient WarmHttp = Net.Create(TimeSpan.FromMinutes(3));
        static string _warmed = "";

        // Carga el modelo en memoria por adelantado (y lo mantiene 30 minutos): la primera respuesta ya no tarda tanto.
        public static async Task Warm(Settings s)
        {
            string model = await ModelFor(s);
            if (!IsOllama(s)) return;
            string key = BaseUrl(s) + "|" + model;
            if (_warmed == key) return;
            _warmed = key;
            try
            {
                string body = JsonSerializer.Serialize(new { model, keep_alive = "30m", prompt = "" });
                using var res = await WarmHttp.PostAsync(Root(s) + "/api/generate", new StringContent(body, System.Text.Encoding.UTF8, "application/json"));
                Log.Write("Ollama: modelo " + model + (res.IsSuccessStatusCode ? " cargado en memoria." : " no se pudo precargar (" + (int)res.StatusCode + ")."));
            }
            catch (Exception e)
            {
                _warmed = "";
                Log.Write("Ollama: no pude precargar el modelo: " + e.Message);
            }
        }
    }
}
