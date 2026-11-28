"""12.74: Jarvis escoge la IA según el trabajo y nunca se queda parado.

  · Programar (generar, revisar, corregir código): la mejor para código entre las que tienes (Claude, ChatGPT, DeepSeek,
    Kimi en NVIDIA, GLM en Z.ai…). Ajustes: «ai_code_provider» (auto, off o una en concreto).
  · Si tu IA se llena, se cae o se queda sin saldo: pasa a la siguiente de la cadena (las de siempre, las demás con clave,
    las de servidores en China solo sin nombres de estudiantes, y la IA de tu PC de última).
  · La que falló descansa un momento: mientras tanto las preguntas van directo a la que sí responde (sin esperar).

La lógica pura está en enrutador.py. Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import time

import enrutador as EN
from nucleo import J

c73 = {"down": {}}
C73_MAX_BACKUPS = 4


def c73_keys():
    return {p for p, sp in J.PROVIDERS.items() if sp["group"] == "cloud" and str(J.settings.get(f"{p}_api_key") or "").strip()}


def c73_is_down(pid):
    return c73["down"].get(pid, 0) > time.time()


def c73_mark(cfg, kind):
    pid = (cfg or {}).get("ai_provider")
    if pid and kind in EN.DOWN_SECS and cfg.get("kind") and not J._is_local_ai(cfg):
        c73["down"][pid] = EN.down_until(kind)


def code_pick(cfg, messages):
    """La IA para un trabajo de código, o None (la tuya ya sirve, o no hay otra)."""
    if getattr(J._tl, "no_code", False) or J._is_local_ai(cfg) or J.net.get("offline"):
        return None
    if not EN.is_code(messages, getattr(J._tl, "task", "") == "code"):
        return None
    ch = EN.code_choice(cfg.get("ai_provider"), c73_keys(), str(J.settings.get("ai_code_provider", "auto") or "auto"))
    if not ch or c73_is_down(ch[0]):
        return None
    pid, model = ch
    try:
        cc = J._ai_cfg({"ai_provider": pid, f"{pid}_model": model} if model else {"ai_provider": pid})
    except Exception:
        return None
    if not cc.get("key"):
        return None
    cc["code"] = True
    if not getattr(J._tl, "code_said", False):
        J._tl.code_said = True
        J.log_terminal(f"Este trabajo de código lo hago con {cc['label']} ({(cc['model'] or '').split('/')[-1]}), la mejor para programar que tienes.", "IA")
    return cc


def c73_backups(cfg):
    """Las IA de respaldo, en orden (cfgs listos para usar)."""
    if cfg.get("backup") or cfg.get("heavy") or cfg.get("code") or J.net.get("offline") or not cfg.get("ai_provider"):
        return []
    want = str(J.settings.get("ai_backup_provider", "auto") or "off")
    first = J.backup_cfg(cfg)
    keys = c73_keys()
    try:
        local = bool(J.motor_ready())
    except Exception:
        local = False
    chain = EN.backup_chain(cfg.get("ai_provider"), keys, first["ai_provider"] if first else "",
                            has_names=bool(getattr(J._tl, "c73_names", False)), local=local, want=want)
    out = []
    for pid in chain:
        if len(out) >= C73_MAX_BACKUPS:
            break
        if first and pid == first["ai_provider"]:
            out.append(first)
            continue
        if c73_is_down(pid) or pid not in J.PROVIDERS:
            continue
        try:
            bc = J._ai_cfg({"ai_provider": pid})
        except Exception:
            continue
        if bc.get("key") or J.PROVIDERS[pid].get("no_key"):
            bc["backup"] = True
            out.append(bc)
    if first and first not in out:
        out.insert(0, first)
    return out


def c73_status():
    now = time.time()
    keys = c73_keys()
    cur = J.settings.get("ai_provider", "")
    ch = EN.code_choice(cur, keys, str(J.settings.get("ai_code_provider", "auto") or "auto"))
    return {"actual": J.PROVIDERS.get(cur, {}).get("short", cur),
            "codigo": J.PROVIDERS[ch[0]]["short"] + (f" ({ch[1].split('/')[-1]})" if ch[1] else "") if ch else J.PROVIDERS.get(cur, {}).get("short", cur),
            "descansando": [{"nombre": J.PROVIDERS[p]["short"], "min": int((t - now) / 60) + 1} for p, t in c73["down"].items() if t > now and p in J.PROVIDERS],
            "respaldo": [J.PROVIDERS[p]["short"] for p in EN.backup_chain(cur, keys, "", local=False)][:6]}


__all__ = ["C73_MAX_BACKUPS", "c73", "c73_backups", "c73_is_down", "c73_keys", "c73_mark", "c73_status", "code_pick"]
