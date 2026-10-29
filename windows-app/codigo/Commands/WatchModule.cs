using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Jarvis.Core;

namespace Jarvis.Commands
{
    // Avisos del sistema: batería baja, disco casi lleno y programas que dejan de responder.
    public sealed class WatchModule
    {
        readonly Engine E;
        DateTime _last = DateTime.MinValue, _diskWarned = DateTime.MinValue;
        int _batteryStep = 100;          // último umbral avisado (20, 10, 5)
        IntPtr _hungWin;
        DateTime _hungSince;
        readonly HashSet<IntPtr> _hungWarned = new HashSet<IntPtr>();

        public WatchModule(Engine e) { E = e; }

        void Warn(string text)
        {
            E.Host.Notify(E.S.Name + " · aviso", text);
            E.Integrations?.Mirror("Aviso del equipo", text);
            E.Host.Say(text);
        }

        public void Tick()
        {
            if (!E.S.SystemAlerts) return;
            var now = DateTime.Now;
            CheckHung(now);
            if ((now - _last).TotalSeconds < 60) return;
            _last = now;
            try { CheckBattery(); } catch { }
            try { CheckDisk(now); } catch { }
        }

        void CheckBattery()
        {
            if (!Native.GetSystemPowerStatus(out var p) || p.BatteryFlag == 128 || p.BatteryLifePercent == 255) return;
            int pct = p.BatteryLifePercent;
            if (p.ACLineStatus == 1)
            {
                _batteryStep = 100;   // enchufado: se rearman los avisos
                return;
            }
            foreach (int step in new[] { 5, 10, 20 })
            {
                if (pct <= step && _batteryStep > step)
                {
                    _batteryStep = step;
                    Warn(step <= 5
                        ? "Batería al " + pct + " por ciento" + E.Sir + ". Enchufe el equipo ya o se apagará."
                        : "Batería al " + pct + " por ciento" + E.Sir + ". Convendría enchufar el equipo.");
                    return;
                }
            }
        }

        void CheckDisk(DateTime now)
        {
            if ((now - _diskWarned).TotalHours < 6) return;
            foreach (var d in DriveInfo.GetDrives().Where(x => x.IsReady && x.DriveType == DriveType.Fixed))
            {
                double free = d.AvailableFreeSpace / 1073741824.0;
                double pct = 100.0 * d.AvailableFreeSpace / Math.Max(1, d.TotalSize);
                if (free < 5 || pct < 4)
                {
                    _diskWarned = now;
                    Warn("El disco " + d.Name.TrimEnd('\\', ':') + " está casi lleno: quedan " + Text.Num(free, 1) + " gigas" + E.Sir + ". Puede pedirme que vacíe la papelera.");
                    return;
                }
            }
        }

        // Una ventana en primer plano que no responde durante 10 segundos.
        void CheckHung(DateTime now)
        {
            IntPtr w = Native.GetForegroundWindow();
            if (w == IntPtr.Zero || !Native.IsHungAppWindow(w))
            {
                _hungWin = IntPtr.Zero;
                return;
            }
            if (w != _hungWin)
            {
                _hungWin = w;
                _hungSince = now;
                return;
            }
            if ((now - _hungSince).TotalSeconds < 10 || _hungWarned.Contains(w)) return;
            _hungWarned.Add(w);
            if (_hungWarned.Count > 50) _hungWarned.Clear();
            string title = Text.Preview(Native.WindowTitle(w), 40);
            Warn((title != "" ? "«" + title + "»" : "La ventana activa") + " no responde" + E.Sir + ". Si quiere, dígame «cierra " + (title != "" ? title : "esta ventana") + "».");
        }
    }
}
