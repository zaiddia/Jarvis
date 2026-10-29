using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.Json;

namespace Jarvis.Core
{
    // Registro en %APPDATA%\JARVIS\jarvis.log (se recorta solo) y en la salida de depuración.
    public static class Log
    {
        static readonly object Lock = new object();
        static string PathLog => System.IO.Path.Combine(Settings.Folder, "jarvis.log");

        public static void Write(string text)
        {
            string line = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff") + "  " + text;
            System.Diagnostics.Debug.WriteLine(line);
            lock (Lock)
            {
                try
                {
                    var fi = new FileInfo(PathLog);
                    if (fi.Exists && fi.Length > 2 * 1024 * 1024)
                    {
                        string old = PathLog + ".1";
                        if (File.Exists(old)) File.Delete(old);
                        File.Move(PathLog, old);
                    }
                    File.AppendAllText(PathLog, line + Environment.NewLine, Encoding.UTF8);
                }
                catch { }
            }
        }
    }

    // Almacén sencillo de datos de JARVIS (recordatorios, listas, memoria…) en %APPDATA%\JARVIS\datos.json.
    public static class Store
    {
        static readonly object Lock = new object();
        static Dictionary<string, JsonElement> _data;
        static string PathData => System.IO.Path.Combine(Settings.Folder, "datos.json");
        static readonly JsonSerializerOptions Opt = new JsonSerializerOptions
        {
            WriteIndented = true,
            Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        };

        static void Ensure()
        {
            if (_data != null) return;
            try
            {
                _data = File.Exists(PathData)
                    ? JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(File.ReadAllText(PathData)) ?? new Dictionary<string, JsonElement>()
                    : new Dictionary<string, JsonElement>();
            }
            catch (Exception e)
            {
                Log.Write("Datos dañados, empiezo de cero: " + e.Message);
                _data = new Dictionary<string, JsonElement>();
            }
        }

        public static T Get<T>(string key, T fallback)
        {
            lock (Lock)
            {
                Ensure();
                if (!_data.TryGetValue(key, out var el)) return fallback;
                try { return el.Deserialize<T>(Opt) ?? fallback; }
                catch { return fallback; }
            }
        }

        public static void Set<T>(string key, T value)
        {
            lock (Lock)
            {
                Ensure();
                _data[key] = JsonSerializer.SerializeToElement(value, Opt);
                try
                {
                    string tmp = PathData + ".tmp";
                    File.WriteAllText(tmp, JsonSerializer.Serialize(_data, Opt), Encoding.UTF8);
                    File.Move(tmp, PathData, true);
                }
                catch (Exception e)
                {
                    Log.Write("No pude guardar los datos: " + e.Message);
                }
            }
        }

        public static string FilePath => PathData;

        public static void Reload()
        {
            lock (Lock) { _data = null; }
        }
    }
}
