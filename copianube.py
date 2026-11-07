"""Copia de seguridad cifrada para la nube (12.8). Lógica pura.

La copia completa (el mismo .zip de siempre) se cifra con una clave que eliges tú: en tu Drive queda un archivo
«.jvbk» que nadie puede abrir sin esa clave, ni siquiera Google. En un equipo nuevo instalas Jarvis, conectas Google,
escribes la clave y la recuperas. La clave se convierte en llave con PBKDF2-SHA256 (muchas vueltas, con sal propia
de cada copia) y el contenido se cifra con Fernet (AES con verificación: si alguien lo altera, no abre).
"""
import base64
import hashlib
import io
import os
import zipfile

MAGIC = b"JARVIS-BK1\n"
ITER = 310_000
EXT = ".jvbk"
KEY_MEMBER = "clave_recuperacion.txt"       # la clave de los datos de estudiantes viaja DENTRO de la copia cifrada
MIN_PASS = 8


class WrongPassword(Exception):
    pass


def _key(password, salt):
    raw = hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"), salt, ITER, dklen=32)
    return base64.urlsafe_b64encode(raw)


def is_sealed(blob):
    return bytes(blob[:len(MAGIC)]) == MAGIC


def seal(raw, password):
    from cryptography.fernet import Fernet
    if len(str(password or "")) < MIN_PASS:
        raise ValueError(f"la clave de las copias debe tener al menos {MIN_PASS} caracteres")
    salt = os.urandom(16)
    return MAGIC + salt + Fernet(_key(password, salt)).encrypt(bytes(raw))


def unseal(blob, password):
    from cryptography.fernet import Fernet, InvalidToken
    if not is_sealed(blob):
        raise ValueError("ese archivo no es una copia cifrada de Jarvis")
    salt = blob[len(MAGIC):len(MAGIC) + 16]
    try:
        return Fernet(_key(password, salt)).decrypt(bytes(blob[len(MAGIC) + 16:]))
    except InvalidToken:
        raise WrongPassword("la clave no es la de esa copia")


def with_key(zip_bytes, data_key):
    """El .zip con la clave de recuperación de los datos de estudiantes adentro (así, con tu clave de las copias,
    un equipo nuevo abre también las notas cifradas)."""
    if not data_key:
        return bytes(zip_bytes)
    buf = io.BytesIO(bytes(zip_bytes))
    with zipfile.ZipFile(buf, "a", zipfile.ZIP_DEFLATED) as z:
        if KEY_MEMBER not in z.namelist():
            z.writestr(KEY_MEMBER, data_key)
    return buf.getvalue()


def split_key(zip_bytes):
    """(zip sin la clave, clave o "")."""
    src = zipfile.ZipFile(io.BytesIO(bytes(zip_bytes)))
    if KEY_MEMBER not in src.namelist():
        return bytes(zip_bytes), ""
    key = src.read(KEY_MEMBER).decode("utf-8", "replace").strip()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for it in src.infolist():
            if it.filename != KEY_MEMBER:
                z.writestr(it, src.read(it.filename))
    return out.getvalue(), key


def cloud_name(zip_name):
    """«Jarvis respaldo 2026-11-06 213000 (automática).zip» → «… .jvbk»."""
    return os.path.splitext(os.path.basename(zip_name))[0] + EXT


def is_copy(name):
    n = str(name).lower()
    return n.startswith("jarvis respaldo") and (n.endswith(".zip") or n.endswith(EXT))


def due(now, last_iso, hour=21):
    """¿Toca la copia de la noche? Una al día: desde la hora elegida; si el equipo estuvo apagado a esa hora, la primera
    vez que esté encendido al día siguiente (no se queda un día sin copia por apagarlo temprano)."""
    import datetime
    try:
        last = datetime.datetime.fromisoformat(last_iso) if last_iso else None
    except ValueError:
        last = None
    if last is None:
        return True                                    # nunca se ha hecho: ya
    if last.date() == now.date():
        return False
    if now.hour >= hour:
        return True
    return (now - last).total_seconds() > 30 * 3600
