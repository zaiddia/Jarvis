"""12.0: Jarvis con rostro holográfico, en el HUD (en lugar del reactor) y a pantalla completa en el proyector.

El rostro mueve la boca al ritmo de lo que dice, parpadea, mira hacia arriba cuando piensa y cambia de expresión según
lo que responde (contento cuando algo quedó listo, preocupado con un error o una alerta, curioso con una pregunta).
El dibujo está en static/js/avatar.js. Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import re

from nucleo import J


@J.app.route("/rostro")
def face_page():
    from flask import render_template
    return render_template("rostro.html", asset_v=getattr(J, "ASSET_V", ""))


def _set_face(on):
    J.settings["hud_avatar"] = bool(on)
    try:
        J.save_settings_file()
    except OSError:
        pass
    J.socketio.emit("settings_updated", J.public_settings())


_FC_ON = re.compile(r"\b(?:muestra|muestrame|pon|ponte|activa|ensename)\s+(?:tu\s+|el\s+)?(?:rostro|cara|avatar|holograma)\b|\bmodo (?:rostro|holograma|avatar)\b")
_FC_OFF = re.compile(r"\b(?:quita|quitate|oculta|desactiva|apaga)\s+(?:tu\s+|el\s+)?(?:rostro|cara|avatar|holograma)\b|\bvuelve al (?:reactor|orbe)\b")
_FC_BEAM = re.compile(r"\b(?:proyecta|pon|lleva)\s+(?:tu\s+)?(?:rostro|cara|avatar|holograma)\s+(?:en|al)\s+(?:el\s+)?(?:proyector|televisor|tablero|videobeam)\b|"
                      r"\b(?:rostro|holograma) en el proyector\b")


def face_voice(text, t):
    if _FC_BEAM.search(t):
        J.open_window("/rostro", "Rostro")
        J.reply("Ahí estoy, en grande. Lleva la ventana al proyector y pulsa F11 para pantalla completa.", "ROSTRO")
        return True
    if _FC_OFF.search(t):
        _set_face(False)
        J.reply("Vuelvo al reactor.", "ROSTRO")
        return True
    if _FC_ON.search(t):
        _set_face(True)
        J.reply("¡Hola! Así me veo. Para verme en grande en el salón: «proyecta tu rostro en el proyector».", "ROSTRO")
        return True
    return False


__all__ = ['_FC_BEAM', '_FC_OFF', '_FC_ON', '_set_face', 'face_page', 'face_voice']
