"""El equipo, con órdenes del sistema (12.9): sin mover el mouse ni teclear por ti. Lógica pura y armado de comandos.

- Programas con winget (el instalador oficial de Windows): buscar, instalar, actualizar y desinstalar.
- Mantenimiento: qué consume más, temporales que se pueden borrar, programas que arrancan con Windows.
- Energía y conexiones: planes de energía, ahorro de batería, Wi-Fi, Bluetooth y modo avión (radios de Windows).
"""
import os
import re
import time
import unicodedata

PROTECTED = {"system", "idle", "registry", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe", "services.exe", "lsass.exe",
             "svchost.exe", "explorer.exe", "dwm.exe", "fontdrvhost.exe", "sihost.exe", "ctfmon.exe", "audiodg.exe", "msmpeng.exe",
             "securityhealthservice.exe", "taskmgr.exe", "conhost.exe", "runtimebroker.exe", "searchhost.exe", "startmenuexperiencehost.exe",
             "memory compression", "spoolsv.exe", "wudfhost.exe", "lsaiso.exe", "dllhost.exe", "textinputhost.exe", "shellexperiencehost.exe",
             "python.exe", "pythonw.exe", "jarvis.exe", "llama-server.exe", "ollama.exe", "ollama app.exe"}
AGREE = ["--accept-source-agreements", "--accept-package-agreements", "--disable-interactivity"]


def norm(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    return re.sub(r"\s+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn")).strip()


# ----------------------------------------------------------------------------- winget
def winget_search(q):
    return ["winget", "search", q, "--source", "winget"] + AGREE[:1] + ["--disable-interactivity"]


def winget_install(pid):
    return ["winget", "install", "--id", pid, "-e", "--silent", "--source", "winget"] + AGREE


def winget_upgrades():
    return ["winget", "upgrade", "--source", "winget"] + AGREE[:1] + ["--disable-interactivity"]


def winget_upgrade_all():
    return ["winget", "upgrade", "--all", "--silent", "--source", "winget"] + AGREE


def winget_upgrade_one(pid):
    return ["winget", "upgrade", "--id", pid, "-e", "--silent", "--source", "winget"] + AGREE


def winget_list(q):
    return ["winget", "list", q] + AGREE[:1] + ["--disable-interactivity"]


def winget_uninstall(pid):
    return ["winget", "uninstall", "--id", pid, "-e", "--silent", "--disable-interactivity"]


def parse_table(out):
    """La tabla de winget (columnas alineadas con espacios) → [{"name","id","version","available"}]."""
    lines = [ln.rstrip() for ln in str(out or "").replace("\r", "\n").split("\n")]
    for i in range(len(lines) - 1):
        if not (re.fullmatch(r"-{10,}", lines[i + 1].strip()) and re.search(r"\bId\b", lines[i])):
            continue
        m0 = re.search(r"(?:^|\s)(\S+)\s+Id\b", lines[i])        # sin la animación de progreso de delante
        shift = m0.start(1) if m0 else 0
        head = lines[i][shift:]
        cols = [(m.start(), m.group(0).lower()) for m in re.finditer(r"\S+", head)]
        rows = []
        for row in lines[i + 2:]:
            if not row.strip():
                continue
            if len(row) < cols[1][0] or re.match(r"^\d+\s", row.strip()):
                break                                               # «3 actualizaciones disponibles.» y lo que sigue
            vals = [row[start:(cols[k + 1][0] if k + 1 < len(cols) else None)].strip() for k, (start, _n) in enumerate(cols)]
            rid = vals[1]
            if not rid or " " in rid:
                continue
            names = [c[1] for c in cols]
            avail = vals[3] if len(vals) > 3 and names[3] in ("available", "disponible") else ""
            rows.append({"name": vals[0], "id": rid, "version": vals[2] if len(vals) > 2 else "", "available": avail})
        return rows
    return []


def best_package(rows, q):
    """El paquete que mejor coincide con lo que pediste (nombre exacto > empieza igual > contiene)."""
    n = norm(q)
    if not rows:
        return None
    for test in (lambda r: norm(r["name"]) == n, lambda r: norm(r["id"]).split(".")[-1] == n.replace(" ", ""),
                 lambda r: norm(r["name"]).startswith(n), lambda r: n in norm(r["name"]) or n.replace(" ", "") in norm(r["id"])):
        hit = [r for r in rows if test(r)]
        if hit:
            return sorted(hit, key=lambda r: len(r["name"]))[0]
    return None


# ----------------------------------------------------------------------------- procesos
def top_processes(procs, n=5):
    """procs: [{"name","rss","cpu"}] (un proceso por fila) → agrupados por programa, del que más consume al que menos."""
    agg = {}
    for p in procs:
        name = str(p.get("name") or "").strip()
        if not name:
            continue
        a = agg.setdefault(name.lower(), {"name": name, "rss": 0, "cpu": 0.0, "n": 0})
        a["rss"] += int(p.get("rss") or 0)
        a["cpu"] += float(p.get("cpu") or 0)
        a["n"] += 1
    rows = list(agg.values())
    return sorted(rows, key=lambda r: (r["cpu"] * 40_000_000 + r["rss"]), reverse=True)[:n]


def friendly(proc_name):
    base = re.sub(r"\.exe$", "", str(proc_name), flags=re.I)
    return {"msedge": "Edge", "chrome": "Chrome", "firefox": "Firefox", "winword": "Word", "excel": "Excel", "powerpnt": "PowerPoint",
            "teams": "Teams", "ms-teams": "Teams", "code": "VS Code", "spotify": "Spotify", "whatsapp": "WhatsApp", "zoom": "Zoom",
            "onedrive": "OneDrive", "discord": "Discord", "acrord32": "Adobe Reader", "acrobat": "Adobe Acrobat"}.get(base.lower(), base)


def can_close(proc_name):
    return str(proc_name).lower() not in PROTECTED


# ----------------------------------------------------------------------------- temporales
def temp_candidates(dirs, now=None, min_age_h=24, limit=200_000):
    """Archivos temporales con más de un día (los recientes los puede estar usando un programa). → ([rutas], bytes)."""
    now = now or time.time()
    files, total = [], 0
    for d in dirs:
        for root, _dirs, names in os.walk(d):
            for nm in names:
                p = os.path.join(root, nm)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                if now - st.st_mtime >= min_age_h * 3600:
                    files.append(p)
                    total += st.st_size
                if len(files) >= limit:
                    return files, total
    return files, total


def gb(n):
    return f"{n / 1e9:.1f}".replace(".", ",") + " GB" if n >= 1e9 else f"{n / 1e6:.0f} MB"


# ----------------------------------------------------------------------------- programas al inicio
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED_RUN = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
APPROVED_FOLDER = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder"


def approved_enabled(raw):
    """El valor binario de StartupApproved: el primer byte par (02, 06) = activo; impar (03, 07) = desactivado."""
    return not raw or (raw[0] % 2 == 0)


def approved_value(enabled, filetime=0):
    return (b"\x02" if enabled else b"\x03") + b"\x00\x00\x00" + int(filetime).to_bytes(8, "little")


def filetime_now():
    return int((time.time() + 11644473600) * 10_000_000)


# ----------------------------------------------------------------------------- energía
PLAN_ALIASES = {"equilibrado": ("equilibrado", "balanced", "recomendado"), "alto": ("alto rendimiento", "high performance", "maximo rendimiento",
                                                                                     "ultimate performance", "rendimiento"),
                "ahorro": ("economizador", "ahorro", "power saver", "economia", "bajo consumo")}


def parse_plans(out):
    """powercfg /list → [{"guid","name","active"}] (sirve en español e inglés)."""
    plans = []
    for ln in str(out or "").splitlines():
        m = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\s*\(([^)]*)\)\s*(\*)?", ln, re.I)
        if m:
            plans.append({"guid": m.group(1), "name": m.group(2).strip(), "active": bool(m.group(3))})
    return plans


def pick_plan(plans, want):
    keys = PLAN_ALIASES.get(want, (want,))
    for p in plans:
        if any(k in norm(p["name"]) for k in keys):
            return p
    return None


# ----------------------------------------------------------------------------- radios (Wi-Fi, Bluetooth, modo avión)
_PS_RADIO = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
Function Await($t, $type) { $n = $asTask.MakeGenericMethod($type).Invoke($null, @($t)); $n.Wait(-1) | Out-Null; $n.Result }
[Windows.Devices.Radios.Radio,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null
[Windows.Devices.Radios.RadioAccessStatus,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null
[Windows.Devices.Radios.RadioState,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null
Await ([Windows.Devices.Radios.Radio]::RequestAccessAsync()) ([Windows.Devices.Radios.RadioAccessStatus]) | Out-Null
$radios = Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])
"""


def radio_script(kinds, state=None):
    """PowerShell que cambia (o solo informa, con state=None) las radios de esos tipos. Imprime «Tipo=Estado» por línea."""
    sel = ",".join(f"'{k}'" for k in kinds)
    body = _PS_RADIO + f"foreach ($r in $radios) {{ if (@({sel}) -contains [string]$r.Kind) {{ "
    if state in ("On", "Off"):
        body += f"Await ($r.SetStateAsync('{state}')) ([Windows.Devices.Radios.RadioAccessStatus]) | Out-Null; "
    body += "Write-Output (\"$($r.Kind)=$($r.State)\") } }"
    return body


def parse_radios(out):
    res = {}
    for ln in str(out or "").splitlines():
        m = re.match(r"\s*(\w+)=(\w+)", ln)
        if m:
            res[m.group(1)] = m.group(2)
    return res


def parse_ssid(out):
    """netsh wlan show interfaces → la red Wi-Fi a la que estás conectado ("" si ninguna)."""
    for ln in str(out or "").splitlines():
        m = re.match(r"\s*SSID\s*:\s*(.+)$", ln)
        if m and "BSSID" not in ln:
            return m.group(1).strip()
    return ""


def parse_profiles(out):
    """netsh wlan show profiles → nombres de las redes guardadas."""
    return [ln.split(":", 1)[1].strip() for ln in str(out or "").splitlines()
            if re.search(r"(?:Perfil de todos los usuarios|All User Profile|Perfil de usuario|User Profile)\s*:", ln) and ln.split(":", 1)[1].strip()]
