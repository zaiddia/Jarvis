"""«Avísame cuando termine…»: Jarvis vigila algo y te avisa (por voz y, si no estás, por Telegram).

    «avísame cuando termine la descarga»            → la carpeta Descargas deja de tener archivos a medio bajar
    «avísame cuando se cierre Zoom»                  → ese programa ya no está abierto
    «avísame cuando termine de instalar» / «… cuando Premiere termine» → el programa deja de trabajar (CPU baja)

Este módulo solo entiende la frase y decide si ya terminó; jarvis.py le da las mediciones (archivos de
la carpeta, procesos abiertos, uso de CPU) cada pocos segundos. Así se puede probar sin descargar nada.
"""
import datetime
import re
import unicodedata

PARTIAL = (".crdownload", ".part", ".partial", ".download", ".opdownload", ".tmp")
MAX_HOURS = 6

_KNOWN = {   # nombre dicho -> nombres de proceso
    "zoom": ["zoom"], "teams": ["ms-teams", "teams"], "chrome": ["chrome"], "edge": ["msedge"], "firefox": ["firefox"],
    "word": ["winword"], "excel": ["excel"], "powerpoint": ["powerpnt"], "spotify": ["spotify"], "steam": ["steam"],
    "premiere": ["adobe premiere pro", "premiere"], "photoshop": ["photoshop"], "obs": ["obs64", "obs"],
    "vlc": ["vlc"], "outlook": ["outlook", "olk"], "whatsapp": ["whatsapp"], "discord": ["discord"],
    "instalador": ["setup", "install", "msiexec", "installer"], "windows update": ["tiworker", "wuauclt"],
    "davinci": ["resolve"], "blender": ["blender"], "handbrake": ["handbrake"], "winrar": ["winrar"], "7zip": ["7zfm", "7zg"],
}


def _norm(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", t)).strip()


_ASK = r"(?:avisame|aviseme|me avisas|me avisa|dime|notificame|recuerdame|alertame)"


def parse(text):
    """{"kind": "descarga"|"cierre"|"proceso", "target": str, "label": str} o None."""
    t = _norm(text)
    if not re.search(rf"\b{_ASK}\b", t) or not re.search(r"\b(?:cuando|apenas|en cuanto|al)\b", t):
        return None
    if re.search(r"\b(?:descarga|descargas|descargue|descarguen|baje|bajen|termine de bajar|se baje)\b", t):
        return {"kind": "descarga", "target": "", "label": "la descarga"}
    m = re.search(r"\b(?:se cierre|cierre|cierren|se cierren|salga de|se apague)\s+(?:el |la |de )?(.+)$", t)
    if m:
        name = m.group(1).strip()
        return {"kind": "cierre", "target": name, "label": f"que se cierre {name}"}
    if re.search(r"\b(?:instalar|instalacion|instale|actualizacion de windows|windows update)\b", t):
        target = "windows update" if "windows" in t else "instalador"
        return {"kind": "proceso", "target": target, "label": "la instalación" if target == "instalador" else "Windows Update"}
    m = re.search(r"\b(?:termine|acabe|finalice)\s+(?:de \w+\s+)?(?:el |la |de |con )?(?:render(?:izar)?\s+(?:de |en )?|exportar?\s+(?:de |en )?)?(.+)$", t) \
        or re.search(r"\b(?:cuando|apenas)\s+(.+?)\s+(?:termine|acabe)\b", t)
    if m:
        name = re.sub(r"^(?:el|la|los|las|de|mi)\s+", "", m.group(1).strip())
        if name in ("descarga",):
            return {"kind": "descarga", "target": "", "label": "la descarga"}
        return {"kind": "proceso", "target": name, "label": f"que termine {name}"}
    return None


def procs_for(name):
    n = _norm(name)
    for k, v in _KNOWN.items():
        if k in n or n in k:
            return v
    return [n.replace(" ", "")]


def _match(procs, running):
    """¿Algún proceso abierto se llama como alguno de procs? running: lista de nombres (sin .exe)."""
    names = [_norm(r).replace(".exe", "") for r in running]
    return [r for r in names if any(p in r for p in procs)]


class Watch:
    def __init__(self, req, now=None):
        self.kind, self.target, self.label = req["kind"], req.get("target", ""), req.get("label", "")
        self.created = now or datetime.datetime.now()
        self.seen_partial = False
        self.seen_running = False
        self.busy_since = None
        self.calm_since = None
        self.stable_since = None

    def expired(self, now):
        return (now - self.created).total_seconds() > MAX_HOURS * 3600

    def step(self, now, partial_files=(), running=(), cpu=None):
        """Devuelve el aviso si ya terminó, «timeout» si no hubo nada que vigilar, o None si sigue.
        partial_files: archivos a medio bajar en Descargas. running: procesos abiertos. cpu: % del programa."""
        if self.expired(now):
            return "timeout"
        if self.kind == "descarga":
            if partial_files:
                self.seen_partial, self.stable_since = True, None
                return None
            if not self.seen_partial:
                # aún no empezó: espera 3 minutos a que aparezca
                return "timeout" if (now - self.created).total_seconds() > 180 else None
            if self.stable_since is None:
                self.stable_since = now
                return None
            if (now - self.stable_since).total_seconds() >= 5:
                return "Listo: terminó la descarga."
            return None
        procs = procs_for(self.target)
        found = _match(procs, running)
        if self.kind == "cierre":
            if found:
                self.seen_running = True
                return None
            if not self.seen_running:
                return "notfound"
            return f"Ya se cerró {self.target}."
        # proceso: estuvo trabajando (CPU alta) y ahora está tranquilo un minuto, o se cerró
        if not found:
            if self.seen_running:
                return f"Listo: terminó {self.label.replace('que termine ', '')}."
            return "notfound" if (now - self.created).total_seconds() > 20 else None
        self.seen_running = True
        if cpu is None:
            return None
        if cpu >= 8:
            self.busy_since, self.calm_since = self.busy_since or now, None
            return None
        if self.busy_since is None:
            return None
        self.calm_since = self.calm_since or now
        if (now - self.calm_since).total_seconds() >= 60:
            return f"Parece que terminó {self.label.replace('que termine ', '')}: ya no está trabajando."
        return None
