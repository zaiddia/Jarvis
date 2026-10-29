using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Security.Cryptography;
using System.Speech.Synthesis;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Jarvis.Core;

namespace Jarvis.Speech
{
    // La voz de JARVIS: en la nube, Piper (neuronal, en el equipo) o la de Windows. Habla en un hilo aparte.
    public sealed class Speaker : IDisposable
    {
        readonly BlockingCollection<string> _queue = new BlockingCollection<string>();
        readonly Thread _thread;
        Settings _s;
        int _gen;                 // cambia al cortar: lo pendiente de antes se descarta
        int _pending;             // textos pedidos y aún sin terminar
        System.Media.SoundPlayer _player;
        SpeechSynthesizer _sapi;
        readonly object _lock = new object();
        static readonly HttpClient Http = Net.Create(TimeSpan.FromSeconds(25));

        public event Action Started;
        public event Action Finished;
        public string LastError { get; private set; } = "";
        public bool Busy => Volatile.Read(ref _pending) > 0;

        public Speaker(Settings s)
        {
            _s = s;
            _thread = new Thread(Loop) { IsBackground = true, Name = "Voz" };
            _thread.Start();
        }

        public void Update(Settings s)
        {
            _s = s;
            StopPiper();
            lock (_lock)
            {
                _sapi?.Dispose();
                _sapi = null;
            }
        }

        public bool CloudReady => _s.VoiceEngine == "cloud" && CloudKey() != "" && (_s.CloudProvider != "azure" || _s.CloudRegion.Trim() != "");
        public string EngineName => CloudReady ? "en la nube (" + CloudLabel() + ")" : NeuralVoices.PiperReady(_s) ? "neuronal (" + NeuralVoices.VoiceStem + ")" : "de Windows";

        public void Speak(string text)
        {
            if (string.IsNullOrWhiteSpace(text)) return;
            Interlocked.Increment(ref _pending);
            _queue.Add(text);
        }

        public void Stop()
        {
            Interlocked.Increment(ref _gen);
            while (_queue.TryTake(out _)) Interlocked.Decrement(ref _pending);
            lock (_lock)
            {
                try { _player?.Stop(); } catch { }
                try { _sapi?.SpeakAsyncCancelAll(); } catch { }
            }
        }

        // Frases cortas para empezar a hablar enseguida.
        static List<string> Split(string t)
        {
            var o = new List<string>();
            var cur = new StringBuilder();
            for (int i = 0; i < t.Length; i++)
            {
                cur.Append(t[i]);
                bool end = ".!?;:".IndexOf(t[i]) >= 0 && (i + 1 == t.Length || t[i + 1] == ' ' || t[i + 1] == '\n');
                if ((end && cur.ToString().Trim().Length >= 25) || t[i] == '\n')
                {
                    if (cur.ToString().Trim() != "") o.Add(cur.ToString().Trim());
                    cur.Clear();
                }
            }
            string rest = cur.ToString().Trim();
            if (rest != "")
            {
                if (o.Count > 0 && rest.Length < 12) o[o.Count - 1] += " " + rest;
                else o.Add(rest);
            }
            return o;
        }

        // Quita lo que no se debe leer en voz alta (símbolos de formato, enlaces largos).
        static string Speakable(string t)
        {
            var sb = new StringBuilder();
            foreach (char c in t)
            {
                if ("*#_`>|".IndexOf(c) >= 0) continue;
                if (c == '•') { sb.Append(", "); continue; }
                sb.Append(c);
            }
            string s = System.Text.RegularExpressions.Regex.Replace(sb.ToString(), @"https?://\S+", "el enlace");
            return s.Trim();
        }

        void Loop()
        {
            foreach (string raw in _queue.GetConsumingEnumerable())
            {
                int gen = Volatile.Read(ref _gen);
                try
                {
                    Started?.Invoke();
                    string text = Speakable(raw);
                    var parts = Split(text);
                    Task<string> next = null;
                    for (int i = 0; i < parts.Count && gen == Volatile.Read(ref _gen); i++)
                    {
                        string wav = next != null ? next.Result : Synthesize(parts[i]);
                        // Mientras suena esta frase, se prepara la siguiente.
                        if (i + 1 < parts.Count)
                        {
                            string nextText = parts[i + 1];
                            next = Task.Run(() => Synthesize(nextText));
                        }
                        else next = null;
                        if (gen != Volatile.Read(ref _gen)) break;
                        if (wav == null)
                        {
                            SpeakSapi(parts[i], gen);  // la voz elegida falló: la de Windows lo dice
                            continue;
                        }
                        Play(wav);
                        try { File.Delete(wav); } catch { }
                    }
                }
                catch (Exception e)
                {
                    LastError = e.Message;
                    Log.Write("Voz: " + e);
                }
                finally
                {
                    if (Interlocked.Decrement(ref _pending) <= 0)
                    {
                        Interlocked.Exchange(ref _pending, 0);
                        Finished?.Invoke();
                    }
                }
            }
        }

        void Play(string wav)
        {
            System.Media.SoundPlayer p;
            lock (_lock)
            {
                p = _player = new System.Media.SoundPlayer(wav);
            }
            try
            {
                p.Load();
                p.PlaySync();
            }
            catch (Exception e)
            {
                LastError = "no se pudo reproducir: " + e.Message;
            }
            finally
            {
                lock (_lock)
                {
                    if (_player == p) _player = null;
                }
                p.Dispose();
            }
        }

        void SpeakSapi(string text, int gen)
        {
            SpeechSynthesizer sy;
            lock (_lock)
            {
                if (_sapi == null)
                {
                    _sapi = new SpeechSynthesizer();
                    _sapi.SetOutputToDefaultAudioDevice();
                    ChooseWindowsVoice(_sapi, _s);
                }
                _sapi.Rate = Math.Clamp(_s.VoiceRate, -10, 10);
                sy = _sapi;
            }
            if (gen != Volatile.Read(ref _gen)) return;
            try { sy.Speak(text); }
            catch (OperationCanceledException) { }
            catch (Exception e) { LastError = e.Message; }
        }

        public static void ChooseWindowsVoice(SpeechSynthesizer sy, Settings s)
        {
            try
            {
                var voices = sy.GetInstalledVoices().Where(v => v.Enabled).Select(v => v.VoiceInfo).ToList();
                VoiceInfo pick = null;
                if (!string.IsNullOrWhiteSpace(s.WindowsVoice))
                    pick = voices.FirstOrDefault(v => Text.Squash(v.Name).Contains(Text.Squash(s.WindowsVoice)));
                var spanish = voices.Where(v => v.Culture.TwoLetterISOLanguageName == "es").ToList();
                var wantGender = s.IsViernes ? VoiceGender.Female : VoiceGender.Male;
                pick ??= spanish.FirstOrDefault(v => v.Gender == wantGender && (v.Name.Contains("Natural") || v.Name.Contains("Neural")));
                pick ??= spanish.FirstOrDefault(v => v.Gender == wantGender);
                pick ??= spanish.FirstOrDefault();
                if (pick != null) sy.SelectVoice(pick.Name);
            }
            catch { }
        }

        public static List<string> WindowsVoices()
        {
            try
            {
                using var sy = new SpeechSynthesizer();
                return sy.GetInstalledVoices().Where(v => v.Enabled).Select(v => v.VoiceInfo.Name + " (" + v.VoiceInfo.Culture.Name + ")").ToList();
            }
            catch { return new List<string>(); }
        }

        // Devuelve la ruta de un WAV o null si no se pudo (entonces habla la voz de Windows).
        string Synthesize(string text)
        {
            if (CloudReady)
            {
                string w = CloudSynthesize(text);
                if (w != null) return w;
                Log.Write("Voz en la nube: " + LastError);
            }
            if (NeuralVoices.PiperExe != "" && (_s.VoiceEngine == "neural" || _s.VoiceEngine == "cloud"))
            {
                string w = PiperSynthesize(text);
                if (w != null) return w;
                Log.Write("Piper: " + LastError);
            }
            return null;
        }

        static int _fileNo;
        static string NewWav() => Path.Combine(NeuralVoices.TempDir, "voz-" + Interlocked.Increment(ref _fileNo) % 8 + ".wav");

        // ---------------------------------------------------------------- Piper (se queda abierto: carga la voz una vez)

        Process _piper;
        string _piperKey = "";
        string _piperDir = "";

        string ScaleArg() => (Math.Clamp(1.0 / (1.0 + _s.VoiceRate * 0.08), 0.65, 1.4)).ToString("0.00", System.Globalization.CultureInfo.InvariantCulture);

        void StopPiper()
        {
            try { _piper?.StandardInput.Close(); } catch { }
            try { if (_piper != null && !_piper.WaitForExit(300)) _piper.Kill(); } catch { }
            _piper?.Dispose();
            _piper = null;
            _piperKey = "";
        }

        string PiperSynthesize(string text)
        {
            lock (_lock)
            {
                try
                {
                    int speaker = NeuralVoices.PiperSpeakers > 1 ? Math.Clamp(_s.PiperSpeaker, 0, NeuralVoices.PiperSpeakers - 1) : -1;
                    string key = NeuralVoices.PiperVoice + "|" + ScaleArg() + "|" + speaker;
                    if (_piper == null || _piper.HasExited || _piperKey != key)
                    {
                        StopPiper();
                        _piperDir = Path.Combine(NeuralVoices.TempDir, "piper");
                        Directory.CreateDirectory(_piperDir);
                        foreach (var f in Directory.GetFiles(_piperDir, "*.wav")) try { File.Delete(f); } catch { }
                        var psi = new ProcessStartInfo(NeuralVoices.PiperExe)
                        {
                            UseShellExecute = false,
                            CreateNoWindow = true,
                            RedirectStandardInput = true,
                            RedirectStandardOutput = true,
                            RedirectStandardError = true,
                            StandardInputEncoding = new UTF8Encoding(false),
                        };
                        foreach (var a in new[] { "--model", NeuralVoices.PiperVoice, "--output_dir", _piperDir, "--length_scale", ScaleArg(), "--sentence_silence", "0.15" })
                            psi.ArgumentList.Add(a);
                        if (speaker >= 0)
                        {
                            psi.ArgumentList.Add("--speaker");
                            psi.ArgumentList.Add(speaker.ToString());
                        }
                        _piper = Process.Start(psi);
                        _piper.ErrorDataReceived += (s, e) => { };
                        _piper.BeginErrorReadLine();
                        _piperKey = key;
                    }
                    _piper.StandardInput.WriteLine(text.Replace('\n', ' ').Replace('\r', ' '));
                    _piper.StandardInput.Flush();
                    // Piper escribe la ruta del WAV cuando termina (la primera vez tarda más: carga la voz).
                    var line = _piper.StandardOutput.ReadLineAsync();
                    if (!line.Wait(TimeSpan.FromSeconds(20)) || line.Result == null)
                    {
                        LastError = "Piper tardó demasiado";
                        StopPiper();
                        return null;
                    }
                    string found = Directory.GetFiles(_piperDir, "*.wav").OrderByDescending(f => File.GetLastWriteTimeUtc(f)).FirstOrDefault();
                    if (found == null)
                    {
                        LastError = "Piper no creó el audio";
                        return null;
                    }
                    // Esperar a que Piper cierre el archivo.
                    for (int i = 0; i < 100; i++)
                    {
                        try
                        {
                            using (new FileStream(found, FileMode.Open, FileAccess.Read, FileShare.None)) { }
                            break;
                        }
                        catch (IOException) { Thread.Sleep(10); }
                    }
                    string wav = NewWav();
                    File.Move(found, wav, true);
                    return wav;
                }
                catch (Exception e)
                {
                    LastError = e.Message;
                    StopPiper();
                    return null;
                }
            }
        }

        // ---------------------------------------------------------------- voz en la nube

        string CloudKey()
        {
            if (!string.IsNullOrWhiteSpace(_s.CloudKey)) return _s.CloudKey.Trim();
            if (_s.CloudProvider == "openai" && _s.AiProvider == "openai" && string.IsNullOrWhiteSpace(_s.ApiUrl)) return _s.ApiKey.Trim();
            // Gemini: la misma clave que la IA (aunque ahora piense con otro proveedor).
            if (_s.CloudProvider == "gemini")
            {
                if (_s.AiProvider == "gemini" && _s.ApiKey.Trim() != "") return _s.ApiKey.Trim();
                if (_s.ApiKeys != null && _s.ApiKeys.TryGetValue("gemini", out var g) && g.Trim() != "") return g.Trim();
            }
            return "";
        }

        string CloudVoice()
        {
            if (!string.IsNullOrWhiteSpace(_s.CloudVoice)) return _s.CloudVoice.Trim();
            if (_s.IsViernes)
                return _s.CloudProvider == "elevenlabs" ? "21m00Tcm4TlvDq8ikWAM" : _s.CloudProvider == "azure" ? "es-CO-SalomeNeural" : _s.CloudProvider == "gemini" ? "Kore" : "marin";
            return _s.CloudProvider == "elevenlabs" ? "JBFqnCBsd6RMkjVDRZzb" : _s.CloudProvider == "azure" ? "es-CO-GonzaloNeural" : _s.CloudProvider == "gemini" ? "Charon" : "cedar";
        }

        public string CloudLabel() => (_s.CloudProvider == "elevenlabs" ? "ElevenLabs" : _s.CloudProvider == "azure" ? "Azure" : _s.CloudProvider == "gemini" ? "Gemini" : "OpenAI") + " · " + CloudVoice();

        string CloudSynthesize(string text)
        {
            try
            {
                string voice = CloudVoice();
                string style = _s.CloudProvider == "openai" || _s.CloudProvider == "gemini" ? (_s.IsViernes && _s.CloudStyle.StartsWith("Habla como JARVIS")
                                                                  ? "Habla como VIERNES, la asistente digital de Tony Stark: voz femenina cálida y segura, cercana y directa, con un toque de humor. En español neutro."
                                                                  : _s.CloudStyle) : "";
                // Caché de frases cortas: suenan al instante y no se pagan dos veces.
                string cacheDir = Path.Combine(NeuralVoices.Dir, "cache");
                string cacheFile = null;
                if (text.Length <= 80)
                {
                    string keyText = _s.CloudProvider + "|" + voice + "|" + _s.CloudModel + "|" + style + "|" + _s.VoiceRate + "|" + text;
                    string hash = Convert.ToHexString(SHA1.HashData(Encoding.UTF8.GetBytes(keyText))).Substring(0, 20);
                    cacheFile = Path.Combine(cacheDir, hash + ".wav");
                    if (File.Exists(cacheFile))
                    {
                        string copy = NewWav();
                        File.Copy(cacheFile, copy, true);
                        return copy;
                    }
                }
                HttpRequestMessage req;
                if (_s.CloudProvider == "elevenlabs")
                {
                    req = new HttpRequestMessage(HttpMethod.Post, "https://api.elevenlabs.io/v1/text-to-speech/" + voice + "?output_format=pcm_24000");
                    req.Headers.Add("xi-api-key", CloudKey());
                    double speed = Math.Clamp(1.0 + _s.VoiceRate * 0.03, 0.7, 1.2);
                    string body = JsonSerializer.Serialize(new
                    {
                        text,
                        model_id = string.IsNullOrWhiteSpace(_s.CloudModel) ? "eleven_multilingual_v2" : _s.CloudModel.Trim(),
                        voice_settings = new { stability = 0.5, similarity_boost = 0.75, speed },
                    });
                    req.Content = new StringContent(body, Encoding.UTF8, "application/json");
                }
                else if (_s.CloudProvider == "azure")
                {
                    req = new HttpRequestMessage(HttpMethod.Post, "https://" + _s.CloudRegion.Trim() + ".tts.speech.microsoft.com/cognitiveservices/v1");
                    req.Headers.Add("Ocp-Apim-Subscription-Key", CloudKey());
                    req.Headers.Add("X-Microsoft-OutputFormat", "raw-24khz-16bit-mono-pcm");
                    req.Headers.Add("User-Agent", "JARVIS");
                    string lang = voice.Length >= 5 ? voice.Substring(0, 5) : "es-ES";
                    int pct = Math.Clamp(_s.VoiceRate * 5, -50, 50);
                    string ssml = "<speak version='1.0' xml:lang='" + lang + "'><voice name='" + System.Security.SecurityElement.Escape(voice) + "'><prosody rate='" +
                                  (pct >= 0 ? "+" : "") + pct + "%'>" + System.Security.SecurityElement.Escape(text) + "</prosody></voice></speak>";
                    req.Content = new StringContent(ssml, Encoding.UTF8, "application/ssml+xml");
                }
                else if (_s.CloudProvider == "gemini")
                {
                    // Voces de Gemini: muy expresivas, siguen el estilo y hablan español con naturalidad.
                    req = new HttpRequestMessage(HttpMethod.Post, "https://generativelanguage.googleapis.com/v1beta/interactions");
                    req.Headers.Add("x-goog-api-key", CloudKey());
                    string st = style + (_s.VoiceRate > 2 ? " Ritmo rápido." : _s.VoiceRate < -2 ? " Ritmo pausado." : "");
                    var content = new Dictionary<string, object> { ["type"] = "text", ["text"] = text };
                    if (st.Trim() != "") content["annotations"] = new[] { new Dictionary<string, object> { ["type"] = "speech_metadata", ["style"] = st.Trim() } };
                    var payload = new Dictionary<string, object>
                    {
                        ["model"] = string.IsNullOrWhiteSpace(_s.CloudModel) ? "gemini-3.8-flash-tts" : _s.CloudModel.Trim(),
                        ["input"] = new[] { new Dictionary<string, object> { ["type"] = "user_input", ["content"] = new[] { content } } },
                        ["response_format"] = new Dictionary<string, object> { ["type"] = "audio" },
                        ["generation_config"] = new Dictionary<string, object> { ["speech_config"] = new[] { new Dictionary<string, object> { ["voice"] = voice } } },
                    };
                    req.Content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json");
                }
                else
                {
                    req = new HttpRequestMessage(HttpMethod.Post, "https://api.openai.com/v1/audio/speech");
                    req.Headers.Add("Authorization", "Bearer " + CloudKey());
                    var payload = new Dictionary<string, object>
                    {
                        ["model"] = string.IsNullOrWhiteSpace(_s.CloudModel) ? "gpt-4o-mini-tts" : _s.CloudModel.Trim(),
                        ["voice"] = voice,
                        ["input"] = text,
                        ["response_format"] = "pcm",
                    };
                    if (style != "") payload["instructions"] = style;
                    req.Content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json");
                }
                using var res = Http.Send(req);
                byte[] pcm = res.Content.ReadAsByteArrayAsync().Result;
                if (!res.IsSuccessStatusCode)
                {
                    int code = (int)res.StatusCode;
                    LastError = code == 401 || code == 403 ? "la clave del servicio de voz no es válida"
                              : code == 404 ? "no existe esa voz o ese modelo"
                              : code == 429 ? "límite o saldo agotado en el servicio de voz"
                              : "el servicio de voz respondió con el error " + code;
                    return null;
                }
                if (_s.CloudProvider == "gemini")
                {
                    pcm = GeminiAudio(pcm);
                    if (pcm == null)
                    {
                        LastError = "Gemini no devolvió audio";
                        return null;
                    }
                }
                if (pcm.Length < 4800)
                {
                    LastError = "el servicio de voz devolvió un audio vacío";
                    return null;
                }
                string wav = NewWav();
                WriteWav(wav, pcm, 24000);
                if (cacheFile != null)
                {
                    Directory.CreateDirectory(cacheDir);
                    File.Copy(wav, cacheFile, true);
                    TrimCache(cacheDir);
                }
                return wav;
            }
            catch (Exception e)
            {
                LastError = "no hay conexión con el servicio de voz (" + e.Message + ")";
                return null;
            }
        }

        // La respuesta de Gemini es JSON con el audio en base64 (WAV de 24 kHz o PCM sin cabecera).
        static byte[] GeminiAudio(byte[] json)
        {
            try
            {
                using var doc = JsonDocument.Parse(json);
                string b64 = FindAudio(doc.RootElement, false);
                if (b64 == null) return null;
                byte[] a = Convert.FromBase64String(b64.Replace('-', '+').Replace('_', '/').PadRight((b64.Length + 3) / 4 * 4, '='));
                // Sin la cabecera WAV (se busca el bloque «data»).
                if (a.Length > 44 && a[0] == 'R' && a[1] == 'I' && a[2] == 'F' && a[3] == 'F')
                {
                    int pos = 12;
                    while (pos + 8 <= a.Length)
                    {
                        int len = BitConverter.ToInt32(a, pos + 4);
                        if (a[pos] == 'd' && a[pos + 1] == 'a' && a[pos + 2] == 't' && a[pos + 3] == 'a')
                            return a.Skip(pos + 8).Take(Math.Min(len, a.Length - pos - 8)).ToArray();
                        if (len < 0) break;
                        pos += 8 + len + (len & 1);
                    }
                    return a.Skip(44).ToArray();
                }
                return a;
            }
            catch (Exception e)
            {
                Log.Write("Voz de Gemini: " + e.Message);
                return null;
            }
        }

        static string FindAudio(JsonElement e, bool audio)
        {
            if (e.ValueKind == JsonValueKind.Object)
            {
                foreach (var p in e.EnumerateObject())
                    if ((p.Name == "type" || p.Name == "mime_type" || p.Name == "mimeType") && p.Value.ValueKind == JsonValueKind.String && (p.Value.GetString() ?? "").Contains("audio"))
                        audio = true;
                if (audio && e.TryGetProperty("data", out var d) && d.ValueKind == JsonValueKind.String && (d.GetString() ?? "").Length > 200) return d.GetString();
                foreach (var p in e.EnumerateObject())
                {
                    string r = FindAudio(p.Value, audio);
                    if (r != null) return r;
                }
            }
            else if (e.ValueKind == JsonValueKind.Array)
                foreach (var x in e.EnumerateArray())
                {
                    string r = FindAudio(x, audio);
                    if (r != null) return r;
                }
            return null;
        }

        static int _cacheWrites;
        static void TrimCache(string dir)
        {
            if (++_cacheWrites % 25 != 0) return;
            try
            {
                var files = new DirectoryInfo(dir).GetFiles("*.wav").OrderBy(f => f.LastWriteTimeUtc).ToList();
                for (int i = 0; i + 300 < files.Count; i++) files[i].Delete();
            }
            catch { }
        }

        public static void WriteWav(string path, byte[] pcm, int rate)
        {
            int len = pcm.Length & ~1;
            using var f = new FileStream(path, FileMode.Create, FileAccess.Write);
            using var w = new BinaryWriter(f);
            w.Write(Encoding.ASCII.GetBytes("RIFF"));
            w.Write(36 + len);
            w.Write(Encoding.ASCII.GetBytes("WAVEfmt "));
            w.Write(16);
            w.Write((short)1);
            w.Write((short)1);
            w.Write(rate);
            w.Write(rate * 2);
            w.Write((short)2);
            w.Write((short)16);
            w.Write(Encoding.ASCII.GetBytes("data"));
            w.Write(len);
            w.Write(pcm, 0, len);
        }

        public void Dispose()
        {
            Stop();
            _queue.CompleteAdding();
            StopPiper();
            lock (_lock) { _sapi?.Dispose(); }
        }
    }
}
