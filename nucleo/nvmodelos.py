"""12.47: los modelos gratis de NVIDIA Build con tu misma clave (Kimi, Qwen y otros). Jarvis los prueba en tu PC y te dice
cuál responde más rápido; con un toque lo dejas para conversar o para los trabajos pesados.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import re
import threading
import time

from nucleo import J

NV_PICK = (r"kimi", r"qwen", r"glm", r"deepseek", r"nemotron", r"llama", r"mistral|magistral", r"gemma", r"minimax", r"step")
NV_MAX = 9
NV_TEST = "Responde en una sola frase corta y en español: ¿qué es una fracción?"
nv = {"running": False, "results": [], "at": 0.0, "msg": ""}
_nv_lock = threading.Lock()


def nv_candidates(models, limit=NV_MAX):
    """Los modelos de tu cuenta que vale la pena medir: Kimi y Qwen primero, después otras familias de chat (uno o dos de cada)."""
    out = []
    for pat in NV_PICK:
        fam = [m for m in models if re.search(pat, m, re.I) and m not in out]
        fam.sort(key=lambda m: (bool(re.search(r"coder|math|guard|safety|reward|embed|vl\b|vision", m, re.I)), len(m)))
        out += fam[:3 if pat in ("kimi", "qwen") else 1]
    return out[:limit]


def nv_rank(results):
    """Primero los que respondieron, del más rápido al más lento."""
    return sorted(results, key=lambda r: (not r["ok"], r["s"]))


def nv_report(results):
    ok = [r for r in results if r["ok"]]
    if not ok:
        return "Ningún modelo de NVIDIA respondió en la prueba. Revisa la clave en Ajustes › Inteligencia artificial."
    best = ok[0]
    txt = f"El más rápido de NVIDIA es {best['modelo'].split('/')[-1]} ({best['s']:.1f} s)."
    if len(ok) > 1:
        txt += " Le siguen " + ", ".join(f"{r['modelo'].split('/')[-1]} ({r['s']:.1f} s)" for r in ok[1:4]) + "."
    slow = [r for r in results if not r["ok"]]
    if slow:
        txt += f" {len(slow)} no respondieron a tiempo."
    return txt + " En Ajustes › Inteligencia artificial puedes dejar uno para conversar o para los trabajos pesados."


def nv_bench_run(pause=1.6):
    """Mide cada modelo con la misma pregunta corta. → lista ordenada [{"modelo", "s", "ok", "texto"}]."""
    cfg = J._ai_cfg({"ai_provider": "nvidia"})
    J._need_key(cfg)
    cands = nv_candidates(J.ai_list_models(cfg))
    res = []
    for i, m in enumerate(cands):
        nv["msg"] = f"Probando {m.split('/')[-1]} ({i + 1} de {len(cands)})…"
        J.socketio.emit("nvidia_bench", nv_state())
        t0 = time.time()
        try:
            out = J._cloud_chat(dict(cfg, model=m), [{"role": "user", "content": NV_TEST}], max_tokens=120)
            ok = len(out.strip()) >= 8
        except Exception as e:
            out, ok = f"({getattr(e, 'why', e)})", False
        res.append({"modelo": m, "s": round(time.time() - t0, 1), "ok": ok, "texto": out.strip()[:80]})
        if pause and i < len(cands) - 1:
            time.sleep(pause)                          # límite gratis: unas 40 peticiones por minuto
    return nv_rank(res)


def nv_state():
    return {"corriendo": nv["running"], "msg": nv["msg"], "resultados": nv["results"], "cuando": nv["at"],
            "conversar": J.settings.get("nvidia_model", "") if J.settings.get("ai_provider") == "nvidia" else "",
            "pesados": J.settings.get("ai_heavy_model", "") or (J.settings.get("nvidia_model", "")
                                                               if J.settings.get("ai_heavy_provider") in ("auto", "nvidia") else "")}


def nv_bench_job():
    with _nv_lock:
        if nv["running"]:
            return False
        nv["running"] = True

    def work():
        try:
            nv["results"] = nv_bench_run()
            nv["at"] = time.time()
            msg = nv_report(nv["results"])
        except Exception as e:
            msg = f"No pude probar los modelos de NVIDIA: {str(getattr(e, 'why', e))[:160]}"
        finally:
            nv["running"], nv["msg"] = False, ""
        J.notify(msg, "IA")
        J.socketio.emit("nvidia_bench", nv_state())
    J.start_job("Comparando los modelos de NVIDIA", work, "nvidia-modelos")
    return True


def nv_use(model, para):
    """Deja un modelo de la última prueba para «conversar» (tu IA principal) o para los «pesados». → texto."""
    if model not in {r["modelo"] for r in nv["results"]}:
        return "Ese modelo no está en la última prueba; pulsa primero «Comparar velocidad»."
    short = model.split("/")[-1]
    if para == "conversar":
        J.settings.update(ai_provider="nvidia", nvidia_model=model)
        out = f"Listo: ahora converso con {short} de NVIDIA."
    else:
        J.settings.update(ai_heavy_provider="nvidia", ai_heavy_model=model)
        out = f"Listo: los trabajos pesados los hace {short} de NVIDIA."
    try:
        J.save_settings_file()
    except OSError:
        pass
    try:
        J.check_ai()
    except Exception:
        pass
    J.socketio.emit("settings_updated", J.public_settings())
    return out


@J.socketio.on("nvidia_bench")
def handle_nvidia_bench(data=None):
    d = data or {}
    act = str(d.get("action") or "")
    if act == "probar":
        if not J.settings.get("nvidia_api_key"):
            return {"ok": False, "msg": "Primero guarda la clave de NVIDIA.", **nv_state()}
        started = nv_bench_job()
        return {"ok": True, "msg": "Probando los modelos de NVIDIA (tarda uno o dos minutos)…" if started else "Ya los estoy probando.",
                **nv_state()}
    if act == "usar":
        return {"ok": True, "msg": nv_use(str(d.get("modelo") or ""), "conversar" if d.get("para") == "conversar" else "pesados"),
                **nv_state()}
    return {"ok": True, **nv_state()}


_NV_VOICE = re.compile(r"\b(?:compara|comparar|prueba|probar|mide|medir)\s+(?:la velocidad de\s+)?(?:los|las)\s+(?:modelos|ias|inteligencias artificiales)"
                       r"\s+de\s+nvidia\b|\bcual (?:modelo|ia) de nvidia es (?:el |la )?mas rapid[oa]\b")


def nvidia_bench_voice(text, t):
    if not _NV_VOICE.search(t):
        return False
    J.reply(handle_nvidia_bench({"action": "probar"})["msg"], "IA")
    return True


__all__ = ["NV_PICK", "NV_MAX", "NV_TEST", "nv", "nv_candidates", "nv_rank", "nv_report", "nv_bench_run", "nv_state", "nv_bench_job",
           "nv_use", "handle_nvidia_bench", "_NV_VOICE", "nvidia_bench_voice"]
