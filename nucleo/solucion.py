"""11.3: solucionario paso a paso verificado con SymPy, y laboratorio interactivo de matemáticas para el proyector.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import re
import urllib.parse

import aula
import verificar
from nucleo import J

last_material = {"m": None, "kind": "", "curso": ""}      # el último material hecho (para «haz el solucionario del taller»)


# ============================================================================ SOLUCIONARIO VERIFICADO
def solve_verified(problemas, titulo="Problemas", curso=""):
    """Resuelve con la IA, verifica con SymPy y corrige lo que esté mal. → (soluciones, ruta del Word o "")."""
    g = aula.grade_of(curso) if curso else None
    subj = J._subject(curso) if curso else "Matemáticas"
    raw = J.ai_chat([{"role": "user", "content": verificar.prompt(problemas, f"{g}°" if g else "", subj) + J.lessons_ctx()}],
                    json_mode=True, max_tokens=9000)
    sols = verificar.clean(J._extract_json(raw), len(problemas))
    for s in sols:
        c = verificar.check(s["verificacion"])
        s["check"] = c
        if c["ok"] is False and c["correcto"]:
            try:
                raw = J.ai_chat([{"role": "user", "content": verificar.fix_prompt(s["problema"], s["pasos"], c["correcto"])}], json_mode=True,
                                max_tokens=2000)
                d = J._extract_json(raw)
                if d.get("pasos"):
                    s["pasos"] = [str(p)[:500] for p in d["pasos"]][:15]
            except Exception:
                s["pasos"] = s["pasos"] + [f"(Corrección: el resultado correcto es {c['correcto']}.)"]
            s["respuesta"] = c["correcto"]
            s["corregido"] = True
    path = ""
    if J.Document is not None and sols:
        path = verificar.docx(titulo, sols, J.settings["output_dir"], J.Document, curso.replace(" · ", " – "), J.settings["aula_docente"])
        J.generated_files.add(path)
    return sols, path


def _problems_from_last(t):
    """Los problemas del último taller o quiz que hiciste."""
    if re.search(r"\bquiz|evaluacion\b", t) and J.last_quiz.get("m"):
        q = J.last_quiz["m"]
        return [p["enunciado"] + " Opciones: " + "; ".join(p["opciones"]) for p in q.get("preguntas", [])], q.get("titulo", "Quiz"), ""
    m = last_material.get("m")
    if m and m.get("ejercicios"):
        return [e["enunciado"] for e in m["ejercicios"]], m.get("titulo", "Taller"), last_material.get("curso", "")
    if J.last_quiz.get("m"):
        q = J.last_quiz["m"]
        return [p["enunciado"] + " Opciones: " + "; ".join(p["opciones"]) for p in q.get("preguntas", [])], q.get("titulo", "Quiz"), ""
    return [], "", ""


_SV_LIST = re.compile(r"^(?:jarvis\s+)?(?:resuelve|resuelveme|solucioname|soluciona)\s+(?:paso a paso|con pasos|verificado)\s*:?\s*(.+)$")
_SV_LAST = re.compile(r"\b(?:haz|hazme|prepara|preparame|genera|dame)\s+(?:el\s+)?solucionario\b|\bresuelve paso a paso (?:el|la|los)\s+"
                      r"(?:ultimo\s+|ultima\s+)?(?:taller|quiz|evaluacion|ejercicios)\b")


def solver_voice(text, t):
    m = _SV_LIST.match(t)
    probs, titulo, curso = [], "", ""
    if m and not _SV_LAST.search(t):
        orig = re.split(r":", text, maxsplit=1)
        probs = verificar.split_problems(orig[1] if len(orig) > 1 else m.group(1))
        titulo = "Problemas"
    elif _SV_LAST.search(t):
        probs, titulo, curso = _problems_from_last(t)
        if not probs:
            J.reply("No tengo un taller o quiz reciente. Dime los problemas: «resuelve paso a paso: 2x + 3 = 7; x² − 5x + 6 = 0».", "SOLUCIONARIO")
            return True
    else:
        return False
    if not probs:
        return False
    if J.state.get("ai") != "ok":
        J.reply("Para el solucionario paso a paso necesito la IA conectada.", "SOLUCIONARIO")
        return True
    curso = curso or aula.data.get("activo", "")
    J.reply(f"Resuelvo paso a paso {len(probs)} problema{'s' if len(probs) != 1 else ''} y verifico cada resultado con SymPy…", "SOLUCIONARIO")

    def work():
        try:
            sols, path = J.solve_verified(probs, titulo, curso)
        except Exception as e:
            J.notify(f"No pude hacer el solucionario: {getattr(e, 'why', e)}", "SOLUCIONARIO")
            return
        ok = sum(1 for s in sols if s["check"]["ok"])
        fixed = sum(1 for s in sols if s.get("corregido"))
        if path:
            J._open_doc(path)
        J.notify(f"Listo el solucionario: {len(sols)} problemas, {ok} verificados con SymPy" +
                 (f" y {fixed} corregido{'s' if fixed != 1 else ''} (la IA se había equivocado; ya quedó bien)" if fixed else "") +
                 (". Está en Documentos, Jarvis, Solucionarios." if path else "."), "SOLUCIONARIO")
    if getattr(J._tl, "capture", None) is not None:
        work()
    else:
        J.start_job("Resolviendo paso a paso", work, "solucionario")
    return True


# ============================================================================ LABORATORIO INTERACTIVO
LABS = {"parabola": "La parábola y = ax² + bx + c", "recta": "La recta y = mx + b", "circulo": "El círculo unitario (seno, coseno, tangente)",
        "seno": "La función seno y = A·sen(Bx + C) + D", "exponencial": "Crecimiento exponencial y = a·bˣ", "pitagoras": "El teorema de Pitágoras",
        "fracciones": "Fracciones con la pizza", "dados": "Probabilidad con dados y monedas", "areas": "Área y perímetro"}
_LAB_ALIAS = [("parabola", r"parabola|cuadratica|segundo grado"), ("recta", r"recta|lineal|pendiente"), ("circulo", r"circulo unitario|circulo|unitario"),
              ("seno", r"seno|coseno|trigonometric|ondas?"), ("exponencial", r"exponencial|crecimiento|interes compuesto"),
              ("pitagoras", r"pitagoras|triangulo rectangulo|hipotenusa"), ("fracciones", r"fracciones|pizza"),
              ("dados", r"dados?|monedas?|probabilidad|azar"), ("areas", r"areas?|perimetro")]


@J.app.route("/lab")
@J.app.route("/lab/<name>")
def lab_page(name=""):
    from flask import render_template
    return render_template("lab.html", lab=name if name in LABS else "", labs=LABS, asset_v=getattr(J, "ASSET_V", ""))


_LAB_RE = re.compile(r"\b(?:abre|abreme|muestra|muestrame|pon|ponme|lanza|activa)\s+(?:el\s+)?(?:laboratorio|simulador|lab)\b(?:\s+(?:de|del|sobre)\s+(?:la\s+|el\s+|los\s+)?(.+))?$")
_LAB_LIST = re.compile(r"\bque (?:laboratorios|simuladores) (?:hay|tienes)\b")


def lab_voice(text, t):
    if _LAB_LIST.search(t):
        J.reply("Laboratorios para el proyector: " + "; ".join(LABS.values()) + ". Di «abre el laboratorio de la parábola».", "LABORATORIO")
        return True
    m = _LAB_RE.search(t)
    if not m:
        return False
    what = m.group(1) or ""
    name = next((k for k, rx in _LAB_ALIAS if re.search(rf"\b(?:{rx})", what)), "")
    try:
        import webbrowser
        webbrowser.open(J.URL + "/lab/" + urllib.parse.quote(name))
    except Exception:
        pass
    J.reply((f"Abrí el laboratorio: {LABS[name]}. Mueve los deslizadores y pregúntales a los estudiantes qué creen que pasará antes de moverlos."
             if name else "Abrí el laboratorio de matemáticas: escoge uno (parábola, recta, círculo unitario, seno, exponencial, Pitágoras, "
                          "fracciones, dados o áreas)."), "LABORATORIO")
    return True


__all__ = ['LABS', '_LAB_ALIAS', '_LAB_LIST', '_LAB_RE', '_SV_LAST', '_SV_LIST', '_problems_from_last', 'lab_page', 'lab_voice', 'last_material',
           'solve_verified', 'solver_voice', 'verificar']
