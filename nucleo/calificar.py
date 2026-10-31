"""10.5: calificar con el celular. Hojas de respuesta impresas (una por estudiante) que se califican con una foto: notas
a su asignatura, análisis de la evaluación (qué falló el curso y por qué) y refuerzo a la medida de cada estudiante.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import io
import os
import re
import secrets
import tempfile

import aula
import banco
import examenes
import omr
import seguimiento
from nucleo import J

sess = {"code": None, "token": ""}


# ============================================================================ CREAR LA EVALUACIÓN Y LAS HOJAS
def exam_from_quiz(quiz, course, titulo=""):
    qs = [q for q in (quiz.get("preguntas") or []) if q.get("opciones")]
    clave = ["abcde".index(str(q.get("respuesta", "a"))[:1].lower()) if str(q.get("respuesta", "a"))[:1].lower() in "abcde" else 0 for q in qs]
    n_opt = max(2, min(5, max((len(q["opciones"]) for q in qs), default=4)))
    names = aula.students(course)
    return examenes.new(titulo or quiz.get("titulo") or "Evaluación", course, clave, n_opt,
                        [{"enunciado": q.get("enunciado", "")[:500], "opciones": list(q["opciones"])[:5], "competencia": q.get("competencia", ""),
                          "explicacion": q.get("explicacion", "")[:300]} for q in qs],
                        {i + 1: n for i, n in enumerate(names)}, quiz.get("tema", ""))


def make_sheets(ex):
    folder = os.path.join(J.settings["output_dir"], "Hojas de respuesta")
    safe = re.sub(r'[\\/:*?"<>|]+', " ", f"{ex['titulo']} {ex['curso']}").strip()
    path = os.path.join(folder, f"{safe} - {ex['code']}.pdf")
    studs = sorted(((int(k), v) for k, v in ex["estudiantes"].items()), key=lambda x: x[0])
    omr.sheets_pdf(path, ex["code"], studs, len(ex["clave"]), ex["n_opt"], ex["titulo"], ex["curso"].replace(" · ", " – "),
                   J.settings["aula_institucion"], extra_blank=3)
    J.generated_files.add(path)
    return path


_SH_RE = re.compile(r"\b(?:prepara|preparame|haz|hazme|imprime|imprimeme|genera|generame|crea|creame|dame|saca|sacame)\b.*"
                    r"\bhojas? (?:de )?(?:respuestas?|burbujas|para calificar)\b")
_COURSE_IN = re.compile(r"\b(?:de|del|para|en)\s+((?:grado\s+)?(?:\d{1,2}(?:\s?[a-z](?![a-z])|\s?-\s?\d)?|sexto|septimo|octavo|noveno|undecimo|decimo|"
                        r"onceavo|once)(?:\s+[a-z](?![a-z]))?)\b")


def sheets_voice(text, t):
    if not _SH_RE.search(t):
        return False
    cm = _COURSE_IN.search(t)
    course = J._resolve_course(cm.group(1) if cm else "")
    if not course:
        J.reply("¿Para qué curso? Por ejemplo: «prepara las hojas de respuesta del quiz para 7A».", "CALIFICAR")
        return True
    course = J.grade_key(course, t, ask=True, origin="CALIFICAR")
    if not course:
        return True
    km = re.search(r"\bclave\s+(?:es\s+)?:?\s*(.+)$", t)
    if km:                                             # evaluación externa (simulacro impreso, libro…): solo la clave
        clave = examenes.parse_key(km.group(1))
        if len(clave) < 2:
            J.reply("No entendí la clave. Dímela así: «la clave es a, c, b, d…» o «1a 2c 3b…».", "CALIFICAR")
            return True
        om = re.search(r"\b([2-5])\s+opciones\b", t)
        tm = re.search(r"\b(?:del|de la|para el|para la)\s+((?:simulacro|evaluacion|examen|prueba|quiz)[\w ]{0,40}?)(?:\s+(?:de|para)\s+\d|\s+clave|$)", t)
        n_opt = int(om.group(1)) if om else max(4, max(clave) + 1)
        ex = examenes.new((tm.group(1).strip().capitalize() if tm else "Evaluación"), course, clave, n_opt, [],
                          {i + 1: n for i, n in enumerate(aula.students(course))})
    else:
        quiz = J.last_quiz["m"]
        tq = re.search(r"\b(?:del|de)\s+(?:quiz|evaluacion|examen)\s+(?:de|sobre)\s+(.+?)(?:\s+(?:para|de|en)\s+(?:grado\s+)?\d|$)", t)
        if tq:
            quiz = banco.build_quiz(tq.group(1).strip(), 10) or quiz
        if not quiz or not quiz.get("preguntas"):
            J.reply("Primero prepárame el quiz («haz un quiz de 10 preguntas de fracciones para 7A») o dime la clave: «hojas de "
                    "respuesta de 20 preguntas para 11A, la clave es a, c, b, d…».", "CALIFICAR")
            return True
        ex = exam_from_quiz(quiz, course)
    path = make_sheets(ex)
    J._open_doc(path)
    n = len(ex["estudiantes"])
    J.reply(f"Listas las hojas de respuesta de «{ex['titulo']}» para {course}: {n} con nombre" + (" (en el orden de tu lista)" if n else "") +
            f" y 3 en blanco, {len(ex['clave'])} preguntas. Imprímelas; cuando las recojas, di «califica las hojas» y les tomas foto con el "
            "celular, o arrástralas al HUD.", "CALIFICAR")
    return True


# ============================================================================ CALIFICAR UNA FOTO
def _vision_read(img_bytes, n_q):
    """Si la hoja no se deja leer sola: la IA con visión lee el código y las burbujas."""
    cfg, err = J._vision_cfg()
    if not cfg:
        raise omr.ReadError(err)
    fd, path = tempfile.mkstemp(suffix=".jpg")
    with os.fdopen(fd, "wb") as f:
        f.write(img_bytes)
    prompt = (f"Es la foto de una hoja de respuestas de burbujas con {n_q} preguntas (opciones A, B, C, D, E). Arriba dice "
              "«Código NNNNN-NN». Para cada pregunta di qué letra está rellena (null si ninguna o si hay dos). Responde SOLO con JSON: "
              '{"codigo": "12345-07", "respuestas": ["A", null, "C", …]}')
    try:
        if cfg["kind"] == "ollama":
            r = J.ollama.Client(host=cfg["ollama_host"], timeout=240).chat(
                model=J.settings["vision_model"].strip() or "moondream", format="json",
                messages=[{"role": "user", "content": prompt, "images": [path]}])
            raw = r["message"]["content"]
        else:
            J._need_key(cfg)
            raw = J._with_fallback(cfg, lambda c: J._cloud_chat(c, [{"role": "user", "content": prompt}], json_mode=True, image_path=path,
                                                                max_tokens=1500))
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    d = J._extract_json(raw)
    m = re.match(r"\s*(\d{1,5})\s*-\s*(\d{1,3})", str(d.get("codigo", "")))
    if not m:
        raise omr.ReadError("no se ve el código de la hoja")
    ans = []
    for x in (d.get("respuestas") or [])[:n_q]:
        x = str(x or "").strip().upper()[:1]
        ans.append("ABCDE".index(x) if x and x in "ABCDE" else None)
    return {"code": int(m.group(1)), "student": int(m.group(2)), "answers": ans + [None] * (n_q - len(ans)), "ink": []}


def grade_photo(img_bytes):
    """Califica la foto de una hoja. → {"ok", "msg", "nombre", "nota", "aciertos", "total", "malas": [números]}."""
    ex = examenes.get(sess["code"]) if sess["code"] else examenes.latest(open_only=True)
    origen = "omr"
    try:
        r = omr.read_image(img_bytes, len(ex["clave"]) if ex else None, ex["n_opt"] if ex else None)
    except omr.ReadError as e:
        if J.state.get("ai") != "ok":
            return {"ok": False, "msg": f"No pude leer la hoja: {e}."}
        try:
            r, origen = _vision_read(img_bytes, len(ex["clave"]) if ex else omr.MAX_Q), "ia"
        except Exception:
            return {"ok": False, "msg": f"No pude leer la hoja: {e}."}
    except ImportError:
        return {"ok": False, "msg": "Falta OpenCV para leer las hojas (actualiza Jarvis o ejecuta instalar.bat)."}
    ex = examenes.get(r["code"])
    if not ex:
        return {"ok": False, "msg": f"Esta hoja es de una evaluación que no tengo (código {r['code']})."}
    if sess["code"] != ex["code"]:
        sess["code"] = ex["code"]
    n_q = len(ex["clave"])
    g = omr.grade(r["answers"][:n_q], ex["clave"])
    res = examenes.add_result(ex["code"], r["student"], r["answers"][:n_q], g, origen=origen)
    malas = [i + 1 for i, x in enumerate(g["detalle"]) if x is False]
    multi = [i + 1 for i, a in enumerate(r["answers"][:n_q]) if a == "multi"]
    out = {"ok": True, "nombre": res["nombre"], "nota": g["nota"], "aciertos": g["aciertos"], "total": g["total"], "malas": malas,
           "multi": multi, "n": len(ex["resultados"]), "titulo": ex["titulo"], "origen": origen,
           "msg": f"{res['nombre']}: {g['aciertos']} de {g['total']} → {str(g['nota']).replace('.', ',')}"}
    _emit()
    return out


def _emit():
    ex = examenes.get(sess["code"]) if sess["code"] else None
    if not ex:
        return
    try:
        J.socketio.emit("grading", {"open": not ex["cerrado"], "titulo": ex["titulo"], "curso": ex["curso"], "n": len(ex["resultados"]),
                                    "esperados": len(ex["estudiantes"]), "url": grading_url() if J.mobile.get("server") else "",
                                    "ultimos": [{"nombre": r["nombre"], "nota": r["nota"]} for r in
                                                sorted(ex["resultados"].values(), key=lambda r: r["t"])[-5:]]})
    except Exception:
        pass


def grading_url():
    return f"http://{J.lan_ip()}:{J.settings['mobile_port']}/h/{sess['token']}"


# ============================================================================ ANÁLISIS Y NOTAS
def analysis(ex):
    rs = list(ex["resultados"].values())
    items = omr.item_analysis(rs, ex["clave"], ex["n_opt"])
    notas = [r["nota"] for r in rs if r["nota"] is not None]
    prom = round(sum(notas) / len(notas), 1) if notas else None
    hard = sorted([it for it in items if it["acierto"] < 60], key=lambda it: it["acierto"])
    return {"n": len(rs), "promedio": prom, "bajos": sum(1 for x in notas if x < 3.0), "items": items, "dificiles": hard,
            "faltan": [v for k, v in ex["estudiantes"].items() if k not in ex["resultados"]]}


def spoken_analysis(ex, a):
    if not a["n"]:
        return f"Aún no he calificado ninguna hoja de «{ex['titulo']}»."
    t = (f"«{ex['titulo']}» ({ex['curso']}): {a['n']} hojas, promedio {str(a['promedio']).replace('.', ',')}, "
         f"{a['bajos']} por debajo de 3,0.")
    if a["dificiles"]:
        t += " Las más difíciles: " + "; ".join(
            f"la {it['q'] + 1} ({it['acierto']} % de acierto" + (f"; muchos marcaron {omr.LETTERS[it['distractor']]}" if it["distractor"] is not None
                                                                  and it["distractor_n"] >= max(2, a["n"] // 4) else "") + ")"
            for it in a["dificiles"][:4]) + "."
    else:
        t += " Ninguna pregunta quedó por debajo del 60 % de acierto. 👏"
    if a["faltan"]:
        t += f" Faltan {len(a['faltan'])} hojas" + (f" ({', '.join(a['faltan'][:4])}…)" if len(a["faltan"]) > 4 else f" ({', '.join(a['faltan'])})") + "."
    return t


def analysis_docx(ex, a):
    if J.Document is None:
        return ""
    doc = J.Document()
    doc.add_heading(f"Análisis: {ex['titulo']}", 0)
    doc.add_paragraph(f"{ex['curso']} · {ex['creado'][:10]} · {a['n']} hojas · promedio {a['promedio']} · {a['bajos']} por debajo de 3,0")
    doc.add_heading("Pregunta por pregunta", 1)
    tb = doc.add_table(rows=1, cols=5)
    tb.style = "Table Grid"
    for c, h in zip(tb.rows[0].cells, ("N.º", "% acierto", "Clave", "Errada más marcada", "Pregunta")):
        c.text = h
    for it in a["items"]:
        r = tb.add_row().cells
        q = ex["preguntas"][it["q"]] if it["q"] < len(ex["preguntas"]) else {}
        r[0].text = str(it["q"] + 1)
        r[1].text = f"{it['acierto']} %"
        r[2].text = omr.LETTERS[it["clave"]]
        r[3].text = (f"{omr.LETTERS[it['distractor']]} ({it['distractor_n']})" if it["distractor"] is not None else "—")
        r[4].text = q.get("enunciado", "")[:160]
    doc.add_heading("Estudiantes", 1)
    tb = doc.add_table(rows=1, cols=4)
    tb.style = "Table Grid"
    for c, h in zip(tb.rows[0].cells, ("Estudiante", "Aciertos", "Nota", "Preguntas erradas")):
        c.text = h
    for r in sorted(ex["resultados"].values(), key=lambda r: r["nombre"]):
        row = tb.add_row().cells
        row[0].text, row[1].text = r["nombre"], f"{r['aciertos']}/{r['total']}"
        row[2].text = str(r["nota"]).replace(".", ",")
        row[3].text = ", ".join(str(i + 1) for i, x in enumerate(r["detalle"]) if x is False) or "—"
    folder = os.path.join(J.settings["output_dir"], "Hojas de respuesta")
    os.makedirs(folder, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|]+', " ", f"Análisis {ex['titulo']} {ex['curso']}").strip()
    path = os.path.join(folder, f"{safe} - {datetime.date.today():%Y-%m-%d}.docx")
    doc.save(path)
    J.generated_files.add(path)
    return path


def record_grades(ex):
    n = 0
    for r in ex["resultados"].values():
        if r["nota"] is None or r["nombre"].startswith("Hoja sin nombre"):
            continue
        seguimiento.add(ex["curso"], r["nombre"], ex["titulo"], r["nota"], origen="hoja", dim="conocer")
        n += 1
    ex["anotado"] = True
    examenes.save()
    return n


def close_grading(say=True):
    ex = examenes.get(sess["code"]) if sess["code"] else examenes.latest(open_only=True)
    if not ex:
        J.reply("No hay ninguna evaluación calificándose.", "CALIFICAR")
        return None
    examenes.close(ex["code"])
    a = analysis(ex)
    try:
        J.saber_from_exam(ex)                          # 10.6: si es un simulacro Saber, al programa
    except Exception as e:
        J.note_error("SABER", e)
    path = analysis_docx(ex, a) if a["n"] else ""
    _emit()
    sess.update(code=None)
    if say:
        J.reply(spoken_analysis(ex, a) + (" Te dejé el análisis en Word." if path else ""), "CALIFICAR")
    named = [r for r in ex["resultados"].values() if not r["nombre"].startswith("Hoja sin nombre")]
    if named and not ex["anotado"]:
        J.request_approval("notas", f"Anotar {len(named)} notas de «{ex['titulo']}» ({ex['curso'].replace(' · ', ', ')})",
                           "; ".join(f"{r['nombre']}: {str(r['nota']).replace('.', ',')}" for r in named[:40]),
                           on_ok=lambda: J.reply(f"Anoté {record_grades(ex)} notas en Conocer. Para el refuerzo: «prepara el refuerzo».", "CALIFICAR"),
                           on_no=lambda: None, ttl=24 * 3600,
                           say=f"¿Anoto las {len(named)} notas en {ex['curso'].replace(' · ', ', ')}? Di «sí» o «no».")
    return a


# ============================================================================ REFUERZO PERSONALIZADO
def reinforcement_prompt(ex, a, grado=""):
    hard = a["dificiles"][:5]
    lines = []
    for it in hard:
        q = ex["preguntas"][it["q"]] if it["q"] < len(ex["preguntas"]) else {}
        ops = q.get("opciones") or []
        wrong = ops[it["distractor"]] if it["distractor"] is not None and it["distractor"] < len(ops) else ""
        lines.append(f"Pregunta {it['q'] + 1} ({it['acierto']} % de acierto): {q.get('enunciado', '(sin texto)')} | correcta: "
                     f"{ops[it['clave']] if it['clave'] < len(ops) else omr.LETTERS[it['clave']]}" + (f" | errada más marcada: {wrong}" if wrong else ""))
    return ("Eres un docente experto en Colombia. Analiza los resultados de esta evaluación" + (f" de grado {grado}" if grado else "") +
            f" («{ex['titulo']}», tema {ex.get('tema') or 'el de la evaluación'}). Preguntas donde más fallaron:\n" + "\n".join(lines) +
            "\nPara cada pregunta: el error de concepto más probable (por la opción errada), una explicación corta y clara para el "
            "estudiante y 4 ejercicios de práctica graduados con su respuesta. Además, una clase de refuerzo de 1 hora para todo el curso. "
            "Usa notación sencilla en texto plano, sin LaTeX. Responde SOLO con JSON: "
            '{"diagnostico": str, "clase": {"objetivo": str, "actividades": [str]}, '
            '"preguntas": [{"numero": int, "error": str, "explicacion": str, "ejercicios": [{"enunciado": str, "respuesta": str}]}]}')


def reinforcement(ex=None):
    ex = ex or examenes.latest()
    if not ex or not ex["resultados"]:
        J.reply("No tengo una evaluación calificada para preparar el refuerzo.", "CALIFICAR")
        return ""
    a = analysis(ex)
    if not a["dificiles"]:
        J.reply("En esa evaluación ninguna pregunta quedó por debajo del 60 %: no hace falta refuerzo general. 👏", "CALIFICAR")
        return ""
    if not ex["preguntas"]:
        J.reply("Esa evaluación no tiene los enunciados (solo la clave), así que no puedo armar el refuerzo pregunta por pregunta.", "CALIFICAR")
        return ""
    if J.state.get("ai") != "ok" or J.Document is None:
        J.reply("Para el refuerzo necesito la IA conectada y python-docx.", "CALIFICAR")
        return ""
    g = aula.grade_of(ex["curso"])
    raw = J.ai_chat([{"role": "user", "content": reinforcement_prompt(ex, a, f"{g}°" if g else "") + J.lessons_ctx()}], json_mode=True, max_tokens=6000)
    d = J._extract_json(raw)
    by_q = {}
    for p in d.get("preguntas") or []:
        try:
            by_q[int(p.get("numero")) - 1] = p
        except (TypeError, ValueError):
            continue
    doc = J.Document()
    doc.add_heading(f"Refuerzo: {ex['titulo']} ({ex['curso']})", 0)
    doc.add_paragraph(str(d.get("diagnostico", ""))[:1500])
    cl = d.get("clase") or {}
    doc.add_heading("Clase de refuerzo para todo el curso", 1)
    doc.add_paragraph("Objetivo: " + str(cl.get("objetivo", ""))[:400])
    for act in (cl.get("actividades") or [])[:10]:
        doc.add_paragraph(str(act)[:600], style="List Number")
    hard_idx = {it["q"] for it in a["dificiles"][:5]}
    for r in sorted(ex["resultados"].values(), key=lambda r: r["nombre"]):
        mine = [i for i, x in enumerate(r["detalle"]) if x is not True and i in hard_idx and i in by_q]
        if not mine:
            continue
        doc.add_page_break()
        doc.add_heading(f"Para: {r['nombre']}", 1)
        doc.add_paragraph(f"En «{ex['titulo']}» sacaste {str(r['nota']).replace('.', ',')}. Vamos a practicar lo que más te costó.")
        for i in mine:
            p = by_q[i]
            doc.add_heading(f"Pregunta {i + 1}", 2)
            doc.add_paragraph(str(p.get("explicacion", ""))[:1200])
            for j, e in enumerate((p.get("ejercicios") or [])[:4], 1):
                doc.add_paragraph(f"{j}. {str(e.get('enunciado', ''))[:500]}")
    doc.add_page_break()
    doc.add_heading("Respuestas (para el docente)", 1)
    for i in sorted(by_q):
        p = by_q[i]
        doc.add_paragraph(f"Pregunta {i + 1} — error probable: {str(p.get('error', ''))[:300]}")
        for j, e in enumerate((p.get("ejercicios") or [])[:4], 1):
            doc.add_paragraph(f"   {j}. {str(e.get('respuesta', ''))[:200]}")
    folder = os.path.join(J.settings["output_dir"], "Hojas de respuesta")
    os.makedirs(folder, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|]+', " ", f"Refuerzo {ex['titulo']} {ex['curso']}").strip()
    path = os.path.join(folder, f"{safe} - {datetime.date.today():%Y-%m-%d}.docx")
    doc.save(path)
    J.generated_files.add(path)
    J._open_doc(path)
    n = sum(1 for r in ex["resultados"].values() if any(x is not True and i in hard_idx for i, x in enumerate(r["detalle"])))
    J.notify(f"Listo el refuerzo de «{ex['titulo']}»: la clase para todo el curso y una guía personal para {n} estudiantes, con solo "
             "lo que cada uno falló (las respuestas van al final, para ti).", "CALIFICAR")
    return path


# ============================================================================ VOZ
_GR_START = re.compile(r"\b(?:califica|calificar|calificame|vamos a calificar|empieza a calificar|escanea|escanear|corrige|corregir)\s+"
                       r"(?:las\s+)?(?:hojas|evaluaciones|examenes)\b|\bcalificar con el celular\b")
_GR_END = re.compile(r"\b(?:termina|termine|terminamos|cierra|acabe|acabamos|finaliza)\s+(?:de\s+)?(?:calificar|la calificacion|las hojas)\b|"
                     r"\bya (?:califique|escanee|termine de calificar)\b")
_GR_REF = re.compile(r"\b(?:prepara|preparame|haz|hazme|genera|generame|arma)\s+(?:el\s+)?refuerzo\b")
_GR_ASK = re.compile(r"\bcomo (?:les fue|nos fue|les va|va la calificacion) (?:en|con) (?:la|el)\s+(?:evaluacion|quiz|examen|simulacro)\b|"
                     r"\banalisis de la evaluacion\b")
_GR_KEY = re.compile(r"^(?:la\s+)?clave (?:de la evaluacion |del quiz |del examen )?(?:es|era|queda)\s*:?\s*(.+)$")
_GR_NAME = re.compile(r"\bla hoja sin nombre\s+(\d{1,2})\s+es de\s+(.+)$")


def grading_voice(text, t):
    if _GR_START.search(t):
        ex = examenes.latest(open_only=True)
        if not ex:
            J.reply("No hay hojas de respuesta por calificar. Primero: «prepara las hojas de respuesta del quiz para 7A».", "CALIFICAR")
            return True
        sess.update(code=ex["code"], token=sess["token"] or secrets.token_urlsafe(8))
        _emit()
        if J.mobile.get("server"):
            J.reply(f"Listo para calificar «{ex['titulo']}» ({ex['curso']}). Escanea el código del HUD con tu celular (en la misma wifi) y "
                    "tómale foto a cada hoja: te digo la nota al instante. También puedes arrastrar las fotos al HUD. Al terminar: «terminé de calificar».",
                    "CALIFICAR")
        else:
            J.reply(f"Listo para calificar «{ex['titulo']}». Arrastra las fotos de las hojas al HUD. Para tomarlas con el celular, activa el "
                    "«panel del celular» en Ajustes › Integraciones. Al terminar: «terminé de calificar».", "CALIFICAR")
        return True
    if _GR_END.search(t):
        if getattr(J._tl, "capture", None) is not None:
            J.close_grading()
        else:
            J.start_job("Analizando la evaluación", J.close_grading, "calificar")
        return True
    if _GR_REF.search(t):
        J.reply("Preparo el refuerzo a la medida de cada estudiante…", "CALIFICAR")
        if getattr(J._tl, "capture", None) is not None:
            J.reinforcement()
        else:
            J.start_job("Preparando el refuerzo personalizado", J.reinforcement, "refuerzo")
        return True
    if _GR_ASK.search(t):
        ex = examenes.latest()
        J.reply(spoken_analysis(ex, analysis(ex)) if ex else "No tengo evaluaciones calificadas.", "CALIFICAR")
        return True
    m = _GR_NAME.search(t)
    if m:
        ex = examenes.latest()
        if ex and f"s{m.group(1)}" in ex["resultados"]:
            names = aula.students(ex["curso"])
            who = aula.find_student(m.group(2), names)[0] if names else m.group(2).title()
            examenes.rename(ex["code"], f"s{m.group(1)}", who or m.group(2).title())
            J.reply(f"Listo, la hoja sin nombre {m.group(1)} es de {who or m.group(2).title()}.", "CALIFICAR")
        else:
            J.reply("No encuentro esa hoja sin nombre.", "CALIFICAR")
        return True
    m = _GR_KEY.match(t)
    if m:
        ex = examenes.latest(open_only=True)
        clave = examenes.parse_key(m.group(1))
        if not ex or len(clave) < 2:
            return False
        ex["clave"] = clave[:len(ex["clave"])] + ex["clave"][len(clave):]
        for k, r in ex["resultados"].items():          # recalifica lo que ya estaba
            g = omr.grade(r["answers"], ex["clave"])
            r.update(aciertos=g["aciertos"], total=g["total"], nota=g["nota"], detalle=g["detalle"])
        examenes.save()
        J.reply(f"Clave de «{ex['titulo']}» actualizada ({len(ex['clave'])} preguntas)" +
                (f"; recalifiqué {len(ex['resultados'])} hojas." if ex["resultados"] else "."), "CALIFICAR")
        return True
    return False


# ============================================================================ CELULAR, HUD Y QR
@J.mobile_app.route("/h/<token>", methods=["GET"])
def grading_page(token):
    from flask import abort, render_template
    if not sess["token"] or not secrets.compare_digest(token, sess["token"]):
        abort(404)
    return render_template("calificar.html", token=token)


@J.mobile_app.route("/h/<token>/datos", methods=["GET"])
def grading_data(token):
    from flask import abort
    if not sess["token"] or not secrets.compare_digest(token, sess["token"]):
        abort(404)
    ex = examenes.get(sess["code"]) if sess["code"] else examenes.latest(open_only=True)
    if not ex:
        return {"ok": False, "titulo": "", "n": 0}
    return {"ok": True, "titulo": ex["titulo"], "curso": ex["curso"], "n": len(ex["resultados"]), "esperados": len(ex["estudiantes"]),
            "preguntas": len(ex["clave"]), "cerrado": ex["cerrado"]}


@J.mobile_app.route("/h/<token>/foto", methods=["POST"])
def grading_photo(token):
    from flask import abort, request
    if not sess["token"] or not secrets.compare_digest(token, sess["token"]):
        abort(404)
    data = request.get_data(cache=False)
    if not data or len(data) > 15 * 1024 * 1024:
        return {"ok": False, "msg": "La foto no llegó o es muy grande."}
    return grade_photo(data)


@J.app.route("/calificar-qr.png")
def grading_qr():
    from flask import Response, abort
    if not sess["token"]:
        abort(404)
    import qrcode
    img = qrcode.make(grading_url(), box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(buf.getvalue(), mimetype="image/png", headers={"Cache-Control": "no-store"})


@J.socketio.on("grade_upload")
def handle_grade_upload(data=None):
    import base64
    d = str((data or {}).get("data") or "")
    if "," in d:
        d = d.split(",", 1)[1]
    try:
        raw = base64.b64decode(d)
    except Exception:
        return {"ok": False, "msg": "No pude abrir la imagen."}
    if not examenes.latest(open_only=True):
        return {"ok": False, "msg": "No hay hojas por calificar."}
    return grade_photo(raw)


@J.socketio.on("grading_state")
def handle_grading_state(data=None):
    ex = examenes.latest(open_only=True)
    return {"open": bool(ex and sess["code"] == ex["code"])}


def grading_start():
    examenes.configure(J.CONFIG_DIR)


__all__ = ['_COURSE_IN', '_GR_ASK', '_GR_END', '_GR_KEY', '_GR_NAME', '_GR_REF', '_GR_START', '_SH_RE', '_emit', '_vision_read', 'analysis',
           'analysis_docx', 'close_grading', 'exam_from_quiz', 'examenes', 'grade_photo', 'grading_data', 'grading_page', 'grading_photo',
           'grading_qr', 'grading_start', 'grading_url', 'grading_voice', 'handle_grade_upload', 'handle_grading_state', 'make_sheets',
           'record_grades', 'reinforcement', 'reinforcement_prompt', 'sess', 'sheets_voice', 'spoken_analysis']
