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
    # 12.26: pasos de la vida diaria (no solo del colegio)
    "tabla": "una hoja de Excel: presupuesto, comparativo, lista de compras con precios, menú de la semana, horario, inventario…",
    "correo": "redactar un correo para alguien; Jarvis lo deja listo y PIDE PERMISO antes de enviarlo (en «pedido», a quién y qué decir)",
    "orden": "una orden corta que Jarvis ya sabe hacer: «recuérdame el viernes a las 9 pagar el arriendo», «anota que…», "
             "«agrega leche a la lista de mercado». En «pedido» va la orden tal cual se diría",
    "adjunto": "trabajar con el último audio, video o documento que el usuario subió con el clip: transcribirlo, sacar el acta, "
               "subtítulos o resumirlo (en «pedido»: transcribir, acta, subtitulos o resumen)",
}
GENERAL = ("investigar", "texto", "tabla", "correo", "orden", "adjunto", "presentacion", "imagen")
SAFE_ORDER = re.compile(r"^(?:recuerdame|recordarme|anota|apunta|toma nota|agrega|anade|añade|pon|guarda|crea una lista|haz una lista|avisame)\b")
MAX_STEPS = 8


def configure(config_dir):
    global _dir
    _dir = os.path.join(config_dir, "proyectos")


def persona():
    """Quién es Jarvis para el planificador; modos.py lo cambia según el modo."""
    return "el asistente personal de una persona en Colombia"


def plan_types(general=False):
    return {k: v for k, v in TYPES.items() if not general or k in GENERAL}


def plan_prompt(goal, context="", general=False):
    tipos = "\n".join(f"- {k}: {v}" for k, v in plan_types(general).items())
    return (f"Eres el planificador de Jarvis, {persona()}. Convierte este pedido en un plan "
            f"de pasos concretos que Jarvis hará solo.\nPedido: «{goal}»\n" + (f"Contexto: {context}\n" if context else "") +
            f"Tipos de paso disponibles (usa SOLO estos):\n{tipos}\n\n"
            f"Reglas: entre 2 y {MAX_STEPS} pasos; cada paso con un «pedido» completo y concreto (tema, grado, cantidad), "
            "como se lo dirías a un asistente; si un paso necesita lo que produce otro, ponlo en «depende» (por ejemplo, "
            "planear las clases depende de investigar); no repitas pasos; si es «la semana», reparte en varias clases.\n"
            + ("No supongas que es del colegio: es la vida diaria (casa, trabajo, plata, viajes, trámites, salud, ocio). "
               "Para enviar algo usa «correo» (nunca se envía sin permiso); para recordar o anotar, «orden».\n" if general else "") +
            'Responde SOLO con JSON: {"nombre": "nombre corto del proyecto", "pasos": [{"id": "p1", "tipo": "investigar", '
            '"titulo": "…", "pedido": "…", "depende": []}, …]}')


def _plain(text):
    import unicodedata
    t = unicodedata.normalize("NFD", str(text or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").strip(" «»\"'")


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
        if tipo == "orden" and not SAFE_ORDER.match(_plain(p.get("pedido"))):
            continue                                       # solo recordar, anotar y listas: nada que borre, apague o envíe
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
             "lectura": "lectura nivelada", "tabla": "hoja de Excel", "correo": "correo (te pido permiso antes de enviarlo)",
             "orden": "orden", "adjunto": "tu archivo subido"}
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


_GENERAL_TRIGGER = re.compile(
    r"\b(?:encargate|ocupate|hazte cargo)\s+de\b|\b(?:organiza|planea|planifica|prepara|arma)(?:me)?\s+(?:mi|el|la|un|una)\s+"
    r"(?:fin de semana|viaje|paseo|vacaciones|mudanza|fiesta|cumpleanos|evento|reunion familiar|semana|mes|presupuesto del mes)\b")
_VERB = (r"busca|investiga|compara|escribe|escribele|redacta|manda|mandale|envia|enviale|crea|haz|hazme|prepara|preparame|transcribe|"
         r"transcribelo|saca|sacale|mandasela|mandaselo|mandala|mandalo|enviasela|enviaselo|enviala|resume|resumelo|recuerdame|anota|agrega|calcula|traduce|genera|organiza|planea|arma")
_STEP_SPLIT = re.compile(r"\s*(?:,\s*(?:y\s+)?(?:luego\s+|despues\s+|tambien\s+)?|\s+y\s+(?:luego|despues|tambien|ademas)\s+|\s+y\s+(?=(?:" + _VERB + r")\b)|"
                         r"\s+(?:luego|despues|ademas)\s+)")


def chain_steps(t):
    """12.26: «transcribe el audio, saca el acta y mándasela a coordinación» → las partes, si son 2 o más órdenes de verdad."""
    parts = [p.strip() for p in _STEP_SPLIT.split(t) if p and p.strip()]
    good = [p for p in parts if re.match(r"(?:" + _VERB + r")\b", p) and len(p.split()) >= 2]
    verbs = {re.match(r"\w+", p).group(0)[:5] for p in good}
    if all(SAFE_ORDER.match(x) for x in good):
        return []                                         # «haz una lista y agrega leche»: eso se hace sin proyecto
    return good if len(good) >= 2 and len(good) == len(parts) and len(verbs) >= 2 else []


def is_project(t, general=False):
    return bool(_TRIGGER.search(t) or _GENERAL_TRIGGER.search(t) or chain_steps(t))


# ============================================================================ 12.31: INFORME FINAL, REVISOR Y MODELO POR PASO
LIGHT = ("orden", "correo", "adjunto")                     # pasos sencillos: el modelo rápido basta
_NUM = {"uno": 1, "primera": 1, "dos": 2, "segunda": 2, "tres": 3, "tercera": 3, "cuatro": 4, "cuarta": 4, "cinco": 5, "quinta": 5,
        "seis": 6, "sexta": 6, "siete": 7, "septima": 7, "ocho": 8, "octava": 8}


def step_brain(tipo):
    """«rapido» o «potente» para este tipo de paso (el informe y el revisor van siempre con el potente)."""
    return "rapido" if tipo in LIGHT else "potente"


def report_prompt(st, limit=1800):
    """Lo que se le pide a la IA para unir todo en un solo informe."""
    parts = []
    for i, p in enumerate(st["pasos"], 1):
        if p["estado"] == "hecho" and p.get("resumen"):
            parts.append(f"[Paso {i}: {p['titulo']} ({p['tipo']})]\n{str(p['resumen'])[:limit]}")
    return ("Eres el redactor final de un proyecto que hicieron varios sub-agentes. Une lo que produjeron en UN informe claro "
            f"para la persona que lo pidió.\nPedido original: «{st['pedido']}»\nProyecto: «{st['nombre']}»\n\n"
            "Lo que salió de cada paso:\n" + "\n\n".join(parts) + "\n\n"
            "Reglas: no inventes datos que no estén arriba; si algo no se pudo hacer, dilo. Español claro, sin markdown.\n"
            'Responde SOLO con JSON: {"titulo": "…", "resumen": "3 a 5 frases con lo esencial", '
            '"secciones": [{"titulo": "…", "texto": "párrafos"}], "conclusiones": "qué sigue o qué decidir"}')


def report_validate(d, st):
    if not isinstance(d, dict):
        raise ValueError("el informe no vino en JSON")
    secs = []
    for s in (d.get("secciones") or [])[:12]:
        if isinstance(s, dict) and str(s.get("texto") or "").strip():
            secs.append({"titulo": str(s.get("titulo") or "Parte").strip()[:120], "texto": str(s["texto"]).strip()[:6000]})
    if not secs:
        raise ValueError("el informe vino sin secciones")
    return {"titulo": str(d.get("titulo") or f"Informe: {st['nombre']}").strip()[:140],
            "resumen": str(d.get("resumen") or "").strip()[:2000], "secciones": secs,
            "conclusiones": str(d.get("conclusiones") or "").strip()[:3000], "revision": None}


def report_text(rep):
    out = [rep["titulo"], "", "Resumen", rep["resumen"], ""]
    for i, s in enumerate(rep["secciones"], 1):
        out += [f"{i}. {s['titulo']}", s["texto"], ""]
    if rep["conclusiones"]:
        out += ["Conclusiones", rep["conclusiones"]]
    return "\n".join(out)


def review_prompt(rep, st, limit=1500):
    """El revisor: compara el informe con lo que de verdad produjeron los pasos (las fuentes)."""
    src = "\n\n".join(f"[{p['titulo']}]\n{str(p['resumen'])[:limit]}" for p in st["pasos"] if p["estado"] == "hecho" and p.get("resumen"))
    return ("Eres el revisor de un informe. Compáralo con lo que produjeron los pasos del proyecto (las fuentes). Busca: datos "
            "que no estén en las fuentes (inventados), cifras o fechas que no coincidan, contradicciones, y partes del pedido "
            f"que quedaron sin responder.\nPedido: «{st['pedido']}»\n\nFUENTES:\n{src}\n\nINFORME:\n{report_text(rep)[:9000]}\n\n"
            'Responde SOLO con JSON: {"veredicto": "bien" | "revisar", "problemas": [{"parte": "número o nombre de la sección", '
            '"detalle": "qué está mal y qué dicen las fuentes"}]} (máximo 6 problemas; lista vacía si todo está bien).')


def review_validate(d):
    if not isinstance(d, dict):
        return {"veredicto": "sin revisar", "problemas": []}
    probs = [{"parte": str(p.get("parte") or "")[:60], "detalle": str(p.get("detalle") or "").strip()[:500]}
             for p in (d.get("problemas") or [])[:6] if isinstance(p, dict) and str(p.get("detalle") or "").strip()]
    v = str(d.get("veredicto") or "").strip().lower()
    return {"veredicto": "revisar" if probs or v == "revisar" else "bien", "problemas": probs}


def review_spoken(rev):
    if not rev or rev["veredicto"] == "sin revisar":
        return ""
    if rev["veredicto"] == "bien":
        return "El revisor no encontró problemas."
    n = len(rev["problemas"])
    return f"El revisor marcó {n} cosa{'s' if n != 1 else ''} por revisar; están al final del informe."


_EDIT = re.compile(r"\b(?:cambia|corrige|rehaz|mejora|ajusta|acorta|alarga|amplia|reescribe|resume)\s+(?:la\s+|el\s+|las\s+)?"
                   r"(?:parte|seccion|apartado)?\s*(\d{1,2}|uno|dos|tres|cuatro|cinco|seis|siete|ocho|primera|segunda|tercera|cuarta|"
                   r"quinta|sexta|septima|octava|conclusiones|resumen)\s+del\s+informe\b(?:\s*[:,;]?\s*(.*))?$")


def parse_edit(t):
    """«cambia la parte 2 del informe: hazla más corta» → (2, "hazla más corta"); «conclusiones» y «resumen» por nombre."""
    m = _EDIT.search(t)
    if not m:
        return None
    w, how = m.group(1), (m.group(2) or "").strip()
    verb = re.match(r"\w+", t[m.start():]).group(0)
    if not how:
        how = {"acorta": "hazla más corta", "alarga": "hazla más completa", "amplia": "hazla más completa",
               "resume": "resúmela"}.get(verb, "mejórala: más clara y mejor escrita")
    part = w if w in ("conclusiones", "resumen") else (int(w) if w.isdigit() else _NUM.get(w, 0))
    return part, how


def edit_prompt(rep, part, how):
    if part == "resumen":
        cur, name = rep["resumen"], "el resumen"
    elif part == "conclusiones":
        cur, name = rep["conclusiones"], "las conclusiones"
    else:
        cur, name = rep["secciones"][part - 1]["texto"], f"la parte {part} («{rep['secciones'][part - 1]['titulo']}»)"
    return (f"Este es {name} de un informe. Reescríbela según lo que pide la persona: «{how}». No inventes datos nuevos; "
            "mantén lo que dice el resto del informe. Responde SOLO con el texto nuevo, sin títulos ni comentarios.\n\n"
            f"Texto actual:\n{cur}\n\nResto del informe (para contexto):\n{report_text(rep)[:5000]}")


def apply_edit(rep, part, new_text):
    t = str(new_text or "").strip()
    if not t:
        raise ValueError("vino vacío")
    if part == "resumen":
        rep["resumen"] = t
    elif part == "conclusiones":
        rep["conclusiones"] = t
    else:
        rep["secciones"][part - 1]["texto"] = t
    rep["revision"] = None                                    # lo cambiado ya no está revisado
    return rep
