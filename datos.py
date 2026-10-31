"""Datos de estudiantes protegidos (8.9): notas, observador, cursos con asistencia y diario de clase cifrados en tu
equipo (son datos de menores de edad, Ley 1581 de 2012).

Se cifran con una clave propia (AES, con la librería «cryptography»). Esa clave se guarda a su vez cifrada con la
protección de Windows, así que solo tu usuario la puede abrir. Para usar los mismos datos en otro equipo (o restaurar
una copia en un equipo nuevo) se usa la «clave de recuperación»: la copias en Ajustes y la pegas en el otro equipo.

Si un archivo está cifrado y no hay clave (o es otra), Jarvis no lo lee ni lo sobrescribe: queda «bloqueado» hasta
que pegues la clave correcta. Así nunca se pierden datos por un error de clave.
"""
import json
import os

MARK = b"JVENC1:"
_cfg = {"key": lambda: "", "on": lambda: False}


class DataLocked(Exception):
    """El archivo está cifrado y no hay clave correcta para abrirlo."""


def available():
    try:
        from cryptography.fernet import Fernet  # noqa: F401
        return True
    except Exception:
        return False


def configure(key_fn, on_fn):
    _cfg.update(key=key_fn, on=on_fn)


def new_key():
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


def valid_key(k):
    try:
        from cryptography.fernet import Fernet
        Fernet(str(k).strip().encode())
        return True
    except Exception:
        return False


def is_encrypted(raw):
    return isinstance(raw, (bytes, bytearray)) and bytes(raw[:len(MARK)]) == MARK


def decrypt(raw, key=None):
    from cryptography.fernet import Fernet, InvalidToken
    k = (key if key is not None else _cfg["key"]()) or ""
    if not k:
        raise DataLocked("falta la clave de los datos de estudiantes")
    try:
        return Fernet(k.strip().encode()).decrypt(bytes(raw[len(MARK):]))
    except (InvalidToken, ValueError, TypeError):
        raise DataLocked("la clave de los datos de estudiantes no es la de este archivo")


def encrypt(plain, key=None):
    from cryptography.fernet import Fernet
    k = key if key is not None else _cfg["key"]()
    return MARK + Fernet(k.strip().encode()).encrypt(plain)


def loads(raw):
    """Bytes del archivo (cifrado o no) → objeto. Lanza DataLocked o ValueError."""
    if is_encrypted(raw):
        if not available():
            raise DataLocked("falta la librería «cryptography» (ejecuta instalar.bat)")
        raw = decrypt(raw)
    return json.loads(raw.decode("utf-8"))


def read_json(path):
    """El contenido del archivo, o None si no existe. Lanza DataLocked si está cifrado y no se puede abrir."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return None
    return loads(raw)


def dumps(obj, encrypt_it=None):
    plain = json.dumps(obj, ensure_ascii=False, indent=1).encode("utf-8")
    on = _cfg["on"]() if encrypt_it is None else encrypt_it
    if on and available() and _cfg["key"]():
        return encrypt(plain)
    return plain


def write_json(path, obj, encrypt_it=None):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(dumps(obj, encrypt_it))
    os.replace(tmp, path)


def file_state(path):
    """«cifrado», «sin cifrar», «bloqueado» o «no existe»."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return "no existe"
    if not is_encrypted(raw):
        return "sin cifrar"
    try:
        decrypt(raw)
        return "cifrado"
    except DataLocked:
        return "bloqueado"
