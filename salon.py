"""El salón (12.12): recuperaciones con seguimiento, asistencia con QR que cambia, coevaluación y laboratorio de Python.
Lógica pura. Son datos de estudiantes: se cifran como las notas si lo activaste (datos.read_json / write_json).

- Recuperaciones: quién quedó por debajo de 3,0, su plan (taller, fecha, criterios) y el seguimiento hasta que aprueba.
- Asistencia por QR: el código cambia cada 30 s (pasarlo por chat no sirve) y un celular marca a un solo estudiante.
- Coevaluación: cada estudiante valora a sus compañeros de grupo con una rúbrica corta; el promedio va a «Ser».
- Laboratorio de Python: el código corre en el navegador del celular (no en tu equipo); Jarvis guarda cómo va cada uno.
"""
import datetime
import hashlib
import hmac
import os
import re
import threading

import datos

_lock = threading.Lock()
_path = None
locked = False
data = {"recup": {}, "asist": {}, "coev": {}, "lab": {}}
WINDOW = 30                                              # segundos que dura cada código del QR
UMBRAL = 3.0
CRITERIOS = ["Participó y aportó ideas", "Cumplió con su parte a tiempo", "Escuchó y respetó a los demás", "Ayudó a que el grupo avanzara"]


def configure(config_dir):
    global _path
    _path = os.path.join(config_dir, "salon.json")
    load()


def load():
    global locked
    locked = False
    for k in data:
        data[k] = {}
    if not _path:
        return
    try:
        d = datos.read_json(_path)
        if isinstance(d, dict):
            for k in data:
                if isinstance(d.get(k), dict):
                    data[k] = d[k]
    except datos.DataLocked:
        locked = True
    except (OSError, ValueError, TypeError):
        pass


def save():
    if not _path or locked:
        return
    with _lock:
        try:
            datos.write_json(_path, data)
        except OSError:
            pass


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


# ============================================================================ RECUPERACIONES
def at_risk(vals, umbral=UMBRAL):
    """vals: {estudiante: valoración o None} → [(estudiante, valoración)] por debajo del umbral, de la más baja a la más alta."""
    return sorted(((e, v) for e, v in vals.items() if v is not None and v < umbral), key=lambda x: x[1])


def recup_open(curso, est, val, fecha_limite, taller="", criterios=""):
    with _lock:
        c = data["recup"].setdefault(curso, {})
        old = c.get(est)
        if old and old["estado"] in ("pendiente", "entregado"):
            return old
        c[est] = {"val_inicial": val, "fecha_limite": fecha_limite.isoformat(), "taller": taller[:2000], "criterios": criterios[:1000],
                  "estado": "pendiente", "nota": None, "creado": _now(), "historial": [f"{_now()[:10]} plan creado"], "avisos": []}
    save()
    return data["recup"][curso][est]


def recup_result(curso, est, nota, umbral=UMBRAL):
    """Anota la nota de la recuperación: aprobada (≥ 3,0) o no aprobada. → el registro o None."""
    r = data["recup"].get(curso, {}).get(est)
    if not r:
        return None
    nota = round(float(nota), 1)
    r.update(nota=nota, estado="aprobada" if nota >= umbral else "no_aprobada")
    r["historial"].append(f"{_now()[:10]} nota {str(nota).replace('.', ',')}: {'aprobó' if nota >= umbral else 'no aprobó'}")
    save()
    return r


def recup_delivered(curso, est):
    r = data["recup"].get(curso, {}).get(est)
    if r and r["estado"] == "pendiente":
        r["estado"] = "entregado"
        r["historial"].append(f"{_now()[:10]} entregó el taller")
        save()
    return r


def recup_summary(curso=None, today=None):
    """{curso: {"pendiente": [...], "entregado": [...], "aprobada": [...], "no_aprobada": [...], "vencidas": [...]}}."""
    today = (today or datetime.date.today()).isoformat()
    out = {}
    for c, ests in data["recup"].items():
        if curso and c != curso:
            continue
        s = {"pendiente": [], "entregado": [], "aprobada": [], "no_aprobada": [], "vencidas": []}
        for e, r in sorted(ests.items()):
            s[r["estado"]].append(e)
            if r["estado"] == "pendiente" and r["fecha_limite"] < today:
                s["vencidas"].append(e)
        out[c] = s
    return out


def recup_to_warn(today=None):
    """Avisos de hoy: recuperaciones que vencen en 2 días, hoy, o que se vencieron sin entregar. [(curso, est, días)]."""
    today = today or datetime.date.today()
    out = []
    for c, ests in data["recup"].items():
        for e, r in ests.items():
            if r["estado"] != "pendiente":
                continue
            left = (datetime.date.fromisoformat(r["fecha_limite"]) - today).days
            if left in (2, 0, -1) and today.isoformat() not in r.get("avisos", []):
                r.setdefault("avisos", []).append(today.isoformat())
                out.append((c, e, left))
    if out:
        save()
    return out


# ============================================================================ ASISTENCIA CON QR QUE CAMBIA
def qr_token(secret, now_ts, window=WINDOW):
    w = int(now_ts // window)
    return hmac.new(str(secret).encode(), str(w).encode(), hashlib.sha256).hexdigest()[:10]


def qr_valid(secret, token, now_ts, window=WINDOW):
    """Vale el código de ahora o el anterior (hasta 60 s): da tiempo de abrirlo, no de reenviarlo."""
    t = str(token or "")
    return any(hmac.compare_digest(t, qr_token(secret, now_ts - k * window, window)) for k in (0, 1))


def attend(curso, est, fecha, hora, tarde=False, device=""):
    """Marca la llegada. → (ok, mensaje). Un celular marca a un solo estudiante por día y curso."""
    with _lock:
        day = data["asist"].setdefault(curso, {}).setdefault(fecha, {})
        if est in day:
            return True, f"Ya estabas marcado a las {day[est]['hora']}."
        if device and any(v.get("dev") == device and k != est for k, v in day.items()):
            return False, "Este celular ya marcó la llegada de otro estudiante. Cada uno marca desde su propio celular."
        day[est] = {"hora": hora, "tarde": bool(tarde), "dev": device[:40]}
        for old in sorted(data["asist"][curso])[:-120]:
            data["asist"][curso].pop(old)
    save()
    return True, ("Llegada marcada, pero tarde." if tarde else "¡Llegada marcada!")


def attended(curso, fecha):
    return data["asist"].get(curso, {}).get(fecha, {})


# ============================================================================ COEVALUACIÓN
def coev_new(sid, curso, grupos=None, criterios=None):
    data["coev"][sid] = {"curso": curso, "criterios": list(criterios or CRITERIOS), "grupos": grupos or [], "resp": {}, "creado": _now(),
                         "cerrada": False}
    save()
    return data["coev"][sid]


def coev_peers(s, est):
    """A quiénes evalúa: los de su grupo (o, sin grupos, los que él escoja)."""
    for g in s.get("grupos") or []:
        if est in g:
            return [x for x in g if x != est]
    return []


def coev_submit(s, evaluador, evaluado, notas):
    if evaluador == evaluado:
        return False, "No te puedes evaluar a ti mismo aquí (para eso está la autoevaluación)."
    peers = coev_peers(s, evaluador)
    if peers and evaluado not in peers:
        return False, "Solo puedes evaluar a los compañeros de tu grupo."
    try:
        vals = [max(1, min(5, int(n))) for n in notas][:len(s["criterios"])]
    except (TypeError, ValueError):
        return False, "Califica cada criterio de 1 a 5."
    if len(vals) != len(s["criterios"]):
        return False, "Falta calificar algún criterio."
    with _lock:
        s["resp"].setdefault(evaluador, {})[evaluado] = vals
    save()
    return True, "¡Gracias! Quedó guardado."


def coev_results(s, min_votes=2):
    """{evaluado: {"nota", "votos", "por_criterio"}}; la nota es el promedio de 1 a 5 (con al menos min_votes compañeros)."""
    acc = {}
    for _ev, given in s["resp"].items():
        for who, vals in given.items():
            acc.setdefault(who, []).append(vals)
    out = {}
    for who, rows in acc.items():
        n = len(rows)
        per = [round(sum(r[i] for r in rows) / n, 1) for i in range(len(s["criterios"]))]
        avg = sum(per) / len(per)
        nota = int(avg * 10 + 0.5 + 1e-9) / 10                      # redondeo de colegio: 4,25 → 4,3
        out[who] = {"nota": nota if n >= min_votes else None, "votos": n, "por_criterio": per}
    return out


# ============================================================================ LABORATORIO DE PYTHON
def lab_new(sid, curso, reto="", esperada=""):
    data["lab"][sid] = {"curso": curso, "reto": str(reto)[:600], "esperada": str(esperada)[:2000], "est": {}, "creado": _now(), "cerrado": False}
    save()
    return data["lab"][sid]


def same_output(expected, got):
    """¿La salida es la pedida? (ignora espacios al final de las líneas y líneas vacías al final)."""
    def clean(t):
        return "\n".join(ln.rstrip() for ln in str(t).replace("\r", "").strip().splitlines())
    return bool(str(expected).strip()) and clean(expected) == clean(got)


def lab_record(s, est, code, output, error=""):
    with _lock:
        e = s["est"].setdefault(est, {"corridas": 0, "errores": 0, "ok": False, "t": ""})
        e["corridas"] += 1
        e["errores"] += 1 if error else 0
        e.update(codigo=str(code)[:8000], salida=str(output)[:2000], error=str(error)[:500], t=_now())
        if not error and same_output(s.get("esperada", ""), output):
            e["ok"] = True
    save()
    return e


def lab_summary(s, names):
    done = [n for n in names if s["est"].get(n, {}).get("ok")]
    working = [n for n in names if n in s["est"] and n not in done]
    stuck = [n for n in working if s["est"][n]["errores"] >= 3 and s["est"][n].get("error")]
    idle = [n for n in names if n not in s["est"]]
    return {"listos": done, "trabajando": working, "atascados": stuck, "sin_empezar": idle}


def clean_name(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()[:80]
