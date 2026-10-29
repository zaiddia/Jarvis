using System;
using System.Runtime.InteropServices;
using System.Text;

namespace Jarvis.Core
{
    // Llamadas a Windows que .NET no trae.
    public static class Native
    {
        // ---- ventanas
        [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
        [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
        [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
        [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
        [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr hWnd);
        [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
        [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder sb, int max);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr hWnd, StringBuilder sb, int max);
        [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
        [DllImport("user32.dll")] public static extern IntPtr GetWindow(IntPtr hWnd, uint cmd);
        public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
        [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc cb, IntPtr lParam);
        [DllImport("user32.dll")] public static extern bool LockWorkStation();
        [DllImport("user32.dll")] public static extern bool SetWindowDisplayAffinity(IntPtr hWnd, uint affinity);
        [DllImport("user32.dll")] public static extern bool RegisterHotKey(IntPtr hWnd, int id, uint mods, uint vk);
        [DllImport("user32.dll")] public static extern bool UnregisterHotKey(IntPtr hWnd, int id);
        [DllImport("user32.dll")] public static extern short GetAsyncKeyState(int vk);
        [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);
        [DllImport("user32.dll")] public static extern bool IsHungAppWindow(IntPtr hWnd);

        // ---- inactividad (solo cuánto hace de la última tecla o movimiento de ratón; no qué se hizo)
        [StructLayout(LayoutKind.Sequential)] struct LASTINPUTINFO { public uint cbSize; public uint dwTime; }
        [DllImport("user32.dll")] static extern bool GetLastInputInfo(ref LASTINPUTINFO plii);
        public static double IdleSeconds()
        {
            var li = new LASTINPUTINFO { cbSize = (uint)Marshal.SizeOf<LASTINPUTINFO>() };
            if (!GetLastInputInfo(ref li)) return 0;
            return unchecked((uint)Environment.TickCount - li.dwTime) / 1000.0;
        }

        public const int SW_MINIMIZE = 6, SW_MAXIMIZE = 3, SW_RESTORE = 9;
        public const uint WM_CLOSE = 0x0010, WM_SYSCOMMAND = 0x0112, WM_HOTKEY = 0x0312;
        public const int SC_MONITORPOWER = 0xF170;
        public const uint MOD_ALT = 1, MOD_CONTROL = 2, MOD_SHIFT = 4, MOD_WIN = 8, MOD_NOREPEAT = 0x4000;
        public const uint WDA_NONE = 0, WDA_EXCLUDEFROMCAPTURE = 0x11;

        public static string WindowTitle(IntPtr h)
        {
            var sb = new StringBuilder(512);
            GetWindowText(h, sb, sb.Capacity);
            return sb.ToString();
        }

        public static string WindowClass(IntPtr h)
        {
            var sb = new StringBuilder(256);
            GetClassName(h, sb, sb.Capacity);
            return sb.ToString();
        }

        // ---- teclado
        [StructLayout(LayoutKind.Sequential)]
        struct INPUT
        {
            public uint type;
            public InputUnion U;
        }

        [StructLayout(LayoutKind.Explicit)]
        struct InputUnion
        {
            [FieldOffset(0)] public KEYBDINPUT ki;
            [FieldOffset(0)] public MOUSEINPUT mi;
        }

        [StructLayout(LayoutKind.Sequential)]
        struct KEYBDINPUT
        {
            public ushort wVk, wScan;
            public uint dwFlags, time;
            public IntPtr dwExtraInfo;
        }

        [StructLayout(LayoutKind.Sequential)]
        struct MOUSEINPUT
        {
            public int dx, dy;
            public uint mouseData, dwFlags, time;
            public IntPtr dwExtraInfo;
        }

        [DllImport("user32.dll", SetLastError = true)] static extern uint SendInput(uint n, INPUT[] inputs, int size);

        const uint KEYEVENTF_EXTENDEDKEY = 1, KEYEVENTF_KEYUP = 2, KEYEVENTF_UNICODE = 4;

        static bool IsExtended(ushort vk) => vk == 0x5B || vk == 0x5C || (vk >= 0xAD && vk <= 0xB3) || (vk >= 0x21 && vk <= 0x2E);

        // Pulsa una combinación (todas abajo y luego arriba en orden inverso).
        public static void SendKeys(params ushort[] keys)
        {
            var list = new System.Collections.Generic.List<INPUT>();
            foreach (var k in keys) list.Add(Key(k, false));
            for (int i = keys.Length - 1; i >= 0; i--) list.Add(Key(keys[i], true));
            SendInput((uint)list.Count, list.ToArray(), Marshal.SizeOf<INPUT>());
        }

        static INPUT Key(ushort vk, bool up)
        {
            var i = new INPUT { type = 1 };
            i.U.ki.wVk = vk;
            i.U.ki.dwFlags = (IsExtended(vk) ? KEYEVENTF_EXTENDEDKEY : 0) | (up ? KEYEVENTF_KEYUP : 0);
            return i;
        }

        // Escribe un texto tal cual (Unicode), en la ventana activa.
        public static void TypeText(string text)
        {
            var list = new System.Collections.Generic.List<INPUT>();
            foreach (char ch in text)
            {
                if (ch == '\r') continue;
                if (ch == '\n')
                {
                    list.Add(Key(0x0D, false));
                    list.Add(Key(0x0D, true));
                    continue;
                }
                var d = new INPUT { type = 1 };
                d.U.ki.wScan = ch;
                d.U.ki.dwFlags = KEYEVENTF_UNICODE;
                var u = d;
                u.U.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP;
                list.Add(d);
                list.Add(u);
            }
            if (list.Count > 0) SendInput((uint)list.Count, list.ToArray(), Marshal.SizeOf<INPUT>());
        }

        // «Ctrl+Alt+J», «F9», «Win+Shift+S» → modificadores y tecla virtual.
        public static bool ParseHotkey(string text, out uint mods, out uint vk)
        {
            mods = 0;
            vk = 0;
            if (string.IsNullOrWhiteSpace(text)) return false;
            foreach (string raw in text.Split('+'))
            {
                string p = Text.Squash(raw);
                switch (p)
                {
                    case "ctrl": case "control": mods |= MOD_CONTROL; continue;
                    case "alt": mods |= MOD_ALT; continue;
                    case "shift": case "mayus": case "mayusculas": mods |= MOD_SHIFT; continue;
                    case "win": case "windows": mods |= MOD_WIN; continue;
                    case "espacio": case "space": vk = 0x20; continue;
                    case "enter": case "intro": vk = 0x0D; continue;
                    case "tab": vk = 0x09; continue;
                    case "esc": case "escape": vk = 0x1B; continue;
                    case "supr": case "delete": vk = 0x2E; continue;
                    case "inicio": case "home": vk = 0x24; continue;
                    case "fin": case "end": vk = 0x23; continue;
                    case "arriba": case "up": vk = 0x26; continue;
                    case "abajo": case "down": vk = 0x28; continue;
                    case "izquierda": case "left": vk = 0x25; continue;
                    case "derecha": case "right": vk = 0x27; continue;
                    case "pausa": case "pause": vk = 0x13; continue;
                }
                if (p.Length >= 2 && p[0] == 'f' && int.TryParse(p.Substring(1), out int f) && f >= 1 && f <= 24) { vk = (uint)(0x70 + f - 1); continue; }
                if (p.Length == 1 && char.IsLetterOrDigit(p[0])) { vk = char.ToUpperInvariant(p[0]); continue; }
                return false;
            }
            return vk != 0;
        }

        // ---- sistema
        [DllImport("shell32.dll")] public static extern int SHQueryUserNotificationState(out int state);
        [DllImport("shell32.dll")] public static extern int SHEmptyRecycleBin(IntPtr hwnd, string root, uint flags);
        [DllImport("powrprof.dll")] public static extern bool SetSuspendState(bool hibernate, bool force, bool disableWake);
        [DllImport("dwmapi.dll")] public static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);
        [DllImport("user32.dll")] public static extern uint GetClipboardSequenceNumber();

        [StructLayout(LayoutKind.Sequential)]
        public struct SYSTEM_POWER_STATUS
        {
            public byte ACLineStatus, BatteryFlag, BatteryLifePercent, SystemStatusFlag;
            public int BatteryLifeTime, BatteryFullLifeTime;
        }
        [DllImport("kernel32.dll")] public static extern bool GetSystemPowerStatus(out SYSTEM_POWER_STATUS s);

        [StructLayout(LayoutKind.Sequential)]
        public struct MEMORYSTATUSEX
        {
            public uint dwLength, dwMemoryLoad;
            public ulong ullTotalPhys, ullAvailPhys, ullTotalPageFile, ullAvailPageFile, ullTotalVirtual, ullAvailVirtual, ullAvailExtendedVirtual;
        }
        [DllImport("kernel32.dll")] public static extern bool GlobalMemoryStatusEx(ref MEMORYSTATUSEX m);
        [DllImport("kernel32.dll")] public static extern bool GetSystemTimes(out long idle, out long kernel, out long user);

        // ¿Otra aplicación está usando el micrófono ahora (una llamada, una grabación)? Lo dice el registro de privacidad de Windows.
        public static bool MicInUseByOthers()
        {
            try
            {
                string me = (Environment.ProcessPath ?? "").Replace('\\', '#');
                using var root = Microsoft.Win32.Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone");
                if (root == null) return false;
                bool InUse(Microsoft.Win32.RegistryKey k) =>
                    k.GetValue("LastUsedTimeStart") is long start && start != 0 && k.GetValue("LastUsedTimeStop") is long stop && stop == 0;
                foreach (var name in root.GetSubKeyNames())
                {
                    using var k = root.OpenSubKey(name);
                    if (k == null) continue;
                    if (name == "NonPackaged")
                    {
                        foreach (var app in k.GetSubKeyNames())
                        {
                            if (string.Equals(app, me, StringComparison.OrdinalIgnoreCase)) continue;
                            using var a = k.OpenSubKey(app);
                            if (a != null && InUse(a)) return true;
                        }
                    }
                    else if (InUse(k)) return true;
                }
            }
            catch { }
            return false;
        }
    }
}
