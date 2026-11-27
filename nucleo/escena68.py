"""12.68: escenas en 3D que se arman por partes, para el video beam.

  «Constrúyeme en 3D el sistema solar» · «arma en 3D la molécula de agua para séptimo» · «haz una escena 3D de un volcán».
  Se abre en su ventana y se va armando sola, parte por parte, con la explicación abajo. Se gira con el mouse o el dedo.
  Por voz: «siguiente parte», «parte anterior», «muéstralo todo», «deja de girar», «vuelve a armarla»,
  «muéstrales la escena en el celular» (QR) y «mis escenas 3D».

La IA solo describe la escena (formas, colores, movimientos); el dibujo lo hace la página de Jarvis (escena3d.py y
templates/escena3d.html). Antes de mostrarla, Jarvis revisa cada parte y, si algo no se vería, se la devuelve a la IA una vez.
Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import io
import json
import os
import re
import time

import escena3d as E3
from nucleo import J

e3d_state = {"sid": "", "at": 0.0}
_E68_COURSE = (r"(?:grado\s+)?(?:\d{1,2}\s?-?\s?[a-z0-9]?|sexto|septimo|octavo|noveno|decimo|once|primero|segundo|tercero|cuarto|quinto)")


def _e68_dir():
    return os.path.join(J.CONFIG_DIR, "escenas3d")


def e68_load(sid):
    if not re.fullmatch(r"[0-9a-f]{12}", str(sid or "")):
        return None
    try:
        with open(os.path.join(_e68_dir(), sid + ".json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def e68_save(scene, tema):
    os.makedirs(_e68_dir(), exist_ok=True)
    sid = os.urandom(6).hex()
    scene = dict(scene, tema=tema, creada=time.strftime("%Y-%m-%d %H:%M"))
    with open(os.path.join(_e68_dir(), sid + ".json"), "w", encoding="utf-8") as f:
        json.dump(scene, f, ensure_ascii=False)
    files = sorted((e for e in os.scandir(_e68_dir()) if e.name.endswith(".json")), key=lambda e: e.stat().st_mtime)
    for e in files[:-30]:                                  # como mucho 30 escenas guardadas
        try:
            os.remove(e.path)
        except OSError:
            pass
    return sid


def e68_list():
    out = []
    try:
        for e in sorted(os.scandir(_e68_dir()), key=lambda e: -e.stat().st_mtime):
            if e.name.endswith(".json"):
                s = e68_load(e.name[:-5])
                if s:
                    out.append((e.name[:-5], s))
    except OSError:
        pass
    return out


def make_scene(tema, curso=""):
    """IA → revisión → (si hay problemas serios) una corrección → escena lista. → (sid, escena, avisos)"""
    raw = J.ai_chat([{"role": "user", "content": E3.prompt(tema, curso)}], json_mode=True, max_tokens=6000)
    first = J._extract_json(raw)
    scene, problems = E3.check(first)
    if E3.serious(problems):
        J.log_terminal("La escena 3D tenía problemas; se la devuelvo a la IA: " + "; ".join(problems[:4]), "ESCENA 3D")
        try:
            raw2 = J.ai_chat([{"role": "user", "content": E3.prompt(tema, curso, problems, json.dumps(first, ensure_ascii=False))}],
                             json_mode=True, max_tokens=6000)
            s2, p2 = E3.check(J._extract_json(raw2))
            if s2 and (scene is None or len(E3.serious(p2)) <= len(E3.serious(problems))):
                scene, problems = s2, p2
        except (J.AIError, ValueError):
            pass
    if not scene:
        raise ValueError("la IA no logró una escena que se pueda dibujar")
    return e68_save(scene, tema), scene, E3.serious(problems)


@J.app.route("/escena3d/<sid>")
def e68_page(sid):
    from flask import abort, render_template
    s = e68_load(sid)
    if not s:
        abort(404)
    return render_template("escena3d.html", scene=s, sid=sid, mobile=False)


@J.mobile_app.route("/e3d/<sid>", methods=["GET"])
def e68_mobile(sid):
    from flask import abort, render_template
    s = e68_load(sid)
    if not s:
        abort(404)
    return render_template("escena3d.html", scene=s, sid=sid, mobile=True)


@J.app.route("/escena3d-qr.png")
def e68_qr():
    import qrcode
    from flask import Response, abort, request
    sid = request.args.get("s", "")
    if not e68_load(sid):
        abort(404)
    buf = io.BytesIO()
    qrcode.make(J._lan(f"/e3d/{sid}"), box_size=10, border=2).save(buf, format="PNG")
    return Response(buf.getvalue(), mimetype="image/png", headers={"Cache-Control": "no-store"})


def _e68_open(sid, title):
    e3d_state.update(sid=sid, at=time.time())
    J.open_window(f"/escena3d/{sid}", "Escena 3D · " + title)


_E68_MAKE = re.compile(
    r"^(?:jarvis\s+)?(?:construyeme|construye|construyenos|armame|arma|armanos|hazme|haz|crea|creame|muestrame|muestranos|muestrales|"
    r"dibujame|dibuja|modela|modelame|genera|generame)\s+(?:(?:en|una escena en|una escena de)\s+(?:3d|tres de|tres dimensiones)\s+(.+?)|"
    r"(?:una\s+)?escena\s+(?:en\s+)?(?:3d|tres de)\s+(?:de|del|de la|de los|de las|sobre|con)\s+(.+?)|"
    r"(.+?)\s+en\s+(?:3d|tres de|tres dimensiones))"
    rf"(?:\s+(?:para|en)\s+(?:el\s+|los de\s+)?({_E68_COURSE})\b.*)?$")
_E68_NEXT = re.compile(r"^(?:jarvis\s+)?(?:siguiente parte|la siguiente parte|siguiente pieza|sigue construyendo|construye lo siguiente|"
                       r"muestra la siguiente parte|siguiente paso)$")
_E68_PREV = re.compile(r"^(?:jarvis\s+)?(?:parte anterior|paso anterior|devuelvete una parte|quita la ultima parte)$")
_E68_ALL = re.compile(r"^(?:jarvis\s+)?(?:muestra(?:lo|la|me)?\s+(?:todo|toda la escena|completo|completa)|termina de (?:construir|armar)(?:la|lo)?)$")
_E68_SPIN = re.compile(r"^(?:jarvis\s+)?(?:para de girar|deja de girar|no gires|ponla a girar|ponlo a girar|girala|giralo|que gire)$")
_E68_AGAIN = re.compile(r"^(?:jarvis\s+)?(?:vuelve a armar(?:la|lo)|armala de nuevo|armala desde el principio)$")
_E68_PHONE = re.compile(r"^(?:jarvis\s+)?(?:muestrales|pasales|mandales|ponles)\s+(?:la|esta)\s+escena(?:\s+3d)?\s+(?:en|al|a)\s+(?:el|los)?\s*celular(?:es)?$")
_E68_LIST = re.compile(r"^(?:jarvis\s+)?(?:mis escenas(?: 3d| en 3d)?|que escenas (?:3d )?tengo|abre la ultima escena(?: 3d)?)$")


def _e68_active():
    return bool(e3d_state["sid"]) and time.time() - e3d_state["at"] < 3600


def _e68_cooking():
    ck = getattr(J, "_cook", None)
    return bool(ck and ck.get("recipe") and time.time() - ck.get("at", 0) < 3 * 3600)


def escena68_voice(text, t):
    if _e68_active():
        for rx, cmd in ((_E68_NEXT, "next"), (_E68_PREV, "prev"), (_E68_ALL, "all"), (_E68_AGAIN, "restart")):
            if rx.match(t) and not (cmd in ("next", "prev") and _e68_cooking()):
                J.socketio.emit("e3d", {"sid": e3d_state["sid"], "cmd": cmd})
                e3d_state["at"] = time.time()
                J.reply({"next": "Ahí va la siguiente parte.", "prev": "Quito la última parte.", "all": "Ahí está completa.",
                         "restart": "La vuelvo a armar desde el principio."}[cmd], "ESCENA 3D")
                return True
        if _E68_SPIN.match(t):
            stop = bool(re.search(r"para|deja|no gires", t))
            J.socketio.emit("e3d", {"sid": e3d_state["sid"], "cmd": "stop_spin" if stop else "spin"})
            J.reply("Quieta." if stop else "La pongo a girar.", "ESCENA 3D")
            return True
        if _E68_PHONE.match(t):
            if J._need_lan():
                return True
            J._open_projector()
            sid = e3d_state["sid"]
            J.socketio.emit("ticket", {"open": True, "url": J._lan(f"/e3d/{sid}"), "qr": f"/escena3d-qr.png?s={sid}", "tipo": "escena3d",
                                       "tema": (e68_load(sid) or {}).get("titulo", "Escena 3D"), "n": 0})
            J.reply("El QR está en el proyector: la abren en el celular y la giran con el dedo.", "ESCENA 3D")
            return True
    if _E68_LIST.match(t):
        lst = e68_list()
        if not lst:
            J.reply("Aún no has creado escenas 3D. Prueba: «constrúyeme en 3D el sistema solar».", "ESCENA 3D")
            return True
        if t.endswith("ultima escena") or "abre" in t:
            _e68_open(lst[0][0], lst[0][1]["titulo"])
            J.reply(f"Abro «{lst[0][1]['titulo']}».", "ESCENA 3D")
            return True
        J.reply(f"Tienes {len(lst)} escena{'s' if len(lst) != 1 else ''}: " + ", ".join(s["titulo"] for _i, s in lst[:6]) +
                ". Di «abre la última escena 3D» para verla.", "ESCENA 3D")
        return True
    m = _E68_MAKE.match(t)
    if not m or J._S3_RE.search(t):                       # «muéstrame el cubo en 3D»: los sólidos de siempre
        return False
    tema = (m.group(1) or m.group(2) or m.group(3) or "").strip()
    tema = re.sub(r"^(?:el|la|los|las|un|una|unos|unas)\s+", "", tema)
    if len(tema) < 3:
        return False
    if J.state.get("ai") != "ok":
        J.reply("Para diseñar la escena necesito la IA conectada.", "ESCENA 3D")
        return True
    curso = m.group(4) or ""
    J.reply(f"Diseño la escena en 3D de {tema}; en cuanto esté, se abre y se arma por partes.", "ESCENA 3D")

    def work():
        try:
            sid, scene, warn = J.make_scene(tema, curso)
        except (J.AIError, ValueError) as e:
            J.notify(J.ai_error_reply(e) if isinstance(e, J.AIError) else f"No pude armar la escena: {e}.", "ESCENA 3D")
            return
        _e68_open(sid, scene["titulo"])
        n = len(scene["pasos"])
        J.notify(f"Lista «{scene['titulo']}»: se arma en {n} partes. Gírala con el mouse; di «siguiente parte», «muéstralo todo» o "
                 "«muéstrales la escena en el celular»." + (" Corregí algunas piezas que no se iban a ver." if warn else ""), "ESCENA 3D")
    J.start_job("Diseñando la escena 3D", work, "escena3d")
    return True


__all__ = ['_E68_AGAIN', '_E68_ALL', '_E68_COURSE', '_E68_LIST', '_E68_MAKE', '_E68_NEXT', '_E68_PHONE', '_E68_PREV', '_E68_SPIN',
           '_e68_active', '_e68_cooking', '_e68_dir', '_e68_open', 'e3d_state', 'e68_list', 'e68_load', 'e68_mobile', 'e68_page',
           'e68_qr', 'e68_save', 'escena68_voice', 'make_scene']
