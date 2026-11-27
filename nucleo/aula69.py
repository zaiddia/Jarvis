"""12.69: preparación para el ascenso, pictogramas, simulaciones PhET, graficadora libre y ajustes.

  1. Ascenso (Decreto 1278): «hagamos un simulacro de la prueba de ascenso» (10 preguntas por voz o en el chat; respondes
     «la B»), «simulacro de ascenso de praxis pedagógica», «simulacro de ascenso en Word», «¿cómo voy en el simulacro de
     ascenso?», «calcula mis puntos de ascenso: 8 años, zona urbana, ningún ascenso». Las preguntas las escribe la IA: son
     práctica, no oficiales.
  2. Pictogramas (ARASAAC): «pasa a pictogramas: lávate las manos, saca el cuaderno…», «pictogramas de lo que subí»,
     «horario del lunes en pictogramas». Word para imprimir con el crédito que pide la licencia.
  3. Simulaciones PhET: «muéstrales la simulación de fracciones», «qué simulaciones de física hay», «descarga las
     simulaciones de matemáticas para usarlas sin internet».
  4. Graficadora: «grafica y = a x² + b x + c», «grafícame seno de x; coseno de x», «abre la graficadora».
  5. La conversación en vivo ya no intenta el modelo que Google retiró el 17 de noviembre de 2026.

La lógica pura está en ascenso.py, pictos.py, phet.py y graficadora.py. Los nombres globales se usan como J.<nombre>.
"""
import datetime
import json
import os
import re
import threading
import time
import urllib.parse

import adjuntos
import ascenso as AS
import envivo
import graficadora as GF
import horario
import phet as PH
import pictos as PC
from nucleo import J

RETIRED_LIVE = ("gemini-3.1-flash-live-preview", "gemini-2.5-flash-native-audio-preview-12-2025")
envivo.MODELS[:] = [m for m in envivo.MODELS if m not in RETIRED_LIVE] or ["gemini-3.8-live"]
asc_state = {"on": False, "qs": [], "i": 0, "results": [], "at": 0.0, "busy": False}
_a69_lock = threading.Lock()


def a69_migrate():
    """El modelo en vivo que Google apagó el 17/11/2026 → el actual (una vez)."""
    if J.settings.get("live_model") in RETIRED_LIVE:
        J.settings["live_model"] = "gemini-3.8-live"
        try:
            J.save_settings_file()
        except OSError:
            pass
        return True
    return False


def _a69_path():
    return os.path.join(J.CONFIG_DIR, "aula69.json")


def a69_data():
    try:
        with open(_a69_path(), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d.setdefault("ascenso", [])
    return d


def a69_save(d):
    with _a69_lock:
        os.makedirs(J.CONFIG_DIR, exist_ok=True)
        tmp = _a69_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, _a69_path())


def _a69_folder(name):
    p = os.path.join(J.settings["output_dir"], name)
    os.makedirs(p, exist_ok=True)
    return p


# ============================================================================ 1. ASCENSO
def asc_questions(n, comp="", area=""):
    raw = J.ai_chat([{"role": "user", "content": AS.prompt(n, area, comp)}], json_mode=True, max_tokens=min(12000, 900 * n + 800))
    return AS.clean(J._extract_json(raw), n)


def asc_word(qs, title):
    doc = J.Document()
    doc.add_heading(title, 1)
    doc.add_paragraph("Preguntas de práctica escritas con IA según los componentes de la prueba pedagógica (no son preguntas "
                      "oficiales). Elige la mejor decisión pedagógica en cada caso.")
    for i, q in enumerate(qs, 1):
        doc.add_paragraph(f"{i}. ({AS.COMPETENCIAS[q['competencia']].split(' (')[0]}) {q['caso']}").runs[0].bold = False
        doc.add_paragraph(q["pregunta"]).runs[0].bold = True
        for k, v in q["opciones"].items():
            doc.add_paragraph(f"{k}. {v}")
    doc.add_page_break()
    doc.add_heading("Respuestas y explicaciones", 2)
    for i, q in enumerate(qs, 1):
        doc.add_paragraph(f"{i}. {q['correcta']} — {q['explicacion']}")
    path = os.path.join(_a69_folder("Ascenso"), f"Simulacro de ascenso {datetime.datetime.now():%Y-%m-%d %H%M}.docx")
    doc.save(path)
    return path


def _asc_ask():
    q = asc_state["qs"][asc_state["i"]]
    asc_state["at"] = time.time()
    J.reply(AS.spoken_question(q, asc_state["i"] + 1, len(asc_state["qs"])) + " ¿Cuál escoges?", "ASCENSO")


def _asc_finish():
    good, n, by, weak = AS.summary(asc_state["results"])
    asc_state["on"] = False
    d = a69_data()
    d["ascenso"].append({"fecha": str(datetime.date.today()), "bien": good, "total": n,
                         "por": {k: list(v) for k, v in by.items()}})
    d["ascenso"] = d["ascenso"][-60:]
    a69_save(d)
    J.reply(f"Terminamos: acertaste {good} de {n}." + (f" Lo que más te conviene repasar: {AS.COMPETENCIAS[weak].split(' (')[0].lower()}"
            f" (simulacro de ascenso de {weak})." if weak and by[weak][0] < by[weak][1] else " ¡Muy bien!"), "ASCENSO")


_ASC_START = re.compile(r"^(?:jarvis\s+)?(?:hagamos|haz(?:me)?|empecemos|iniciemos|quiero(?: hacer)?|dame|preparame|vamos con|practiquemos)\s+"
                        r"(?:un\s+|el\s+)?(?:simulacro|practica|preguntas?)\s+(?:de\s+(?:la\s+)?)?(?:prueba\s+(?:pedagogica\s+)?(?:de\s+)?)?"
                        r"(?:ascenso|concurso de ascenso|la prueba de ascenso|prueba pedagogica)(.*)$|"
                        r"^(?:jarvis\s+)?(?:practiquemos|preparame para)\s+(?:el|la)\s+(?:ascenso|prueba de ascenso|concurso de ascenso)(.*)$")
_ASC_HOW = re.compile(r"^(?:jarvis\s+)?(?:como voy|como me fue|mis resultados)\s+(?:en|de)\s+(?:los\s+|el\s+)?(?:simulacros?|prueba)\s+(?:de\s+)?ascenso$")
_ASC_POINTS = re.compile(r"^(?:jarvis\s+)?(?:calcula(?:me)?|cuantos|cuanto)\s+(?:mis\s+)?puntos?\s+(?:de|para el|necesito en la prueba de)\s+ascenso(.*)$")
_ASC_STOP = re.compile(r"^(?:jarvis\s+)?(?:termina|terminemos|para|deja|acaba)\s+(?:el\s+)?(?:simulacro|la practica)(?: de ascenso)?$")
_ASC_REPEAT = re.compile(r"^(?:jarvis\s+)?(?:repite|repiteme|otra vez)(?: la pregunta)?$")
_ASC_PASS = re.compile(r"^(?:jarvis\s+)?(?:no se|paso|no tengo idea|siguiente pregunta|dime la respuesta)$")


def _asc_active():
    return asc_state["on"] and time.time() - asc_state["at"] < 1800


def _a69_asc_voice(text, t):
    if _asc_active():
        letter = AS.answer_letter(t)
        if letter or _ASC_PASS.match(t):
            q = asc_state["qs"][asc_state["i"]]
            ok = letter == q["correcta"]
            asc_state["results"].append({"competencia": q["competencia"], "ok": ok})
            J.reply(("¡Correcto! " if ok else (f"No: la mejor es la {q['correcta']}. " if letter else f"Es la {q['correcta']}. "))
                    + q["explicacion"], "ASCENSO")
            asc_state["i"] += 1
            if asc_state["i"] >= len(asc_state["qs"]):
                _asc_finish()
            else:
                _asc_ask()
            return True
        if _ASC_REPEAT.match(t):
            _asc_ask()
            return True
        if _ASC_STOP.match(t):
            if asc_state["results"]:
                _asc_finish()
            else:
                asc_state["on"] = False
                J.reply("Listo, dejamos el simulacro.", "ASCENSO")
            return True
    m = _ASC_START.match(t)
    if m:
        rest = (m.group(1) or m.group(2) or "").strip()
        mn = re.search(r"\b(\d{1,2})\s+(?:preguntas|casos)\b", rest)
        n = max(3, min(40, int(mn.group(1)) if mn else 10))
        comp = AS.competence_in(rest)
        area = (re.search(r"\b(?:de|para)\s+(matematicas|tecnologia|informatica|ciencias|lenguaje|sociales|ingles|primaria)\b", rest) or [None, ""])[1]
        if J.state.get("ai") != "ok":
            J.reply("Para escribir las preguntas necesito la IA conectada.", "ASCENSO")
            return True
        if asc_state["busy"]:
            J.reply("Ya estoy preparando las preguntas.", "ASCENSO")
            return True
        word = bool(re.search(r"\b(?:en|para)\s+(?:word|imprimir|documento)\b", rest))
        J.reply(f"Preparo {n if word else min(n, 15)} casos de práctica" + (f" de {AS.COMPETENCIAS[comp].split(' (')[0].lower()}" if comp else "")
                + ". Son preguntas hechas con IA según lo que evalúa la prueba, no las oficiales.", "ASCENSO")

        def work():
            asc_state["busy"] = True
            try:
                qs = J.asc_questions(n if word else min(n, 15), comp, area)
            except (J.AIError, ValueError) as e:
                J.notify(J.ai_error_reply(e) if isinstance(e, J.AIError) else f"No pude armar el simulacro: {e}.", "ASCENSO")
                return
            finally:
                asc_state["busy"] = False
            if word:
                path = J.asc_word(qs, "Simulacro de la prueba pedagógica de ascenso")
                J.generated_files.add(path)
                J.notify(f"Listo el simulacro con {len(qs)} casos en Word (las respuestas explicadas van al final), en Documentos, "
                         "Jarvis, Ascenso.", "ASCENSO")
                if J.settings.get("aula_open_docs", True):
                    J._open_doc(path)
                return
            asc_state.update(on=True, qs=qs, i=0, results=[])
            _asc_ask()
        J.start_job("Preparando el simulacro de ascenso", work, "ascenso")
        return True
    if _ASC_HOW.match(t):
        hist = a69_data()["ascenso"]
        if not hist:
            J.reply("Aún no has hecho simulacros de ascenso. Di «hagamos un simulacro de la prueba de ascenso».", "ASCENSO")
            return True
        tot = {}
        for h in hist:
            for k, (b, n) in h["por"].items():
                tb, tn = tot.get(k, (0, 0))
                tot[k] = (tb + b, tn + n)
        last = hist[-1]
        parts = [f"{AS.COMPETENCIAS[k].split(' (')[0].lower()} {round(100 * b / n)} %" for k, (b, n) in sorted(tot.items(), key=lambda kv: kv[1][0] / kv[1][1])]
        J.reply(f"Llevas {len(hist)} simulacro{'s' if len(hist) != 1 else ''}; en el último acertaste {last['bien']} de {last['total']}. "
                "Por competencia: " + ", ".join(parts) + ".", "ASCENSO")
        return True
    m = _ASC_POINTS.match(t)
    if m:
        years, zone, moves = AS.parse_points(m.group(1))
        txt = AS.needed_text(years, zone, moves) if years is not None else ""
        J.reply(txt or ("Dime tus datos así: «calcula mis puntos de ascenso: 8 años de servicio, zona urbana de municipio certificado, "
                        "ningún ascenso». La zona puede ser rural de difícil acceso, rural, urbana de municipio no certificado o "
                        "urbana de municipio o distrito certificado (como Cali)."), "ASCENSO")
        return True
    return False


# ============================================================================ 2. PICTOGRAMAS
def _a69_picto_dir():
    p = os.path.join(J.CONFIG_DIR, "pictos_cache")
    os.makedirs(p, exist_ok=True)
    return p


def picto_for(word):
    """Ruta del PNG del pictograma de ARASAAC para esa palabra (con caché), o "" si no hay."""
    key = PC.norm(word)
    if not key:
        return ""
    base = os.path.join(_a69_picto_dir(), re.sub(r"\s+", "_", key)[:60])
    if os.path.exists(base + ".png"):
        return base + ".png"
    if os.path.exists(base + ".none") and time.time() - os.path.getmtime(base + ".none") < 7 * 86400:
        return ""
    try:
        pid = PC.first_id(J._http("GET", PC.search_url(key), timeout=15))
    except J.AIError as e:
        if e.code == 404:
            open(base + ".none", "w").close()
        return ""
    if pid is None:
        open(base + ".none", "w").close()
        return ""
    for u in PC.image_urls(pid):
        try:
            r = J._http("GET", u, {"Accept": "image/png"}, timeout=20, stream=True)
            with r:
                data = r.read()
            if data[:4] == b"\x89PNG":
                with open(base + ".png", "wb") as f:
                    f.write(data)
                return base + ".png"
        except J.AIError:
            continue
    return ""


def make_pictos(content):
    """content: {"titulo", "pasos": [{"texto", "claves"}]} → (ruta del Word, cuántos sin pictograma)"""
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt
    doc = J.Document()
    h = doc.add_heading(content["titulo"], 1)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    steps = content["pasos"]
    cols = 3 if len(steps) > 4 else max(1, len(steps))
    rows = (len(steps) + cols - 1) // cols
    tb = doc.add_table(rows=rows, cols=cols)
    tb.style = "Table Grid"
    missing = 0
    for i, st in enumerate(steps):
        cell = tb.cell(i // cols, i % cols)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        got = [x for x in (J.picto_for(k) for k in st["claves"][:2]) if x]
        if not got:
            missing += 1
        for img in got:
            p.add_run().add_picture(img, width=Cm(4.6 / len(got) if len(got) > 1 else 4.6))
        q = cell.add_paragraph()
        q.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = q.add_run(f"{i + 1}. {st['texto']}" if len(steps) > 1 else st["texto"])
        r.bold = True
        r.font.size = Pt(16 if got else 22)
    note = doc.add_paragraph(PC.CREDIT)
    note.runs[0].font.size = Pt(8)
    path = os.path.join(_a69_folder("Pictogramas"), re.sub(r'[\\/:*?"<>|]+', "-", content["titulo"])[:80]
                        + f" {datetime.datetime.now():%Y-%m-%d %H%M}.docx")
    doc.save(path)
    return path, missing


_PIC = re.compile(r"^(?:jarvis\s+)?(?:pasa(?:me)?|pon(?:me)?|convierte(?:me)?|haz(?:me)?|traduce(?:me)?|arma(?:me)?)\s+(?:esto\s+|estos pasos\s+|"
                  r"estas instrucciones\s+)?(?:a|en|con|los|unos|un tablero de|una tira de)?\s*pictogramas?\b(.*)$|"
                  r"^(?:jarvis\s+)?(?:pictogramas?|tira de pictogramas|agenda visual)\s+(?:de|para|con)\b(.*)$|"
                  r"^(?:jarvis\s+)?(?:el\s+)?horario\s+(?:del?\s+)?(lunes|martes|miercoles|jueves|viernes|sabado|hoy|manana)\s+(?:en|con)\s+pictogramas$")


def _a69_pic_voice(text, t):
    m = _PIC.match(t)
    if not m:
        return False
    day_word = m.group(3)
    if day_word:
        today = datetime.date.today()
        names = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado"]
        day = today.weekday() if day_word == "hoy" else (today.weekday() + 1) % 7 if day_word == "manana" else names.index(day_word)
        content = PC.schedule_steps(horario.items, day)
        if not content["pasos"]:
            J.reply("No tengo clases en tu horario para ese día.", "PICTOGRAMAS")
            return True
        source = None
    else:
        raw = re.split(r"(?i)pictogramas?\s*(?:de|para|con)?\s*[:,]?\s*", text, maxsplit=1)
        source = raw[1].strip() if len(raw) > 1 and len(raw[1].strip()) > 3 else ""
        if not source or re.fullmatch(r"(?:lo que (?:te )?subi|el documento|este documento|el archivo|esto)\W*", PC.norm(source)):
            it = next((i for i in adjuntos.recent(1800) if i["tipo"] in ("texto", "pdf", "word", "imagen")), None)
            if not it:
                J.reply("Dime el texto después de «pictogramas:» (por ejemplo «pasa a pictogramas: lávate las manos, saca el cuaderno») "
                        "o sube el documento.", "PICTOGRAMAS")
                return True
            source = J._text_of_item(it) or ""
        content = None
    J.reply("Busco los pictogramas en ARASAAC y armo la hoja…", "PICTOGRAMAS")

    def work():
        c = content
        if c is None:
            try:
                c = PC.clean(J._extract_json(J.ai_chat([{"role": "user", "content": PC.prompt(source)}], json_mode=True, max_tokens=1500)))
            except (J.AIError, ValueError):
                c = PC.split_plain(source)
        try:
            path, missing = J.make_pictos(c)
        except Exception as e:
            J.notify(f"No pude armar los pictogramas: {e}.", "PICTOGRAMAS")
            return
        J.generated_files.add(path)
        J.notify(f"Listos {len(c['pasos'])} pasos con pictogramas, en Word para imprimir, en Documentos, Jarvis, Pictogramas."
                 + (f" {missing} no tienen dibujo (no lo encontré o no hay internet): van con letra grande." if missing else "")
                 + " Lleva el crédito de ARASAAC que pide la licencia.", "PICTOGRAMAS")
        if J.settings.get("aula_open_docs", True):
            J._open_doc(path)
    J.start_job("Armando los pictogramas", work, "pictogramas")
    return True


# ============================================================================ 3. SIMULACIONES PhET
def _a69_phet_dir():
    p = os.path.join(J.CONFIG_DIR, "phet")
    os.makedirs(p, exist_ok=True)
    return p


def phet_cached(slug):
    p = os.path.join(_a69_phet_dir(), slug + ".html")
    return p if os.path.isfile(p) and os.path.getsize(p) > 5000 else ""


def phet_download(slug):
    """Guarda la simulación (en español; si no está traducida, en inglés). → ruta o "" si no se pudo."""
    if slug not in PH.SIMS:
        return ""
    for lang in ("es", "en"):
        try:
            r = J._http("GET", PH.url(slug, lang), {"Accept": "text/html"}, timeout=120, stream=True)
            with r:
                data = r.read()
        except J.AIError:
            continue
        if len(data) > 5000 and b"<html" in data[:2000].lower():
            dst = os.path.join(_a69_phet_dir(), slug + ".html")
            with open(dst + ".tmp", "wb") as f:
                f.write(data)
            os.replace(dst + ".tmp", dst)
            return dst
    return ""


@J.app.route("/phet/<slug>")
def a69_phet_page(slug):
    from flask import abort, redirect, send_file
    if slug not in PH.SIMS:
        abort(404)
    p = phet_cached(slug)
    if p:
        return send_file(p, mimetype="text/html")
    if J.is_offline():
        return ("<!DOCTYPE html><meta charset='utf-8'><body style='font:20px system-ui;padding:40px'>Esta simulación aún no está "
                "guardada y no hay internet. Con internet, di «descarga las simulaciones» para tenerlas sin conexión.</body>")
    threading.Thread(target=J.phet_download, args=(slug,), daemon=True).start()     # para la próxima vez, sin internet
    return redirect(PH.url(slug))


_PH_OPEN = re.compile(r"^(?:jarvis\s+)?(?:abre|abreme|muestra|muestrame|muestrales|pon|ponles|ponme|lanza|proyecta|ensename|ensenales)\s+"
                      r"(?:la\s+|una\s+)?simulacion(?:\s+de\s+phet|\s+phet)?\s+(?:de|del|de la|de los|de las|sobre)\s+(.+)$|"
                      r"^(?:jarvis\s+)?simulacion\s+(?:de\s+phet\s+)?(?:de|del|de la|sobre)\s+(.+)$")
_PH_LIST = re.compile(r"^(?:jarvis\s+)?(?:que|cuales)\s+simulaciones(?: de phet)?(?:\s+de\s+(\w+(?: de la \w+)?))?\s+(?:hay|tienes)(?:\s+de\s+(.+))?$")
_PH_DL = re.compile(r"^(?:jarvis\s+)?(?:descarga|baja|guarda)(?:me)?\s+(?:las\s+)?simulaciones(?: de phet)?(?:\s+de\s+(.+?))?(?:\s+para (?:usarlas )?sin internet)?$")
_a69_dl = {"busy": False}


def _a69_phet_voice(text, t):
    m = _PH_OPEN.match(t)
    if m:
        want = (m.group(1) or m.group(2) or "").strip()
        slug = PH.find(want)
        if not slug:
            J.reply(f"No tengo una simulación de «{want}». Di «qué simulaciones hay» para ver la lista.", "SIMULACIONES")
            return True
        J.open_window(f"/phet/{slug}", PH.SIMS[slug][0])
        J.reply(f"Abro «{PH.SIMS[slug][0]}» de PhET." + ("" if phet_cached(slug) else " La guardo para que la próxima vez funcione sin internet."),
                "SIMULACIONES")
        return True
    m = _PH_LIST.match(t)
    if m:
        lst = PH.by_area(m.group(1) or m.group(2) or "")
        if not lst:
            J.reply("Tengo simulaciones de matemáticas, física, química, biología y ciencias de la tierra.", "SIMULACIONES")
            return True
        J.reply(f"Tengo {len(lst)}: " + ", ".join(n for _s, n in lst[:18]) + ("…" if len(lst) > 18 else "") +
                ". Di, por ejemplo, «muéstrales la simulación de fracciones».", "SIMULACIONES")
        return True
    m = _PH_DL.match(t)
    if m:
        lst = [s for s, _n in PH.by_area(m.group(1) or "")]
        if J.is_offline():
            J.reply("Para descargarlas necesito internet.", "SIMULACIONES")
            return True
        if _a69_dl["busy"]:
            J.reply("Ya las estoy descargando.", "SIMULACIONES")
            return True
        J.reply(f"Descargo {len(lst)} simulaciones para usarlas sin internet; tarda unos minutos.", "SIMULACIONES")

        def work():
            _a69_dl["busy"] = True
            try:
                ok = sum(1 for s in lst if phet_cached(s) or J.phet_download(s))
            finally:
                _a69_dl["busy"] = False
            J.notify(f"Listo: {ok} de {len(lst)} simulaciones guardadas; ya funcionan sin internet.", "SIMULACIONES")
        J.start_job("Descargando simulaciones", work, "phet")
        return True
    return False


# ============================================================================ 4. GRAFICADORA
@J.app.route("/graficadora")
def a69_grapher_page():
    from flask import render_template, request
    funcs = []
    for f in request.args.getlist("f")[:GF.MAX_FUNCS]:
        try:
            funcs.append(GF.canonical(f)[0])
        except ValueError:
            continue
    vals = {}
    for k in GF.PARAMS:
        try:
            if request.args.get(k) is not None:
                vals[k] = max(-10.0, min(10.0, float(request.args[k])))
        except ValueError:
            pass
    return render_template("graficadora.html", funcs=funcs, vals=vals)


_GF = re.compile(r"^(?:jarvis\s+)?(?:grafica(?:me|nos|les)?|dibuja(?:me)? la (?:funcion|grafica de)|traza(?:me)?|haz(?:me)? la grafica de|"
                 r"muestra(?:me|les)? la grafica de)\s+(?:la funcion\s+)?(.+)$")
_GF_OPEN = re.compile(r"^(?:jarvis\s+)?(?:abre|abreme|muestra|muestrales|pon)\s+(?:la\s+)?graficadora$")


def _a69_gf_voice(text, t):
    if _GF_OPEN.match(t):
        J.open_window("/graficadora", "Graficadora")
        J.reply("Abrí la graficadora: escribe la función y las letras se vuelven deslizadores.", "GRAFICADORA")
        return True
    m = _GF.match(t)
    if not m:
        return False
    raw = re.split(r"(?i)\b(?:gr[aá]fica(?:me|nos|les)?|dibuja(?:me)? la (?:funci[oó]n|gr[aá]fica de)|traza(?:me)?|haz(?:me)? la gr[aá]fica de|"
                   r"muestra(?:me|les)? la gr[aá]fica de)\s+(?:la funci[oó]n\s+)?", text, maxsplit=1)
    expr = raw[-1]
    vals = GF.values_in(expr)
    expr = re.split(r"(?i)\s+con\s+[a-z]\s*(?:=|igual|vale)", expr)[0]
    try:
        funcs = GF.parse_request(expr)
    except ValueError as e:
        if re.search(r"\b(?:barras|torta|pastel|estadistic)\b", t):
            return False
        J.reply(f"No pude leer la función: {e}. Dímela así: «grafica y = 2x² − 3x + 1».", "GRAFICADORA")
        return True
    q = urllib.parse.urlencode([("f", f) for f, _p in funcs] + [(k, v) for k, v in vals.items()])
    J.open_window(f"/graficadora?{q}", "Graficadora")
    params = sorted({p for _f, ps in funcs for p in ps})
    J.reply("Ahí está " + ("la gráfica" if len(funcs) == 1 else f"la gráfica de las {len(funcs)} funciones") +
            (f"; mueve {', '.join(params)} con los deslizadores (▶ los anima)." if params else ".") +
            " Se acerca con la rueda del mouse y muestra dónde corta los ejes.", "GRAFICADORA")
    return True


def aula69_voice(text, t):
    for fn in (_a69_asc_voice, _a69_pic_voice, _a69_phet_voice, _a69_gf_voice):
        if fn(text, t):
            return True
    return False


__all__ = ['RETIRED_LIVE', '_ASC_HOW', '_ASC_PASS', '_ASC_POINTS', '_ASC_REPEAT', '_ASC_START', '_ASC_STOP', '_GF', '_GF_OPEN', '_PH_DL',
           '_PH_LIST', '_PH_OPEN', '_PIC', '_a69_asc_voice', '_a69_dl', '_a69_folder', '_a69_gf_voice', '_a69_lock', '_a69_path',
           '_a69_pic_voice', '_a69_phet_dir', '_a69_phet_voice', '_a69_picto_dir', '_asc_active', '_asc_ask', '_asc_finish',
           'a69_data', 'a69_grapher_page', 'a69_migrate', 'a69_phet_page', 'a69_save', 'asc_questions', 'asc_state', 'asc_word',
           'aula69_voice', 'make_pictos', 'phet_cached', 'phet_download', 'picto_for']
