"""12.32: cuánto se usa la IA, los datos de estudiantes protegidos y el consejo de modelos.

  · Consumo: cada llamada a la IA suma (por día, por modelo y por proyecto): llamadas, palabras aproximadas que van y
    vuelven (en «tokens», unas 4 letras cada uno) y cuántas veces respondió «saturado» o «sin cuota». «¿Cuánto he usado
    la IA hoy?». Si pones un tope de llamadas al día (ai_daily_limit), te avisa al 80 %.
  · Privacidad: si un texto que va a la nube trae nombres de tus estudiantes (de las listas de tus cursos), los cambia
    por «Estudiante 1», «Estudiante 2»… antes de enviarlo y los vuelve a poner en la respuesta. Si prefieres, con
    privacy_local_first lo responde la IA de tu equipo (si la tienes) y no sale nada.
  · Consejo de modelos: «pregúntale al consejo: ¿me conviene comprar o arrendar?». La misma pregunta a varios modelos
    por separado (los que tengas: Gemini, su modelo rápido, Claude, OpenAI, la IA local…) y luego uno resume en qué
    coinciden, en qué no y qué recomendaría.
"""
import datetime
import json
import os
import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor

import aula
from nucleo import J

# ============================================================================ CONSUMO
_use = {"days": {}, "dirty": False, "t": 0.0, "warned": ""}
_use_lock = threading.Lock()


def _use_path():
    return os.path.join(J.CONFIG_DIR, "consumo_ia.json")


def _use_load():
    if _use["t"]:
        return
    _use["t"] = time.time()
    try:
        with open(_use_path(), encoding="utf-8") as f:
            _use["days"] = json.load(f).get("days", {})
    except (OSError, ValueError):
        _use["days"] = {}


_flush_lock = threading.Lock()


def usage_flush():
    with _flush_lock:                                     # (en Windows, dos escrituras a la vez se pisan el archivo)
        _usage_flush()


def _usage_flush():
    if not _use["dirty"]:
        return
    try:
        os.makedirs(J.CONFIG_DIR, exist_ok=True)
        keep = dict(sorted(_use["days"].items())[-60:])          # dos meses
        with open(_use_path() + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"days": keep}, f, ensure_ascii=False)
        os.replace(_use_path() + ".tmp", _use_path())
        _use["dirty"] = False
    except OSError:
        pass


def _toks(x):
    if isinstance(x, list):
        return sum(_toks(m.get("content") if isinstance(m, dict) else m) for m in x)
    return max(0, len(str(x or "")) // 4)


def usage_add(cfg, messages, out="", ok=True, kind=""):
    """Suma una llamada (la cuenta de tokens es aproximada: unas 4 letras por token)."""
    _use_load()
    day = datetime.date.today().isoformat()
    model = f"{cfg.get('label') or cfg.get('ai_provider')} · {cfg.get('model') or ''}".strip(" ·")
    tin, tout = _toks(messages), _toks(out)
    with _use_lock:
        d = _use["days"].setdefault(day, {"calls": 0, "in": 0, "out": 0, "errors": 0, "quota": 0, "models": {}})
        d["calls"] += 1
        d["in"] += tin
        d["out"] += tout
        if not ok:
            d["errors"] += 1
            if kind in ("quota", "server"):
                d["quota"] += 1
        m = d["models"].setdefault(model, {"calls": 0, "tok": 0})
        m["calls"] += 1
        m["tok"] += tin + tout
        _use["dirty"] = True
    st = getattr(J._tl, "project_st", None)                   # el proyecto que está trabajando en este hilo
    if st is not None:
        c = st.setdefault("consumo", {"calls": 0, "tok": 0})
        c["calls"] += 1
        c["tok"] += tin + tout
    if time.time() - _use.get("ft", 0) > 20:
        _use["ft"] = time.time()
        threading.Thread(target=usage_flush, daemon=True).start()
    _usage_warn(day)


def _usage_warn(day):
    lim = int(J.settings.get("ai_daily_limit") or 0)
    d = _use["days"].get(day) or {}
    if lim and d.get("calls", 0) >= 0.8 * lim and _use["warned"] != day:
        _use["warned"] = day
        J.notify(f"Ojo: hoy llevo {d['calls']} llamadas a la IA de las {lim} que pusiste como tope. Lo grande (proyectos, "
                 "pruebas) mejor mañana, o súbele el tope en Ajustes.", "CONSUMO")


def usage_today(day=None):
    _use_load()
    return dict(_use["days"].get(day or datetime.date.today().isoformat()) or {"calls": 0, "in": 0, "out": 0, "errors": 0, "quota": 0, "models": {}})


def _k(n):
    return f"{n / 1000:.1f} mil".replace(".0 mil", " mil") if n >= 1000 else str(n)


def usage_spoken(day=None):
    d = usage_today(day)
    if not d["calls"]:
        return "Hoy todavía no he usado la IA."
    top = sorted(d["models"].items(), key=lambda kv: -kv[1]["calls"])[:3]
    txt = (f"Hoy van {d['calls']} llamadas a la IA, unos {_k(d['in'] + d['out'])} tokens (aproximado): "
           + "; ".join(f"{m}: {v['calls']}" for m, v in top) + ".")
    if d["quota"]:
        txt += f" {d['quota']} vez{'es' if d['quota'] != 1 else ''} respondió «saturado» o «sin cuota»."
    lim = int(J.settings.get("ai_daily_limit") or 0)
    if lim:
        txt += f" Tu tope es {lim} al día ({round(100 * d['calls'] / lim)} %)."
    return txt


_USE_RE = re.compile(r"\bcuant[oa]s?\s+(?:he usado|llevo|van|gaste|he gastado|uso|usaste|consumi|has usado|has gastado|llamadas)\b.{0,30}\b(?:ia|inteligencia artificial|gemini|cuota|tokens?)\b|"
                     r"\b(?:consumo|uso|gasto) de (?:la )?(?:ia|inteligencia artificial|gemini|cuota)\b|\bcomo voy con la cuota\b")


def usage_voice(text, t):
    if not _USE_RE.search(t):
        return False
    J.reply(usage_spoken(), "CONSUMO")
    return True


# ============================================================================ PRIVACIDAD
def _plain(s):
    s = unicodedata.normalize("NFD", str(s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


_names_cache = {"key": None, "rx": None, "names": []}


def _student_names():
    """Los nombres de tus listas (completos y «Nombre Apellido»), de más largo a más corto."""
    allc = aula.data.get("cursos") or {}
    key = tuple((c, len(v)) for c, v in sorted(allc.items()))
    if _names_cache["key"] == key:
        return _names_cache["names"], _names_cache["rx"]
    names = set()
    for v in allc.values():
        for n in v or []:
            w = str(n).split()
            if len(w) >= 2:
                names.add(" ".join(w))
                names.add(" ".join(w[:2]))
                if len(w) >= 3:
                    names.add(f"{w[0]} {w[2]}")         # Nombre + primer apellido cuando hay dos nombres
    names = sorted(names, key=len, reverse=True)
    rx = re.compile(r"(?<!\w)(" + "|".join(re.escape(_plain(n)).replace(r"\ ", r"\s+") for n in names) + r")(?!\w)") if names else None
    _names_cache.update(key=key, rx=rx, names=names)
    return names, rx


def privacy_names_in(text):
    _n, rx = _student_names()
    return bool(rx and rx.search(_plain(text)))


def _scrub_text(text, mp):
    _n, rx = _student_names()
    if not rx:
        return text
    plain = _plain(text)
    out, last = [], 0
    for m in rx.finditer(plain):                        # mismas posiciones: _plain no cambia la longitud del texto
        orig = text[m.start():m.end()]
        key = re.sub(r"\s+", " ", m.group(1))
        tag = mp["by"].get(key)
        if not tag:
            tag = f"Estudiante {len(mp['by']) + 1}"
            mp["by"][key] = tag
            mp["back"][tag] = re.sub(r"\s+", " ", orig)
        out.append(text[last:m.start()] + tag)
        last = m.end()
    return "".join(out) + text[last:]


def privacy_scrub(messages):
    """→ (mensajes con los nombres cambiados, mapa para devolverlos). Mapa vacío si no había nombres."""
    mp = {"by": {}, "back": {}}
    if not J.settings.get("privacy_students", True):
        return messages, mp
    names, rx = _student_names()
    if not rx:
        return messages, mp
    out = []
    for m in messages:
        c = m.get("content") if isinstance(m, dict) else None
        if isinstance(c, str) and len(_plain(c)) == len(c):
            out.append(dict(m, content=_scrub_text(c, mp)))
        else:
            out.append(m)
    return out, mp


def privacy_restore(text, mp):
    if not mp or not mp["back"] or not isinstance(text, str):
        return text
    for tag in sorted(mp["back"], key=lambda x: -len(x)):  # «Estudiante 12» antes que «Estudiante 1»
        text = re.sub(rf"\b{re.escape(tag)}\b", mp["back"][tag], text)
    return text


def privacy_local_cfg():
    """La IA de tu equipo, si la tienes y escogiste que los datos de estudiantes no salgan. → cfg o None."""
    if not J.settings.get("privacy_local_first", False):
        return None
    try:
        name = J.net.get("local_model") or J.local_pick()
    except Exception:
        name = ""
    if not name:
        return None
    if str(name).startswith("motor:"):
        return dict(J._ai_cfg({"ai_provider": "motor"}), label="Jarvis local (datos de estudiantes)")
    return dict(J._ai_cfg({"ai_provider": "ollama", "ollama_model": name}), label="Ollama (datos de estudiantes)")


# ============================================================================ CONSEJO DE MODELOS
COUNCIL_MAX = 4


def council_members():
    """Los modelos que pueden opinar: el principal, su rápido, los otros proveedores con clave y la IA local."""
    out, seen = [], set()
    main = J._ai_cfg()

    def add(cfg, label):
        k = (cfg.get("ai_provider"), cfg.get("model"))
        if cfg.get("model") and k not in seen and len(out) < COUNCIL_MAX:
            seen.add(k)
            out.append(dict(cfg, label=label))
    if main["kind"] != "ollama":
        add(main, f"{main['label']} ({main['model']})")
        fm = J.fast_model()
        if fm and fm != main["model"]:
            add(dict(main, model=fm), f"{main['label']} ({fm})")
    for pid, sp in J.PROVIDERS.items():
        if pid in ("ollama", "motor") or pid == main.get("ai_provider") or sp.get("custom"):
            continue
        if str(J.settings.get(f"{pid}_api_key", "")).strip() and str(J.settings.get(f"{pid}_model", "")).strip():
            c = J._ai_cfg({"ai_provider": pid})
            add(c, f"{c['label']} ({c['model']})")
    try:
        loc = J.net.get("local_model") or J.local_pick()
    except Exception:
        loc = ""
    if loc and not str(loc).startswith("motor:"):
        c = J._ai_cfg({"ai_provider": "ollama", "ollama_model": loc})
        add(c, f"IA local ({loc})")
    return out


def _council_one(cfg, q):
    msgs = [{"role": "system", "content": "Responde en español de Colombia, en 4 a 8 frases, con tu recomendación clara y sus razones. "
                                          "Si depende de algo, di de qué."},
            {"role": "user", "content": q}]
    if cfg["kind"] == "ollama":
        J.ollama_ensure(cfg["ollama_host"])
        r = J._ollama_chat(cfg, model=cfg["model"], messages=msgs, options={"num_predict": 500}, keep_alive=J._keep_alive())
        out = J.motorlocal.clean_reply(r["message"]["content"] or "")
    else:
        m2, mp = privacy_scrub(msgs)
        out = privacy_restore(J._cloud_chat(cfg, m2, max_tokens=900), mp)
    usage_add(cfg, msgs, out)
    return out.strip()


def council_prompt(q, answers):
    parts = "\n\n".join(f"[{name}]\n{a}" for name, a in answers)
    return (f"Varios modelos de IA respondieron por separado, sin ver a los otros, esta pregunta: «{q}»\n\n{parts}\n\n"
            "Haz la síntesis para la persona, en español claro y sin markdown: 1) en qué coinciden, 2) en qué difieren y por qué "
            "importa, 3) qué recomendarías tú con todo eso y de qué depende. Máximo 10 frases.")


def council_run(q):
    members = council_members()
    if len(members) < 2:
        return None, ("Para el consejo necesito al menos dos modelos: el modelo rápido de tu cuenta, otra IA con su clave "
                      "(Claude, OpenAI…) o la IA local. Hoy solo tengo uno.")
    answers = []
    with ThreadPoolExecutor(max_workers=len(members)) as ex:
        futs = [(m["label"], ex.submit(_council_one, m, q)) for m in members]
        for label, f in futs:
            try:
                a = f.result(timeout=180)
                if a:
                    answers.append((label, a))
            except Exception as e:
                J.log_terminal(f"Consejo: {label} no respondió ({getattr(e, 'why', e)}).", "AVISO")
    if len(answers) < 2:
        return answers, "Solo me respondió " + (answers[0][0] if answers else "ningún modelo") + "; el consejo necesita al menos dos."
    try:
        synth = J.ai_chat([{"role": "user", "content": council_prompt(q, answers)}], max_tokens=1200).strip()
    except Exception as e:
        synth = f"(No pude hacer la síntesis: {getattr(e, 'why', e)}.)"
    return answers, synth


_COUNCIL = re.compile(r"^(?:jarvis[ ,]+)?(?:preguntale al|pregunta al|consulta al|consultale al|que dice el|que opina el|"
                      r"llama al|reune al|reúne al)\s+consejo(?:\s+de\s+(?:modelos|ias?|inteligencias))?\s*[:,]?\s*(.*)$|"
                      r"^(?:jarvis[ ,]+)?consejo de (?:modelos|ias?)\s*[:,]\s*(.+)$")


def council_voice(text, t):
    m = _COUNCIL.match(t)
    if not m:
        return False
    if J.state.get("ai") != "ok":
        J.reply("Para el consejo de modelos necesito la IA conectada.", "CONSEJO")
        return True
    raw = re.split(r"[:,]\s*", text, maxsplit=1)
    q = raw[1].strip() if len(raw) == 2 and len(raw[1].strip()) > 5 else (m.group(1) or m.group(2) or "").strip()
    if len(q) < 6:
        J.reply("¿Qué le pregunto al consejo? Por ejemplo: «pregúntale al consejo: ¿me conviene comprar o arrendar?».", "CONSEJO")
        return True
    n = len(council_members())
    J.reply(f"Le pregunto a {n} modelos por separado y te traigo en qué coinciden…" if n >= 2 else
            "Reviso qué modelos tengo para el consejo…", "CONSEJO")

    def work():
        answers, synth = council_run(q)
        if answers is None or len(answers or []) < 2:
            J.reply(synth, "CONSEJO")
            return
        J.show("Consejo de modelos — «" + q + "»\n\n" + "\n\n".join(f"**{name}:** {a}" for name, a in answers)
               + "\n\n**Síntesis:** " + synth, "CONSEJO")
        J.speak(synth)
    J.start_job("Consejo de modelos", work, "consejo")
    return True


__all__ = ['COUNCIL_MAX', '_flush_lock', '_usage_flush', '_COUNCIL', '_USE_RE', '_council_one', '_names_cache', '_scrub_text', '_student_names', '_toks', '_use',
           '_use_load', '_use_lock', '_use_path', '_usage_warn', 'council_members', 'council_prompt', 'council_run', 'council_voice',
           'privacy_local_cfg', 'privacy_names_in', 'privacy_restore', 'privacy_scrub', 'usage_add', 'usage_flush', 'usage_spoken',
           'usage_today', 'usage_voice']
