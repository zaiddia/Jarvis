using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Jarvis.Commands;
using Jarvis.Core;

namespace Jarvis.Ai
{
    // Conversación con Claude (Anthropic) o con modelos compatibles con OpenAI (OpenAI, Ollama, LM Studio…).
    // La IA puede usar herramientas: ejecutar órdenes del propio JARVIS, recordar datos y leer el portapapeles.
    public sealed class AiClient
    {
        static readonly HttpClient Http = Net.Create(Timeout.InfiniteTimeSpan);
        readonly Func<Settings> _settings;
        readonly Engine _engine;
        readonly List<(string role, string text)> _history = new List<(string, string)>();
        DateTime _lastAt = DateTime.MinValue;
        bool _geminiNoEffort;

        public AiClient(Func<Settings> settings, Engine engine)
        {
            _settings = settings;
            _engine = engine;
        }

        Settings S => _settings();

        public bool Ready => S.AiProvider == "ollama" || (S.AiProvider != "ollama" && S.ApiKey.Trim() != "") || (S.AiProvider == "openai" && S.ApiUrl.Trim() != "");
        bool Local => LocalAi.IsLocal(S);
        bool Gemini => S.AiProvider == "gemini";
        const string GeminiUrl = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions";
        public void Forget() => _history.Clear();
        // ¿La última pregunta tuvo respuesta de verdad? (no un mensaje de error). Lo usa la prueba completa.
        public bool LastOk { get; private set; }
        public string ProviderLabel => (S.AiProvider == "anthropic" ? "Claude" : Gemini ? "Gemini" : LocalAi.IsOllama(S) ? "Ollama" : S.ApiUrl.Trim() != "" ? "servidor propio" : "OpenAI") + " (" + S.EffectiveModel + ")";

        // ---------------------------------------------------------------- herramientas

        static JsonObject Schema(params (string name, string desc)[] props)
        {
            var p = new JsonObject();
            foreach (var (n, d) in props) p[n] = new JsonObject { ["type"] = "string", ["description"] = d };
            return new JsonObject
            {
                ["type"] = "object",
                ["properties"] = p,
                ["required"] = new JsonArray(props.Select(x => (JsonNode)x.name).ToArray()),
            };
        }

        static readonly (string name, string desc, JsonObject schema)[] Tools =
        {
            ("ejecutar_orden",
             "Ejecuta en el equipo del usuario una orden del asistente, escrita en español sencillo como la diría el usuario " +
             "(mira el catálogo de habilidades en tus instrucciones y usa órdenes parecidas a sus ejemplos). Devuelve lo que contestó el asistente; " +
             "si no la entendió, devuelve órdenes parecidas que sí entiende para que lo intentes con una de ellas.",
             Schema(("orden", "La orden en español, corta y concreta"))),
            ("recordar",
             "Guarda de forma permanente un dato sobre el usuario: nombres de su gente, gustos, fechas, rutinas, dónde dejó algo. " +
             "Úsala sin preguntar cuando el usuario cuente algo estable de su vida. Escribe el dato en primera persona del usuario («Mi hermana se llama Ana»). " +
             "Un dato nuevo sobre lo mismo sustituye al anterior.",
             Schema(("dato", "El dato, en una frase en primera persona"))),
            ("olvidar",
             "Borra de la memoria los datos sobre algo, cuando el usuario pida que lo olvides o te diga que ya no es así.",
             Schema(("tema", "De qué trata lo que hay que olvidar, en pocas palabras"))),
            ("crear_rutina",
             "Crea o cambia una rutina: una frase que lanza varias órdenes seguidas y que, si se quiere, se lanza sola a una hora o al encender el equipo. " +
             "Ejemplo: frase «buenos días», cuando «07:30 lun-vie», pasos «dime el tiempo; qué tengo hoy; noticias».",
             Schema(("frase", "La frase que la lanza (por ejemplo «modo trabajo» o «buenos días»)"),
                    ("cuando", "Cuándo se lanza sola: «07:30», «07:30 lun-vie», «21:00 sab,dom», «al iniciar» (al encender el equipo), «al volver» (al volver tras un rato fuera) o vacío si solo se lanza con la frase"),
                    ("pasos", "Las órdenes separadas por punto y coma, como las diría el usuario; «di …» para decir algo"))),
            ("leer_portapapeles",
             "Devuelve el texto que el usuario tiene copiado en el portapapeles. Úsala cuando hable de «esto que he copiado» o «el texto copiado».",
             new JsonObject { ["type"] = "object", ["properties"] = new JsonObject() }),
        };

        async Task<string> RunTool(string name, JsonNode input)
        {
            try
            {
                switch (name)
                {
                    case "ejecutar_orden":
                    {
                        string order = input?["orden"]?.GetValue<string>() ?? "";
                        if (order.Trim() == "") return "Falta la orden.";
                        var r = await _engine.HandleAsync(order);
                        if (r == null)
                        {
                            var near = Skills.Closest(order);
                            return "El asistente no entendió «" + order + "»." + (near.Count > 0 ? " Órdenes parecidas que sí entiende: " + string.Join(", ", near.Select(x => "«" + x + "»")) + "." : "") +
                                   " Si ninguna sirve, díselo al usuario con naturalidad.";
                        }
                        return r.Say == "" ? "Hecho." : r.Say;
                    }
                    case "recordar":
                    {
                        string fact = input?["dato"]?.GetValue<string>() ?? "";
                        if (fact.Trim() == "") return "Falta el dato.";
                        return Memory.Add(fact) ? "Guardado (sustituye a lo que había sobre eso)." : "Guardado.";
                    }
                    case "olvidar":
                    {
                        string what = input?["tema"]?.GetValue<string>() ?? "";
                        int n = Memory.Forget(what);
                        return n > 0 ? "Olvidados " + n + " datos." : "No había nada sobre eso en la memoria.";
                    }
                    case "crear_rutina":
                    {
                        string phrase = input?["frase"]?.GetValue<string>() ?? "";
                        string when = input?["cuando"]?.GetValue<string>() ?? "";
                        string steps = input?["pasos"]?.GetValue<string>() ?? "";
                        return _engine.Routines.Create(phrase, when, steps);
                    }
                    case "leer_portapapeles":
                    {
                        string t = _engine.Host.ClipboardText();
                        return t == "" ? "El portapapeles está vacío." : (t.Length > 8000 ? t.Substring(0, 8000) + "…" : t);
                    }
                }
            }
            catch (Exception e)
            {
                return "Error: " + e.Message;
            }
            return "Herramienta desconocida.";
        }

        // ---------------------------------------------------------------- instrucciones

        string SystemPrompt(string windowTitle, string question = "")
        {
            var s = S;
            var es = CultureInfo.GetCultureInfo("es-ES");
            var sb = new StringBuilder();
            if (s.IsViernes)
                sb.Append("Eres VIERNES, la asistente personal por voz del usuario en su PC con Windows, inspirada en la IA de Tony Stark: cercana, directa, segura y con un toque de humor. ");
            else
                sb.Append("Eres JARVIS, el asistente personal por voz del usuario en su PC con Windows, inspirado en el mayordomo digital de Tony Stark: elegante, eficiente, leal y con un humor británico sutil. ");
            sb.Append("Hablas siempre en español, de forma natural y cálida, como una persona real en una conversación (no como un robot). ");
            sb.Append("Tus respuestas se leen en voz alta: sé breve (una a tres frases salvo que te pidan detalle), sin markdown, sin listas, sin emojis, sin enlaces, sin asteriscos. ");
            sb.Append("Escribe los números como se dicen cuando ayude a leerlos. ");
            if (s.Treatment.Trim() != "") sb.Append("Trata al usuario de usted y llámale «" + s.Treatment.Trim() + "» de vez en cuando, sin abusar. ");
            sb.Append("El texto del usuario viene del reconocimiento de voz y puede traer errores (palabras mal oídas, sin signos): interpreta la intención más probable en lugar de pedir que lo repita; " +
                      "solo pregunta si de verdad hay dos opciones muy distintas. ");
            sb.Append("Si te piden hacer algo en el equipo, o lo que dicen lo implica, usa la herramienta ejecutar_orden con una orden corta y clara, parecida a los ejemplos del catálogo; " +
                      "puedes llamarla varias veces. Interpreta la intención: «está muy oscuro aquí» → ejecutar_orden(«sube el brillo»); «esto suena muy alto» → ejecutar_orden(«baja el volumen»); " +
                      "«ponme algo para animarme» → ejecutar_orden(«pon salsa»); «quiero ver videos de gatos» → ejecutar_orden(«pon un video de gatos»); " +
                      "«avísame en un rato que saque la ropa» → ejecutar_orden(«recuérdame en 30 minutos sacar la ropa»); «me voy a trabajar» → ofrece su rutina si la tiene. ");
            sb.Append("\nCATÁLOGO DE HABILIDADES (órdenes que el asistente entiende):\n" + Skills.Catalog());
            sb.Append("Cuando el usuario cuente algo estable de su vida (nombres de su familia o mascotas, gustos, alergias, trabajo, fechas importantes, dónde guarda algo), " +
                      "guárdalo con la herramienta recordar sin preguntar y sin anunciarlo con solemnidad; usa lo que recuerdas para personalizar tus respuestas. " +
                      "Si pide una rutina («cada mañana dime el tiempo y mi agenda»), créala con crear_rutina. ");
            sb.Append("Después de usar una herramienta, confirma en una frase corta y natural lo que hiciste (por ejemplo «Listo, ya está sonando»). ");
            sb.Append("Nunca digas que no puedes controlar el equipo sin probar antes la herramienta. Si algo falla, dilo con naturalidad y sugiere qué hacer. ");
            sb.Append("Si el usuario solo conversa, conversa: responde con interés y, si viene al caso, haz una pregunta breve para seguir la charla. ");
            sb.Append("\nAhora es " + DateTime.Now.ToString("dddd d 'de' MMMM 'de' yyyy, HH:mm", es) + ". ");
            if (s.City.Trim() != "") sb.Append("El usuario vive en " + s.City.Trim() + ". ");
            if (s.SendContext && windowTitle != "") sb.Append("La ventana que tiene delante se titula «" + windowTitle + "». ");
            var facts = Memory.Relevant(question);
            if (facts.Count > 0) sb.Append("\nLo que sabes del usuario (te lo contó él): " + string.Join("; ", facts) + ".");
            var routines = _engine.Routines.Describe();
            if (routines != "") sb.Append("\nSus rutinas: " + routines + ".");
            return sb.ToString();
        }

        // ---------------------------------------------------------------- pregunta

        public async Task<string> AskAsync(string question, string windowTitle, Action<string> onSentence, CancellationToken ct, byte[] screenJpeg = null)
        {
            LastOk = false;
            if (!Ready) return "Para eso necesito una clave de IA. Póngala en mis ajustes, en la pestaña Inteligencia.";
            if ((DateTime.Now - _lastAt).TotalMinutes > 15) _history.Clear();
            _lastAt = DateTime.Now;
            var splitter = new SentenceSplitter(onSentence);
            string answer;
            try
            {
                answer = S.AiProvider == "anthropic"
                    ? await AskAnthropic(question, windowTitle, splitter, ct, screenJpeg)
                    : await AskOpenAi(question, windowTitle, splitter, ct, screenJpeg);
            }
            catch (OperationCanceledException) when (!ct.IsCancellationRequested && splitter.All.Trim() == "")
            {
                // No fue el usuario: se acabó el tiempo.
                return Local ? "El modelo local tardó demasiado. Pruebe uno más pequeño (por ejemplo llama3.2 o qwen3:4b) o espere a que termine de cargarse."
                             : "La IA tardó demasiado en responder. Pruebe otra vez.";
            }
            catch (OperationCanceledException)
            {
                return splitter.All;
            }
            catch (AiError e)
            {
                splitter.Flush();
                return e.Message;
            }
            catch (HttpRequestException e) when (Local)
            {
                Log.Write("IA local: " + e.Message);
                return LocalAi.IsOllama(S)
                    ? "No encuentro Ollama en " + LocalAi.BaseUrl(S) + ". Ábralo, o ejecute «ollama serve», y compruebe que tiene un modelo con «ollama list»."
                    : "No encuentro el servidor de IA en " + LocalAi.BaseUrl(S) + ". ¿Está en marcha?";
            }
            catch (HttpRequestException e)
            {
                Log.Write("IA: " + e.Message);
                return "No tengo conexión con la inteligencia artificial. Revise internet.";
            }
            splitter.Flush();
            answer = answer.Trim();
            _history.Add(("user", screenJpeg != null ? "[Mirando la pantalla] " + question : question));
            _history.Add(("assistant", answer == "" ? "Hecho." : answer));
            while (_history.Count > 16) _history.RemoveAt(0);
            LastOk = true;
            return answer;
        }

        sealed class AiError : Exception
        {
            public AiError(string m) : base(m) { }
        }

        static string Explain(int code, string body, string model)
        {
            string detail = "";
            try
            {
                var root = JsonNode.Parse(body);
                if (root is JsonArray arr && arr.Count > 0) root = arr[0];   // Gemini devuelve a veces una lista
                detail = root?["error"]?["message"]?.GetValue<string>() ?? "";
            }
            catch { }
            Log.Write("IA respondió " + code + ": " + Text.Preview(body, 400));
            return code switch
            {
                401 or 403 => "La clave de IA no es válida o no tiene permiso. Revísela en mis ajustes.",
                404 => "El modelo «" + model + "» no existe o no está disponible para su clave. Cámbielo en mis ajustes.",
                429 => "Se ha alcanzado el límite de uso o no queda saldo en la cuenta de IA.",
                400 when detail.Contains("credit") => "No queda saldo en la cuenta de IA.",
                400 when detail.Contains("API key") || detail.Contains("API_KEY") => "La clave de IA no es válida. Revísela en mis ajustes.",
                400 when detail.Contains("location is not supported") || detail.Contains("User location") => "El servicio de IA no está disponible en su país con esa clave.",
                500 or 502 or 503 or 529 => "El servicio de IA está saturado ahora mismo. Pruebe en un momento.",
                _ => "La IA respondió con un error (" + code + ")" + (detail != "" ? ": " + Text.Preview(detail, 120) : "."),
            };
        }

        // ---------------------------------------------------------------- Anthropic

        async Task<string> AskAnthropic(string question, string window, SentenceSplitter split, CancellationToken ct, byte[] image)
        {
            var s = S;
            var messages = new JsonArray();
            foreach (var (role, text) in _history) messages.Add(new JsonObject { ["role"] = role, ["content"] = text });
            if (image == null) messages.Add(new JsonObject { ["role"] = "user", ["content"] = question });
            else
                messages.Add(new JsonObject
                {
                    ["role"] = "user",
                    ["content"] = new JsonArray
                    {
                        new JsonObject
                        {
                            ["type"] = "image",
                            ["source"] = new JsonObject { ["type"] = "base64", ["media_type"] = "image/jpeg", ["data"] = Convert.ToBase64String(image) },
                        },
                        new JsonObject { ["type"] = "text", ["text"] = "Esta es una captura de mi pantalla ahora mismo. " + question },
                    },
                });
            var tools = new JsonArray(Tools.Select(t => (JsonNode)new JsonObject
            {
                ["name"] = t.name,
                ["description"] = t.desc,
                ["input_schema"] = t.schema.DeepClone(),
            }).ToArray());
            var full = new StringBuilder();
            for (int turn = 0; turn < 5; turn++)
            {
                var body = new JsonObject
                {
                    ["model"] = s.EffectiveModel,
                    ["max_tokens"] = 1024,
                    ["system"] = SystemPrompt(window, question),
                    ["messages"] = messages.DeepClone(),
                    ["tools"] = tools.DeepClone(),
                    ["stream"] = true,
                };
                string url = s.ApiUrl.Trim() != "" && s.ApiUrl.Contains("anthropic") ? s.ApiUrl.Trim() : "https://api.anthropic.com/v1/messages";
                using var req = new HttpRequestMessage(HttpMethod.Post, url);
                req.Headers.Add("x-api-key", s.ApiKey.Trim());
                req.Headers.Add("anthropic-version", "2023-06-01");
                req.Content = new StringContent(body.ToJsonString(), Encoding.UTF8, "application/json");
                using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
                cts.CancelAfter(TimeSpan.FromSeconds(60));
                using var res = await Http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead, cts.Token);
                if (!res.IsSuccessStatusCode) throw new AiError(Explain((int)res.StatusCode, await res.Content.ReadAsStringAsync(cts.Token), s.EffectiveModel));

                var blocks = new List<JsonObject>();
                var toolJson = new Dictionary<int, StringBuilder>();
                string stop = "";
                using var stream = await res.Content.ReadAsStreamAsync(cts.Token);
                using var reader = new StreamReader(stream, Encoding.UTF8);
                string line;
                while ((line = await reader.ReadLineAsync(cts.Token)) != null)
                {
                    if (!line.StartsWith("data:")) continue;
                    JsonNode ev;
                    try { ev = JsonNode.Parse(line.Substring(5).Trim()); } catch { continue; }
                    string type = ev?["type"]?.GetValue<string>() ?? "";
                    if (type == "content_block_start")
                    {
                        int idx = ev["index"]!.GetValue<int>();
                        var cb = ev["content_block"]!.DeepClone().AsObject();
                        while (blocks.Count <= idx) blocks.Add(null);
                        blocks[idx] = cb;
                        if (cb["type"]?.GetValue<string>() == "tool_use") toolJson[idx] = new StringBuilder();
                    }
                    else if (type == "content_block_delta")
                    {
                        int idx = ev["index"]!.GetValue<int>();
                        var d = ev["delta"];
                        string dt = d?["type"]?.GetValue<string>() ?? "";
                        if (dt == "text_delta")
                        {
                            string t = d["text"]?.GetValue<string>() ?? "";
                            if (idx < blocks.Count && blocks[idx] != null) blocks[idx]["text"] = (blocks[idx]["text"]?.GetValue<string>() ?? "") + t;
                            full.Append(t);
                            split.Add(t);
                        }
                        else if (dt == "input_json_delta" && toolJson.TryGetValue(idx, out var sbj))
                            sbj.Append(d["partial_json"]?.GetValue<string>() ?? "");
                    }
                    else if (type == "message_delta")
                        stop = ev["delta"]?["stop_reason"]?.GetValue<string>() ?? stop;
                    else if (type == "error")
                        throw new AiError("La IA devolvió un error: " + (ev["error"]?["message"]?.GetValue<string>() ?? "desconocido") + ".");
                }

                foreach (var kv in toolJson)
                {
                    JsonNode input;
                    try { input = kv.Value.Length == 0 ? new JsonObject() : JsonNode.Parse(kv.Value.ToString()); }
                    catch { input = new JsonObject(); }
                    blocks[kv.Key]["input"] = input ?? new JsonObject();
                }
                var content = new JsonArray(blocks.Where(b => b != null && !(b["type"]?.GetValue<string>() == "text" && (b["text"]?.GetValue<string>() ?? "") == ""))
                                                  .Select(b => (JsonNode)b).ToArray());
                if (stop != "tool_use" || toolJson.Count == 0) return full.ToString();

                messages.Add(new JsonObject { ["role"] = "assistant", ["content"] = content });
                var results = new JsonArray();
                foreach (var b in blocks.Where(b => b != null && b["type"]?.GetValue<string>() == "tool_use"))
                {
                    string name = b["name"]!.GetValue<string>();
                    string output = await RunTool(name, b["input"]);
                    Log.Write("Herramienta " + name + " " + b["input"]?.ToJsonString() + " → " + Text.Preview(output, 120));
                    results.Add(new JsonObject { ["type"] = "tool_result", ["tool_use_id"] = b["id"]!.GetValue<string>(), ["content"] = output });
                }
                messages.Add(new JsonObject { ["role"] = "user", ["content"] = results });
                if (full.Length > 0 && !char.IsWhiteSpace(full[^1]))
                {
                    full.Append(' ');
                    split.Add(" ");
                }
            }
            return full.ToString();
        }

        // ---------------------------------------------------------------- OpenAI y compatibles

        string OpenAiUrl()
        {
            if (Gemini) return GeminiUrl;   // Gemini con la interfaz compatible con OpenAI
            if (Local) return LocalAi.ChatUrl(S);
            string u = S.ApiUrl.Trim().TrimEnd('/');
            if (u == "" || S.AiProvider == "anthropic") return "https://api.openai.com/v1/chat/completions";
            if (u.EndsWith("/chat/completions")) return u;
            if (u.EndsWith("/v1")) return u + "/chat/completions";
            return u + "/v1/chat/completions";
        }

        async Task<string> AskOpenAi(string question, string window, SentenceSplitter split, CancellationToken ct, byte[] image)
        {
            var s = S;
            var messages = new JsonArray { new JsonObject { ["role"] = "system", ["content"] = SystemPrompt(window, question) } };
            foreach (var (role, text) in _history) messages.Add(new JsonObject { ["role"] = role, ["content"] = text });
            if (image == null) messages.Add(new JsonObject { ["role"] = "user", ["content"] = question });
            else
                messages.Add(new JsonObject
                {
                    ["role"] = "user",
                    ["content"] = new JsonArray
                    {
                        new JsonObject { ["type"] = "text", ["text"] = "Esta es una captura de mi pantalla ahora mismo. " + question },
                        new JsonObject
                        {
                            ["type"] = "image_url",
                            ["image_url"] = new JsonObject { ["url"] = "data:image/jpeg;base64," + Convert.ToBase64String(image) },
                        },
                    },
                });
            var tools = new JsonArray(Tools.Select(t => (JsonNode)new JsonObject
            {
                ["type"] = "function",
                ["function"] = new JsonObject { ["name"] = t.name, ["description"] = t.desc, ["parameters"] = t.schema.DeepClone() },
            }).ToArray());
            bool official = s.ApiUrl.Trim() == "" && !Gemini && !Local;   // OpenAI de verdad
            string model = Local ? await LocalAi.ModelFor(s) : s.EffectiveModel;
            // Qwen3 piensa en voz alta por defecto: «/no_think» lo apaga (más rápido y nada que leer de más).
            if (Local && model.StartsWith("qwen3", StringComparison.OrdinalIgnoreCase))
                messages[0]["content"] = messages[0]["content"].GetValue<string>() + "\n/no_think";
            var think = new ThinkFilter();
            var orders = new OrderFilter();
            bool useTools = true;
            var full = new StringBuilder();
            for (int turn = 0; turn < 5; turn++)
            {
                var body = new JsonObject
                {
                    ["model"] = model,
                    ["messages"] = messages.DeepClone(),
                    ["stream"] = true,
                };
                if (useTools) body["tools"] = tools.DeepClone();
                if (official) body["max_completion_tokens"] = 1500;
                if (Gemini && !_geminiNoEffort) body["reasoning_effort"] = "low";   // respuestas habladas: rápido antes que profundo
                using var req = new HttpRequestMessage(HttpMethod.Post, OpenAiUrl());
                if (s.ApiKey.Trim() != "") req.Headers.Add("Authorization", "Bearer " + s.ApiKey.Trim());
                req.Content = new StringContent(body.ToJsonString(), Encoding.UTF8, "application/json");
                using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
                cts.CancelAfter(TimeSpan.FromSeconds(official || Gemini ? 60 : 300));   // un modelo local tarda en cargarse la primera vez
                using var res = await Http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead, cts.Token);
                if (!res.IsSuccessStatusCode)
                {
                    string err = await res.Content.ReadAsStringAsync(cts.Token);
                    // Algunos modelos locales no admiten herramientas: se reintenta sin ellas.
                    if ((int)res.StatusCode == 400 && Gemini && body.ContainsKey("reasoning_effort") && err.Contains("reasoning"))
                    {
                        // Algunos modelos no admiten el ajuste de razonamiento: se repite sin él.
                        _geminiNoEffort = true;
                        turn--;
                        continue;
                    }
                    if ((int)res.StatusCode == 400 && useTools && !official && !Gemini && err.Contains("tool"))
                    {
                        // Sin herramientas, la IA puede pedir órdenes con líneas «ORDEN: …» (las ejecuta JARVIS y no se leen en voz alta).
                        useTools = false;
                        messages[0]["content"] = messages[0]["content"].GetValue<string>() + "\n" + OrderFilter.Instructions;
                        turn--;
                        continue;
                    }
                    if (Local && ((int)res.StatusCode == 404 || err.Contains("not found")))
                    {
                        var have = LocalAi.Installed;
                        try { have = await LocalAi.ListModels(s); } catch { }
                        throw new AiError(have.Count == 0
                            ? "El servidor local no tiene ningún modelo. Descargue uno, por ejemplo con «ollama pull qwen3» o «ollama pull llama3.2»."
                            : "No tengo el modelo «" + model + "». Instalados: " + string.Join(", ", have.Take(5)) + ". Deje «Modelo» vacío en mis ajustes y usaré el primero.");
                    }
                    throw new AiError(Explain((int)res.StatusCode, err, model));
                }
                var calls = new SortedDictionary<int, (string id, string name, StringBuilder args)>();
                // Campos extra de cada llamada (Gemini manda la «firma de pensamiento» y hay que devolverla tal cual).
                var extras = new Dictionary<int, JsonObject>();
                string finish = "";
                var text = new StringBuilder();
                using var stream = await res.Content.ReadAsStreamAsync(cts.Token);
                using var reader = new StreamReader(stream, Encoding.UTF8);
                string line;
                while ((line = await reader.ReadLineAsync(cts.Token)) != null)
                {
                    if (!line.StartsWith("data:")) continue;
                    string data = line.Substring(5).Trim();
                    if (data == "[DONE]") break;
                    JsonNode ev;
                    try { ev = JsonNode.Parse(data); } catch { continue; }
                    var choice = ev?["choices"]?[0];
                    if (choice == null) continue;
                    var delta = choice["delta"];
                    string piece = delta?["content"]?.GetValueKind() == JsonValueKind.String ? delta["content"].GetValue<string>() : "";
                    piece = think.Feed(piece);   // sin el «<think>…</think>» de los modelos que razonan
                    if (!useTools) piece = orders.Feed(piece);
                    if (piece != "")
                    {
                        text.Append(piece);
                        full.Append(piece);
                        split.Add(piece);
                    }
                    if (delta?["tool_calls"] is JsonArray tc)
                        foreach (var call in tc)
                        {
                            int idx = call?["index"]?.GetValue<int>() ?? 0;
                            if (!calls.TryGetValue(idx, out var cur)) cur = ("", "", new StringBuilder());
                            string id = call?["id"]?.GetValue<string>();
                            string nm = call?["function"]?["name"]?.GetValue<string>();
                            string ar = call?["function"]?["arguments"]?.GetValue<string>();
                            if (!string.IsNullOrEmpty(id)) cur.id = id;
                            if (!string.IsNullOrEmpty(nm)) cur.name = nm;
                            if (ar != null) cur.args.Append(ar);
                            calls[idx] = cur;
                            if (call is JsonObject co)
                                foreach (var kv in co)
                                    if (kv.Key != "index" && kv.Key != "id" && kv.Key != "type" && kv.Key != "function" && kv.Value != null)
                                    {
                                        if (!extras.TryGetValue(idx, out var ex)) extras[idx] = ex = new JsonObject();
                                        ex[kv.Key] = kv.Value.DeepClone();
                                    }
                        }
                    if (choice["finish_reason"]?.GetValueKind() == JsonValueKind.String) finish = choice["finish_reason"].GetValue<string>();
                }
                if (!useTools)
                {
                    string rest = orders.Flush();
                    if (rest != "") { text.Append(rest); full.Append(rest); split.Add(rest); }
                    var asked = orders.Take();
                    if (asked.Count > 0 && turn < 4)
                    {
                        var done = new List<string>();
                        foreach (var o in asked)
                        {
                            string output = await RunTool("ejecutar_orden", new JsonObject { ["orden"] = o });
                            Log.Write("Orden de la IA (sin herramientas) «" + o + "» → " + Text.Preview(output, 120));
                            done.Add("«" + o + "»: " + output);
                        }
                        messages.Add(new JsonObject { ["role"] = "assistant", ["content"] = text.Length > 0 ? text.ToString() : "(órdenes enviadas)" });
                        messages.Add(new JsonObject { ["role"] = "user", ["content"] = "[Resultado de las órdenes, no lo dijo el usuario] " + string.Join(" | ", done) +
                                                                                      ". Confirma al usuario en una frase corta lo que hiciste (sin repetir lo que ya dijiste)." });
                        if (full.Length > 0 && !char.IsWhiteSpace(full[^1])) { full.Append(' '); split.Add(" "); }
                        continue;
                    }
                }
                if (calls.Count == 0) return full.ToString();

                // Sin identificador (algunos servidores no lo mandan): se inventa uno.
                foreach (int k in calls.Keys.ToList())
                    if (string.IsNullOrEmpty(calls[k].id)) calls[k] = ("llamada_" + turn + "_" + k, calls[k].name, calls[k].args);
                var tcArr = new JsonArray(calls.Select(kv =>
                {
                    var o = new JsonObject
                    {
                        ["id"] = kv.Value.id,
                        ["type"] = "function",
                        ["function"] = new JsonObject { ["name"] = kv.Value.name, ["arguments"] = kv.Value.args.Length == 0 ? "{}" : kv.Value.args.ToString() },
                    };
                    if (extras.TryGetValue(kv.Key, out var ex)) foreach (var e in ex) o[e.Key] = e.Value?.DeepClone();
                    return (JsonNode)o;
                }).ToArray());
                messages.Add(new JsonObject { ["role"] = "assistant", ["content"] = text.Length > 0 ? text.ToString() : null, ["tool_calls"] = tcArr });
                foreach (var c in calls.Values)
                {
                    JsonNode input;
                    try { input = JsonNode.Parse(c.args.Length == 0 ? "{}" : c.args.ToString()); } catch { input = new JsonObject(); }
                    string output = await RunTool(c.name, input);
                    Log.Write("Herramienta " + c.name + " " + c.args + " → " + Text.Preview(output, 120));
                    messages.Add(new JsonObject { ["role"] = "tool", ["tool_call_id"] = c.id, ["content"] = output });
                }
                if (full.Length > 0 && !char.IsWhiteSpace(full[^1]))
                {
                    full.Append(' ');
                    split.Add(" ");
                }
            }
            return full.ToString();
        }

        // Prueba rápida para el botón «Probar» de los ajustes.
        public async Task<string> TestAsync()
        {
            if (!Ready) return "Falta la clave.";
            var saved = new List<(string, string)>(_history);
            try
            {
                _history.Clear();
                string r = await AskAsync("Responde solo: «Conexión correcta».", "", null, CancellationToken.None);
                return r;
            }
            finally
            {
                _history.Clear();
                _history.AddRange(saved);
            }
        }
    }

    // Para modelos sin herramientas: aparta las líneas «ORDEN: …» del texto (no se leen en voz alta) y las guarda para ejecutarlas.
    public sealed class OrderFilter
    {
        public const string Instructions =
            "No tienes herramientas en esta conversación. Si hay que hacer algo en el equipo, escribe una línea que empiece exactamente por «ORDEN:» " +
            "seguida de la orden (una orden por línea, como las del catálogo), por ejemplo:\nORDEN: sube el brillo\nEsas líneas no se le leen al usuario; " +
            "después recibirás el resultado y lo confirmarás en una frase.";
        const string Prefix = "ORDEN:";
        readonly StringBuilder _line = new StringBuilder();   // principio de la línea actual, mientras pueda ser una orden
        readonly List<string> _found = new List<string>();
        bool _lineStart = true, _inOrder;

        public string Feed(string chunk)
        {
            var o = new StringBuilder();
            foreach (char ch in chunk ?? "")
            {
                if (_inOrder)
                {
                    if (ch == '\n') { Close(); continue; }
                    _line.Append(ch);
                    continue;
                }
                if (_lineStart)
                {
                    if (_line.Length == 0 && (ch == ' ' || ch == '\t' || ch == '*' || ch == '-')) { _line.Append(ch); continue; }
                    _line.Append(ch);
                    string t = _line.ToString().TrimStart(' ', '\t', '*', '-');
                    if (t.Length <= Prefix.Length && Prefix.StartsWith(t, StringComparison.OrdinalIgnoreCase))
                    {
                        if (t.Length == Prefix.Length) { _inOrder = true; _line.Clear(); }
                        continue;
                    }
                    o.Append(_line);
                    _line.Clear();
                    _lineStart = ch == '\n';
                    continue;
                }
                o.Append(ch);
                if (ch == '\n') _lineStart = true;
            }
            return o.ToString();
        }

        void Close()
        {
            string order = _line.ToString().Trim(' ', '«', '»', '"', '*', '.');
            if (order != "") _found.Add(order);
            _line.Clear();
            _inOrder = false;
            _lineStart = true;
        }

        // Al acabar la respuesta: lo que quedó a medias.
        public string Flush()
        {
            if (_inOrder) { Close(); return ""; }
            string rest = _line.ToString();
            _line.Clear();
            _lineStart = true;
            return rest;
        }

        public List<string> Take()
        {
            var l = new List<string>(_found);
            _found.Clear();
            return l;
        }
    }

    // Quita los bloques «<think>…</think>» (razonamiento de Qwen3, DeepSeek…) aunque lleguen partidos en trozos.
    public sealed class ThinkFilter
    {
        readonly StringBuilder _pending = new StringBuilder();
        bool _in;
        const string Open = "<think>", Close = "</think>";

        public string Feed(string chunk)
        {
            _pending.Append(chunk ?? "");
            string p = _pending.ToString();
            _pending.Clear();
            var o = new StringBuilder();
            int i = 0;
            while (i < p.Length)
            {
                if (_in)
                {
                    int e = p.IndexOf(Close, i, StringComparison.Ordinal);
                    if (e < 0)
                    {
                        int keep = Math.Min(Close.Length - 1, p.Length - i);
                        _pending.Append(p, p.Length - keep, keep);   // por si «</think>» llega partido
                        return o.ToString();
                    }
                    _in = false;
                    i = e + Close.Length;
                    while (i < p.Length && (p[i] == '\n' || p[i] == '\r' || p[i] == ' ')) i++;
                    continue;
                }
                int b = p.IndexOf(Open, i, StringComparison.Ordinal);
                if (b < 0)
                {
                    int lt = p.LastIndexOf('<');
                    if (lt >= i && p.Length - lt < Open.Length && Open.StartsWith(p.Substring(lt), StringComparison.Ordinal))
                    {
                        o.Append(p, i, lt - i);
                        _pending.Append(p, lt, p.Length - lt);
                        return o.ToString();
                    }
                    o.Append(p, i, p.Length - i);
                    return o.ToString();
                }
                o.Append(p, i, b - i);
                _in = true;
                i = b + Open.Length;
            }
            return o.ToString();
        }
    }

    // Va entregando frases completas mientras llega el texto, para empezar a hablar antes de que termine.
    public sealed class SentenceSplitter
    {
        readonly Action<string> _out;
        readonly StringBuilder _buf = new StringBuilder();
        readonly StringBuilder _all = new StringBuilder();
        public SentenceSplitter(Action<string> output) { _out = output; }
        public string All => _all.ToString();

        public void Add(string t)
        {
            _all.Append(t);
            if (_out == null) return;
            _buf.Append(t);
            while (true)
            {
                string s = _buf.ToString();
                int cut = -1;
                for (int i = 0; i < s.Length - 1; i++)
                {
                    bool end = (".!?…".IndexOf(s[i]) >= 0 && (s[i + 1] == ' ' || s[i + 1] == '\n')) || s[i] == '\n';
                    if (end && i >= 20)
                    {
                        // no cortar en «3.5» ni en «Sr.»
                        if (s[i] == '.' && i > 0 && char.IsDigit(s[i - 1]) && i + 2 < s.Length && char.IsDigit(s[i + 2])) continue;
                        cut = i + 1;
                        break;
                    }
                }
                if (cut < 0) break;
                string sentence = s.Substring(0, cut).Trim();
                _buf.Remove(0, cut);
                if (sentence != "") _out(sentence);
            }
        }

        public void Flush()
        {
            string rest = _buf.ToString().Trim();
            _buf.Clear();
            if (rest != "" && _out != null) _out(rest);
        }
    }
}
