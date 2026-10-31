"""Tu estilo al escribir (9.5): los correos y comunicados que Jarvis redacta suenan como tú.

Jarvis guarda (solo en tu equipo) los últimos textos que enviaste o aprobaste con él, y con varios de ellos la IA
resume tu forma de escribir: cómo saludas y te despides, el tono, el largo y las expresiones que usas. Ese resumen se
usa al redactar correos, respuestas e informes. También: «aprende mi estilo con este texto: …».
"""
import datetime
import json
import os
import re
import threading

_lock = threading.Lock()
_path = None
data = {"ejemplos": [], "perfil": "", "perfil_n": 0}
MAX = 15


def configure(config_dir):
    global _path
    _path = os.path.join(config_dir, "estilo.json")
    load()


def load():
    global data
    try:
        with open(_path, encoding="utf-8") as f:
            d = json.load(f)
        data = d if isinstance(d, dict) else {}
    except (OSError, ValueError, TypeError):
        data = {}
    data.setdefault("ejemplos", [])
    data.setdefault("perfil", "")
    data.setdefault("perfil_n", 0)


def save():
    if not _path:
        return
    try:
        os.makedirs(os.path.dirname(_path), exist_ok=True)
        with open(_path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(_path + ".tmp", _path)
    except OSError:
        pass


def add_example(texto, tipo="correo"):
    """Guarda un texto tuyo. Devuelve True si conviene (re)calcular el perfil."""
    t = re.sub(r"[ \t]+", " ", str(texto)).strip()
    if len(t) < 60:
        return False
    with _lock:
        if any(e["texto"] == t[:2500] for e in data["ejemplos"]):
            return False
        data["ejemplos"].append({"texto": t[:2500], "tipo": tipo, "fecha": datetime.date.today().isoformat()})
        del data["ejemplos"][:-MAX]
        save()
    n = len(data["ejemplos"])
    return n >= 3 and (not data["perfil"] or n - data["perfil_n"] >= 3)


def profile_prompt():
    ex = "\n\n---\n\n".join(e["texto"] for e in data["ejemplos"][-10:])
    return ("Estos son textos que escribió un docente en Colombia. Describe su estilo de escritura para que otro pueda imitarlo: "
            "cómo saluda y cómo se despide (con ejemplos literales cortos), tono (formal, cercano…), trato (usted/tú), largo "
            "típico, puntuación, expresiones o muletillas frecuentes y cómo firma. Máximo 90 palabras, en viñetas cortas, sin "
            "copiar datos personales de terceros.\n\n" + ex[:9000])


def set_profile(text):
    with _lock:
        data["perfil"] = str(text).strip()[:900]
        data["perfil_n"] = len(data["ejemplos"])
        save()


def context():
    if not data["perfil"]:
        return ""
    return " Escribe imitando el estilo del docente (así escribe): " + data["perfil"].replace("\n", " ")


def clear():
    with _lock:
        data.update(ejemplos=[], perfil="", perfil_n=0)
        save()
