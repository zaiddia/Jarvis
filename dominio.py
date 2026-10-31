"""Ruta de dominio y tarjetas con repaso espaciado (11.2). Lógica pura, sin Jarvis.

· Ruta de dominio: los temas del periodo en el orden de tu planeación. Un tema queda DOMINADO cuando el estudiante,
  en el nivel avanzado de la práctica, acierta dos seguidos a la primera. El siguiente tema se abre solo cuando
  domina el anterior (la práctica no lo deja saltar), pero los repasos de lo que falló siguen apareciendo.
· Tarjetas (Leitner): pregunta corta → respuesta. Si la sabe, la tarjeta pasa a la siguiente caja y vuelve más tarde
  (1, 3, 7, 14 y 30 días); si no, vuelve a la caja 1 (mañana). Se exportan para Anki o Quizlet.
"""
import datetime
import os
import re
import threading
import uuid

import datos

_lock = threading.Lock()
_path = None
data = {"mazos": {}, "rep": {}}      # mazos: {curso: {tema: [{"id", "frente", "reverso"}]}}; rep: {curso: {est: {id: {"caja", "proxima"}}}}
locked = False
INTERVAL = {1: 1, 2: 3, 3: 7, 4: 14, 5: 30}


def configure(config_dir):
    global _path
    _path = os.path.join(config_dir, "tarjetas.json")
    load()


def load():
    global data, locked
    try:
        d = datos.read_json(_path)
        data, locked = (d if isinstance(d, dict) and "mazos" in d else {"mazos": {}, "rep": {}}), False
        data.setdefault("rep", {})
    except datos.DataLocked:
        data, locked = {"mazos": {}, "rep": {}}, True
    except (OSError, ValueError, TypeError):
        data = {"mazos": {}, "rep": {}}


def save():
    if not _path or locked:
        return
    try:
        datos.write_json(_path, data)
    except OSError:
        pass


def _norm(t):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", str(t).lower())).strip()


# ----------------------------------------------------------------------------- ruta de dominio
def mastered(t):
    """¿Domina el tema? (nivel 3 y dos aciertos seguidos a la primera en ese nivel, o ya marcado)."""
    return bool(t and (t.get("dom") or (t.get("nivel", 1) >= 3 and t.get("racha", 0) >= 2)))


def status(route, temas):
    """route: [temas en orden]; temas: los de la práctica del estudiante. → [{"tema", "estado", "nivel", "pct"}].
    Estados: dominado · actual (el que está abierto) · en progreso (abierto antes de un repaso) · bloqueado."""
    out, opened = [], False
    for tema in route:
        t = _match(tema, temas)
        if mastered(t):
            est = "dominado"
        elif not opened:
            est, opened = "actual", True
        else:
            est = "bloqueado"
        out.append({"tema": tema, "estado": est, "nivel": (t or {}).get("nivel", 1) if t else 0,
                    "pct": round(100 * t["ok"] / t["n"]) if t and t.get("n") else None})
    return out


def _match(tema, temas):
    k = _norm(tema)
    if tema in temas:
        return temas[tema]
    for name, t in temas.items():
        if _norm(name) == k:
            return t
    return None


def current(route, temas):
    """El tema abierto de la ruta (el primero sin dominar) o None si ya domina todo."""
    for s in status(route, temas):
        if s["estado"] == "actual":
            return s["tema"]
    return None


def course_view(route, students):
    """{est: [estados]} y por tema cuántos lo dominan. students: {est: temas}."""
    rows = {e: status(route, t) for e, t in students.items()}
    per = [{"tema": tema, "dominan": sum(1 for r in rows.values() if r[i]["estado"] == "dominado"), "total": len(rows)} for i, tema in enumerate(route)]
    return rows, per


# ----------------------------------------------------------------------------- tarjetas
def cards_prompt(tema, grado, asignatura="Matemáticas", n=10):
    return (f"Crea {n} tarjetas de memoria (flashcards) de {asignatura} para grado {grado} en Colombia sobre «{tema}»: en el frente una "
            "pregunta corta (definición, propiedad, fórmula, un cálculo rápido o un ejemplo) y en el reverso la respuesta breve y exacta. "
            "Texto plano, sin LaTeX (usa x², √9, 3/4). Responde SOLO con JSON: {\"tarjetas\": [{\"frente\": str, \"reverso\": str}]}")


def clean_cards(d):
    out = []
    for c in (d.get("tarjetas") or [])[:30] if isinstance(d, dict) else []:
        if isinstance(c, dict) and str(c.get("frente", "")).strip() and str(c.get("reverso", "")).strip():
            out.append({"id": uuid.uuid4().hex[:10], "frente": str(c["frente"]).strip()[:300], "reverso": str(c["reverso"]).strip()[:400]})
    return out


def add_deck(curso, tema, cards):
    with _lock:
        deck = data["mazos"].setdefault(curso, {}).setdefault(tema, [])
        have = {_norm(c["frente"]) for c in deck}
        new = [c for c in cards if _norm(c["frente"]) not in have]
        deck.extend(new)
        save()
    return len(new)


def all_cards(curso):
    return [(tema, c) for tema, cs in data["mazos"].get(curso, {}).items() for c in cs]


def due(curso, est, today=None, limit=20):
    """Las tarjetas que le tocan hoy (las nuevas primero de a 5, luego las vencidas)."""
    today = (today or datetime.date.today()).isoformat()
    rep = data["rep"].get(curso, {}).get(est, {})
    vencidas = [(t, c) for t, c in all_cards(curso) if c["id"] in rep and rep[c["id"]]["proxima"] <= today]
    nuevas = [(t, c) for t, c in all_cards(curso) if c["id"] not in rep][:5]
    return (vencidas + nuevas)[:limit]


def review(curso, est, card_id, knew, today=None):
    today = today or datetime.date.today()
    with _lock:
        r = data["rep"].setdefault(curso, {}).setdefault(est, {}).setdefault(card_id, {"caja": 0, "proxima": today.isoformat()})
        r["caja"] = min(5, r["caja"] + 1) if knew else 1
        r["proxima"] = (today + datetime.timedelta(days=INTERVAL[r["caja"]])).isoformat()
        save()
        return r


def stats(curso):
    """Por estudiante: tarjetas vistas y cuántas en las cajas altas (4 y 5 = las sabe a largo plazo)."""
    out = {}
    for est, rep in data["rep"].get(curso, {}).items():
        out[est] = {"vistas": len(rep), "firmes": sum(1 for r in rep.values() if r["caja"] >= 4)}
    return out


def export_tsv(curso, path):
    """Para Anki y Quizlet: una tarjeta por línea, «frente<TAB>reverso<TAB>etiqueta»."""
    rows = []
    for tema, c in all_cards(curso):
        clean = lambda s: str(s).replace("\t", " ").replace("\n", " ")
        rows.append(f"{clean(c['frente'])}\t{clean(c['reverso'])}\t{re.sub(r'[^0-9A-Za-zÁÉÍÓÚÑáéíóúñ]+', '_', tema)[:40]}")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("#separator:tab\n#html:false\n#tags column:3\n" + "\n".join(rows) + "\n")
    return len(rows)
