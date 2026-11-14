"""12.32: reglas de avisos por evento y proyectos que se repiten (lógica pura: entender la frase y decidir qué toca).

Avisos por evento (además de los del PC: «cuando conecte el cargador…»):
  · «cuando me llegue un correo de la coordinadora, avísame al celular»
  · «cuando aparezca una reunión nueva en el calendario, recuérdamela la víspera»
  · «si el dólar pasa de 4.200, avísame» / «cuando el euro baje de 4.500»
Proyectos que se repiten: «cada lunes a las 7, investiga los precios de la canasta familiar y hazme un informe».
"""
import datetime
import json
import os
import re
import threading
import unicodedata

_lock = threading.Lock()
_path = None
data = {"reglas": [], "recurrentes": [], "vistos": {"mail": [], "cal": []}, "recordados": []}

DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
ASSETS = {"dolar": "USD", "dolares": "USD", "euro": "EUR", "euros": "EUR", "bitcoin": "BTC", "btc": "BTC", "ethereum": "ETH"}


def norm(t):
    t = unicodedata.normalize("NFD", str(t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[¿?¡!]", " ", t)).strip(" .")


def configure(config_dir):
    global _path
    _path = os.path.join(config_dir, "automaticos.json")
    try:
        with open(_path, encoding="utf-8") as f:
            d = json.load(f)
        for k in data:
            if k in d:
                data[k] = d[k]
    except (OSError, ValueError):
        pass


def save():
    if not _path:
        return
    with _lock:
        try:
            with open(_path + ".tmp", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            os.replace(_path + ".tmp", _path)
        except OSError:
            pass


def _amount(s):
    s = norm(s).replace("$", "")
    m = re.match(r"(\d+(?:[.,]\d+)*)\s*(millones|millon|mil|k)?\b", s)
    if not m:
        return None
    num, unit = m.group(1), m.group(2)
    if unit:
        val = float(num.replace(",", ".")) if re.fullmatch(r"\d+[.,]\d{1,2}", num) else float(re.sub(r"[.,]", "", num))
        return val * {"mil": 1e3, "k": 1e3, "millon": 1e6, "millones": 1e6}[unit]
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", num):
        return float(re.sub(r"[.,]", "", num))
    return float(num.replace(",", "."))


_TO_PHONE = re.compile(r"\b(?:celular|telefono|telegram|whatsapp|wasap|movil)\b")


def parse_rule(t):
    """La frase → {"tipo": "correo"|"calendario"|"precio", …, "celular": bool, "vispera": bool} o None."""
    t = norm(t)
    phone = bool(_TO_PHONE.search(t))
    m = re.match(r"^(?:avisame\s+)?(?:cuando|si)\s+(?:me\s+)?(?:llegue|escriba|mande|envie|entre)\s+(?:un\s+|algun\s+)?(?:correo|email|mail|e-?mail)"
                 r"\s+(?:de|del|de la|desde)\s+(.+?)(?:\s*,\s*|\s+(?=avisame|mandame|dime|alertame|notificame)|$)(.*)$", t)
    if m:
        who = re.sub(r"^(?:la|el|mi|los|las)\s+", "", m.group(1)).strip()
        return {"tipo": "correo", "de": who, "celular": phone} if who else None
    m = re.match(r"^(?:avisame\s+)?(?:cuando|si)\s+(?:me\s+)?(?:escriba|escribe)\s+(?!un\s|una\s)(.+?)(?:\s*,\s*|\s+(?=avisame|mandame|dime|alertame|notificame)|$)", t)
    if m:
        who = re.sub(r"^(?:la|el|mi|los|las)\s+", "", m.group(1)).strip()
        return {"tipo": "correo", "de": who, "celular": phone} if who else None
    m = re.match(r"^(?:avisame\s+)?(?:cuando|si)\s+(?:aparezca|agreguen|pongan|haya|entre|llegue|me\s+inviten\s+a)\s+(?:una?\s+)?(?:nuev[oa]\s+)?"
                 r"(reunion|evento|cita|invitacion|clase)(?:\s+nuev[oa])?(?:\s+(?:en|a)\s+(?:el\s+|mi\s+)?calendario)?(.*)$", t)
    if m:
        rest = m.group(2)
        return {"tipo": "calendario", "que": m.group(1), "vispera": bool(re.search(r"\b(?:vispera|dia antes|un dia antes|antes)\b", rest)),
                "celular": phone}
    m = re.match(r"^(?:avisame\s+)?(?:cuando|si)\s+(?:el\s+|la\s+)?(dolar|dolares|euro|euros|bitcoin|btc|ethereum)\s+"
                 r"(pase de|pasa de|suba de|sube de|supere|supera|este por encima de|esta por encima de|llegue a|llega a|pase los|pasa los|"
                 r"baje de|baja de|este por debajo de|esta por debajo de|caiga de|cae de|baje a|baja a|caiga a|cae a)\s+"
                 r"([$\d][\d.,]*\s*(?:millones|millon|mil|k)?)", t)
    if m:
        val = _amount(m.group(3))
        if not val:
            return None
        op = ">" if re.match(r"pas|sub|super|est[ae] por encima|lleg", m.group(2)) else "<"
        return {"tipo": "precio", "activo": ASSETS[m.group(1)], "op": op, "valor": val, "celular": phone}
    return None


def describe(r):
    tail = " y te aviso al celular" if r.get("celular") else ""
    if r["tipo"] == "correo":
        return f"Cuando te llegue un correo de «{r['de']}», te aviso{tail}."
    if r["tipo"] == "calendario":
        return f"Cuando aparezca un evento nuevo en tu calendario, te aviso{tail}" + (", y otra vez la víspera." if r.get("vispera") else ".")
    names = {"USD": "el dólar", "EUR": "el euro", "BTC": "el bitcoin", "ETH": "el ethereum"}
    v = f"{r['valor']:,.0f}".replace(",", ".")
    return f"Cuando {names[r['activo']]} {'pase de' if r['op'] == '>' else 'baje de'} ${v}, te aviso{tail}."


def add_rule(r):
    with _lock:
        r = dict(r, id=max([x.get("id", 0) for x in data["reglas"]] + [0]) + 1, creada=datetime.datetime.now().isoformat(timespec="minutes"))
        data["reglas"].append(r)
    save()
    return r


def remove_rule(n):
    with _lock:
        hit = next((r for r in data["reglas"] if str(r["id"]) == str(n)), None)
        if hit:
            data["reglas"].remove(hit)
    save()
    return hit


def mail_matches(rule, msg):
    who = norm(rule.get("de"))
    hay = norm(f"{msg.get('de_nombre', '')} {msg.get('de', '')}")
    return bool(who) and (who in hay or all(w in hay for w in who.split()))


def price_crossed(rule, value, last):
    """¿Cruzó el umbral desde la última vez? (solo avisa al cruzarlo, no cada 5 minutos mientras siga arriba)."""
    if value is None:
        return False
    now_in = value > rule["valor"] if rule["op"] == ">" else value < rule["valor"]
    was_in = last is not None and (last > rule["valor"] if rule["op"] == ">" else last < rule["valor"])
    return now_in and not was_in


def event_key(ev):
    return f"{ev.get('titulo', '')}|{str(ev.get('inicio', ''))[:16]}"


# ---------------------------------------------------------------------------- recurrentes
_CADA = re.compile(r"^(?:jarvis[ ,]+)?(?:cada|todos los|todas las)\s+(lunes|martes|miercoles|jueves|viernes|sabados?|domingos?|dias?|semanas?|mes(?:es)?)"
                   r"(?:\s+a\s+las\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm|de la manana|de la tarde|de la noche)?)?\s*[,:]?\s+(.+)$")
_REPORTY = re.compile(r"\b(?:informe|investiga|reporte|resumen|resumeme|analiza|compara|averigua|busca|revisa)\w*\b")


def parse_recurring(t):
    """«cada lunes a las 7, investiga … y hazme un informe» → {"dias": [0], "hora": "07:00", "pedido": "…"} o None."""
    m = _CADA.match(norm(t))
    if not m or not _REPORTY.search(m.group(5)):
        return None
    w = m.group(1)
    if w.startswith("dia"):
        dias = list(range(7))
    elif w.startswith("semana"):
        dias = [0]
    elif w.startswith("mes"):
        dias = ["mes"]
    else:
        dias = [DIAS.index(w.rstrip("s") if w.rstrip("s") in DIAS else w)]
    h = int(m.group(2)) if m.group(2) else 7
    mi = int(m.group(3) or 0)
    ap = m.group(4) or ""
    if ("pm" in ap or "tarde" in ap or "noche" in ap) and h < 12:
        h += 12
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        return None
    return {"dias": dias, "hora": f"{h:02d}:{mi:02d}", "pedido": m.group(5).strip()}


def when_text(r):
    d = r["dias"]
    lab = "cada mes (el día 1)" if d == ["mes"] else "todos los días" if len(d) == 7 else "cada " + ", ".join(
        ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"][i] for i in d)
    return f"{lab} a las {r['hora']}"


def due(r, now):
    """¿Toca correrlo ahora? (una vez por día programado, desde su hora)."""
    if r.get("pausado"):
        return False
    hh, mm = (int(x) for x in r["hora"].split(":"))
    if (now.hour, now.minute) < (hh, mm) or r.get("ultimo") == now.date().isoformat():
        return False
    d = r["dias"]
    return now.day == 1 if d == ["mes"] else now.weekday() in d


def compare_prompt(prev_text, new_text, pedido):
    return ("Este informe se hace periódicamente. Compara el de hoy con el de la vez anterior y di, en español claro y sin "
            "markdown, qué cambió: qué subió o bajó (con las cifras de ambos), qué es nuevo y qué ya no aparece. Si no hay "
            f"cifras comparables, dilo. Máximo 8 frases.\nPedido: «{pedido}»\n\nANTERIOR:\n{prev_text[:6000]}\n\nHOY:\n{new_text[:6000]}")
