"""Proyectos de varios pasos con sub-agentes (7.6): «prepárame la semana de 7A sobre fracciones».

La IA convierte el pedido en un plan de pasos de tipos conocidos (investigar, plan de clase, taller, quiz, rúbrica,
presentación, texto), con dependencias. Jarvis te lo muestra y, cuando lo apruebas, lo hace: los pasos que no
dependen de otros van en paralelo (cada uno es un «sub-agente» con su propia tarea), y lo que sale de un paso (por
ejemplo, la investigación) se le pasa a los que dependen de él. Todo queda en una carpeta del proyecto, con un
resumen. Si Jarvis se cierra a mitad, el proyecto se puede continuar.
"""
import datetime
import json
import os
import re
import threading
import time
import uuid

_lock = threading.Lock()
_dir = None
TYPES = {
    "investigar": "investigación con fuentes en internet (un informe en Word con citas)",
    "plan": "plan de clase (objetivo, inicio, desarrollo, cierre, evaluación) en Word",
    "taller": "taller o guía de trabajo para los estudiantes en Word",
    "quiz": "evaluación o quiz con preguntas y respuestas en Word",
    "rubrica": "rúbrica de evaluación en Word",
    "presentacion": "presentación de diapositivas en PowerPoint",
    "texto": "un texto libre en Word: carta a padres, guía, resumen, correo, comunicado, etc.",
    "imagen": "una imagen o ilustración para la clase (solo si el docente pide imágenes)",
    "saber": "preguntas tipo Saber (ICFES) con contexto y competencia",
    "malla": "la malla curricular o planeación de todo un periodo, semana a semana",
    "piar": "ajustes razonables (PIAR) de un material para un estudiante con una necesidad específica",
    "lectura": "una lectura en tres niveles (básico, intermedio y avanzado) con vocabulario y preguntas",
}
MAX_STEPS = 8


def configure(config_dir):
    global _dir
    _dir = os.path.join(config_dir, "proyectos")


def plan_prompt(goal, context=""):
    tipos = "\n".join(f"- {k}: {v}" for k, v in TYPES.items())
    return ("Eres el planificador de Jarvis, el asistente de un docente en Colombia. Convierte este pedido en un plan "
            f"de pasos concretos que Jarvis hará solo.\nPedido: «{goal}»\n" + (f"Contexto: {context}\n" if context else "") +
            f"Tipos de paso disponibles (usa SOLO estos):\n{tipos}\n\n"
            f"Reglas: entre 2 y {MAX_STEPS} pasos; cada paso con un «pedido» completo y concreto (tema, grado, cantidad), "
            "como se lo dirías a un asistente; si un paso necesita lo que produce otro, ponlo en «depende» (por ejemplo, "
            "planear las clases depende de investigar); no repitas pasos; si es «la semana», reparte en varias clases.\n"
            'Responde SOLO con JSON: {"nombre": "nombre corto del proyecto", "pasos": [{"id": "p1", "tipo": "investigar", '
            '"titulo": "…", "pedido": "…", "depende": []}, …]}')


def validate_plan(d, goal=""):
    """Comprueba y limpia el plan. Lanza ValueError si no sirve."""
    if not isinstance(d, dict) or not isinstance(d.get("pasos"), list):
        raise ValueError("el plan no tiene pasos")
    pasos, ids = [], set()
    for i, p in enumerate(d["pasos"][:MAX_STEPS]):
        if not isinstance(p, dict):
            continue
        tipo = str(p.get("tipo", "")).strip().lower()
        tipo = {"investigacion": "investigar", "presentación": "presentacion", "rúbrica": "rubrica",
                "evaluacion": "quiz", "plan de clase": "plan"}.get(tipo, tipo)
        if tipo not in TYPES:
            continue
        pid = re.sub(r"[^\w-]", "", str(p.get("id") or f"p{i + 1}"))[:12] or f"p{i + 1}"
        while pid in ids:
            pid += "b"
        ids.add(pid)
        pedido = str(p.get("pedido") or p.get("titulo") or "").strip()[:600]
        if len(pedido) < 4:
            continue
        pasos.append({"id": pid, "tipo": tipo, "titulo": str(p.get("titulo") or pedido)[:120].strip(),
                      "pedido": pedido, "depende": [str(x) for x in (p.get("depende") or []) if isinstance(x, (str, int))]})
    valid = {p["id"] for p in pasos}
    for p in pasos:
        p["depende"] = [x for x in p["depende"] if x in valid and x != p["id"]]
    # sin ciclos: si los hay, se quitan las dependencias que los causan
    order, seen = [], set()
    for _ in range(len(pasos) + 1):
        for p in pasos:
            if p["id"] not in seen and all(x in seen for x in p["depende"]):
                order.append(p)
                seen.add(p["id"])
    for p in pasos:
        if p["id"] not in seen:
            p["depende"] = []
            order.append(p)
            seen.add(p["id"])
    if len(order) < 1:
        raise ValueError("el plan no tiene pasos válidos")
    nombre = str(d.get("nombre") or goal or "Proyecto").strip()[:80]
    return {"nombre": nombre, "pasos": order}


def spoken_plan(plan):
    names = {"investigar": "investigar", "plan": "plan de clase", "taller": "taller", "quiz": "evaluación",
             "rubrica": "rúbrica", "presentacion": "presentación", "texto": "texto", "imagen": "imagen",
             "saber": "preguntas tipo Saber", "malla": "malla curricular", "piar": "ajustes razonables",
             "lectura": "lectura nivelada"}
    items = [f"{i + 1}) {names.get(p['tipo'], p['tipo'])}: {p['titulo']}" for i, p in enumerate(plan["pasos"])]
    return f"Proyecto «{plan['nombre']}», {len(items)} pasos: " + "; ".join(items) + "."


# ----------------------------------------------------------------------------- estado
def new(goal, plan, out_root):
    pid = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    folder = os.path.join(out_root, "Proyectos", f"{safe_name(plan['nombre'])} - {datetime.date.today():%Y-%m-%d}")
    n = 2
    base = folder
    while os.path.exists(folder):
        folder = f"{base} ({n})"
        n += 1
    st = {"id": pid, "pedido": goal, "nombre": plan["nombre"], "carpeta": folder, "estado": "pendiente",
          "creado": time.time(), "terminado": 0,
          "pasos": [dict(p, estado="pendiente", archivo="", resumen="", error="", inicio=0, fin=0) for p in plan["pasos"]]}
    save(st)
    return st


def save(st):
    if not _dir:
        return
    try:
        with _lock:
            os.makedirs(_dir, exist_ok=True)
            p = os.path.join(_dir, st["id"] + ".json")
            with open(p + ".tmp", "w", encoding="utf-8") as f:
                json.dump(st, f, ensure_ascii=False, indent=1)
            os.replace(p + ".tmp", p)
    except OSError:
        pass


def load_all():
    if not _dir or not os.path.isdir(_dir):
        return []
    out = []
    for name in sorted(os.listdir(_dir)):
        if name.endswith(".json"):
            try:
                with open(os.path.join(_dir, name), encoding="utf-8") as f:
                    out.append(json.load(f))
            except (OSError, ValueError):
                continue
    return out


def unfinished():
    return [p for p in load_all() if p.get("estado") in ("en marcha", "interrumpido")]


def ready_steps(st):
    """Pasos que ya se pueden empezar: pendientes y con todas sus dependencias hechas."""
    done = {p["id"] for p in st["pasos"] if p["estado"] == "hecho"}
    failed = {p["id"] for p in st["pasos"] if p["estado"] in ("error", "omitido")}
    out = []
    for p in st["pasos"]:
        if p["estado"] != "pendiente":
            continue
        if any(d in failed for d in p["depende"]):
            p["estado"] = "omitido"
            p["error"] = "dependía de un paso que falló"
            continue
        if all(d in done for d in p["depende"]):
            out.append(p)
    return out


def finished(st):
    return all(p["estado"] in ("hecho", "error", "omitido") for p in st["pasos"])


def context_for(st, step, limit=2500):
    """Lo que produjeron los pasos de los que depende (para pasárselo al sub-agente)."""
    parts = []
    for p in st["pasos"]:
        if p["id"] in step["depende"] and p["resumen"]:
            parts.append(f"[{p['titulo']}]\n{p['resumen'][:limit]}")
    return "\n\n".join(parts)


def progress_text(st):
    n = len(st["pasos"])
    hechos = sum(1 for p in st["pasos"] if p["estado"] == "hecho")
    activos = [p["titulo"] for p in st["pasos"] if p["estado"] == "en marcha"]
    errores = sum(1 for p in st["pasos"] if p["estado"] in ("error", "omitido"))
    txt = f"Proyecto «{st['nombre']}»: {hechos} de {n} pasos listos"
    if activos:
        txt += ", ahora: " + ", ".join(activos[:3])
    if errores:
        txt += f"; {errores} no salieron"
    return txt + "."


def summary_text(st):
    hechos = [p for p in st["pasos"] if p["estado"] == "hecho"]
    malos = [p for p in st["pasos"] if p["estado"] in ("error", "omitido")]
    txt = f"Terminé el proyecto «{st['nombre']}»: {len(hechos)} de {len(st['pasos'])} pasos listos"
    if malos:
        txt += " (no salieron: " + ", ".join(p["titulo"] for p in malos[:3]) + ")"
    return txt + ". Todo está en la carpeta Proyectos de tus documentos de Jarvis."


def safe_name(text):
    t = re.sub(r'[<>:"/\\|?*\x00-\x1f.]+', " ", str(text)).strip()
    return re.sub(r"\s+", " ", t)[:60] or "Proyecto"


_TRIGGER = re.compile(
    r"\b(?:prepar\w*|organiz\w*|arma\w*|planea\w*|disen\w*|haz\w*|crea\w*)\s+(?:me\s+)?(?:toda\s+|todo\s+)?"
    r"(?:la|una|el|un)?\s*(?:semana|unidad|secuencia(?: didactica)?|proyecto|periodo|clase completa|jornada)\b"
    r"|^(?:jarvis\s+)?proyecto\b|\bprepar\w*\s+todo\s+(?:lo|para)\b|\bhaz(?:me)? un proyecto\b")


def is_project(t):
    return bool(_TRIGGER.search(t))
