using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.InteropServices;
using Jarvis.Core;

namespace Jarvis.Speech
{
    // Baja el volumen de las demás aplicaciones (música, vídeos) mientras JARVIS escucha o habla,
    // y lo devuelve después. Si el programa se cierra a medias, se restaura al volver a abrirlo.
    public static class Ducker
    {
        [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
        class MMDeviceEnumeratorCom { }

        [ComImport, Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        interface IMMDeviceEnumerator
        {
            int EnumAudioEndpoints(int dataFlow, int stateMask, out IntPtr devices);
            int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice endpoint);
        }

        [ComImport, Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        interface IMMDevice
        {
            int Activate(ref Guid iid, int clsCtx, IntPtr activationParams, [MarshalAs(UnmanagedType.IUnknown)] out object iface);
        }

        [ComImport, Guid("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        interface IAudioSessionManager2
        {
            int GetAudioSessionControl(IntPtr guid, int flags, out IntPtr control);
            int GetSimpleAudioVolume(IntPtr guid, int flags, out IntPtr volume);
            int GetSessionEnumerator(out IAudioSessionEnumerator e);
        }

        [ComImport, Guid("E2F5BB11-0570-40CA-ACDD-3AA01277DEE8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        interface IAudioSessionEnumerator
        {
            int GetCount(out int count);
            int GetSession(int index, [MarshalAs(UnmanagedType.IUnknown)] out object session);
        }

        // IAudioSessionControl2 (incluye los métodos de IAudioSessionControl, en orden).
        [ComImport, Guid("BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        interface IAudioSessionControl2
        {
            int GetState(out int state);
            int GetDisplayName(out IntPtr name);
            int SetDisplayName(IntPtr name, IntPtr ctx);
            int GetIconPath(out IntPtr path);
            int SetIconPath(IntPtr path, IntPtr ctx);
            int GetGroupingParam(out Guid g);
            int SetGroupingParam(IntPtr g, IntPtr ctx);
            int RegisterAudioSessionNotification(IntPtr n);
            int UnregisterAudioSessionNotification(IntPtr n);
            int GetSessionIdentifier(out IntPtr id);
            int GetSessionInstanceIdentifier(out IntPtr id);
            int GetProcessId(out uint pid);
            [PreserveSig] int IsSystemSoundsSession();
            int SetDuckingPreference([MarshalAs(UnmanagedType.Bool)] bool optOut);
        }

        [ComImport, Guid("87CE5498-68D6-44E5-9215-6DA47EF883D8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        interface ISimpleAudioVolume
        {
            int SetMasterVolume(float level, ref Guid ctx);
            int GetMasterVolume(out float level);
            int SetMute([MarshalAs(UnmanagedType.Bool)] bool mute, ref Guid ctx);
            int GetMute([MarshalAs(UnmanagedType.Bool)] out bool mute);
        }

        sealed class Saved
        {
            public uint Pid { get; set; }
            public float Level { get; set; }
        }

        static readonly object Lock = new object();
        static List<Saved> _saved;
        static readonly Guid Ctx = new Guid("6A4E1D2B-7F37-4C53-9E33-4A5D2C3B4A11");

        static List<(uint pid, ISimpleAudioVolume vol)> Sessions()
        {
            var o = new List<(uint, ISimpleAudioVolume)>();
            var en = (IMMDeviceEnumerator)new MMDeviceEnumeratorCom();
            if (en.GetDefaultAudioEndpoint(0, 0, out IMMDevice dev) != 0 || dev == null) return o;
            Guid iid = typeof(IAudioSessionManager2).GUID;
            dev.Activate(ref iid, 23, IntPtr.Zero, out object mgrObj);
            if (mgrObj is not IAudioSessionManager2) return o;   // sin sesiones de audio (p. ej. sin altavoces)
            var mgr = (IAudioSessionManager2)mgrObj;
            mgr.GetSessionEnumerator(out var list);
            if (list == null) return o;
            list.GetCount(out int n);
            uint me = (uint)Environment.ProcessId;
            for (int i = 0; i < n; i++)
            {
                try
                {
                    list.GetSession(i, out object sObj);
                    var ctl = (IAudioSessionControl2)sObj;
                    if (ctl.IsSystemSoundsSession() == 0) continue;   // S_OK = sonidos del sistema
                    ctl.GetProcessId(out uint pid);
                    ctl.GetState(out int state);
                    if (pid == me || pid == 0 || state != 1) continue;  // 1 = activa (sonando)
                    o.Add((pid, (ISimpleAudioVolume)sObj));
                }
                catch { }
            }
            return o;
        }

        public static bool Ducked
        {
            get { lock (Lock) return _saved != null; }
        }

        public static void Duck(int percent)
        {
            lock (Lock)
            {
                if (_saved != null) return;
                try
                {
                    var saved = new List<Saved>();
                    float factor = Math.Clamp(percent, 0, 90) / 100f;
                    Guid g = Ctx;
                    foreach (var (pid, vol) in Sessions())
                    {
                        vol.GetMasterVolume(out float lvl);
                        if (lvl <= 0.01f) continue;
                        saved.Add(new Saved { Pid = pid, Level = lvl });
                        vol.SetMasterVolume(lvl * factor, ref g);
                    }
                    _saved = saved;
                    if (saved.Count > 0) Store.Set("volumenes-bajados", saved);
                }
                catch (Exception e)
                {
                    Log.Write("Bajar volumen: " + e.Message);
                }
            }
        }

        public static void Restore()
        {
            lock (Lock)
            {
                var saved = _saved ?? Store.Get<List<Saved>>("volumenes-bajados", null);
                _saved = null;
                if (saved == null || saved.Count == 0) return;
                try
                {
                    Guid g = Ctx;
                    var all = Sessions();
                    // También las sesiones ya en pausa: buscar en todas, no solo las que suenan.
                    foreach (var s in saved)
                        foreach (var (pid, vol) in AllSessionsOf(s.Pid, all))
                            vol.SetMasterVolume(s.Level, ref g);
                }
                catch (Exception e)
                {
                    Log.Write("Devolver volumen: " + e.Message);
                }
                Store.Set("volumenes-bajados", new List<Saved>());
            }
        }

        static IEnumerable<(uint, ISimpleAudioVolume)> AllSessionsOf(uint pid, List<(uint pid, ISimpleAudioVolume vol)> active)
        {
            foreach (var a in active) if (a.pid == pid) yield return a;
            foreach (var x in InactiveSessions(pid)) yield return x;
        }

        static List<(uint, ISimpleAudioVolume)> InactiveSessions(uint wanted)
        {
            var o = new List<(uint, ISimpleAudioVolume)>();
            try
            {
                var en = (IMMDeviceEnumerator)new MMDeviceEnumeratorCom();
                if (en.GetDefaultAudioEndpoint(0, 0, out IMMDevice dev) != 0 || dev == null) return o;
                Guid iid = typeof(IAudioSessionManager2).GUID;
                dev.Activate(ref iid, 23, IntPtr.Zero, out object mgrObj);
            if (mgrObj is not IAudioSessionManager2) return o;   // sin sesiones de audio (p. ej. sin altavoces)
                ((IAudioSessionManager2)mgrObj).GetSessionEnumerator(out var list);
            if (list == null) return o;
                list.GetCount(out int n);
                for (int i = 0; i < n; i++)
                {
                    list.GetSession(i, out object sObj);
                    var ctl = (IAudioSessionControl2)sObj;
                    ctl.GetProcessId(out uint pid);
                    ctl.GetState(out int state);
                    if (pid == wanted && state != 1) o.Add((pid, (ISimpleAudioVolume)sObj));
                }
            }
            catch { }
            return o;
        }

        // ---------------------------------------------------------------- volumen de una aplicación («baja el volumen de Spotify»)

        static List<(uint pid, ISimpleAudioVolume vol)> EverySession()
        {
            var o = new List<(uint, ISimpleAudioVolume)>();
            var en = (IMMDeviceEnumerator)new MMDeviceEnumeratorCom();
            if (en.GetDefaultAudioEndpoint(0, 0, out IMMDevice dev) != 0 || dev == null) return o;
            Guid iid = typeof(IAudioSessionManager2).GUID;
            dev.Activate(ref iid, 23, IntPtr.Zero, out object mgrObj);
            if (mgrObj is not IAudioSessionManager2) return o;   // sin sesiones de audio (p. ej. sin altavoces)
            ((IAudioSessionManager2)mgrObj).GetSessionEnumerator(out var list);
            if (list == null) return o;
            list.GetCount(out int n);
            for (int i = 0; i < n; i++)
            {
                try
                {
                    list.GetSession(i, out object sObj);
                    var ctl = (IAudioSessionControl2)sObj;
                    if (ctl.IsSystemSoundsSession() == 0) continue;
                    ctl.GetProcessId(out uint pid);
                    if (pid == 0) continue;
                    o.Add((pid, (ISimpleAudioVolume)sObj));
                }
                catch { }
            }
            return o;
        }

        static string ProcName(uint pid)
        {
            try { using var p = System.Diagnostics.Process.GetProcessById((int)pid); return p.ProcessName.ToLowerInvariant(); }
            catch { return ""; }
        }

        // Nombres de las apps que tienen sonido ahora (para decirlas).
        public static List<string> AppsWithSound()
        {
            var names = new List<string>();
            try
            {
                foreach (var (pid, _) in EverySession())
                {
                    string n = ProcName(pid);
                    if (n != "" && !names.Contains(n)) names.Add(n);
                }
            }
            catch { }
            return names;
        }

        // change: recibe el volumen actual (0…1) y devuelve el nuevo; mute: null = no tocar.
        // Devuelve el nuevo volumen de la primera sesión encontrada, o -1 si la app no tiene sonido.
        public static float SetAppVolume(string[] processNames, Func<float, float> change, bool? mute = null)
        {
            float result = -1;
            lock (Lock)
            {
                try
                {
                    Guid g = Ctx;
                    foreach (var (pid, vol) in EverySession())
                    {
                        string n = ProcName(pid);
                        if (n == "" || !processNames.Any(x => n == x || (x.Length >= 4 && n.StartsWith(x)))) continue;
                        vol.GetMasterVolume(out float cur);
                        // Si JARVIS la tenía bajada, el cambio parte del volumen real.
                        var saved = _saved?.FirstOrDefault(x => x.Pid == pid);
                        float baseLevel = saved != null ? saved.Level : cur;
                        float next = Math.Clamp(change(baseLevel), 0f, 1f);
                        if (saved != null) saved.Level = next;
                        else vol.SetMasterVolume(next, ref g);
                        if (mute.HasValue) vol.SetMute(mute.Value, ref g);
                        if (result < 0) result = next;
                    }
                }
                catch (Exception e)
                {
                    Log.Write("Volumen de app: " + e.Message);
                }
            }
            return result;
        }
    }
}
