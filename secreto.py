"""Claves cifradas (8.0): las claves de la IA, Telegram, Classroom, WhatsApp y el correo se guardan en config.json
cifradas con la protección de datos de Windows (DPAPI). Solo tu usuario de Windows, en este equipo, puede abrirlas: si
alguien copia la carpeta de Jarvis a otro equipo, las claves no le sirven.

En modo portable (USB) no se cifran (DPAPI ata las claves a un equipo y en la USB dejarían de funcionar en otro PC).
Fuera de Windows se guardan como antes.
"""
import base64
import ctypes
import sys

PREFIX = "dpapi:"
_ENTROPY = b"Jarvis-config-v8"
IS_WIN = sys.platform == "win32"


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data):
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def available():
    return IS_WIN and hasattr(ctypes, "windll")


def _crypt(data, protect):
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    src, _keep = _blob(data)
    ent, _keep2 = _blob(_ENTROPY)
    out = _Blob()
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    # CRYPTPROTECT_UI_FORBIDDEN = 0x1: nunca muestra ventanas
    if not fn(ctypes.byref(src), ctypes.c_wchar_p("Jarvis") if protect else None, ctypes.byref(ent), None, None, 0x1,
              ctypes.byref(out)):
        raise OSError("DPAPI no pudo procesar la clave")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def is_sealed(value):
    return isinstance(value, str) and value.startswith(PREFIX)


def seal(value, enabled=True):
    """Texto cifrado listo para config.json (o el mismo texto si no se puede o no se debe cifrar)."""
    if not enabled or not value or not isinstance(value, str) or is_sealed(value) or not available():
        return value
    try:
        return PREFIX + base64.b64encode(_crypt(value.encode("utf-8"), True)).decode()
    except OSError:
        return value


def unseal(value):
    """(texto, ok). ok=False si estaba cifrada y no se pudo abrir (otro equipo u otro usuario)."""
    if not is_sealed(value):
        return value, True
    if not available():
        return "", False
    try:
        return _crypt(base64.b64decode(value[len(PREFIX):]), False).decode("utf-8"), True
    except (OSError, ValueError, UnicodeDecodeError):
        return "", False


def seal_all(data, fields, enabled=True):
    out = dict(data)
    for k in fields:
        if isinstance(out.get(k), str) and out[k]:
            out[k] = seal(out[k], enabled)
    return out


