"""12.9: el día a día del asistente general: gastos, pagos del mes, listas y la casa inteligente.

- «Gasté 20 mil en almuerzo», «compré pan por 5 mil», «¿cuánto he gastado este mes?», «¿cuánto llevo en transporte?»,
  «borra el último gasto».
- «Recuérdame pagar el internet el 15 de cada mes de 90 mil», «¿qué pagos tengo?», «ya pagué el internet»,
  «borra el pago del gimnasio». Avisa dos días antes y el mismo día (también por Telegram si lo tienes).
- «Agrega leche, pan y huevos a la lista del mercado», «¿qué hay en la lista del mercado?», «ya compré leche»,
  «quita pan de la lista del mercado», «borra la lista del mercado», «¿qué listas tengo?».
- Home Assistant: «enciende la luz de la sala», «apaga el ventilador», «luz del cuarto al 40 %».
Todo funciona igual desde Telegram. Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import json
import re
import threading
import time
import urllib.error
import urllib.request

import casa
import vidadiaria as vd
from nucleo import J

_AMT = r"(?:\$\s*)?\d[\d.,]*\s*(?:mil|millones|millon|lucas|luca|k)?(?:\s*pesos)?|un millon|mil pesos"
_G1 = re.compile(rf"^(?:jarvis[ ,]+)?(?:anota|apunta|registra|agrega)?\s*(?:un\s+)?gasto\s+de\s+({_AMT})\s+(?:en|de|por|para)\s+(.+)$")
_G2 = re.compile(rf"^(?:jarvis[ ,]+)?(?:gaste|me gaste|pague|compre|di)\s+({_AMT})\s+(?:en|de|por|para)\s+(.+)$")
_G3 = re.compile(rf"^(?:jarvis[ ,]+)?(?:gaste|me gaste|pague|compre)\s+(.+?)\s+(?:en|por|de)\s+({_AMT})$")
_G_UNDO = re.compile(r"\b(?:borra|elimina|quita|deshaz)\s+(?:el\s+)?ultimo gasto\b")
_G_ASK = re.compile(r"\bcuanto (?:he|llevo|hemos|e) gastad[oa]\b|\bcuanto (?:llevo|va) (?:gastado )?en\b|\b(?:mis|resumen de(?: mis)?) gastos\b|"
                    r"\ben que (?:he gastado|se me va la plata|gasto mas)\b")
_P_ADD = re.compile(rf"^(?:jarvis[ ,]+)?(?:recuerdame|avisame(?: para)?|agrega(?: el)? pago(?: de| del)?|anota(?: el)? pago(?: de| del)?)\s+(?:pagar\s+)?"
                    rf"(?:el |la |los |las )?(.+?)\s+(?:el|los|cada)\s+(\d{{1,2}})(?:\s+de\s+cada\s+mes|\s+de\s+todos\s+los\s+meses|\s+cada\s+mes)?"
                    rf"(?:\s+(?:de|por|que son|son)\s+({_AMT}))?$")
_P_ASK = re.compile(r"\b(?:que|cuales) (?:pagos|cuentas|recibos) tengo\b|\bmis pagos\b|\bque (?:tengo|me toca) (?:que )?pagar\b|\bque cuentas (?:vencen|tengo por pagar)\b")
_P_DONE = re.compile(r"^(?:jarvis[ ,]+)?ya\s+pague\s+(?:el |la |los |las )?(.+)$")
_P_DEL = re.compile(r"^(?:jarvis[ ,]+)?(?:borra|elimina|quita)\s+(?:el\s+)?pago\s+(?:del?\s+|de la\s+)?(.+)$")
_LS_ADD = re.compile(r"^(?:jarvis[ ,]+)?(?:agrega|agregale|anade|pon|ponme|apunta|anota|mete|incluye)\s+(.+?)\s+(?:a|en)\s+(?:la\s+|mi\s+)?lista\s+(?:de\s+la\s+|del\s+|de\s+)?(.+)$")
_LS_SHOW = re.compile(r"\b(?:que hay|que tengo|que falta|que tiene|que queda)\s+en\s+(?:la\s+|mi\s+)?lista\s+(?:de\s+la\s+|del\s+|de\s+)?(.+)$|"
                     r"^(?:jarvis[ ,]+)?(?:lee|leeme|muestrame|dime|ensename)\s+(?:la\s+|mi\s+)?lista\s+(?:de\s+la\s+|del\s+|de\s+)?(.+)$")
_LS_CHECK = re.compile(r"^(?:jarvis[ ,]+)?ya\s+(?:compre|tengo|consegui|traje|tache|marque|hice)\s+(?:el |la |los |las )?(.+)$")
_LS_DEL = re.compile(r"^(?:jarvis[ ,]+)?(?:quita|borra|saca|elimina|tacha)\s+(.+?)\s+de\s+(?:la\s+|mi\s+)?lista\s+(?:de\s+la\s+|del\s+|de\s+)?(.+)$")
_LS_CLEAR = re.compile(r"^(?:jarvis[ ,]+)?(?:borra|vacia|limpia|elimina)\s+(?:toda\s+)?(?:la\s+|mi\s+)?lista\s+(?:de\s+la\s+|del\s+|de\s+)?(.+)$")
_LS_ALL = re.compile(r"\b(?:que|cuales) listas tengo\b|^(?:jarvis[ ,]+)?mis listas$")
_ha_cache = {"t": 0.0, "ents": [], "fail": 0.0}


def _clean_concept(c):
    return re.sub(r"\s+(?:hoy|ayer|esta manana|esta tarde)$", "", c.strip(" .,")).strip()


def _when(c):
    return datetime.date.today() - datetime.timedelta(days=1) if re.search(r"\bayer\b", c) else datetime.date.today()


def expense_voice(text, t):
    v = vd.norm(text)
    for rx, amount_first in ((_G1, True), (_G2, True), (_G3, False)):
        m = rx.match(v)
        if not m:
            continue
        a, c = (m.group(1), m.group(2)) if amount_first else (m.group(2), m.group(1))
        amt = vd.parse_amount(a)
        if not amt or amt < 50:
            continue
        g = vd.add_expense(amt, _clean_concept(c), _when(c))
        p = vd.find_payment(g["concepto"])
        if p and rx is not _G3 and v.startswith(("pague", "jarvis pague")):
            vd.mark_paid(p["nombre"])
        tot, _by, _n = vd.spent("mes")
        J.reply(f"Anotado: {vd.money(amt)} en {g['concepto']} ({g['categoria']}). Este mes llevas {vd.money(tot)}.", "GASTOS")
        return True
    if _G_UNDO.search(t):
        g = vd.undo_last_expense()
        J.reply(f"Borré el gasto de {vd.money(g['monto'])} en {g['concepto']}." if g else "No hay gastos anotados.", "GASTOS")
        return True
    if _G_ASK.search(t):
        period = "hoy" if re.search(r"\bhoy\b", t) else "semana" if "semana" in t else "mes_pasado" if "mes pasado" in t else "mes"
        cat = ""
        m = re.search(r"\ben\s+(\w+)\s*$", t)
        if m and m.group(1) not in ("mes", "semana", "hoy", "total"):
            cat = vd.category(m.group(1))
            cat = "" if cat == "Otros" and m.group(1) not in ("otros", "otras") else cat
        tot, by, n = vd.spent(period, cat=cat)
        lbl = {"hoy": "hoy", "semana": "esta semana", "mes_pasado": "el mes pasado", "mes": "este mes"}[period]
        if not n:
            J.reply(f"No tengo gastos anotados {lbl}" + (f" en {cat.lower()}" if cat else "") + ". Dime, por ejemplo: «gasté 20 mil en almuerzo».", "GASTOS")
        elif cat:
            J.reply(f"En {cat.lower()} llevas {vd.money(tot)} {lbl} ({n} gasto{'s' if n != 1 else ''}).", "GASTOS")
        else:
            top = ", ".join(f"{k.lower()} {vd.money(x)}" for k, x in list(by.items())[:4])
            J.reply(f"{lbl[0].upper() + lbl[1:]} llevas {vd.money(tot)} en {n} gasto{'s' if n != 1 else ''}. Lo que más: {top}.", "GASTOS")
            J.card("gastos", f"Gastos {lbl}", "\n".join(f"{k}: {vd.money(x)}" for k, x in by.items()), "$", secs=14)
        return True
    return False


def payment_voice(text, t):
    v = vd.norm(text)
    m = _P_ADD.match(v)
    if m:
        name = m.group(1).strip()
        if name.startswith("pagar "):
            name = name[6:]
        amt = vd.parse_amount(m.group(3)) if m.group(3) else None
        p = vd.add_payment(name, int(m.group(2)), amt)
        J.reply(f"Listo: te aviso de pagar {p['nombre']} el {p['dia']} de cada mes" + (f" ({vd.money(amt)})" if amt else "") +
                ", dos días antes y el mismo día.", "PAGOS")
        return True
    if _P_ASK.search(t):
        if not vd.data["pagos"]:
            J.reply("No tienes pagos guardados. Dime, por ejemplo: «recuérdame pagar el internet el 15 de cada mes».", "PAGOS")
            return True
        soon = vd.upcoming(within=40)
        parts = [f"{p['nombre']} {vd.when_text(left)} (el {d.day})" + (f", {vd.money(p['monto'])}" if p.get("monto") else "") for p, d, left in soon]
        total = sum(p.get("monto") or 0 for p, _d, left in soon if left <= 31)
        J.reply("Tus pagos: " + "; ".join(parts) + "." + (f" En total, {vd.money(total)} al mes." if total else ""), "PAGOS")
        return True
    m = _P_DONE.match(v)
    if m and vd.find_payment(m.group(1)):
        p = vd.mark_paid(m.group(1))
        J.reply(f"Anotado: {p['nombre']} pagado este mes. Te aviso del próximo.", "PAGOS")
        return True
    m = _P_DEL.match(v)
    if m:
        p = vd.remove_payment(m.group(1))
        J.reply(f"Borré el pago de {p['nombre']}." if p else "No encontré ese pago. Di «¿qué pagos tengo?».", "PAGOS")
        return True
    return False


def list_voice(text, t):
    v = vd.norm(text)
    m = _LS_ADD.match(v)
    if m and vd.list_name(m.group(2)):
        lst = vd.list_name(m.group(2))
        added = vd.add_items(lst, vd.split_items(m.group(1)))
        n = len(vd.pending_items(lst))
        J.reply((f"Agregué {', '.join(added)} a la lista de {lst}." if added else "Eso ya estaba en la lista.") + f" Tiene {n} cosa{'s' if n != 1 else ''}.",
                "LISTAS")
        return True
    m = _LS_SHOW.search(v)
    if m and vd.list_name(m.group(1) or m.group(2)):
        lst = vd.list_name(m.group(1) or m.group(2))
        items = vd.pending_items(lst)
        J.reply(f"En la lista de {lst}: {', '.join(items)}." if items else f"La lista de {lst} está vacía.", "LISTAS")
        if items:
            J.card("lista", f"Lista de {lst}", "\n".join("• " + x for x in items), "☰", secs=16)
        return True
    m = _LS_DEL.match(v)
    if m and vd.list_name(m.group(2)):
        lst = vd.list_name(m.group(2))
        gone = vd.remove_items(lst, vd.split_items(m.group(1)))
        J.reply(f"Quité {', '.join(gone)} de la lista de {lst}." if gone else f"Eso no estaba en la lista de {lst}.", "LISTAS")
        return True
    m = _LS_CLEAR.match(v)
    if m and vd.list_name(m.group(1)):
        lst = vd.list_name(m.group(1))
        n = vd.clear_list(lst)
        J.reply(f"Borré la lista de {lst} ({n} cosa{'s' if n != 1 else ''})." if n else f"La lista de {lst} ya estaba vacía.", "LISTAS")
        return True
    m = _LS_CHECK.match(v)
    if m:
        done = vd.check_items(vd.split_items(m.group(1)))
        if done:
            left = {lst: len(vd.pending_items(lst)) for lst, _ in done}
            J.reply("Tachado: " + ", ".join(it for _l, it in done) + ". " + " ".join(f"En {lst} quedan {n}." for lst, n in left.items()), "LISTAS")
            return True
        return False                                    # «ya hice el taller»: no es de una lista, que lo vea otro
    if _LS_ALL.search(t):
        L = {k: len(vd.pending_items(k)) for k in vd.data["listas"] if vd.pending_items(k)}
        J.reply("Tus listas: " + "; ".join(f"{k} ({n})" for k, n in L.items()) + "." if L else
                "No tienes listas. Dime, por ejemplo: «agrega leche a la lista del mercado».", "LISTAS")
        return True
    return False


# ============================================================================ HOME ASSISTANT
def _ha_ready():
    return bool(str(J.settings.get("ha_url", "")).startswith(("http://", "https://")) and J.settings.get("ha_token"))


def _ha_call(method, path, body=None, timeout=6):
    url = J.settings["ha_url"].rstrip("/") + path
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method,
                                 headers={"Authorization": f"Bearer {J.settings['ha_token']}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8") or "null")


def ha_entities(max_age=60):
    """Los aparatos de tu casa (en caché un minuto). Si Home Assistant no responde, no se vuelve a probar en 5 minutos:
    así «abre Spotify» no espera por la casa."""
    if time.time() - _ha_cache["t"] < max_age and _ha_cache["ents"]:
        return _ha_cache["ents"]
    if time.time() - _ha_cache["fail"] < 300:
        return _ha_cache["ents"]
    try:
        _ha_cache.update(t=time.time(), ents=casa.entities(_ha_call("GET", "/api/states", timeout=3)))
    except Exception:
        _ha_cache["fail"] = time.time()
        raise
    return _ha_cache["ents"]


def home_voice(text, t):
    if not _ha_ready():
        return False
    p = casa.parse(t)
    if not p or len(p["nombre"].split()) > 5 or casa.NOT_HOME.search(p["nombre"]):
        return False
    try:
        e = casa.match(ha_entities(), p["nombre"])
    except (OSError, ValueError, urllib.error.URLError):
        return False                                    # Home Assistant no responde: que la orden siga su camino
    if not e:
        return False
    try:
        if p["accion"] == "estado":
            fresh = _ha_call("GET", f"/api/states/{e['id']}")
            e = {**e, "estado": str(fresh.get("state", e["estado"]))}
            J.reply(casa.spoken_state(e), "CASA")
            return True
        dom, svc, body = casa.service(e, p["accion"], p["brillo"])
        _ha_call("POST", f"/api/services/{dom}/{svc}", body)
        _ha_cache["t"] = 0.0
        word = "Encendí" if p["accion"] == "on" else "Apagué"
        if dom == "cover":
            word = "Abrí" if p["accion"] == "on" else "Cerré"
        J.reply(f"{word} {e['nombre']}" + (f" al {p['brillo']} %" if p["brillo"] is not None and dom == "light" else "") + ".", "CASA")
    except (OSError, ValueError, urllib.error.URLError) as ex:
        J.reply(f"Home Assistant no respondió: {str(ex)[:100]}", "CASA")
    return True


@J.socketio.on("ha_test")
def handle_ha_test(data=None):
    if not _ha_ready():
        return {"ok": False, "error": "Escribe la dirección de tu Home Assistant y el token, y guarda."}
    try:
        _ha_cache.update(t=0.0, fail=0.0)
        ents = ha_entities()
        return {"ok": True, "n": len(ents), "ejemplos": [e["nombre"] for e in ents[:8]]}
    except Exception as e:
        return {"ok": False, "error": f"No respondió: {str(e)[:120]}"}


# ============================================================================ RESUMEN Y AVISOS
def brief_extras(now=None):
    """Lo del asistente general para el resumen de la mañana."""
    now = now or datetime.datetime.now()
    out = []
    try:
        out += J.brief_school(now.date())             # 12.12: festivos, recesos y fechas del colegio
    except Exception:
        pass
    soon = [(p, left) for p, _d, left in vd.upcoming(now.date(), 3)]
    if soon:
        out.append("Pagos: " + "; ".join(f"{p['nombre']} {vd.when_text(left)}" for p, left in soon) + ".")
    for name in ("mercado", "pendientes"):
        n = len(vd.pending_items(name))
        if n:
            out.append(f"En la lista de {name} hay {n} cosa{'s' if n != 1 else ''}.")
    try:
        bat = J.psutil.sensors_battery() if J.psutil is not None else None
        if bat and not bat.power_plugged and bat.percent < 40:
            out.append(f"El portátil está al {bat.percent:.0f} % de batería.")
        import shutil
        free = shutil.disk_usage(J.CONFIG_DIR).free / 1e9
        if free < 5:
            out.append(f"Te quedan {free:.0f} GB libres en el disco: di «limpia los temporales».")
    except Exception:
        pass
    return out


def _pay_worker():
    time.sleep(90)
    while True:
        try:
            h = datetime.datetime.now().hour
            if 7 <= h <= 21:
                for p, d, left in vd.payments_to_warn():
                    msg = (f"Recuerda pagar {p['nombre']} {vd.when_text(left)}" + (f" ({vd.money(p['monto'])})" if p.get("monto") else "") +
                           (". Ya se venció." if left < 0 else ".") + " Cuando lo pagues, di «ya pagué " + p["nombre"] + "».")
                    J.notify(msg, "PAGOS")
                    if J.settings.get("telegram_alerts") and J.telegram_ready():
                        threading.Thread(target=J.telegram_send, args=("💳 " + msg,), daemon=True).start()
        except Exception as e:
            J.note_error("PAGOS", e)
        time.sleep(1800)


def daily_start():
    threading.Thread(target=_pay_worker, daemon=True, name="pagos").start()


@J.socketio.on("daily_info")
def handle_daily_info(data=None):
    tot, by, n = vd.spent("mes")
    return {"gastos_mes": tot, "por_categoria": by, "n": n,
            "pagos": [{"nombre": p["nombre"], "dia": d.day, "faltan": left, "monto": p.get("monto")} for p, d, left in vd.upcoming(within=40)],
            "listas": {k: vd.pending_items(k) for k in vd.data["listas"] if vd.pending_items(k)},
            "ha": _ha_ready()}


__all__ = ['_G1', '_G2', '_G3', '_G_ASK', '_G_UNDO', '_LS_ADD', '_LS_ALL', '_LS_CHECK', '_LS_CLEAR', '_LS_DEL', '_LS_SHOW', '_P_ADD', '_P_ASK', '_P_DEL',
           '_P_DONE', '_ha_cache', '_ha_call', '_ha_ready', 'brief_extras', 'daily_start', 'expense_voice', 'ha_entities', 'handle_daily_info',
           'handle_ha_test', 'home_voice', 'list_voice', 'payment_voice']
