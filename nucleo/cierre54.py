"""12.54: acta de la comisión de evaluación y promoción, y orientación vocacional para once.

    «prepara el acta de la comisión de evaluación de séptimo» · «actas de las comisiones de evaluación»
    «abre el test vocacional para 11A» (QR en el proyector; responden en el celular) · «cierra el test vocacional»
    «resultados del test vocacional de 11A» · «orientación vocacional para Ana de 11A»

La lógica está en comision.py y vocacional.py. Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import html
import io
import json
import os
import re
import secrets
import threading
import time

import aula
import comision as CM
import periodos
import seguimiento
import vocacional as VC
from nucleo import J

# ============================================================================ ACTA DE LA COMISIÓN DE EVALUACIÓN Y PROMOCIÓN
cm_state = {"busy": False}
_cmi_lock = threading.Lock()


def _cmi_path():
    return os.path.join(J.CONFIG_DIR, "comisiones.json")


def _cmi_prev():
    try:
        with open(_cmi_path(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def comision_keys(grado):
    keys = set(seguimiento.data) | set(periodos.data) | set(aula.data.get("cursos", {}))
    return sorted(k for k in keys if aula.grade_of(str(k).split(" · ")[0]) == grado)


def comision_cases(grado):
    pw = J.pweights()
    cur = min(max(1, int(J.settings["period_current"])), len(pw))
    final = cur == len(pw)
    cases = []
    for key in J.comision_keys(grado):
        abs_ = J._absences(key)
        for est, st in J.course_year(key).items():
            recs = [f"{n['actividad']} ({n['nota']:g})" for n in seguimiento.data.get(key, {}).get(est, []) if n.get("origen") == "recuperacion"]
            c = CM.case_of(key, est, dict(st, final=final), abs_.get(est, 0), recs)
            if c:
                cases.append(c)
    return cases, cur, final


def comision_acta(grado):
    """→ (ruta del Word, casos) o ValueError si no hay casos."""
    cases, per, final = J.comision_cases(grado)
    if not cases:
        raise ValueError(f"en grado {grado} no hay estudiantes con desempeño bajo ni en riesgo en tus asignaturas")
    prev_all = _cmi_prev().get(str(grado), {})
    prev = {c["estudiante"]: "; ".join(prev_all.get(c["estudiante"], [])) for c in cases if prev_all.get(c["estudiante"])}
    siee = ""
    if J.inst_docs():
        hits = J.inst_search("criterios de promoción reprobación comisión de evaluación y promoción", k=4)
        siee = "\n\n".join(f"[{h['libro']}, pág. {h['pagina']}] {h['texto'][:1400]}" for h in hits)
    recs, obs, estr = cases, "", []
    if J.state.get("ai") == "ok":
        try:
            d = J._extract_json(J.ai_chat([{"role": "user", "content": CM.prompt(CM.grade_label(grado), per, final, cases, siee, prev)}],
                                          json_mode=True, max_tokens=5000))
            recs, obs, estr = CM.clean(d, cases)
        except Exception as e:
            J.log_terminal(f"Comisión: la IA no ayudó con las recomendaciones ({e}); dejo el acta con los datos.", "COMISIÓN")
            recs = [dict(c, recomendaciones=[], compromisos=[], promocion="") for c in cases]
    else:
        recs = [dict(c, recomendaciones=[], compromisos=[], promocion="") for c in cases]
    path = _cmi_docx(grado, per, final, recs, obs, estr, prev)
    with _cmi_lock:
        d = _cmi_prev()
        d[str(grado)] = {c["estudiante"]: c["compromisos"] for c in recs if c.get("compromisos")}
        os.makedirs(J.CONFIG_DIR, exist_ok=True)
        with open(_cmi_path(), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
    return path, recs


def _cmi_docx(grado, per, final, recs, obs, estr, prev):
    import docx
    doc = docx.Document()
    doc.add_heading(f"Comisión de evaluación y promoción · Grado {CM.grade_label(grado)}", 0)
    doc.add_paragraph(f"Periodo {per}{' (cierre del año)' if final else ''} · Fecha: {datetime.date.today().strftime('%d/%m/%Y')} · "
                      f"Insumo preparado por el docente con Jarvis para las asignaturas a su cargo.")
    doc.add_paragraph().add_run("Las decisiones corresponden a la comisión, según el Sistema Institucional de Evaluación (SIEE) y el "
                                "Decreto 1290 de 2009. Información confidencial de los estudiantes.").italic = True
    doc.add_heading("Asistentes", 1)
    tb = doc.add_table(rows=1, cols=3)
    tb.style = "Light Grid Accent 1"
    for c, h in zip(tb.rows[0].cells, ("Nombre", "Rol", "Firma")):
        c.text = h
    for rol in ("Docente", "Docente", "Docente", "Representante de los padres de familia", "Rector(a) o su delegado(a)"):
        row = tb.add_row().cells
        row[1].text = rol
    doc.add_heading("Orden del día", 1)
    for i, s in enumerate(("Verificación de los compromisos del periodo anterior", "Análisis de los casos de desempeño bajo y en riesgo",
                           "Recomendaciones y compromisos", "Promoción" if final else "Estrategias de apoyo para el grado",
                           "Varios y cierre"), 1):
        doc.add_paragraph(f"{i}. {s}")
    if prev:
        doc.add_heading("1. Compromisos del periodo anterior", 1)
        t2 = doc.add_table(rows=1, cols=3)
        t2.style = "Light Grid Accent 1"
        for c, h in zip(t2.rows[0].cells, ("Estudiante", "Compromisos", "¿Se cumplieron?")):
            c.text = h
        for est, txt in prev.items():
            r = t2.add_row().cells
            r[0].text, r[1].text = est, txt
    doc.add_heading("2. Casos analizados", 1)
    t3 = doc.add_table(rows=1, cols=6)
    t3.style = "Light Grid Accent 1"
    for c, h in zip(t3.rows[0].cells, ("Estudiante", "Curso / asignatura", "Periodos anteriores", "Periodo actual", "Fallas", "Motivo")):
        c.text = h
    for c in recs:
        r = t3.add_row().cells
        r[0].text, r[1].text = c["estudiante"], c["curso"]
        r[2].text = ", ".join("—" if v is None else f"{v:g}" for v in c["previos"]) or "—"
        r[3].text = "—" if c["actual"] is None else f"{c['actual']:g}"
        r[4].text, r[5].text = str(c["faltas"]), "; ".join(c["motivos"])
    doc.add_heading("3. Recomendaciones y compromisos", 1)
    for c in recs:
        doc.add_heading(f"{c['estudiante']} · {c['curso']}", 2)
        if c.get("recuperaciones"):
            doc.add_paragraph("Actividades de recuperación ya presentadas: " + "; ".join(c["recuperaciones"]))
        for x in c.get("recomendaciones") or ["(escribir)"]:
            doc.add_paragraph(x, style="List Bullet")
        doc.add_paragraph().add_run("Compromisos:").bold = True
        for x in c.get("compromisos") or ["(escribir, con fecha)"]:
            doc.add_paragraph(x, style="List Number")
        if final:
            doc.add_paragraph(f"Concepto de promoción: {c.get('promocion') or 'a decisión de la comisión'}")
    doc.add_heading("4. " + ("Promoción" if final else "Estrategias de apoyo para el grado"), 1)
    for x in estr or ["(escribir)"]:
        doc.add_paragraph(x, style="List Bullet")
    if obs:
        doc.add_heading("Observaciones generales", 1)
        doc.add_paragraph(obs)
    doc.add_paragraph("\nSe levanta la sesión. En constancia firman los asistentes.")
    out = os.path.join(J.settings["output_dir"], "Comisiones")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, f"Comisión grado {grado} periodo {per} {time.strftime('%Y-%m-%d %H%M')}.docx")
    doc.save(path)
    return path


_CM_GR = r"(\d{1,2}\s?[a-z]?|sexto|septimo|octavo|noveno|decimo|once|undecimo)"
_CM = re.compile(r"\b(?:prepara|preparame|haz|hazme|arma|armame|genera|elabora)\s+(?:el\s+|las\s+)?(?:acta|actas|insumo)\s+(?:de\s+)?(?:la\s+|las\s+)?"
                 r"comision(?:es)?\s+de\s+evaluacion(?:\s+y\s+promocion)?(?:\s+(?:de|del|para)\s+(?:grado\s+)?" + _CM_GR + r")?\b"
                 r"|\bactas? de (?:la |las )?comision(?:es)? de evaluacion(?:\s+y\s+promocion)?(?:\s+(?:de|del|para)\s+(?:grado\s+)?" + _CM_GR + r")?\b")


def comision_voice(text, t):
    m = _CM.search(t)
    if not m:
        return False
    spoken = next((g for g in m.groups() if g), "")
    grados = []
    if spoken:
        g = aula.grade_of(spoken)
        if g:
            grados = [g]
    else:
        grados = sorted({g for g in (aula.grade_of(str(k).split(" · ")[0]) for k in set(seguimiento.data) | set(aula.data.get("cursos", {}))) if g})
    if not grados:
        J.reply("¿De qué grado? Por ejemplo: «prepara el acta de la comisión de evaluación de séptimo».", "COMISIÓN")
        return True
    if cm_state["busy"]:
        J.reply("Ya estoy preparando un acta; te aviso al terminar.", "COMISIÓN")
        return True
    cm_state["busy"] = True
    J.reply("Preparo " + ("el acta de la comisión de grado " + str(grados[0]) if len(grados) == 1 else f"las actas de {len(grados)} grados")
            + " con tus notas, fallas y recuperaciones" + (" y los criterios de tu SIEE" if J.inst_docs() else "") + ". Te aviso.", "COMISIÓN")

    def work():
        done, empty = [], []
        try:
            for g in grados:
                try:
                    path, recs = comision_acta(g)
                except ValueError:
                    empty.append(g)
                    continue
                J.generated_files.add(path)
                done.append((g, len(recs), path))
        except J.AIError as e:
            J.notify(J.ai_error_reply(e), "COMISIÓN")
            return
        finally:
            cm_state["busy"] = False
        if not done:
            J.notify("No hay casos para la comisión: nadie tiene desempeño bajo ni está en riesgo en tus asignaturas. 👌", "COMISIÓN")
            return
        J._open_doc(done[0][2])
        J.notify("Listas las actas: " + "; ".join(f"grado {g}, {n} caso(s)" for g, n, _p in done)
                 + (f". Sin casos: grado {', '.join(map(str, empty))}" if empty else "")
                 + ". Están en Documentos, Jarvis, Comisiones, con las recomendaciones y compromisos para revisar en la reunión.", "COMISIÓN")
    J.start_job("Preparando el acta de la comisión", work, "comision")
    return True


# ============================================================================ ORIENTACIÓN VOCACIONAL
voc = {"sessions": {}, "last": ""}
_voc_lock = threading.Lock()


def _voc_path():
    return os.path.join(J.CONFIG_DIR, "vocacional.json")


def voc_data():
    try:
        with open(_voc_path(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def voc_save_result(curso, est, answers):
    prof = VC.score(answers)
    with _voc_lock:
        d = voc_data()
        d.setdefault(curso, {})[est] = {"perfil": prof, "codigo": VC.code(prof), "fecha": datetime.date.today().isoformat()}
        os.makedirs(J.CONFIG_DIR, exist_ok=True)
        with open(_voc_path(), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
    return prof


@J.mobile_app.route("/voc/<code>", methods=["GET"])
def voc_page(code):
    from flask import abort
    s = voc["sessions"].get(str(code))
    if not s or not s.get("abierta"):
        abort(404)
    opts = ["Nada", "Poco", "Algo", "Bastante", "Mucho"]
    qs = "".join(f"<div class='q'><p>{i + 1}. {html.escape(q)}</p><div class='o'>"
                 + "".join(f"<label><input type='radio' name='q{i}' value='{v}' required><span>{o}</span></label>" for v, o in enumerate(opts))
                 + "</div></div>" for i, (_k, q) in enumerate(VC.QUESTIONS))
    return ("<!DOCTYPE html><html lang='es'><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
            "<title>Test de intereses</title><style>body{margin:0;padding:14px;background:#0e1116;color:#ecf0f1;font-family:system-ui,sans-serif}"
            "h1{color:#58c4dd;font-size:20px}.q{background:#161c26;border-radius:12px;padding:10px 12px;margin:10px 0}.q p{margin:0 0 8px}"
            ".o{display:flex;gap:4px;flex-wrap:wrap}.o label{flex:1;min-width:58px}.o input{display:none}.o span{display:block;text-align:center;"
            "padding:8px 2px;border-radius:8px;background:#222b3a;font-size:13px}.o input:checked+span{background:#58c4dd;color:#0e1116;font-weight:700}"
            "input[type=text]{width:100%;padding:12px;border-radius:10px;border:0;font-size:16px;box-sizing:border-box}"
            "button{width:100%;padding:14px;margin:14px 0;border:0;border-radius:12px;background:#f5b942;font-size:17px;font-weight:700}"
            "#r{background:#12261c;border-radius:12px;padding:14px;display:none}</style></head><body>"
            f"<h1>Test de intereses · {html.escape(s['curso'])}</h1><p>¿Cuánto te gusta cada actividad? No hay respuestas buenas ni malas.</p>"
            "<form id='f'><input type='text' id='n' placeholder='Tu nombre y apellido' required>" + qs +
            "<button type='submit'>Ver mi perfil</button></form><div id='r'></div>"
            "<script>document.getElementById('f').addEventListener('submit',function(e){e.preventDefault();var a=[];"
            f"for(var i=0;i<{len(VC.QUESTIONS)};i++){{var x=document.querySelector('input[name=q'+i+']:checked');a.push(x?+x.value:0)}}"
            f"fetch('/voc/{code}/enviar',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{nombre:document.getElementById('n').value,respuestas:a}})}})"
            ".then(function(r){return r.json()}).then(function(d){var r=document.getElementById('r');r.style.display='block';"
            "if(!d.ok){r.textContent=d.msg;return}document.getElementById('f').style.display='none';r.textContent=d.texto})});</script></body></html>")


@J.mobile_app.route("/voc/<code>/enviar", methods=["POST"])
def voc_submit(code):
    from flask import jsonify, request
    s = voc["sessions"].get(str(code))
    if not s or not s.get("abierta"):
        return jsonify({"ok": False, "msg": "El test ya se cerró."})
    d = request.get_json(silent=True) or {}
    ans = d.get("respuestas") or []
    if not isinstance(ans, list) or len(ans) != len(VC.QUESTIONS):
        return jsonify({"ok": False, "msg": "Responde todas las preguntas."})
    est = VC.match_student(str(d.get("nombre") or "")[:80], aula.students(s["curso"]))
    if not est:
        return jsonify({"ok": False, "msg": "No encontré tu nombre en la lista del curso. Escríbelo como aparece en la lista (nombre y apellido)."})
    prof = voc_save_result(s["curso"], est, ans)
    s["n"] = s.get("n", 0) + 1
    J.socketio.emit("ticket_progress", {"tipo": "vocacional", "n": s["n"]})
    return jsonify({"ok": True, "texto": f"Gracias, {est.split()[0]}. " + VC.describe(prof)
                    + " Tu docente te dará una orientación más completa. Recuerda: tus intereses pueden cambiar, ¡explora!"})


@J.app.route("/voc-qr.png")
def voc_qr():
    import qrcode
    from flask import Response, abort, request
    c = request.args.get("c", "")
    if c not in voc["sessions"]:
        abort(404)
    buf = io.BytesIO()
    qrcode.make(J._lan(f"/voc/{c}"), box_size=10, border=2).save(buf, format="PNG")
    return Response(buf.getvalue(), mimetype="image/png", headers={"Cache-Control": "no-store"})


def voc_orientation(curso, est):
    """Informe individual (IA) en Word. → ruta."""
    r = voc_data().get(curso, {}).get(est)
    if not r:
        raise ValueError(f"{est} todavía no ha hecho el test")
    d = J._extract_json(J.ai_chat([{"role": "user", "content": VC.report_prompt(est, r["perfil"])}], json_mode=True, max_tokens=2600))
    import docx
    doc = docx.Document()
    doc.add_heading(f"Orientación vocacional · {est}", 0)
    doc.add_paragraph(f"{curso} · {datetime.date.today().strftime('%d/%m/%Y')} · Perfil de intereses: " +
                      ", ".join(f"{VC.TYPES[k][0]} {r['perfil'][k]} %" for k in VC.top(r["perfil"], 6)))
    doc.add_paragraph(str(d.get("mensaje") or VC.describe(r["perfil"])))
    if d.get("carreras"):
        doc.add_heading("Carreras y programas para explorar", 1)
        for c in d["carreras"][:6]:
            if isinstance(c, dict):
                p = doc.add_paragraph(style="List Bullet")
                p.add_run(f"{c.get('nombre', '')} ({c.get('tipo', '')}): ").bold = True
                p.add_run(str(c.get("por_que", "")))
    for title, key in (("Qué puedes hacer este año", "este_anio"), ("Rutas para seguir estudiando en Colombia", "rutas")):
        if d.get(key):
            doc.add_heading(title, 1)
            for x in d[key][:6]:
                doc.add_paragraph(str(x), style="List Bullet")
    doc.add_paragraph().add_run("Es una orientación a partir de tus intereses, no un diagnóstico. Consulta becas, fechas y requisitos "
                                "en las páginas oficiales (SNIES, Sofía Plus del SENA, ICETEX y admisiones de cada universidad).").italic = True
    out = os.path.join(J.settings["output_dir"], "Orientación vocacional", curso.replace("/", "-"))
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, f"{est}.docx")
    doc.save(path)
    return path


def voc_summary(curso):
    d = voc_data().get(curso, {})
    if not d:
        return ""
    count = {}
    for r in d.values():
        k = VC.top(r["perfil"], 1)[0]
        count[k] = count.get(k, 0) + 1
    parts = ", ".join(f"{n} {VC.TYPES[k][0].lower()}" for k, n in sorted(count.items(), key=lambda kv: -kv[1]))
    return f"En {curso} hicieron el test {len(d)} estudiantes. Intereses principales: {parts}."


_VC_GR = r"(\d{1,2}\s?[a-z]?|once|undecimo|decimo)"
_VC_OPEN = re.compile(r"\b(?:abre|inicia|lanza|activa|pon|proyecta)\s+(?:el\s+)?test (?:vocacional|de intereses)(?:\s+(?:para|de|en)\s+" + _VC_GR + r")?\b")
_VC_CLOSE = re.compile(r"\b(?:cierra|termina|finaliza)\s+(?:el\s+)?test (?:vocacional|de intereses)\b")
_VC_RES = re.compile(r"\bresultados? del test (?:vocacional|de intereses)(?:\s+(?:de|en|del)\s+" + _VC_GR + r")?\b")
_VC_ONE = re.compile(r"\borientacion vocacional (?:para|de) (.+?)(?:\s+(?:de|del|en)\s+" + _VC_GR + r")?$")


def _voc_course(spoken):
    if spoken:
        return J._resolve_course(spoken) or ""
    act = aula.data.get("activo", "")
    if act and aula.grade_of(act) in (10, 11):
        return act
    elevens = [c for c in aula.data.get("cursos", {}) if aula.grade_of(c) == 11]
    return elevens[0] if len(elevens) == 1 else ""


def vocacional_voice(text, t):
    m = _VC_OPEN.search(t)
    if m:
        curso = _voc_course(m.group(1))
        if not curso:
            J.reply("¿Para qué curso? Por ejemplo: «abre el test vocacional para 11A».", "VOCACIONAL")
            return True
        if J._need_lan():
            return True
        code = secrets.token_urlsafe(5)
        voc["sessions"][code] = {"curso": curso, "abierta": True, "t": time.time(), "n": 0}
        voc["last"] = code
        J._open_projector()
        J.socketio.emit("ticket", {"open": True, "url": J._lan(f"/voc/{code}"), "qr": "/voc-qr.png?c=" + code, "tipo": "vocacional",
                                   "tema": f"Test de intereses · {curso}", "n": 0})
        J.reply(f"El test de intereses de {curso} está en el proyector: escanean el QR, escriben su nombre y responden 30 preguntas "
                "(unos 7 minutos). Al terminar, di «cierra el test vocacional».", "VOCACIONAL")
        return True
    if _VC_CLOSE.search(t):
        s = voc["sessions"].get(voc["last"])
        if not s or not s.get("abierta"):
            J.reply("No hay un test vocacional abierto.", "VOCACIONAL")
            return True
        s["abierta"] = False
        J.socketio.emit("ticket", {"open": False})
        J.reply(f"Cerré el test. {voc_summary(s['curso']) or 'Nadie alcanzó a responder.'} Para el informe de cada uno: "
                "«orientación vocacional para Ana».", "VOCACIONAL")
        return True
    m = _VC_RES.search(t)
    if m:
        curso = _voc_course(m.group(1)) or next(iter(voc_data()), "")
        J.reply(voc_summary(curso) or "Todavía nadie ha hecho el test vocacional. Di «abre el test vocacional para 11A».", "VOCACIONAL")
        return True
    m = _VC_ONE.search(t)
    if m:
        name = m.group(1).strip()
        curso = _voc_course(m.group(2))
        cands = [(c, e) for c, d in voc_data().items() for e in d if (not curso or c == curso) and VC.norm_name(name) in VC.norm_name(e)]
        if not cands:
            J.reply(f"No tengo el test de «{name}». Primero lo hace en el celular: «abre el test vocacional para 11A».", "VOCACIONAL")
            return True
        if J.state.get("ai") != "ok":
            J.reply("Para escribir la orientación necesito la IA conectada.", "VOCACIONAL")
            return True
        c, est = cands[0]
        J.reply(f"Preparo la orientación vocacional de {est}…", "VOCACIONAL")

        def work():
            try:
                path = voc_orientation(c, est)
            except J.AIError as e:
                J.notify(J.ai_error_reply(e), "VOCACIONAL")
                return
            except Exception as e:
                J.notify(f"No pude preparar la orientación: {str(getattr(e, 'why', e))[:160]}", "VOCACIONAL")
                return
            J.generated_files.add(path)
            J._open_doc(path)
            J.notify(f"Lista la orientación vocacional de {est}, en Documentos, Jarvis, Orientación vocacional.", "VOCACIONAL")
        J.start_job("Orientación vocacional", work, "vocacional")
        return True
    return False


def cierre54_voice(text, t):
    return comision_voice(text, t) or vocacional_voice(text, t)


__all__ = ["cm_state", "_cmi_path", "_cmi_prev", "comision_keys", "comision_cases", "comision_acta", "_cmi_docx", "comision_voice", "_CM", "_CM_GR",
           "voc", "_voc_path", "voc_data", "voc_save_result", "voc_page", "voc_submit", "voc_qr", "voc_orientation", "voc_summary",
           "_VC_GR", "_VC_OPEN", "_VC_CLOSE", "_VC_RES", "_VC_ONE", "_voc_course", "vocacional_voice", "cierre54_voice"]
