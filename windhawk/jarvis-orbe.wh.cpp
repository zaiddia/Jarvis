// ==WindhawkMod==
// @id              jarvis-orbe
// @name            Reactor de Jarvis en la barra de tareas
// @description     Un mini reactor animado junto al reloj: escucha, piensa y habla a la vista, tarjeta con tu día, cuadro para escribirle, volumen con la rueda y avisos
// @version         2.0.1
// @author          zaiddia
// @github          https://github.com/zaiddia
// @include         explorer.exe
// @compilerOptions -lwinhttp -lcomctl32 -lgdi32 -luser32 -lshell32 -lmsimg32
// ==/WindhawkMod==

// ==WindhawkModReadme==
/*
# Reactor de Jarvis

Un **mini reactor** en la barra de tareas, junto al reloj, conectado a Jarvis
(7.3 o posterior, abierto en tu mismo usuario de Windows).

## Qué muestra
| El reactor | Significa |
|---|---|
| Bobinas del color de tu tema, respirando | Jarvis está atento: di «Jarvis» |
| Las bobinas se encienden con tu voz | Te está escuchando (medidor de nivel) |
| Un destello que gira por las bobinas | Está pensando |
| Todo late al ritmo de la voz | Está hablando |
| Gris | Micrófono en pausa |
| Apagado, con el núcleo rojo | Jarvis no está abierto |
| Arco ámbar alrededor | Un temporizador: el arco se va vaciando (parpadea el último medio minuto) |
| Destello rojo-ámbar | Un aviso o recordatorio |
| Onda blanca desde el núcleo | Jarvis acaba de responder |

## Qué puedes hacer
- **Clic**: háblale (como decir «Jarvis»). **Doble clic**: mostrar u ocultar el panel.
- **Mayús + clic** (o clic derecho › *Escribir aquí*): un cuadro para escribirle sin abrir el panel.
- **Rueda del ratón** encima: sube o baja el volumen. **Clic central**: pausa o reanuda la música.
- **Pasar el ratón**: una tarjeta con su estado, tu temporizador con cuenta atrás, lo próximo de tu agenda
  y lo último que te dijo.
- Cuando responde con el panel oculto, su respuesta aparece en una **burbuja** sobre el reactor.
- **Arrástralo** por la barra para cambiarlo de sitio (clic derecho › *Volver a su sitio* para deshacerlo).
- **Clic derecho**: menú con *Modo clase*, *Temporizador*, *¿Qué tengo pendiente?*, música, micrófono,
  *Prueba completa* y *Ajustes*.

Habla con Jarvis solo dentro de tu equipo (127.0.0.1) y con el código secreto que Jarvis guarda en
`%APPDATA%\Jarvis\enlace.json` (cambia cada vez que Jarvis arranca). Se oculta con programas en pantalla completa.
*/
// ==/WindhawkModReadme==

// ==WindhawkModSettings==
/*
- position: clock
  $name: Dónde va el reactor
  $options:
  - clock: A la izquierda del reloj y los iconos de la bandeja
  - left: En el extremo izquierdo de la barra de tareas
- offset: 0
  $name: Desplazamiento (píxeles)
  $description: Muévelo a la izquierda (positivo) o a la derecha (negativo). También puedes arrastrarlo.
- size: 40
  $name: Tamaño del reactor (píxeles, a 100 % de escala)
- click: listen
  $name: Al hacer clic
  $options:
  - listen: Hablarle a Jarvis (y con doble clic, mostrar u ocultar el panel)
  - toggle: Mostrar u ocultar el panel (y con doble clic, hablarle)
- card: true
  $name: Tarjeta al pasar el ratón
- bubble: true
  $name: Burbuja con lo que responde (cuando el panel está oculto)
- wheel: true
  $name: Rueda del ratón para el volumen (y clic central para la música)
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
#include <windowsx.h>
#include <winhttp.h>

#include <math.h>
#include <stdio.h>
#include <wchar.h>

#include <string>

// ============================================================================ DIBUJO (puro, sin Windows)
// El reactor se pinta píxel a píxel con alfa premultiplicado. Esta parte no usa la API de Windows.
namespace reactor {

enum class Mode { Off, Idle, Awaiting, Thinking, Speaking, Muted };

struct View {
    Mode mode = Mode::Off;
    float accent[3] = {0.18f, 0.90f, 1.00f};   // color del tema de Jarvis
    float level = 0;                          // micrófono 0..1 (suavizado)
    float timerFrac = -1;                     // 0..1 lo que queda del temporizador; -1 = ninguno
    float timerLeft = 0;                      // segundos
    float alert = 0;                          // 0..1 destello de aviso
    float ripple = -1;                        // 0..1 onda de mensaje nuevo; -1 = ninguna
    float hover = 0;                          // 0..1
    float t = 0;                              // segundos
};

inline float clamp01(float v) { return v < 0 ? 0 : (v > 1 ? 1 : v); }
inline float smooth(float e0, float e1, float x) {
    float k = clamp01((x - e0) / (e1 - e0));
    return k * k * (3 - 2 * k);
}
// 1 dentro de la banda [a, b] con bordes suaves de «aa» píxeles
inline float band(float d, float a, float b, float aa) { return smooth(a - aa, a + aa, d) * (1 - smooth(b - aa, b + aa, d)); }
inline float wrapPi(float a) {
    while (a > 3.14159265f) a -= 6.2831853f;
    while (a < -3.14159265f) a += 6.2831853f;
    return a;
}

struct Px {
    float r = 0, g = 0, b = 0, a = 0;
    void over(float cr, float cg, float cb, float ca) {        // pintar encima (no premultiplicado de entrada)
        ca = clamp01(ca);
        r = cr * ca + r * (1 - ca);
        g = cg * ca + g * (1 - ca);
        b = cb * ca + b * (1 - ca);
        a = ca + a * (1 - ca);
    }
    void add(float cr, float cg, float cb, float k) {          // luz que se suma
        k = k < 0 ? 0 : k;
        r += cr * k;
        g += cg * k;
        b += cb * k;
        a = clamp01(a + k * 0.9f);
    }
};

inline void paint(unsigned int* px, int w, int h, const View& v) {
    const float PI = 3.14159265f, TAU = 6.2831853f;
    float cx = w / 2.0f, cy = h / 2.0f;
    float R = (w < h ? w : h) / 2.0f - 0.5f;
    float aa = 0.75f;
    bool off = v.mode == Mode::Off, muted = v.mode == Mode::Muted;
    float base[3] = {v.accent[0], v.accent[1], v.accent[2]};
    if (muted || off) {
        base[0] = base[1] = base[2] = off ? 0.32f : 0.62f;
    }
    if (v.mode == Mode::Thinking) {                     // pensando: hacia el ámbar
        base[0] = 0.25f * base[0] + 0.75f * 1.00f;
        base[1] = 0.25f * base[1] + 0.75f * 0.70f;
        base[2] = 0.25f * base[2] + 0.75f * 0.26f;
    }
    float t = v.t;
    float breathe = 0.5f + 0.5f * sinf(t * 1.7f);
    float speak = v.mode == Mode::Speaking ? 0.55f + 0.45f * fabsf(sinf(t * 7.3f) * sinf(t * 3.1f + 1.0f)) : 0;
    float energy = off ? 0.08f : muted ? 0.30f : v.mode == Mode::Idle ? 0.36f + 0.24f * breathe
                 : v.mode == Mode::Awaiting ? 0.70f + 0.30f * v.level : v.mode == Mode::Thinking ? 0.75f : 0.6f + 0.4f * speak;
    energy = clamp01(energy + v.hover * 0.15f);
    float spin = t * (v.mode == Mode::Thinking ? 2.6f : v.mode == Mode::Speaking ? 1.2f : 0.35f);
    const int COILS = 10;
    float lit = v.mode == Mode::Awaiting ? 2.0f + v.level * COILS : COILS;   // medidor de voz: bobinas encendidas

    for (int y = 0; y < h; y++) {
        for (int x = 0; x < w; x++) {
            float dx = x + 0.5f - cx, dy = y + 0.5f - cy;
            float d = sqrtf(dx * dx + dy * dy) / R;           // 0 centro .. 1 borde
            float ang = atan2f(dx, -dy);                      // 0 arriba, sentido horario
            float ua = ang < 0 ? ang + TAU : ang;             // 0..2π
            Px p;
            if (d > 1.06f) {
                px[y * w + x] = 0;
                continue;
            }
            float aap = aa / R;
            // 1) disco de fondo (casi negro azulado) para que se lea sobre cualquier barra
            float disc = 1 - smooth(1.0f - aap * 1.5f, 1.0f, d);
            p.over(0.016f, 0.03f, 0.05f, disc * 0.92f);
            // 2) bisel metálico exterior con marcas que giran
            float bez = band(d, 0.84f, 0.98f, aap);
            float shade = 0.20f + 0.16f * (-dy / R) ;          // luz desde arriba
            p.over(0.10f + shade * 0.5f, 0.13f + shade * 0.5f, 0.17f + shade * 0.55f, bez * 0.95f);
            float tick = 0.5f + 0.5f * cosf((ua - spin * 0.25f) * 24.0f);
            float ticks = band(d, 0.88f, 0.95f, aap) * smooth(0.82f, 0.97f, tick);
            p.add(base[0], base[1], base[2], ticks * (0.18f + 0.30f * energy));
            // 3) arco del temporizador sobre el bisel (se vacía en sentido horario)
            if (v.timerFrac >= 0) {
                float blink = v.timerLeft < 30 ? 0.55f + 0.45f * (sinf(t * 9.0f) > 0 ? 1.0f : 0.25f) : 1.0f;
                float on = ua <= v.timerFrac * TAU ? 1.0f : 0.0f;
                float arc = band(d, 0.855f, 0.965f, aap);
                p.over(1.0f, 0.70f, 0.26f, arc * on * 0.92f * blink);
                p.add(1.0f, 0.70f, 0.26f, arc * (1 - on) * 0.06f);
            }
            // 4) bobinas (segmentos trapezoidales) — el corazón del reactor
            float seg = ua / TAU * COILS;
            int idx = (int)seg;
            float within = seg - idx;                          // 0..1 dentro del segmento
            float gapPx = 1.1f / (d * R * TAU / COILS + 1e-3f);  // hueco de ~1 px entre bobinas
            float coilMask = band(d, 0.50f, 0.78f, aap) * smooth(gapPx, gapPx + 0.08f, within) *
                             (1 - smooth(1 - gapPx - 0.08f, 1 - gapPx, within));
            float coilLevel = energy;
            if (v.mode == Mode::Awaiting) {
                coilLevel = idx < (int)lit ? 0.55f + 0.45f * v.level : 0.12f;
            } else if (v.mode == Mode::Thinking) {
                float head = fmodf(spin * 1.6f, TAU);
                float da = wrapPi(ua - head);
                float trail = da < 0 ? expf(da * 1.6f) : expf(-da * 9.0f);
                coilLevel = 0.10f + 1.0f * trail;
            } else if (v.mode == Mode::Speaking) {
                coilLevel = 0.35f + 0.65f * speak * (0.75f + 0.25f * sinf(idx * 1.7f + t * 6.0f));
            }
            float radial = 1 - 0.35f * fabsf((d - 0.64f) / 0.14f);   // más brillante en el centro de la bobina
            p.over(0.05f, 0.07f, 0.09f, coilMask * 0.9f);
            p.add(base[0], base[1], base[2], coilMask * coilLevel * radial * 1.05f);
            // resplandor entre bobinas
            float glowR = expf(-powf((d - 0.64f) / 0.20f, 2)) * (off ? 0 : 0.22f * energy);
            p.add(base[0], base[1], base[2], glowR * disc);
            // 5) anillo interior y núcleo
            float inner = band(d, 0.40f, 0.455f, aap);
            p.over(0.12f, 0.16f, 0.20f, inner * 0.9f);
            p.add(base[0], base[1], base[2], inner * (0.25f + 0.5f * energy));
            float coreR = 0.30f + 0.04f * (v.mode == Mode::Speaking ? speak : v.mode == Mode::Awaiting ? v.level : breathe * 0.5f);
            float core = 1 - smooth(coreR - aap * 1.2f, coreR + aap * 0.6f, d);
            float hot = expf(-powf(d / (coreR * 0.55f), 2));
            if (off) {
                p.over(0.08f, 0.09f, 0.10f, core);
                p.add(0.9f, 0.18f, 0.22f, hot * (0.35f + 0.25f * breathe));   // núcleo rojo apagado
            } else {
                p.over(base[0] * 0.35f, base[1] * 0.35f, base[2] * 0.35f, core);
                p.add(base[0], base[1], base[2], core * (0.45f + 0.55f * energy));
                p.add(1, 1, 1, hot * (0.35f + 0.55f * energy) * core);      // centro casi blanco
                p.add(base[0], base[1], base[2], expf(-powf(d / 0.55f, 2)) * 0.25f * energy * disc);
            }
            // 6) onda de mensaje nuevo
            if (v.ripple >= 0) {
                float rr = 0.25f + v.ripple * 0.85f;
                float wave = expf(-powf((d - rr) / 0.07f, 2)) * (1 - v.ripple);
                p.add(1, 1, 1, wave * 0.75f * disc);
            }
            // 7) destello de aviso
            if (v.alert > 0) {
                float fl = (0.5f + 0.5f * sinf(t * 14.0f)) * v.alert;
                float ring = band(d, 0.80f, 1.0f, aap * 2);
                p.add(1.0f, 0.38f, 0.22f, (ring * 0.9f + disc * 0.25f) * fl);
            }
            // 8) brillo especular arriba (vidrio)
            float spec = band(d, 0.80f, 0.97f, aap) * smooth(-0.2f, -0.85f, dy / R) * 0.22f;
            p.add(1, 1, 1, spec);
            (void)PI;
            // salida premultiplicada
            float A = clamp01(p.a);
            float r = clamp01(p.r), g = clamp01(p.g), b = clamp01(p.b);
            unsigned Ai = (unsigned)(A * 255 + 0.5f);
            unsigned Ri = (unsigned)(r * 255 + 0.5f), Gi = (unsigned)(g * 255 + 0.5f), Bi = (unsigned)(b * 255 + 0.5f);
            if (Ri > Ai) Ri = Ai;
            if (Gi > Ai) Gi = Ai;
            if (Bi > Ai) Bi = Ai;
            px[y * w + x] = (Ai << 24) | (Ri << 16) | (Gi << 8) | Bi;
        }
    }
}

}  // namespace reactor
// ============================================================================ FIN DIBUJO

namespace {

using reactor::Mode;

// ------------------------------------------------------------------ ajustes
struct Settings {
    bool atClock = true;
    int offset = 0;
    int size = 40;
    bool clickToggles = false;
    bool card = true;
    bool bubble = true;
    bool wheel = true;
    bool hideFullscreen = true;
    std::wstring linkFile;
};
Settings g_settings;
CRITICAL_SECTION g_lock;   // protege g_settings, g_status, el puerto y el código

void LoadSettings() {
    Settings s;
    PCWSTR pos = Wh_GetStringSetting(L"position");
    s.atClock = !pos || wcscmp(pos, L"left") != 0;
    Wh_FreeStringSetting(pos);
    s.offset = Wh_GetIntSetting(L"offset");
    s.size = Wh_GetIntSetting(L"size");
    if (s.size < 20 || s.size > 72) {
        s.size = 40;
    }
    PCWSTR click = Wh_GetStringSetting(L"click");
    s.clickToggles = click && wcscmp(click, L"toggle") == 0;
    Wh_FreeStringSetting(click);
    s.card = Wh_GetIntSetting(L"card") != 0;
    s.bubble = Wh_GetIntSetting(L"bubble") != 0;
    s.wheel = Wh_GetIntSetting(L"wheel") != 0;
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

Settings Cfg() {
    EnterCriticalSection(&g_lock);
    Settings s = g_settings;
    LeaveCriticalSection(&g_lock);
    return s;
}

// ------------------------------------------------------------------ estado que llega de Jarvis
struct Status {
    Mode mode = Mode::Off;
    float level = 0;
    int timers = 0, next = -1, total = 0;
    bool visible = false, live = false;
    int seq = 0, alertSeq = 0;
    std::wstring role, msg, alert, label, agenda, aiLabel, net;
    float accent[3] = {0.18f, 0.90f, 1.00f};
};
Status g_status;
int g_port = 0;
std::string g_token;

HANDLE g_thread = nullptr, g_poller = nullptr, g_quit = nullptr, g_single = nullptr;
HWND g_orb = nullptr, g_card = nullptr, g_input = nullptr, g_edit = nullptr;
HFONT g_fontTitle = nullptr, g_fontBody = nullptr, g_fontSmall = nullptr;

const wchar_t kOrbClass[] = L"JarvisReactorWindhawk";
const wchar_t kCardClass[] = L"JarvisReactorCard";
const wchar_t kInputClass[] = L"JarvisReactorInput";
constexpr UINT WM_APP_STATUS = WM_APP + 1;
constexpr UINT WM_APP_RELOAD = WM_APP + 2;
constexpr UINT_PTR kAnimTimer = 1, kPlaceTimer = 2, kHoverTimer = 3, kClickTimer = 4, kCardTimer = 5;

// animación (solo hilo de la ventana)
struct Anim {
    float level = 0, hover = 0, alert = 0, ripple = -1;
    DWORD alertUntil = 0, rippleStart = 0;
    int lastSeq = -1, lastAlertSeq = -1;
} g_anim;

// tarjeta
enum class CardKind { None, Info, Message, Alert };
CardKind g_cardKind = CardKind::None;
std::wstring g_cardTitle, g_cardText;
bool g_hovering = false;

// arrastre
bool g_down = false, g_dragging = false, g_ignoreUp = false;
POINT g_downPt = {};
int g_dragOffset = 0, g_dragStartOffset = 0;

// ------------------------------------------------------------------ JSON mínimo (el que manda Jarvis)
// Busca "clave": como clave de verdad (no dentro de un texto, donde las comillas van escapadas).
size_t JsonFind(const std::string& j, const char* key) {
    std::string k = std::string("\"") + key + "\"";
    size_t p = 0;
    while ((p = j.find(k, p)) != std::string::npos) {
        size_t q = p;
        while (q > 0 && (j[q - 1] == ' ' || j[q - 1] == '\n')) {
            q--;
        }
        if (q > 0 && (j[q - 1] == '{' || j[q - 1] == ',')) {
            size_t c = j.find(':', p + k.size());
            return c == std::string::npos ? c : c + 1;
        }
        p += k.size();
    }
    return std::string::npos;
}

void Utf8Append(std::string& out, unsigned cp) {
    if (cp < 0x80) {
        out += (char)cp;
    } else if (cp < 0x800) {
        out += (char)(0xC0 | (cp >> 6));
        out += (char)(0x80 | (cp & 0x3F));
    } else if (cp < 0x10000) {
        out += (char)(0xE0 | (cp >> 12));
        out += (char)(0x80 | ((cp >> 6) & 0x3F));
        out += (char)(0x80 | (cp & 0x3F));
    } else {
        out += (char)(0xF0 | (cp >> 18));
        out += (char)(0x80 | ((cp >> 12) & 0x3F));
        out += (char)(0x80 | ((cp >> 6) & 0x3F));
        out += (char)(0x80 | (cp & 0x3F));
    }
}

std::wstring Wide(const std::string& u8) {
    if (u8.empty()) {
        return L"";
    }
    int n = MultiByteToWideChar(CP_UTF8, 0, u8.data(), (int)u8.size(), nullptr, 0);
    std::wstring w(n, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, u8.data(), (int)u8.size(), &w[0], n);
    return w;
}

std::string Utf8(const std::wstring& w) {
    if (w.empty()) {
        return "";
    }
    int n = WideCharToMultiByte(CP_UTF8, 0, w.data(), (int)w.size(), nullptr, 0, nullptr, nullptr);
    std::string s(n, '\0');
    WideCharToMultiByte(CP_UTF8, 0, w.data(), (int)w.size(), &s[0], n, nullptr, nullptr);
    return s;
}

std::string JsonRaw(const std::string& j, const char* key) {
    size_t p = JsonFind(j, key);
    if (p == std::string::npos) {
        return "";
    }
    while (p < j.size() && j[p] == ' ') {
        p++;
    }
    if (p < j.size() && j[p] == '"') {                       // texto con escapes \" \\ \n \uXXXX
        std::string out;
        for (size_t i = p + 1; i < j.size(); i++) {
            char ch = j[i];
            if (ch == '"') {
                break;
            }
            if (ch != '\\' || i + 1 >= j.size()) {
                out += ch;
                continue;
            }
            char e = j[++i];
            if (e == 'n' || e == 'r' || e == 't') {
                out += ' ';
            } else if (e == 'u' && i + 4 < j.size()) {
                unsigned cp = (unsigned)strtoul(j.substr(i + 1, 4).c_str(), nullptr, 16);
                i += 4;
                if (cp >= 0xD800 && cp <= 0xDBFF && i + 6 < j.size() && j[i + 1] == '\\' && j[i + 2] == 'u') {
                    unsigned lo = (unsigned)strtoul(j.substr(i + 3, 4).c_str(), nullptr, 16);
                    cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
                    i += 6;
                }
                Utf8Append(out, cp);
            } else {
                out += e;
            }
        }
        return out;
    }
    size_t e = p;
    while (e < j.size() && j[e] != ',' && j[e] != '}' && j[e] != ' ') {
        e++;
    }
    return j.substr(p, e - p);
}

std::string JsonEscape(const std::string& s) {
    std::string o;
    for (unsigned char c : s) {
        if (c == '"' || c == '\\') {
            o += '\\';
            o += (char)c;
        } else if (c < 0x20) {
            o += ' ';
        } else {
            o += (char)c;
        }
    }
    return o;
}

// ------------------------------------------------------------------ enlace con Jarvis
std::wstring LinkPath() {
    std::wstring custom = Cfg().linkFile;
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
    std::string token = JsonRaw(j, "token");
    int port = atoi(JsonRaw(j, "port").c_str());
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
    HINTERNET s = WinHttpOpen(L"JarvisReactor/2.0", WINHTTP_ACCESS_TYPE_NO_PROXY, WINHTTP_NO_PROXY_NAME,
                              WINHTTP_NO_PROXY_BYPASS, 0);
    if (!s) {
        return 0;
    }
    WinHttpSetTimeouts(s, 800, 800, 1500, 3000);
    HINTERNET c = WinHttpConnect(s, L"127.0.0.1", (INTERNET_PORT)port, 0);
    HINTERNET r = c ? WinHttpOpenRequest(c, method, path, nullptr, WINHTTP_NO_REFERER, WINHTTP_DEFAULT_ACCEPT_TYPES, 0)
                    : nullptr;
    if (r) {
        std::wstring hdr = L"X-Jarvis-Token: " + std::wstring(token.begin(), token.end()) +
                           L"\r\nContent-Type: application/json; charset=utf-8\r\n";
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
                while (WinHttpQueryDataAvailable(r, &avail) && avail && out->size() < 16384) {
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

void ParseAccent(const std::string& hex, float* rgb) {
    if (hex.size() != 6) {
        return;
    }
    unsigned v = (unsigned)strtoul(hex.c_str(), nullptr, 16);
    rgb[0] = ((v >> 16) & 255) / 255.0f;
    rgb[1] = ((v >> 8) & 255) / 255.0f;
    rgb[2] = (v & 255) / 255.0f;
}

DWORD WINAPI PollThread(LPVOID) {
    DWORD lastRead = 0;
    int fails = 0;
    DWORD wait = 300;
    while (WaitForSingleObject(g_quit, wait) == WAIT_TIMEOUT) {
        if (!g_port || (fails && GetTickCount() - lastRead > 4000)) {
            ReadLinkFile();                          // Jarvis cambia el código cada vez que arranca
            lastRead = GetTickCount();
        }
        std::string j;
        Status st;
        if (Http(L"GET", L"/api/orbe", "", &j) == 200) {
            fails = 0;
            std::string mode = JsonRaw(j, "mode"), mic = JsonRaw(j, "mic");
            st.mode = mode == "speaking" ? Mode::Speaking : mode == "thinking" ? Mode::Thinking
                    : mode == "awaiting" ? Mode::Awaiting : mic != "on" ? Mode::Muted : Mode::Idle;
            st.level = (float)atof(JsonRaw(j, "level").c_str());
            st.timers = atoi(JsonRaw(j, "timers").c_str());
            st.next = atoi(JsonRaw(j, "next").c_str());
            st.total = atoi(JsonRaw(j, "total").c_str());
            st.visible = JsonRaw(j, "visible") == "true";
            st.live = JsonRaw(j, "live") == "true";
            st.seq = atoi(JsonRaw(j, "seq").c_str());
            st.alertSeq = atoi(JsonRaw(j, "alert_seq").c_str());
            st.role = Wide(JsonRaw(j, "role"));
            st.msg = Wide(JsonRaw(j, "msg"));
            st.alert = Wide(JsonRaw(j, "alert"));
            st.label = Wide(JsonRaw(j, "label"));
            st.agenda = Wide(JsonRaw(j, "agenda"));
            st.aiLabel = Wide(JsonRaw(j, "ai_label"));
            st.net = Wide(JsonRaw(j, "net"));
            ParseAccent(JsonRaw(j, "accent"), st.accent);
        } else {
            fails++;
            st.mode = Mode::Off;
        }
        EnterCriticalSection(&g_lock);
        g_status = st;
        LeaveCriticalSection(&g_lock);
        if (g_orb) {
            PostMessageW(g_orb, WM_APP_STATUS, 0, 0);
        }
        // Más rápido mientras te escucha (el medidor de voz), tranquilo en reposo, lento si Jarvis está cerrado.
        wait = st.mode == Mode::Off ? 1500 : (st.mode == Mode::Awaiting || st.mode == Mode::Speaking) ? 110 : 300;
    }
    return 0;
}

Status Snapshot() {
    EnterCriticalSection(&g_lock);
    Status s = g_status;
    LeaveCriticalSection(&g_lock);
    return s;
}

struct SendJob {
    std::wstring path;
    std::string body;
    std::string fallbackUrl;
};

DWORD WINAPI SendThread(LPVOID p) {
    SendJob* job = (SendJob*)p;
    int code = Http(L"POST", job->path.c_str(), job->body, nullptr);
    if (code == 403 || code == 0) {
        // Código viejo (Jarvis se reinició) o Jarvis cerrado: releer el enlace y, si no, abrir Jarvis.
        if (ReadLinkFile()) {
            code = Http(L"POST", job->path.c_str(), job->body, nullptr);
        }
        if (code != 200 && !job->fallbackUrl.empty()) {
            ShellExecuteW(nullptr, L"open", Wide(job->fallbackUrl).c_str(), nullptr, nullptr, SW_SHOWNORMAL);
        }
    }
    delete job;
    return 0;
}

void Post(const wchar_t* path, const std::string& body, const std::string& fallback) {
    SendJob* job = new SendJob{path, body, fallback};
    HANDLE t = CreateThread(nullptr, 0, SendThread, job, 0, nullptr);
    if (t) {
        CloseHandle(t);
    } else {
        delete job;
    }
}

void Link(const char* url) {
    Post(L"/api/enlace", std::string("{\"url\": \"") + url + "\", \"origen\": \"orbe\"}", url);
}

void Order(const std::wstring& text) {
    Post(L"/api/orden", "{\"texto\": \"" + JsonEscape(Utf8(text)) + "\"}", "");
}

// ------------------------------------------------------------------ utilidades de pantalla
UINT DpiOf(HWND h) {
    typedef UINT(WINAPI * Fn)(HWND);
    static Fn fn = (Fn)GetProcAddress(GetModuleHandleW(L"user32.dll"), "GetDpiForWindow");
    return fn && h ? fn(h) : 96;
}

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
    if (!g_orb || g_dragging) {
        return;
    }
    Settings cs = Cfg();
    HWND tray = FindWindowW(L"Shell_TrayWnd", nullptr);
    RECT tr;
    if (!tray || !GetWindowRect(tray, &tr) || !IsWindowVisible(tray)) {
        ShowWindow(g_orb, SW_HIDE);
        return;
    }
    UINT dpi = DpiOf(tray);
    int size = MulDiv(cs.size, dpi, 96);
    int barH = tr.bottom - tr.top, barW = tr.right - tr.left;
    if (barH < barW && size > barH - 2) {
        size = barH - 2;                             // barra fina: que quepa
    }
    int shift = cs.offset + g_dragOffset;
    int x, y;
    if (barH > barW) {                               // barra vertical: arriba
        x = tr.left + (barW - size) / 2;
        y = tr.top + MulDiv(8, dpi, 96) + shift;
    } else {
        y = tr.top + (barH - size) / 2;
        if (cs.atClock) {
            RECT nr;
            HWND notify = FindWindowExW(tray, nullptr, L"TrayNotifyWnd", nullptr);
            int right = (notify && GetWindowRect(notify, &nr) && nr.left > tr.left) ? nr.left : tr.right - MulDiv(260, dpi, 96);
            x = right - size - MulDiv(8, dpi, 96) - shift;
        } else {
            x = tr.left + MulDiv(6, dpi, 96) - shift;
        }
        if (x < tr.left) x = tr.left;
        if (x > tr.right - size) x = tr.right - size;
    }
    if (cs.hideFullscreen && ForegroundIsFullscreen()) {
        ShowWindow(g_orb, SW_HIDE);
        if (g_card) ShowWindow(g_card, SW_HIDE);
        return;
    }
    SetWindowPos(g_orb, HWND_TOPMOST, x, y, size, size, SWP_NOACTIVATE | SWP_SHOWWINDOW);
}

// ------------------------------------------------------------------ pintar el reactor
void RenderOrb() {
    if (!g_orb || !IsWindowVisible(g_orb)) {
        return;
    }
    RECT rc;
    GetWindowRect(g_orb, &rc);
    int w = rc.right - rc.left, h = rc.bottom - rc.top;
    if (w <= 0 || h <= 0) {
        return;
    }
    Status st = Snapshot();
    DWORD now = GetTickCount();
    reactor::View v;
    v.mode = st.mode;
    v.accent[0] = st.accent[0];
    v.accent[1] = st.accent[1];
    v.accent[2] = st.accent[2];
    g_anim.level += (st.level - g_anim.level) * 0.35f;
    v.level = g_anim.level;
    g_anim.hover += ((g_hovering ? 1.0f : 0.0f) - g_anim.hover) * 0.25f;
    v.hover = g_anim.hover;
    if (st.timers > 0 && st.total > 0 && st.next >= 0) {
        v.timerFrac = reactor::clamp01((float)st.next / (float)st.total);
        v.timerLeft = (float)st.next;
    }
    v.alert = now < g_anim.alertUntil ? reactor::clamp01((g_anim.alertUntil - now) / 1500.0f) : 0;
    if (g_anim.rippleStart && now - g_anim.rippleStart < 700) {
        v.ripple = (now - g_anim.rippleStart) / 700.0f;
    }
    v.t = (now % 3600000) / 1000.0f;

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
    if (bmp && bits) {
        HGDIOBJ old = SelectObject(mem, bmp);
        reactor::paint((unsigned int*)bits, w, h, v);
        POINT src = {0, 0}, dst = {rc.left, rc.top};
        SIZE sz = {w, h};
        BLENDFUNCTION bf = {AC_SRC_OVER, 0, 255, AC_SRC_ALPHA};
        UpdateLayeredWindow(g_orb, screen, &dst, &sz, mem, &src, 0, &bf, ULW_ALPHA);
        SelectObject(mem, old);
        DeleteObject(bmp);
    }
    DeleteDC(mem);
    ReleaseDC(nullptr, screen);
}

// ------------------------------------------------------------------ tarjeta (estado, burbuja, aviso)
COLORREF Accent(const Status& st) {
    return RGB((int)(st.accent[0] * 255), (int)(st.accent[1] * 255), (int)(st.accent[2] * 255));
}

std::wstring ModeText(const Status& st) {
    switch (st.mode) {
        case Mode::Off: return L"Jarvis no está abierto · clic para abrirlo";
        case Mode::Awaiting: return L"Te escucho…";
        case Mode::Thinking: return L"Pensando…";
        case Mode::Speaking: return L"Hablando";
        case Mode::Muted: return L"Micrófono en pausa";
        default: return L"Atento · di «Jarvis» o haz clic";
    }
}

std::wstring Clip(const std::wstring& s, size_t n) {
    return s.size() <= n ? s : s.substr(0, n - 1) + L"…";
}

void BuildInfoCard() {
    Status st = Snapshot();
    g_cardTitle = L"J.A.R.V.I.S.  ·  " + ModeText(st);
    std::wstring t;
    if (st.mode != Mode::Off) {
        if (st.timers > 0 && st.next >= 0) {
            wchar_t b[96];
            swprintf(b, 96, L"Temporizador  %d:%02d", st.next / 60, st.next % 60);
            t += b;
            if (!st.label.empty()) t += L"  ·  " + Clip(st.label, 30);
            if (st.timers > 1) t += L"  (+" + std::to_wstring(st.timers - 1) + L")";
            t += L"\n";
        }
        if (!st.agenda.empty()) t += L"Hoy  ·  " + Clip(st.agenda, 70) + L"\n";
        if (!st.aiLabel.empty()) t += L"IA  ·  " + Clip(st.aiLabel, 50) + (st.net == L"offline" ? L"  · sin internet" : L"") + L"\n";
        if (!st.msg.empty() && st.role == L"jarvis") t += L"\n«" + Clip(st.msg, 180) + L"»";
        if (t.empty()) t = L"Clic: háblale · Doble clic: panel · Rueda: volumen · Clic derecho: más";
    } else {
        t = L"Ábrelo y el reactor se enciende solo.";
    }
    while (!t.empty() && t.back() == L'\n') t.pop_back();
    g_cardText = t;
}

void LayoutCard() {
    if (!g_card || !g_orb) return;
    UINT dpi = DpiOf(g_orb);
    int width = MulDiv(g_cardKind == CardKind::Info ? 300 : 280, dpi, 96);
    int pad = MulDiv(12, dpi, 96);
    HDC dc = GetDC(g_card);
    RECT tr = {0, 0, width - 2 * pad, 0}, br = {0, 0, width - 2 * pad, 0};
    HGDIOBJ old = SelectObject(dc, g_fontTitle);
    DrawTextW(dc, g_cardTitle.c_str(), -1, &tr, DT_CALCRECT | DT_SINGLELINE | DT_END_ELLIPSIS | DT_NOPREFIX);
    SelectObject(dc, g_fontBody);
    DrawTextW(dc, g_cardText.c_str(), -1, &br, DT_CALCRECT | DT_WORDBREAK | DT_NOPREFIX);
    SelectObject(dc, old);
    ReleaseDC(g_card, dc);
    int height = pad + (tr.bottom - tr.top) + MulDiv(6, dpi, 96) + (br.bottom - br.top) + pad + MulDiv(3, dpi, 96);
    int maxH = MulDiv(260, dpi, 96);
    if (height > maxH) height = maxH;

    RECT orb;
    GetWindowRect(g_orb, &orb);
    MONITORINFO mi = {};
    mi.cbSize = sizeof(mi);
    GetMonitorInfoW(MonitorFromWindow(g_orb, MONITOR_DEFAULTTONEAREST), &mi);
    RECT wa = mi.rcWork;
    int gap = MulDiv(10, dpi, 96);
    int x = (orb.left + orb.right) / 2 - width / 2;
    int y = orb.top - gap - height;                         // barra abajo: encima
    if (y < wa.top) y = orb.bottom + gap;                   // barra arriba: debajo
    if (x + width > wa.right - gap) x = wa.right - gap - width;
    if (x < wa.left + gap) x = wa.left + gap;
    int r = MulDiv(14, dpi, 96);
    SetWindowPos(g_card, HWND_TOPMOST, x, y, width, height, SWP_NOACTIVATE | SWP_SHOWWINDOW);
    SetWindowRgn(g_card, CreateRoundRectRgn(0, 0, width + 1, height + 1, r, r), TRUE);
    InvalidateRect(g_card, nullptr, FALSE);
}

void ShowCard(CardKind kind, UINT ms) {
    if (!g_card) return;
    Status st = Snapshot();
    g_cardKind = kind;
    if (kind == CardKind::Info) {
        BuildInfoCard();
    } else if (kind == CardKind::Message) {
        g_cardTitle = L"Jarvis";
        g_cardText = Clip(st.msg, 320);
    } else if (kind == CardKind::Alert) {
        g_cardTitle = L"Aviso de Jarvis";
        g_cardText = Clip(st.alert, 300);
    }
    LayoutCard();
    KillTimer(g_orb, kCardTimer);
    if (ms) SetTimer(g_orb, kCardTimer, ms, nullptr);
}

void HideCard() {
    if (g_card) ShowWindow(g_card, SW_HIDE);
    g_cardKind = CardKind::None;
    KillTimer(g_orb, kCardTimer);
}

LRESULT CALLBACK CardProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
        case WM_PAINT: {
            PAINTSTRUCT ps;
            HDC dc = BeginPaint(hwnd, &ps);
            RECT rc;
            GetClientRect(hwnd, &rc);
            int w = rc.right, h = rc.bottom;
            HDC mem = CreateCompatibleDC(dc);
            HBITMAP bmp = CreateCompatibleBitmap(dc, w, h);
            HGDIOBJ oldBmp = SelectObject(mem, bmp);
            Status st = Snapshot();
            COLORREF acc = g_cardKind == CardKind::Alert ? RGB(255, 150, 70) : Accent(st);
            // fondo: degradado azul noche
            TRIVERTEX vx[2] = {{0, 0, 0x0700, 0x1000, 0x1C00, 0}, {w, h, 0x0200, 0x0500, 0x0B00, 0}};
            GRADIENT_RECT gr = {0, 1};
            GradientFill(mem, vx, 2, &gr, 1, GRADIENT_FILL_RECT_V);
            UINT dpi = DpiOf(hwnd);
            int pad = MulDiv(12, dpi, 96);
            // línea de acento arriba y borde fino
            HBRUSH ab = CreateSolidBrush(acc);
            RECT top = {0, 0, w, MulDiv(3, dpi, 96)};
            FillRect(mem, &top, ab);
            DeleteObject(ab);
            HPEN pen = CreatePen(PS_SOLID, 1, RGB(GetRValue(acc) / 3, GetGValue(acc) / 3, GetBValue(acc) / 3));
            HGDIOBJ oldPen = SelectObject(mem, pen);
            HGDIOBJ oldBr = SelectObject(mem, GetStockObject(NULL_BRUSH));
            int r = MulDiv(14, dpi, 96);
            RoundRect(mem, 0, 0, w, h, r, r);
            SelectObject(mem, oldBr);
            SelectObject(mem, oldPen);
            DeleteObject(pen);
            SetBkMode(mem, TRANSPARENT);
            RECT tr = {pad, pad, w - pad, h - pad};
            HGDIOBJ oldFont = SelectObject(mem, g_fontTitle);
            SetTextColor(mem, acc);
            RECT tcalc = tr;
            DrawTextW(mem, g_cardTitle.c_str(), -1, &tcalc, DT_CALCRECT | DT_SINGLELINE | DT_END_ELLIPSIS | DT_NOPREFIX);
            DrawTextW(mem, g_cardTitle.c_str(), -1, &tr, DT_SINGLELINE | DT_END_ELLIPSIS | DT_NOPREFIX);
            RECT br = {pad, tr.top + (tcalc.bottom - tcalc.top) + MulDiv(6, dpi, 96), w - pad, h - pad};
            SelectObject(mem, g_fontBody);
            SetTextColor(mem, RGB(214, 242, 255));
            DrawTextW(mem, g_cardText.c_str(), -1, &br, DT_WORDBREAK | DT_END_ELLIPSIS | DT_NOPREFIX);
            // barra de progreso del temporizador (tarjeta de estado)
            if (g_cardKind == CardKind::Info && st.timers > 0 && st.total > 0 && st.next >= 0) {
                int bh = MulDiv(3, dpi, 96);
                RECT bg = {pad, h - pad / 2 - bh, w - pad, h - pad / 2};
                HBRUSH dim = CreateSolidBrush(RGB(30, 40, 52));
                FillRect(mem, &bg, dim);
                DeleteObject(dim);
                RECT fg = bg;
                fg.right = bg.left + (int)((bg.right - bg.left) * ((double)st.next / st.total));
                HBRUSH amber = CreateSolidBrush(RGB(255, 181, 71));
                FillRect(mem, &fg, amber);
                DeleteObject(amber);
            }
            SelectObject(mem, oldFont);
            BitBlt(dc, 0, 0, w, h, mem, 0, 0, SRCCOPY);
            SelectObject(mem, oldBmp);
            DeleteObject(bmp);
            DeleteDC(mem);
            EndPaint(hwnd, &ps);
            return 0;
        }
        case WM_LBUTTONUP:
            HideCard();
            Link("jarvis://mostrar");
            return 0;
        case WM_RBUTTONUP:
            HideCard();
            return 0;
        case WM_MOUSEACTIVATE:
            return MA_NOACTIVATE;
        case WM_ERASEBKGND:
            return 1;
    }
    return DefWindowProcW(hwnd, msg, wp, lp);
}

// ------------------------------------------------------------------ cuadro para escribirle
WNDPROC g_editOrig = nullptr;

void CloseInput() {
    if (g_input) {
        HWND w = g_input;
        g_input = nullptr;
        g_edit = nullptr;
        DestroyWindow(w);
    }
}

LRESULT CALLBACK EditProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    if (msg == WM_KEYDOWN && wp == VK_RETURN) {
        wchar_t buf[1024] = {};
        GetWindowTextW(hwnd, buf, 1024);
        std::wstring text = buf;
        while (!text.empty() && text.back() == L' ') text.pop_back();
        if (!text.empty()) Order(text);
        CloseInput();
        return 0;
    }
    if (msg == WM_KEYDOWN && wp == VK_ESCAPE) {
        CloseInput();
        return 0;
    }
    if (msg == WM_CHAR && (wp == VK_RETURN || wp == VK_ESCAPE)) {
        return 0;                                    // sin «ding»
    }
    return CallWindowProcW(g_editOrig, hwnd, msg, wp, lp);
}

HBRUSH g_inputBrush = nullptr;

LRESULT CALLBACK InputProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
        case WM_ACTIVATE:
            if (LOWORD(wp) == WA_INACTIVE) {
                PostMessageW(hwnd, WM_CLOSE, 0, 0);
            }
            return 0;
        case WM_CLOSE:
            CloseInput();
            return 0;
        case WM_CTLCOLOREDIT:
            SetTextColor((HDC)wp, RGB(214, 242, 255));
            SetBkColor((HDC)wp, RGB(8, 16, 28));
            return (LRESULT)g_inputBrush;
        case WM_PAINT: {
            PAINTSTRUCT ps;
            HDC dc = BeginPaint(hwnd, &ps);
            RECT rc;
            GetClientRect(hwnd, &rc);
            FillRect(dc, &rc, g_inputBrush);
            Status st = Snapshot();
            HBRUSH ab = CreateSolidBrush(Accent(st));
            RECT line = {0, rc.bottom - 2, rc.right, rc.bottom};
            FillRect(dc, &line, ab);
            DeleteObject(ab);
            SetBkMode(dc, TRANSPARENT);
            SetTextColor(dc, Accent(st));
            HGDIOBJ of = SelectObject(dc, g_fontSmall);
            RECT tr = rc;
            tr.left += MulDiv(10, DpiOf(hwnd), 96);
            tr.top += MulDiv(5, DpiOf(hwnd), 96);
            DrawTextW(dc, L"Escríbele a Jarvis  ·  Enter para enviar, Esc para cerrar", -1, &tr, DT_SINGLELINE | DT_NOPREFIX);
            SelectObject(dc, of);
            EndPaint(hwnd, &ps);
            return 0;
        }
    }
    return DefWindowProcW(hwnd, msg, wp, lp);
}

void OpenInput() {
    if (g_input) {
        SetForegroundWindow(g_input);
        return;
    }
    HideCard();
    UINT dpi = DpiOf(g_orb);
    int w = MulDiv(360, dpi, 96), h = MulDiv(62, dpi, 96);
    RECT orb;
    GetWindowRect(g_orb, &orb);
    MONITORINFO mi = {};
    mi.cbSize = sizeof(mi);
    GetMonitorInfoW(MonitorFromWindow(g_orb, MONITOR_DEFAULTTONEAREST), &mi);
    int gap = MulDiv(10, dpi, 96);
    int x = (orb.left + orb.right) / 2 - w / 2, y = orb.top - gap - h;
    if (y < mi.rcWork.top) y = orb.bottom + gap;
    if (x + w > mi.rcWork.right - gap) x = mi.rcWork.right - gap - w;
    if (x < mi.rcWork.left + gap) x = mi.rcWork.left + gap;
    HINSTANCE inst = GetModuleHandleW(nullptr);
    g_input = CreateWindowExW(WS_EX_TOPMOST | WS_EX_TOOLWINDOW, kInputClass, L"Jarvis", WS_POPUP, x, y, w, h, nullptr,
                              nullptr, inst, nullptr);
    if (!g_input) return;
    int r = MulDiv(12, dpi, 96);
    SetWindowRgn(g_input, CreateRoundRectRgn(0, 0, w + 1, h + 1, r, r), FALSE);
    int pad = MulDiv(10, dpi, 96);
    g_edit = CreateWindowExW(0, L"EDIT", L"", WS_CHILD | WS_VISIBLE | ES_AUTOHSCROLL, pad, MulDiv(26, dpi, 96),
                             w - 2 * pad, MulDiv(26, dpi, 96), g_input, nullptr, inst, nullptr);
    SendMessageW(g_edit, WM_SETFONT, (WPARAM)g_fontBody, TRUE);
    SendMessageW(g_edit, EM_SETCUEBANNER, TRUE, (LPARAM)L"Por ejemplo: pon un temporizador de 10 minutos");
    g_editOrig = (WNDPROC)SetWindowLongPtrW(g_edit, GWLP_WNDPROC, (LONG_PTR)EditProc);
    ShowWindow(g_input, SW_SHOW);
    SetForegroundWindow(g_input);
    SetFocus(g_edit);
}

// ------------------------------------------------------------------ menú
enum MenuId {
    kMenuListen = 1, kMenuToggle, kMenuType, kMenuPanelWrite, kMenuClass, kMenuTimer5, kMenuTimer10, kMenuPending,
    kMenuPlay, kMenuNext, kMenuPrev, kMenuMic, kMenuCheck, kMenuSettings, kMenuResetPos,
};

void ShowMenu(HWND hwnd) {
    HideCard();
    Status st = Snapshot();
    HMENU m = CreatePopupMenu();
    HMENU music = CreatePopupMenu();
    AppendMenuW(music, MF_STRING, kMenuPlay, L"Pausar o reanudar");
    AppendMenuW(music, MF_STRING, kMenuNext, L"Siguiente");
    AppendMenuW(music, MF_STRING, kMenuPrev, L"Anterior");
    AppendMenuW(m, MF_STRING, kMenuListen, L"Hablar con Jarvis");
    AppendMenuW(m, MF_STRING, kMenuType, L"Escribir aquí…\tMayús+clic");
    AppendMenuW(m, MF_STRING, kMenuToggle, st.visible ? L"Ocultar el panel" : L"Mostrar el panel");
    AppendMenuW(m, MF_SEPARATOR, 0, nullptr);
    AppendMenuW(m, MF_STRING, kMenuClass, L"Modo clase");
    AppendMenuW(m, MF_STRING, kMenuTimer5, L"Temporizador de 5 minutos");
    AppendMenuW(m, MF_STRING, kMenuTimer10, L"Temporizador de 10 minutos");
    AppendMenuW(m, MF_STRING, kMenuPending, L"¿Qué tengo pendiente?");
    AppendMenuW(m, MF_POPUP, (UINT_PTR)music, L"Música");
    AppendMenuW(m, MF_SEPARATOR, 0, nullptr);
    AppendMenuW(m, MF_STRING, kMenuMic, st.mode == Mode::Muted ? L"Reanudar el micrófono" : L"Pausar el micrófono");
    AppendMenuW(m, MF_STRING, kMenuCheck, L"Prueba completa");
    AppendMenuW(m, MF_STRING, kMenuSettings, L"Ajustes de Jarvis");
    if (g_dragOffset) {
        AppendMenuW(m, MF_STRING, kMenuResetPos, L"Volver a su sitio");
    }
    if (st.mode == Mode::Off) {
        for (int id = kMenuListen; id <= kMenuSettings; id++) {
            if (id != kMenuToggle) EnableMenuItem(m, id, MF_BYCOMMAND | MF_GRAYED);
        }
        ModifyMenuW(m, kMenuToggle, MF_BYCOMMAND | MF_STRING, kMenuToggle, L"Abrir Jarvis");
    }
    POINT p;
    GetCursorPos(&p);
    SetForegroundWindow(hwnd);
    int cmd = TrackPopupMenu(m, TPM_RETURNCMD | TPM_RIGHTBUTTON | TPM_BOTTOMALIGN | TPM_CENTERALIGN, p.x, p.y, 0, hwnd, nullptr);
    DestroyMenu(m);
    PostMessageW(hwnd, WM_NULL, 0, 0);
    switch (cmd) {
        case kMenuListen: Link("jarvis://escuchar"); break;
        case kMenuType: OpenInput(); break;
        case kMenuToggle: Link(st.mode == Mode::Off ? "jarvis://mostrar" : "jarvis://alternar"); break;
        case kMenuClass: Link("jarvis://rutina/Modo%20clase"); break;
        case kMenuTimer5: Link("jarvis://temporizador/5"); break;
        case kMenuTimer10: Link("jarvis://temporizador/10"); break;
        case kMenuPending: Link("jarvis://orden/qu%C3%A9%20tengo%20pendiente"); break;
        case kMenuPlay: Link("jarvis://multimedia/pausar"); break;
        case kMenuNext: Link("jarvis://multimedia/siguiente"); break;
        case kMenuPrev: Link("jarvis://multimedia/anterior"); break;
        case kMenuMic: Link("jarvis://microfono"); break;
        case kMenuCheck: Link("jarvis://prueba"); break;
        case kMenuSettings: Link("jarvis://ajustes"); break;
        case kMenuResetPos:
            g_dragOffset = 0;
            Wh_SetIntValue(L"dragOffset", 0);
            Place();
            break;
        default: break;
    }
}

// ------------------------------------------------------------------ ventana del reactor
void OnStatus() {
    Status st = Snapshot();
    Settings cs = Cfg();
    DWORD now = GetTickCount();
    if (g_anim.lastSeq >= 0 && st.seq != g_anim.lastSeq && st.role == L"jarvis") {
        g_anim.rippleStart = now;                              // onda: acaba de responder
        if (cs.bubble && !st.visible && !g_hovering && !g_input && g_cardKind != CardKind::Alert && !st.msg.empty()) {
            ShowCard(CardKind::Message, 4000 + (UINT)st.msg.size() * 45 > 12000 ? 12000 : 4000 + (UINT)st.msg.size() * 45);
        }
    }
    if (g_anim.lastAlertSeq >= 0 && st.alertSeq != g_anim.lastAlertSeq) {
        g_anim.alertUntil = now + 4000;                        // destello del aviso
        if (!g_input) ShowCard(CardKind::Alert, 12000);
    }
    if (st.mode != Mode::Off) {
        g_anim.lastSeq = st.seq;
        g_anim.lastAlertSeq = st.alertSeq;
    } else {
        g_anim.lastSeq = g_anim.lastAlertSeq = -1;             // al volver Jarvis, no repetir lo viejo
    }
    if (g_cardKind == CardKind::Info) {
        BuildInfoCard();
        LayoutCard();
    }
}

LRESULT CALLBACK OrbProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
        case WM_TIMER:
            if (wp == kAnimTimer) {
                RenderOrb();
                Status st = Snapshot();
                bool busy = st.mode == Mode::Thinking || st.mode == Mode::Speaking || st.mode == Mode::Awaiting ||
                            GetTickCount() < g_anim.alertUntil || g_anim.hover > 0.02f;
                SetTimer(hwnd, kAnimTimer, st.mode == Mode::Off ? 400 : busy ? 33 : 66, nullptr);
            } else if (wp == kPlaceTimer) {
                Place();
            } else if (wp == kHoverTimer) {
                KillTimer(hwnd, kHoverTimer);
                if (g_hovering && Cfg().card && !g_input && g_cardKind != CardKind::Alert) {
                    ShowCard(CardKind::Info, 0);
                }
            } else if (wp == kClickTimer) {
                KillTimer(hwnd, kClickTimer);
                Status st = Snapshot();
                if (st.mode == Mode::Off) {
                    Link("jarvis://mostrar");
                } else {
                    Link(Cfg().clickToggles ? "jarvis://alternar" : "jarvis://escuchar");
                }
            } else if (wp == kCardTimer) {
                HideCard();
            }
            return 0;
        case WM_APP_STATUS:
            OnStatus();
            return 0;
        case WM_APP_RELOAD:
            Place();
            RenderOrb();
            return 0;
        case WM_MOUSEMOVE: {
            if (!g_hovering) {
                g_hovering = true;
                TRACKMOUSEEVENT tme = {sizeof(tme), TME_LEAVE, hwnd, 0};
                TrackMouseEvent(&tme);
                SetTimer(hwnd, kHoverTimer, 450, nullptr);
            }
            if (g_down) {
                POINT p;
                GetCursorPos(&p);
                int dxs = p.x - g_downPt.x, dys = p.y - g_downPt.y;
                if (!g_dragging && (abs(dxs) > 6 || abs(dys) > 6)) {
                    g_dragging = true;
                    HideCard();
                }
                if (g_dragging) {
                    HWND tray = FindWindowW(L"Shell_TrayWnd", nullptr);
                    RECT tr = {};
                    if (tray) GetWindowRect(tray, &tr);
                    bool vertical = (tr.bottom - tr.top) > (tr.right - tr.left);
                    g_dragOffset = g_dragStartOffset + (vertical ? dys : -dxs);
                    g_dragging = false;
                    Place();
                    g_dragging = true;
                }
            }
            return 0;
        }
        case WM_MOUSELEAVE:
            g_hovering = false;
            KillTimer(hwnd, kHoverTimer);
            if (g_cardKind == CardKind::Info) HideCard();
            return 0;
        case WM_LBUTTONDOWN:
            g_down = true;
            g_dragging = false;
            GetCursorPos(&g_downPt);
            g_dragStartOffset = g_dragOffset;
            SetCapture(hwnd);
            return 0;
        case WM_LBUTTONUP: {
            if (g_ignoreUp) {                            // el segundo «soltar» de un doble clic
                g_ignoreUp = g_down = g_dragging = false;
                ReleaseCapture();
                return 0;
            }
            bool wasDrag = g_dragging;
            g_down = g_dragging = false;
            ReleaseCapture();
            if (wasDrag) {
                Wh_SetIntValue(L"dragOffset", g_dragOffset);
                return 0;
            }
            if (GetKeyState(VK_SHIFT) & 0x8000) {
                OpenInput();
                return 0;
            }
            SetTimer(hwnd, kClickTimer, GetDoubleClickTime(), nullptr);   // esperar por si es doble clic
            return 0;
        }
        case WM_LBUTTONDBLCLK:
            KillTimer(hwnd, kClickTimer);
            g_ignoreUp = true;
            Link(Cfg().clickToggles ? "jarvis://escuchar" : "jarvis://alternar");
            return 0;
        case WM_MBUTTONUP:
            if (Cfg().wheel) Link("jarvis://multimedia/pausar");
            return 0;
        case WM_MOUSEWHEEL:
            if (Cfg().wheel) {
                Link(GET_WHEEL_DELTA_WPARAM(wp) > 0 ? "jarvis://volumen/subir" : "jarvis://volumen/bajar");
            }
            return 0;
        case WM_RBUTTONUP:
            ShowMenu(hwnd);
            return 0;
        case WM_MOUSEACTIVATE:
            return MA_NOACTIVATE;
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

HFONT MakeFont(int pt, int weight, UINT dpi) {
    return CreateFontW(-MulDiv(pt, dpi, 72), 0, 0, 0, weight, FALSE, FALSE, FALSE, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS,
                       CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH, L"Segoe UI");
}

DWORD WINAPI OrbThread(LPVOID ready) {
    HINSTANCE inst = GetModuleHandleW(nullptr);
    WNDCLASSW wc = {};
    wc.style = CS_DBLCLKS;
    wc.lpfnWndProc = OrbProc;
    wc.hInstance = inst;
    wc.lpszClassName = kOrbClass;
    wc.hCursor = LoadCursorW(nullptr, MAKEINTRESOURCEW(32649));   // mano
    RegisterClassW(&wc);
    WNDCLASSW cc = {};
    cc.lpfnWndProc = CardProc;
    cc.hInstance = inst;
    cc.lpszClassName = kCardClass;
    cc.hCursor = LoadCursorW(nullptr, MAKEINTRESOURCEW(32649));
    RegisterClassW(&cc);
    WNDCLASSW ic = {};
    ic.lpfnWndProc = InputProc;
    ic.hInstance = inst;
    ic.lpszClassName = kInputClass;
    ic.hCursor = LoadCursorW(nullptr, MAKEINTRESOURCEW(32512));
    RegisterClassW(&ic);
    INITCOMMONCONTROLSEX icc = {sizeof(icc), ICC_STANDARD_CLASSES};
    InitCommonControlsEx(&icc);
    g_inputBrush = CreateSolidBrush(RGB(8, 16, 28));

    g_dragOffset = Wh_GetIntValue(L"dragOffset", 0);
    g_orb = CreateWindowExW(WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_LAYERED, kOrbClass, L"Jarvis",
                            WS_POPUP, 0, 0, 40, 40, nullptr, nullptr, inst, nullptr);
    if (g_orb) {
        UINT dpi = DpiOf(FindWindowW(L"Shell_TrayWnd", nullptr));
        g_fontTitle = MakeFont(10, FW_SEMIBOLD, dpi);
        g_fontBody = MakeFont(10, FW_NORMAL, dpi);
        g_fontSmall = MakeFont(8, FW_NORMAL, dpi);
        g_card = CreateWindowExW(WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_LAYERED, kCardClass, L"",
                                 WS_POPUP, 0, 0, 10, 10, nullptr, nullptr, inst, nullptr);
        if (g_card) SetLayeredWindowAttributes(g_card, 0, 242, LWA_ALPHA);
        Place();
        RenderOrb();
        SetTimer(g_orb, kAnimTimer, 66, nullptr);
        SetTimer(g_orb, kPlaceTimer, 1000, nullptr);   // la barra puede moverse, ocultarse o cambiar de tamaño
    } else {
        Wh_Log(L"No se pudo crear el reactor: %u", GetLastError());
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
    CloseInput();
    for (HWND* h : {&g_card, &g_orb}) {
        if (*h) {
            DestroyWindow(*h);
            *h = nullptr;
        }
    }
    for (HFONT* f : {&g_fontTitle, &g_fontBody, &g_fontSmall}) {
        if (*f) {
            DeleteObject(*f);
            *f = nullptr;
        }
    }
    if (g_inputBrush) {
        DeleteObject(g_inputBrush);
        g_inputBrush = nullptr;
    }
    UnregisterClassW(kOrbClass, inst);
    UnregisterClassW(kCardClass, inst);
    UnregisterClassW(kInputClass, inst);
    return 0;
}

}  // namespace

////////////////////////////////////////////////////////////////////////////////
// Ciclo de vida del mod

BOOL Wh_ModInit() {
    InitializeCriticalSection(&g_lock);
    LoadSettings();
    // Puede haber varios explorer.exe: solo uno muestra el reactor.
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
    }
}

void Wh_ModSettingsChanged() {
    LoadSettings();
    if (g_orb) {
        PostMessageW(g_orb, WM_APP_RELOAD, 0, 0);
    }
}
