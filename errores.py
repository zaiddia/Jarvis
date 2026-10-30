"""Registro de errores (8.0): los fallos reales quedan guardados con la orden que los causó, para poder arreglarlos.

Se guardan en errores.jsonl (los últimos 400), sin claves: cualquier clave o contraseña que aparezca en el texto se
reemplaza por ***. El «informe» junta la prueba completa, los últimos errores y el final del registro en un texto que
puedes enviar a quien te ayuda con Jarvis.
"""
import datetime
import json
import os
import re
import threading
import traceback

_lock = threading.Lock()
_path = None
MAX = 400
_secrets = []           # función que devuelve las claves actuales (para taparlas)
_recent = {}            # firma → hora, para no repetir el mismo error 100 veces seguidas


def configure(config_dir, secrets_fn=None):
    global _path
    _path = os.path.join(config_dir, "errores.jsonl")
    if secrets_fn:
        _secrets[:] = [secrets_fn]


def scrub(text):
    text = str(text)
    if _secrets:
        try:
            for v in sorted((x for x in _secrets[0]() if isinstance(x, str) and len(x) >= 6), key=len, reverse=True):
                text = text.replace(v, "***")
        except Exception:
            pass
    text = re.sub(r"(?i)(key|token|apikey|password|secret|bearer)([=:\s\"']+)[A-Za-z0-9_\-.]{8,}", r"\1\2***", text)
    text = re.sub(r"bot\d{6,}:[A-Za-z0-9_\-]{20,}", "bot***", text)
    return text


def record(origin, error, cmd="", tb=None, level="error"):
    """Guarda un error. error puede ser una excepción o un texto. Devuelve la entrada (o None si se repitió)."""
    if isinstance(error, BaseException):
        msg = f"{type(error).__name__}: {error}"
        tb = tb or "".join(traceback.format_exception(type(error), error, error.__traceback__))[-3000:]
    else:
        msg = str(error)
    sig = f"{origin}|{msg[:120]}"
    now = datetime.datetime.now()
    last = _recent.get(sig)
    if last and (now - last).total_seconds() < 60:
        return None
    _recent[sig] = now
    if len(_recent) > 300:
        _recent.clear()
    item = {"t": now.isoformat(timespec="seconds"), "nivel": level, "origen": str(origin)[:40], "error": scrub(msg)[:800],
            "orden": scrub(cmd)[:300], "traza": scrub(tb or "")[-3000:]}
    if not _path:
        return item
    with _lock:
        try:
            os.makedirs(os.path.dirname(_path), exist_ok=True)
            with open(_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
            if os.path.getsize(_path) > 600_000:
                _trim()
        except OSError:
            pass
    return item


def _trim():
    with open(_path, encoding="utf-8") as f:
        lines = f.readlines()[-MAX:]
    with open(_path + ".tmp", "w", encoding="utf-8") as f:
        f.writelines(lines)
    os.replace(_path + ".tmp", _path)


def recent(n=50):
    if not _path or not os.path.exists(_path):
        return []
    out = []
    with _lock:
        try:
            with open(_path, encoding="utf-8") as f:
                for line in f.readlines()[-n:]:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
        except OSError:
            pass
    return out


def clear():
    if _path and os.path.exists(_path):
        with _lock:
            os.remove(_path)


def report(version, check_text, log_lines, n=40):
    """Texto del informe para enviar (sin claves)."""
    errs = recent(n)
    out = [f"INFORME DE JARVIS {version} — {datetime.datetime.now():%Y-%m-%d %H:%M}", "", check_text or "(sin prueba completa)",
           "", f"ÚLTIMOS ERRORES ({len(errs)})"]
    for e in errs:
        out.append(f"\n[{e['t']}] {e['nivel'].upper()} en {e['origen']}: {e['error']}")
        if e.get("orden"):
            out.append(f"  orden: «{e['orden']}»")
        if e.get("traza"):
            out.append("  " + e["traza"].strip().replace("\n", "\n  ")[-1500:])
    out += ["", "FINAL DEL REGISTRO", *[scrub(x) for x in list(log_lines)[-120:]]]
    return "\n".join(out)


def spoken(n_days=7):
    cut = (datetime.datetime.now() - datetime.timedelta(days=n_days)).isoformat()
    errs = [e for e in recent(200) if e["t"] >= cut and e["nivel"] == "error"]
    if not errs:
        return f"No he tenido errores en los últimos {n_days} días."
    last = errs[-1]
    return (f"He tenido {len(errs)} error{'es' if len(errs) != 1 else ''} esta semana. El último, en {last['origen']}: "
            f"{last['error'][:160]}. Puedes enviarme el informe desde Ajustes, sección Acerca de.")
