"""10.2: el acumulado del año como en Zeti (VF) y lo que le falta a cada estudiante para aprobar (VRA), con avisos a tiempo.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import re

import aula
import periodos
import seguimiento
import zeti
from nucleo import J


def pweights():
    return zeti.parse_period_weights(J.settings["zeti_period_weights"])


def current_val(curso, est):
    since = J.settings["zeti_since"] or ""
    ns = [n for n in seguimiento.data.get(curso, {}).get(est, []) if n.get("fecha", "") >= since]
    return zeti.valoracion(ns, zeti.WEIGHTS)["val"]


def year_status(curso, est):
    """{"periodo", "previos", "faltan_previos", "actual", "vf", "vf_proy", "vra", "pierde", "aprobo"}."""
    pw = pweights()
    cur = min(max(1, int(J.settings["period_current"])), len(pw))
    prev = periodos.vals(curso, est, cur)
    missing = [i + 1 for i, v in enumerate(prev) if v is None]
    vf = zeti.final([v for v in prev], pw) if not missing else None
    act = current_val(curso, est)
    out = {"periodo": cur, "previos": prev, "faltan_previos": missing, "actual": act, "vf": vf, "vf_proy": None, "vra": None,
           "pierde": False, "aprobo": False}
    if vf is None:
        return out
    out["vra"] = zeti.vra(vf, cur - 1, pw)
    out["aprobo"] = out["vra"] is None
    if act is not None:
        out["vf_proy"] = zeti.rhu(vf + act * pw[cur - 1] / 100, 1)
    last = cur == len(pw)
    if out["vra"] is not None:
        # pierde: en el último periodo, lo que lleva no alcanza; antes, lo que le falta ya es casi imposible (> 4,5)
        out["pierde"] = (last and (act is None or act < out["vra"])) or out["vra"] > 4.5
    return out


def course_year(curso):
    names = sorted(set(aula.students(curso)) | set(seguimiento.data.get(curso, {})) | set(periodos.data.get(curso, {})))
    return {n: J.year_status(curso, n) for n in names}


def year_map(curso):
    """{estudiante: (VF proyectado o cerrado, VRA)} para la planilla de Zeti, o None si no hay periodos anteriores."""
    if int(J.settings["period_current"]) <= 1 and not periodos.data.get(curso):
        return None
    out = {}
    for n, s in J.course_year(curso).items():
        if s["vf"] is not None:
            out[n] = (s["vf"], s["vra"])
    return out or None


def _yf(x):
    return str(x).replace(".", ",")


def spoken_status(curso, est, s):
    if s["faltan_previos"]:
        return (f"De {est} no tengo la valoración del periodo {', '.join(map(str, s['faltan_previos']))}. Pega la tabla de Zeti de ese "
                "periodo en Ajustes › Memoria › Periodos anteriores y te digo cuánto necesita.")
    if s["aprobo"]:
        return f"{est} ya aprobó el año: lleva {_yf(s['vf'])} acumulado. 🎉"
    t = f"{est} lleva {_yf(s['vf'])} acumulado y necesita {_yf(s['vra'])} en promedio en lo que queda del año para llegar a 3,0"
    if s["actual"] is not None:
        t += f"; en este periodo va en {_yf(s['actual'])}" + (", así que por ahora no le alcanza" if s["actual"] < s["vra"] else ", le alcanza si sigue así")
    return t + "."


_NEED_RE = re.compile(r"\b(?:cuanto|que nota)\s+(?:necesita|le falta a|le falta|requiere|debe sacar)\s+(?:a\s+)?(.+?)(?:\s+para\s+(?:pasar|aprobar|ganar)(?: el ano)?)?$")
_LOSE_RE = re.compile(r"\b(?:quien|quienes)\s+(?:puede|pueden|va|van|esta|estan)\s+(?:a\s+)?(?:perder|perdiendo|reprobando|reprobar)\s+(?:el\s+)?ano\b"
                      r"(?:\s+en\s+(.+))?|\bquien(?:es)? (?:ya )?(?:gano|ganaron|aprobo|aprobaron) el ano\b(?:\s+en\s+(.+))?")
_PER_RE = re.compile(r"\b(?:estamos en|empezo|empieza|arranco|inicio)\s+(?:el\s+)?(primer|segundo|tercer|cuarto|1|2|3|4)(?:o|er)?\s+periodo\b|"
                     r"\b(?:estamos en el|ya es el)\s+periodo\s+(\d)\b")
_ORD = {"primer": 1, "segundo": 2, "tercer": 3, "cuarto": 4}


def year_voice(text, t):
    m = _PER_RE.search(t)
    if m:
        w = m.group(1) or m.group(2)
        p = _ORD.get(w) or int(w)
        if p > len(pweights()):
            J.reply(f"Tu año tiene {len(pweights())} periodos (Ajustes › Memoria).", "ACUMULADO")
            return True
        J.settings["period_current"] = p
        try:
            J.save_settings_file()
        except OSError:
            pass
        J.reply(f"Anotado: estamos en el periodo {p}. Para el acumulado necesito la valoración de los periodos anteriores: si no los "
                "cerraste con Jarvis, pega la tabla de Zeti de cada uno en Ajustes › Memoria › Periodos anteriores.", "ACUMULADO")
        return True
    m = _LOSE_RE.search(t)
    if m:
        spoken = (m.group(1) or m.group(2) or "").strip()
        if not spoken and not ("gan" in t or "aprob" in t):  # 10.3: sin curso, todos (de sexto a undécimo)
            parts = []
            for c in sorted(set(aula.data.get("cursos", {})) | set(periodos.data), key=aula.course_sort_key):
                lose = [n for n, s in J.course_year(c).items() if s["pierde"]]
                if lose:
                    parts.append(f"{c}: {len(lose)} ({', '.join(lose[:3])}{'…' if len(lose) > 3 else ''})")
            if not periodos.data:
                J.reply("Aún no tengo las valoraciones de los periodos anteriores. Pega la tabla de Zeti de cada curso y periodo en "
                        "Ajustes › Memoria › Periodos anteriores.", "ACUMULADO")
            else:
                J.reply(("Pueden perder el año: " + "; ".join(parts) + ". Pregúntame por un curso para ver cuánto necesita cada uno.")
                        if parts else "En ninguno de tus cursos hay estudiantes en peligro de perder el año. 👌", "ACUMULADO")
            return True
        course = J._resolve_course(spoken)
        if not course:
            J.reply("¿De qué curso? Por ejemplo: «¿quiénes pueden perder el año en 7A?».", "ACUMULADO")
            return True
        ks = [course] if course in J.keys_of(course) or len(J.keys_of(course)) == 1 else J.keys_of(course)   # 10.4: cada asignatura
        J.reply(" ".join(J._year_report(k, t) for k in ks), "ACUMULADO")
        return True
    m = _NEED_RE.search(t)
    if m:
        course, name = J._student_or_ask(m.group(1), "ACUMULADO")
        if name:
            J.reply(J.spoken_status(course, name, J.year_status(course, name)), "ACUMULADO")
        return True
    return False


def _year_report(course, t=""):
    """El reporte de un curso (o curso · asignatura): quién puede perder el año y quién está en la cuerda floja."""
    st = J.course_year(course)
    if all(s["vf"] is None for s in st.values()):
        return (f"Aún no tengo las valoraciones de los periodos anteriores de {course}. Pega la tabla de Zeti de cada periodo en "
                "Ajustes › Memoria › Periodos anteriores.")
    if "gan" in t or "aprob" in t:
        ok = [n for n, s in st.items() if s["aprobo"]]
        return (f"En {course} ya aprobaron el año {len(ok)}: " + ", ".join(ok[:12]) + ".") if ok else f"En {course} nadie ha asegurado el año todavía."
    lose = sorted(((n, s) for n, s in st.items() if s["pierde"]), key=lambda x: -(x[1]["vra"] or 0))
    watch = [(n, s) for n, s in st.items() if not s["pierde"] and s["vra"] is not None and s["vra"] >= 3.5]
    if not lose and not watch:
        return f"En {course} nadie está en peligro de perder el año. 👌"
    txt = ""
    if lose:
        txt += f"En {course} pueden perder el año {len(lose)}: " + "; ".join(
            f"{n} (necesita {_yf(s['vra'])}" + (f", va en {_yf(s['actual'])})" if s["actual"] is not None else ")") for n, s in lose[:8]) + ". "
    if watch:
        txt += "Para estar pendiente: " + "; ".join(f"{n} (necesita {_yf(s['vra'])})" for n, s in watch[:6]) + "."
    return txt.strip() + " Si quieres, «haz los planes de recuperación de " + course + "»."


def year_attention():
    """Para «¿qué necesita mi atención?»: cursos con estudiantes que pueden perder el año."""
    out = []
    for c in sorted(set(aula.data.get("cursos", {})) | set(periodos.data), key=aula.course_sort_key)[:24]:
        n = sum(1 for s in J.course_year(c).values() if s["pierde"])
        if n:
            out.append({"k": f"pa:{c}:{n}", "p": 2, "t": f"{n} pueden perder el año en {c}", "cmd": f"¿quiénes pueden perder el año en {c}?"})
    return out


def save_period_vals():
    """Al cerrar el periodo: guarda la Val de cada estudiante y pasa al siguiente periodo. Devuelve cuántas guardó."""
    cur = int(J.settings["period_current"])
    n = 0
    for c in sorted(set(aula.data.get("cursos", {})) | set(seguimiento.data), key=aula.course_sort_key)[:24]:
        names = set(aula.students(c)) | set(seguimiento.data.get(c, {}))
        for e in names:
            v = J.current_val(c, e)
            if v is not None:
                periodos.set_val(c, e, cur, v)
                n += 1
    if cur < len(pweights()):
        J.settings["period_current"] = cur + 1
        try:
            J.save_settings_file()
        except OSError:
            pass
    return n


def paste_periods(curso, periodo, text, apply=True):
    """La tabla de Zeti de un periodo pegada → guarda la Val de cada estudiante. → {"ok", "n", "sin", "creado", "msg"}."""
    rows = periodos.parse_paste(text)
    if not rows:
        return {"ok": False, "msg": "No encontré filas con nombre y valoración. Copia la tabla completa de Zeti (desde el primer estudiante) y pégala."}
    curso = J._resolve_course(curso) or str(curso).strip().upper()
    if not curso:
        return {"ok": False, "msg": "Escoge el curso."}
    names = aula.students(curso)
    creado = False
    if not names and apply:                            # sin lista en Jarvis: se crea con la de Zeti, en su orden
        aula.save_course(curso, "\n".join(r["nombre"] for r in rows))
        names, creado = aula.data["cursos"][curso], True
    hits, sin = [], []
    for r in rows:
        name = r["nombre"] if r["nombre"] in names else (aula.find_student(r["nombre"], names)[0] if names else r["nombre"])
        if not name or r["val"] is None:
            sin.append(r["nombre"])
            continue
        hits.append((name, r["val"]))
    if apply:
        for name, v in hits:
            periodos.set_val(curso, name, periodo, v)
    msg = (f"{'Guardé' if apply else 'Encontré'} la valoración del periodo {periodo} de {len(hits)} estudiante{'s' if len(hits) != 1 else ''} de {curso}"
           + (" (creé la lista del curso con la de Zeti)" if creado else "") + (f". Sin emparejar: {', '.join(sin[:6])}" if sin else "") + ".")
    if not hits and names:
        msg += f" Ningún nombre coincide con tu lista de {curso}: revisa que sea el curso correcto, o reemplaza la lista por la de Zeti en Ajustes › Memoria."
    return {"ok": bool(hits) or not apply, "n": len(hits), "sin": sin, "creado": creado, "msg": msg, "curso": curso}


@J.socketio.on("periods_paste")
def handle_periods_paste(data=None):
    d = data or {}
    try:
        p = int(d.get("periodo") or 0)
    except (TypeError, ValueError):
        p = 0
    if not 1 <= p <= len(pweights()):
        return {"ok": False, "msg": "Escoge el periodo."}
    return J.paste_periods(str(d.get("curso") or ""), p, str(d.get("text") or "")[:400000], apply=not d.get("preview"))


@J.socketio.on("periods_info")
def handle_periods_info(data=None):
    return {"cursos": sorted(set(aula.data.get("cursos", {})) | set(seguimiento.data), key=aula.course_sort_key)[:24], "periodos": len(pweights()),
            "actual": int(J.settings["period_current"]),
            "guardados": {c: sorted({p for e in v.values() for p in e}) for c, v in periodos.data.items()}}


def year_start():
    periodos.configure(J.CONFIG_DIR)


__all__ = ['_year_report', '_LOSE_RE', '_NEED_RE', '_ORD', '_PER_RE', 'course_year', 'current_val', 'handle_periods_info', 'handle_periods_paste',
           'paste_periods', 'periodos', 'pweights', 'save_period_vals', 'spoken_status', 'year_attention', 'year_map', 'year_start',
           'year_status', 'year_voice']
