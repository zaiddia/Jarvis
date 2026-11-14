"""Mi día a día (12.15): vencimientos, medicamentos, citas, cumpleaños, presupuesto, suscripciones y viajes.

Lógica pura (sin Jarvis): guardar, calcular avisos y armar textos. nucleo/hogarvoz.py habla, avisa y muestra la página.
Los gastos y las listas siguen en vidadiaria.py; aquí se leen para el presupuesto y las suscripciones.
"""
import datetime
import json
import os
import re
import threading
import unicodedata
import uuid

_lock = threading.Lock()
_path = None
KEYS = {"venc": [], "meds": [], "citas": [], "cumples": [], "presupuesto": {}, "viajes": [], "avisados": {}, "comidas": {}}
data = {k: (v.copy() if isinstance(v, (list, dict)) else v) for k, v in KEYS.items()}
D = datetime.date
DT = datetime.datetime

VENC_TIPOS = {
    "soat": ("SOAT", r"soat"), "tecnomecanica": ("Revisión técnico-mecánica", r"tecno ?mecanica|tecnicomecanica|revision tecnica|revision tecnico ?mecanica"),
    "licencia": ("Licencia de conducción", r"licencia(?: de conduccion| de conducir)?|pase"),
    "pasaporte": ("Pasaporte", r"pasaporte"), "cedula": ("Cédula", r"cedula"), "visa": ("Visa", r"visa"),
    "seguro": ("Seguro", r"seguro|poliza"), "garantia": ("Garantía", r"garantia"), "contrato": ("Contrato", r"contrato|arriendo"),
    "impuesto": ("Impuesto", r"impuesto|predial|vehicular|renta|declaracion"), "otro": ("Documento", r""),
}
VENC_DIAS = (30, 7, 1, 0)


def norm(t):
    t = unicodedata.normalize("NFD", str(t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", t)).strip()


def configure(config_dir):
    global _path
    _path = os.path.join(config_dir, "mi_dia.json")
    load()


def load():
    for k, v in KEYS.items():
        data[k] = v.copy()
    if not _path:
        return
    try:
        with open(_path, encoding="utf-8") as f:
            d = json.load(f)
        for k, v in KEYS.items():
            if isinstance(d.get(k), type(v)):
                data[k] = d[k]
    except (OSError, ValueError, TypeError, AttributeError):
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


def _new(**kw):
    return {"id": uuid.uuid4().hex[:8], **kw}


def remove(section, rid):
    n = len(data[section])
    data[section] = [x for x in data[section] if x.get("id") != rid]
    if len(data[section]) != n:
        save()
        return True
    return False


def find(section, name, key="nombre"):
    n = norm(name)
    items = data[section]
    return (next((x for x in items if norm(x.get(key)) == n), None) or next((x for x in items if n and n in norm(x.get(key))), None)
            or next((x for x in items if norm(x.get(key)) and norm(x.get(key)) in n), None))


def once(key):
    """True la primera vez que se pide este aviso (para no repetirlo)."""
    if key in data["avisados"]:
        return False
    data["avisados"][key] = DT.now().isoformat(timespec="minutes")
    if len(data["avisados"]) > 3000:
        for k in sorted(data["avisados"], key=data["avisados"].get)[:1000]:
            data["avisados"].pop(k, None)
    save()
    return True


# ============================================================================ FECHAS HABLADAS
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
_MES_RE = "|".join(MESES + ["setiembre"])


def parse_date(text, today=None, future=True):
    """«15 de marzo de 2027», «15/03/2027», «el 20», «mañana», «en 3 meses». → date o None."""
    today = today or D.today()
    t = norm(text)
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", text)
    if m:
        y = int(m.group(3)) + (2000 if len(m.group(3)) == 2 else 0)
        try:
            return D(y, int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    if m:
        try:
            return D(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.search(rf"\b(\d{{1,2}}|primero)\s+de\s+({_MES_RE})(?:\s+(?:de|del)\s+(\d{{4}}))?\b", t)
    if m:
        day = 1 if m.group(1) == "primero" else int(m.group(1))
        month = (MESES.index(m.group(2)) if m.group(2) in MESES else 8) + 1
        year = int(m.group(3)) if m.group(3) else today.year
        try:
            d = D(year, month, day)
        except ValueError:
            return None
        if not m.group(3) and future and d < today:
            d = d.replace(year=year + 1)
        return d
    if re.search(r"\bpasado manana\b", t):
        return today + datetime.timedelta(days=2)
    if re.search(r"\bmanana\b", t):
        return today + datetime.timedelta(days=1)
    if re.search(r"\bhoy\b", t):
        return today
    m = re.search(r"\ben\s+(\d+|un|una|dos|tres|seis)\s+(dias?|semanas?|mes(?:es)?|anos?)\b", t)
    if m:
        n = {"un": 1, "una": 1, "dos": 2, "tres": 3, "seis": 6}.get(m.group(1)) or int(m.group(1))
        u = m.group(2)
        if u.startswith("dia"):
            return today + datetime.timedelta(days=n)
        if u.startswith("semana"):
            return today + datetime.timedelta(weeks=n)
        if u.startswith("mes"):
            return add_months(today, n)
        return add_months(today, 12 * n)
    m = re.search(r"\b(?:el|este|esta|para el|el proximo|el otro|proximo)\s+(lunes|martes|miercoles|jueves|viernes|sabado|domingo)\b", t)
    if m:                                               # 12.27: «el martes», «este viernes», «el próximo lunes»
        wd = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"].index(m.group(1))
        ahead = (wd - today.weekday()) % 7 or 7
        return today + datetime.timedelta(days=ahead)
    m = re.search(r"\b(?:el|para el)\s+(\d{1,2})\b(?!\s*(?:de|:|horas|h\b|am|pm))", t)
    if m and 1 <= int(m.group(1)) <= 31:
        d = int(m.group(1))
        try:
            x = today.replace(day=d)
        except ValueError:
            return None
        return x if x >= today or not future else add_months(x, 1)
    return None


def parse_time(text):
    """«a las 3 de la tarde», «8:30 am», «a las 15:00», «a las 7 y media». → "HH:MM" o ""."""
    raw = str(text or "").lower()
    t = norm(text)
    m = re.search(r"\b(\d{1,2}):(\d{2})\s*(a\.?\s?m\.?|p\.?\s?m\.?)?", raw)
    if m:
        h, mi, suf = int(m.group(1)), int(m.group(2)), (m.group(3) or "").replace(".", "").replace(" ", "")
    else:
        m = re.search(r"\ba las (\d{1,2})(?: y (media|cuarto)| (\d{2}))?(?: (de la manana|de la tarde|de la noche|del mediodia|am|pm|a m|p m))?", t)
        if not m:
            return ""
        h = int(m.group(1))
        mi = 30 if m.group(2) == "media" else 15 if m.group(2) == "cuarto" else int(m.group(3) or 0)
        suf = (m.group(4) or "").replace(" ", "")
    if h > 23 or mi > 59:
        return ""
    if suf in ("pm", "delatarde", "delanoche") and h < 12:
        h += 12
    elif suf in ("am", "delamanana") and h == 12:
        h = 0
    elif not suf and 1 <= h <= 6:
        h += 12                                              # «a las 3» casi siempre es de la tarde
    return f"{h:02d}:{mi:02d}"


def add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    for day in (d.day, 30, 29, 28):
        try:
            return D(y, m, day)
        except ValueError:
            continue


def spoken_date(d, today=None):
    today = today or D.today()
    diff = (d - today).days
    base = f"{d.day} de {MESES[d.month - 1]}" + (f" de {d.year}" if d.year != today.year else "")
    if diff == 0:
        return f"hoy ({base})"
    if diff == 1:
        return f"mañana ({base})"
    if 1 < diff <= 60:
        return f"el {base}, en {diff} días"
    if diff < 0:
        return f"el {base}, hace {-diff} días"
    return f"el {base}"


# ============================================================================ 1. VENCIMIENTOS
def venc_type(text):
    t = norm(text)
    for k, (_, rx) in VENC_TIPOS.items():
        if rx and re.search(rf"\b(?:{rx})\b", t):
            return k
    return "otro"


def venc_display(nombre, tipo):
    """«soat de la moto» → «SOAT de la moto»; «licencia de conduccion» → «Licencia de conducción»."""
    if tipo in VENC_TIPOS and tipo != "otro":
        m = re.search(rf"\b(?:{VENC_TIPOS[tipo][1]})\b", norm(nombre))
        if m and m.start() == 0:
            rest = norm(nombre)[m.end():].strip()
            return VENC_TIPOS[tipo][0] + (" " + rest if rest else "")
    return nombre[:1].upper() + nombre[1:]


def venc_add(nombre, fecha, tipo=None, nota="", persona=""):
    nombre = re.sub(r"\s+", " ", str(nombre)).strip(" .,")[:80] or "Documento"
    tipo = tipo if tipo in VENC_TIPOS else venc_type(nombre)
    if nombre == nombre.lower():
        nombre = venc_display(nombre, tipo)
    old = find("venc", nombre)
    if old and old["tipo"] == tipo:
        old.update(fecha=fecha.isoformat(), nota=nota[:300] or old.get("nota", ""))
        save()
        return old
    x = _new(nombre=nombre, tipo=tipo, fecha=fecha.isoformat(), nota=str(nota)[:300], persona=str(persona)[:40])
    data["venc"].append(x)
    save()
    return x


def venc_soon(today=None, within=31):
    today = today or D.today()
    out = []
    for x in data["venc"]:
        left = (D.fromisoformat(x["fecha"]) - today).days
        if left <= within:
            out.append((x, left))
    return sorted(out, key=lambda p: p[1])


def venc_to_warn(today=None):
    today = today or D.today()
    out = []
    for x in data["venc"]:
        left = (D.fromisoformat(x["fecha"]) - today).days
        if left in VENC_DIAS and once(f"venc:{x['id']}:{x['fecha']}:{left}"):
            out.append((x, left))
    return out


def venc_text(x, left):
    name = x["nombre"]
    if left < 0:
        return f"{name} se venció hace {-left} días."
    if left == 0:
        return f"{name} se vence hoy."
    if left == 1:
        return f"{name} se vence mañana."
    return f"{name} se vence en {left} días ({spoken_date(D.fromisoformat(x['fecha']))})."


def renta_digits_query(year, digits):
    return f"calendario declaración de renta personas naturales {year} DIAN últimos dos dígitos NIT {digits}"


# ============================================================================ 3. MEDICAMENTOS Y CITAS
def med_add(nombre, horas, dosis="", persona="", stock=None, por_toma=1, hasta=None):
    horas = sorted({h for h in horas if re.fullmatch(r"\d{2}:\d{2}", h)})
    if not horas:
        raise ValueError("dime a qué horas (por ejemplo «a las 8 y a las 8 de la noche» o «cada 8 horas»)")
    old = next((m for m in data["meds"] if norm(m["nombre"]) == norm(nombre) and norm(m.get("persona")) == norm(persona)), None)
    if old:
        old.update(horas=horas, dosis=dosis or old.get("dosis", ""), stock=stock if stock is not None else old.get("stock"),
                   por_toma=por_toma or 1, hasta=hasta.isoformat() if hasta else old.get("hasta"))
        save()
        return old
    m = _new(nombre=str(nombre).strip()[:60], horas=horas, dosis=str(dosis)[:60], persona=str(persona)[:40], stock=stock,
             por_toma=max(1, int(por_toma or 1)), hasta=hasta.isoformat() if hasta else None, tomas={})
    data["meds"].append(m)
    save()
    return m


def every_hours(n, first="08:00"):
    """«cada 8 horas» desde las 8:00 → ["08:00", "16:00", "00:00"]."""
    n = max(1, min(24, int(n)))
    h0, m0 = map(int, first.split(":"))
    return sorted({f"{(h0 + i * n) % 24:02d}:{m0:02d}" for i in range(24 // n)})


def med_active(m, today=None):
    today = today or D.today()
    return not m.get("hasta") or today.isoformat() <= m["hasta"]


def meds_due(now=None, window=10):
    """Tomas que tocan ahora (hasta `window` minutos tarde), una vez cada una. → [(med, "HH:MM")]."""
    now = now or DT.now()
    out = []
    for m in data["meds"]:
        if not med_active(m, now.date()):
            continue
        for h in m["horas"]:
            hh, mm = map(int, h.split(":"))
            at = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if 0 <= (now - at).total_seconds() < window * 60 and once(f"med:{m['id']}:{now.date()}:{h}"):
                out.append((m, h))
    return out


def med_last_due(m, now=None):
    """La toma de hoy más reciente que ya pasó (o la primera si aún no toca ninguna)."""
    now = now or DT.now()
    past = [h for h in m["horas"] if h <= now.strftime("%H:%M")]
    return past[-1] if past else m["horas"][0]


def med_taken(m, now=None):
    """«Ya me la tomé». → (hora marcada, pastillas que quedan o None)."""
    now = now or DT.now()
    h = med_last_due(m, now)
    day = m.setdefault("tomas", {}).setdefault(now.date().isoformat(), [])
    if h not in day:
        day.append(h)
        if m.get("stock") is not None:
            m["stock"] = max(0, int(m["stock"]) - int(m.get("por_toma", 1)))
    for k in sorted(m["tomas"])[:-40]:
        m["tomas"].pop(k, None)
    save()
    return h, m.get("stock")


def med_days_left(m):
    if m.get("stock") is None:
        return None
    per_day = len(m["horas"]) * int(m.get("por_toma", 1))
    return int(m["stock"]) // per_day if per_day else None


def meds_refill(today=None):
    today = today or D.today()
    out = []
    for m in data["meds"]:
        left = med_days_left(m)
        if left is not None and left <= 5 and med_active(m, today) and once(f"refill:{m['id']}:{today}"):
            out.append((m, left))
    return out


def meds_missed(now=None, grace=60):
    """Tomas de hoy que pasaron hace más de `grace` minutos sin marcar (un aviso por toma)."""
    now = now or DT.now()
    out = []
    for m in data["meds"]:
        if not med_active(m, now.date()):
            continue
        done = m.get("tomas", {}).get(now.date().isoformat(), [])
        for h in m["horas"]:
            hh, mm = map(int, h.split(":"))
            at = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if h not in done and grace * 60 <= (now - at).total_seconds() < (grace + 30) * 60 and once(f"miss:{m['id']}:{now.date()}:{h}"):
                out.append((m, h))
    return out


def cita_add(que, fecha, hora="", lugar="", persona=""):
    c = _new(que=str(que).strip(" .,")[:100], fecha=fecha.isoformat(), hora=hora, lugar=str(lugar)[:100], persona=str(persona)[:40])
    data["citas"].append(c)
    data["citas"] = sorted(data["citas"], key=lambda x: (x["fecha"], x.get("hora") or ""))[-300:]
    save()
    return c


def citas_soon(today=None, within=14):
    today = today or D.today()
    return [c for c in data["citas"] if 0 <= (D.fromisoformat(c["fecha"]) - today).days <= within]


def citas_to_warn(now=None):
    """La víspera desde las 6 p. m. y el mismo día temprano (o 2 horas antes)."""
    now = now or DT.now()
    out = []
    for c in data["citas"]:
        d = D.fromisoformat(c["fecha"])
        left = (d - now.date()).days
        if left == 1 and now.hour >= 18 and once(f"cita:{c['id']}:vispera"):
            out.append((c, "mañana"))
        elif left == 0 and once(f"cita:{c['id']}:hoy"):
            if c.get("hora"):
                hh, mm = map(int, c["hora"].split(":"))
                if (now.replace(hour=hh, minute=mm) - now).total_seconds() > 2.5 * 3600:
                    data["avisados"].pop(f"cita:{c['id']}:hoy", None)       # aún es temprano: avisa más cerca
                    continue
            out.append((c, "hoy"))
    return out


def cita_text(c, cuando):
    hora = f" a las {hour_spoken(c['hora'])}" if c.get("hora") else ""
    quien = f" de {c['persona']}" if c.get("persona") else ""
    lugar = f" en {c['lugar']}" if c.get("lugar") else ""
    return f"{cuando.capitalize()} tienes la cita{quien}: {c['que']}{hora}{lugar}."


def hour_spoken(h):
    hh, mm = map(int, h.split(":"))
    suf = "de la mañana" if hh < 12 else "de la tarde" if hh < 19 else "de la noche"
    h12 = hh % 12 or 12
    return f"{h12}{':%02d' % mm if mm else ''} {suf}"


# ============================================================================ 4. CUMPLEAÑOS
def cumple_add(nombre, mes, dia, anio=None, relacion=""):
    old = find("cumples", nombre)
    if old:
        old.update(mes=int(mes), dia=int(dia), anio=anio or old.get("anio"), relacion=relacion or old.get("relacion", ""))
        save()
        return old
    c = _new(nombre=str(nombre).strip(" .,")[:60], mes=int(mes), dia=int(dia), anio=anio, relacion=str(relacion)[:40])
    data["cumples"].append(c)
    save()
    return c


def next_birthday(c, today=None):
    today = today or D.today()
    for y in (today.year, today.year + 1):
        try:
            d = D(y, c["mes"], c["dia"])
        except ValueError:
            d = D(y, 3, 1)                                       # 29 de febrero en año no bisiesto
        if d >= today:
            return d


def cumples_soon(today=None, within=30):
    today = today or D.today()
    out = [(c, next_birthday(c, today)) for c in data["cumples"]]
    return sorted([(c, d, (d - today).days) for c, d in out if (d - today).days <= within], key=lambda x: x[2])


def cumples_to_warn(today=None, before=3):
    today = today or D.today()
    out = []
    for c, d, left in cumples_soon(today, before):
        if left in (before, 0) and once(f"cumple:{c['id']}:{d}:{left}"):
            out.append((c, d, left))
    return out


def age_on(c, d):
    return d.year - int(c["anio"]) if c.get("anio") else None


def greeting_prompt(c, d, tono=""):
    edad = age_on(c, d)
    return ("Escribe un mensaje corto y cálido de feliz cumpleaños en español de Colombia para enviar por WhatsApp. "
            f"Para: {c['nombre']}" + (f" ({c['relacion']})" if c.get("relacion") else "") + (f", cumple {edad} años" if edad else "") + ". "
            + (f"Tono: {tono}. " if tono else "") + "Máximo 3 frases, sin hashtags, con a lo sumo un emoji. Solo el mensaje.")


def gift_prompt(c, presupuesto=None, gustos=""):
    return ("Dame 5 ideas de regalo concretas y fáciles de conseguir en Colombia para "
            f"{c['nombre']}" + (f" ({c['relacion']})" if c.get("relacion") else "")
            + (f", que le gusta {gustos}" if gustos else "") + (f", con presupuesto de hasta {presupuesto} pesos" if presupuesto else "")
            + ". Una línea por idea con precio aproximado. Sin introducción.")


# ============================================================================ 5. PRESUPUESTO Y SUSCRIPCIONES
def budget_set(cat, tope):
    data["presupuesto"][cat] = int(tope)
    save()


def budget_status(spent_by_cat, today=None):
    """[(categoría, gastado, tope, %)] de las que tienen tope."""
    out = []
    for cat, tope in data["presupuesto"].items():
        g = int(spent_by_cat.get(cat, 0))
        out.append((cat, g, tope, round(100 * g / tope) if tope else 0))
    return sorted(out, key=lambda x: -x[3])


def budget_to_warn(spent_by_cat, today=None):
    today = today or D.today()
    out = []
    for cat, g, tope, pct in budget_status(spent_by_cat, today):
        for lvl in (100, 80):
            if pct >= lvl:
                if once(f"budget:{cat}:{today:%Y-%m}:{lvl}"):
                    out.append((cat, g, tope, pct, lvl))
                break
    return out


def subscriptions(gastos, pagos=(), today=None):
    """Cobros que se repiten: el mismo concepto con un valor parecido en 2 o más meses distintos, y los pagos fijos con valor.
    → [{"nombre", "monto", "meses", "anual", "origen"}]."""
    today = today or D.today()
    since = add_months(today.replace(day=1), -6).isoformat()
    groups = {}
    for g in gastos:
        if g["fecha"] < since:
            continue
        k = re.sub(r"\b(?:de|del|la|el|mes|mensual|pago|plan)\b", " ", norm(g["concepto"]))
        k = re.sub(r"\s+", " ", k).strip()
        if k:
            groups.setdefault(k, []).append(g)
    out = []
    for k, items in groups.items():
        months = {g["fecha"][:7] for g in items}
        if len(months) < 2:
            continue
        amounts = sorted(g["monto"] for g in items)
        med = amounts[len(amounts) // 2]
        if all(abs(a - med) <= max(2000, med * 0.15) for a in amounts):
            out.append({"nombre": items[-1]["concepto"], "monto": med, "meses": len(months), "anual": med * 12, "origen": "gastos"})
    names = {norm(x["nombre"]) for x in out}
    for p in pagos:
        if p.get("monto") and norm(p["nombre"]) not in names:
            out.append({"nombre": p["nombre"], "monto": int(p["monto"]), "meses": None, "anual": int(p["monto"]) * 12, "origen": "pagos"})
    return sorted(out, key=lambda x: -x["anual"])


# ============================================================================ 2. RECIBOS (lectura con la IA)
RECEIPT_PROMPT = ("Lee este recibo o factura de Colombia y responde SOLO un JSON: "
                  '{"negocio": "…", "fecha": "AAAA-MM-DD o vacío", "total": 12345, "concepto": "qué se compró, corto", '
                  '"es_garantia": false, "producto": "", "meses_garantia": 0}. '
                  "«total» es el valor total pagado en pesos, como número entero (sin puntos ni signo). "
                  "«es_garantia» es true solo si es la compra de un aparato o electrodoméstico (celular, nevera, TV, computador…); "
                  "si el recibo dice cuántos meses de garantía, ponlos; si no, 12 para aparatos. Si no es un recibo, total 0.")


def parse_receipt(d, today=None):
    today = today or D.today()
    if not isinstance(d, dict):
        raise ValueError("no entendí el recibo")
    try:
        total = int(round(float(str(d.get("total") or 0).replace(".", "").replace(",", ".") if isinstance(d.get("total"), str) else d.get("total") or 0)))
    except (TypeError, ValueError):
        total = 0
    if total < 50:
        raise ValueError("no encontré el total en la foto; prueba con una foto más nítida y completa")
    try:
        fecha = D.fromisoformat(str(d.get("fecha"))[:10])
        if fecha > today or (today - fecha).days > 400:
            fecha = today
    except ValueError:
        fecha = today
    negocio = re.sub(r"\s+", " ", str(d.get("negocio") or "")).strip()[:50]
    concepto = re.sub(r"\s+", " ", str(d.get("concepto") or "")).strip()[:60]
    meses = int(d.get("meses_garantia") or 0) if str(d.get("meses_garantia") or "0").isdigit() else 0
    return {"total": total, "fecha": fecha, "negocio": negocio, "concepto": concepto or negocio or "compra",
            "garantia": bool(d.get("es_garantia")), "producto": str(d.get("producto") or concepto)[:60], "meses": meses or (12 if d.get("es_garantia") else 0)}


# ============================================================================ 6. COMIDAS
def meals_prompt(dias=7, personas=2, presupuesto=None, gustos="", tengo=""):
    return ("Arma un menú semanal casero colombiano, sencillo y balanceado. "
            f"Días: {dias}. Personas: {personas}. " + (f"Presupuesto semanal aproximado: {presupuesto} pesos. " if presupuesto else "")
            + (f"Gustos o restricciones: {gustos}. " if gustos else "") + (f"Ya hay en casa: {tengo} (úsalo primero). " if tengo else "")
            + 'Responde SOLO un JSON: {"dias": [{"dia": "Lunes", "desayuno": "…", "almuerzo": "…", "cena": "…"}], '
            '"lista": [{"item": "arroz", "cantidad": "1 kg", "precio": 4500}], "costo_total": 120000}. '
            "Precios aproximados en pesos colombianos. La lista agrupa lo que hay que comprar (sin lo que ya hay en casa).")


def meals_validate(d):
    if not isinstance(d, dict):
        raise ValueError("el menú no vino bien")
    dias = []
    for x in (d.get("dias") or [])[:7]:
        if isinstance(x, dict) and x.get("dia"):
            dias.append({k: re.sub(r"\s+", " ", str(x.get(k) or "")).strip()[:120] for k in ("dia", "desayuno", "almuerzo", "cena")})
    lista = []
    for x in (d.get("lista") or [])[:60]:
        if isinstance(x, dict) and str(x.get("item") or "").strip():
            try:
                precio = int(float(x.get("precio") or 0))
            except (TypeError, ValueError):
                precio = 0
            lista.append({"item": str(x["item"]).strip()[:50], "cantidad": str(x.get("cantidad") or "").strip()[:30], "precio": precio})
    if not dias:
        raise ValueError("el menú vino vacío")
    try:
        costo = int(float(d.get("costo_total") or 0)) or sum(x["precio"] for x in lista)
    except (TypeError, ValueError):
        costo = sum(x["precio"] for x in lista)
    return {"dias": dias, "lista": lista, "costo": costo, "fecha": D.today().isoformat()}


def cook_prompt(ingredientes):
    return ("Con estos ingredientes de la casa, propone 2 platos caseros colombianos fáciles: " + ingredientes
            + ". Para cada uno: nombre, qué más hace falta (si algo) y pasos en 4 líneas cortas. Sin introducción.")


# ============================================================================ 9. VIAJES
PACK_BASE = ["Cédula", "Cargador del celular", "Medicamentos", "Cepillo y crema de dientes", "Desodorante", "Ropa interior", "Pijama", "Gafas (si usas)"]


def trip_add(destino, desde, hasta, vuelo="", hora_vuelo="", internacional=False, moneda=""):
    t = _new(destino=str(destino).strip(" .,")[:60], desde=desde.isoformat(), hasta=hasta.isoformat(), vuelo=str(vuelo)[:20],
             hora_vuelo=hora_vuelo, internacional=bool(internacional), moneda=str(moneda)[:3].upper(), lista=f"maleta {norm(destino)[:30]}")
    data["viajes"] = [v for v in data["viajes"] if v["hasta"] >= D.today().isoformat()][-20:] + [t]
    save()
    return t


def packing_list(t, tmax=None, tmin=None, rain=None):
    days = (D.fromisoformat(t["hasta"]) - D.fromisoformat(t["desde"])).days + 1
    items = list(PACK_BASE)
    items.append(f"{days} mudas de ropa")
    if t.get("internacional"):
        items = [x for x in items if x != "Cédula"] + ["Pasaporte", "Visa (si la piden)", "Seguro de viaje", "Adaptador de enchufe"]
    if tmax is not None and tmax >= 27:
        items += ["Bloqueador solar", "Gafas de sol", "Vestido de baño", "Ropa fresca", "Sandalias", "Gorra o sombrero"]
    if tmin is not None and tmin <= 14:
        items += ["Chaqueta abrigada", "Bufanda", "Medias gruesas"]
    if rain is not None and rain >= 50:
        items += ["Sombrilla o impermeable"]
    if days >= 4:
        items += ["Bolsa para ropa sucia"]
    seen, out = set(), []
    for x in items:
        if x.lower() not in seen:
            seen.add(x.lower())
            out.append(x)
    return out


def trips_to_warn(now=None):
    now = now or DT.now()
    out = []
    for t in data["viajes"]:
        d = D.fromisoformat(t["desde"])
        left = (d - now.date()).days
        if left == 2 and once(f"viaje:{t['id']}:docs"):
            out.append((t, "docs"))
        if t.get("hora_vuelo"):
            hh, mm = map(int, t["hora_vuelo"].split(":"))
            dep = DT.combine(d, datetime.time(hh, mm))
            hrs = (dep - now).total_seconds() / 3600
            if 23 <= hrs <= 25 and once(f"viaje:{t['id']}:checkin"):
                out.append((t, "checkin"))
            if 3 <= hrs <= 3.5 and once(f"viaje:{t['id']}:salir"):
                out.append((t, "salir"))
        elif left == 1 and now.hour >= 18 and once(f"viaje:{t['id']}:vispera"):
            out.append((t, "vispera"))
    return out


def trip_text(t, kind):
    if kind == "docs":
        return (f"En dos días viajas a {t['destino']}. Revisa {'el pasaporte' if t.get('internacional') else 'la cédula'}, "
                f"las reservas y la lista «{t['lista']}».")
    if kind == "checkin":
        return f"Mañana vuelas a {t['destino']}" + (f" ({t['vuelo']})" if t.get("vuelo") else "") + ": ya puedes hacer el check-in en línea."
    if kind == "salir":
        return f"Tu vuelo a {t['destino']} sale a las {hour_spoken(t['hora_vuelo'])}: es buena hora para salir al aeropuerto."
    return f"Mañana viajas a {t['destino']}. ¿Ya empacaste? La lista está en «{t['lista']}»."
