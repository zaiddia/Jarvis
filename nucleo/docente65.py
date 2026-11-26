"""12.65: nueve funciones nuevas.

  1. «¿Esto es una estafa? …» (o el botón al subir una captura o un mensaje): veredicto, señales y qué hacer.
  2. «Evalúa esta exposición de Juan» (o el botón al subir el video): Gemini ve y escucha; rúbrica, nota sugerida, Word.
  3. «Prepara el diagnóstico de matemáticas para séptimo» · «abre el diagnóstico para 7A» (QR) · «cierra el diagnóstico».
  4. «Revisa este contrato» (o el botón al subir un PDF o Word): qué es, lo riesgoso, la ley y qué negociar.
  5. «Haz los diplomas de los mejores de cada curso» · «diplomas de 7A» · «diploma para Sofía Gómez de 9A por su liderazgo».
  6. «¿Debo declarar renta?» (con el certificado de ingresos subido, o «gano 4 millones al mes»): topes en UVT oficiales.
  7. «Planea una salida pedagógica al jardín botánico con 9A el 15 de marzo» · «Juan entregó la autorización» ·
     «¿quién no ha entregado la autorización?».
  8. «Formula el proyecto ambiental» · «evidencia del PRAE: jornada de reciclaje» · «informe final del PRAE».
  9. «Organiza los exámenes de las próximas dos semanas» (con tu horario): sin dos el mismo día por curso; aviso la víspera.

La lógica está en estafas.py, exposicion.py, diagnostico.py, clausura.py y renta.py. Los nombres globales de Jarvis se
usan como J.<nombre>.
"""
import base64
import datetime
import html
import io
import json
import os
import re
import secrets
import subprocess
import tempfile
import threading
import time

import adjuntos
import animar
import aula
import clausura as CL
import confianza
import diagnostico as DG
import estafas as EF
import exposicion as EX
import festivos
import horario
import renta as RT
import seguimiento
import vocacional
from nucleo import J

D65_ACTIONS = {"estafa": "¿Es una estafa?", "contrato": "Revisar contrato", "exposicion": "Evaluar exposición",
               "renta": "¿Debo declarar renta?"}
_d65_lock = threading.Lock()


def _d65_path():
    return os.path.join(J.CONFIG_DIR, "docente65.json")


def d65_data():
    try:
        with open(_d65_path(), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    for k in ("diagnosticos", "salidas", "proyectos", "cronograma"):
        d.setdefault(k, {} if k != "cronograma" else [])
    return d


def d65_save(d):
    with _d65_lock:
        os.makedirs(J.CONFIG_DIR, exist_ok=True)
        tmp = _d65_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1, default=str)
        os.replace(tmp, _d65_path())


def _d65_out(*parts):
    folder = os.path.join(J.settings["output_dir"], *parts)
    os.makedirs(folder, exist_ok=True)
    return folder


def _d65_open(path):
    if J.settings.get("aula_open_docs", True):
        J._open_doc(path)


def _d65_doc(title, sub=""):
    doc = J.Document()
    inst = J.settings.get("aula_institucion", "").strip()
    if inst:
        doc.add_paragraph(inst).runs[0].bold = True
    doc.add_heading(title, 0)
    if sub:
        doc.add_paragraph(sub)
    return doc


def _d65_text_doc(doc, text):
    """Texto de la IA (secciones en MAYÚSCULAS seguidas de «:») → títulos y párrafos."""
    for line in str(text or "").splitlines():
        s = line.strip().strip("*#").strip()
        if not s:
            continue
        m = re.match(r"^([A-ZÁÉÍÓÚÑ0-9 ()/,.-]{4,60}):?\s*(.*)$", s)
        if m and m.group(1).upper() == m.group(1) and len(m.group(1).split()) <= 8:
            doc.add_heading(m.group(1).title(), 2)
            if m.group(2):
                doc.add_paragraph(m.group(2))
        elif re.match(r"^[-•]\s+", s):
            doc.add_paragraph(re.sub(r"^[-•]\s+", "", s), style="List Bullet")
        else:
            doc.add_paragraph(s)


def _d65_safe(name):
    return re.sub(r'[\\/:*?"<>|]+', "-", str(name)).strip()[:80] or "documento"


def _d65_recent(kinds):
    """El último archivo que subiste de esos tipos (en la última media hora)."""
    for it in adjuntos.recent(1800):
        if it["tipo"] in kinds:
            return it
    return None


# ============================================================================ 1 y 4. ESTAFAS Y CONTRATOS
def scam_check_text(text):
    sigs = EF.signals(text)
    if J.state.get("ai") != "ok":
        return EF.local_text(sigs)
    try:
        return J.ai_chat([{"role": "system", "content": EF.scam_prompt(sigs) + confianza.RULE},
                          {"role": "user", "content": confianza.wrap(str(text)[:12000], "MENSAJE A REVISAR")}], max_tokens=1200).strip()
    except J.AIError:
        return EF.local_text(sigs)


def scam_check_items(its):
    texts = []
    for it in its:
        t, img = J.content_for_ai(it, 12000)
        if img:
            return J._vision_text(EF.scam_prompt([]) + " Esto es una captura de pantalla: lee todo lo que dice antes de juzgar.", img, 1500)
        texts.append(t)
    return scam_check_text("\n\n".join(texts))


def contract_check(its):
    return J.ask_files(its, EF.contract_prompt())


_D65_SCAM = re.compile(r"^(?:jarvis\s+)?(?:(?:esto|este mensaje|este correo|este enlace|este link|esta pagina|esta tienda|esto que me llego)\s+)?"
                       r"(?:es|sera|parece)\s+(?:una\s+)?(?:estafa|fraude|robo|enganio|engano|phishing)\b[\s?:.,]*(.*)$|"
                       r"^(?:jarvis\s+)?(?:revisa|mira|analiza|chequea)\s+si\s+(?:esto|este mensaje|este correo|este enlace|este link)\s+es\s+"
                       r"(?:una\s+)?(?:estafa|fraude|real|verdad|confiable)\b[\s?:.,]*(.*)$")
_D65_CONTRACT = re.compile(r"^(?:jarvis\s+)?(?:revisa|analiza|explicame|lee)(?:me)?\s+(?:este|el)\s+(?:contrato|documento antes de firmar|pagare|"
                           r"credito|arriendo|plan)\b")


def _d65_scam_voice(text, t):
    m = _D65_SCAM.match(t)
    if not m:
        return False
    # lo que viene después en la frase original (con mayúsculas y enlaces tal cual)
    tail = re.split(r"(?i)(?:estafa|fraude|phishing|robo|engaño|confiable|real|verdad)\s*[?:.,]*\s*", text, maxsplit=1)
    tail = tail[1].strip() if len(tail) > 1 else ""
    if len(tail) >= 12:
        J.reply("Lo reviso…", "ESTAFAS")
        J.start_job("Revisando si es una estafa", lambda: J.notify(J.scam_check_text(tail), "ESTAFAS"), "estafa")
        return True
    it = _d65_recent(("imagen", "texto", "pdf", "word"))
    if it:
        J.reply(f"Reviso «{it['nombre']}»…", "ESTAFAS")
        J.start_job("Revisando si es una estafa", lambda: J.notify(J.scam_check_items([it]), "ESTAFAS"), "estafa")
        return True
    J.reply("Pégame el mensaje o el enlace después de la pregunta («¿esto es una estafa? …»), o súbeme la captura y toca "
            "«¿Es una estafa?».", "ESTAFAS")
    return True


def _d65_contract_voice(text, t):
    if not _D65_CONTRACT.match(t):
        return False
    it = _d65_recent(("pdf", "word", "imagen", "texto"))
    if not it:
        J.reply("Súbeme el contrato (PDF, Word o fotos) y toca «Revisar contrato», o dime «revisa este contrato» después de subirlo.", "CONTRATOS")
        return True
    J.reply(f"Leo «{it['nombre']}» y te explico lo importante…", "CONTRATOS")
    J.start_job("Revisando el contrato", lambda: J.notify(J.contract_check([it]), "CONTRATOS"), "contrato")
    return True


# ============================================================================ 2. EXPOSICIONES DESDE VIDEO
def _d65_small_video(src):
    """Una copia liviana para la IA (360 p, 5 cuadros por segundo, audio mono). → ruta."""
    ff = animar.ffmpeg_exe()
    if not ff:
        raise ValueError("falta el componente de video (imageio-ffmpeg)")
    for scale, fps, crf in (("360", 5, 32), ("240", 2, 36)):
        out = os.path.join(tempfile.mkdtemp(prefix="jarvis_expo_"), "expo.mp4")
        r = subprocess.run([ff, "-y", "-i", src, "-vf", f"scale=-2:{scale},fps={fps}", "-c:v", "libx264", "-preset", "veryfast",
                            "-crf", str(crf), "-c:a", "aac", "-ac", "1", "-b:a", "32k", out],
                           capture_output=True, timeout=900, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) <= 19_000_000:
            return out
    raise ValueError("el video es muy largo para evaluarlo de una vez (más de unos 15 minutos); córtalo en partes")


def expo_evaluate(it, estudiante="", tema="", rubric_custom=""):
    """→ (dict de la evaluación, ruta del Word)."""
    cfg = J._gemini_for_stt()
    if not cfg:
        raise ValueError("para ver el video necesito tu clave de Gemini (Ajustes › Inteligencia artificial)")
    small = J._d65_small_video(it["ruta"])
    with open(small, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    body = {"contents": [{"role": "user", "parts": [{"inline_data": {"mime_type": "video/mp4", "data": b64}},
                                                     {"text": EX.prompt(estudiante, tema, rubric_custom)}]}],
            "generationConfig": {"maxOutputTokens": 4096, "temperature": 0.2, "responseMimeType": "application/json"}}

    def call(c):
        return J._gemini_text(J._post(f"{J.GEMINI_BASE}/models/{c['model']}:generateContent", J._gemini_headers(c), body, (), timeout=600))
    d = EX.parse(J._with_fallback(cfg, call))
    doc = _d65_doc("Evaluación de exposición", f"{estudiante or 'Estudiante'} · {tema or it['nombre']} · {datetime.date.today():%d/%m/%Y}")
    tb = doc.add_table(rows=1, cols=4)
    tb.style = "Table Grid"
    for c, h in zip(tb.rows[0].cells, ("Criterio", "Nota", "Lo que vi", "Para mejorar")):
        c.text = h
    for c in d["criterios"]:
        row = tb.add_row().cells
        row[0].text, row[1].text, row[2].text, row[3].text = c["nombre"], str(c["nota"]).replace(".", ","), c["evidencia"], c["mejorar"]
    doc.add_paragraph().add_run(f"Nota sugerida: {str(d['nota']).replace('.', ',')} (la nota final la pone el docente)").bold = True
    for title, key in (("Fortalezas", "fortalezas"), ("Aspectos a mejorar", "aspectos_a_mejorar")):
        if d[key]:
            doc.add_heading(title, 2)
            for x in d[key]:
                doc.add_paragraph(x, style="List Bullet")
    if d["comentario_estudiante"]:
        doc.add_heading("Para el estudiante", 2)
        doc.add_paragraph(d["comentario_estudiante"])
    path = os.path.join(_d65_out("Exposiciones"), _d65_safe(f"{estudiante or 'Exposición'} {datetime.date.today():%Y-%m-%d}") + ".docx")
    doc.save(path)
    return d, path


_D65_EXPO = re.compile(r"^(?:jarvis\s+)?(?:evalua|califica|revisa|valora)(?:me)?\s+(?:esta|la|este|el)\s+(?:exposicion|presentacion oral|sustentacion|"
                       r"video de la exposicion)(?:\s+(?:de|del estudiante|de la estudiante)\s+(.+?))?(?:\s+(?:sobre|del tema|de)\s+(.+?))?"
                       r"(?:\s+con\s+(?:la\s+)?rubrica.*)?$")


def _d65_expo_start(it, estudiante="", tema=""):
    rub = _d65_recent(("pdf", "word", "texto"))
    rub_txt = J._text_of_item(rub) if rub else ""

    def work():
        try:
            d, path = J.expo_evaluate(it, estudiante, tema, rub_txt)
        except (ValueError, J.AIError) as e:
            J.notify(f"No pude evaluar la exposición: {getattr(e, 'why', '') or e}.", "EXPOSICIÓN")
            return
        J.notify(EX.spoken(d, estudiante) + " Te dejé el Word con la rúbrica y el comentario para el estudiante.", "EXPOSICIÓN")
        _d65_open(path)
    J.start_job("Evaluando la exposición", work, "exposicion")


def _d65_expo_voice(text, t):
    m = _D65_EXPO.match(t)
    if not m:
        return False
    it = _d65_recent(("video",))
    if not it:
        J.reply("Súbeme el video de la exposición (lo grabas con el celular) y dime «evalúa esta exposición de Juan».", "EXPOSICIÓN")
        return True
    est = (m.group(1) or "").strip().title()
    J.reply(f"Veo la exposición{' de ' + est if est else ''} con Gemini y la califico con la rúbrica; tarda unos minutos. "
            "El video va a Google para analizarlo.", "EXPOSICIÓN")
    _d65_expo_start(it, est, (m.group(2) or "").strip())
    return True


# ============================================================================ 3. DIAGNÓSTICO DE INICIO DE AÑO
diag = {"sessions": {}, "last": ""}
_D65_GRADE_WORDS = {**{k: int(v) for k, v in aula.ORDINALES.items()}, "decimo": 10, "once": 11, "undecimo": 11, "noveno": 9}


def _d65_grade(t):
    m = re.search(r"\b(?:grado\s+)?(\d{1,2})(?:\s*[°º]|\b)", t)
    if m and 1 <= int(m.group(1)) <= 11:
        return int(m.group(1))
    for w, n in _D65_GRADE_WORDS.items():
        if re.search(rf"\b{w}\b", t):
            return n
    return 0


def diag_create(asignatura, grado, n=15):
    raw = J.ai_chat([{"role": "user", "content": DG.prompt(asignatura, grado, n)}], json_mode=True, max_tokens=6000)
    qs = DG.parse(raw)
    d = d65_data()
    key = f"{asignatura.lower()}|{grado}"
    d["diagnosticos"][key] = {"asignatura": asignatura, "grado": grado, "preguntas": qs, "resultados": {}, "creado": str(datetime.date.today())}
    d65_save(d)
    doc = _d65_doc(f"Evaluación diagnóstica · {asignatura} · grado {grado}", "Nombre: ______________________  Curso: ______")
    for i, q in enumerate(qs, 1):
        doc.add_paragraph(f"{i}. {q['enunciado']}")
        for j, o in enumerate(q["opciones"]):
            doc.add_paragraph(f"   {'ABCDE'[j]}) {o}")
    doc.add_page_break()
    doc.add_heading("Clave (para el docente)", 2)
    for i, q in enumerate(qs, 1):
        doc.add_paragraph(f"{i}. {'ABCDE'[q['correcta']]} · {q['competencia']}" + (f" · {q['dba']}" if q["dba"] else ""))
    path = os.path.join(_d65_out("Diagnósticos"), _d65_safe(f"Diagnóstico {asignatura} grado {grado}") + ".docx")
    doc.save(path)
    return key, qs, path


@J.mobile_app.route("/diag/<code>", methods=["GET"])
def diag_page(code):
    from flask import abort
    s = diag["sessions"].get(str(code))
    if not s or not s.get("abierta"):
        abort(404)
    qs = d65_data()["diagnosticos"].get(s["key"], {}).get("preguntas", [])
    body = "".join(f"<div class='q'><p>{i + 1}. {html.escape(q['enunciado'])}</p>" + "".join(
        f"<label><input type='radio' name='q{i}' value='{j}'><span>{'ABCDE'[j]}) {html.escape(o)}</span></label>" for j, o in enumerate(q["opciones"]))
        + "</div>" for i, q in enumerate(qs))
    return ("<!DOCTYPE html><html lang='es'><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
            "<title>Diagnóstico</title><style>body{margin:0;padding:14px;background:#0e1116;color:#ecf0f1;font-family:system-ui,sans-serif}"
            "h1{color:#58c4dd;font-size:20px}.q{background:#161c26;border-radius:12px;padding:10px 12px;margin:10px 0}.q p{margin:0 0 8px}"
            "label{display:block;margin:4px 0}input[type=radio]{display:none}label span{display:block;padding:9px 10px;border-radius:8px;background:#222b3a}"
            "input:checked+span{background:#58c4dd;color:#0e1116;font-weight:700}input[type=text]{width:100%;padding:12px;border-radius:10px;border:0;"
            "font-size:16px;box-sizing:border-box}button{width:100%;padding:14px;margin:14px 0;border:0;border-radius:12px;background:#f5b942;"
            "font-size:17px;font-weight:700}#r{background:#12261c;border-radius:12px;padding:14px;display:none}</style></head><body>"
            f"<h1>Diagnóstico · {html.escape(s['titulo'])}</h1><p>No es una nota: sirve para saber por dónde empezar. Responde con calma.</p>"
            "<form id='f'><input type='text' id='n' placeholder='Tu nombre y apellido' required>" + body +
            "<button type='submit'>Enviar</button></form><div id='r'></div><script>document.getElementById('f').addEventListener('submit',"
            f"function(e){{e.preventDefault();var a=[];for(var i=0;i<{len(qs)};i++){{var x=document.querySelector('input[name=q'+i+']:checked');"
            f"a.push(x?+x.value:null)}}fetch('/diag/{code}/enviar',{{method:'POST',headers:{{'Content-Type':'application/json'}},"
            "body:JSON.stringify({nombre:document.getElementById('n').value,respuestas:a})}).then(function(r){return r.json()})"
            ".then(function(d){var r=document.getElementById('r');r.style.display='block';if(!d.ok){r.textContent=d.msg;return}"
            "document.getElementById('f').style.display='none';r.textContent=d.texto})});</script></body></html>")


@J.mobile_app.route("/diag/<code>/enviar", methods=["POST"])
def diag_submit(code):
    from flask import jsonify, request
    s = diag["sessions"].get(str(code))
    if not s or not s.get("abierta"):
        return jsonify({"ok": False, "msg": "El diagnóstico ya se cerró."})
    body = request.get_json(silent=True) or {}
    d = d65_data()
    dg = d["diagnosticos"].get(s["key"])
    ans = body.get("respuestas") or []
    if not dg or not isinstance(ans, list) or len(ans) != len(dg["preguntas"]):
        return jsonify({"ok": False, "msg": "No pude leer tus respuestas; vuelve a intentarlo."})
    est = vocacional.match_student(str(body.get("nombre") or "")[:80], aula.students(s["curso"]))
    if not est:
        return jsonify({"ok": False, "msg": "No encontré tu nombre en la lista del curso. Escríbelo como aparece en la lista."})
    sc = DG.score(dg["preguntas"], [None if a is None else int(a) for a in ans])
    dg["resultados"].setdefault(s["curso"], {})[est] = {"aciertos": sc["aciertos"], "total": sc["total"], "nota": sc["nota"],
                                                        "por_comp": {k: list(v) for k, v in sc["por_comp"].items()}}
    d65_save(d)
    s["n"] = s.get("n", 0) + 1
    J.socketio.emit("ticket_progress", {"tipo": "diagnostico", "n": s["n"]})
    return jsonify({"ok": True, "texto": f"¡Gracias, {est.split()[0]}! Acertaste {sc['aciertos']} de {sc['total']}. "
                                          "Con esto tu docente sabrá por dónde empezar."})


@J.app.route("/diag-qr.png")
def diag_qr():
    import qrcode
    from flask import Response, abort, request
    c = request.args.get("c", "")
    if c not in diag["sessions"]:
        abort(404)
    buf = io.BytesIO()
    qrcode.make(J._lan(f"/diag/{c}"), box_size=10, border=2).save(buf, format="PNG")
    return Response(buf.getvalue(), mimetype="image/png", headers={"Cache-Control": "no-store"})


def diag_report(key, curso):
    dg = d65_data()["diagnosticos"][key]
    res = {e: {**r, "por_comp": {k: tuple(v) for k, v in r["por_comp"].items()}} for e, r in dg["resultados"].get(curso, {}).items()}
    sm = DG.course_summary(res)
    doc = _d65_doc(f"Resultados del diagnóstico · {dg['asignatura']} · {curso}", f"{len(res)} estudiantes · {datetime.date.today():%d/%m/%Y}")
    doc.add_heading("Por competencia", 2)
    for c, pct in sorted(sm["comp"].items(), key=lambda x: x[1]):
        doc.add_paragraph(f"{c}: {pct} % del curso ({DG.level(pct / 100)})", style="List Bullet")
    doc.add_heading("Necesitan refuerzo", 2)
    for c, ests in sm["refuerzo"].items():
        doc.add_paragraph(f"{c}: " + ", ".join(sorted(ests)), style="List Bullet")
    doc.add_heading("Grupos de trabajo sugeridos (mezclan niveles)", 2)
    for i, g in enumerate(sm["grupos"], 1):
        doc.add_paragraph(f"Grupo {i}: " + ", ".join(g), style="List Bullet")
    doc.add_heading("Por estudiante", 2)
    for e, r in sorted(res.items()):
        doc.add_paragraph(f"{e}: {r['aciertos']}/{r['total']}")
    path = os.path.join(_d65_out("Diagnósticos"), _d65_safe(f"Resultados diagnóstico {dg['asignatura']} {curso}") + ".docx")
    doc.save(path)
    return sm, path


_D65_DIAG_NEW = re.compile(r"^(?:jarvis\s+)?(?:prepara|preparame|haz|hazme|crea|creame|arma)\s+(?:el|un|la|una)\s+(?:diagnostico|evaluacion diagnostica|"
                           r"prueba diagnostica)\s+de\s+(.+?)\s+(?:para|de|en)\s+(?:grado\s+)?(.+)$")
_D65_DIAG_OPEN = re.compile(r"^(?:jarvis\s+)?(?:abre|inicia|lanza|proyecta|pon)\s+(?:el|la)\s+(?:diagnostico|evaluacion diagnostica|prueba diagnostica)"
                            r"(?:\s+de\s+(.+?))?(?:\s+(?:para|en|con)\s+(\S+))?$")
_D65_DIAG_CLOSE = re.compile(r"^(?:jarvis\s+)?(?:cierra|termina|finaliza)\s+(?:el|la)\s+(?:diagnostico|evaluacion diagnostica|prueba diagnostica)$")


def _d65_diag_voice(text, t):
    m = _D65_DIAG_NEW.match(t)
    if m:
        asig = m.group(1).strip().capitalize()
        grado = _d65_grade(m.group(2))
        if not grado:
            J.reply("¿Para qué grado? Por ejemplo: «prepara el diagnóstico de matemáticas para séptimo».", "DIAGNÓSTICO")
            return True
        J.reply(f"Preparo el diagnóstico de {asig.lower()} para grado {grado}, con lo que debían dominar en {grado - 1}°…", "DIAGNÓSTICO")

        def work():
            try:
                _key, qs, path = J.diag_create(asig, grado)
            except (ValueError, J.AIError) as e:
                J.notify(f"No pude preparar el diagnóstico: {getattr(e, 'why', '') or e}.", "DIAGNÓSTICO")
                return
            J.notify(f"Listo: {len(qs)} preguntas en {len({q['competencia'] for q in qs})} competencias, con la clave. Para que lo "
                     f"respondan en el celular: «abre el diagnóstico de {asig.lower()} para {grado}A».", "DIAGNÓSTICO")
            _d65_open(path)
        J.start_job("Preparando el diagnóstico", work, "diagnostico")
        return True
    m = _D65_DIAG_OPEN.match(t)
    if m:
        d = d65_data()["diagnosticos"]
        curso = J._resolve_course(m.group(2)) if m.group(2) else aula.data.get("activo", "")
        if not curso:
            J.reply("¿Para qué curso? Por ejemplo: «abre el diagnóstico de matemáticas para 7A».", "DIAGNÓSTICO")
            return True
        g = aula.grade_of(curso)
        cands = [k for k, v in d.items() if v["grado"] == g and (not m.group(1) or DG.norm(m.group(1)) in DG.norm(v["asignatura"]))]
        if not cands:
            J.reply(f"No tengo un diagnóstico para grado {g}. Primero: «prepara el diagnóstico de matemáticas para {g}».", "DIAGNÓSTICO")
            return True
        if J._need_lan():
            return True
        key = cands[-1]
        code = secrets.token_urlsafe(5)
        diag["sessions"][code] = {"key": key, "curso": curso, "abierta": True, "n": 0, "titulo": f"{d[key]['asignatura']} · {curso}"}
        diag["last"] = code
        J._open_projector()
        J.socketio.emit("ticket", {"open": True, "url": J._lan(f"/diag/{code}"), "qr": "/diag-qr.png?c=" + code, "tipo": "diagnostico",
                                   "tema": f"Diagnóstico · {d[key]['asignatura']} · {curso}", "n": 0})
        J.reply(f"El diagnóstico de {d[key]['asignatura'].lower()} para {curso} está en el proyector: escanean el QR, escriben su "
                "nombre y responden. Al terminar: «cierra el diagnóstico».", "DIAGNÓSTICO")
        return True
    if _D65_DIAG_CLOSE.match(t):
        s = diag["sessions"].get(diag["last"])
        if not s or not s.get("abierta"):
            J.reply("No hay un diagnóstico abierto.", "DIAGNÓSTICO")
            return True
        s["abierta"] = False
        J.socketio.emit("ticket", {"open": False})
        sm, path = J.diag_report(s["key"], s["curso"])
        J.reply("Cerré el diagnóstico. " + DG.spoken(sm, s["curso"]), "DIAGNÓSTICO")
        _d65_open(path)
        return True
    return False


# ============================================================================ 5. DIPLOMAS Y MENCIONES
def _d65_diploma_page(doc, nombre, motivo, curso, puesto=""):
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, RGBColor
    inst = J.settings.get("aula_institucion", "").strip() or "Institución Educativa"

    def line(txt, size, bold=False, color=None, italic=False, space=10):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(space)
        r = p.add_run(txt)
        r.font.size, r.bold, r.italic = Pt(size), bold, italic
        if color:
            r.font.color.rgb = RGBColor(*color)
    line(inst.upper(), 18, True, (0x1F, 0x3A, 0x60))
    line("otorga el presente", 13, italic=True)
    line("DIPLOMA DE HONOR" if not puesto else f"DIPLOMA · {puesto.upper()}", 30, True, (0xB8, 0x86, 0x0B), space=14)
    line("a", 13, italic=True)
    line(nombre, 28, True, (0x1F, 0x3A, 0x60), space=12)
    line(f"del curso {curso}, {motivo}," if curso else f"{motivo},", 15)
    line(f"durante el año escolar {datetime.date.today().year}.", 15, space=40)
    line("______________________________                    ______________________________", 12, space=2)
    doc_name = J.settings.get("aula_docente", "").strip() or "Docente"
    line(f"Rector(a)                                                              {doc_name}", 11)


def diplomas_make(items, title):
    """items: [(nombre, motivo, curso, puesto)]. → ruta del Word (un diploma por página, horizontal)."""
    from docx.enum.section import WD_ORIENT
    from docx.shared import Cm
    doc = J.Document()
    sec = doc.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE
    sec.page_width, sec.page_height = sec.page_height, sec.page_width
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, side, Cm(2))
    for i, (n, mot, c, p) in enumerate(items):
        if i:
            doc.add_page_break()
        _d65_diploma_page(doc, n, mot, c, p)
    path = os.path.join(_d65_out("Diplomas"), _d65_safe(title) + ".docx")
    doc.save(path)
    return path


def diploma_top_items(cursos, n=3):
    items, empty = [], []
    for c in cursos:
        avgs = {e: seguimiento.average(c, e) for e in seguimiento.data.get(c, {})}
        top = CL.top_students(avgs, n)
        if not top:
            empty.append(c)
        for i, (e, a) in enumerate(top):
            pos = sorted({x for _y, x in top}, reverse=True).index(a)
            items.append((e, f"por su excelencia académica (promedio {str(round(a, 1)).replace('.', ',')})", c, CL.PUESTOS[min(pos, 2)]))
    return items, empty


_D65_DIPL_TOP = re.compile(r"^(?:jarvis\s+)?(?:haz|hazme|crea|prepara|genera|arma)\s+(?:los\s+)?diplomas\s+(?:de\s+(?:los\s+)?(?:mejores|primeros puestos|"
                           r"mejores promedios)(?:\s+de\s+(?:cada|todos los)\s+cursos?)?|de\s+(\S+))(?:\s+de\s+(\S+))?$")
_D65_DIPL_ONE = re.compile(r"^(?:jarvis\s+)?(?:haz|hazme|crea|prepara|genera)\s+(?:un|el)\s+(?:diploma|mencion(?: de honor)?|reconocimiento)\s+"
                           r"(?:para|a)\s+(.+?)(?:\s+(?:de|del curso)\s+(\d{1,2}\s?[a-z]?\b|\d{1,2}-\d))?(\s+por\s+.+)?$")


def _d65_diploma_voice(text, t):
    m = _D65_DIPL_TOP.match(t)
    if m:
        spoken = m.group(1) or m.group(2)
        cursos = [J._resolve_course(spoken)] if spoken else sorted(seguimiento.data)
        cursos = [c for c in cursos if c]
        if not cursos:
            J.reply("Aún no tengo notas registradas para escoger a los mejores. Puedo hacer uno a mano: «diploma para Sofía Gómez de "
                    "9A por su liderazgo».", "DIPLOMAS")
            return True
        items, empty = diploma_top_items(cursos)
        if not items:
            J.reply("Nadie llega a 4,0 de promedio en esos cursos con las notas que tengo. Puedo hacerlos a mano: «diploma para …».", "DIPLOMAS")
            return True
        path = diplomas_make(items, f"Diplomas {'-'.join(cursos)[:40]} {datetime.date.today().year}")
        J.reply(f"Listos {len(items)} diplomas de los mejores promedios de {len(cursos) - len(empty)} cursos (con empates incluidos), "
                "uno por página, para imprimir. Revisa los nombres antes de imprimir." +
                (f" En {', '.join(empty)} nadie llega a 4,0." if empty else ""), "DIPLOMAS")
        _d65_open(path)
        return True
    m = _D65_DIPL_ONE.match(t)
    if m:
        name_norm = m.group(1).strip()
        raw = re.search(r"(?i)(?:para|a)\s+(.+?)(?:\s+(?:de|del curso)\s+\d{1,2}\s?[a-zA-Z]?\b|\s+por\s+|$)", text)
        name = (raw.group(1).strip() if raw else name_norm).strip(" .").title()
        curso = J._resolve_course(m.group(2)) if m.group(2) else ""
        motivo = CL.motivo_of(m.group(3) or "")
        path = diplomas_make([(name, motivo, curso or (m.group(2) or "").upper(), "")], f"Diploma {name}")
        J.reply(f"Listo el diploma de {name} {motivo}.", "DIPLOMAS")
        _d65_open(path)
        return True
    return False


# ============================================================================ 6. RENTA
_D65_MONEY = r"(\d+(?:[.,]\d+)?)\s*(millones|millon|mill|m|mil)?(?:\s+de pesos)?"


def renta_parse(t):
    """«gano 4,5 millones al mes», «tengo una casa de 200 millones» → {clave: pesos}."""
    def amount(n, unit):
        v = float(n.replace(".", "").replace(",", ".")) if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", n) else float(n.replace(",", "."))
        return v * (1_000_000 if unit and unit.startswith("mill") or unit == "m" else 1000 if unit == "mil" else 1)
    out = {}
    m = re.search(rf"\b(?:gano|me pagan|salario de|sueldo de|ingresos? de|recibo)\s+{_D65_MONEY}(\s+(?:al|por|cada)\s+mes|\s+mensual(?:es)?)?", t)
    if m:
        v = amount(m.group(1), m.group(2))
        out["ingresos"] = v * 13 if m.group(3) else v          # al mes: 12 sueldos + la prima (aprox.)
    m = re.search(rf"\b(?:patrimonio|tengo (?:una casa|un apartamento|bienes|ahorros|un carro)[^\d]{{0,20}})\s*(?:de\s+)?{_D65_MONEY}", t)
    if m:
        out["patrimonio"] = amount(m.group(1), m.group(2))
    m = re.search(rf"\b(?:con la tarjeta|tarjeta de credito)[^\d]{{0,20}}{_D65_MONEY}", t)
    if m:
        out["tarjeta"] = amount(m.group(1), m.group(2))
    return out


def renta_reply(year, valores, extra=""):
    res = RT.check(year, valores)
    msg = RT.spoken(year, res)
    if res["obliga"] is not False:
        msg += " Para pagar menos, puedes restar: " + "; ".join(RT.DEDUCCIONES[:4]) + "."
    return (extra + msg + " Te dejé la lista de papeles en el panel. Es una orientación con los topes de la DIAN; para "
            "hacer la declaración, consulta con un contador o usa el servicio de la DIAN.")


def renta_from_items(its):
    cert = J.ask_files(its, RT.certificado_prompt())
    m = re.search(r"\{.*\}", cert or "", re.S)
    d = json.loads(m.group(0)) if m else {}
    year = int(d.get("ano") or datetime.date.today().year - 1)
    vals = {}
    if d.get("ingresos"):
        vals["ingresos"] = float(d["ingresos"])
    extra = (f"En el certificado{' de ' + d['entidad'] if d.get('entidad') else ''} del año {year} veo ingresos por "
             f"{RT.pesos(vals['ingresos'])}" + (f" y retención de {RT.pesos(float(d['retencion']))}" if d.get("retencion") else "") + ". "
             if vals else "No encontré los ingresos en el certificado. ")
    return renta_reply(year, vals, extra)


_D65_RENTA = re.compile(r"\b(?:debo|tengo que|me toca|estoy obligad[oa] a)\s+declarar(?:\s+la)?\s+renta\b|\bme toca declarar\b|"
                        r"\bdeclarar renta\b.*\?$|^(?:jarvis\s+)?(?:quienes|quien) (?:debe|deben) declarar renta")


def _d65_renta_voice(text, t):
    if not _D65_RENTA.search(t):
        return False
    vals = renta_parse(t)
    year = datetime.date.today().year if datetime.date.today().month >= 11 else datetime.date.today().year - 1
    m = re.search(r"\b(?:por el|del|en el|ano gravable)\s+(20\d{2})\b", t)
    if m:
        year = int(m.group(1))
    J.card("tip", f"Para la renta del año {year}", "", "🧾", secs=30,
           steps=[f"Papeles: {p}" for p in RT.PAPELES] + [f"Puedes restar: {x}" for x in RT.DEDUCCIONES])
    it = _d65_recent(("pdf", "imagen"))
    if not vals and it and re.search(r"certificad|ingresos|retenci|220", J.normalize(it["nombre"])):
        J.reply(f"Leo «{it['nombre']}»…", "RENTA")
        J.start_job("Revisando la renta", lambda: J.notify(J.renta_from_items([it]), "RENTA"), "renta")
        return True
    if not vals:
        tp = RT.topes(year) or RT.topes(max(RT.UVT))
        J.reply(f"Para el año {year} (se declara en {year + 1}) estás obligado si pasas uno de estos topes: ingresos de "
                f"{RT.pesos(tp[0][1])} o más, patrimonio de más de {RT.pesos(tp[1][1])}, o consumos con tarjeta, compras o "
                f"consignaciones de más de {RT.pesos(tp[2][1])}. Dime «¿debo declarar renta? gano 4 millones al mes» o súbeme el "
                "certificado de ingresos y retenciones.", "RENTA")
        return True
    J.reply(renta_reply(year, vals, "Contando 12 sueldos y la prima. " if "ingresos" in vals and re.search(r"al mes|mensual|por mes", t) else ""), "RENTA")
    return True


# ============================================================================ 7. SALIDAS PEDAGÓGICAS
_D65_SALIDA = re.compile(r"^(?:jarvis\s+)?(?:planea|planeame|organiza|prepara|preparame|arma)\s+(?:una|la)\s+(?:salida(?: pedagogica)?|excursion|visita)\s+"
                         r"(?:a|al|a la)\s+(.+?)\s+(?:con|para)\s+(?:el curso\s+|los de\s+)?(\d{1,2}\s?[a-z]\b|\d{1,2}-\d)(?:\s+(?:el|para el)\s+(.+))?$")
_D65_AUT_OK = re.compile(r"^(?:jarvis\s+)?(.+?)\s+(?:ya\s+)?(?:entrego|trajo|devolvio)\s+(?:la\s+)?(?:autorizacion|permiso)$")
_D65_AUT_MISS = re.compile(r"\b(?:quien|quienes) (?:no ha|no han|falta[n]? por|faltan de) (?:entregado|traido|entregar|traer)\s+(?:la\s+)?(?:autorizacion|permiso)")


def salida_make(lugar, curso, fecha_txt):
    plan = J.ai_chat([{"role": "user", "content": CL.salida_prompt(lugar, curso, fecha_txt)}], max_tokens=2500)
    doc = _d65_doc(f"Salida pedagógica · {lugar}", f"Curso {curso} · {fecha_txt or 'fecha por definir'} · Docente: {J.settings.get('aula_docente', '') or '________'}")
    _d65_text_doc(doc, plan)
    doc.add_heading("Lista de chequeo antes de la salida", 2)
    doc.add_paragraph(f"Según la {CL.SALIDA_NORMA} y lo que pida tu secretaría de educación:")
    for x in CL.SALIDA_CHECK:
        doc.add_paragraph("☐ " + x)
    ests = aula.students(curso)
    for e in ests or ["______________________________"]:
        doc.add_page_break()
        doc.add_heading("Autorización para salida pedagógica", 1)
        txt = CL.autorizacion_text(J.settings.get("aula_institucion", ""), lugar, curso, fecha_txt, docente=J.settings.get("aula_docente", ""))
        doc.add_paragraph(txt.replace("estudiante ______________________________", f"estudiante {e}") if ests else txt)
        doc.add_paragraph("EPS: ____________  Alergias o medicamentos: ______________________________")
        doc.add_paragraph("Teléfono del acudiente: ______________   Contacto de emergencia: ______________")
        doc.add_paragraph("\nFirma del acudiente: ______________________________    Fecha: ____________")
    path = os.path.join(_d65_out("Salidas pedagógicas"), _d65_safe(f"Salida {lugar} {curso}") + ".docx")
    doc.save(path)
    d = d65_data()
    d["salidas"][curso] = {"lugar": lugar, "fecha": fecha_txt, "estudiantes": ests, "entregadas": [], "creada": str(datetime.date.today())}
    d65_save(d)
    return path, len(ests)


def _d65_salida_voice(text, t):
    m = _D65_SALIDA.match(t)
    if m:
        curso = J._resolve_course(m.group(2)) or m.group(2).upper().replace(" ", "")
        lugar = m.group(1).strip()
        raw = re.search(r"(?i)\b(?:a|al|a la)\s+(.+?)\s+(?:con|para)\s+", text)
        lugar = raw.group(1).strip() if raw else lugar
        fecha = (m.group(3) or "").strip()
        J.reply(f"Planeo la salida a {lugar} con {curso}: plan pedagógico, lista de chequeo y una autorización por estudiante…", "SALIDAS")

        def work():
            try:
                path, n = J.salida_make(lugar, curso, fecha)
            except J.AIError as e:
                J.notify(J.ai_error_reply(e), "SALIDAS")
                return
            J.notify(f"Listo el Word de la salida: plan, lista de chequeo (Directiva 55 de 2014) y {n or 'un formato de'} "
                     f"autorizaci{'ones' if n != 1 else 'ón'}. Cuando las entreguen: «Juan entregó la autorización»; y «¿quién no ha "
                     "entregado la autorización?».", "SALIDAS")
            _d65_open(path)
        J.start_job("Planeando la salida", work, "salida")
        return True
    if _D65_AUT_MISS.search(t):
        d = d65_data()["salidas"]
        if not d:
            J.reply("No tengo salidas planeadas. Di «planea una salida al museo con 9A».", "SALIDAS")
            return True
        curso, s = max(d.items(), key=lambda kv: kv[1]["creada"])
        falta = [e for e in s["estudiantes"] if e not in s["entregadas"]]
        J.reply(f"Para la salida a {s['lugar']} con {curso}: " + (f"faltan {len(falta)}: " + ", ".join(falta[:15]) + "." if falta else
                "ya entregaron todos.") if s["estudiantes"] else "no tengo la lista de ese curso.", "SALIDAS")
        return True
    m = _D65_AUT_OK.match(t)
    if m:
        d = d65_data()
        if not d["salidas"]:
            return False
        curso, s = max(d["salidas"].items(), key=lambda kv: kv[1]["creada"])
        est = vocacional.match_student(m.group(1), s["estudiantes"]) if s["estudiantes"] else ""
        if not est or est not in s["estudiantes"]:
            J.reply(f"No encontré a «{m.group(1)}» en la lista de {curso}.", "SALIDAS")
            return True
        if est not in s["entregadas"]:
            s["entregadas"].append(est)
            d65_save(d)
        falta = len(s["estudiantes"]) - len(s["entregadas"])
        J.reply(f"Anotado: {est} entregó la autorización. " + (f"Faltan {falta}." if falta else "¡Ya están todas!"), "SALIDAS")
        return True
    return False


# ============================================================================ 8. PROYECTOS TRANSVERSALES
_D65_PROY_NEW = re.compile(r"^(?:jarvis\s+)?(?:formula|formulame|haz|hazme|crea|prepara|preparame|arma|escribe)\s+(?:el|un)\s+proyecto\s+(?:transversal\s+)?(?:de\s+)?(.+)$")
_D65_PROY_EV = re.compile(r"^(?:jarvis\s+)?(?:evidencia|anota (?:una )?evidencia|registra (?:una )?evidencia)\s+(?:del|de la|de|para el)\s+(?:proyecto\s+)?(.+?)\s*[:,]\s*(.+)$")
_D65_PROY_INF = re.compile(r"^(?:jarvis\s+)?(?:haz|hazme|prepara|preparame|escribe)?\s*(?:el\s+)?informe(?: final)?\s+(?:del|de la|de)\s+(?:proyecto\s+)?(.+)$")


def proyecto_make(key, contexto=""):
    name, norma = CL.PROYECTOS[key]
    txt = J.ai_chat([{"role": "user", "content": CL.proyecto_prompt(key, J.settings.get("aula_institucion", ""), contexto)}], max_tokens=4000)
    doc = _d65_doc(name, f"{norma} · {datetime.date.today().year}")
    _d65_text_doc(doc, txt)
    path = os.path.join(_d65_out("Proyectos transversales"), _d65_safe(f"{name} {datetime.date.today().year}") + ".docx")
    doc.save(path)
    d = d65_data()
    d["proyectos"].setdefault(key, {"evidencias": []})
    d65_save(d)
    return path


def _d65_proy_voice(text, t):
    m = _D65_PROY_EV.match(t)
    if m and CL.proyecto_of(m.group(1)):
        key = CL.proyecto_of(m.group(1))
        raw = re.split(r"\s*[:,]\s*", text, maxsplit=1)
        ev = raw[1].strip() if len(raw) > 1 else m.group(2)
        d = d65_data()
        d["proyectos"].setdefault(key, {"evidencias": []})["evidencias"].append({"fecha": str(datetime.date.today()), "texto": ev[:500]})
        d65_save(d)
        J.reply(f"Anotada la evidencia del proyecto {CL.PROYECTOS[key][0].lower()} "
                f"({len(d['proyectos'][key]['evidencias'])} en total). Si tienes fotos, súbelas y guárdalas en la carpeta del proyecto.", "PROYECTOS")
        return True
    m = _D65_PROY_INF.match(t)
    if m and CL.proyecto_of(m.group(1)):
        key = CL.proyecto_of(m.group(1))
        evs = d65_data()["proyectos"].get(key, {}).get("evidencias", [])
        if not evs:
            J.reply("Aún no tengo evidencias de ese proyecto. Dímelas así: «evidencia del PRAE: jornada de reciclaje con sexto».", "PROYECTOS")
            return True

        def work():
            try:
                txt = J.ai_chat([{"role": "user", "content": CL.informe_prompt(key, evs)}], max_tokens=3000)
            except J.AIError as e:
                J.notify(J.ai_error_reply(e), "PROYECTOS")
                return
            doc = _d65_doc(f"Informe final · {CL.PROYECTOS[key][0]}", f"{len(evs)} evidencias · {datetime.date.today():%d/%m/%Y}")
            _d65_text_doc(doc, txt)
            path = os.path.join(_d65_out("Proyectos transversales"), _d65_safe(f"Informe {CL.PROYECTOS[key][0]} {datetime.date.today().year}") + ".docx")
            doc.save(path)
            J.notify(f"Listo el informe final con {len(evs)} evidencias.", "PROYECTOS")
            _d65_open(path)
        J.reply("Escribo el informe final con las evidencias del año…", "PROYECTOS")
        J.start_job("Informe del proyecto", work, "proyecto")
        return True
    m = _D65_PROY_NEW.match(t)
    if m and CL.proyecto_of(m.group(1)):
        key = CL.proyecto_of(m.group(1))
        J.reply(f"Formulo el proyecto «{CL.PROYECTOS[key][0]}» con su marco legal, cronograma de febrero a noviembre e indicadores…", "PROYECTOS")

        def work():
            try:
                path = J.proyecto_make(key)
            except J.AIError as e:
                J.notify(J.ai_error_reply(e), "PROYECTOS")
                return
            J.notify("Listo el proyecto. Durante el año dime las evidencias («evidencia del proyecto ambiental: …») y al final "
                     "«informe final del proyecto ambiental».", "PROYECTOS")
            _d65_open(path)
        J.start_job("Formulando el proyecto", work, "proyecto")
        return True
    return False


# ============================================================================ 9. CRONOGRAMA DE EVALUACIONES
_D65_CRON = re.compile(r"^(?:jarvis\s+)?(?:organiza|programa|reparte|haz|hazme|arma)\s+(?:el cronograma de\s+)?(?:las\s+|los\s+|mis\s+)?"
                       r"(?:examenes|evaluaciones|pruebas|quices)(?:\s+del\s+\w+\s+periodo)?(?:\s+(?:de|en|para)\s+(?:las|la)\s+(?:proximas?|siguientes?)\s+"
                       r"(\d|una|dos|tres|cuatro)\s+semanas?)?(?:\s+desde\s+el\s+(\d{1,2})\s+de\s+(\w+))?$")
_D65_MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def cronograma_make(start, weeks):
    slots = [(x["curso"], x["materia"] or "Clase", x["dia"]) for x in horario.items if x.get("curso") and x["dia"] < 5]
    hol = set()
    for y in {start.year, (start + datetime.timedelta(weeks=weeks)).year}:
        hol |= set(festivos.holidays(y))
    plan, missing = CL.schedule(slots, start, weeks, 2, hol)
    doc = _d65_doc("Cronograma de evaluaciones", f"Del {start:%d/%m} por {weeks} semana{'s' if weeks != 1 else ''}")
    tb = doc.add_table(rows=1, cols=3)
    tb.style = "Table Grid"
    for c, h in zip(tb.rows[0].cells, ("Fecha", "Curso", "Asignatura")):
        c.text = h
    for x in plan:
        r = tb.add_row().cells
        r[0].text, r[1].text, r[2].text = f"{CL.DAYS[x['fecha'].weekday()].capitalize()} {x['fecha']:%d/%m}", x["curso"], x["asignatura"]
    path = os.path.join(_d65_out("Cronogramas"), _d65_safe(f"Cronograma evaluaciones {start:%Y-%m-%d}") + ".docx")
    doc.save(path)
    d = d65_data()
    d["cronograma"] = [{"fecha": str(x["fecha"]), "curso": x["curso"], "asignatura": x["asignatura"], "avisado": False} for x in plan]
    d65_save(d)
    return plan, missing, path


def _d65_cron_voice(text, t):
    m = _D65_CRON.match(t)
    if not m:
        return False
    if not horario.items:
        J.reply("Para repartir las evaluaciones necesito tu horario: escríbelo en Ajustes › Aula y colegio › Horario.", "CRONOGRAMA")
        return True
    weeks = {"una": 1, "dos": 2, "tres": 3, "cuatro": 4}.get(m.group(1) or "", int(m.group(1)) if (m.group(1) or "").isdigit() else 2)
    today = datetime.date.today()
    start = today + datetime.timedelta(days=(7 - today.weekday()) % 7 or 7)
    if m.group(2) and m.group(3) in _D65_MONTHS:
        mo = _D65_MONTHS.index(m.group(3)) + 1
        start = datetime.date(today.year + (mo < today.month), mo, int(m.group(2)))
    plan, missing, path = cronograma_make(start, weeks)
    J.reply(f"Repartí {len(plan)} evaluaciones en {weeks} semana{'s' if weeks != 1 else ''} desde el {start:%d/%m}: ningún curso tiene dos "
            "el mismo día y tú no tienes más de dos por día para calificar." +
            (f" No me cupieron: {', '.join(f'{c} {a}' for c, a in missing)}." if missing else "") +
            " Te aviso la víspera de cada una.", "CRONOGRAMA")
    _d65_open(path)
    return True


def docente65_tick(now=None):
    """La víspera de cada evaluación, después de las 3 de la tarde, avisa una vez."""
    now = now or datetime.datetime.now()
    if now.hour < 15:
        return
    d = d65_data()
    tomorrow = str((now + datetime.timedelta(days=1)).date())
    due = [x for x in d["cronograma"] if x["fecha"] == tomorrow and not x["avisado"]]
    if not due:
        return
    for x in due:
        x["avisado"] = True
    d65_save(d)
    J.notify("Mañana evalúas: " + "; ".join(f"{x['curso']} {x['asignatura']}" for x in due) + ".", "CRONOGRAMA")


# ============================================================================ BOTONES AL SUBIR Y VOZ
def d65_card_actions(its):
    if len(its) != 1:
        return []
    k = its[0]["tipo"]
    acts = []
    if k in ("imagen", "texto"):
        acts.append("estafa")
    if k in ("pdf", "word"):
        acts.append("contrato")
    if k == "video":
        acts.append("exposicion")
    if k in ("pdf", "imagen") and re.search(r"certificad|ingresos|retenci|220|renta", J.normalize(its[0]["nombre"])):
        acts.append("renta")
    return [{"a": a, "t": D65_ACTIONS[a]} for a in acts]


def d65_attach(its, action, pregunta=""):
    if action == "estafa":
        J.notify(J.scam_check_items(its), "ESTAFAS")
    elif action == "contrato":
        J.notify(J.contract_check(its), "CONTRATOS")
    elif action == "exposicion":
        J.notify("Veo la exposición con Gemini y la califico con la rúbrica; tarda unos minutos.", "EXPOSICIÓN")
        _d65_expo_start(its[0])
    elif action == "renta":
        J.notify(J.renta_from_items(its), "RENTA")
    return None


def docente65_voice(text, t):
    for fn in (_d65_scam_voice, _d65_contract_voice, _d65_expo_voice, _d65_diag_voice, _d65_diploma_voice, _d65_renta_voice,
               _d65_salida_voice, _d65_proy_voice, _d65_cron_voice):
        if fn(text, t):
            return True
    return False


__all__ = ['D65_ACTIONS', '_D65_AUT_MISS', '_D65_AUT_OK', '_D65_CONTRACT', '_D65_CRON', '_D65_DIAG_CLOSE', '_D65_DIAG_NEW', '_D65_DIAG_OPEN',
           '_D65_DIPL_ONE', '_D65_DIPL_TOP', '_D65_EXPO', '_D65_GRADE_WORDS', '_D65_MONEY', '_D65_MONTHS', '_D65_PROY_EV', '_D65_PROY_INF',
           '_D65_PROY_NEW', '_D65_RENTA', '_D65_SALIDA', '_D65_SCAM', '_d65_contract_voice', '_d65_cron_voice', '_d65_diag_voice',
           '_d65_diploma_page', '_d65_diploma_voice', '_d65_doc', '_d65_expo_start', '_d65_expo_voice', '_d65_grade', '_d65_lock',
           '_d65_open', '_d65_out', '_d65_path', '_d65_proy_voice', '_d65_recent', '_d65_renta_voice', '_d65_safe', '_d65_salida_voice',
           '_d65_scam_voice', '_d65_small_video', '_d65_text_doc', 'contract_check', 'cronograma_make', 'd65_attach', 'd65_card_actions',
           'd65_data', 'd65_save', 'diag', 'diag_create', 'diag_page', 'diag_qr', 'diag_report', 'diag_submit', 'diploma_top_items',
           'diplomas_make', 'docente65_tick', 'docente65_voice', 'expo_evaluate', 'proyecto_make', 'renta_from_items', 'renta_parse',
           'renta_reply', 'salida_make', 'scam_check_items', 'scam_check_text']
