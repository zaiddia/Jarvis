"""12.53: documentos del colegio con respuesta y página, asistente de convivencia (Ley 1620), portafolio de evidencias y
reglas automáticas «si pasa esto, haz aquello».

    «guarda este documento como documento del colegio» (con el PEI, SIEE o manual subido al chat)
    «¿qué dice el SIEE sobre las recuperaciones?» · «según el manual de convivencia, ¿cuántas fallas se permiten?»
    «registra una situación de convivencia: en el descanso Juan empujó a Pedro…»
    «arma mi portafolio de evidencias del año»
    «si alguien saca menos de 3 en un quiz, prepárale un refuerzo y avísame» · «¿qué reglas tengo?» · «borra la regla 1»

La lógica está en convivencia.py, portafolio.py y reglas.py (y libro.py para los documentos). Los nombres globales de
Jarvis se usan como J.<nombre>.
"""
import datetime
import json
import os
import re
import shutil
import threading
import time
import zipfile

import adjuntos
import aula
import confianza
import convivencia as CV
import libro
import portafolio as PF
import reglas as RG
import seguimiento
from nucleo import J

INST = "Institucional"

# ============================================================================ 4. DOCUMENTOS DEL COLEGIO
def inst_docs():
    return {k: v for k, v in libro.index["libros"].items() if v.get("asignatura") == INST}


def inst_add(its):
    """Guarda los archivos subidos como documentos del colegio. → [(nombre, páginas)]."""
    out = []
    for it in its:
        with open(it["ruta"], "rb") as f:
            raw = f.read()
        pages = libro.extract(raw, it["nombre"])
        libro.add_book(it["nombre"].rsplit(".", 1)[0], INST, pages, it["nombre"])
        out.append((it["nombre"].rsplit(".", 1)[0], len(pages)))
    return out


_DOCS = {"siee": r"siee|sistema institucional de evaluacion|evaluacion", "manual": r"manual|convivencia", "pei": r"\bpei\b|proyecto educativo"}


def inst_search(question, k=5):
    want = next((rx for key, rx in _DOCS.items() if re.search(r"\b" + key, J.normalize(question))), "")
    hits = [h for h in libro.search(question, INST, k=12)]
    if want:
        pref = [h for h in hits if re.search(want, J.normalize(h["libro"]))]
        hits = pref or hits
    return hits[:k]


def inst_answer(question):
    hits = inst_search(question)
    if not hits:
        return "No encontré eso en los documentos del colegio que me diste."
    body = "\n\n".join(f"[{h['libro']}, pág. {h['pagina']}]\n{h['texto'][:1800]}" for h in hits)
    return J.ai_chat([{"role": "user", "content":
                       "Responde la pregunta del docente SOLO con lo que dicen estos fragmentos de los documentos de su colegio. "
                       "Cita el documento y la página entre paréntesis después de cada dato, por ejemplo (SIEE, pág. 12). "
                       "Si los fragmentos no lo dicen, responde que no está en los documentos. Español claro, sin markdown.\n\n"
                       + confianza.wrap(body, "DOCUMENTOS DEL COLEGIO") + confianza.RULE + f"\n\nPregunta: {question}"}],
                     max_tokens=900).strip()


_INST_SAVE = re.compile(r"\b(?:guarda|agrega|anade|sube|usa)(?:me|lo|la|los|las)?\s+(?:este|esta|estos|estas|el|los)?\s*(?:documentos?|archivos?|pdfs?|manual|siee|pei)?"
                        r"\s*(?:como|a)\s+(?:los\s+)?documentos? (?:del|de mi) colegio\b|"
                        r"^(?:jarvis\s+)?(?:este|esto) es (?:el|nuestro|mi) (?:manual de convivencia|siee|pei|proyecto educativo)\b")
_INST_ASK = re.compile(r"\b(?:que dice|que dicen|segun|busca en|consulta en|que establece|que contempla)\s+(?:el|la|los|las|nuestro|mi)?\s*"
                       r"(siee|manual de convivencia|manual|pei|proyecto educativo institucional|documentos? del colegio|reglamento)\b(.*)$")
_INST_LIST = re.compile(r"\bque documentos del colegio (?:tienes|tengo|guardaste)\b|\bmis documentos del colegio\b")


def inst_voice(text, t):
    if _INST_LIST.search(t):
        d = inst_docs()
        J.reply(("Tengo: " + "; ".join(f"{v['nombre']} ({v['paginas']} págs.)" for v in d.values()) + ".") if d else
                "Aún no me has dado documentos del colegio. Sube el PEI, el SIEE o el manual al chat y dime «guárdalos como documentos del colegio».",
                "COLEGIO")
        return True
    if _INST_SAVE.search(t):
        its = [i for i in J._upload_batch(10) if i["tipo"] in ("pdf", "word", "texto")]
        if not its:
            J.reply("Sube primero el documento (PDF o Word) al chat y luego dime «guárdalo como documento del colegio».", "COLEGIO")
            return True
        try:
            added = inst_add(its)
        except ValueError as e:
            J.reply(f"No pude guardarlo: {e}.", "COLEGIO")
            return True
        J.reply("Guardé " + "; ".join(f"«{n}» ({p} págs.)" for n, p in added) + ". Ya puedes preguntarme, por ejemplo, «¿qué dice el SIEE "
                "sobre las recuperaciones?». Solo uso estos documentos que me diste.", "COLEGIO")
        return True
    m = _INST_ASK.search(t)
    if not m or (not inst_docs() and "documento" not in m.group(1) and m.group(1) not in ("siee", "manual de convivencia", "pei")):
        return False
    if not inst_docs():
        J.reply("Aún no tengo los documentos del colegio. Sube el PEI, el SIEE o el manual de convivencia al chat y dime "
                "«guárdalos como documentos del colegio».", "COLEGIO")
        return True
    if J.state.get("ai") != "ok":
        hits = inst_search(text)
        J.reply(("Esto es lo que encontré: " + " … ".join(f"({h['libro']}, pág. {h['pagina']}) {h['texto'][:220]}" for h in hits[:2]))
                if hits else "No lo encontré en los documentos del colegio.", "COLEGIO")
        return True
    J.reply(inst_answer(text), "COLEGIO")
    return True


# ============================================================================ 1. CONVIVENCIA ESCOLAR
cv_state = {"busy": False}


def convivencia_case(relato, curso=""):
    manual = ""
    hits = [h for h in libro.search(relato, INST, k=8) if re.search(r"manual|convivencia", J.normalize(h["libro"]))][:4]
    if hits:
        manual = "\n\n".join(f"[{h['libro']}, pág. {h['pagina']}] {h['texto'][:1400]}" for h in hits)
    raw = J.ai_chat([{"role": "user", "content": CV.prompt(relato, manual, curso)}], json_mode=True, max_tokens=2600)
    a = CV.clean(J._extract_json(raw), relato)
    return a, _cv_docx(a, relato, curso)


def _cv_docx(a, relato, curso):
    import docx
    doc = docx.Document()
    doc.add_heading("Registro de situación de convivencia escolar", 0)
    doc.add_paragraph(f"Fecha: {datetime.date.today().strftime('%d/%m/%Y')}" + (f" · Curso: {curso}" if curso else "")
                      + f" · Clasificación sugerida: tipo {a['tipo']}" if a["tipo"] != "sin clasificar" else
                      f"Fecha: {datetime.date.today().strftime('%d/%m/%Y')} · Clasificación: pendiente (faltan datos)")
    p = doc.add_paragraph()
    p.add_run("Documento de apoyo generado con Jarvis. La clasificación y las decisiones corresponden al comité escolar de "
              "convivencia y a coordinación, según el manual de convivencia del colegio. Información confidencial.").italic = True
    if a["urgente"]:
        doc.add_paragraph().add_run(CV.URGENT_TEXT).bold = True
    doc.add_heading("Por qué", 1)
    doc.add_paragraph(a["por_que"] or "—")
    doc.add_heading("Pasos del protocolo", 1)
    for s in a["pasos"]:
        doc.add_paragraph(s, style="List Number")
    if a["informar_a"]:
        doc.add_heading("A quién informar", 1)
        for s in a["informar_a"]:
            doc.add_paragraph(s, style="List Bullet")
    if a["faltan_datos"]:
        doc.add_heading("Datos que faltan", 1)
        for s in a["faltan_datos"]:
            doc.add_paragraph(s, style="List Bullet")
    doc.add_heading("Registro", 1)
    for k, lab in (("hechos", "Descripción de los hechos"), ("involucrados", "Involucrados"), ("acciones", "Acciones realizadas"),
                   ("compromisos", "Compromisos")):
        doc.add_paragraph().add_run(lab + ": ").bold = True
        doc.add_paragraph(a["registro"][k] or "_" * 60)
    doc.add_paragraph("\nFirma docente: ______________________    Firma coordinación: ______________________")
    doc.add_paragraph("Firma estudiante(s): __________________    Firma acudiente(s): ______________________")
    if a["citacion"]:
        doc.add_page_break()
        doc.add_heading("Citación al acudiente", 1)
        doc.add_paragraph(a["citacion"])
    doc.add_heading("Relato original del docente", 2)
    doc.add_paragraph(relato)
    if a["fuentes"]:
        doc.add_paragraph("Fuentes: " + "; ".join(a["fuentes"]))
    out = os.path.join(J.settings["output_dir"], "Convivencia")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, f"Situación {time.strftime('%Y-%m-%d %H%M')}{' ' + curso.replace('/', '-') if curso else ''}.docx")
    doc.save(path)
    return path


_CV = re.compile(r"^(?:jarvis\s*,?\s+)?(?:registra|registrame|anota|analiza|reporta|revisa)\s+(?:una|esta|la)\s+situacion de convivencia\s*[:,.]?\s*(.*)$|"
                 r"^(?:jarvis\s*,?\s+)?situacion de convivencia\s*[:,.]\s*(.+)$|"
                 r"\b(?:que protocolo (?:aplico|sigo|activo)|que ruta de atencion (?:aplico|sigo|activo)|ruta de atencion para)\s*(?:si|cuando|para)?\s*(.+)$")


def convivencia_voice(text, t):
    m = _CV.search(t)
    if not m:
        return False
    relato_t = next((g for g in m.groups() if g), "").strip()
    raw = re.split(r"convivencia\s*[:,.]|protocolo \w+|ruta de atenci[oó]n \w+", text, maxsplit=1, flags=re.I)
    relato = (raw[1] if len(raw) > 1 else relato_t).strip(" :,.") or relato_t
    if len(relato.split()) < 5:
        J.reply("Cuéntame qué pasó: quiénes, dónde, qué hicieron, si hubo daño o si se ha repetido. Por ejemplo: «situación de "
                "convivencia: en el descanso Juan empujó a Pedro y se golpeó la rodilla; es la tercera vez esta semana».", "CONVIVENCIA")
        return True
    if CV.URGENT.search(relato):
        J.reply(CV.URGENT_TEXT, "CONVIVENCIA")
    if J.state.get("ai") != "ok":
        J.reply("Para analizar la situación necesito la IA conectada. Mientras tanto: avisa a coordinación y deja por escrito lo que pasó.",
                "CONVIVENCIA")
        return True
    if cv_state["busy"]:
        J.reply("Estoy analizando otra situación; te aviso enseguida.", "CONVIVENCIA")
        return True
    cm = re.search(r"\b(?:de|del|en)\s+(\d{1,2}\s?[a-z])\b", t)
    curso = (J._resolve_course(cm.group(1)) or "") if cm else ""
    cv_state["busy"] = True
    J.reply("Analizo la situación con la Ley 1620" + (" y tu manual de convivencia" if inst_docs() else "") + "…", "CONVIVENCIA")

    def work():
        try:
            a, path = convivencia_case(relato, curso)
        except J.AIError as e:
            J.notify(J.ai_error_reply(e), "CONVIVENCIA")
            return
        except Exception as e:
            J.notify(f"No pude analizar la situación: {str(getattr(e, 'why', e))[:160]}", "CONVIVENCIA")
            return
        finally:
            cv_state["busy"] = False
        J.generated_files.add(path)
        J._open_doc(path)
        J.notify(CV.spoken(a), "CONVIVENCIA")
    J.start_job("Analizando situación de convivencia", work, "convivencia")
    return True


# ============================================================================ 2. PORTAFOLIO DE EVIDENCIAS
def make_portfolio(since=None):
    since = since or PF.year_start()
    root = J.settings["output_dir"]
    items = [it for it in PF.collect(root, since) if "Portafolio" not in it[0]]
    if not items:
        raise ValueError("no encontré trabajos tuyos con Jarvis desde esa fecha")
    groups = PF.by_area(items)
    refl, pres = {}, ""
    if J.state.get("ai") == "ok":
        try:
            d = J._extract_json(J.ai_chat([{"role": "user", "content": PF.reflection_prompt(groups, year=since.year)}], json_mode=True,
                                          max_tokens=2600))
            refl = {str(k): str(v) for k, v in (d.get("reflexiones") or {}).items()} if isinstance(d, dict) else {}
            pres = str(d.get("presentacion") or "") if isinstance(d, dict) else ""
        except Exception:
            refl = {}
    import docx
    doc = docx.Document()
    doc.add_heading(f"Portafolio de evidencias {since.year}", 0)
    doc.add_paragraph(f"Del {since.strftime('%d/%m/%Y')} al {datetime.date.today().strftime('%d/%m/%Y')} · {len(items)} evidencias.")
    doc.add_paragraph().add_run("Organizado por las competencias de la evaluación de desempeño (Decreto 1278 de 2002, Guía 31 "
                                "del MEN). Verifica con el protocolo vigente de tu entidad territorial y ajusta las reflexiones "
                                "con tu voz.").italic = True
    if pres:
        doc.add_heading("Presentación", 1)
        doc.add_paragraph(pres)
    out_dir = os.path.join(root, "Portafolio")
    os.makedirs(out_dir, exist_ok=True)
    zpath = os.path.join(out_dir, f"Evidencias {since.year} {time.strftime('%Y-%m-%d %H%M')}.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for area, its in groups.items():
            doc.add_heading(area, 1)
            r = next((v for k, v in refl.items() if k.split("·")[-1].strip().lower()[:12] in area.lower()), "")
            if r:
                doc.add_paragraph(r)
            tb = doc.add_table(rows=1, cols=2)
            tb.style = "Light Grid Accent 1"
            tb.rows[0].cells[0].text, tb.rows[0].cells[1].text = "Fecha", "Evidencia"
            for p, d, _a in its:
                row = tb.add_row().cells
                row[0].text, row[1].text = d.strftime("%d/%m/%Y"), os.path.basename(p)
                try:
                    if os.path.getsize(p) < 60 * 1024 * 1024:
                        z.write(p, os.path.join(re.sub(r"[^\w áéíóúñ·-]", "", area).strip(), os.path.basename(p)))
                except OSError:
                    pass
    dpath = os.path.join(out_dir, f"Portafolio {since.year} {time.strftime('%Y-%m-%d %H%M')}.docx")
    doc.save(dpath)
    return {"docx": dpath, "zip": zpath, "n": len(items), "areas": {k: len(v) for k, v in groups.items()}}


_PF = re.compile(r"\b(?:arma|armame|haz|hazme|prepara|preparame|organiza|organizame|genera)\s+(?:mi|el)\s+portafolio(?:\s+de\s+evidencias)?\b")


def portfolio_voice(text, t):
    if not _PF.search(t):
        return False
    since = None
    m = re.search(r"\bdesde\s+(?:el\s+)?(?:(\d{1,2})\s+de\s+)?(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\b", t)
    if m:
        mes = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"].index(m.group(2)) + 1
        today = datetime.date.today()
        since = datetime.date(today.year if mes <= today.month else today.year - 1, mes, int(m.group(1) or 1))
    J.reply("Armo tu portafolio con lo que hemos hecho este año, organizado por competencias. Te aviso.", "PORTAFOLIO")

    def work():
        try:
            r = make_portfolio(since)
        except Exception as e:
            J.notify(f"No pude armar el portafolio: {str(getattr(e, 'why', e))[:160]}", "PORTAFOLIO")
            return
        J.generated_files.add(r["docx"])
        J._open_doc(r["docx"])
        J.notify(f"Listo tu portafolio: {r['n']} evidencias (" + ", ".join(f"{k.split('·')[-1].strip().lower()}: {v}" for k, v in r["areas"].items())
                 + "). Te dejé el Word con el índice y las reflexiones, y un ZIP con los archivos, en Documentos, Jarvis, Portafolio.",
                 "PORTAFOLIO")
    J.start_job("Armando el portafolio", work, "portafolio")
    return True


# ============================================================================ 5. REGLAS AUTOMÁTICAS
_rg = {"lock": threading.Lock(), "pending": [], "timer": None}


def _rg_path():
    return os.path.join(J.CONFIG_DIR, "reglas_aula.json")


def rules_list():
    try:
        with open(_rg_path(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {"reglas": [], "avisados": []}
    except (OSError, ValueError):
        return {"reglas": [], "avisados": []}


def _rules_save(d):
    os.makedirs(J.CONFIG_DIR, exist_ok=True)
    with open(_rg_path(), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)


def rules_on_grade(curso, estudiante, actividad, nota, origen=""):
    """Lo llama seguimiento.add: si una regla se cumple, se junta (se avisa una vez por tanda, no 30 avisos seguidos)."""
    rs = [r for r in rules_list()["reglas"] if r["evento"] in ("nota_baja", "nota_alta")]
    hits = [r for r in rs if RG.grade_matches(r, float(nota), actividad)]
    if not hits:
        return
    with _rg["lock"]:
        for r in hits:
            _rg["pending"].append((r, curso, estudiante, actividad, float(nota)))
        if _rg["timer"] is None:
            _rg["timer"] = threading.Timer(20.0, rules_flush)
            _rg["timer"].daemon = True
            _rg["timer"].start()


def rules_flush():
    with _rg["lock"]:
        items, _rg["pending"], _rg["timer"] = _rg["pending"], [], None
    groups = {}
    for r, curso, est, act, nota in items:
        groups.setdefault((json.dumps(r, sort_keys=True), curso, act), []).append((est, nota))
    for (rk, curso, act), people in groups.items():
        r = json.loads(rk)
        names = ", ".join(f"{e} ({n:g})" for e, n in people[:6]) + ("…" if len(people) > 6 else "")
        if r["evento"] == "nota_baja":
            msg = f"Regla: en «{act}» de {curso}, {len(people)} estudiante(s) sacaron menos de {r['umbral']:g}: {names}."
            if "refuerzo" in r["acciones"]:
                msg += " Les preparo un taller de refuerzo."
                J.start_job("Refuerzo automático", lambda c=curso, a=act: J.generate_material(f"taller de refuerzo sobre {a} para {c}", "taller"),
                            "refuerzo")
        else:
            msg = f"Regla: en «{act}» de {curso}, {len(people)} estudiante(s) sacaron {r['umbral']:g} o más: {names}."
            if "felicitar" in r["acciones"]:
                msg += " Buen momento para felicitarlos."
        if "acudiente" in r["acciones"]:
            msg += " Si quieres, escríbele a los acudientes; tengo los nombres listos."
        J.notice_add(msg, "aviso", "REGLAS")
        J.notify(msg, "REGLAS")


def rules_absence_tick():
    """Una vez al día: quién lleva N faltas seguidas (o en el periodo) según tus reglas."""
    d = rules_list()
    rs = [r for r in d["reglas"] if r["evento"] == "fallas"]
    if not rs:
        return 0
    seen = set(d.get("avisados", []))
    n = 0
    for course, days in (aula.data.get("asistencia") or {}).items():
        class_days = sorted(days)
        for est in set(x for lst in days.values() for x in lst):
            absent = {dd for dd, lst in days.items() if est in lst}
            for r in rs:
                cnt = RG.streak(absent, class_days) if r.get("filtro") == "seguidas" else len(absent)
                key = f"{course}|{est}|{r['umbral']:g}|{max(absent)}"
                if cnt >= r["umbral"] and key not in seen:
                    seen.add(key)
                    n += 1
                    msg = f"Regla: {est} ({course}) lleva {cnt} faltas" + (" seguidas" if r.get("filtro") == "seguidas" else "") + "."
                    if "acudiente" in r["acciones"]:
                        msg += (f" Mensaje sugerido para el acudiente: «Buen día. Le escribo porque {est} ha faltado {cnt} clases"
                                f"{' seguidas' if r.get('filtro') == 'seguidas' else ''}. ¿Todo está bien? Quedo atento para apoyarlo.»")
                    J.notice_add(msg, "aviso", "REGLAS")
                    J.notify(msg, "REGLAS")
    d["avisados"] = sorted(seen)[-500:]
    _rules_save(d)
    return n


_RG_LIST = re.compile(r"\b(?:que|cuales)\s+reglas\s+(?:tengo|hay|tienes)\b|\bmis reglas(?: automaticas)?\b")
_RG_DEL = re.compile(r"\b(?:borra|elimina|quita)\s+(?:la\s+)?regla\s+(\d{1,2})\b|\b(?:borra|elimina|quita)\s+todas\s+las\s+reglas\b")


def rules_voice(text, t):
    if _RG_LIST.search(t):
        rs = rules_list()["reglas"]
        J.reply(("Tus reglas: " + "; ".join(f"{i + 1}) {RG.describe(r)}" for i, r in enumerate(rs)) + ".") if rs else
                "No tienes reglas. Por ejemplo: «si alguien saca menos de 3 en un quiz, prepárale un refuerzo y avísame».", "REGLAS")
        return True
    m = _RG_DEL.search(t)
    if m:
        d = rules_list()
        if m.group(1):
            i = int(m.group(1)) - 1
            if not 0 <= i < len(d["reglas"]):
                J.reply("No tengo esa regla. Di «¿qué reglas tengo?».", "REGLAS")
                return True
            d["reglas"].pop(i)
        else:
            d["reglas"] = []
        _rules_save(d)
        J.reply("Listo, regla borrada." if m.group(1) else "Borré todas las reglas.", "REGLAS")
        return True
    r = RG.parse(t)
    if not r:
        return False
    d = rules_list()
    if len(d["reglas"]) >= RG.MAX_RULES:
        J.reply(f"Ya tienes {RG.MAX_RULES} reglas; borra alguna primero.", "REGLAS")
        return True
    d["reglas"].append(r)
    _rules_save(d)
    J.reply(f"Regla guardada: {RG.describe(r)}. «¿Qué reglas tengo?» para verlas.", "REGLAS")
    return True


# ============================================================================ TODO JUNTO
def colegio53_voice(text, t):
    for fn in (convivencia_voice, rules_voice, inst_voice, portfolio_voice):
        if fn(text, t):
            return True
    return False


_rg_day = {"d": ""}


def colegio53_tick():
    today = datetime.date.today().isoformat()
    if _rg_day["d"] != today and datetime.datetime.now().hour >= 15:
        _rg_day["d"] = today
        try:
            rules_absence_tick()
        except Exception as e:
            J.note_error("REGLAS", e)


def _rg_listener(*a, **k):
    try:
        J.rules_on_grade(*a, **k)
    except Exception as e:
        J.note_error("REGLAS", e)


def colegio53_start():
    if _rg_listener not in seguimiento.listeners:
        seguimiento.listeners.append(_rg_listener)


colegio53_start()                                       # (al importar: las notas que entren ya pasan por tus reglas)


__all__ = ["INST", "inst_docs", "inst_add", "inst_search", "inst_answer", "inst_voice", "_INST_SAVE", "_INST_ASK", "_INST_LIST", "_DOCS",
           "cv_state", "convivencia_case", "_cv_docx", "convivencia_voice", "_CV",
           "make_portfolio", "portfolio_voice", "_PF",
           "_rg", "_rg_path", "rules_list", "_rules_save", "rules_on_grade", "rules_flush", "rules_absence_tick", "rules_voice",
           "_RG_LIST", "_RG_DEL", "colegio53_voice", "colegio53_tick", "colegio53_start", "_rg_day", "_rg_listener"]
