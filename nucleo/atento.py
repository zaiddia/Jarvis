"""9.3: «¿qué necesita mi atención?» y su pulso cada hora, compromisos y correos por responder, y material de clase a partir
de un enlace o de un texto que pegas (también la lectura nivelada en tres niveles).

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import re
import threading
import time

import aprobaciones
import atencion
import aula
import calendario
import compromisos
import errores
import horario
import investigar
import notas
import seguimiento
from nucleo import J


# ============================================================================ ¿QUÉ NECESITA MI ATENCIÓN?
def attention_items(now=None):
    now = now or datetime.datetime.now()
    today = now.date()
    out = []
    for a in aprobaciones.pending():
        out.append({"k": f"ap:{a['id']}", "p": 1, "t": f"aprobar «{a['titulo'][:70]}»", "cmd": "¿qué tengo por aprobar?"})
    for x in compromisos.pending():
        st = compromisos.status(x, today)
        if st in ("vencido", "hoy"):
            out.append({"k": f"co:{x['id']}:{st}", "p": 1, "t": ("se venció: " if st == "vencido" else "hoy: ") + x["texto"][:80],
                        "cmd": "¿qué compromisos tengo?"})
        elif st == "mañana":
            out.append({"k": f"co:{x['id']}:m", "p": 2, "t": "mañana: " + x["texto"][:80], "cmd": "¿qué compromisos tengo?"})
    msgs = J.mail_cache.get("msgs") or []
    owe = compromisos.to_answer(msgs, J.settings["email_address"])
    if owe:
        out.append({"k": "mail:" + "|".join(sorted(m.get("msgid") or m.get("asunto", "") for m in owe))[:200], "p": 2,
                    "t": f"responder {len(owe)} correo{'s' if len(owe) != 1 else ''} (" + ", ".join(m["de_nombre"][:20] for m in owe[:3]) + ")",
                    "cmd": "¿qué correos debo responder?"})
    for n in notas.pending():
        if n.get("fecha") and n["fecha"] <= today.isoformat():
            late = n["fecha"] < today.isoformat()
            out.append({"k": f"no:{n.get('id')}", "p": 1 if late else 2, "t": ("atrasado: " if late else "hoy: ") + notas.what(n)[:80],
                        "cmd": "¿qué tengo pendiente?"})
    nx, day = horario.next_class(now)
    if nx and day == today:
        mins = int((datetime.datetime.combine(today, datetime.time(*map(int, nx["inicio"].split(":")))) - now).total_seconds() // 60)
        if 0 <= mins <= 60:
            out.append({"k": f"cl:{today}:{nx['inicio']}", "p": 2, "t": f"en {mins} min tienes {horario.label(nx)}",
                        "cmd": "prepárame la próxima clase de "})
    try:
        for e in calendario.upcoming(limit=5):
            if e["todo_el_dia"] or e["inicio"][:10] != today.isoformat():
                continue
            mins = int((datetime.datetime.fromisoformat(e["inicio"]).replace(tzinfo=None) - now).total_seconds() // 60)
            if 0 <= mins <= 120:
                out.append({"k": f"ev:{e.get('uid')}:{e['inicio']}", "p": 1 if mins <= 30 else 2, "t": f"en {mins} min: {e['titulo'][:60]}",
                            "cmd": "¿qué tengo hoy?"})
    except Exception:
        pass
    for course in sorted(set(aula.data.get("cursos", {})) | set(seguimiento.data), key=aula.course_sort_key)[:24]:
        names = sorted(set(aula.students(course)) | set(seguimiento.data.get(course, {})))
        r = seguimiento.at_risk(course, names, J._absences(course), J.settings["risk_grade"], J.settings["risk_absences"])
        if r:
            out.append({"k": f"ri:{course}:{len(r)}", "p": 3, "t": f"{len(r)} en riesgo en {course}", "cmd": f"¿quiénes están en riesgo en {course}?"})
    try:
        for a in J.early_alerts(today) if J.settings.get("early_alerts", True) else []:
            if a["tipo"] != "mejora":
                out.append({"k": "ea:" + a["k"], "p": 2, "t": f"{a['estudiante']} ({a['curso']}) {a['detalle']}"[:110],
                            "cmd": f"muéstrame a {a['estudiante']} de {a['curso']}"})
    except Exception:
        pass
    try:
        out += J.year_attention()                      # 10.2: quién puede perder el año
        out += J.plan_attention()                      # 10.8: dónde vas atrasado con la planeación
    except Exception:
        pass
    day_ago = (now - datetime.timedelta(days=1)).isoformat()
    errs = [e for e in errores.recent(50) if e["t"] >= day_ago and e["nivel"] == "error"]
    if errs:
        out.append({"k": f"er:{errs[-1]['t']}", "p": 3, "t": f"{len(errs)} error{'es' if len(errs) != 1 else ''} de Jarvis hoy",
                    "cmd": "genera el informe de errores"})
    return atencion.order(out)


_ATT_RE = re.compile(r"\b(?:que|en que)\s+(?:necesita|requiere|merece)\s+mi atencion\b|\bque es (?:lo )?urgente\b|\bque tengo (?:de )?urgente\b|"
                     r"\ben que (?:debo|deberia) enfocarme\b|\bque me falta hacer\b|\bque hay pendiente(?: para hoy)?\b|\bque debo hacer ahora\b|"
                     r"\bque tengo que atender\b")


def attention_voice(text, t):
    if not _ATT_RE.search(t):
        return False
    items = J.attention_items()
    _pulse["seen"].update(x["k"] for x in items)
    J.reply(atencion.spoken(items), "ATENCIÓN")
    return True


_pulse = {"seen": set(), "last": 0.0}


def attention_tick(now=None):
    """El pulso: cada hora (en tu horario de trabajo) avisa solo de lo nuevo e importante. Devuelve lo avisado."""
    now = now or datetime.datetime.now()
    s = J.settings
    if not s["attention_pulse"] or not (s["attention_from"] <= now.hour < s["attention_to"]) or now.weekday() >= 5 and not s["attention_weekend"]:
        return []
    if now.timestamp() - _pulse["last"] < 55 * 60:
        return []
    _pulse["last"] = now.timestamp()
    new = atencion.new_items(J.attention_items(now), _pulse["seen"])
    if not new:
        return []
    _pulse["seen"].update(x["k"] for x in new)
    msg = "Necesita tu atención: " + "; ".join(x["t"] for x in new[:4]) + ("…" if len(new) > 4 else "") + "."
    J.notice_add(msg, "aviso", "ATENCIÓN")
    J.push_chat("jarvis", msg, "ATENCIÓN")
    if s["attention_phone"]:
        J.phone_send("🧭 " + msg)
    return new


# ============================================================================ COMPROMISOS Y CORREOS POR RESPONDER
_CO_LIST = re.compile(r"\b(?:que|cuales)\s+(?:compromisos|promesas)\s+(?:tengo|me faltan|hay)\b|\bmis compromisos\b|\bque prometi\b|"
                      r"\ben que quede\b")
_CO_OWE = re.compile(r"\b(?:que|cuales)\s+correos\s+(?:debo|tengo que|me falta|me faltan|falta)\s+(?:responder|contestar)\b|"
                     r"\bcorreos (?:pendientes|por responder|sin responder)\b|\ba quien le debo (?:respuesta|un correo)\b")
_CO_DISCARD = re.compile(r"\b(?:ese|el) correo (?:de (.+?) )?no (?:necesita|requiere) respuesta\b|\bdescarta el correo de (.+)$")


def commitments_voice(text, t):
    c = compromisos.parse_voice(t)
    if c:
        orig = re.split(r"\b(?:quedé|quede|me comprometí|me comprometi|prometí|prometi|me toca|compromiso(?: de)?:?)\s+(?:en\s+|a\s+|con\s+)?",
                        text, maxsplit=1, flags=re.I)
        x = compromisos.add(orig[-1] if len(orig) > 1 else c)
        when = f" para el {x['fecha'][8:10]}/{x['fecha'][5:7]}" + (f" a las {x['hora']}" if x["hora"] else "") if x["fecha"] else ""
        J.reply(f"Anotado el compromiso{when}: {x['texto']}. Te lo recuerdo a tiempo.", "COMPROMISOS")
        return True
    if _CO_LIST.search(t):
        J.reply(compromisos.spoken(compromisos.pending()), "COMPROMISOS")
        return True
    if _CO_OWE.search(t):
        owe = compromisos.to_answer(J.mail_cache.get("msgs") or [], J.settings["email_address"])
        if not (J.mail_cache.get("msgs")):
            J.reply("Aún no he leído tu correo. Pregúntame «¿qué correos importantes tengo?» y luego te digo cuáles piden respuesta.", "COMPROMISOS")
        elif not owe:
            J.reply("No tienes correos pendientes por responder. 👌", "COMPROMISOS")
        else:
            J.reply(f"Te toca responder {len(owe)}: " + "; ".join(f"{m['de_nombre']} («{m['asunto'][:50]}»)" for m in owe[:6]) +
                    ". Di «contéstale a … que …» o «ese correo de … no necesita respuesta».", "COMPROMISOS")
        return True
    m = _CO_DISCARD.search(t)
    if m:
        who = (m.group(1) or m.group(2) or "").strip()
        owe = compromisos.to_answer(J.mail_cache.get("msgs") or [], J.settings["email_address"])
        hit = next((x for x in owe if not who or J.normalize(who) in J.normalize(x["de_nombre"] + " " + x["de"])), None)
        if not hit:
            J.reply("No encuentro ese correo entre los pendientes.", "COMPROMISOS")
        else:
            compromisos.mark_answered(hit, discard=True)
            J.reply(f"Listo, ya no te lo recuerdo: {hit['de_nombre']}.", "COMPROMISOS")
        return True
    m = compromisos._DONE.match(t)
    if m and compromisos.pending():
        x = compromisos.find(m.group(1) or t)
        if x:
            compromisos.done(x["id"])
            J.reply(f"¡Bien! Marqué como cumplido: {x['texto']}.", "COMPROMISOS")
            return True
    return False


_co_warned = {}


def commitments_tick(now=None):
    """Recuerda el compromiso el día antes (desde las 5 p. m.) y el mismo día (desde las 7 a. m.). Devuelve lo avisado."""
    now = now or datetime.datetime.now()
    said = []
    for x in compromisos.pending():
        st = compromisos.status(x, now.date())
        key = None
        if st == "mañana" and now.hour >= 17:
            key = f"{x['id']}:antes"
        elif st == "hoy" and now.hour >= 7:
            key = f"{x['id']}:hoy"
        if key and key not in _co_warned:
            _co_warned[key] = True
            J.alert(("Mañana" if st == "mañana" else "Hoy") + f" tienes este compromiso: {x['texto']}.", "COMPROMISOS")
            said.append(key)
    return said


def _attention_worker():
    time.sleep(240)
    while True:
        for fn in (J.commitments_tick, J.attention_tick):
            try:
                fn()
            except Exception as e:
                J.note_error("ATENCIÓN", e)
        time.sleep(120)


# ============================================================================ MATERIAL DESDE UN ENLACE O UN TEXTO
_URL = re.compile(r"https?://[^\s<>«»\"']+", re.I)


def link_material_voice(text, t):
    """«haz un quiz con este artículo https://…», «nivela este texto: …» (texto pegado)."""
    kind = aula.detect_kind(t)
    url = _URL.search(text)
    pasted = ""
    if not url:
        parts = re.split(r":\s*", text, maxsplit=1)
        if len(parts) == 2 and len(parts[1]) > 250:
            pasted = parts[1].strip()
    if not kind or not (url or pasted):
        return False
    if J.Document is None:
        J.reply("No puedo crear documentos: falta python-docx.", "ERROR")
        return True
    head = _URL.sub("", text).split(":")[0].strip() if url else text.split(":")[0].strip()
    if pasted:
        J.generate_material(f"{head}. Basado en este texto:\n{pasted[:7000]}", kind)
        return True
    link = url.group(0).rstrip(".,;)")
    J.reply("Leo la página y te preparo el material sobre ese contenido…", "AULA")

    def work():
        try:
            body = investigar.page_text(J._get_text(link, timeout=15)[:800000])
        except Exception as e:
            J.notify(f"No pude abrir la página ({e}). Copia el texto y dímelo con «nivela este texto: …».", "AULA")
            return
        if len(body) < 200:
            J.notify("Esa página casi no tiene texto que pueda leer (puede pedir inicio de sesión). Copia el texto y pégamelo.", "AULA")
            return
        J.generate_material(f"{head}. Basado en el contenido de esta página ({investigar.host(link)}):\n{body[:7000]}", kind)
    J.start_job("Leyendo la página para el material", work, "enlace")
    return True


def attention_start():
    compromisos.configure(J.CONFIG_DIR)
    threading.Thread(target=J._attention_worker, daemon=True, name="atencion").start()


__all__ = [
    '_ATT_RE', '_CO_DISCARD', '_CO_LIST', '_CO_OWE', '_URL', '_attention_worker', '_co_warned', '_pulse', 'attention_items',
    'attention_start', 'attention_tick', 'attention_voice', 'commitments_tick', 'commitments_voice', 'link_material_voice',
]
