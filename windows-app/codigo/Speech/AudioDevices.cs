using System;
using System.Runtime.InteropServices;

namespace Jarvis.Speech
{
    // Core Audio de Windows: volumen, silencio y medidor de nivel de la salida y del micrófono.
    public static class AudioDevices
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

        [ComImport, Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        interface IAudioEndpointVolume
        {
            int RegisterControlChangeNotify(IntPtr notify);
            int UnregisterControlChangeNotify(IntPtr notify);
            int GetChannelCount(out uint count);
            int SetMasterVolumeLevel(float levelDB, ref Guid ctx);
            int SetMasterVolumeLevelScalar(float level, ref Guid ctx);
            int GetMasterVolumeLevel(out float levelDB);
            int GetMasterVolumeLevelScalar(out float level);
            int SetChannelVolumeLevel(uint channel, float levelDB, ref Guid ctx);
            int SetChannelVolumeLevelScalar(uint channel, float level, ref Guid ctx);
            int GetChannelVolumeLevel(uint channel, out float levelDB);
            int GetChannelVolumeLevelScalar(uint channel, out float level);
            int SetMute([MarshalAs(UnmanagedType.Bool)] bool mute, ref Guid ctx);
            int GetMute([MarshalAs(UnmanagedType.Bool)] out bool mute);
        }

        [ComImport, Guid("C02216F6-8C67-4B5B-9D00-D008E73E0064"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        interface IAudioMeterInformation
        {
            int GetPeakValue(out float peak);
        }

        const int eRender = 0, eCapture = 1, eConsole = 0, CLSCTX_ALL = 23;
        static Guid IID_Volume = typeof(IAudioEndpointVolume).GUID;
        static Guid IID_Meter = typeof(IAudioMeterInformation).GUID;

        static T Endpoint<T>(int flow, Guid iid) where T : class
        {
            try
            {
                var en = (IMMDeviceEnumerator)new MMDeviceEnumeratorCom();
                if (en.GetDefaultAudioEndpoint(flow, eConsole, out IMMDevice dev) != 0 || dev == null) return null;
                Guid g = iid;
                dev.Activate(ref g, CLSCTX_ALL, IntPtr.Zero, out object o);
                return o as T;
            }
            catch
            {
                return null;
            }
        }

        // ---- volumen de la salida (0…1)
        public static float GetVolume()
        {
            var v = Endpoint<IAudioEndpointVolume>(eRender, IID_Volume);
            if (v == null) return -1;
            v.GetMasterVolumeLevelScalar(out float l);
            return l;
        }

        public static bool SetVolume(float level)
        {
            var v = Endpoint<IAudioEndpointVolume>(eRender, IID_Volume);
            if (v == null) return false;
            Guid g = Guid.Empty;
            v.SetMasterVolumeLevelScalar(Math.Clamp(level, 0f, 1f), ref g);
            if (level > 0) v.SetMute(false, ref g);
            return true;
        }

        public static bool? GetMute(bool mic = false)
        {
            var v = Endpoint<IAudioEndpointVolume>(mic ? eCapture : eRender, IID_Volume);
            if (v == null) return null;
            v.GetMute(out bool m);
            return m;
        }

        public static bool SetMute(bool mute, bool mic = false)
        {
            var v = Endpoint<IAudioEndpointVolume>(mic ? eCapture : eRender, IID_Volume);
            if (v == null) return false;
            Guid g = Guid.Empty;
            v.SetMute(mute, ref g);
            return true;
        }

        // ---- medidor de la salida (para las barras del reactor mientras habla)
        static IAudioMeterInformation _meter;
        static DateTime _meterAt = DateTime.MinValue;

        public static float OutputPeak()
        {
            try
            {
                if (_meter == null && (DateTime.Now - _meterAt).TotalSeconds > 5)
                {
                    _meterAt = DateTime.Now;
                    _meter = Endpoint<IAudioMeterInformation>(eRender, IID_Meter);
                }
                if (_meter == null) return 0;
                _meter.GetPeakValue(out float p);
                return p;
            }
            catch
            {
                _meter = null;
                return 0;
            }
        }

        // ---- medidor del micrófono (solo lee el nivel que ya mide Windows; no graba nada)
        static IAudioMeterInformation _inMeter;
        static DateTime _inMeterAt = DateTime.MinValue;

        public static float InputPeak()
        {
            try
            {
                if (_inMeter == null && (DateTime.Now - _inMeterAt).TotalSeconds > 5)
                {
                    _inMeterAt = DateTime.Now;
                    _inMeter = Endpoint<IAudioMeterInformation>(eCapture, IID_Meter);
                }
                if (_inMeter == null) return 0;
                _inMeter.GetPeakValue(out float p);
                return p;
            }
            catch
            {
                _inMeter = null;
                return 0;
            }
        }

        public static bool HasMicrophone() => Endpoint<IAudioEndpointVolume>(eCapture, IID_Volume) != null;
    }
}
