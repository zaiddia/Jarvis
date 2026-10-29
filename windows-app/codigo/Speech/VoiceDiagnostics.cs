using System;
using System.Collections.Generic;
using System.Linq;
using System.Speech.Recognition;
using System.Threading;
using Jarvis.Core;
using Microsoft.Win32;

namespace Jarvis.Speech
{
    // «¿Por qué no me oye?»: revisa micrófono, permisos, idiomas y reconocedores, y dice qué falta.
    public static class VoiceDiagnostics
    {
        public sealed class Item
        {
            public bool Ok;
            public string Text = "";
            public string Fix = "";        // dónde arreglarlo (ms-settings:…)
        }

        static string RegValue(RegistryKey root, string path, string name)
        {
            try
            {
                using var k = root.OpenSubKey(path);
                return k?.GetValue(name)?.ToString() ?? "";
            }
            catch { return ""; }
        }

        public static List<Item> Run(Settings s, ISpeechInput input)
        {
            var o = new List<Item>();
            const string mic = @"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone";

            bool hasMic = AudioDevices.HasMicrophone();
            o.Add(new Item { Ok = hasMic, Text = hasMic ? "Hay un micrófono predeterminado." : "Windows no tiene ningún micrófono predeterminado.", Fix = "ms-settings:sound" });
            if (hasMic)
            {
                bool muted = AudioDevices.GetMute(true) == true;
                o.Add(new Item { Ok = !muted, Text = muted ? "El micrófono está silenciado en Windows." : "El micrófono no está silenciado.", Fix = "ms-settings:sound" });
            }

            string all = RegValue(Registry.CurrentUser, mic, "Value");
            string machine = RegValue(Registry.LocalMachine, mic, "Value");
            string desktop = RegValue(Registry.CurrentUser, mic + @"\NonPackaged", "Value");
            bool denied = all == "Deny" || machine == "Deny" || desktop == "Deny";
            o.Add(new Item
            {
                Ok = !denied,
                Text = denied ? "Windows no deja usar el micrófono a las aplicaciones de escritorio." : "Las aplicaciones de escritorio pueden usar el micrófono.",
                Fix = "ms-settings:privacy-microphone",
            });

            string online = RegValue(Registry.CurrentUser, @"Software\Microsoft\Speech_OneCore\Settings\OnlineSpeechPrivacy", "HasAccepted");
            bool onlineOk = online == "1";
            o.Add(new Item
            {
                Ok = onlineOk,
                Text = onlineOk ? "El reconocimiento de voz en línea está activado." : "El reconocimiento de voz en línea está desactivado (el reconocimiento moderno lo necesita).",
                Fix = "ms-settings:privacy-speech",
            });

            var modern = ModernListener.SpanishLanguages();
            o.Add(new Item
            {
                Ok = modern.Length > 0,
                Text = modern.Length > 0 ? "Dictado en español disponible: " + string.Join(", ", modern) + "." : "No hay dictado en español instalado en Windows.",
                Fix = "ms-settings:regionlanguage",
            });

            try
            {
                var classic = SpeechRecognitionEngine.InstalledRecognizers().Select(r => r.Culture.Name).ToList();
                bool es = classic.Any(c => c.StartsWith("es"));
                o.Add(new Item
                {
                    Ok = es || modern.Length > 0,
                    Text = classic.Count == 0 ? "No hay reconocedor clásico (no hace falta si el moderno funciona)."
                         : "Reconocedor clásico: " + string.Join(", ", classic) + (es ? "." : " (sin español; no hace falta si el moderno funciona)."),
                    Fix = "ms-settings:speech",
                });
            }
            catch { }

            bool wh = NeuralVoices.WhisperExe != "";
            o.Add(new Item { Ok = true, Text = wh ? "Whisper instalado (lo usa el reconocedor clásico)." : "Whisper no instalado (opcional)." });

            o.Add(new Item
            {
                Ok = input != null && input.Running,
                Text = input != null && input.Running ? "Escuchando con: " + input.RecognizerName + "." : "No está escuchando: " + (input?.Status ?? "sin iniciar") + ".",
            });

            // Nivel: medio segundo de muestras del medidor del micrófono.
            if (input != null && input.Running)
            {
                float max = 0;
                for (int i = 0; i < 10; i++)
                {
                    max = Math.Max(max, AudioDevices.InputPeak());
                    Thread.Sleep(50);
                }
                o.Add(new Item
                {
                    Ok = max > 0.002f,
                    Text = max > 0.002f ? "El micrófono recibe sonido (nivel " + (int)(max * 100) + ")." : "El micrófono no recibe nada de sonido: ¿es el micrófono correcto? ¿está conectado?",
                    Fix = "ms-settings:sound",
                });
            }
            return o;
        }

        public static string Summary(List<Item> items)
        {
            var bad = items.Where(i => !i.Ok).ToList();
            if (bad.Count == 0) return "Todo en orden para escuchar.";
            return "Encontré " + bad.Count + (bad.Count == 1 ? " problema: " : " problemas. El primero: ") + bad[0].Text;
        }
    }
}
