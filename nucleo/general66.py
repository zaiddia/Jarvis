"""12.66: seis funciones para el día a día.

  1. Reclamos: «haz un derecho de petición a la EPS Sura porque no me autorizan la resonancia» · «reclama a Claro porque
     me cobraron de más» · «haz una tutela contra…» · «ya radiqué el reclamo de Claro» · «me respondieron el reclamo de
     Claro» · «mis reclamos». Plazo en días hábiles (sin festivos) y aviso con el siguiente paso si no responden.
  2. Extracto: sube el PDF y toca «Analizar extracto» (o «analiza mi extracto»): en qué se va la plata y cobros a revisar.
  3. Deudas: «anota una deuda: tarjeta Éxito 3 millones al 2,1 % mensual, cuota de 250 mil» · «mis deudas» ·
     «plan para salir de deudas abonando la prima de 2 millones» · «ya pagué la deuda de la tarjeta Éxito».
  4. «¿Esto es verdad? …» / «verifica esta noticia: …»: busca y responde con veredicto, fuentes y un mensaje para el grupo.
  5. Exámenes de laboratorio: sube el resultado y toca «Explicar exámenes» (o «explícame estos exámenes»).
  6. «Practiquemos inglés en vivo (nivel intermedio) sobre viajes»: la práctica de 12.21, pero hablando en la conversación
     en vivo; al terminar, el repaso de errores y palabras nuevas en Word.

La lógica está en vidapractica.py. Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import json
import os
import re
import threading

import adjuntos
import confianza
import festivos
import humano
import vidapractica as G
from nucleo import J

G66_ACTIONS = {"extracto": "Analizar extracto", "laboratorio": "Explicar exámenes"}
_g66_lock = threading.Lock()
g66_tutor = {"on": False, "level": "basico", "topic": "", "start": 0}


def _g66_path():
    return os.path.join(J.CONFIG_DIR, "general66.json")


def g66_data():
    try:
        with open(_g66_path(), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d.setdefault("reclamos", [])
    d.setdefault("deudas", [])
    return d


def g66_save(d):
    with _g66_lock:
        os.makedirs(J.CONFIG_DIR, exist_ok=True)
        tmp = _g66_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1, default=str)
        os.replace(tmp, _g66_path())


def _g66_holidays(*years):
    out = set()
    for y in years:
        out |= set(festivos.holidays(y))
    return out


def _g66_recent(kinds):
    for it in adjuntos.recent(1800):
        if it["tipo"] in kinds:
            return it
    return None


def _g66_pesos(n):
    return "$" + f"{int(round(n)):,}".replace(",", ".")


# ============================================================================ 1. RECLAMOS
def claim_make(kind, entidad, hechos):
    txt = J.ai_chat([{"role": "user", "content": G.letter_prompt(kind, entidad, hechos, J.settings.get("address_name", ""),
                                                                 J.settings.get("weather_city", ""))}], max_tokens=3000)
    title = {"peticion": "Derecho de petición", "tutela": "Acción de tutela (borrador)", "queja": "Queja"}[kind]
    doc = J.Document()
    for line in str(txt).splitlines():
        if line.strip():
            doc.add_paragraph(line.strip().strip("*#"))
    folder = os.path.join(J.settings["output_dir"], "Reclamos")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, re.sub(r'[\\/:*?"<>|]+', "-", f"{title} - {entidad} {datetime.date.today():%Y-%m-%d}")[:120] + ".docx")
    doc.save(path)
    sector, escala, nota = G.sector_of(f"{entidad} {hechos}")
    d = g66_data()
    d["reclamos"].append({"id": len(d["reclamos"]) + 1, "tipo": kind, "entidad": entidad, "hechos": hechos[:300], "sector": sector,
                          "creado": str(datetime.date.today()), "radicado": "", "vence": "", "respondido": False, "avisado": False,
                          "archivo": path})
    g66_save(d)
    return path, sector, escala, nota


def claim_filed(rec, day=None):
    day = day or datetime.date.today()
    rec["radicado"] = str(day)
    rec["vence"] = str(G.business_deadline(day, G.DAYS_TO_ANSWER, _g66_holidays(day.year, day.year + 1)))
    return rec["vence"]


def _g66_find_claim(d, spoken):
    """El reclamo abierto con esa entidad (o el último abierto, si no se dice cuál)."""
    q = G.norm(spoken)
    open_ = [r for r in d["reclamos"] if not r["respondido"]]
    if not q:
        return open_[-1] if open_ else None
    hit = [r for r in open_ if G.norm(r["entidad"]) in q or q in G.norm(r["entidad"])]
    return hit[-1] if hit else None


_G66_NEW = re.compile(r"^(?:jarvis\s+)?(?:haz|hazme|redacta|redactame|escribe|escribeme|prepara|preparame)\s+(?:un|una|el|la)\s+"
                      r"(derecho de peticion|peticion|tutela|accion de tutela|queja|reclamo|reclamacion)\s+(?:a|ante|contra|para)\s+(?:la\s+|el\s+)?"
                      r"(.+?)\s+(?:porque|por|ya que|pues|debido a que)\s+(.+)$")
_G66_SHORT = re.compile(r"^(?:jarvis\s+)?(?:reclama(?:le)?|quejate)\s+(?:a|ante|con)\s+(?:la\s+|el\s+)?(.+?)\s+(?:porque|por|ya que)\s+(.+)$")
_G66_FILED = re.compile(r"^(?:jarvis\s+)?(?:ya\s+)?(?:radique|envie|mande|presente|puse)\s+(?:el|la)\s+(?:reclamo|peticion|derecho de peticion|queja)"
                       r"(?:\s+(?:a|de|ante|contra)\s+(?:la\s+|el\s+)?(.+?))?(?:\s+(?:hoy|ayer))?$")
_G66_ANSWERED = re.compile(r"^(?:jarvis\s+)?(?:ya\s+)?me (?:respondieron|contestaron)\s+(?:el|la)\s+(?:reclamo|peticion|derecho de peticion|queja)"
                          r"(?:\s+(?:a|de|ante|contra)\s+(?:la\s+|el\s+)?(.+?))?$")
_G66_LIST = re.compile(r"^(?:jarvis\s+)?(?:mis|cuales son mis|como van mis|que paso con mis)\s+(?:reclamos|peticiones|derechos de peticion|quejas)$")


def _g66_orig_tail(text, norm_tail):
    raw = re.sub(r"[\s.!?¡¿]+$", "", str(text or ""))
    tail = raw[-len(norm_tail):] if norm_tail and len(raw) >= len(norm_tail) else ""
    return tail if tail and G.norm(tail) == norm_tail else norm_tail


def _g66_claim_voice(text, t):
    m = _G66_NEW.match(t)
    m2 = None if m else _G66_SHORT.match(t)
    if m or m2:
        word = m.group(1) if m else "reclamo"
        kind = "tutela" if "tutela" in word else "queja" if word == "queja" else "peticion"
        ent_n, hechos_n = (m.group(2), m.group(3)) if m else (m2.group(1), m2.group(2))
        hechos = _g66_orig_tail(text, hechos_n)
        entidad = _g66_orig_tail(re.sub(r"(?i)\s+(?:porque|por|ya que|pues|debido a que)\s+.*$", "", text), ent_n).strip().title()
        J.reply(f"Redacto {'la tutela' if kind == 'tutela' else 'el ' + ('derecho de petición' if kind == 'peticion' else 'escrito de queja')} "
                f"para {entidad}…", "RECLAMOS")

        def work():
            try:
                path, sector, escala, nota = J.claim_make(kind, entidad, hechos)
            except J.AIError as e:
                J.notify(J.ai_error_reply(e), "RECLAMOS")
                return
            J.notify("Listo el borrador en Word: complétalo donde dice [entre corchetes] y fírmalo. Radícalo por el canal oficial "
                     f"de {entidad} (página, correo o ventanilla) y guarda el número de radicado. Luego dime «ya radiqué el "
                     f"reclamo de {entidad}» y te aviso cuando venza el plazo de respuesta ({G.DAYS_TO_ANSWER} días hábiles). "
                     + (nota + " " if nota else "") + "Esto es una orientación; no reemplaza a un abogado.", "RECLAMOS")
            if J.settings.get("aula_open_docs", True):
                J._open_doc(path)
        J.start_job("Redactando el reclamo", work, "reclamo")
        return True
    m = _G66_FILED.match(t)
    if m:
        d = g66_data()
        r = _g66_find_claim(d, m.group(1) or "")
        if not r:
            J.reply("No tengo ese reclamo. Primero: «haz un derecho de petición a … porque …».", "RECLAMOS")
            return True
        day = datetime.date.today() - datetime.timedelta(days=1 if re.search(r"\bayer\b", t) else 0)
        vence = datetime.date.fromisoformat(J.claim_filed(r, day))
        g66_save(d)
        J.reply(f"Anotado: radicaste el reclamo a {r['entidad']} el {day:%d/%m}. Tienen hasta el {J.fecha_hablada(vence)} para "
                "responderte; si no lo hacen, te aviso y te digo qué sigue.", "RECLAMOS")
        return True
    m = _G66_ANSWERED.match(t)
    if m:
        d = g66_data()
        r = _g66_find_claim(d, m.group(1) or "")
        if not r:
            J.reply("No tengo reclamos abiertos con ese nombre.", "RECLAMOS")
            return True
        r["respondido"] = True
        g66_save(d)
        _s, escala, _n = G.sector_of(f"{r['entidad']} {r['hechos']}")
        J.reply(f"Anotado: {r['entidad']} respondió. Si la respuesta no te resuelve, el siguiente paso es {escala}.", "RECLAMOS")
        return True
    if _G66_LIST.match(t):
        rs = [r for r in g66_data()["reclamos"] if not r["respondido"]]
        if not rs:
            J.reply("No tienes reclamos abiertos.", "RECLAMOS")
            return True
        J.reply(f"Tienes {len(rs)} reclamo{'s' if len(rs) != 1 else ''} abierto{'s' if len(rs) != 1 else ''}: " + "; ".join(
            f"{r['entidad']} ({'vence el ' + datetime.date.fromisoformat(r['vence']).strftime('%d/%m') if r['vence'] else 'sin radicar'})"
            for r in rs[:6]) + ".", "RECLAMOS")
        return True
    return False


def general66_tick(now=None):
    """Si venció el plazo de un reclamo radicado y nadie respondió: aviso una vez, con el siguiente paso."""
    now = now or datetime.datetime.now()
    if now.hour < 9:
        return
    d = g66_data()
    due = [r for r in d["reclamos"] if r["vence"] and not r["respondido"] and not r["avisado"] and r["vence"] < str(now.date())]
    if not due:
        return
    for r in due:
        r["avisado"] = True
        _s, escala, nota = G.sector_of(f"{r['entidad']} {r['hechos']}")
        J.notify(f"Se venció el plazo para que {r['entidad']} respondiera tu reclamo (radicado el "
                 f"{datetime.date.fromisoformat(r['radicado']):%d/%m}). Siguiente paso: {escala}. " + (nota + " " if nota else "") +
                 "Si ya te respondieron, dime «me respondieron el reclamo de " + r["entidad"] + "».", "RECLAMOS")
    g66_save(d)


# ============================================================================ 3. DEUDAS
_G66_MONEY = r"(\d+(?:[.,]\d+)?)\s*(millones|millon|mill|mil|m\b)?"


def _g66_amount(n, unit):
    v = float(n.replace(".", "").replace(",", ".")) if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", n) else float(n.replace(",", "."))
    return v * (1_000_000 if unit and (unit.startswith("mill") or unit == "m") else 1000 if unit == "mil" else 1)


def debt_parse(t):
    """«tarjeta exito 3 millones al 2,1 % mensual, cuota de 250 mil» → deuda o None."""
    m = re.match(rf"^(.+?)\s+(?:de\s+|por\s+)?{_G66_MONEY}\b", t)
    r = re.search(r"\b(?:al|con|tasa(?: de)?|interes(?: de)?)\s+(\d+(?:[.,]\d+)?)\s*(?:%|por ciento)\s*(mensual|mes|ea|e a|efectivo anual|anual)?", t)
    c = re.search(rf"\bcuota(?: minima)?(?: de)?\s+{_G66_MONEY}", t)
    if not (m and r and c):
        return None
    kind = "ea" if r.group(2) and r.group(2).replace(" ", "") in ("ea", "efectivoanual", "anual") else "mensual"
    return {"nombre": m.group(1).strip().title()[:40], "saldo": _g66_amount(m.group(2), m.group(3)),
            "tasa": G.monthly_rate(float(r.group(1).replace(",", ".")), kind), "cuota": _g66_amount(c.group(1), c.group(2)),
            "tasa_txt": f"{r.group(1)} % {'EA' if kind == 'ea' else 'mensual'}"}


_G66_DEBT_ADD = re.compile(r"^(?:jarvis\s+)?(?:anota|agrega|registra|apunta)\s+(?:una\s+)?deuda\s*[:,]?\s*(.+)$")
_G66_DEBT_LIST = re.compile(r"^(?:jarvis\s+)?(?:mis deudas|cuanto debo|que deudas tengo|cuales son mis deudas)$")
_G66_DEBT_PLAN = re.compile(r"^(?:jarvis\s+)?(?:haz(?:me)?\s+)?(?:un\s+|el\s+)?plan (?:para|de) (?:salir de|pagar) (?:las |mis )?deudas(.*)$|"
                            r"^(?:jarvis\s+)?como (?:salgo|salir) de (?:mis |las )?deudas(.*)$")
_G66_DEBT_DONE = re.compile(r"^(?:jarvis\s+)?(?:ya\s+)?(?:pague|termine de pagar|sali de|salde|cancele)\s+(?:la\s+)?deuda\s+(?:de\s+|del\s+|de la\s+)?(.+)$")


def debt_plan_text(debts, extra=0.0, lump=0.0):
    av = G.simulate(debts, extra, "avalancha", lump)
    sb = G.simulate(debts, extra, "bola de nieve", lump)
    if av["imposible"]:
        return ("Con esas cuotas las deudas no bajan: los intereses se comen el pago. Lo primero es subir la cuota de la que tiene "
                "el interés más alto o pedir al banco una compra de cartera a una tasa menor.")
    today = datetime.date.today()

    def when(n):
        y, mo = divmod(today.month - 1 + n, 12)
        return f"{('enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre').split()[mo]} de {today.year + y}"
    txt = (f"Si pagas primero la de interés más alto (avalancha), quedas libre en {av['meses']} meses ({when(av['meses'])}) y pagas "
           f"{_g66_pesos(av['intereses'])} de intereses; el orden: " + ", ".join(n for n, _ in av["orden"]) + ". ")
    if sb["orden"] and [n for n, _ in sb["orden"]] != [n for n, _ in av["orden"]]:
        txt += (f"Si empiezas por la más pequeña (bola de nieve), terminas en {sb['meses']} meses y pagas {_g66_pesos(sb['intereses'])}, "
                f"pero la primera queda paga en el mes {sb['orden'][0][1]}, para que veas el avance pronto. ")
    if not extra and not lump:
        base = G.simulate(debts, 0, "avalancha", 2_000_000)
        txt += (f"Si abonas 2 millones de la prima, terminas en {base['meses']} meses y te ahorras "
                f"{_g66_pesos(av['intereses'] - base['intereses'])} de intereses.")
    return txt


def _g66_debt_voice(text, t):
    m = _G66_DEBT_ADD.match(t)
    if m:
        raw = re.split(r"(?i)deuda\s*[:,]?\s*", G.norm(text), maxsplit=1)          # con comas y «%» (la t normalizada los quita)
        dbt = debt_parse(raw[1] if len(raw) > 1 else m.group(1))
        if not dbt:
            J.reply("Dímela así: «anota una deuda: tarjeta Éxito 3 millones al 2,1 % mensual, cuota de 250 mil» (la tasa la ves en "
                    "el extracto; puede ser mensual o efectiva anual, «28 % EA»).", "DEUDAS")
            return True
        d = g66_data()
        d["deudas"] = [x for x in d["deudas"] if x["nombre"] != dbt["nombre"]] + [dbt]
        g66_save(d)
        J.reply(f"Anotada: {dbt['nombre']}, {_g66_pesos(dbt['saldo'])} al {dbt['tasa_txt']}, cuota de {_g66_pesos(dbt['cuota'])}. "
                "Cuando estén todas: «plan para salir de deudas».", "DEUDAS")
        return True
    if _G66_DEBT_LIST.match(t):
        ds = g66_data()["deudas"]
        if not ds:
            J.reply("No tengo deudas anotadas. «Anota una deuda: … 3 millones al 2 % mensual, cuota de 250 mil».", "DEUDAS")
            return True
        J.reply(f"Debes {_g66_pesos(sum(x['saldo'] for x in ds))} en {len(ds)} deudas: " +
                "; ".join(f"{x['nombre']} {_g66_pesos(x['saldo'])} ({x['tasa_txt']})" for x in ds) + ".", "DEUDAS")
        return True
    m = _G66_DEBT_PLAN.match(t)
    if m:
        ds = g66_data()["deudas"]
        if not ds:
            J.reply("Primero anota tus deudas: «anota una deuda: tarjeta 3 millones al 2 % mensual, cuota de 250 mil».", "DEUDAS")
            return True
        rest = re.split(r"deudas", G.norm(text), maxsplit=1)[-1]
        lump = re.search(rf"\b(?:abonando|abono|con)\s+(?:la prima de\s+)?{_G66_MONEY}", rest)
        extra = re.search(rf"\b{_G66_MONEY}\s+(?:extra|mas)\s+(?:al|cada|por)\s+mes", rest)
        J.reply(J.debt_plan_text(ds, _g66_amount(extra.group(1), extra.group(2)) if extra else 0.0,
                                 _g66_amount(lump.group(1), lump.group(2)) if lump and not extra else 0.0), "DEUDAS")
        return True
    m = _G66_DEBT_DONE.match(t)
    if m:
        d = g66_data()
        q = G.norm(m.group(1))
        hit = [x for x in d["deudas"] if q in G.norm(x["nombre"]) or G.norm(x["nombre"]) in q]
        if not hit:
            return False
        d["deudas"] = [x for x in d["deudas"] if x not in hit]
        g66_save(d)
        J.reply(f"¡Felicidades! Saldaste {hit[0]['nombre']}. " + (f"Te quedan {len(d['deudas'])}: pásale esa cuota a la siguiente."
                                                                if d["deudas"] else "¡Ya no tienes deudas anotadas!"), "DEUDAS")
        return True
    return False


# ============================================================================ 4. «¿ESTO ES VERDAD?»
def fact_check(claim):
    try:
        res = J._web_results(claim[:200])
    except Exception:
        res = []
    ctx = humano.facts_text(res, 6) if res else "(no se pudo buscar en internet)"
    return J.ai_chat([{"role": "system", "content": G.factcheck_prompt() + confianza.RULE},
                      {"role": "user", "content": confianza.wrap(claim[:6000], "LO QUE HAY QUE VERIFICAR") + "\n\n" +
                       confianza.wrap(ctx, "RESULTADOS DE BÚSQUEDA")}], max_tokens=1400).strip()


_G66_FACT = re.compile(r"^(?:jarvis\s+)?(?:(?:esto|eso|esta noticia|esta cadena|este video)\s+)?(?:es|sera)\s+(?:verdad|cierto|real)\b|"
                       r"^(?:jarvis\s+)?(?:verifica|verificame|chequea|confirma)(?:me)?\s+(?:esta|esto|esa|la)\s*(?:noticia|cadena|informacion|dato)?\b|"
                       r"^(?:jarvis\s+)?es cierto que\b")


def _g66_fact_voice(text, t):
    if not _G66_FACT.match(t):
        return False
    tail = re.split(r"(?i)(?:verdad|cierto|real|noticia|cadena|información|informacion|dato|verifica(?:me)?|chequea|confirma)\s*[?:.,]*\s*",
                    text, maxsplit=1)
    claim = tail[1].strip() if len(tail) > 1 else ""
    if re.match(r"(?i)^es cierto que", text.strip()):
        claim = re.sub(r"(?i)^\s*es cierto que\s*", "", text).strip(" ?¿")
    if len(claim) < 12:
        it = _g66_recent(("imagen", "texto"))
        if not it:
            J.reply("Pégame la cadena o la noticia después de la pregunta («¿esto es verdad? …»), o súbeme la captura.", "VERIFICAR")
            return True
        claim = J._text_of_item(it) if it["tipo"] == "texto" else J.ocr(it)
    if J.state.get("ai") != "ok":
        J.reply("Para verificar necesito la IA conectada.", "VERIFICAR")
        return True
    J.reply("Lo busco en fuentes confiables…", "VERIFICAR")
    J.start_job("Verificando", lambda: J.notify(J.fact_check(claim), "VERIFICAR"), "verificar")
    return True


# ============================================================================ 2 y 5. EXTRACTO Y LABORATORIO (archivos)
_G66_STMT = re.compile(r"^(?:jarvis\s+)?(?:analiza|revisa|explicame|mira)(?:me)?\s+(?:mi|el|este)\s+(?:extracto|estado de cuenta)\b")
_G66_LAB = re.compile(r"^(?:jarvis\s+)?(?:explicame|explica|revisa|interpreta|analiza)(?:me)?\s+(?:estos|mis|los|este|el)\s+"
                      r"(?:examenes|resultados|laboratorios?|hemograma|examen de sangre)\b")


def g66_card_actions(its):
    if len(its) != 1:
        return []
    it = its[0]
    name = J.normalize(it["nombre"])
    acts = []
    if it["tipo"] == "pdf" and re.search(r"extracto|estado de cuenta|bancolombia|davivienda|bbva|tarjeta|nequi|movimientos", name):
        acts.append("extracto")
    if it["tipo"] in ("pdf", "imagen") and re.search(r"laboratorio|examen|hemograma|resultado|colesterol|glucosa|perfil|orina|lab", name):
        acts.append("laboratorio")
    return [{"a": a, "t": G66_ACTIONS[a]} for a in acts]


def g66_attach(its, action, pregunta=""):
    if action == "extracto":
        J.notify(J.ask_files(its, G.statement_prompt()), "EXTRACTO")
    elif action == "laboratorio":
        J.notify(J.ask_files(its, G.lab_prompt()), "EXÁMENES")
    return None


def _g66_file_voice(text, t):
    for rx, kinds, action, ask in ((_G66_STMT, ("pdf",), "extracto", "Súbeme el PDF del extracto y toca «Analizar extracto»."),
                                   (_G66_LAB, ("pdf", "imagen"), "laboratorio", "Súbeme el resultado (PDF o foto) y toca «Explicar exámenes».")):
        if rx.match(t):
            it = _g66_recent(kinds)
            if not it:
                J.reply(ask, "ADJUNTOS")
                return True
            J.reply(f"Leo «{it['nombre']}»…", "ADJUNTOS")
            J.start_job("Leyendo el archivo", lambda: J.g66_attach([it], action), action)
            return True
    return False


# ============================================================================ 6. PROFESOR DE INGLÉS
_G66_EN = re.compile(r"^(?:jarvis\s+)?(?:practiquemos|practicar|quiero practicar|vamos a practicar|hablemos en|hablame en|ayudame a practicar)\s+"
                     r"(?:el\s+)?ingles\s+(?:en vivo|hablando|conversando|por voz)(?:\s+(?:nivel\s+)?(basico|intermedio|avanzado))?"
                     r"(?:\s+(?:sobre|de|acerca de)\s+(.+))?$")          # (sin «en vivo», sigue la práctica escrita de 12.21)
_G66_EN_END = re.compile(r"^(?:jarvis\s+)?(?:terminemos|termina|acaba|deja)\s+(?:la\s+)?(?:practica|clase)(?: de ingles)?(?: en vivo)?$")


def g66_tutor_ctx():
    return G.tutor_rule(g66_tutor["level"], g66_tutor["topic"]) if g66_tutor["on"] else ""


def g66_tutor_review():
    """Al terminar: el repaso de errores y palabras nuevas, en Word."""
    if not g66_tutor["on"]:
        return None
    g66_tutor["on"] = False
    hist = [m for m in J.chat_history if m.get("t", 0) >= g66_tutor["start"] and m.get("role") in ("user", "assistant")] \
        if any("t" in m for m in J.chat_history) else J.chat_history[-40:]
    tr = "\n".join(f"{'Estudiante' if m['role'] == 'user' else 'Tutor'}: {m['content']}" for m in hist if m.get("content"))
    if len(tr) < 80:
        return None
    try:
        rev = J.ai_chat([{"role": "user", "content": G.review_prompt(tr)}], max_tokens=1500)
    except J.AIError:
        return None
    doc = J.Document()
    doc.add_heading(f"Repaso de inglés · {datetime.date.today():%d/%m/%Y}", 0)
    for line in str(rev).splitlines():
        if line.strip():
            doc.add_paragraph(line.strip().strip("*#"))
    folder = os.path.join(J.settings["output_dir"], "Inglés")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"Repaso {datetime.datetime.now():%Y-%m-%d %H%M}.docx")
    doc.save(path)
    J.notify("¡Buena práctica! Te dejé el repaso con tus errores y las palabras nuevas, en Documentos, Jarvis, Inglés.", "INGLÉS")
    return path


def _g66_en_voice(text, t):
    m = _G66_EN.match(t)
    if m:
        g66_tutor.update(on=True, level=m.group(1) or "basico", topic=(m.group(2) or "").strip(), start=__import__("time").time())
        if J.live_mode() != "vivo":
            g66_tutor["on"] = False
            J.reply("Para conversar en inglés uso la conversación en vivo, y ahora no está disponible (necesita la clave de Gemini y el "
                    "modo «en vivo» en Ajustes › Voz).", "INGLÉS")
            return True
        J.reply("Let's practice! Te hablo en inglés y te corrijo con suavidad. Cuando quieras terminar, di «terminemos la práctica».", "INGLÉS")
        if not J.live_start():
            g66_tutor["on"] = False
            J.reply("No pude abrir la conversación en vivo ahora mismo; inténtalo en un momento.", "INGLÉS")
        return True
    if _G66_EN_END.match(t) and g66_tutor["on"] and J.live.get("active"):
        J.live_stop("terminaste la práctica")
        J.start_job("Repaso de inglés", J.g66_tutor_review, "ingles")
        return True
    return False


def general66_voice(text, t):
    for fn in (_g66_claim_voice, _g66_debt_voice, _g66_fact_voice, _g66_file_voice, _g66_en_voice):
        if fn(text, t):
            return True
    return False


__all__ = ['G66_ACTIONS', '_G66_ANSWERED', '_G66_DEBT_ADD', '_G66_DEBT_DONE', '_G66_DEBT_LIST', '_G66_DEBT_PLAN', '_G66_EN', '_G66_EN_END',
           '_G66_FACT', '_G66_FILED', '_G66_LAB', '_G66_LIST', '_G66_MONEY', '_G66_NEW', '_G66_SHORT', '_G66_STMT', '_g66_amount',
           '_g66_claim_voice', '_g66_debt_voice', '_g66_en_voice', '_g66_fact_voice', '_g66_file_voice', '_g66_find_claim',
           '_g66_holidays', '_g66_lock', '_g66_orig_tail', '_g66_path', '_g66_pesos', '_g66_recent', 'claim_filed', 'claim_make',
           'debt_parse', 'debt_plan_text', 'fact_check', 'g66_attach', 'g66_card_actions', 'g66_data', 'g66_save', 'g66_tutor',
           'g66_tutor_ctx', 'g66_tutor_review', 'general66_tick', 'general66_voice']
