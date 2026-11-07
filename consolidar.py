"""Memoria que se ordena sola (12.1). Lógica pura, sin Jarvis.

Cada noche Jarvis repasa lo que le dijiste en el día y saca los datos duraderos sobre ti (tus cursos, tus preferencias,
lo que te funciona) que el reconocimiento por frases fijas de perfil.py no atrapó. Los resúmenes de la IA pueden
inventar o torcer las cosas, así que cada dato nuevo debe traer la CITA TEXTUAL de lo que tú dijiste, y solo se guarda
si esa cita aparece de verdad en la conversación. Así cada dato sabe de dónde salió y se puede corregir.
"""
import re
import unicodedata


def norm(text):
    t = unicodedata.normalize("NFD", str(text or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", t)).strip()


def user_lines(entries, limit=160):
    """Lo que dijo el usuario (no Jarvis), sin órdenes cortas de control."""
    out = []
    for e in entries:
        if e.get("r") != "u":
            continue
        x = str(e.get("x", "")).strip()
        if len(x.split()) >= 4:
            out.append(x)
    return out[-limit:]


def prompt(lines, known):
    conv = "\n".join(f"- {l}" for l in lines)
    ya = "\n".join(f"- {k}" for k in known[:60]) or "(nada)"
    return f"""Estas son frases que un docente le dijo hoy a su asistente:
{conv}

Ya sé esto de él:
{ya}

Saca SOLO datos duraderos y útiles sobre él o su trabajo que aún no estén en la lista: cursos y asignaturas, su colegio, \
preferencias de cómo quiere el material o las respuestas, horarios fijos, personas importantes, cosas que le funcionan o no \
en clase. NO incluyas tareas de hoy, órdenes puntuales ni datos de estudiantes. Si un dato nuevo contradice uno que ya sé, \
inclúyelo y pon en "reemplaza" el dato viejo tal cual aparece en la lista.
Responde SOLO un JSON: {{"datos": [{{"dato": "en primera persona, corto: Prefiero los talleres con 10 ejercicios", \
"cita": "las palabras EXACTAS del docente de donde sale", "reemplaza": ""}}]}}
Máximo 6 datos. Si no hay nada nuevo, {{"datos": []}}."""


def clean(d, lines, known):
    """Solo los datos con cita verificable, nuevos y cortos. → [{"dato", "cita", "reemplaza"}]."""
    if not isinstance(d, dict):
        return []
    said = [norm(l) for l in lines]
    known_n = {norm(k): k for k in known}
    out = []
    for it in (d.get("datos") or [])[:6]:
        if not isinstance(it, dict):
            continue
        dato = re.sub(r"\s+", " ", str(it.get("dato") or "")).strip().strip(" .")[:200]
        cita = norm(it.get("cita"))
        if not dato or len(cita.split()) < 3:
            continue
        if not any(cita in s for s in said):                 # la cita no está en lo que dijo: puede ser inventado
            continue
        if norm(dato) in known_n or any(_overlap(norm(dato), k) > 0.8 for k in known_n):
            continue
        rep = str(it.get("reemplaza") or "").strip()
        rep = known_n.get(norm(rep), "") if rep else ""
        out.append({"dato": dato, "cita": str(it.get("cita")).strip()[:200], "reemplaza": rep})
    return out


def _overlap(a, b):
    wa, wb = set(w for w in a.split() if len(w) > 3), set(w for w in b.split() if len(w) > 3)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))
