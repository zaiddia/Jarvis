"""12.40: tu profesor particular de lo que quieras (modo general).

- «quiero aprender inglés» (o guitarra, Excel, cocina…, «desde cero», «nivel intermedio», «15 minutos al día»): arma un plan
  de 24 lecciones cortas.
- «dame la lección de hoy» / «lección de inglés»: explicación corta, ejemplos y 4 ejercicios que respondes uno por uno
  («pista», «no sé», «salir de la lección»). Lo que aprendes queda en tarjetas de repaso.
- «repasa inglés»: las tarjetas que tocan hoy (repetición espaciada: lo que sabes vuelve más tarde, lo que fallas, mañana).
- «practica inglés conmigo»: conversación en el idioma; Jarvis contesta en inglés y, si te equivocas, agrega
  «Corrección: …» en español. En la voz en vivo funciona hablando. «Termina la práctica» para salir.
- «¿cómo voy en inglés?»: lecciones hechas, racha, tarjetas dominadas y porcentaje de acierto.
- «recuérdame practicar inglés a las 6 de la tarde»: el recordatorio diario (por defecto a las 7 de la noche).
"""
import datetime
import json
import os
import re
import threading
import time

import cursopersonal as CP
from nucleo import J

_st = {"lock": threading.Lock(), "session": None, "convo": ""}
CP_ORIGIN = "PROFESOR"
CONVO_IDLE = 30 * 60


def _cp_path():
    return os.path.join(J.CONFIG_DIR, "cursos_personales.json")


def cp_load():
    try:
        with open(_cp_path(), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d.setdefault("cursos", {})
    d.setdefault("activo", "")
    return d


def cp_save(d):
    tmp = _cp_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _cp_path())


def _find(d, t):
    """El curso que nombra la frase, o el activo."""
    nt = CP.norm(t)
    for k, c in d["cursos"].items():
        name = CP.norm(c["tema"])
        if name and (name in nt or name.split()[0] in nt.split()):
            return k, c
    k = d.get("activo")
    return (k, d["cursos"][k]) if k in d["cursos"] else (None, None)


# ---------------------------------------------------------------- frases
_LEARN = re.compile(r"^(?:jarvis[ ,]+)?(?:oye[ ,]+)?(?:quiero|quisiera|me gustaria|necesito|voy a)\s+(?:aprender|estudiar|mejorar(?: mi| en)?)\s+(?:a\s+)?(.+)$|"
                    r"^(?:jarvis[ ,]+)?(?:enseñame|ensename|ayudame a aprender|se mi profesor(?:a)? de)\s+(?:a\s+)?(.+)$")
_LESSON = re.compile(r"\b(?:dame|empecemos|empieza|hagamos|quiero)\s+(?:la\s+|mi\s+)?leccion(?:\s+de\s+hoy)?\b|^(?:jarvis[ ,]+)?(?:la\s+)?leccion de (?:hoy|[a-z ]{3,30})$|"
                     r"\b(?:siguiente|proxima|otra)\s+leccion\b|\bhora de (?:estudiar|practicar)\b")
_REVIEW = re.compile(r"\b(?:repasa|repasemos|repaso|haz el repaso|tarjetas)\b(?:\s+(?:de\s+)?(.+))?$")
_CONVO = re.compile(r"\b(?:practica|practiquemos|conversemos|hablemos|charlemos)\s+(?:en\s+)?(ingles|frances|portugues|aleman|italiano|japones|chino|coreano|ruso)(?:\s+conmigo)?\b|"
                    r"\b(?:practica|practiquemos|conversa)\s+(?:conmigo\s+)?(?:en\s+)?(ingles|frances|portugues|aleman|italiano|japones|chino|coreano|ruso)\b")
_CONVO_OFF = re.compile(r"\b(?:termina|terminar|para|deja|sal de|salir de|acaba)\s+(?:la\s+)?(?:practica|conversacion)(?:\s+(?:de|en)\s+\w+)?\b|"
                        r"\b(?:stop|end) (?:the )?practice\b")
_HOW = re.compile(r"\bcomo voy (?:en|con)\s+(?:el curso de\s+|mi\s+)?(.+?)\??$|\bmi progreso (?:en|de)\s+(.+?)\??$|\bque cursos (?:tengo|estoy haciendo)\b")
_REMIND = re.compile(r"\brecuerdame (?:practicar|estudiar|la leccion de)\s+(.+?)\s+a las\s+(.+)$")
_DROP = re.compile(r"\b(?:borra|elimina|deja|abandona|quita)\w*\s+(?:el\s+)?curso de\s+(.+)$")
_EXIT = re.compile(r"^(?:salir|sal|terminar|termina|para|basta|ya no|cancela|cancelar)(?:\s+(?:de\s+|del\s+)?(?:la\s+|el\s+)?(?:leccion|repaso|practica))?$|"
                   r"\b(?:salir|sal|termina|cancela)\s+(?:de\s+|del\s+)?(?:la\s+|el\s+)?(?:leccion|repaso)\b")
_HINT = re.compile(r"^(?:pista|una pista|dame una pista|ayuda|ayudame|hint)$")
_SKIP = re.compile(r"^(?:no se|no lo se|no tengo idea|paso|siguiente|saltar|salta|ni idea|no me acuerdo)$")


# ---------------------------------------------------------------- crear el curso
def make_course(tema, nivel, minutos, meta=""):
    c = CP.new_course(tema, nivel, meta, minutos)
    if J.state.get("ai") == "ok":
        try:
            c["plan"] = CP.parse_plan(J.ai_chat([{"role": "user", "content": CP.plan_prompt(c)}], json_mode=True, max_tokens=2500))
        except Exception as e:
            J.log_terminal(f"Profesor particular: no pude armar el plan ({e}).", "AVISO")
    return c


def learn_voice_start(text, t):
    m = _LEARN.match(t)
    if not m:
        return False
    raw = (m.group(1) or m.group(2) or "").strip(" .?!")
    if re.match(r"(?:lo que|que|todo lo que)\s+(?:sabes|puedes|haces)\b|usarte\b|usar (?:a )?jarvis\b|a usar(?:te)?\b", raw):
        return False
    raw = re.sub(r"\s*,?\s*(?:desde cero|de cero|nivel \w+|principiante|basico|intermedio|avanzado)\b", "", raw)
    raw = re.sub(r"\s*,?\s*(?:unos\s+)?\d{1,2}\s*(?:minutos|min)\b.*$", "", raw).strip(" ,")
    meta = ""
    mm = re.search(r"\s+(?:para|porque)\s+(.+)$", raw)
    if mm:
        meta, raw = mm.group(1), raw[:mm.start()]
    if not raw or len(raw.split()) > 6 or re.search(r"\b(?:comprar|a manejar el pc)\b", raw):
        return False
    if J.state.get("ai") != "ok":
        J.reply("Para armarte el curso necesito la IA conectada.", CP_ORIGIN)
        return True
    tema = CP.LANGS.get(raw, raw)
    nivel, minutos = CP.level_in(t), CP.minutes_in(t)

    def work():
        c = make_course(tema, nivel, minutos, meta)
        if not c["plan"]:
            J.reply(f"No pude armar el plan de {tema} ahora. Inténtalo en un momento.", CP_ORIGIN)
            return
        with _st["lock"]:
            d = cp_load()
            d["cursos"][CP.slug(tema)] = c
            d["activo"] = CP.slug(tema)
            cp_save(d)
        first = "; ".join(x["titulo"] for x in c["plan"][:3])
        lang = CP.language_of(tema)
        J.reply(f"Listo: tu curso de {tema} (nivel {nivel}) tiene {len(c['plan'])} lecciones de {minutos} minutos. Empieza con: {first}. "
                f"Di «dame la lección de hoy» para empezar" + (" o «practica " + lang + " conmigo» para conversar" if lang else "") +
                f". Te recuerdo practicar todos los días a las {c['hora']} (puedes cambiarlo: «recuérdame practicar {tema} a las 6 de la tarde»).", CP_ORIGIN)
    J.reply(f"Te armo un curso de {tema} con lecciones de {minutos} minutos…", CP_ORIGIN)
    J.start_job("Armando tu curso", work, "curso")
    return True


# ---------------------------------------------------------------- lección y repaso (respondes uno por uno)
def _ask_current():
    s = _st["session"]
    if not s:
        return
    if s["i"] >= len(s["items"]):
        J.finish_session()
        return
    it = s["items"][s["i"]]
    label = "Ejercicio" if s["kind"] == "leccion" else "Tarjeta"
    J.reply(f"{label} {s['i'] + 1} de {len(s['items'])}: {it['pregunta']}", CP_ORIGIN)


def start_lesson(key, c):
    n = CP.next_lesson(c)
    if not n:
        J.reply(f"¡Terminaste las {len(c['plan'])} lecciones de {c['tema']}! 🎉 Di «repasa {c['tema']}» para no olvidar, o «quiero aprender "
                f"{c['tema']} nivel intermedio» para seguir subiendo.", CP_ORIGIN)
        return
    if J.state.get("ai") != "ok":
        J.reply("Para preparar la lección necesito la IA conectada. Mientras tanto puedes decir «repasa " + c["tema"] + "».", CP_ORIGIN)
        return

    def work():
        try:
            les = CP.parse_lesson(J.ai_chat([{"role": "user", "content": CP.lesson_prompt(c, n)}], json_mode=True, max_tokens=2200))
        except Exception as e:
            J.reply(f"No pude preparar la lección: {e}", CP_ORIGIN)
            return
        if not les:
            J.reply("La lección no me salió bien; dime «dame la lección de hoy» otra vez.", CP_ORIGIN)
            return
        _st["session"] = {"kind": "leccion", "key": key, "n": n, "items": les["ejercicios"], "i": 0, "ok": 0, "hint": False,
                          "lesson": les}
        ej = (" Ejemplos: " + " · ".join(les["ejemplos"])) if les["ejemplos"] else ""
        J.reply(f"Lección {n} de {len(c['plan'])} de {c['tema']}: {c['plan'][n - 1]['titulo']}. {les['explicacion']}{ej}\n"
                "Ahora, unos ejercicios: respóndeme uno por uno (di «pista» si te atascas o «no sé» para ver la respuesta).", CP_ORIGIN)
        _ask_current()
    J.start_job("Preparando la lección", work, "leccion")


def study_review(key, c):
    due = CP.due_cards(c)
    if not due:
        nxt = min((x["proxima"] for x in c["tarjetas"]), default="")
        J.reply(f"Hoy no te toca repasar {c['tema']}" + (f"; tus próximas tarjetas son el {nxt}." if nxt else "; aún no tienes tarjetas: haz una lección primero."), CP_ORIGIN)
        return
    items = [{"pregunta": x["frente"], "respuesta": x["reverso"], "pista": "", "card": x["id"]} for x in due[:15]]
    _st["session"] = {"kind": "repaso", "key": key, "items": items, "i": 0, "ok": 0, "hint": False}
    J.reply(f"Repaso de {c['tema']}: {len(items)} tarjeta{'s' if len(items) != 1 else ''} para hoy. Dime qué va al otro lado.", CP_ORIGIN)
    _ask_current()


def _grade(c, it, answer):
    q = CP.quick_check(answer, it["respuesta"])
    if q is not None or J.state.get("ai") != "ok":
        return bool(q), ""
    try:
        ok, why = CP.parse_check(J.ai_chat([{"role": "user", "content": CP.check_prompt(c, it["pregunta"], it["respuesta"], answer)}],
                                           json_mode=True, max_tokens=200))
        return bool(ok), why
    except Exception:
        return False, ""


def session_answer(text, t):
    """Mientras hay lección o repaso, lo que dices es tu respuesta (salvo «salir» o una orden corta de siempre)."""
    s = _st["session"]
    if not s:
        return False
    if _EXIT.search(t):
        _st["session"] = None
        J.reply("Listo, dejamos la " + ("lección" if s["kind"] == "leccion" else "práctica") + " aquí. Lo que alcanzaste a hacer quedó guardado.", CP_ORIGIN)
        return True
    words = t.split()
    if len(words) <= 6 and words and words[0][:5] in J.nl_starters() and not _HINT.match(t) and not _SKIP.match(t):
        return False                                   # «sube el volumen» en medio de la lección: es una orden
    d = cp_load()
    c = d["cursos"].get(s["key"])
    if not c:
        _st["session"] = None
        return False
    it = s["items"][s["i"]]
    if _HINT.match(t):
        J.reply(f"Pista: {it['pista']}" if it.get("pista") else "Piensa en la explicación de la lección; inténtalo, aunque no estés seguro.", CP_ORIGIN)
        s["hint"] = True
        return True
    if _SKIP.match(t):
        ok, why = False, ""
        J.reply(f"Era: {it['respuesta']}. La volveremos a ver pronto.", CP_ORIGIN)
    else:
        ok, why = _grade(c, it, text)
        J.reply(("¡Bien! ✅ " if ok else f"Casi. La respuesta es: {it['respuesta']}. ") + (why if why else ""), CP_ORIGIN)
    with _st["lock"]:
        d = cp_load()
        c = d["cursos"].get(s["key"]) or c
        c["intentos"] += 1
        c["aciertos"] += 1 if ok else 0
        if s["kind"] == "repaso":
            for card in c["tarjetas"]:
                if card["id"] == it.get("card"):
                    CP.review(card, ok)
        elif not ok:                                     # lo que fallas en la lección vuelve como tarjeta mañana
            CP.add_cards(c, [{"frente": it["pregunta"], "reverso": it["respuesta"]}])
        d["cursos"][s["key"]] = c
        cp_save(d)
    s["ok"] += 1 if ok else 0
    s["i"] += 1
    s["hint"] = False
    _ask_current()
    return True


def finish_session():
    s = _st["session"]
    _st["session"] = None
    if not s:
        return
    with _st["lock"]:
        d = cp_load()
        c = d["cursos"].get(s["key"])
        if not c:
            return
        if s["kind"] == "leccion":
            if s["n"] not in c["hechas"]:
                c["hechas"].append(s["n"])
            CP.add_cards(c, s["lesson"]["tarjetas"])
        CP.mark_day(c)
        d["cursos"][s["key"]] = c
        cp_save(d)
    p = CP.progress(c)
    msg = f"Terminamos: {s['ok']} de {len(s['items'])} bien. "
    if s["kind"] == "leccion":
        msg += f"Llevas {p['lecciones']} de {p['total']} lecciones. "
        if s["lesson"].get("practica"):
            msg += f"Para practicar por tu cuenta: {s['lesson']['practica']} "
    msg += f"Racha: {p['racha']} día{'s' if p['racha'] != 1 else ''} seguido{'s' if p['racha'] != 1 else ''}. 🔥" if p["racha"] > 1 else "¡Mañana seguimos!"
    J.reply(msg, CP_ORIGIN)


# ---------------------------------------------------------------- conversación en el idioma
def study_ctx():
    """Lo que se le agrega a la IA (chat y voz en vivo) mientras practicas conversación."""
    key = _st["convo"]
    if not key:
        return ""
    c = cp_load()["cursos"].get(key)
    return CP.conversation_rule(c) if c else ""


def start_convo(lang):
    with _st["lock"]:
        d = cp_load()
        key = CP.slug(lang)
        if key not in d["cursos"]:
            d["cursos"][key] = CP.new_course(lang)            # sin plan todavía: igual puedes conversar
        d["activo"] = key
        cp_save(d)
    _st["convo"], _st["convo_t"] = key, time.time()
    c = d["cursos"][key]
    try:
        if J.live.get("active"):
            J.live_stop("práctica de idioma")              # la próxima vez que hables abre con la regla de la práctica
    except Exception:
        pass
    J.reply(f"¡Vamos! Desde ahora te hablo en {lang} (nivel {c['nivel']}) y, si te equivocas, te corrijo en español. Hablando funciona "
            "mejor con la voz en vivo; escribiendo también vale. Para terminar: «termina la práctica».", CP_ORIGIN)


def end_convo():
    key, _st["convo"] = _st["convo"], ""
    if not key:
        return False
    with _st["lock"]:
        d = cp_load()
        c = d["cursos"].get(key)
        if c:
            CP.mark_day(c)
            cp_save(d)
    try:
        if J.live.get("active"):
            J.live_stop("fin de la práctica")
    except Exception:
        pass
    J.reply("Terminamos la práctica. ¡Bien hecho! Lo cuento en tu racha.", CP_ORIGIN)
    return True


def convo_answer(text, t):
    """En la práctica de conversación, lo que no es una orden va directo a la IA (con la regla del idioma), sin pasar por
    la comprensión de órdenes en español (una llamada menos y nada de confusiones con frases en inglés)."""
    if not _st["convo"] or _CONVO_OFF.search(t) or _EXIT.match(t):
        return False
    if time.time() - _st.get("convo_t", time.time()) > CONVO_IDLE:   # media hora sin hablar: la práctica terminó sola
        _st["convo"] = ""
        J.log_terminal("La práctica de idioma terminó sola (media hora sin hablar).", CP_ORIGIN)
        return False
    _st["convo_t"] = time.time()
    words = t.split()
    if words and words[0][:5] in J.nl_starters() and len(words) <= 6:
        return False
    if J.state.get("ai") != "ok":
        J.reply("Para conversar necesito la IA conectada.", CP_ORIGIN)
        return True
    if getattr(J._tl, "remote", False) or getattr(J._tl, "capture", None) is not None:
        J.reply(J.ask_ai(text), CP_ORIGIN)
    else:
        J.answer_question_streaming(text)
    return True


# ---------------------------------------------------------------- voz
def study_voice(text, t):
    if _st["convo"] and _CONVO_OFF.search(t):
        return end_convo()
    m = _CONVO.search(t)
    if m:
        lang = CP.LANGS.get(m.group(1) or m.group(2))
        start_convo(lang)
        return True
    if learn_voice_start(text, t):
        return True
    m = _REMIND.search(t)
    if m:
        d = cp_load()
        key, c = _find(d, m.group(1))
        hh = J._hh(m.group(2))
        if not c or not hh:
            return False
        c["hora"], c["aviso"] = hh, ""
        d["cursos"][key] = c
        cp_save(d)
        J.reply(f"Listo: te recuerdo practicar {c['tema']} todos los días a las {hh}.", CP_ORIGIN)
        return True
    m = _DROP.search(t)
    if m:
        d = cp_load()
        key, c = _find(d, m.group(1))
        if not c or CP.norm(c["tema"]).split()[0] not in CP.norm(m.group(1)):
            return False
        d["cursos"].pop(key, None)
        if d["activo"] == key:
            d["activo"] = next(iter(d["cursos"]), "")
        cp_save(d)
        J.reply(f"Borré el curso de {c['tema']}.", CP_ORIGIN)
        return True
    m = _HOW.search(t)
    if m:
        d = cp_load()
        if not d["cursos"]:
            return False
        if not (m.group(1) or m.group(2)):
            J.reply("Tus cursos: " + "; ".join(f"{c['tema']} ({len(c['hechas'])} de {len(c['plan'])} lecciones)" for c in d["cursos"].values()) + ".", CP_ORIGIN)
            return True
        key, c = _find(d, m.group(1) or m.group(2))
        if not c or CP.norm(c["tema"]).split()[0] not in CP.norm(m.group(1) or m.group(2) or ""):
            return False
        p = CP.progress(c)
        J.reply(f"En {c['tema']} llevas {p['lecciones']} de {p['total']} lecciones, {p['dias']} día{'s' if p['dias'] != 1 else ''} de práctica "
                f"(racha de {p['racha']}), {p['tarjetas']} tarjetas ({p['dominadas']} ya dominadas, {p['pendientes']} para repasar hoy)"
                + (f" y {p['acierto']} % de acierto" if p["acierto"] is not None else "") + ".", CP_ORIGIN)
        return True
    if _LESSON.search(t) and not re.match(r"(?:olvida|borra|quita|elimina)", t):
        d = cp_load()
        key, c = _find(d, t)
        if not c and not re.search(r"\b(?:dame|empecemos|empieza|hagamos)\b|leccion de hoy", t):
            return False
        if not c:
            if "leccion" in t:
                J.reply("Aún no tienes un curso. Di «quiero aprender» y lo que quieras: inglés, guitarra, Excel…", CP_ORIGIN)
                return True
            return False
        d["activo"] = key
        cp_save(d)
        start_lesson(key, c)
        return True
    m = _REVIEW.search(t)
    if m and ("repas" in t or "tarjetas" in t):
        d = cp_load()
        key, c = _find(d, m.group(1) or t)
        if not c:
            return False
        study_review(key, c)
        return True
    return False


# ---------------------------------------------------------------- recordatorio diario
def study_tick(now=None):
    now = now or datetime.datetime.now()
    today = now.date().isoformat()
    sent = []
    with _st["lock"]:
        d = cp_load()
        changed = False
        for key, c in d["cursos"].items():
            if not c.get("plan") or not c.get("hora") or c.get("aviso") == today or today in c.get("dias", []):
                continue
            if now.strftime("%H:%M") < c["hora"]:
                continue
            c["aviso"] = today
            changed = True
            sent.append(c["tema"])
        if changed:
            cp_save(d)
    for tema in sent:
        c = next(x for x in d["cursos"].values() if x["tema"] == tema)
        p = CP.progress(c)
        J.notify(f"Te toca tu práctica de {tema} ({c['minutos']} minutos)." + (f" No pierdas tu racha de {p['racha']} días. 🔥" if p["racha"] > 1 else "") +
                 " Di «dame la lección de hoy»" + (f" o «repasa {tema}» ({p['pendientes']} tarjetas)" if p["pendientes"] else "") + ".", "RECORDATORIO")
    return sent


__all__ = ['CONVO_IDLE', 'CP_ORIGIN', '_CONVO', '_CONVO_OFF', '_DROP', '_EXIT', '_HINT', '_HOW', '_LEARN', '_LESSON', '_REMIND', '_REVIEW', '_SKIP', '_ask_current',
           '_cp_path', '_find', '_grade', '_st', 'convo_answer', 'cp_load', 'cp_save', 'end_convo', 'finish_session', 'learn_voice_start', 'make_course',
           'session_answer', 'start_convo', 'start_lesson', 'study_review', 'study_ctx', 'study_tick', 'study_voice']
