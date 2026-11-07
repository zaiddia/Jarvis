"""Mis aplicaciones (12.14): tarjetas para abrir programas, webs, carpetas y archivos con tus frases.

Lógica pura: guardar, buscar la tarjeta de una frase, avisar de frases repetidas, grupos y horario.
nucleo/aplicaciones.py abre las cosas, muestra la página y escucha las frases.
"""
import datetime
import difflib
import json
import os
import re
import threading
import time
import unicodedata
import uuid

TIPOS = {"app": "Programa", "web": "Web", "carpeta": "Carpeta", "archivo": "Archivo"}
DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
_lock = threading.Lock()
_path = None
data = {"apps": [], "grupos": [], "importado": False}


def norm(text):
    t = unicodedata.normalize("NFD", str(text or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\b(?:por favor|porfa|jarvis)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def configure(config_dir):
    global _path
    _path = os.path.join(config_dir, "mis_apps.json")
    load()


def load():
    data.update(apps=[], grupos=[], importado=False)
    if not _path:
        return
    try:
        with open(_path, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            data["apps"] = [a for a in d.get("apps") or [] if isinstance(a, dict) and a.get("id")]
            data["grupos"] = [g for g in d.get("grupos") or [] if isinstance(g, dict) and g.get("id")]
            data["importado"] = bool(d.get("importado"))
    except (OSError, ValueError):
        pass


def save():
    if not _path:
        return
    with _lock:
        try:
            tmp = _path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, _path)
        except OSError:
            pass


# ============================================================================ TARJETAS
def guess_tipo(destino):
    d = str(destino or "").strip().strip('"')
    if re.match(r"^https?://", d, re.I) or re.match(r"^www\.", d, re.I):
        return "web"
    if d.lower().startswith("shell:") or (os.path.splitext(d)[1] == "" and ("\\" in d or "/" in d)):
        return "carpeta"
    if re.search(r"\.(?:exe|lnk|bat|cmd|msc|appref-ms)$", d, re.I) or ":" in d and not ("\\" in d or "/" in d):
        return "app"                                          # también ms-settings:, appid…
    return "archivo" if os.path.splitext(d)[1] else "app"


def _clean_phrases(frases):
    out, seen = [], set()
    for f in frases or []:
        f = re.sub(r"\s+", " ", str(f)).strip().strip('"«»').strip()
        if f and norm(f) and norm(f) not in seen and len(f) <= 80:
            seen.add(norm(f))
            out.append(f)
    return out[:12]


def _horario(h):
    if not isinstance(h, dict) or not h.get("hora"):
        return None
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", str(h["hora"]).strip())
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise ValueError("la hora va como 06:50")
    dias = sorted({int(x) for x in h.get("dias") or [] if str(x).isdigit() and 0 <= int(x) <= 6}) or [0, 1, 2, 3, 4]
    return {"hora": f"{int(m.group(1)):02d}:{m.group(2)}", "dias": dias}


def upsert(item):
    """Crea o cambia una tarjeta. → la tarjeta. Lanza ValueError si falta algo."""
    nombre = re.sub(r"\s+", " ", str(item.get("nombre") or "")).strip()[:60]
    destino = str(item.get("destino") or "").strip().strip('"')[:600]
    if not nombre:
        raise ValueError("ponle un nombre")
    if not destino:
        raise ValueError("falta qué abrir (la ruta, la dirección web o la carpeta)")
    tipo = item.get("tipo") if item.get("tipo") in TIPOS else guess_tipo(destino)
    if tipo == "web":
        if re.match(r"^www\.", destino, re.I) or re.match(r"^[\w-]+(?:\.[\w-]+)+(?:/\S*)?$", destino):
            destino = "https://" + destino
        if not re.match(r"^https?://\S+$", destino, re.I):
            raise ValueError("la dirección web debe empezar por https://")
    frases = _clean_phrases(item.get("frases") or [])
    if not frases:
        frases = [f"abre {nombre.lower()}"]
    rec = {"id": item.get("id") or uuid.uuid4().hex[:8], "nombre": nombre, "tipo": tipo, "destino": destino, "frases": frases,
           "navegador": str(item.get("navegador") or "")[:20] if tipo == "web" else "",
           "appid": bool(item.get("appid")) and tipo == "app", "horario": _horario(item.get("horario")),
           "usos": 0, "ultimo": ""}
    with _lock:
        old = next((a for a in data["apps"] if a["id"] == rec["id"]), None)
        if old:
            rec["usos"], rec["ultimo"] = old.get("usos", 0), old.get("ultimo", "")
            data["apps"][data["apps"].index(old)] = rec
        else:
            data["apps"].append(rec)
    save()
    return rec


def remove(cid):
    with _lock:
        n = len(data["apps"]) + len(data["grupos"])
        data["apps"] = [a for a in data["apps"] if a["id"] != cid]
        data["grupos"] = [g for g in data["grupos"] if g["id"] != cid]
        for g in data["grupos"]:
            g["items"] = [x for x in g["items"] if x != cid]
        changed = n != len(data["apps"]) + len(data["grupos"])
    if changed:
        save()
    return changed


def upsert_group(item):
    nombre = re.sub(r"\s+", " ", str(item.get("nombre") or "")).strip()[:60]
    ids = [a["id"] for a in data["apps"]]
    items = [x for x in item.get("items") or [] if x in ids][:12]
    if not nombre:
        raise ValueError("ponle un nombre al grupo")
    if len(items) < 2:
        raise ValueError("un grupo abre al menos dos tarjetas")
    rec = {"id": item.get("id") or uuid.uuid4().hex[:8], "nombre": nombre, "items": items,
           "frases": _clean_phrases(item.get("frases") or []) or [nombre.lower()], "horario": _horario(item.get("horario")),
           "usos": 0, "ultimo": ""}
    with _lock:
        old = next((g for g in data["grupos"] if g["id"] == rec["id"]), None)
        if old:
            rec["usos"], rec["ultimo"] = old.get("usos", 0), old.get("ultimo", "")
            data["grupos"][data["grupos"].index(old)] = rec
        else:
            data["grupos"].append(rec)
    save()
    return rec


def get(cid):
    return next((x for x in data["apps"] + data["grupos"] if x["id"] == cid), None)


def used(cid):
    x = get(cid)
    if x:
        x["usos"] = int(x.get("usos", 0)) + 1
        x["ultimo"] = datetime.datetime.now().isoformat(timespec="minutes")
        save()


def most_used(n=5):
    return sorted((x for x in data["apps"] + data["grupos"] if x.get("usos")), key=lambda x: (-x["usos"], x["nombre"]))[:n]


# ============================================================================ FRASES
def phrase_index():
    """{frase normalizada: (tarjeta o grupo)}; los grupos y las tarjetas por nombre también."""
    idx = {}
    for x in data["grupos"] + data["apps"]:
        for f in x["frases"]:
            idx.setdefault(norm(f), x)
    return idx


def match_phrase(text, fuzzy=0.9):
    """La tarjeta o grupo cuya frase es justo lo que dijiste (tolera una letra mal oída). → elemento o None."""
    t = norm(text)
    if not t:
        return None
    idx = phrase_index()
    if t in idx:
        return idx[t]
    if len(t) >= 6:
        best = difflib.get_close_matches(t, list(idx), n=1, cutoff=fuzzy)
        if best and abs(len(best[0]) - len(t)) <= 3:
            return idx[best[0]]
    return None


def match_name(q, cutoff=0.86):
    """Para «abre <nombre>»: por el nombre de la tarjeta o del grupo. → elemento o None."""
    q = norm(q)
    if not q:
        return None
    names = {}
    for x in data["grupos"] + data["apps"]:
        names.setdefault(norm(x["nombre"]), x)
        for f in x["frases"]:
            names.setdefault(re.sub(r"^(?:abre|abrir|abreme|pon|ponme|inicia|lanza|entra a|ve a)\s+(?:el |la |los |las |mi |mis )?", "", norm(f)), x)
    if q in names:
        return names[q]
    best = difflib.get_close_matches(q, list(names), n=1, cutoff=cutoff)
    return names[best[0]] if best else None


def conflicts(frases, own_id="", builtin=()):
    """Avisos para estas frases: repetidas en otra tarjeta, o iguales a algo que Jarvis ya hace. → [texto]."""
    out = []
    idx = {}
    for x in data["grupos"] + data["apps"]:
        if x["id"] == own_id:
            continue
        for f in x["frases"]:
            idx.setdefault(norm(f), x)
    for f in frases:
        n = norm(f)
        if n in idx:
            out.append(f"«{f}» ya abre «{idx[n]['nombre']}».")
        elif len(n) < 4:
            out.append(f"«{f}» es muy corta: Jarvis podría confundirla al oír.")
        else:
            for b in builtin:
                if n == b:
                    out.append(f"«{f}» es una orden que Jarvis ya conoce; con esta tarjeta ganará tu tarjeta.")
                    break
    return out


# ============================================================================ HORARIO
def due(now=None, fired=None):
    """Tarjetas o grupos que tocan ahora (en este minuto o hasta 2 min tarde), una vez al día. → [elemento]."""
    now = now or datetime.datetime.now()
    fired = fired if fired is not None else {}
    out = []
    for x in data["grupos"] + data["apps"]:
        h = x.get("horario")
        if not h or now.weekday() not in h["dias"]:
            continue
        hh, mm = map(int, h["hora"].split(":"))
        at = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        key = f"{x['id']}:{now.date().isoformat()}"
        if 0 <= (now - at).total_seconds() < 180 and key not in fired:
            fired[key] = time.time()
            out.append(x)
    return out


def describe_schedule(h):
    if not h:
        return ""
    d = h["dias"]
    days = "entre semana" if d == [0, 1, 2, 3, 4] else "todos los días" if d == list(range(7)) else ", ".join(DIAS[i] for i in d)
    return f"{days} a las {h['hora']}"


# ============================================================================ IMPORTAR EL FORMATO DE TEXTO
def import_text(text):
    """Las líneas «nombre = destino» de Ajustes pasan a tarjetas (si no existen ya). → cuántas."""
    n = 0
    for line in str(text or "").splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if not k or not v:
            continue
        if any(norm(a["nombre"]) == norm(k) and a["destino"] == v for a in data["apps"]):
            continue
        try:
            upsert({"nombre": k[:1].upper() + k[1:], "destino": v, "frases": [f"abre {k}", k]})
            n += 1
        except ValueError:
            pass
    return n
