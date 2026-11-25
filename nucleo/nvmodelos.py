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
        return "Ninguna IA gratis respondió en la prueba. Revisa las claves en Ajustes › Inteligencia artificial."
    best = ok[0]
    txt = f"El más rápido es {best['modelo'].split('/')[-1]} ({best['s']:.1f} s)."
    if len(ok) > 1:
        txt += " Le siguen " + ", ".join(f"{r['modelo'].split('/')[-1]} ({r['s']:.1f} s)" for r in ok[1:4]) + "."
    slow = [r for r in results if not r["ok"]]
    if slow:
        txt += f" {len(slow)} no respondieron a tiempo."
    return txt + " En Ajustes › Inteligencia artificial puedes dejar uno para conversar o para los trabajos pesados."


FREE_PROVIDERS = ("nvidia", "iteracompute", "sensenova")      # 12.48 (12.60: SenseNova): las gratis con varios modelos que vale la pena comparar


def nv_pairs():
    """[(cfg, modelo)] de todas las IA gratis con clave guardada."""
    pairs = []
    for pid in FREE_PROVIDERS:
        if not J.settings.get(f"{pid}_api_key"):
            continue
        cfg = J._ai_cfg({"ai_provider": pid})
        if pid == "nvidia":
            try:
                pairs += [(cfg, m) for m in nv_candidates(J.ai_list_models(cfg))]
            except Exception:
                pairs.append((cfg, cfg["model"]))
        else:
            pairs.append((cfg, cfg["model"] or J.PROVIDERS[pid].get("model", "")))
    return pairs


def nv_bench_run(pause=1.6):
    """Mide cada modelo con la misma pregunta corta. → lista ordenada [{"modelo", "proveedor", "s", "ok", "texto"}]."""
    pairs = nv_pairs()
    if not pairs:
        raise ValueError("no hay claves guardadas de NVIDIA, IteraCompute ni SenseNova")
    res = []
    for i, (cfg, m) in enumerate(pairs):
        nv["msg"] = f"Probando {m.split('/')[-1]} ({i + 1} de {len(pairs)})…"
        J.socketio.emit("nvidia_bench", nv_state())
        t0 = time.time()
        try:
            out = J._cloud_chat(dict(cfg, model=m), [{"role": "user", "content": NV_TEST}], max_tokens=120)
            ok = len(out.strip()) >= 8
        except Exception as e:
            out, ok = f"({getattr(e, 'why', e)})", False
        res.append({"modelo": m, "proveedor": cfg["ai_provider"], "s": round(time.time() - t0, 1), "ok": ok, "texto": out.strip()[:80]})
        if pause and i < len(pairs) - 1:
            time.sleep(pause)                          # límite gratis: unas 40 peticiones por minuto
    return nv_rank(res)


def nv_state():
    prov = J.settings.get("ai_provider", "")
    hp = J.settings.get("ai_heavy_provider", "auto")
    return {"corriendo": nv["running"], "msg": nv["msg"], "resultados": nv["results"], "cuando": nv["at"],
            "conversar": J.settings.get(f"{prov}_model", "") if prov in FREE_PROVIDERS else "",
            "pesados": J.settings.get("ai_heavy_model", "") or (J.settings.get(f"{hp}_model", "") if hp in FREE_PROVIDERS else "")}


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
    J.start_job("Comparando las IA gratis", work, "nvidia-modelos")
    return True


def nv_use(model, para):
    """Deja un modelo de la última prueba para «conversar» (tu IA principal) o para los «pesados». → texto."""
    row = next((r for r in nv["results"] if r["modelo"] == model), None)
    if not row:
        return "Ese modelo no está en la última prueba; pulsa primero «Comparar velocidad»."
    pid = row.get("proveedor") or "nvidia"
    short, plabel = model.split("/")[-1], J.PROVIDERS[pid]["short"]
    if para == "conversar":
        J.settings.update({"ai_provider": pid, f"{pid}_model": model})
        out = f"Listo: ahora converso con {short} de {plabel}."
    else:
        J.settings.update(ai_heavy_provider=pid, ai_heavy_model=model)
        out = f"Listo: los trabajos pesados los hace {short} de {plabel}."
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
        if not any(J.settings.get(f"{p}_api_key") for p in FREE_PROVIDERS):
            return {"ok": False, "msg": "Primero guarda la clave de NVIDIA o de IteraCompute.", **nv_state()}
        started = nv_bench_job()
        return {"ok": True, "msg": "Probando las IA gratis (tarda uno o dos minutos)…" if started else "Ya los estoy probando.",
                **nv_state()}
    if act == "usar":
        return {"ok": True, "msg": nv_use(str(d.get("modelo") or ""), "conversar" if d.get("para") == "conversar" else "pesados"),
                **nv_state()}
    return {"ok": True, **nv_state()}


_NV_VOICE = re.compile(r"\b(?:compara|comparar|prueba|probar|mide|medir)\s+(?:la velocidad de\s+)?(?:los|las)\s+(?:modelos|ias?|inteligencias? artificiales?)"
                       r"\s+(?:de\s+nvidia|gratis|gratuit[oa]s)\b|\bcual (?:modelo|ia) (?:de nvidia|gratis) es (?:el |la )?mas rapid[oa]\b")


def nvidia_bench_voice(text, t):
    if not _NV_VOICE.search(t):
        return False
    J.reply(handle_nvidia_bench({"action": "probar"})["msg"], "IA")
    return True


__all__ = ["FREE_PROVIDERS", "nv_pairs", "NV_PICK", "NV_MAX", "NV_TEST", "nv", "nv_candidates", "nv_rank", "nv_report", "nv_bench_run", "nv_state", "nv_bench_job",
           "nv_use", "handle_nvidia_bench", "_NV_VOICE", "nvidia_bench_voice"]
