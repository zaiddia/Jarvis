"""Kit para colegas (10.0): comparte con otro docente lo que le enseñaste a Jarvis, sin datos de estudiantes.

Un kit es un .json con: tus rutinas (sin horario automático), tus habilidades, tus lecciones, las actividades que
funcionaron, tus planes de clase y las preguntas de tu banco. Nunca lleva notas, listas, asistencia, observador
ni nada de tus estudiantes, ni ajustes ni claves. Al importarlo, todo se suma a lo que el colega ya tiene.
"""
import datetime
import json
import os
import re

KIND = "kit-jarvis"
MAX_BYTES = 3_000_000
PARTS = {"rutinas": "rutinas", "habilidades": "habilidades", "lecciones": "lecciones", "actividades": "actividades que funcionaron",
         "planes": "planes de clase", "banco": "preguntas del banco"}
# Lo que jamás debe viajar en un kit (si aparece, el archivo no es un kit limpio)
_FORBIDDEN = re.compile(r'"(?:asistencia|notas_estudiantes|observador|cursos|estudiantes?|password|contrasena|api_key|token|secret)"\s*:',
                        re.I)


def _s(x, n):
    return str(x or "").strip()[:n]


def build(routines, skills, lessons, activities, plans, bank, author="", defaults=(), min_result=70):
    def_names = {_s(r.get("nombre"), 60).lower() for r in defaults}
    return {
        "tipo": KIND, "version": 1, "autor": _s(author, 60), "fecha": datetime.date.today().isoformat(),
        "rutinas": [{"nombre": _s(r["nombre"], 60), "frases": list(r.get("frases") or [])[:10], "pasos": list(r.get("pasos") or [])[:40]}
                    for r in routines if _s(r.get("nombre"), 60).lower() not in def_names],
        "habilidades": [{k: v for k, v in s.items() if k != "archivo"} for s in skills],
        "lecciones": [_s(x["texto"], 300) for x in lessons],
        "actividades": [{"tema": _s(a.get("tema"), 120), "actividad": _s(a.get("actividad"), 600), "resultado": a.get("resultado")}
                        for a in activities if a.get("resultado") is not None and a["resultado"] >= min_result],
        "planes": [{"tema": _s(p.get("tema"), 120), "titulo": _s(p.get("titulo"), 160), "objetivo": _s(p.get("objetivo"), 400),
                    "momentos": [{"nombre": _s(m.get("nombre"), 60), "duracion": _s(m.get("duracion"), 30),
                                  "actividades": _s(m.get("actividades"), 1500)} for m in (p.get("momentos") or [])[:8] if isinstance(m, dict)]}
                   for p in plans],
        "banco": [{"enunciado": _s(q.get("enunciado"), 600), "opciones": [_s(o, 200) for o in (q.get("opciones") or [])[:4]],
                   "respuesta": q.get("respuesta"), "explicacion": _s(q.get("explicacion"), 400), "tema": _s(q.get("tema"), 120),
                   "grado": _s(q.get("grado"), 30)} for q in bank],
    }


def counts(k):
    return {p: len(k.get(p) or []) for p in PARTS}


_ONE = {"rutinas": "rutina", "habilidades": "habilidad", "lecciones": "lección", "actividades": "actividad que funcionó",
        "planes": "plan de clase", "banco": "pregunta del banco"}


def label(part, n):
    return f"{n} {PARTS[part] if n != 1 else _ONE[part]}"


def summary(k):
    parts = [label(p, n) for p, n in counts(k).items() if n]
    who = f" de {k['autor']}" if k.get("autor") else ""
    return (f"Kit{who}: " + ", ".join(parts) + ".") if parts else f"El kit{who} está vacío."


def save(k, out_dir):
    folder = os.path.join(out_dir, "Kit para colegas")
    os.makedirs(folder, exist_ok=True)
    name = re.sub(r'[\\/:*?"<>|]+', " ", k.get("autor") or "Jarvis").strip() or "Jarvis"
    path = os.path.join(folder, f"Kit de {name} - {k['fecha']}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(k, f, ensure_ascii=False, indent=1)
    return path


def parse(text):
    """Lee y limpia un kit. Lanza ValueError con un mensaje claro."""
    if len(str(text).encode("utf-8")) > MAX_BYTES:
        raise ValueError("el archivo es demasiado grande para ser un kit")
    if _FORBIDDEN.search(str(text)):
        raise ValueError("el archivo trae datos que un kit nunca lleva (estudiantes o claves); no lo importo")
    try:
        d = json.loads(text)
    except ValueError:
        raise ValueError("el archivo no es un JSON válido")
    if not isinstance(d, dict) or d.get("tipo") != KIND:
        raise ValueError("el archivo no es un kit de Jarvis")
    out = {"tipo": KIND, "autor": _s(d.get("autor"), 60), "fecha": _s(d.get("fecha"), 10)}
    for p in PARTS:
        v = d.get(p) or []
        out[p] = [x for x in v if isinstance(x, (dict, str))][:500] if isinstance(v, list) else []
    out["lecciones"] = [_s(x, 300) for x in out["lecciones"] if isinstance(x, str) and len(x.split()) >= 3]
    out["rutinas"] = [r for r in out["rutinas"] if isinstance(r, dict) and _s(r.get("nombre"), 60) and r.get("pasos")]
    out["actividades"] = [a for a in out["actividades"] if isinstance(a, dict) and _s(a.get("actividad"), 600)]
    out["planes"] = [p for p in out["planes"] if isinstance(p, dict) and (p.get("tema") or p.get("titulo"))]
    out["banco"] = [q for q in out["banco"] if isinstance(q, dict) and q.get("enunciado") and len(q.get("opciones") or []) >= 2]
    out["habilidades"] = [h for h in out["habilidades"] if isinstance(h, dict)]
    return out
