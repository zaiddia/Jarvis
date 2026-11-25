"""12.57: pulido tras revisar 75 frases reales.

  · «tómame una foto» / «toma una foto con la cámara»: cuenta tres segundos y la guarda en Imágenes › Jarvis › Fotos.
  · La charla («te quiero, Jarvis», «eres muy lento», «estoy aburrido», «buenos días») va directo a la respuesta, sin el
    enrutador de órdenes ni la capa de comprensión: una llamada a la IA en vez de dos.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import os
import re
import shutil

from nucleo import J

_P57_PHOTO = re.compile(r"^(?:jarvis )?(?:toma(?:me)?|saca(?:me)?|tomame|hazme) (?:una )?(?:foto|fotografia|selfie)(?: con la (?:camara|webcam))?$|"
                        r"^(?:toma|saca) (?:una )?foto (?:de|a) (?:mi|esto|lo que tengo)(?: con la camara)?$")
_P57_CHAT = re.compile(r"^(?:jarvis )?(?:te quiero|te amo|te extrane|eres (?:muy |lo |el |la |un |una )?\w+|estas (?:muy )?\w+|"
                       r"estoy (?:aburrid[oa]|feliz|content[oa]|cansad[oa]|triste|bien|mal|estresad[oa]|agotad[oa])|me siento \w+|"
                       r"no (?:me )?entendiste|no me entiendes|que (?:lento|rapido|chevere|bacano|bien|mal|pena|risa)|jaja\w*|"
                       r"buenos dias|buenas tardes|buenas|hola|que mas|quiubo|como amaneciste|como te fue|como vas)(?: jarvis)?(?: .{0,40})?$")
_P57_ORDER = re.compile(r"\b(?:abre|pon|ponme|crea|haz|hazme|busca|manda|envia|recuerdame|apaga|sube|baja|cierra|llama|anota|agrega|"
                        r"dime|dame|muestrame|lee|prepara|genera|calcula|traduce|ayudame)\b")


def p57_chatty(t):
    """¿Es charla (sin orden dentro)? Entonces va directo a la respuesta."""
    return bool(_P57_CHAT.match(t)) and not _P57_ORDER.search(t) and len(t.split()) <= 12


def _p57_photo():
    try:
        path = J.capture_camera(wait=3.0)
    except Exception as e:
        J.reply(str(e), "CÁMARA")
        return
    folder = os.path.join(J.settings.get("output_dir") or os.path.expanduser("~"), "Fotos")
    try:
        os.makedirs(folder, exist_ok=True)
        dest = os.path.join(folder, f"foto_{datetime.datetime.now():%Y%m%d_%H%M%S}{os.path.splitext(path)[1] or '.png'}")
        shutil.copyfile(path, dest)
    except OSError as e:
        J.reply(f"Tomé la foto, pero no pude guardarla ({e}).", "CÁMARA")
        return
    J.reply("¡Lista! La guardé en tu carpeta de Jarvis, en Fotos.", "CÁMARA")
    J.card("tip", "Foto", os.path.basename(dest), "📷", secs=6)


def pulir57_voice(text, t):
    d = J.skills.parse(text) if re.match(r"^(?:jarvis )?(?:llama|marca|haz(?:le|me)? una llamada|llamada)", t) else None
    if d and d[0] == "llamar" and not J.skills.resolve_contact(d[1]["contacto"]):        # 12.58: sin número, ni preguntar «¿llamo?»
        J.reply(f"No tengo el número de «{d[1]['contacto']}». Añádelo en Ajustes › Cuentas y mensajes › Contactos, o dime "
                "el número con el código de país, por ejemplo «llama al +57 300 123 4567».", "PC")
        return True
    if _P57_PHOTO.match(t):
        J.reply("Mira a la cámara: en tres segundos.", "CÁMARA")
        J.start_job("Tomando la foto", J._p57_photo, "foto")
        return True
    return False


__all__ = ['_P57_CHAT', '_P57_ORDER', '_P57_PHOTO', '_p57_photo', 'p57_chatty', 'pulir57_voice']
