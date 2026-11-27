"""12.71: Jarvis más inteligente.

  1. Datos exactos: cuentas, porcentajes, fechas, días hábiles (con festivos de Colombia) y unidades los calcula Jarvis, no
     la IA, y se los pasa como «datos exactos» («¿cuánto es el 19 % de 2.350.000?», «¿cuántos días hábiles faltan para el 15
     de diciembre?», «convierte 5 millas a km»).
  2. Pensar más cuando hace falta: lo difícil («demuestra…», «planea…», «¿qué me conviene…?», «piénsalo bien…») va con el
     pensamiento en nivel alto y, si tu modelo es «lite», con el mejor modelo de tu misma cuenta. Lo simple sigue igual de rápido.
  3. Doble revisión en salud, dinero y leyes: antes de decir la respuesta, una segunda pasada busca datos inventados, normas mal
     citadas o consejos riesgosos; si hay error lo corrige y si algo no se puede asegurar, lo dice.
  4. Mostrar, no solo decir: si explica una función, abre la graficadora; si el tema tiene simulación PhET o escena 3D, te dice
     cómo verla.
  5. Autoexamen semanal (domingo en la tarde): cuántas órdenes entendió a la primera, la prueba de comprensión y las frases que
     fallaron vueltas a probar; propone arreglos y los guarda solo con tu «sí». «¿Cómo me has entendido esta semana?» ·
     «haz el autoexamen».
La lógica pura está en razonar.py. Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import json
import os
import re
import threading
import time
import urllib.parse

import confianza
import festivos
import razonar as RZ
from nucleo import J

c71_brain = {"key": "", "strong": "", "checking": False}
c71_seen = {"visual": {}}
c71_job = {"busy": False}
_c71_lock = threading.Lock()


# ============================================================================ 1. DATOS EXACTOS
def _c71_holidays(year):
    try:
        return festivos.holidays(year)
    except Exception:
        return {}


def c71_facts(prompt):
    if not J.settings.get("smart_tools", True):
        return ""
    try:
        facts = RZ.exact_facts(prompt, datetime.date.today(), festivos.parse_date, _c71_holidays)
    except Exception as e:
        J.log_terminal(f"Datos exactos: {e}", "AVISO")
        return ""
    if facts:
        J.log_terminal("Datos exactos para la IA: " + " | ".join(facts), "RAZONAR")
    return RZ.facts_block(facts)


# ============================================================================ 2. PENSAR MÁS
def c71_strong_model():
    """El mejor modelo de tu cuenta si el principal es «lite» (se busca una vez, en segundo plano). "" = el principal."""
    cfg = J._ai_cfg()
    if cfg["kind"] == "ollama" or cfg.get("offline") or J._is_local_ai(cfg):
        return ""
    key = f"{cfg['ai_provider']}|{cfg['model']}"
    if c71_brain["key"] != key and not c71_brain["checking"]:
        c71_brain["checking"] = True

        def look():
            try:
                c71_brain["strong"] = RZ.strong_model_for(cfg["model"], J.ai_list_models(cfg))
            except Exception:
                c71_brain["strong"] = ""
            c71_brain["key"] = key
            c71_brain["checking"] = False
            if c71_brain["strong"]:
                J.log_terminal(f"Para lo difícil uso {c71_brain['strong']} (pensando a fondo).", "IA")
        threading.Thread(target=look, daemon=True, name="cerebro-fuerte").start()
        return ""
    return c71_brain["strong"] if c71_brain["key"] == key else ""


def c71_prepare(text):
    """Antes de responder: cuánto pensar. → nivel"""
    J._tl.think, J._tl.strong_model = "", ""
    if not J.settings.get("smart_think", True):
        return "normal"
    level = RZ.difficulty(text)
    if level == "dificil":
        J._tl.think = "high"
        J._tl.strong_model = c71_strong_model()
    return level


def c71_clear():
    J._tl.think, J._tl.strong_model = "", ""


# ============================================================================ 3. DOBLE REVISIÓN
def c71_review_topic(text):
    if not J.settings.get("smart_review", True) or getattr(J._tl, "live", False):
        return ""
    return RZ.sensitive(text)


def c71_answer_reviewed(text, topic):
    """Responde sin hablar todavía, revisa y luego dice la versión revisada."""
    ack = J.ack_start(text)
    try:
        kind, *rest = J.ask_ai(text, route=False)
        answer = rest[0] if rest else ""
        if kind != "chat" or not answer or J.state.get("ai") != "ok":
            ack.done()
            J.reply(answer)
            return
        try:
            raw = J.ai_chat([{"role": "system", "content": "Revisas respuestas antes de que un asistente las diga." + confianza.RULE},
                             {"role": "user", "content": RZ.review_prompt(text, answer, topic)}], json_mode=True, max_tokens=2000)
            final, changed = RZ.apply_review(answer, J._extract_json(raw))
        except Exception as e:
            J.log_terminal(f"Revisión de {topic}: no pude revisar ({getattr(e, 'why', e)}); digo la respuesta tal cual.", "RAZONAR")
            final, changed = answer, False
    finally:
        ack.done()
    if changed:
        J.log_terminal(f"Revisé la respuesta de {topic} y la corregí antes de decirla.", "RAZONAR")
        for m in reversed(J.chat_history):
            if m.get("role") == "assistant" and m.get("content") == answer:
                m["content"] = final
                break
        c71_note("corregida")
    J.reply(final)


# ============================================================================ 4. MOSTRAR
def c71_after_answer(question, answer=""):
    if not J.settings.get("smart_visual", True) or getattr(J._tl, "remote", False) or getattr(J._tl, "live", False):
        return None
    if not answer:
        last = next((m for m in reversed(J.chat_history) if m.get("role") == "assistant"), None)
        answer = (last or {}).get("content", "")
    v = RZ.visual_for(question, answer)
    if not v:
        return None
    key = f"{v[0]}:{v[1]}"
    if time.time() - c71_seen["visual"].get(key, 0) < 600:
        return None
    c71_seen["visual"][key] = time.time()
    if v[0] == "grafica":
        J.open_window("/graficadora?" + urllib.parse.urlencode({"f": v[1]}), "Graficadora")
        J.log_terminal(f"Abrí la gráfica de y = {v[1]} para acompañar la explicación.", "RAZONAR")
    elif v[0] == "phet":
        J.reply(f"Si quieres verlo, di «muéstrales la simulación de {J.PH_NAME(v[1])}».", "RAZONAR")
    else:
        J.reply(f"Si quieres verlo en 3D, di «constrúyeme en 3D {('el ' if not v[1].startswith(('la ', 'el ')) else '')}{v[1]}».", "RAZONAR")
    return v


def PH_NAME(slug):
    import phet
    return phet.SIMS[slug][0].lower()


# ============================================================================ 5. AUTOEXAMEN SEMANAL
def _c71_path():
    return os.path.join(J.CONFIG_DIR, "inteligencia.json")


def c71_data():
    try:
        with open(_c71_path(), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d.setdefault("semanas", {})
    d.setdefault("fallos", [])
    d.setdefault("pruebas", [])
    return d


def c71_save(d):
    with _c71_lock:
        os.makedirs(J.CONFIG_DIR, exist_ok=True)
        tmp = _c71_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, _c71_path())


def c71_note(kind, phrase=""):
    """Cuenta lo que pasó con cada orden: total, ia (la entendió la comprensión), aclarar, fallo, corregida."""
    try:
        d = c71_data()
        wk = datetime.date.today().strftime("%G-%V")
        w = d["semanas"].setdefault(wk, {})
        w[kind] = w.get(kind, 0) + 1
        if kind == "fallo" and phrase:
            d["fallos"] = [f for f in d["fallos"] if f["t"] != phrase][-59:] + [{"t": phrase[:200], "f": str(datetime.date.today())}]
        for k in list(d["semanas"])[:-12]:
            d["semanas"].pop(k, None)
        c71_save(d)
    except Exception:
        pass


def c71_week_text(wk=None):
    d = c71_data()
    wk = wk or datetime.date.today().strftime("%G-%V")
    w = d["semanas"].get(wk, {})
    tot = w.get("total", 0)
    if not tot:
        return "", d
    bad = w.get("fallo", 0) + w.get("aclarar", 0)
    pct = round(100 * (tot - bad) / tot)
    txt = (f"Esta semana me diste {tot} órdenes y entendí a la primera el {pct} %" +
           (f"; {w.get('ia', 0)} las entendí traduciendo lo que dijiste" if w.get("ia") else "") +
           (f"; en {w['aclarar']} te pregunté cuál querías" if w.get("aclarar") else "") +
           (f"; {w['fallo']} no las supe hacer" if w.get("fallo") else "") +
           (f". Corregí {w['corregida']} respuestas delicadas antes de decirlas" if w.get("corregida") else "") + ".")
    return txt, d


def c71_exam(n=20):
    """La prueba de comprensión, las frases que fallaron vueltas a probar (sin ejecutar nada) y el informe. → (texto, arreglos)"""
    res = J.nl_test_run(n=n)
    pct = round(100 * (res["bien"] + res["aclaro"]) / res["n"]) if res["n"] else None
    d = c71_data()
    prev = d["pruebas"][-1]["pct"] if d["pruebas"] else None
    if pct is not None:
        d["pruebas"] = (d["pruebas"] + [{"f": str(datetime.date.today()), "pct": pct, "n": res["n"]}])[-26:]
    fixes = []
    week_ago = str(datetime.date.today() - datetime.timedelta(days=8))
    for f in [x for x in d["fallos"] if x["f"] >= week_ago][-10:]:
        try:
            r = J._nl_ask(f["t"])
        except Exception:
            break
        if r.get("tipo") == "orden" and r.get("seguro") and r.get("orden") and J.normalize(r["orden"]) != J.normalize(f["t"]):
            fixes.append((f["t"], r["orden"]))
    c71_save(d)
    week, _d = c71_week_text()
    txt = (week + " " if week else "") + (
        f"En la prueba de comprensión acerté el {pct} %" + (f" (la semana pasada {prev} %)" if prev is not None else "") + "." if pct is not None
        else ("No pude hacer la prueba de comprensión" + (f": {res['corte']}." if res.get("corte") else ".")))
    if fixes:
        txt += f" Volví a probar las frases que fallaron y para {len(fixes)} ya sé qué hacer, por ejemplo «{fixes[0][0]}» → «{fixes[0][1]}»."
    return txt, fixes


def _c71_run_exam(say=True):
    if c71_job["busy"]:
        return
    c71_job["busy"] = True
    try:
        txt, fixes = J.c71_exam()
    except Exception as e:
        J.note_error("AUTOEXAMEN", e)
        return
    finally:
        c71_job["busy"] = False
    J.notify(txt, "AUTOEXAMEN")
    if fixes:
        def save():
            for frase, orden in fixes:
                J.r55_memo_put(J.normalize(frase), orden)
            J.reply(f"Listo, guardé {len(fixes)} arreglos: la próxima vez esas frases van directo.", "AUTOEXAMEN")
        J.request_approval("aprender", f"Guardar {len(fixes)} arreglos de comprensión",
                           "; ".join(f"«{a}» → «{b}»" for a, b in fixes[:6]), on_ok=save,
                           on_no=lambda: J.reply("Vale, no los guardo.", "AUTOEXAMEN"), ttl=86400,
                           say="¿Guardo esos arreglos para entenderte mejor? Di «sí» o «no».")


def listo71_tick(now=None):
    """El domingo desde las 6 de la tarde, una vez por semana."""
    now = now or datetime.datetime.now()
    if not J.settings.get("smart_weekly", True) or now.weekday() != 6 or now.hour < 18:
        return
    wk = now.strftime("%G-%V")
    if J.settings.get("smart_weekly_last") == wk or J.is_offline() or J.state.get("ai") != "ok":
        return
    J.settings["smart_weekly_last"] = wk
    J.save_settings_file()
    threading.Thread(target=_c71_run_exam, daemon=True, name="autoexamen").start()


_C71_WEEK = re.compile(r"^(?:jarvis\s+)?(?:como me has entendido|que tan bien me entendiste|como me entendiste)(?: esta semana)?$")
_C71_EXAM = re.compile(r"^(?:jarvis\s+)?(?:haz|hazte|corre|ejecuta)\s+(?:el\s+|tu\s+)?autoexamen$")


def listo71_voice(text, t):
    if _C71_WEEK.match(t):
        txt, _d = c71_week_text()
        J.reply(txt or "Esta semana todavía no me has dado órdenes que pueda contar.", "AUTOEXAMEN")
        return True
    if _C71_EXAM.match(t):
        if J.state.get("ai") != "ok":
            J.reply("Para el autoexamen necesito la IA conectada.", "AUTOEXAMEN")
            return True
        J.reply("Me pongo a prueba sin ejecutar nada: tarda unos dos minutos. Te aviso.", "AUTOEXAMEN")
        J.start_job("Autoexamen", lambda: _c71_run_exam(), "autoexamen")
        return True
    return False


__all__ = ['PH_NAME', '_C71_EXAM', '_C71_WEEK', '_c71_holidays', '_c71_lock', '_c71_path', '_c71_run_exam', 'c71_after_answer',
           'c71_answer_reviewed', 'c71_brain', 'c71_clear', 'c71_data', 'c71_exam', 'c71_facts', 'c71_job', 'c71_note', 'c71_prepare',
           'c71_review_topic', 'c71_save', 'c71_seen', 'c71_strong_model', 'c71_week_text', 'listo71_tick', 'listo71_voice']
