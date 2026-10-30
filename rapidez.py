"""¿Cuánto tarda Jarvis en contestar, y dónde se va el tiempo?

Cada turno se mide por etapas:
    transcribir   la 2ª etapa del reconocimiento (Whisper o Gemini), si la hay
    esperar       desde que tiene tu frase hasta que empieza a atenderla (cola)
    pensar        entender la orden y preparar la respuesta (aquí entra la IA)
    voz           generar el audio de la primera frase
    arrancar      empezar a sonar
jarvis.py marca los momentos; este módulo calcula, guarda los últimos turnos y lo cuenta.
"""
import threading
import time
from collections import deque

STAGES = (("transcribir", "t0", "transcripcion"), ("esperar", "transcripcion", "orden"),
          ("pensar", "orden", "respuesta"), ("voz", "respuesta", "voz_lista"), ("arrancar", "voz_lista", "sonando"))
NAMES = {"transcribir": "reconocer tu voz", "esperar": "ponerse a ello", "pensar": "pensar la respuesta",
         "voz": "generar la voz", "arrancar": "empezar a sonar"}
SLOW_TOTAL = 4.0
STALE = 90.0

_lock = threading.Lock()
cur = None
hist = deque(maxlen=60)


def begin(source, now=None):
    global cur
    with _lock:
        cur = {"src": source, "t0": now or time.time()}


def mark(name, now=None):
    """Anota un momento del turno en curso (solo la primera vez)."""
    global cur
    now = now or time.time()
    with _lock:
        if cur is not None and now - cur["t0"] > STALE:
            cur = None                                     # turno abandonado (no hubo respuesta): se descarta
        if cur is not None and name not in cur:
            cur[name] = now
            if name == "sonando":
                return _finish()
    return None


def finish_without_voice():
    with _lock:
        if cur is not None and "respuesta" in cur and "sonando" not in cur:
            return _finish()
    return None


def _finish():
    global cur
    t = cur
    cur = None
    if "transcripcion" not in t:
        t["transcripcion"] = t["t0"]
    out = {"src": t["src"], "total": round((t.get("sonando") or t.get("respuesta") or t["t0"]) - t["t0"], 2)}
    for name, a, b in STAGES:
        if a in t and b in t:
            out[name] = round(max(0.0, t[b] - t[a]), 2)
    hist.append(out)
    return out


def line(r):
    parts = [f"{k} {r[k]:.1f} s" for k, _, _ in STAGES if r.get(k)]
    return f"Respondí en {r['total']:.1f} s ({', '.join(parts)})" if parts else f"Respondí en {r['total']:.1f} s"


def summary(n=20):
    """Promedios de los últimos turnos con voz: {"turnos", "total", etapa: segundos, "lenta": etapa}."""
    items = [r for r in list(hist)[-n:] if r.get("total")]
    if not items:
        return None
    avg = {"turnos": len(items), "total": round(sum(r["total"] for r in items) / len(items), 2)}
    for name, _, _ in STAGES:
        vals = [r[name] for r in items if name in r]
        if vals:
            avg[name] = round(sum(vals) / len(vals), 2)
    stages = {k: avg[k] for k, _, _ in STAGES if k in avg}
    avg["lenta"] = max(stages, key=stages.get) if stages else ""
    return avg


TIPS = {
    "transcribir": "la segunda etapa del reconocimiento: con Whisper prueba un modelo más pequeño, o deja «Gemini» si tienes buena conexión",
    "pensar": "la IA: con Ollama prueba un modelo más pequeño (llama3.2 o qwen3:4b); en la nube, uno «flash» o «mini»",
    "voz": "generar la voz: Piper (sin internet) es la más rápida; la de Gemini, la más lenta",
    "esperar": "el equipo está ocupado: cierra programas pesados",
    "arrancar": "el audio tarda en empezar: revisa la salida de sonido",
}


def spoken(s):
    if not s:
        return "Aún no he medido ninguna respuesta. Pregúntame algo y vuelve a preguntarme."
    txt = f"En mis últimas {s['turnos']} respuestas tardé de media {s['total']:.1f} segundos"
    if s.get("lenta"):
        txt += f", y lo que más tarda es {NAMES[s['lenta']]} ({s[s['lenta']]:.1f} s)"
    txt += "."
    if s["total"] > SLOW_TOTAL and s.get("lenta") in TIPS:
        txt += " Para ir más rápido: " + TIPS[s["lenta"]] + "."
    return txt
