"""Asistente general (12.9): modos, gastos, pagos, listas y disparadores. Lógica pura, sin Jarvis.

- Modos: «docente» (el colegio) y «general» (todo lo demás). En automático, Jarvis es docente durante tu horario de
  clases o conectado al Wi-Fi del colegio, y general el resto del tiempo.
- Gastos: «gasté 20 mil en almuerzo» → anotado en «Comida». «¿Cuánto he gastado este mes?».
- Pagos: «recuérdame pagar el internet el 15 de cada mes» → aviso dos días antes y el mismo día.
- Listas: «agrega leche y pan a la lista del mercado», «¿qué hay en la lista del mercado?», «ya compré leche».
- Disparadores: «cuando conecte el cargador, modo general» · «cuando me conecte al wifi Colegio, modo docente» ·
  «cuando abra Excel, silencia las notificaciones» · «cuando la batería esté baja, activa el ahorro de batería».
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
data = {"gastos": [], "pagos": [], "listas": {}, "disparadores": []}
MODES = ("docente", "general")


def norm(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s%$.,]", " ", "".join(c for c in t if unicodedata.category(c) != "Mn"))).strip()


# ----------------------------------------------------------------------------- almacén
def configure(config_dir):
    global _path
    _path = os.path.join(config_dir, "vida_diaria.json")
    load()


def load():
    global data
    try:
        with open(_path, encoding="utf-8") as f:
            d = json.load(f)
        data = d if isinstance(d, dict) else {}
    except (OSError, ValueError, TypeError):
        data = {}
    for k, v in (("gastos", []), ("pagos", []), ("listas", {}), ("disparadores", [])):
        if not isinstance(data.get(k), type(v)):
            data[k] = v


def save():
    if not _path:
        return
    with _lock:
        os.makedirs(os.path.dirname(_path), exist_ok=True)
        with open(_path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(_path + ".tmp", _path)


# ----------------------------------------------------------------------------- modos
def resolve_mode(setting, in_class=False, ssid="", school_wifi="", has_schedule=True, school_hours=False):
    """El modo que toca. setting: auto|docente|general."""
    if setting in MODES:
        return setting
    nets = [norm(x) for x in re.split(r"[,;]", school_wifi or "") if x.strip()]
    if ssid and nets and norm(ssid) in nets:
        return "docente"
    if in_class or school_hours:
        return "docente"
    if not has_schedule and not nets:                  # 12.26: sin horario ni Wi-Fi del colegio, docente solo en horas de colegio
        return "docente" if school_hours else "general"
    return "general"


def school_hours(items, now):
    """¿Estamos en la jornada (desde 30 min antes de la primera clase hasta 30 min después de la última)?"""
    hoy = sorted((x for x in items or [] if x.get("dia") == now.weekday()), key=lambda x: x.get("inicio", ""))
    if not hoy:
        return False

    def mins(hm):
        h, m = str(hm).split(":")[:2]
        return int(h) * 60 + int(m)
    t = now.hour * 60 + now.minute
    return mins(hoy[0]["inicio"]) - 30 <= t <= mins(max(x["fin"] for x in hoy)) + 30


# ----------------------------------------------------------------------------- dinero
_UNITS = {"mil": 1_000, "millon": 1_000_000, "millones": 1_000_000, "lucas": 1_000, "luca": 1_000, "k": 1_000}
_MONEY = re.compile(r"(?:\$\s*)?(\d+(?:[.,]\d+)*)\s*(mil|millones|millon|lucas|luca|k)?\b(?:\s*(?:pesos|cop))?")


def parse_amount(text):
    """«20 mil» → 20000 · «$15.000» → 15000 · «1,5 millones» → 1500000 · «un millón» → 1000000. → int o None."""
    t = norm(text)
    if re.search(r"\bun millon\b", t):
        return 1_000_000
    if re.search(r"\bmil pesos\b", t) and not re.search(r"\d", t):
        return 1_000
    m = _MONEY.search(t)
    if not m:
        return None
    num, unit = m.group(1), m.group(2)
    if unit:
        val = float(num.replace(",", ".")) if re.fullmatch(r"\d+[.,]\d{1,2}", num) else float(re.sub(r"[.,]", "", num))
        return int(round(val * _UNITS[unit]))
    digits = re.sub(r"[.,]", "", num) if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", num) else num.split(",")[0].split(".")[0]
    try:
        return int(digits)
    except ValueError:
        return None


def money(v):
    """20000 → «$20.000»."""
    return "$" + f"{int(v):,}".replace(",", ".")


def money_spoken(v):
    v = int(v)
    if v >= 1_000_000 and v % 100_000 == 0:
        m = v / 1_000_000
        return (f"{m:g}".replace(".", ",") + (" millón" if m == 1 else " millones")) + " de pesos"
    if v >= 1000 and v % 1000 == 0:
        return f"{v // 1000} mil pesos"
    return money(v) + " pesos"


CATS = [
    ("Comida", r"almuerzo|desayuno|cena|comida|restaurante|mercado|onces|cafe|tinto|pan|fruta|domicilio|rappi|pizza|hamburguesa|empanada|snack|gaseosa|supermercado"),
    ("Transporte", r"bus|taxi|uber|didi|gasolina|transmilenio|pasaje|peaje|parqueadero|moto|mio|metro|transporte|cabify|indriver"),
    ("Servicios", r"luz|agua|gas|internet|celular|plan|arriendo|administracion|energia|telefono|claro|movistar|tigo|netflix|spotify|disney|youtube premium|icloud"),
    ("Salud", r"drogueria|medicamento|medico|eps|cita|odontolog|farmacia|examen|gafas|pastillas"),
    ("Educación", r"libro|curso|fotocopia|papeleria|utiles|matricula|colegio|universidad|impresion|marcadores|cuaderno"),
    ("Hogar", r"aseo|detergente|ferreteria|mueble|cocina|limpieza|electrodomestico|lavanderia"),
    ("Ocio", r"cine|salida|cerveza|juego|concierto|paseo|viaje|regalo|ropa|zapatos|bar"),
]


def category(concept):
    c = norm(concept)
    for name, pat in CATS:
        if re.search(rf"\b(?:{pat})", c):
            return name
    return "Otros"


def add_expense(amount, concept, when=None):
    when = when or datetime.date.today()
    item = {"id": uuid.uuid4().hex[:8], "fecha": when.isoformat(), "monto": int(amount), "concepto": str(concept).strip()[:80] or "gasto",
            "categoria": category(concept)}
    data["gastos"].append(item)
    data["gastos"] = data["gastos"][-3000:]
    save()
    return item


def spent(period="mes", today=None, cat=""):
    """(total, {categoria: total}, n) del periodo: hoy|semana|mes|mes_pasado."""
    today = today or datetime.date.today()
    if period == "hoy":
        a, b = today, today
    elif period == "semana":
        a, b = today - datetime.timedelta(days=today.weekday()), today
    elif period == "mes_pasado":
        b = today.replace(day=1) - datetime.timedelta(days=1)
        a = b.replace(day=1)
    else:
        a, b = today.replace(day=1), today
    items = [g for g in data["gastos"] if a.isoformat() <= g["fecha"] <= b.isoformat() and (not cat or g["categoria"] == cat)]
    by = {}
    for g in items:
        by[g["categoria"]] = by.get(g["categoria"], 0) + g["monto"]
    return sum(g["monto"] for g in items), dict(sorted(by.items(), key=lambda kv: -kv[1])), len(items)


def undo_last_expense():
    if not data["gastos"]:
        return None
    g = data["gastos"].pop()
    save()
    return g


# ----------------------------------------------------------------------------- pagos del mes
def add_payment(name, day, amount=None, today=None):
    name = str(name).strip()[:60]
    day = max(1, min(31, int(day)))
    for p in data["pagos"]:
        if norm(p["nombre"]) == norm(name):
            p.update({"dia": day, "monto": amount if amount else p.get("monto")})
            save()
            return p
    p = {"id": uuid.uuid4().hex[:8], "nombre": name, "dia": day, "monto": amount, "pagado": "", "avisos": [],
         "creado": (today or datetime.date.today()).isoformat()}
    data["pagos"].append(p)
    save()
    return p


def find_payment(name):
    n = norm(name)
    return next((p for p in data["pagos"] if norm(p["nombre"]) == n), None) or \
        next((p for p in data["pagos"] if n and (n in norm(p["nombre"]) or norm(p["nombre"]) in n)), None)


def remove_payment(name):
    p = find_payment(name)
    if p:
        data["pagos"].remove(p)
        save()
    return p


def _due_date(p, today):
    import calendar
    last = calendar.monthrange(today.year, today.month)[1]
    d = today.replace(day=min(p["dia"], last))
    fresh = str(p.get("creado", "")) > d.isoformat()     # lo agregaste después del día de este mes: el primero es el otro
    if d < today and p.get("pagado") != today.strftime("%Y-%m") and not fresh:
        return d                                         # vencido este mes y sin pagar
    if p.get("pagado") == today.strftime("%Y-%m") or d < today or fresh:
        y, m = (today.year + (today.month == 12), today.month % 12 + 1)
        return datetime.date(y, m, min(p["dia"], calendar.monthrange(y, m)[1]))
    return d


def upcoming(today=None, within=5):
    """[(pago, fecha, días que faltan)] de los que vencen pronto o ya se vencieron sin pagar, del más urgente al último."""
    today = today or datetime.date.today()
    out = []
    for p in data["pagos"]:
        d = _due_date(p, today)
        left = (d - today).days
        if left <= within:
            out.append((p, d, left))
    return sorted(out, key=lambda x: x[2])


def mark_paid(name, today=None):
    p = find_payment(name)
    if p:
        p["pagado"] = (today or datetime.date.today()).strftime("%Y-%m")
        save()
    return p


def payments_to_warn(today=None):
    """Los avisos que tocan hoy (2 días antes, el día y si se venció) y que no se han dado. Los marca como dados."""
    today = today or datetime.date.today()
    out = []
    for p, d, left in upcoming(today, 2):
        key = f"{today.isoformat()}"
        if left in (2, 0) or left < 0:
            if key not in p.get("avisos", []):
                p.setdefault("avisos", []).append(key)
                p["avisos"] = p["avisos"][-10:]
                out.append((p, d, left))
    if out:
        save()
    return out


def when_text(left):
    return "hoy" if left == 0 else "mañana" if left == 1 else f"en {left} días" if left > 0 else \
        ("ayer" if left == -1 else f"hace {-left} días")


# ----------------------------------------------------------------------------- listas
_NOT_LISTS = {"clase", "estudiantes", "asistencia", "curso", "cursos", "alumnos", "reproduccion", "canciones", "espera"}
_LIST_ALIAS = {"compras": "mercado", "super": "mercado", "supermercado": "mercado", "la compra": "mercado", "mandado": "mercado",
               "mandados": "mercado", "tareas": "pendientes", "por hacer": "pendientes", "cosas por hacer": "pendientes"}


def list_name(raw):
    n = norm(raw)
    n = re.sub(r"^(?:la |el |de |del |de la |mi |mis )+", "", n).strip()
    n = _LIST_ALIAS.get(n, n)
    return "" if not n or n in _NOT_LISTS else n[:40]


def split_items(text):
    parts = re.split(r",|\by\b|\be\b|;", str(text))
    out = []
    for p in parts:
        p = re.sub(r"^\s*(?:un|una|unos|unas|el|la|los|las)\s+", "", p.strip(" .")).strip()
        if p:
            out.append(p[:60])
    return out


def add_items(lst, items):
    L = data["listas"].setdefault(lst, [])
    added = []
    for it in items:
        if not any(norm(x["item"]) == norm(it) and not x["hecho"] for x in L):
            L.append({"item": it, "hecho": False})
            added.append(it)
    save()
    return added


def pending_items(lst):
    return [x["item"] for x in data["listas"].get(lst, []) if not x["hecho"]]


def check_items(items, lst=None):
    """«ya compré leche»: la marca como hecha (en esa lista o en la que esté). → [(lista, item)]."""
    done = []
    for it in items:
        n = norm(it)
        for name in ([lst] if lst else list(data["listas"])):
            for x in data["listas"].get(name, []):
                if not x["hecho"] and (norm(x["item"]) == n or (len(n) > 2 and n in norm(x["item"]))):
                    x["hecho"] = True
                    done.append((name, x["item"]))
                    break
    if done:
        save()
    return done


def remove_items(lst, items):
    L = data["listas"].get(lst, [])
    gone = [x["item"] for x in L if any(norm(x["item"]) == norm(i) for i in items)]
    data["listas"][lst] = [x for x in L if x["item"] not in gone]
    save()
    return gone


def clear_list(lst):
    had = len(pending_items(lst))
    data["listas"].pop(lst, None)
    save()
    return had


# ----------------------------------------------------------------------------- disparadores
EVENTS = {"cargador_on": "Al conectar el cargador", "cargador_off": "Al desconectar el cargador", "wifi": "Al conectarte al Wi-Fi",
          "bateria_baja": "Cuando la batería esté baja", "app": "Al abrir un programa", "encender": "Al encender el PC"}
_T_SEP = r"\s*(?:,|\bentonces\b|\bhaz\b|\bque\b|:)?\s*"


def parse_trigger(t):
    """«cuando conecte el cargador, modo general» → {"evento","valor","accion"} o None. t ya normalizado."""
    t = norm(t).rstrip(".")
    if not t.startswith("cuando "):
        return None
    rest = t[7:]
    pats = [
        ("cargador_on", r"(?:conecte|enchufe|ponga|pongo|conecto|enchufo)\s+(?:el\s+)?cargador"),
        ("cargador_off", r"(?:desconecte|desenchufe|quite|quito|desconecto)\s+(?:el\s+)?cargador"),
        ("bateria_baja", r"(?:la\s+)?bateria\s+(?:este|esta|baje|llegue|quede)\s+(?:baja|(?:a|al|del?)\s+\d+\s*%?|en\s+\d+\s*%?)"),
        ("encender", r"(?:encienda|prenda|enciendo|prendo|arranque)\s+(?:el\s+)?(?:pc|computador|portatil|equipo)"),
    ]
    for ev, p in pats:
        m = re.match(rf"({p}){_T_SEP}(.+)$", rest)
        if m:
            n = re.search(r"(\d+)", m.group(1)) if ev == "bateria_baja" else None
            return {"evento": ev, "valor": (n.group(1) if n else "20") if ev == "bateria_baja" else "", "accion": m.group(2).strip()}
    m = re.match(r"(?:me\s+)?(?:conecte|llegue|entre)\s+(?:a\s+la\s+red|al\s+wifi|al\s+wi\s?fi|a\s+la\s+wifi)\s+(?:del?\s+|de\s+la\s+)?(.+)$", rest)
    if m:
        name, act = _name_and_action(m.group(1))
        return {"evento": "wifi", "valor": name, "accion": act} if act else None
    m = re.match(r"(?:abra|abro|inicie|inicio|abras)\s+(?:el\s+|la\s+)?(.+)$", rest)
    if m:
        name, act = _name_and_action(m.group(1))
        if act:
            return {"evento": "app", "valor": name, "accion": act}
    return None


def _name_and_action(body):
    """«Colegio San José, modo docente» → (nombre, acción); sin coma, el nombre es la primera palabra."""
    if "," in body:
        name, act = body.split(",", 1)
    else:
        name, _, act = body.partition(" ")
    return name.strip(), act.strip()


def add_trigger(tr):
    if not tr or not tr.get("accion") or norm(tr["accion"]).startswith("cuando"):
        return None
    for x in data["disparadores"]:
        if x["evento"] == tr["evento"] and norm(x.get("valor", "")) == norm(tr.get("valor", "")):
            x["accion"] = tr["accion"]
            save()
            return x
    x = {"id": uuid.uuid4().hex[:8], "evento": tr["evento"], "valor": tr.get("valor", ""), "accion": tr["accion"][:200],
         "creado": datetime.date.today().isoformat()}
    data["disparadores"].append(x)
    data["disparadores"] = data["disparadores"][-40:]
    save()
    return x


def describe(x):
    base = EVENTS.get(x["evento"], x["evento"])
    if x["evento"] == "wifi":
        base += f" «{x['valor']}»"
    elif x["evento"] == "app":
        base = f"Al abrir {x['valor']}"
    elif x["evento"] == "bateria_baja":
        base = f"Con la batería en {x['valor'] or 20} %"
    return f"{base}: «{x['accion']}»"


def remove_trigger(ref):
    """Por número (1, 2…) o por una palabra del evento o la acción."""
    L = data["disparadores"]
    hit = None
    if str(ref).strip().isdigit() and 1 <= int(ref) <= len(L):
        hit = L[int(ref) - 1]
    else:
        n = norm(ref)
        hit = next((x for x in L if n and (n in norm(describe(x)))), None)
    if hit:
        L.remove(hit)
        save()
    return hit


def fire(events):
    """Los disparadores que corresponden a estos eventos [(evento, valor)]."""
    out = []
    for ev, val in events:
        for x in data["disparadores"]:
            if x["evento"] != ev:
                continue
            if ev in ("wifi", "app") and norm(x["valor"]) not in norm(val) and norm(val) != norm(x["valor"]):
                continue
            if ev == "bateria_baja" and val is not None and int(val) > int(x.get("valor") or 20):
                continue
            out.append(x)
    return out
