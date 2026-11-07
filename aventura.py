"""Aventura matemática por equipos (12.0). Lógica pura, sin Jarvis.

La IA escribe una historia por capítulos (escapar de una nave, resolver un misterio…) y cada puerta se abre con un
problema del tema. Las respuestas se comprueban con SymPy cuando se puede (si la IA marcó mal la correcta, se arregla).
Aquí está el juego: equipos, jugadores, respuestas desde el celular, puntos y el podio final.
"""
import random
import re
import secrets
import threading
import time

import verificar

TEAMS = [("Fénix", "🔥"), ("Cometas", "☄️"), ("Tiburones", "🦈"), ("Búhos", "🦉"), ("Robots", "🤖"), ("Dragones", "🐉")]
THEMES = ["escapar de una nave espacial que se queda sin oxígeno", "resolver el misterio del museo donde desapareció una joya",
          "encontrar el tesoro perdido de una isla del Caribe", "salvar la ciudad de un apagón total", "salir de un templo antiguo lleno de trampas",
          "detener a un robot que se salió de control en el colegio"]
_lock = threading.Lock()


def prompt(tema, grado="", capitulos=5, trama=""):
    trama = trama or random.choice(THEMES)
    return f"""Crea una AVENTURA MATEMÁTICA por equipos para estudiantes de {grado or 'bachillerato'} sobre: {tema}.
Trama: {trama}. Es una historia emocionante contada por capítulos; cada capítulo termina frente a una puerta (o un obstáculo) \
que solo se abre resolviendo un problema de {tema}. Los problemas suben de dificultad poco a poco y se pueden resolver en 1 o 2 minutos.
En español de Colombia, con suspenso y humor sano. {capitulos} capítulos.
Responde SOLO un JSON:
{{"titulo": "…", "intro": "2 o 3 frases que presentan la misión",
 "capitulos": [{{"titulo": "…", "historia": "3 o 4 frases que cuentan lo que pasa y terminan en la puerta",
   "problema": "el enunciado (corto, con números concretos)", "opciones": ["A", "B", "C", "D"], "correcta": 0,
   "explicacion": "por qué (una o dos frases)",
   "verificacion": {{"tipo": "ecuacion" | "expresion" | "ninguna", "expr": "2x + 3 = 7 o 3/4 + 1/2", "resultado": "el valor de la opción correcta"}}}}],
 "final": "2 o 3 frases épicas: la misión se cumplió"}}
Cada pregunta tiene 4 opciones con distractores creíbles (errores típicos) y una sola correcta."""


def _txt(v, n=600):
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def clean(d):
    """Valida la aventura y verifica con SymPy la respuesta correcta de cada capítulo. → (aventura, n corregidas)."""
    if not isinstance(d, dict):
        raise ValueError("la aventura no es un JSON")
    caps, fixed = [], 0
    for c in (d.get("capitulos") or [])[:10]:
        if not isinstance(c, dict):
            continue
        ops = [_txt(o, 120) for o in (c.get("opciones") or [])][:4]
        if len(ops) < 2 or not _txt(c.get("problema")):
            continue
        try:
            k = int(c.get("correcta", 0))
        except (TypeError, ValueError):
            k = 0
        k = k if 0 <= k < len(ops) else 0
        v = c.get("verificacion")
        if isinstance(v, dict) and v.get("tipo") in ("ecuacion", "expresion"):
            chk = verificar.check({**v, "resultado": ops[k]})
            if chk["ok"] is False and chk["correcto"]:
                hit = next((i for i, o in enumerate(ops) if verificar.check({**v, "resultado": o})["ok"]), None)
                if hit is None:
                    continue                       # ninguna opción es la correcta: ese capítulo no se juega
                k, fixed = hit, fixed + 1
        caps.append({"titulo": _txt(c.get("titulo"), 80) or f"Capítulo {len(caps) + 1}", "historia": _txt(c.get("historia"), 700),
                     "problema": _txt(c.get("problema"), 400), "opciones": ops, "correcta": k, "explicacion": _txt(c.get("explicacion"), 300)})
    if len(caps) < 2:
        raise ValueError("la aventura trae muy pocos capítulos válidos")
    return {"titulo": _txt(d.get("titulo"), 80) or "Aventura matemática", "intro": _txt(d.get("intro"), 600), "capitulos": caps,
            "final": _txt(d.get("final"), 600) or "¡Misión cumplida!"}, fixed


# ============================================================================ JUEGO
def new_game(adv, n_teams=4, segundos=60, curso="", tema=""):
    n = max(2, min(len(TEAMS), int(n_teams or 4)))
    return {"code": secrets.token_urlsafe(4), "adv": adv, "curso": curso, "tema": tema, "fase": "sala", "cap": -1, "segundos": int(segundos),
            "equipos": [{"nombre": nm, "emoji": em, "puntos": 0} for nm, em in TEAMS[:n]], "jugadores": {}, "respuestas": {}, "t0": 0.0,
            "puertas": [], "ver": 0}


def join(g, nombre, equipo, pid=None):
    nombre = _txt(nombre, 30)
    if not nombre:
        return None, "Escribe tu nombre."
    try:
        e = int(equipo)
    except (TypeError, ValueError):
        return None, "Escoge tu equipo."
    if not 0 <= e < len(g["equipos"]):
        return None, "Ese equipo no existe."
    with _lock:
        pid = pid if pid in g["jugadores"] else secrets.token_urlsafe(6)
        g["jugadores"][pid] = {"nombre": nombre, "equipo": e}
        g["ver"] += 1
    return pid, ""


def advance(g, now=None):
    """sala → historia → pregunta → revelar → historia (siguiente) … → final."""
    now = now or time.time()
    with _lock:
        f = g["fase"]
        if f in ("sala", "revelar"):
            if g["cap"] + 1 >= len(g["adv"]["capitulos"]):
                g["fase"] = "final"
            else:
                g["cap"] += 1
                g["fase"] = "historia"
        elif f == "historia":
            g["fase"], g["respuestas"], g["t0"] = "pregunta", {}, now
        elif f == "pregunta":
            _reveal(g)
        g["ver"] += 1
        return g["fase"]


def answer(g, pid, op, now=None):
    now = now or time.time()
    with _lock:
        if g["fase"] != "pregunta":
            return False, "Espera al siguiente reto."
        if pid not in g["jugadores"]:
            return False, "Primero únete a un equipo."
        if pid in g["respuestas"]:
            return False, "Ya respondiste."
        try:
            op = int(op)
        except (TypeError, ValueError):
            return False, "Escoge una opción."
        cap = g["adv"]["capitulos"][g["cap"]]
        if not 0 <= op < len(cap["opciones"]):
            return False, "Escoge una opción."
        g["respuestas"][pid] = {"op": op, "t": now - g["t0"]}
        g["ver"] += 1
        everyone = len(g["respuestas"]) >= len(g["jugadores"])
    if everyone:
        advance(g, now)
    return True, "¡Respuesta enviada!"


def time_left(g, now=None):
    if g["fase"] != "pregunta":
        return None
    return max(0, int(g["segundos"] - ((now or time.time()) - g["t0"])))


def _reveal(g):
    """Puntos: cada equipo gana 100 × la parte de sus jugadores que acertó, + hasta 50 por rapidez del primero en acertar."""
    cap = g["adv"]["capitulos"][g["cap"]]
    res, total_ok = [], 0
    for i, eq in enumerate(g["equipos"]):
        mem = [p for p, j in g["jugadores"].items() if j["equipo"] == i]
        ans = [g["respuestas"][p] for p in mem if p in g["respuestas"]]
        ok = [a for a in ans if a["op"] == cap["correcta"]]
        total_ok += len(ok)
        pts = 0
        if mem and ok:
            pts = round(100 * len(ok) / len(mem)) + round(50 * max(0.0, 1 - min(a["t"] for a in ok) / max(1, g["segundos"])))
        eq["puntos"] += pts
        res.append({"equipo": i, "puntos": pts, "aciertos": len(ok), "respuestas": len(ans), "miembros": len(mem)})
    answered = len(g["respuestas"])
    abierta = answered > 0 and total_ok * 2 >= answered
    g["puertas"].append(abierta)
    g["ultimo"] = {"resultados": res, "abierta": abierta, "aciertos": total_ok, "respuestas": answered}
    g["fase"] = "revelar"


def podium(g):
    return sorted(range(len(g["equipos"])), key=lambda i: -g["equipos"][i]["puntos"])


def public(g, pid=None, reveal_answer=False, now=None):
    """Lo que ve el celular (o el proyector con reveal_answer=True)."""
    cap = g["adv"]["capitulos"][g["cap"]] if 0 <= g["cap"] < len(g["adv"]["capitulos"]) else None
    me = g["jugadores"].get(pid) if pid else None
    out = {"ver": g["ver"], "fase": g["fase"], "titulo": g["adv"]["titulo"], "cap": g["cap"], "n_caps": len(g["adv"]["capitulos"]),
           "equipos": g["equipos"], "jugadores": len(g["jugadores"]), "respondieron": len(g["respuestas"]), "restante": time_left(g, now),
           "puertas": g["puertas"], "yo": me, "ya": bool(pid and pid in g["respuestas"])}
    if g["fase"] == "sala":
        out["intro"] = g["adv"]["intro"]
        out["por_equipo"] = [sum(1 for j in g["jugadores"].values() if j["equipo"] == i) for i in range(len(g["equipos"]))]
    if cap:
        out.update(cap_titulo=cap["titulo"], historia=cap["historia"])
        if g["fase"] in ("pregunta", "revelar"):
            out.update(problema=cap["problema"], opciones=cap["opciones"])
        if g["fase"] == "revelar" or (reveal_answer and g["fase"] == "revelar"):
            out.update(correcta=cap["correcta"], explicacion=cap["explicacion"], ultimo=g.get("ultimo"))
            if pid and pid in g["respuestas"]:
                out["acerte"] = g["respuestas"][pid]["op"] == cap["correcta"]
    if g["fase"] == "final":
        out.update(final=g["adv"]["final"], podio=podium(g))
    return out
