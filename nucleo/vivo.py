"""Conversación en vivo, presentaciones y Excel por voz, y cámara/pantalla en vivo.

Parte de Jarvis (antes dentro de jarvis.py). Los nombres globales de Jarvis se usan como J.<nombre>.
"""
from flask import request
import aula
import datetime
import envivo
import importlib.util
import json
import oficina
import os
import re
import skills
import tempfile
import threading
import time

from nucleo import J


# =============================================================================
# CONVERSACIÓN EN VIVO (Gemini Live). Protocolo en envivo.py.
# Tras «Jarvis», el audio del micrófono va directo a Gemini, que lo oye tal cual, sabe solo
# cuándo terminaste, contesta con voz natural y se deja interrumpir. Lo del ambiente (sin
# «Jarvis») sigue sin salir del PC: el reconocimiento local solo busca la palabra.
# =============================================================================
LIVE_URL = envivo.LIVE_URL
LIVE_STATE_PATH = os.path.join(J.CONFIG_DIR, "envivo.json")
_live_lock = threading.Lock()

LIVE_RULE = (
    " Ahora hablas con el usuario por voz, en vivo: respóndele en español de Colombia, natural, cálido y breve "
    "(una o dos frases, salvo que pida más). "
    "Para CUALQUIER acción en su computador (abrir o cerrar programas, volumen, brillo, WhatsApp, música, "
    "temporizadores, alarmas, recordatorios, notas, rutinas, calendario, el tablero del aula, material de clase, "
    "dictado, capturas de pantalla, el videobeam, etc.) llama a la función ejecutar_orden con la orden completa "
    "en español, como la diría el usuario (por ejemplo: «manda un WhatsApp a Andrea Ortiz diciendo que llego "
    "tarde»). Nunca digas que hiciste algo si la función no lo confirma: cuéntale lo que ella responda. Si la "
    "función dice que no es una orden del computador, responde tú. "
    "Si te pide que mires algo (con la cámara o en su pantalla), llama a la función mirar; cuando termine, a "
    "dejar_de_mirar. Nunca leas en voz alta contraseñas ni datos personales que aparezcan en la imagen. "
    "Si lo que oyes no va dirigido a ti (una conversación de fondo, un video, alumnos hablando), no respondas. "
    "Cuando el usuario se despida o diga que eso es todo, despídete en pocas palabras y llama a "
    "terminar_conversacion.")

LIVE_FUNCS = [
    {"name": "ejecutar_orden",
     "description": ("Hace que Jarvis ejecute una orden en el computador del usuario (Windows): abrir o cerrar "
                     "programas, volumen, WhatsApp, temporizadores, recordatorios, notas, rutinas, calendario, "
                     "tablero del aula, material de clase, dictado, etc. Devuelve lo que Jarvis respondió."),
     "parameters": {"type": "OBJECT", "properties": {"orden": {
         "type": "STRING", "description": "La orden completa en español, como la diría el usuario."}},
         "required": ["orden"]}},
    {"name": "terminar_conversacion",
     "description": "Cierra la conversación en vivo cuando el usuario se despide o dice que eso es todo."},
    {"name": "mirar",
     "description": ("Empieza a ver lo que el usuario te quiere mostrar: fuente 'camara' (algo frente a la cámara: "
                     "un cuaderno, un objeto, un experimento, un dibujo) o 'pantalla' (lo que tiene en su "
                     "computador). Úsala cuando diga «mira esto», «¿qué ves?», «mira mi pantalla», «ayúdame con "
                     "esto que tengo abierto». Luego describe o ayuda con lo que veas."),
     "parameters": {"type": "OBJECT", "properties": {"fuente": {
         "type": "STRING", "enum": ["camara", "pantalla"], "description": "camara o pantalla"}},
         "required": ["fuente"]}},
    {"name": "dejar_de_mirar",
     "description": "Deja de ver la cámara o la pantalla (cuando el usuario dice «ya», «deja de mirar», «listo»)."},
]


def _ws_installed():
    try:
        import importlib.util
        return importlib.util.find_spec("websockets") is not None
    except Exception:
        return False


LIVE_PROVIDERS = {"gemini": "Gemini Live", "openai": "OpenAI Realtime", "deepgram": "Deepgram"}
OPENAI_LIVE_URL = envivo.OPENAI_URL
DEEPGRAM_URL = envivo.DEEPGRAM_URL


def _live_key(p):
    if p == "gemini":
        c = J._gemini_for_stt()
        return c["key"] if c else ""
    if p == "openai":
        return J.settings["chatgpt_api_key"].strip()
    if p == "deepgram":
        return J.settings["deepgram_api_key"].strip()
    return ""


def _live_order(include_paused=False):
    """Proveedores a probar, en orden: el elegido y, si falla, los otros que tengan clave."""
    first = J.settings["live_provider"]
    order = [first] + ([p for p in J.LIVE_PROVIDERS if p != first] if J.settings["live_fallback"] else [])
    pause = J.live.setdefault("pause", {})
    return [p for p in order if J._live_key(p) and (include_paused or time.time() >= pause.get(p, 0))]


def live_mode():
    """'vivo' si la conversación en vivo se usará ahora, si no 'clasico' (el motivo queda en live['why'])."""
    if J.settings["listen_mode"] == "clasico":
        return "clasico"
    for cond, why in ((not J._live_order(include_paused=True), "falta la clave del proveedor de voz en vivo"),
                      (not J._ws_installed(), "falta un componente (websockets): ejecuta instalar.bat"),
                      (J.is_offline(), "no hay internet"),
                      (J.dictation_on.is_set(), "estás dictando")):
        if cond:
            J.live["why"] = why
            return "clasico"
    if not J._live_order():                              # todos fallaron hace poco: el motivo ya está en live["why"]
        return "clasico"
    return "vivo"


def _live_load():
    try:
        with open(J.LIVE_STATE_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _live_save(**kw):
    d = J._live_load()
    d.update(kw)
    try:
        with open(J.LIVE_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except OSError:
        pass


def _live_system():
    now = datetime.datetime.now()
    recent = ""
    hist = [m for m in J.chat_history[-8:] if m.get("role") in ("user", "assistant")]
    if hist:
        recent = " Conversación reciente: " + " | ".join(
            f"{'Usuario' if m['role'] == 'user' else 'Tú'}: {str(m['content'])[:200]}" for m in hist) + "."
    return (J.settings["system_prompt"] + J.VOICE_RULE + f" Hoy es {J.fecha_hablada(now.date())}, son las "
            f"{now:%H:%M}." + J._notes_ctx() + J._user_ctx() + recent + J.LIVE_RULE)


def _live_attempts():
    """Combinaciones a probar (modelo, formato, extras). La que funcionó la última vez va primero."""
    voice = J.settings["gemini_tts_voice"]
    system = J._live_system()
    models = [J.settings["live_model"]] + [m for m in envivo.MODELS if m != J.settings["live_model"]]
    combos = [(m, v, full) for m in models for v in ("nested", "flat") for full in (True, False)]
    saved = J._live_load().get("combo")
    if saved:
        saved = (saved[0], saved[1], bool(saved[2]))
        if saved in combos:
            combos.remove(saved)
            combos.insert(0, saved)
    out = []
    for m, v, full in combos:
        tools = [{"functionDeclarations": J.LIVE_FUNCS}]
        if full and J.settings["live_search"]:
            tools.append({"googleSearch": {}})
        setup = envivo.build_setup(m, voice, system, tools, v)
        if full:
            setup["setup"]["proactivity"] = {"proactiveAudio": True}   # puede ignorar lo que no va con él
        out.append((m, f"{v}|{int(full)}", setup))
    return out


def _live_session(p, key, **cb):
    """(sesión, intentos) para el proveedor p."""
    system = J._live_system()
    if p == "openai":
        models = [J.settings["openai_live_model"]] + [m for m in envivo.OPENAI_MODELS if m != J.settings["openai_live_model"]]
        return (envivo.OpenAIRealtime(key, url=J.OPENAI_LIVE_URL, **cb),
                [(m, envivo.openai_session(m, J.settings["openai_live_voice"], system, J.LIVE_FUNCS)) for m in models])
    if p == "deepgram":
        return (envivo.DeepgramAgent(key, url=J.DEEPGRAM_URL, **cb),
                [(f"Deepgram ({J.settings['deepgram_voice']})",
                  envivo.deepgram_settings(J.settings["deepgram_voice"], J.settings["deepgram_think_model"], system, J.LIVE_FUNCS))])
    return envivo.LiveSession(key, url=J.LIVE_URL, **cb), J._live_attempts()


def _live_open(p, cb=None):
    """Abre una sesión con el proveedor p. Devuelve (sesión, modelo) o lanza LiveError."""
    sess, attempts = J._live_session(p, J._live_key(p), **(cb or {}))
    try:
        model, combo = sess.start(attempts)
    except Exception as e:
        raise e if isinstance(e, envivo.LiveError) else envivo.LiveError(str(e))
    if p == "gemini":
        v, full = combo.split("|")
        J._live_save(combo=[model, v, int(full)])
    return sess, model


def live_start(initial_audio=None):
    """Abre la conversación en vivo. False si no se pudo (entonces se usa el modo clásico)."""
    with J._live_lock:
        if J.live["active"] or J.live["connecting"]:
            return True
        if J.live_mode() != "vivo":
            return False
        J.live.update(connecting=True, prebuf=bytearray(initial_audio or b""))
    t0 = time.time()
    cb = dict(on_audio=J._live_on_audio, on_input_text=J._live_on_input, on_output_text=J._live_on_output,
              on_interrupted=J._live_on_interrupted, on_turn_complete=J._live_on_turn_complete,
              on_tool_calls=J._live_tools, on_closed=J._live_on_closed, on_go_away=lambda *_: None,
              on_error=lambda m: J.log_terminal(f"Voz en vivo: {m}", "AVISO"))
    errors, sess, model, used = [], None, "", ""
    for p in J._live_order():
        try:
            sess, model = J._live_open(p, cb)
            used = p
            break
        except envivo.LiveError as e:
            pause = {"key": 1800, "model": 1800, "schema": 1800, "quota": 900}.get(e.kind, 120)
            J.live.setdefault("pause", {})[p] = time.time() + pause
            errors.append(f"{J.LIVE_PROVIDERS[p]}: {e}")
    if sess is None:
        J.live.update(connecting=False, prebuf=bytearray(), why="; ".join(errors) or "sin proveedor")
        J.log_terminal(f"La conversación en vivo no está disponible ({'; '.join(errors)}). "
                     "Mientras tanto uso el modo clásico.", "AVISO")
        return False
    if errors:
        J.log_terminal(f"{'; '.join(errors)}. Uso {J.LIVE_PROVIDERS[used]} como respaldo.", "AVISO")
    if J.live["player"] is None:
        J.live["player"] = envivo.Player()
    with J._live_lock:
        J.live.update(session=sess, active=True, connecting=False, started=time.time(), last=time.time(),
                    in_buf="", out_buf="", ending=False, model=model, why="", turn_audio=False, provider=used)
        pre, J.live["prebuf"] = bytes(J.live["prebuf"]), bytearray()
    for i in range(0, len(pre), 8000):                 # lo que dijiste mientras conectaba
        sess.send_audio(pre[i:i + 8000])
    J.set_state(live=True)
    J.refresh_mode()
    J.log_terminal(f"Conversación en vivo con {model} ({time.time() - t0:.1f} s). Habla con normalidad; "
                 f"termina sola tras {J.settings['live_idle']} s de silencio.", "EN VIVO")
    threading.Thread(target=J._live_watchdog, args=(sess,), daemon=True).start()
    return True


def live_stop(reason="cerrada"):
    s = J.live["session"]
    if s is not None:
        s.close(reason)


def live_feed(data, peak):
    """Cada trozo del micrófono mientras la conversación está abierta (o conectándose)."""
    if J.live["connecting"]:
        if len(J.live["prebuf"]) < 16000 * 2 * 15:
            J.live["prebuf"] += data
        return
    s = J.live["session"]
    if not J.live["active"] or s is None:
        return
    p = J.live["player"]
    echo = (p is not None and p.playing()) or J.tts_playing.is_set()
    if echo and not (J.settings["barge_in"] and peak >= J.settings["live_barge_level"] / 100):
        data = b"\x00" * len(data)                     # su propia voz por los parlantes: no se la manda
    s.send_audio(data)


def _live_on_audio(pcm):
    J.live["last"] = time.time()
    if not J.live["turn_audio"]:
        J.live["turn_audio"] = True
        J._live_flush_user()
    try:
        J.live["player"].write(pcm)
    except Exception as e:
        J.log_terminal(f"No pude reproducir la voz en vivo: {e}", "ERROR")
        J.live_stop("sin salida de audio")
        return
    J.set_state(mode="speaking")


def _live_on_input(text):
    J.live["last"] = time.time()
    J.live["in_buf"] += text
    J.socketio.emit("heard", {"text": J.live["in_buf"].strip()})


def _live_on_output(text):
    J.live["out_buf"] += text


def _live_flush_user():
    said = re.sub(r"\s+", " ", J.live["in_buf"]).strip()
    J.live["in_buf"] = ""
    if said:
        J.log_terminal(f'"{said}"', "VOZ")
        J.push_chat("user", said, "voz")
        J.chat_history.append({"role": "user", "content": said})
    return said


def _live_flush_jarvis(cut=False):
    ans = re.sub(r"\s+", " ", J.live["out_buf"]).strip()
    J.live["out_buf"] = ""
    if ans:
        if cut:
            ans += " (interrumpido)"
        J.log_terminal(ans, "JARVIS")
        J.push_chat("jarvis", ans, "EN VIVO")
        J.chat_history.append({"role": "assistant", "content": ans})
        del J.chat_history[:-40]
    return ans


def _live_on_interrupted():
    if J.live["player"] is not None:
        J.live["player"].clear()
    J._live_flush_jarvis(cut=True)
    J.live["turn_audio"] = False
    J.refresh_mode()


def _live_on_turn_complete():
    J.live["last"] = time.time()
    J._live_flush_user()
    J._live_flush_jarvis()
    J.live["turn_audio"] = False
    J.save_memory()


def _live_on_closed(reason):
    J.live_view_stop()
    with J._live_lock:
        was = J.live["active"]
        J.live.update(active=False, connecting=False, session=None)
    J._live_flush_user()
    J._live_flush_jarvis()
    J.set_state(live=False)
    J.refresh_mode()
    if was:
        J.log_terminal(f"Conversación en vivo terminada ({reason}). Di «Jarvis» para empezar otra.", "EN VIVO")


def _live_watchdog(sess):
    while not sess.closed.is_set():
        time.sleep(0.4)
        p = J.live["player"]
        playing = p is not None and p.playing()
        J.refresh_mode()
        if J.live["ending"] and not playing:
            J.live_stop("te despediste")
        elif not playing and time.time() - J.live["last"] > J.settings["live_idle"]:
            J.live_stop(f"{J.settings['live_idle']} s sin hablar")
        elif time.time() - J.live["started"] > 9 * 60:
            J.live_stop("límite de tiempo de la sesión")


def live_run_order(order):
    """La función ejecutar_orden: corre la orden por el mismo camino que una orden escrita,
    sin voz (la respuesta la dice Gemini) y sin acciones peligrosas."""
    order = re.sub(r"\s+", " ", str(order or "")).strip()[:400]
    if not order:
        return {"error": "La orden llegó vacía."}
    J.pending.update(skill=None, args=None, expires=0)  # nunca confirmar algo peligroso desde aquí
    direct = skills.parse(order)
    sk = skills.REGISTRY.get(direct[0]) if direct else None
    if sk is not None and sk.dangerous:
        J.log_terminal(f"Orden peligrosa pedida en vivo, no ejecutada: {order}", "AVISO")
        return {"error": "Por seguridad, esa acción (apagar, reiniciar, cerrar sesión, vaciar la papelera…) no se "
                         "hace desde la conversación en vivo. Dile al usuario que la escriba en el panel de Jarvis."}
    J.log_terminal(f"Orden: {order}", "EN VIVO")
    J._tl.capture, J._tl.live, J._tl.no_order = [], True, False
    try:
        J.process_command(order)
        said, no_order = list(J._tl.capture), J._tl.no_order
    except Exception as e:
        return {"error": f"Falló: {e}"}
    finally:
        J._tl.capture, J._tl.live, J._tl.no_order = None, False, False
    if no_order and not said:
        return {"result": "Eso no es una orden del computador: respóndela tú."}
    return {"result": " ".join(said) or "Hecho."}


def _live_tools(calls):
    out = []
    for c in calls:
        name, args = c.get("name"), c.get("args") or {}
        J.live["last"] = time.time()
        if name == "terminar_conversacion":
            J.live["ending"] = True
            res = {"result": "La conversación se cerrará al terminar de hablar."}
        elif name == "ejecutar_orden":
            res = J.live_run_order(args.get("orden", ""))
        elif name == "mirar":
            res = J.live_view_start(str(args.get("fuente") or "camara"))
        elif name == "dejar_de_mirar":
            J.live_view_stop()
            res = {"result": "Ya no estás viendo."}
        else:
            res = {"error": f"Función desconocida: {name}"}
        out.append({"id": c.get("id"), "name": name, "response": res})
    return out


_BEEP = {"path": None}


def _beep_path():
    """Un «tin» corto para avisar que ya te escucha (en vivo no se dice «¿Sí?»)."""
    if J._BEEP["path"] and os.path.exists(J._BEEP["path"]):
        return J._BEEP["path"]
    import math
    import wave
    path = os.path.join(tempfile.gettempdir(), "jarvis_escucha.wav")
    rate, n = 22050, int(22050 * 0.16)
    frames = bytearray()
    for i in range(n):
        env = min(1.0, i / 300) * min(1.0, (n - i) / 900)
        v = int(9000 * env * (math.sin(2 * math.pi * 880 * i / rate) + 0.4 * math.sin(2 * math.pi * 1320 * i / rate)))
        frames += int(max(-32767, min(32767, v))).to_bytes(2, "little", signed=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    J._BEEP["path"] = path
    return path


def live_test():
    """Botón «Probar» de Ajustes: abre y cierra una sesión con cada proveedor que tenga clave."""
    if J.live["active"]:
        return {"ok": True, "msg": f"Ya hay una conversación en vivo abierta con {J.live['model']}."}
    if not J._ws_installed():
        return {"ok": False, "msg": "Falta un componente (websockets). Ejecuta instalar.bat o actualiza Jarvis."}
    J.live["pause"] = {}
    J.live["why"] = ""
    provs = J._live_order()
    if not provs:
        return {"ok": False, "msg": "No hay clave para ningún proveedor de voz en vivo (Gemini en Ajustes › IA)."}
    lines, ok_any = [], False
    for p in provs:
        t0 = time.time()
        try:
            sess, model = J._live_open(p)
            sess.close("prueba")
            lines.append(f"✓ {J.LIVE_PROVIDERS[p]}: conectado con {model} en {time.time() - t0:.1f} s")
            ok_any = True
        except envivo.LiveError as e:
            lines.append(f"✗ {J.LIVE_PROVIDERS[p]}: {e}")
    return {"ok": ok_any, "msg": "  ·  ".join(lines)}


# =============================================================================
# PRESENTACIONES Y HOJAS DE EXCEL POR VOZ (lógica en oficina.py)
# =============================================================================
office_job = {"busy": False}


def notify(text, origin="JARVIS"):
    """Avisa algo que terminó en segundo plano. Si hay una conversación en vivo abierta, se lo
    pasa a la IA de voz para que lo diga ella (así no hablan dos voces a la vez). Si la orden
    vino del celular (Telegram) hace poco, también se lo cuenta allá."""
    if J.settings["telegram_remote"] and time.time() - J.tg["last_cmd"] < 900:
        threading.Thread(target=J.telegram_send, args=(text,), daemon=True).start()
    s = J.live.get("session")
    if J.live.get("active") and s is not None:
        J.log_terminal(text, origin)
        J.push_chat("jarvis", text, origin)
        try:
            s.send_text(f"[Aviso de Jarvis para que se lo digas al usuario en una frase: {text}]")
            return
        except Exception:
            pass
    J.reply(text, origin)


def _open_doc(path):
    J.generated_files.add(path)
    if J.IS_WIN and J.settings["aula_open_docs"]:
        try:
            os.startfile(path)
            return True
        except OSError:
            pass
    return False


def _course_in(t):
    """El curso nombrado en la frase («de 7A»), o el activo del tablero."""
    for c in sorted(aula.data["cursos"], key=len, reverse=True):
        if re.search(rf"\b{re.escape(J.normalize(c))}\b", t):
            return c, aula.data["cursos"][c]
    return aula.active()


def _periodo_in(t):
    m = re.search(r"\b(?:periodo|bimestre|trimestre)\s+(\d|uno|dos|tres|cuatro)\b"
                  r"|\b(primer|segundo|tercer|cuarto)\s+(?:periodo|bimestre|trimestre)\b", t)
    if not m:
        return ""
    w = m.group(1) or m.group(2)
    n = {"uno": 1, "primer": 1, "dos": 2, "segundo": 2, "tres": 3, "tercer": 3, "cuatro": 4, "cuarto": 4}.get(w, w)
    return f"Periodo {n}"


def _office_ai_json(prompt, validate, request, max_tokens=8000):
    m, last = None, None
    for _ in range(2):                                 # un reintento si la IA devuelve algo mal formado
        try:
            raw = J.ai_chat([{"role": "user", "content": prompt}], json_mode=True, max_tokens=max_tokens)
            return validate(J._extract_json(raw), request)
        except (ValueError, TypeError) as e:
            last = e
    raise ValueError(str(last) or "respuesta no válida")


def office_voice(text, t):
    """«haz una presentación sobre…», «crea la planilla de notas de 7A», «crea una tabla en Excel de…»."""
    found = oficina.detect(text)
    if not found:
        return False
    kind, d = found
    if kind == "notas":
        try:
            course, names = J._course_in(t)
        except ValueError as e:
            J.reply(str(e), "AULA")
            return True
        try:
            path = oficina.build_grades_xlsx(course, names, d["count"], J.settings["output_dir"],
                                             J.settings["aula_docente"], J.settings["aula_institucion"], J._periodo_in(t))
        except ImportError:
            J.reply("Para crear hojas de Excel falta un componente (openpyxl). Actualiza Jarvis o ejecuta instalar.bat.", "ERROR")
            return True
        opened = J._open_doc(path)
        J.log_terminal(f"Planilla guardada en: {path}", "AULA")
        J.reply(f"Listo, la planilla de notas de {course}: {len(names)} estudiantes y {d['count']} notas, con promedio "
              "y desempeño automáticos. La guardé en Documentos, Jarvis, Planillas" + (" y la abrí." if opened else "."), "AULA")
        return True
    if J.office_job["busy"]:
        J.reply("Ya estoy preparando otro documento. Cuando termine, hago este.", "AULA")
        return True
    what = "la presentación" if kind == "pptx" else "la tabla"
    J.office_job["busy"] = True
    J.reply(f"Preparando {what}. Te aviso cuando esté lista; suele tardar menos de un minuto.", "AULA")

    def work():
        try:
            if kind == "pptx":
                m = J._office_ai_json(oficina.pptx_prompt(d["request"], d["count"], d["grade"]),
                                    oficina.pptx_validate, d["request"])
                path = oficina.build_pptx(m, J.settings["output_dir"], J.settings["aula_docente"],
                                          J.settings["aula_institucion"], d["grade"])
                n = len(m["diapositivas"])
                msg = (f"Lista la presentación «{m['titulo']}»: {n} diapositivas, con notas para ti debajo de cada una. "
                       "La guardé en la carpeta Material de clase")
            else:
                m = J._office_ai_json(oficina.table_prompt(d["request"]), oficina.table_validate, d["request"])
                path = oficina.build_table_xlsx(m, J.settings["output_dir"])
                msg = f"Lista la tabla «{m['titulo']}» con {len(m['filas'])} filas. La guardé en Documentos, Jarvis, Planillas"
            opened = J._open_doc(path)
            J.log_terminal(f"Guardado en: {path}", "AULA")
            J.notify(msg + (" y la abrí." if opened else "."), "AULA")
        except ImportError:
            J.notify("Para crear presentaciones y hojas de Excel falta un componente. Actualiza Jarvis o ejecuta instalar.bat.", "ERROR")
        except J.AIError as e:
            J.notify(J.ai_error_reply(e), "AULA")
        except Exception as e:
            J.log_terminal(f"Documento: {e}", "ERROR")
            J.notify(f"No me salió bien {what}. Inténtalo otra vez, quizá con un tema más concreto.", "AULA")
        finally:
            J.office_job["busy"] = False
    J.start_job("Creando el documento", work, "oficina")
    return True


# =============================================================================
# JARVIS VE EN VIVO: cámara o pantalla dentro de la conversación en vivo
# =============================================================================
live_view = {"src": None, "until": 0.0, "cap": None, "stop": threading.Event(), "sensitive": False}
LIVE_VIEW_MAX = 180                                    # segundos como máximo por cada «mira»


def _jpeg_from_bgr(frame, max_w=1024):
    import cv2
    h, w = frame.shape[:2]
    if w > max_w:
        frame = cv2.resize(frame, (max_w, int(h * max_w / w)))
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
    if not ok:
        raise ValueError("no pude codificar la imagen")
    return buf.tobytes()


def _live_camera_frame():
    import cv2
    cap = J.live_view["cap"]
    if cap is None:
        idx = J.settings["camera_index"]
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW) if J.IS_WIN else cv2.VideoCapture(idx)
        if not cap.isOpened():
            cap.release()
            raise ValueError("No pude abrir la cámara: revisa que no la use otra aplicación (Teams, Zoom…) y "
                             "que Windows le dé permiso en Configuración › Privacidad › Cámara.")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        J.live_view["cap"] = cap
        t0 = time.time()
        while time.time() - t0 < 0.8:                  # que ajuste luz y foco
            cap.read()
    frame = None
    for _ in range(3):
        ok, f = cap.read()
        if ok:
            frame = f
    if frame is None:
        raise ValueError("La cámara no entregó imagen.")
    return J._jpeg_from_bgr(frame)


def _live_screen_frame():
    """JPEG de la pantalla, o None si la ventana activa es privada (no se captura)."""
    if skills.pyautogui is None:
        raise ValueError("Para ver la pantalla falta la librería pyautogui.")
    title = J._foreground_title()
    if title and J.SENSITIVE_TITLES.search(title):
        return None
    import io
    img = skills.pyautogui.screenshot()
    if img.width > 1280:
        img = img.resize((1280, round(img.height * 1280 / img.width)))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=70)
    return buf.getvalue()


def _live_frame(src):
    return J._live_camera_frame() if src == "camara" else J._live_screen_frame()


def live_view_stop(reason=""):
    J.live_view["stop"].set()
    J.live_view["src"] = None
    cap, J.live_view["cap"] = J.live_view["cap"], None
    if cap is not None:
        try:
            cap.release()
        except Exception:
            pass
    J.set_state(viewing="")


def live_view_start(src):
    """Lo llama la IA de voz (función «mirar»). Devuelve el resultado para ella."""
    src = "camara" if src in ("camara", "cámara", "camera") else "pantalla"
    s = J.live.get("session")
    if not J.live.get("active") or s is None:
        return {"error": "No hay conversación en vivo."}
    if not hasattr(s, "send_image") or J.live.get("provider") == "deepgram":
        return {"error": "Con este proveedor de voz no puedo ver imágenes. Funciona con Gemini Live u OpenAI Realtime."}
    J.live_view_stop()
    try:
        frame = J._live_frame(src)
    except ImportError:
        return {"error": "Para usar la cámara falta un componente (opencv). Ejecuta instalar.bat."}
    except ValueError as e:
        return {"error": str(e)}
    if frame is None:
        return {"error": "La ventana activa parece privada (contraseñas, banco o pagos): no la voy a mirar. "
                         "Dile al usuario que cambie a otra ventana."}
    if not s.send_image(frame):
        return {"error": "No pude enviar la imagen."}
    J.live_view.update(src=src, until=time.time() + J.LIVE_VIEW_MAX, sensitive=False)
    J.live_view["stop"] = threading.Event()
    J.set_state(viewing=src)
    que = "la cámara" if src == "camara" else "la pantalla"
    J.log_terminal(f"Mirando {que} (máximo {J.LIVE_VIEW_MAX // 60} minutos; di «deja de mirar» para parar).", "EN VIVO")
    if J.live.get("provider") == "gemini":                # Gemini Live recibe video: 1 imagen por segundo
        threading.Thread(target=J._live_view_loop, args=(s, src, J.live_view["stop"]), daemon=True).start()
        return {"result": f"Ya estás viendo {que} en vivo (una imagen por segundo). Describe o ayuda con lo que veas."}
    return {"result": f"Te envié una imagen de {que}. Si el usuario cambia algo, vuelve a llamar a mirar."}


def _live_view_loop(sess, src, stop):
    while not stop.wait(1.0):
        if sess.closed.is_set() or time.time() > J.live_view["until"]:
            break
        try:
            frame = J._live_frame(src)
        except Exception as e:
            J.log_terminal(f"Visión en vivo: {e}", "AVISO")
            break
        if frame is None:                              # cambió a una ventana privada: no se envía
            if not J.live_view["sensitive"]:
                J.live_view["sensitive"] = True
                J.log_terminal("Ventana privada en pantalla: dejo de enviar imágenes mientras esté abierta.", "EN VIVO")
            continue
        J.live_view["sensitive"] = False
        sess.send_image(frame)
    if J.live_view["stop"] is stop:
        J.live_view_stop()


__all__ = [
    'DEEPGRAM_URL',
    'LIVE_FUNCS',
    'LIVE_PROVIDERS',
    'LIVE_RULE',
    'LIVE_STATE_PATH',
    'LIVE_URL',
    'LIVE_VIEW_MAX',
    'OPENAI_LIVE_URL',
    '_BEEP',
    '_beep_path',
    '_course_in',
    '_jpeg_from_bgr',
    '_live_attempts',
    '_live_camera_frame',
    '_live_flush_jarvis',
    '_live_flush_user',
    '_live_frame',
    '_live_key',
    '_live_load',
    '_live_lock',
    '_live_on_audio',
    '_live_on_closed',
    '_live_on_input',
    '_live_on_interrupted',
    '_live_on_output',
    '_live_on_turn_complete',
    '_live_open',
    '_live_order',
    '_live_save',
    '_live_screen_frame',
    '_live_session',
    '_live_system',
    '_live_tools',
    '_live_view_loop',
    '_live_watchdog',
    '_office_ai_json',
    '_open_doc',
    '_periodo_in',
    '_ws_installed',
    'live_feed',
    'live_mode',
    'live_run_order',
    'live_start',
    'live_stop',
    'live_test',
    'live_view',
    'live_view_start',
    'live_view_stop',
    'notify',
    'office_job',
    'office_voice',
]
