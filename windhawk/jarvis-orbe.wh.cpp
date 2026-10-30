// ==WindhawkMod==
// @id              jarvis-orbe
// @name            Orbe de Jarvis en la barra de tareas
// @description     Un orbe junto al reloj que muestra si Jarvis escucha, piensa o habla. Clic: háblale. Clic derecho: menú de órdenes
// @version         1.0.0
// @author          zaiddia
// @github          https://github.com/zaiddia
// @include         explorer.exe
// @compilerOptions -lwinhttp -lcomctl32 -lgdi32 -luser32 -lshell32
// ==/WindhawkMod==

// ==WindhawkModReadme==
/*
# Orbe de Jarvis

Pone el **reactor de Jarvis** en la barra de tareas, junto al reloj. Necesita
**Jarvis 7.2 o posterior** abierto en el mismo usuario de Windows.

| El orbe | Significa |
|---|---|
| Cian suave, respirando | Jarvis está atento (di «Jarvis») |
| Cian brillante | Te está escuchando |
| Ámbar girando | Está pensando |
| Verde latiendo | Está hablando |
| Gris | Micrófono en pausa |
| Apagado, con una raya | Jarvis no está abierto |
| Punto ámbar arriba | Hay un temporizador en marcha (pasa el ratón para ver cuánto falta) |

- **Clic**: háblale (como decir «Jarvis» o pulsar Ctrl+Alt+Espacio). Lo puedes
  cambiar por «mostrar u ocultar el panel» en los ajustes del mod.
- **Clic derecho**: menú con *Escribir una orden*, *Modo clase*,
  *Temporizador de 5 minutos*, *¿Qué tengo pendiente?*, *Pausar el micrófono*,
  *Prueba completa* y *Ajustes*.
- Si Jarvis está cerrado, el clic lo abre (activa antes *Ajustes › Integraciones ›
  Integrar Jarvis con Windows*).

El orbe habla con Jarvis solo dentro de tu equipo (127.0.0.1), con el código
secreto que Jarvis guarda en `%APPDATA%\Jarvis\enlace.json`. Se oculta solo
cuando hay un programa en pantalla completa.
*/
// ==/WindhawkModReadme==

// ==WindhawkModSettings==
/*
- position: clock
  $name: Dónde va el orbe
  $options:
  - clock: A la izquierda del reloj y los iconos de la bandeja
  - left: En el extremo izquierdo de la barra de tareas
- offset: 0
  $name: Desplazamiento (píxeles)
  $description: Muévelo a la izquierda (positivo) o a la derecha (negativo) si tapa algún icono.
- size: 34
  $name: Tamaño del orbe (píxeles, a 100 % de escala)
- click: listen
  $name: Al hacer clic
  $options:
  - listen: Hablarle a Jarvis
  - toggle: Mostrar u ocultar el panel de Jarvis
- hideFullscreen: true
  $name: Ocultarlo con programas en pantalla completa
- linkFile: ""
  $name: Archivo de enlace (solo si usas Jarvis en modo USB)
  $description: Vacío = %APPDATA%\Jarvis\enlace.json. En modo USB, la ruta a datos\enlace.json de tu memoria.
*/
// ==/WindhawkModSettings==

#include <windows.h>
#include <commctrl.h>
#include <shellapi.h>
#include <winhttp.h>

#include <math.h>
#include <stdio.h>
#include <wchar.h>

#include <string>

namespace {

// ------------------------------------------------------------------ ajustes
struct Settings {
    bool atClock = true;
    int offset = 0;
    int size = 34;
    bool clickToggles = false;
    bool hideFullscreen = true;
    std::wstring linkFile;
};
Settings g_settings;
CRITICAL_SECTION g_lock;                 // protege g_settings, g_status, el puerto y el código

void LoadSettings() {
    Settings s;
    PCWSTR pos = Wh_GetStringSetting(L"position");
    s.atClock = !pos || wcscmp(pos, L"left") != 0;
    Wh_FreeStringSetting(pos);
    s.offset = Wh_GetIntSetting(L"offset");
    s.size = Wh_GetIntSetting(L"size");
    if (s.size < 18 || s.size > 64) {
        s.size = 34;
    }
    PCWSTR click = Wh_GetStringSetting(L"click");
    s.clickToggles = click && wcscmp(click, L"toggle") == 0;
    Wh_FreeStringSetting(click);
    s.hideFullscreen = Wh_GetIntSetting(L"hideFullscreen") != 0;
    PCWSTR lf = Wh_GetStringSetting(L"linkFile");
    if (lf && *lf) {
        s.linkFile = lf;
    }
    Wh_FreeStringSetting(lf);
    EnterCriticalSection(&g_lock);
    g_settings = s;
    LeaveCriticalSection(&g_lock);
}

Settings CurrentSettings() {
    EnterCriticalSection(&g_lock);
    Settings s = g_settings;
    LeaveCriticalSection(&g_lock);
    return s;
}

// ------------------------------------------------------------------ estado compartido
enum class Mode { Off, Idle, Awaiting, Thinking, Speaking, Muted };

struct Status {
    Mode mode = Mode::Off;
    int timers = 0;
    int next = -1;
    bool visible = false;
    bool live = false;
};

Status g_status;
std::wstring g_host = L"127.0.0.1";
int g_port = 0;
std::string g_token;

HANDLE g_thread = nullptr;
HANDLE g_poller = nullptr;
HANDLE g_quit = nullptr;
HANDLE g_single = nullptr;
HWND g_orb = nullptr;
HWND g_tip = nullptr;
TOOLINFOW g_ti = {};
bool g_hover = false;

const wchar_t kClass[] = L"JarvisOrbeWindhawk";
constexpr UINT WM_APP_STATUS = WM_APP + 1;
constexpr UINT WM_APP_RELOAD = WM_APP + 2;
constexpr UINT_PTR kAnimTimer = 1;
constexpr UINT_PTR kPlaceTimer = 2;

// ------------------------------------------------------------------ enlace con Jarvis
std::wstring LinkPath() {
    std::wstring custom = CurrentSettings().linkFile;
    if (!custom.empty()) {
        return custom;
    }
    wchar_t buf[MAX_PATH] = {};
    DWORD n = GetEnvironmentVariableW(L"APPDATA", buf, MAX_PATH);
    if (!n || n >= MAX_PATH) {
        return L"";
    }
    return std::wstring(buf) + L"\\Jarvis\\enlace.json";
}

// Valor de "clave": "texto" o "clave": número en un JSON pequeño y conocido.
std::string JsonStr(const std::string& j, const char* key) {
    std::string k = std::string("\"") + key + "\"";
    size_t p = j.find(k);
    if (p == std::string::npos) {
        return "";
    }
    p = j.find(':', p + k.size());
    if (p == std::string::npos) {
        return "";
    }
    p++;
    while (p < j.size() && (j[p] == ' ' || j[p] == '\t')) {
        p++;
    }
    if (p < j.size() && j[p] == '"') {
        size_t e = j.find('"', p + 1);
        return e == std::string::npos ? "" : j.substr(p + 1, e - p - 1);
    }
    size_t e = p;
    while (e < j.size() && j[e] != ',' && j[e] != '}' && j[e] != ' ') {
        e++;
    }
    return j.substr(p, e - p);
}

bool ReadLinkFile() {
    std::wstring path = LinkPath();
    if (path.empty()) {
        return false;
    }
    HANDLE f = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                           nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (f == INVALID_HANDLE_VALUE) {
        return false;
    }
    char buf[2048] = {};
    DWORD got = 0;
    BOOL ok = ReadFile(f, buf, sizeof(buf) - 1, &got, nullptr);
    CloseHandle(f);
    if (!ok || !got) {
        return false;
    }
    std::string j(buf, got);
    std::string token = JsonStr(j, "token");
    int port = atoi(JsonStr(j, "port").c_str());
    if (token.size() < 32 || port <= 0 || port > 65535) {
        return false;
    }
    EnterCriticalSection(&g_lock);
    g_token = token;
    g_port = port;
    LeaveCriticalSection(&g_lock);
    return true;
}

// Petición a Jarvis (solo 127.0.0.1). Devuelve el código HTTP (0 si no hubo conexión).
int Http(const wchar_t* method, const wchar_t* path, const std::string& body, std::string* out) {
    EnterCriticalSection(&g_lock);
    int port = g_port;
    std::string token = g_token;
    LeaveCriticalSection(&g_lock);
    if (!port || token.empty()) {
        return 0;
    }
    int status = 0;
    HINTERNET s = WinHttpOpen(L"JarvisOrbe/1.0", WINHTTP_ACCESS_TYPE_NO_PROXY, WINHTTP_NO_PROXY_NAME,
                              WINHTTP_NO_PROXY_BYPASS, 0);
    if (!s) {
        return 0;
    }
    WinHttpSetTimeouts(s, 800, 800, 1500, 3000);
    HINTERNET c = WinHttpConnect(s, g_host.c_str(), (INTERNET_PORT)port, 0);
    HINTERNET r = c ? WinHttpOpenRequest(c, method, path, nullptr, WINHTTP_NO_REFERER,
                                         WINHTTP_DEFAULT_ACCEPT_TYPES, 0)
                    : nullptr;
    if (r) {
        std::wstring hdr = L"X-Jarvis-Token: ";
        hdr += std::wstring(token.begin(), token.end());
        hdr += L"\r\nContent-Type: application/json\r\n";
        BOOL sent = WinHttpSendRequest(r, hdr.c_str(), (DWORD)-1L,
                                       body.empty() ? WINHTTP_NO_REQUEST_DATA : (LPVOID)body.data(),
                                       (DWORD)body.size(), (DWORD)body.size(), 0);
        if (sent && WinHttpReceiveResponse(r, nullptr)) {
            DWORD code = 0, len = sizeof(code);
            WinHttpQueryHeaders(r, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER, WINHTTP_HEADER_NAME_BY_INDEX,
                                &code, &len, WINHTTP_NO_HEADER_INDEX);
            status = (int)code;
            if (out) {
                out->clear();
                DWORD avail = 0;
                while (WinHttpQueryDataAvailable(r, &avail) && avail && out->size() < 8192) {
                    std::string chunk(avail, '\0');
                    DWORD read = 0;
                    if (!WinHttpReadData(r, &chunk[0], avail, &read) || !read) {
                        break;
                    }
                    out->append(chunk.data(), read);
                }
            }
        }
        WinHttpCloseHandle(r);
    }
    if (c) {
        WinHttpCloseHandle(c);
    }
    WinHttpCloseHandle(s);
    return status;
}

Mode ParseMode(const std::string& j) {
    std::string mode = JsonStr(j, "mode");
    std::string mic = JsonStr(j, "mic");
    if (mode == "speaking") {
        return Mode::Speaking;
    }
    if (mode == "thinking") {
        return Mode::Thinking;
    }
    if (mode == "awaiting") {
        return Mode::Awaiting;
    }
    if (mic != "on") {
        return Mode::Muted;
    }
    return Mode::Idle;
}

DWORD WINAPI PollThread(LPVOID) {
    DWORD lastRead = 0;
    int fails = 0;
    while (WaitForSingleObject(g_quit, fails ? 1500 : 350) == WAIT_TIMEOUT) {
        if (!g_port || (fails && GetTickCount() - lastRead > 4000)) {
            ReadLinkFile();                         // Jarvis cambia el código cada vez que arranca
            lastRead = GetTickCount();
        }
        std::string body;
        Status st;
        if (Http(L"GET", L"/api/orbe", "", &body) == 200) {
            fails = 0;
            st.mode = ParseMode(body);
            st.timers = atoi(JsonStr(body, "timers").c_str());
            st.next = atoi(JsonStr(body, "next").c_str());
            st.visible = JsonStr(body, "visible") == "true";
            st.live = JsonStr(body, "live") == "true";
        } else {
            fails++;
            st.mode = Mode::Off;
        }
        EnterCriticalSection(&g_lock);
        bool changed = st.mode != g_status.mode || st.timers != g_status.timers || st.next != g_status.next;
        g_status = st;
        LeaveCriticalSection(&g_lock);
        if (changed && g_orb) {
            PostMessageW(g_orb, WM_APP_STATUS, 0, 0);
        }
    }
    return 0;
}

struct SendJob {
    std::string url;
};

DWORD WINAPI SendThread(LPVOID p) {
    SendJob* job = (SendJob*)p;
    std::string body = "{\"url\": \"" + job->url + "\", \"origen\": \"orbe\"}";
    int code = Http(L"POST", L"/api/enlace", body, nullptr);
    if (code == 403 || code == 0) {
        // Código viejo (Jarvis se reinició) o Jarvis cerrado: releer el enlace y, si no, abrir Jarvis.
        if (ReadLinkFile()) {
            code = Http(L"POST", L"/api/enlace", body, nullptr);
        }
        if (code != 200) {
            std::wstring w(job->url.begin(), job->url.end());
            ShellExecuteW(nullptr, L"open", w.c_str(), nullptr, nullptr, SW_SHOWNORMAL);
        }
    }
    delete job;
    return 0;
}

void Send(const char* url) {
    SendJob* job = new SendJob{url};
    HANDLE t = CreateThread(nullptr, 0, SendThread, job, 0, nullptr);
    if (t) {
        CloseHandle(t);
    } else {
        delete job;
    }
}

// ------------------------------------------------------------------ dibujo (alfa por píxel, sin GDI+)
struct Rgb {
    float r, g, b;
};

Rgb ModeColor(Mode m) {
    switch (m) {
        case Mode::Awaiting: return {0.18f, 0.90f, 1.00f};
        case Mode::Thinking: return {1.00f, 0.71f, 0.28f};
        case Mode::Speaking: return {0.24f, 1.00f, 0.60f};
        case Mode::Muted: return {0.55f, 0.60f, 0.66f};
        case Mode::Off: return {0.35f, 0.38f, 0.42f};
        default: return {0.18f, 0.90f, 1.00f};
    }
}

float Clamp01(float v) {
    return v < 0 ? 0 : (v > 1 ? 1 : v);
}

void Render(HWND hwnd) {
    RECT rc;
    GetWindowRect(hwnd, &rc);
    int w = rc.right - rc.left, h = rc.bottom - rc.top;
    if (w <= 0 || h <= 0) {
        return;
    }
    EnterCriticalSection(&g_lock);
    Status st = g_status;
    LeaveCriticalSection(&g_lock);

    BITMAPINFO bi = {};
    bi.bmiHeader.biSize = sizeof(bi.bmiHeader);
    bi.bmiHeader.biWidth = w;
    bi.bmiHeader.biHeight = -h;
    bi.bmiHeader.biPlanes = 1;
    bi.bmiHeader.biBitCount = 32;
    bi.bmiHeader.biCompression = BI_RGB;
    void* bits = nullptr;
    HDC screen = GetDC(nullptr);
    HDC mem = CreateCompatibleDC(screen);
    HBITMAP bmp = CreateDIBSection(screen, &bi, DIB_RGB_COLORS, &bits, nullptr, 0);
    if (!bmp || !bits) {
        DeleteDC(mem);
        ReleaseDC(nullptr, screen);
        return;
    }
    HGDIOBJ old = SelectObject(mem, bmp);

    float t = GetTickCount() / 1000.0f;
    Rgb c = ModeColor(st.mode);
    float cx = w / 2.0f, cy = h / 2.0f;
    float R = (w < h ? w : h) / 2.0f - 1.5f;
    float breathe = 0.5f + 0.5f * sinf(t * (st.mode == Mode::Speaking ? 9.0f : st.mode == Mode::Awaiting ? 4.0f : 1.6f));
    float glow = st.mode == Mode::Off ? 0.0f : (st.mode == Mode::Idle || st.mode == Mode::Muted ? 0.35f + 0.25f * breathe : 0.6f + 0.4f * breathe);
    if (g_hover) {
        glow = glow < 0.8f ? 0.8f : glow;
    }
    float spin = t * 4.0f;

    unsigned int* px = (unsigned int*)bits;
    for (int y = 0; y < h; y++) {
        for (int x = 0; x < w; x++) {
            float dx = x + 0.5f - cx, dy = y + 0.5f - cy;
            float d = sqrtf(dx * dx + dy * dy);
            float a = 0, r = 0, g = 0, b = 0;
            // halo exterior
            float hd = (d - R * 0.78f) / (R * 0.16f);
            float cd = d / (R * 0.45f);
            float halo = (expf(-hd * hd) * 0.55f + expf(-cd * cd) * 0.45f) * glow * (d < R ? 1.0f : 0.0f);
            // anillo
            float ring = Clamp01(1.0f - fabsf(d - R * 0.78f) / 1.6f);
            if (st.mode == Mode::Thinking) {
                float ang = atan2f(dy, dx);
                float seg = 0.5f + 0.5f * cosf(ang * 3.0f - spin);
                ring *= 0.35f + 0.65f * seg;
            }
            // núcleo
            float core = Clamp01(1.0f - (d - R * 0.28f) / 1.4f);
            float coreLevel = st.mode == Mode::Off ? 0.25f : 0.55f + 0.45f * glow;
            // fondo oscuro del disco (para que se lea sobre cualquier barra)
            float disc = Clamp01(1.0f - (d - R) / 1.2f) * 0.78f;

            a = disc;
            r = g = b = 0.02f * disc;                       // casi negro
            float add = halo + ring * 0.95f + core * coreLevel;
            r += c.r * add;
            g += c.g * add;
            b += c.b * add;
            a = Clamp01(a + halo + ring + core * coreLevel);
            if (st.mode == Mode::Off) {                      // raya: Jarvis cerrado
                float line = Clamp01(1.0f - fabsf(dx + dy) / 1.3f) * (d < R * 0.7f ? 1.0f : 0.0f);
                r += 0.6f * line; g += 0.6f * line; b += 0.6f * line;
                a = Clamp01(a + line);
            }
            if (st.timers > 0) {                             // punto ámbar arriba a la derecha
                float tx = cx + R * 0.68f, ty = cy - R * 0.68f;
                float td = sqrtf((x + 0.5f - tx) * (x + 0.5f - tx) + (y + 0.5f - ty) * (y + 0.5f - ty));
                float dot = Clamp01(1.0f - (td - R * 0.17f) / 1.1f);
                r = r * (1 - dot) + 1.0f * dot;
                g = g * (1 - dot) + 0.71f * dot;
                b = b * (1 - dot) + 0.28f * dot;
                a = Clamp01(a + dot);
            }
            // alfa premultiplicado
            r = Clamp01(r); g = Clamp01(g); b = Clamp01(b);
            unsigned A = (unsigned)(a * 255 + 0.5f);
            unsigned Rr = (unsigned)(Clamp01(r) * a * 255 + 0.5f);
            unsigned Gg = (unsigned)(Clamp01(g) * a * 255 + 0.5f);
            unsigned Bb = (unsigned)(Clamp01(b) * a * 255 + 0.5f);
            if (Rr > A) Rr = A;
            if (Gg > A) Gg = A;
            if (Bb > A) Bb = A;
            px[y * w + x] = (A << 24) | (Rr << 16) | (Gg << 8) | Bb;
        }
    }

    POINT src = {0, 0};
    POINT dst = {rc.left, rc.top};
    SIZE sz = {w, h};
    BLENDFUNCTION bf = {AC_SRC_OVER, 0, 255, AC_SRC_ALPHA};
    UpdateLayeredWindow(hwnd, screen, &dst, &sz, mem, &src, 0, &bf, ULW_ALPHA);
    SelectObject(mem, old);
    DeleteObject(bmp);
    DeleteDC(mem);
    ReleaseDC(nullptr, screen);
}

// ------------------------------------------------------------------ posición
bool ForegroundIsFullscreen() {
    HWND fg = GetForegroundWindow();
    if (!fg || fg == GetShellWindow() || fg == GetDesktopWindow()) {
        return false;
    }
    wchar_t cls[64] = {};
    GetClassNameW(fg, cls, 64);
    if (!wcscmp(cls, L"WorkerW") || !wcscmp(cls, L"Progman") || !wcscmp(cls, L"Shell_TrayWnd")) {
        return false;
    }
    RECT r;
    if (!GetWindowRect(fg, &r)) {
        return false;
    }
    MONITORINFO mi = {};
    mi.cbSize = sizeof(mi);
    if (!GetMonitorInfoW(MonitorFromWindow(fg, MONITOR_DEFAULTTONEAREST), &mi)) {
        return false;
    }
    return r.left <= mi.rcMonitor.left && r.top <= mi.rcMonitor.top && r.right >= mi.rcMonitor.right &&
           r.bottom >= mi.rcMonitor.bottom;
}

void Place() {
    if (!g_orb) {
        return;
    }
    Settings cs = CurrentSettings();
    HWND tray = FindWindowW(L"Shell_TrayWnd", nullptr);
    RECT tr;
    if (!tray || !GetWindowRect(tray, &tr) || !IsWindowVisible(tray)) {
        ShowWindow(g_orb, SW_HIDE);
        return;
    }
    UINT dpi = 96;
    typedef UINT(WINAPI * GetDpiForWindowFn)(HWND);
    static GetDpiForWindowFn getDpi =
        (GetDpiForWindowFn)GetProcAddress(GetModuleHandleW(L"user32.dll"), "GetDpiForWindow");
    if (getDpi) {
        dpi = getDpi(tray);
    }
    int size = MulDiv(cs.size, dpi, 96);
    int barH = tr.bottom - tr.top, barW = tr.right - tr.left;
    bool vertical = barH > barW;
    int x, y;
    if (vertical) {                                      // barra a un lado: el orbe arriba
        x = tr.left + (barW - size) / 2;
        y = tr.top + MulDiv(8, dpi, 96) + cs.offset;
    } else {
        y = tr.top + (barH - size) / 2;
        if (cs.atClock) {
            RECT nr;
            HWND notify = FindWindowExW(tray, nullptr, L"TrayNotifyWnd", nullptr);
            int right = (notify && GetWindowRect(notify, &nr) && nr.left > tr.left) ? nr.left : tr.right - MulDiv(260, dpi, 96);
            x = right - size - MulDiv(8, dpi, 96) - cs.offset;
        } else {
            x = tr.left + MulDiv(6, dpi, 96) - cs.offset;
        }
    }
    bool hide = cs.hideFullscreen && ForegroundIsFullscreen();
    if (hide) {
        ShowWindow(g_orb, SW_HIDE);
        return;
    }
    SetWindowPos(g_orb, HWND_TOPMOST, x, y, size, size, SWP_NOACTIVATE | SWP_SHOWWINDOW);
    if (g_tip) {
        g_ti.rect = {0, 0, size, size};
        SendMessageW(g_tip, TTM_NEWTOOLRECTW, 0, (LPARAM)&g_ti);
    }
}

// ------------------------------------------------------------------ texto de ayuda y menú
void TipText(wchar_t* buf, size_t n) {
    EnterCriticalSection(&g_lock);
    Status st = g_status;
    LeaveCriticalSection(&g_lock);
    const wchar_t* what = L"Jarvis está atento: di «Jarvis» o haz clic";
    switch (st.mode) {
        case Mode::Off: what = L"Jarvis no está abierto (clic para abrirlo)"; break;
        case Mode::Awaiting: what = L"Jarvis te escucha…"; break;
        case Mode::Thinking: what = L"Jarvis está pensando…"; break;
        case Mode::Speaking: what = L"Jarvis está hablando"; break;
        case Mode::Muted: what = L"Micrófono en pausa · clic derecho para reanudarlo"; break;
        default: break;
    }
    if (st.timers > 0 && st.next >= 0) {
        swprintf(buf, n, L"%ls\nTemporizador: faltan %d:%02d%ls", what, st.next / 60, st.next % 60,
                 st.timers > 1 ? L" (y otros)" : L"");
    } else {
        swprintf(buf, n, L"%ls", what);
    }
}

enum MenuId {
    kMenuListen = 1, kMenuToggle, kMenuWrite, kMenuClass, kMenuTimer, kMenuPending, kMenuMic, kMenuCheck, kMenuSettings,
};

void ShowMenu(HWND hwnd) {
    HMENU m = CreatePopupMenu();
    AppendMenuW(m, MF_STRING, kMenuListen, L"Hablar con Jarvis");
    AppendMenuW(m, MF_STRING, kMenuToggle, L"Mostrar u ocultar el panel");
    AppendMenuW(m, MF_STRING, kMenuWrite, L"Escribir una orden…");
    AppendMenuW(m, MF_SEPARATOR, 0, nullptr);
    AppendMenuW(m, MF_STRING, kMenuClass, L"Modo clase");
    AppendMenuW(m, MF_STRING, kMenuTimer, L"Temporizador de 5 minutos");
    AppendMenuW(m, MF_STRING, kMenuPending, L"¿Qué tengo pendiente?");
    AppendMenuW(m, MF_SEPARATOR, 0, nullptr);
    AppendMenuW(m, MF_STRING, kMenuMic, L"Pausar o reanudar el micrófono");
    AppendMenuW(m, MF_STRING, kMenuCheck, L"Prueba completa");
    AppendMenuW(m, MF_STRING, kMenuSettings, L"Ajustes de Jarvis");
    POINT p;
    GetCursorPos(&p);
    SetForegroundWindow(hwnd);
    int cmd = TrackPopupMenu(m, TPM_RETURNCMD | TPM_RIGHTBUTTON | TPM_BOTTOMALIGN | TPM_CENTERALIGN, p.x, p.y, 0,
                             hwnd, nullptr);
    DestroyMenu(m);
    PostMessageW(hwnd, WM_NULL, 0, 0);
    switch (cmd) {
        case kMenuListen: Send("jarvis://escuchar"); break;
        case kMenuToggle: Send("jarvis://alternar"); break;
        case kMenuWrite: Send("jarvis://escribir"); break;
        case kMenuClass: Send("jarvis://rutina/Modo%20clase"); break;
        case kMenuTimer: Send("jarvis://temporizador/5"); break;
        case kMenuPending: Send("jarvis://orden/qu%C3%A9%20tengo%20pendiente"); break;
        case kMenuMic: Send("jarvis://microfono"); break;
        case kMenuCheck: Send("jarvis://prueba"); break;
        case kMenuSettings: Send("jarvis://ajustes"); break;
        default: break;
    }
}

bool Animating() {
    EnterCriticalSection(&g_lock);
    Mode m = g_status.mode;
    LeaveCriticalSection(&g_lock);
    return m != Mode::Off;
}

LRESULT CALLBACK OrbProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
        case WM_TIMER:
            if (wp == kAnimTimer) {
                if (IsWindowVisible(hwnd)) {
                    Render(hwnd);
                }
                EnterCriticalSection(&g_lock);
                Mode m = g_status.mode;
                LeaveCriticalSection(&g_lock);
                // Más fluido cuando pasa algo; tranquilo (y barato) cuando está en reposo.
                UINT next = (m == Mode::Thinking || m == Mode::Speaking || m == Mode::Awaiting) ? 33 : 90;
                SetTimer(hwnd, kAnimTimer, Animating() ? next : 500, nullptr);
            } else if (wp == kPlaceTimer) {
                Place();
            }
            return 0;
        case WM_APP_STATUS:
            Render(hwnd);
            return 0;
        case WM_APP_RELOAD:
            Place();
            Render(hwnd);
            return 0;
        case WM_MOUSEMOVE:
            if (!g_hover) {
                g_hover = true;
                TRACKMOUSEEVENT tme = {sizeof(tme), TME_LEAVE, hwnd, 0};
                TrackMouseEvent(&tme);
                Render(hwnd);
            }
            return 0;
        case WM_MOUSELEAVE:
            g_hover = false;
            Render(hwnd);
            return 0;
        case WM_LBUTTONUP:
            Send(CurrentSettings().clickToggles ? "jarvis://alternar" : "jarvis://escuchar");
            return 0;
        case WM_RBUTTONUP:
            ShowMenu(hwnd);
            return 0;
        case WM_MOUSEACTIVATE:
            return MA_NOACTIVATE;
        case WM_NOTIFY: {
            NMHDR* nm = (NMHDR*)lp;
            if (nm && nm->code == TTN_GETDISPINFOW) {
                static wchar_t text[256];
                TipText(text, 256);
                ((NMTTDISPINFOW*)lp)->lpszText = text;
                return 0;
            }
            break;
        }
        case WM_DISPLAYCHANGE:
        case WM_DPICHANGED:
        case WM_SETTINGCHANGE:
            Place();
            return 0;
        case WM_DESTROY:
            KillTimer(hwnd, kAnimTimer);
            KillTimer(hwnd, kPlaceTimer);
            return 0;
    }
    return DefWindowProcW(hwnd, msg, wp, lp);
}

DWORD WINAPI OrbThread(LPVOID ready) {
    HINSTANCE inst = GetModuleHandleW(nullptr);
    WNDCLASSW wc = {};
    wc.lpfnWndProc = OrbProc;
    wc.hInstance = inst;
    wc.lpszClassName = kClass;
    wc.hCursor = LoadCursorW(nullptr, MAKEINTRESOURCEW(32649));
    RegisterClassW(&wc);
    g_orb = CreateWindowExW(WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_LAYERED, kClass, L"Jarvis",
                            WS_POPUP, 0, 0, CurrentSettings().size, CurrentSettings().size, nullptr, nullptr, inst, nullptr);
    if (g_orb) {
        INITCOMMONCONTROLSEX icc = {sizeof(icc), ICC_WIN95_CLASSES};
        InitCommonControlsEx(&icc);
        g_tip = CreateWindowExW(WS_EX_TOPMOST, TOOLTIPS_CLASSW, nullptr, WS_POPUP | TTS_NOPREFIX | TTS_ALWAYSTIP, 0,
                                0, 0, 0, g_orb, nullptr, inst, nullptr);
        if (g_tip) {
            g_ti.cbSize = sizeof(g_ti);
            g_ti.uFlags = TTF_SUBCLASS;
            g_ti.hwnd = g_orb;
            g_ti.uId = 1;
            g_ti.lpszText = LPSTR_TEXTCALLBACKW;
            g_ti.rect = {0, 0, CurrentSettings().size, CurrentSettings().size};
            SendMessageW(g_tip, TTM_ADDTOOLW, 0, (LPARAM)&g_ti);
            SendMessageW(g_tip, TTM_SETMAXTIPWIDTH, 0, 360);
        }
        Place();
        Render(g_orb);
        SetTimer(g_orb, kAnimTimer, 90, nullptr);
        SetTimer(g_orb, kPlaceTimer, 1000, nullptr);   // la barra puede moverse, ocultarse o cambiar de tamaño
    } else {
        Wh_Log(L"No se pudo crear el orbe: %u", GetLastError());
    }
    SetEvent((HANDLE)ready);

    bool running = g_orb != nullptr;
    while (running) {
        DWORD r = MsgWaitForMultipleObjects(1, &g_quit, FALSE, INFINITE, QS_ALLINPUT);
        if (r == WAIT_OBJECT_0) {
            break;
        }
        MSG msg;
        while (PeekMessageW(&msg, nullptr, 0, 0, PM_REMOVE)) {
            if (msg.message == WM_QUIT) {
                running = false;
                break;
            }
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
    }
    if (g_tip) {
        DestroyWindow(g_tip);
        g_tip = nullptr;
    }
    if (g_orb) {
        DestroyWindow(g_orb);
        g_orb = nullptr;
    }
    UnregisterClassW(kClass, inst);
    return 0;
}

}  // namespace

////////////////////////////////////////////////////////////////////////////////
// Ciclo de vida del mod

BOOL Wh_ModInit() {
    InitializeCriticalSection(&g_lock);
    LoadSettings();
    // Puede haber varios explorer.exe: solo uno muestra el orbe.
    g_single = CreateMutexW(nullptr, FALSE, L"WindhawkJarvisOrbe_Instance");
    if (!g_single || GetLastError() == ERROR_ALREADY_EXISTS) {
        if (g_single) {
            CloseHandle(g_single);
            g_single = nullptr;
        }
        return TRUE;
    }
    g_quit = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    if (!g_quit) {
        return FALSE;
    }
    ReadLinkFile();
    HANDLE ready = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    g_thread = CreateThread(nullptr, 0, OrbThread, ready, 0, nullptr);
    if (g_thread && ready) {
        WaitForSingleObject(ready, 5000);
    }
    if (ready) {
        CloseHandle(ready);
    }
    g_poller = CreateThread(nullptr, 0, PollThread, nullptr, 0, nullptr);
    return TRUE;
}

void Wh_ModUninit() {
    if (g_quit) {
        SetEvent(g_quit);
    }
    for (HANDLE* h : {&g_poller, &g_thread}) {
        if (*h) {
            WaitForSingleObject(*h, 5000);
            CloseHandle(*h);
            *h = nullptr;
        }
    }
    if (g_quit) {
        CloseHandle(g_quit);
        g_quit = nullptr;
    }
    if (g_single) {
        CloseHandle(g_single);
        g_single = nullptr;
        DeleteCriticalSection(&g_lock);
    }
}

void Wh_ModSettingsChanged() {
    LoadSettings();
    if (g_orb) {
        PostMessageW(g_orb, WM_APP_RELOAD, 0, 0);
    }
}
