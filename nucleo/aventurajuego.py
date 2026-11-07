"""12.0: aventura matemática en el proyector. Un paso más allá de Kahoot.

«Jarvis, lanza una aventura de ecuaciones para 8A»: la IA cuenta una historia por capítulos y cada puerta se abre con
un problema del tema. Los celulares son los controles (se unen a un equipo con un QR), hay marcador en vivo, Jarvis
narra cada capítulo y el final es épico, con podio. La lógica está en aventura.py.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import io
import re
import threading
import time

import aula
import aventura
from nucleo import J

adv = {"g": None, "busy": False}


def _adv_emit():
    g = adv["g"]
    if g:
        J.socketio.emit("adv", dict(aventura.public(g, reveal_answer=True), url=J._lan(f"/x/{g['code']}")))


def make_adventure(tema, curso="", capitulos=5, equipos=4):
    g = aula.grade_of(curso) if curso else None
    raw = J.ai_chat([{"role": "user", "content": aventura.prompt(tema, f"{g}°" if g else "", capitulos) + J.lessons_ctx()}], json_mode=True,
                    max_tokens=7000)
    a, fixed = aventura.clean(J._extract_json(raw))
    if fixed:
        J.log_terminal(f"Aventura: corregí {fixed} respuesta(s) que la IA había marcado mal (SymPy).", "AVENTURA")
    adv["g"] = aventura.new_game(a, equipos, J.settings.get("adventure_secs", 60), curso, tema)
    return adv["g"]


def step(narrate=True):
    """El siguiente paso del juego (lo pulsa el docente en el proyector o lo dice por voz)."""
    g = adv["g"]
    if not g:
        return ""
    fase = aventura.advance(g)
    _adv_emit()
    if narrate and J.settings.get("adventure_voice", True):
        if fase == "historia":
            cap = g["adv"]["capitulos"][g["cap"]]
            J.speak(f"Capítulo {g['cap'] + 1}. {cap['titulo']}. {cap['historia']}")
        elif fase == "revelar":
            u = g.get("ultimo") or {}
            J.speak(("¡La puerta se abre!" if u.get("abierta") else "La puerta resiste… pero seguimos.") +
                    f" Acertaron {u.get('aciertos', 0)} de {u.get('respuestas', 0)}.")
        elif fase == "final":
            best = g["equipos"][aventura.podium(g)[0]]
            J.speak(f"{g['adv']['final']} ¡Ganan los {best['nombre']}, con {best['puntos']} puntos!")
    return fase


def _timer_worker():
    while True:
        time.sleep(1)
        g = adv["g"]
        try:
            if g and g["fase"] == "pregunta" and aventura.time_left(g) == 0:
                step()
            elif g and g["fase"] == "pregunta":
                J.socketio.emit("adv_tick", {"restante": aventura.time_left(g), "respondieron": len(g["respuestas"]), "jugadores": len(g["jugadores"])})
        except Exception as e:
            J.note_error("AVENTURA", e)


# ============================================================================ PROYECTOR
@J.app.route("/aventura")
def adventure_page():
    from flask import render_template
    return render_template("aventura.html", asset_v=getattr(J, "ASSET_V", ""))


@J.app.route("/aventura-qr.png")
def adventure_qr():
    import qrcode
    from flask import Response, abort
    g = adv["g"]
    if not g:
        abort(404)
    buf = io.BytesIO()
    qrcode.make(J._lan(f"/x/{g['code']}"), box_size=10, border=2).save(buf, format="PNG")
    return Response(buf.getvalue(), mimetype="image/png", headers={"Cache-Control": "no-store"})


@J.socketio.on("adv_state")
def handle_adv_state(data=None):
    g = adv["g"]
    if not g:
        return {"none": True, "busy": adv["busy"]}
    return dict(aventura.public(g, reveal_answer=True), url=J._lan(f"/x/{g['code']}"))


@J.socketio.on("adv_action")
def handle_adv_action(data=None):
    a = str((data or {}).get("a", ""))
    if a == "siguiente":
        return {"fase": step()}
    if a == "terminar":
        adv["g"] = None
        J.socketio.emit("adv", {"none": True})
        return {"ok": True}
    return {"ok": False}


# ============================================================================ CELULARES
def _game(code):
    from flask import abort
    g = adv["g"]
    if not g or g["code"] != str(code):
        abort(404)
    return g


@J.mobile_app.route("/x/<code>", methods=["GET"])
def adventure_phone(code):
    from flask import render_template
    g = _game(code)
    return render_template("aventura_movil.html", code=code, titulo=g["adv"]["titulo"], equipos=g["equipos"])


@J.mobile_app.route("/x/<code>/estado", methods=["GET"])
def adventure_phone_state(code):
    from flask import request
    g = _game(code)
    return aventura.public(g, request.args.get("p", ""))


@J.mobile_app.route("/x/<code>/unirme", methods=["POST"])
def adventure_join(code):
    from flask import request
    g = _game(code)
    d = request.get_json(silent=True) or {}
    pid, err = aventura.join(g, d.get("nombre", ""), d.get("equipo"), d.get("p"))
    if pid:
        _adv_emit()
    return {"ok": bool(pid), "p": pid or "", "msg": err}


@J.mobile_app.route("/x/<code>/responder", methods=["POST"])
def adventure_answer(code):
    from flask import request
    g = _game(code)
    d = request.get_json(silent=True) or {}
    ok, msg = aventura.answer(g, d.get("p", ""), d.get("op"))
    if ok:
        _adv_emit()
    return {"ok": ok, "msg": msg}


# ============================================================================ VOZ
_AV_MAKE = re.compile(r"\b(?:lanza|lanzame|haz|hazme|crea|creame|arma|armame|prepara|preparame|empieza|juguemos|jugar)\s+(?:una\s+|la\s+)?"
                      r"aventura(?:\s+matematica)?\s+(?:de|sobre|con)\s+(.+?)"
                      r"(?:\s+(?:para|en|con)\s+((?:grado\s+)?(?:\d{1,2}\s?[a-z]?|sexto|septimo|octavo|noveno|decimo|undecimo|once)\b.*))?$")
_AV_NEXT = re.compile(r"^(?:jarvis\s+)?(?:siguiente capitulo|sigue la aventura|siguiente reto|muestra el reto|abre la puerta|revela la respuesta|"
                      r"siguiente(?: paso)? de la aventura)$")
_AV_END = re.compile(r"\b(?:termina|cierra|acaba)\s+(?:la\s+)?aventura\b")
_AV_SCORE = re.compile(r"\b(?:como va|marcador de) la aventura\b|\bque equipo va ganando\b")


def adventure_voice(text, t):
    m = _AV_MAKE.search(t)
    if m:
        tema = m.group(1).strip()
        curso = (J._resolve_course(m.group(2)) if m.group(2) else "") or aula.data.get("activo", "")
        if J.state.get("ai") != "ok":
            J.reply("Para escribir la aventura necesito la IA conectada.", "AVENTURA")
            return True
        if J._need_lan():
            return True
        if adv["busy"]:
            J.reply("Ya estoy escribiendo una aventura; un momento.", "AVENTURA")
            return True
        n = re.search(r"\b(\d)\s+equipos\b", t)
        equipos = int(n.group(1)) if n else 4
        adv["busy"] = True
        J.reply(f"Escribo la aventura de «{tema}»: historia por capítulos, una puerta con un problema en cada uno. Abro el proyector…", "AVENTURA")

        def work():
            try:
                g = make_adventure(tema, curso, 5, equipos)
            except J.AIError as e:
                J.notify(J.ai_error_reply(e), "AVENTURA")
                return
            except Exception as e:
                J.notify(f"No pude armar la aventura: {e}", "AVENTURA")
                return
            finally:
                adv["busy"] = False
            J.open_window("/aventura", "Aventura")
            _adv_emit()
            J.notify(f"Lista «{g['adv']['titulo']}»: {len(g['adv']['capitulos'])} capítulos y {len(g['equipos'])} equipos. "
                     "Que escaneen el QR del proyector y escojan equipo; cuando estén, pulsa «Empezar» o di «siguiente capítulo».", "AVENTURA")
        J.start_job("Escribiendo la aventura", work, "aventura")
        return True
    if adv["g"] and _AV_NEXT.match(t):
        fase = step()
        J.reply({"historia": "Siguiente capítulo.", "pregunta": "¡A resolver!", "revelar": "Veamos…", "final": "¡Final!"}.get(fase, "Listo."),
                "AVENTURA")
        return True
    if adv["g"] and _AV_END.search(t):
        handle_adv_action({"a": "terminar"})
        J.reply("Terminé la aventura.", "AVENTURA")
        return True
    if adv["g"] and _AV_SCORE.search(t):
        g = adv["g"]
        orden = aventura.podium(g)
        J.reply("Marcador: " + ", ".join(f"{g['equipos'][i]['nombre']} {g['equipos'][i]['puntos']}" for i in orden) + ".", "AVENTURA")
        return True
    return False


def adventure_start():
    threading.Thread(target=_timer_worker, daemon=True, name="aventura").start()


__all__ = ['_AV_END', '_AV_MAKE', '_AV_NEXT', '_AV_SCORE', '_adv_emit', '_game', '_timer_worker', 'adv', 'adventure_answer', 'adventure_join',
           'adventure_page', 'adventure_phone', 'adventure_phone_state', 'adventure_qr', 'adventure_start', 'adventure_voice', 'aventura',
           'handle_adv_action', 'handle_adv_state', 'make_adventure', 'step']
