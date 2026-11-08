"""Compartir con la familia, resumen del mes, cumpleaños de tus contactos e inicio unificado (12.16).

- «Mándale la lista del mercado a mi esposa», «compártele el menú a mi mamá», «avísale a mi hermana del cumpleaños de mamá»:
  Jarvis arma el mensaje y te lo muestra; solo lo envía por WhatsApp cuando dices «sí».
- «Resumen del mes»: gastos frente al presupuesto, suscripciones, lo que se venció y lo que viene. El día 1 llega solo.
- «Importa los cumpleaños de mis contactos»: los trae de Google (con el permiso de contactos, solo lectura).
- midia_dash(): lo de «Mi día» para el panel «Hoy» del HUD.
"""
import datetime
import re
import threading
import time

import hogar as H
import skills
import vidadiaria as vd
from nucleo import J

_CD = datetime.date
_cmp = {"started": False}
PEOPLE_API = "https://people.googleapis.com/v1/"


# ============================================================================ COMPARTIR
_SH = re.compile(r"^(?:jarvis[ ,]+)?(?:mandale|enviale|compartele|pasale|manda|envia|comparte)\s+"
                 r"(?:la\s+|el\s+|mis\s+|mi\s+)?(lista\s+(?:de\s+la\s+|del\s+|de\s+)?.+?|menu(?:\s+de\s+la\s+semana)?|vencimientos|viaje|lista de maleta)\s+"
                 r"(?:a|con)\s+(?:mi\s+)?(.+?)(?:\s+por\s+(?:whatsapp|wasap|guasap))?$")
_TELL = re.compile(r"^(?:jarvis[ ,]+)?(?:avisale|recuerdale|dile)\s+a\s+(?:mi\s+)?(.+?)\s+(?:del|de la|de los|sobre el|sobre la)\s+(cumpleanos|cita|viaje)\s+(?:de\s+)?(?:mi\s+)?(.*)$")


def share_text(what):
    """El mensaje para compartir algo de Mi día. → (título, texto) o (None, motivo)."""
    w = H.norm(what)
    if w.startswith("lista"):
        name = vd.list_name(re.sub(r"^lista\s+(?:de\s+la\s+|del\s+|de\s+)?", "", w))
        items = vd.pending_items(name)
        if not items:
            return None, f"La lista de {name} está vacía."
        return f"la lista de {name}", f"🛒 Lista de {name}:\n" + "\n".join(f"• {x}" for x in items[:60])
    if w.startswith("menu"):
        m = H.data.get("comidas") or {}
        if not m.get("dias"):
            return None, "Aún no hay menú. Di «arma el menú de la semana»."
        lines = [f"{d['dia']}: {d.get('almuerzo', '')}" + (f" · cena: {d['cena']}" if d.get("cena") else "") for d in m["dias"]]
        return "el menú", "🍲 Menú de la semana:\n" + "\n".join(lines)
    if w.startswith("venc"):
        items = H.venc_soon(within=60)
        if not items:
            return None, "No hay nada por vencer en los próximos dos meses."
        return "los vencimientos", "📄 Por vencer:\n" + "\n".join(f"• {H.venc_text(x, left)}" for x, left in items[:10])
    if "viaje" in w or "maleta" in w:
        vs = sorted([v for v in H.data["viajes"] if v["hasta"] >= _CD.today().isoformat()], key=lambda v: v["desde"])
        if not vs:
            return None, "No tienes viajes anotados."
        v = vs[0]
        items = vd.pending_items(v["lista"])
        return "el viaje", (f"✈ Viaje a {v['destino']}: {v['desde']} al {v['hasta']}" + (f", vuelo a las {H.hour_spoken(v['hora_vuelo'])}" if v.get("hora_vuelo") else "")
                            + (".\nPara la maleta:\n" + "\n".join(f"• {x}" for x in items[:40]) if items else "."))
    return None, "No sé compartir eso todavía."


def tell_text(kind, who):
    if kind == "cumpleanos":
        c = H.find("cumples", who) if who else None
        if not c:
            return None, f"No tengo el cumpleaños de {who or 'esa persona'}. Dime «el cumpleaños de … es el …»."
        d = H.next_birthday(c)
        return f"el cumpleaños de {c['nombre']}", f"🎂 Te recuerdo: {c['nombre']} cumple {H.spoken_date(d)}" + (f" ({H.age_on(c, d)} años)" if c.get("anio") else "") + "."
    if kind == "cita":
        cs = H.citas_soon(within=30)
        c = next((x for x in cs if not who or H.norm(who) in H.norm(x.get("persona", "") + " " + x["que"])), cs[0] if cs else None)
        if not c:
            return None, "No hay citas próximas."
        return "la cita", "🩺 " + H.cita_text(c, H.spoken_date(_CD.fromisoformat(c["fecha"])))
    return share_text("viaje")


def _ask_send(person, title, msg):
    num = skills.resolve_contact(person)
    if not num:
        J.reply(f"No tengo a «{person}» en la agenda. Agrégalo en Ajustes › Cuentas y mensajes (nombre = número) y me lo vuelves a pedir.", "FAMILIA")
        return
    J.request_approval("mensaje", f"WhatsApp a {person}: {title}", msg[:900],
                       on_ok=lambda: J.run_skill("whatsapp", {"contacto": person, "mensaje": msg}),
                       on_no=lambda: J.reply("Vale, no lo envío.", "FAMILIA"), ttl=600,
                       say=f"Le mando a {person} {title}: «{msg[:160]}{'…' if len(msg) > 160 else ''}». ¿Lo envío? Di «sí» o «no».")


def share_voice(text, t):
    m = _SH.match(t)
    if m and re.search(r"\b(?:excel|word|pdf|texto|drive|correo|csv|powerpoint|audio|proyector|pantalla|tablero)\b", m.group(2)):
        m = None                                         # «pasa la lista a Excel» no es para una persona
    if m:
        title, msg = share_text(m.group(1))
        if not title:
            J.reply(msg, "FAMILIA")
            return True
        _ask_send(m.group(2).strip(), title, msg)
        return True
    m = _TELL.match(t)
    if m:
        title, msg = tell_text(m.group(2), m.group(3).strip())
        if not title:
            J.reply(msg, "FAMILIA")
            return True
        _ask_send(m.group(1).strip(), title, msg)
        return True
    return False


# ============================================================================ RESUMEN DEL MES
def month_summary(month_day, today=None):
    """Resumen del mes de `month_day` (gastos, presupuesto, suscripciones, vencimientos) y lo que viene después."""
    today = today or _CD.today()
    a = month_day.replace(day=1)
    b = H.add_months(a, 1) - datetime.timedelta(days=1)
    items = [g for g in vd.data["gastos"] if a.isoformat() <= g["fecha"] <= b.isoformat()]
    mes = H.MESES[a.month - 1]
    parts = []
    if items:
        tot = sum(g["monto"] for g in items)
        by = {}
        for g in items:
            by[g["categoria"]] = by.get(g["categoria"], 0) + g["monto"]
        top = sorted(by.items(), key=lambda kv: -kv[1])[:3]
        parts.append(f"En {mes} gastaste {vd.money(tot)}; lo que más: " + ", ".join(f"{c} {vd.money(v)}" for c, v in top) + ".")
        over = [(c, by.get(c, 0), tp) for c, tp in H.data["presupuesto"].items() if by.get(c, 0) > tp]
        if over:
            parts.append("Te pasaste del presupuesto en " + ", ".join(f"{c} ({vd.money(g)} de {vd.money(tp)})" for c, g, tp in over) + ".")
        elif H.data["presupuesto"]:
            parts.append("Te mantuviste dentro del presupuesto. ¡Bien!")
    else:
        parts.append(f"No anotaste gastos en {mes}.")
    subs = H.subscriptions(vd.data["gastos"], vd.data["pagos"], b)
    if subs:
        parts.append(f"Tus cobros fijos suman {vd.money(sum(s['monto'] for s in subs))} al mes.")
    vencidos = [x for x in H.data["venc"] if a.isoformat() <= x["fecha"] <= b.isoformat()]
    if vencidos:
        parts.append("Se vencía en el mes: " + ", ".join(x["nombre"] for x in vencidos) + " (si ya lo renovaste, dime «ya renové …»).")
    empty = [m["nombre"] for m in H.data["meds"] if m.get("stock") == 0]
    if empty:
        parts.append("Sin pastillas: " + ", ".join(empty) + ".")
    na = H.add_months(a, 1)
    nb = H.add_months(na, 1) - datetime.timedelta(days=1)
    nxt = []
    nxt += [f"vence {x['nombre']} el {_CD.fromisoformat(x['fecha']).day}" for x in H.data["venc"] if na.isoformat() <= x["fecha"] <= nb.isoformat()]
    nxt += [f"cumple {c['nombre']} el {c['dia']}" for c in H.data["cumples"] if c["mes"] == na.month]
    nxt += [f"cita: {c['que']} el {_CD.fromisoformat(c['fecha']).day}" for c in H.data["citas"] if na.isoformat() <= c["fecha"] <= nb.isoformat()]
    nxt += [f"viaje a {v['destino']} el {_CD.fromisoformat(v['desde']).day}" for v in H.data["viajes"] if na.isoformat() <= v["desde"] <= nb.isoformat()]
    if nxt:
        parts.append(f"En {H.MESES[na.month - 1]}: " + "; ".join(nxt[:8]) + ".")
    return " ".join(parts)


_SUMM = re.compile(r"\bresumen del mes(?: pasado)?\b|\bcomo me fue (?:el|este) mes(?: pasado)?\b|\bbalance del mes\b")


def summary_voice(text, t):
    if not _SUMM.search(t):
        return False
    today = _CD.today()
    day = (today.replace(day=1) - datetime.timedelta(days=1)) if ("pasado" in t or today.day <= 3) else today
    J.reply(month_summary(day, today), "RESUMEN DEL MES")
    return True


# ============================================================================ CUMPLEAÑOS DESDE GOOGLE
CONTACTS_SCOPE = "https://www.googleapis.com/auth/contacts.readonly"


def parse_birthdays(connections):
    """[(nombre, mes, día, año o None)] de las personas de Google que tienen cumpleaños."""
    out = []
    for p in connections or []:
        name = next((n.get("displayName") for n in p.get("names") or [] if n.get("displayName")), "")
        bd = next((b.get("date") for b in p.get("birthdays") or [] if b.get("date", {}).get("month")), None)
        if name and bd and bd.get("day"):
            out.append((name.strip()[:60], int(bd["month"]), int(bd["day"]), int(bd["year"]) if bd.get("year") else None))
    return out


def import_birthdays():
    """→ mensaje."""
    c = J.classroom_client()
    if not c:
        return "Primero conecta tu cuenta de Google en Ajustes › Cuentas y mensajes › Cuenta de Google."
    if CONTACTS_SCOPE not in str(J.settings.get("google_scopes") or ""):
        return ("Para leer los cumpleaños de tus contactos necesito un permiso nuevo: pulsa otra vez «Conectar con Google» en Ajustes "
                "y acepta «Ver tus contactos». Si Google dice que la API no está activa, actívala (People API) en tu proyecto de Google Cloud.")
    conns, params = [], {"personFields": "names,birthdays", "pageSize": 1000}
    for _ in range(10):
        d = c.call("GET", "people/me/connections", params, base=PEOPLE_API)
        conns += d.get("connections") or []
        if not d.get("nextPageToken"):
            break
        params["pageToken"] = d["nextPageToken"]
    found = parse_birthdays(conns)
    new = 0
    for name, mes, dia, anio in found:
        if not H.find("cumples", name):
            new += 1
        H.cumple_add(name, mes, dia, anio)
    if not found:
        return "Tus contactos de Google no tienen cumpleaños guardados."
    soon = H.cumples_soon(within=30)
    return (f"Traje {len(found)} cumpleaños de tus contactos ({new} nuevos). "
            + (("Los próximos: " + "; ".join(f"{x['nombre']} {H.spoken_date(d)}" for x, d, _ in soon[:4]) + ".") if soon else ""))


_IMP = re.compile(r"\b(?:importa|trae|traeme|sincroniza|carga)(?:me)?\s+(?:los\s+)?cumpleanos\s+(?:de\s+)?(?:mis\s+contactos|google|mis contactos de google)\b")


def contacts_voice(text, t):
    if not _IMP.search(t):
        return False
    try:
        J.reply(import_birthdays(), "CUMPLEAÑOS")
    except Exception as e:
        J.reply(f"Google no dejó leer los contactos: {str(e)[:160]}", "CUMPLEAÑOS")
    return True


# ============================================================================ INICIO UNIFICADO (panel «Hoy»)
def midia_dash(now=None):
    now = now or datetime.datetime.now()
    today = now.date()
    out = {"venc": [{"t": x["nombre"], "n": left} for x, left in H.venc_soon(today, 30)[:3]]}
    nxt = None
    for m in H.data["meds"]:
        if not H.med_active(m, today):
            continue
        done = m.get("tomas", {}).get(today.isoformat(), [])
        for h in m["horas"]:
            if h not in done and (nxt is None or h < nxt["h"]):
                nxt = {"t": m["nombre"], "h": h, "tarde": h < now.strftime("%H:%M")}
    out["toma"] = nxt
    out["citas"] = [H.cita_text(c, "hoy" if c["fecha"] == today.isoformat() else "mañana")
                    for c in H.data["citas"] if c["fecha"] in (today.isoformat(), (today + datetime.timedelta(days=1)).isoformat())][:2]
    out["cumples"] = [{"t": c["nombre"], "n": left} for c, _d, left in H.cumples_soon(today, 7)[:3]]
    _tot, by, _n = vd.spent("mes", today)
    st = H.budget_status(by)
    out["presupuesto"] = {"cat": st[0][0], "pct": st[0][3]} if st else None
    vs = [v for v in H.data["viajes"] if today.isoformat() <= v["desde"] <= (today + datetime.timedelta(days=15)).isoformat()]
    out["viaje"] = {"t": vs[0]["destino"], "n": (_CD.fromisoformat(vs[0]["desde"]) - today).days} if vs else None
    try:
        out["dnd"] = J.dnd_status()
    except Exception:
        out["dnd"] = None
    return out


# ============================================================================ AVISOS
def _cmp_worker():
    time.sleep(120)
    while True:
        try:
            now = datetime.datetime.now()
            if now.day == 1 and now.hour >= 8 and H.once(f"resumen:{now:%Y-%m}"):
                msg = month_summary(now.date() - datetime.timedelta(days=1), now.date())
                J.notify("Resumen del mes. " + msg, "RESUMEN DEL MES")
                if J.settings.get("telegram_alerts") and J.telegram_ready():
                    threading.Thread(target=J.telegram_send, args=("📊 Resumen del mes\n" + msg,), daemon=True).start()
        except Exception as e:
            J.note_error("RESUMEN", e)
        time.sleep(1800)


def compartir_start():
    if not _cmp["started"]:
        _cmp["started"] = True
        threading.Thread(target=_cmp_worker, daemon=True, name="resumen-mes").start()


def compartir_voice(text, t):
    return share_voice(text, t) or summary_voice(text, t) or contacts_voice(text, t)


__all__ = ['CONTACTS_SCOPE', 'PEOPLE_API', '_IMP', '_SH', '_SUMM', '_TELL', '_ask_send', '_cmp', '_cmp_worker', 'contacts_voice', 'compartir_start',
           'compartir_voice', 'import_birthdays', 'midia_dash', 'month_summary', 'parse_birthdays', 'share_text', 'share_voice', 'summary_voice',
           'tell_text']
