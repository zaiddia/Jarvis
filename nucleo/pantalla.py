"""Visión de pantalla y copiloto.

Parte de Jarvis (antes dentro de jarvis.py). Los nombres globales de Jarvis se usan como J.<nombre>.
"""
from collections import deque
import json
import os
import re
import skills
import tempfile
import threading
import time
import uuid

from nucleo import J


# =============================================================================
# VISIÓN DE PANTALLA Y COPILOTO
#   · A demanda: «¿qué hay en la pantalla?» (describe) o «ayúdame con esto» (sugerencias).
#   · Copiloto: cada pocos minutos mira la pantalla y, SOLO si tiene algo útil, sugiere.
#   Nunca captura ventanas sensibles (contraseñas, bancos, pagos, navegación privada).
# =============================================================================
SENSITIVE_TITLES = re.compile(
    r"contrase|password|clave|iniciar sesi|inicio de sesi|sign.?in|log.?in|banco|bank|bancolombia|"
    r"davivienda|nequi|daviplata|paypal|pago|payment|checkout|tarjeta|inprivate|incognito|"
    r"privad[ao]|bitwarden|1password|keepass|lastpass", re.I)
copilot = {"last_run": 0.0, "thumb": None, "recent": deque(maxlen=6), "skipped_sensitive": 0.0}


def _foreground_title():
    """Título de la última ventana que usaste (no la de Jarvis)."""
    if not J.IS_WIN:
        return ""
    try:
        h = skills._last_ext.get("hwnd") or skills.user32.GetForegroundWindow()
        return skills._title_of(h) or ""
    except Exception:
        return ""


def _idle_seconds():
    """Segundos desde la última vez que tocaste teclado o ratón."""
    if not J.IS_WIN:
        return 0.0
    try:
        import ctypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
        li = LASTINPUTINFO()
        li.cbSize = ctypes.sizeof(li)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(li)):
            return (ctypes.windll.kernel32.GetTickCount() - li.dwTime) / 1000.0
    except Exception:
        pass
    return 0.0


def _capture_screen(hide_hud=True, max_w=1280):
    """Captura la pantalla reducida (más rápida y gasta menos cuota). Devuelve (ruta, imagen)."""
    path = os.path.join(tempfile.gettempdir(), f"jarvis_vista_{uuid.uuid4().hex}.png")
    if hide_hud:
        J._temp_hide(True)
        time.sleep(0.35)
    try:
        img = skills.pyautogui.screenshot()
    finally:
        if hide_hud:
            J._temp_hide(False)
    if img.width > max_w:
        img = img.resize((max_w, round(img.height * max_w / img.width)))
    img.save(path, optimize=True)
    return path, img


def _vision_cfg():
    """Proveedor que puede ver imágenes: el elegido si puede; si no, Gemini con tu clave."""
    cfg = J._ai_cfg()
    if cfg["kind"] == "ollama":
        if J.ollama is None:
            return None, "Para la visión con Ollama falta la librería 'ollama'."
        return cfg, None
    if cfg["spec"].get("vision") and cfg["key"]:
        return cfg, None
    g = J._gemini_for_stt()
    if g:
        return g, None
    return None, (f"Con {cfg['label']} no puedo ver la pantalla. Funciona con Gemini, Claude, ChatGPT "
                  "u Ollama con un modelo de visión; o guarda una clave de Gemini en Ajustes, sección IA.")


def _vision_chunks(cfg, prompt, path, history=()):
    """Fragmentos de la respuesta del modelo de visión, a medida que se generan."""
    msgs = [*history, {"role": "user", "content": prompt}]
    if cfg["kind"] != "ollama":
        J._need_key(cfg)
        return J._with_fallback(cfg, lambda c: J._cloud_stream(c, msgs, image_path=path))
    vmodel = J.settings["vision_model"].strip() or "moondream"

    def oll():
        st = J.ollama.Client(host=cfg["ollama_host"], timeout=180).chat(
            model=vmodel, stream=True, keep_alive="30m",
            messages=[*history, {"role": "user", "content": prompt, "images": [path]}],
            options={"num_predict": 260})
        for part in st:
            c = (part.get("message") or {}).get("content", "")
            if c:
                yield c
    return oll()


def _work_context():
    title = J._foreground_title()
    ctx = f" La ventana activa es «{title}»." if title else ""
    if J.settings["copilot_context"].strip():
        ctx += f" Sobre su trabajo, el usuario te contó: {J.settings['copilot_context'].strip()}"
    return title, ctx


def screen_assist(pregunta="", mode="describe"):
    """mode='describe': qué hay en pantalla. mode='help': sugerencias para lo que estás haciendo."""
    if skills.pyautogui is None:
        J.reply("Para ver la pantalla necesito la librería pyautogui.", "VISION")
        return
    cfg, err = J._vision_cfg()
    if not cfg:
        J.reply(err, "VISION")
        return
    title, ctx = J._work_context()
    if title and J.SENSITIVE_TITLES.search(title):
        J.reply("Esa ventana parece privada (contraseñas, banco o pagos), así que no la voy a capturar.", "VISION")
        return
    path, _ = J._capture_screen(hide_hud=True)
    if mode == "help":
        prompt = ("Eres Jarvis, el asistente personal del usuario. Mira esta captura de su pantalla." + ctx +
                  " En una frase di qué está haciendo, y luego dale dos o tres sugerencias concretas y "
                  "útiles para esa tarea: errores que veas, algo que falte, una forma más rápida de "
                  "hacerlo o el siguiente paso. Responde en español hablado y breve, como una "
                  "conversación: sin listas, sin markdown, máximo cinco frases.")
        if pregunta.strip():
            prompt += f" Lo que te pidió exactamente: «{pregunta.strip()}»."
    else:
        prompt = ("Describe en español, de forma breve y clara, lo que se ve en esta captura de "
                  "pantalla de un computador. Si hay texto importante, menciónalo.")
        if pregunta.strip():
            prompt += f" En concreto: {pregunta.strip()}"
    J.thinking += 1
    J.refresh_mode()
    full, buf = "", ""
    try:
        for chunk in J._vision_chunks(cfg, prompt, path):
            full += chunk
            buf += chunk
            m = J._SENT_END.search(buf)
            while m:
                sent = buf[:m.end()].strip()
                buf = buf[m.end():]
                if len(sent) > 1:
                    J.speak(J._clean_for_speech(sent))
                m = J._SENT_END.search(buf)
    except Exception as e:
        msg = str(e)
        vmodel = J.settings["vision_model"].strip() or "moondream"
        if cfg["kind"] == "ollama" and ("not found" in msg.lower() or "pull" in msg.lower()):
            J.reply(f"No tengo el modelo de visión «{vmodel}». En una terminal ejecuta: ollama pull {vmodel}.", "VISION")
        else:
            J.log_terminal(f"Error de visión: {e}", "ERROR")
            J.reply(J.ai_error_reply(e) if isinstance(e, J.AIError) else "No pude analizar la pantalla.", "VISION")
        return
    finally:
        J.thinking -= 1
        J.refresh_mode()
        try:
            os.remove(path)
        except OSError:
            pass
    if buf.strip():
        J.speak(J._clean_for_speech(buf))
    full = full.strip() or "No distinguí nada claro en la pantalla."
    J.log_terminal(full, "VISION")
    J.push_chat("jarvis", full, "VISION")
    # Se recuerda lo que vio: así puedes seguir preguntando («¿y cómo hago eso?»).
    keep = J.settings["history_turns"] * 2
    pedido = pregunta.strip() or ("ayúdame con lo que tengo en pantalla" if mode == "help" else "¿qué hay en la pantalla?")
    J.chat_history.extend([{"role": "user", "content": f"{pedido} (le mostré a Jarvis mi pantalla{': ' + title if title else ''})"},
                         {"role": "assistant", "content": full}])
    del J.chat_history[:-max(keep, 2)]
    J.save_memory()


def describe_screen(pregunta=""):
    J.screen_assist(pregunta, "describe")


def _screen_changed(img):
    """Compara una miniatura en grises con la anterior: si la pantalla casi no cambió, no
    tiene sentido gastar una consulta."""
    small = list(img.convert("L").resize((48, 27)).getdata())
    prev, J.copilot["thumb"] = J.copilot["thumb"], small
    if prev is None:
        return True
    diff = sum(abs(a - b) for a, b in zip(small, prev)) / len(small)
    return diff >= 3.0


def copilot_tick(force=False):
    """Una pasada del copiloto. Devuelve la sugerencia, o None si no había nada útil."""
    cfg, err = J._vision_cfg()
    if not cfg or skills.pyautogui is None:
        return None
    title, ctx = J._work_context()
    if title and J.SENSITIVE_TITLES.search(title):
        if time.time() - J.copilot["skipped_sensitive"] > 600:
            J.log_terminal("Copiloto en pausa: la ventana activa parece privada.", "COPILOTO")
            J.copilot["skipped_sensitive"] = time.time()
        return None
    path, img = J._capture_screen(hide_hud=False)            # sin parpadeos del HUD
    try:
        if not force and not J._screen_changed(img):
            return None
        anteriores = " | ".join(J.copilot["recent"]) or "ninguna"
        prompt = ("Eres el copiloto de Jarvis y observas la pantalla del usuario mientras trabaja." + ctx +
                  " Ignora el pequeño panel de Jarvis. Si ves algo concreto en lo que puedas ayudar ahora "
                  "mismo (un error, algo que falta, una forma más rápida de hacerlo o un dato útil para su "
                  "tarea), responde con UNA sola sugerencia breve, de máximo dos frases, en español, "
                  "dirigida al usuario. Si no hay nada realmente útil, responde exactamente: NADA. "
                  f"No describas la pantalla. No repitas estas sugerencias anteriores: {anteriores}.")
        text = "".join(J._vision_chunks(cfg, prompt, path)).strip()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    clean = text.strip().strip('"«»').strip()
    if not clean or re.match(r"^\W*nada\b", clean, re.I):
        return None
    J.copilot["recent"].append(clean[:160])
    J.log_terminal(clean, "COPILOTO")
    J.push_chat("jarvis", "💡 " + clean, "COPILOTO")
    J.socketio.emit("copilot_tip", {"text": clean})
    J.chat_history.append({"role": "assistant", "content": f"(Sugerencia del copiloto mirando tu pantalla) {clean}"})
    J.save_memory()
    if J.settings["copilot_speak"]:
        J.speak(J._clean_for_speech(clean))
    return clean


def _copilot_worker():
    while True:
        time.sleep(10)
        if not J.settings["copilot_enabled"]:
            continue
        if time.time() - J.copilot["last_run"] < J.settings["copilot_interval"] * 60:
            continue
        # Solo mientras trabajas: no si estás ausente, dictando o si Jarvis está hablando/pensando.
        if J.dictation_on.is_set() or J.tts_playing.is_set() or J.thinking or J._idle_seconds() > 120:
            continue
        if J.is_offline() and J._vision_cfg()[0] and J._vision_cfg()[0]["kind"] != "ollama":
            continue                                       # sin internet: el copiloto espera
        J.copilot["last_run"] = time.time()
        try:
            J.copilot_tick()
        except J.AIError as e:
            J.log_terminal(f"Copiloto: {e.why}", "AVISO")
        except Exception as e:
            J.log_terminal(f"Copiloto: {e}", "AVISO")


def set_copilot(on, interval=None):
    changes = {"copilot_enabled": bool(on)}
    if interval:
        changes["copilot_interval"] = interval
    errs = J.apply_settings(changes)
    if on:
        J.copilot.update(thumb=None, last_run=time.time() - J.settings["copilot_interval"] * 60 + 20)
    return errs


def _key(*keys):
    """Pulsa una tecla o combinación en la ventana activa (si hay pyautogui)."""
    if skills.pyautogui is None:
        return
    if len(keys) == 1:
        skills.pyautogui.press(keys[0])
    else:
        skills.pyautogui.hotkey(*keys)


def dictation_control(t, text):
    """Comandos para operar controles de formularios HTML por voz durante el dictado.
    Devuelve True si manejó el comando. t = texto normalizado, text = texto original."""
    # Moverse entre campos y controles
    if re.fullmatch(r"(?:siguiente campo|tabulador|tab|siguiente control|pasa al siguiente|siguiente)", t):
        J._key("tab"); return True
    if re.fullmatch(r"(?:campo anterior|control anterior|regresa el campo|anterior)", t):
        J._key("shift", "tab"); return True

    # Casillas de verificación y botones de opción -> barra espaciadora
    if re.fullmatch(r"(?:marca(?:r)?|activa(?:r)?|selecciona(?:r)?|desmarca(?:r)?|quita(?:r)? la marca|pulsa (?:la )?barra|espacio|marca (?:la |esta )?casilla|activa (?:la |esta )?casilla)"
                    r"(?: (?:la |esta )?(?:casilla|opcion|opción))?", t):
        J._key("space"); return True

    # Listas desplegables (<select>)
    if re.fullmatch(r"(?:abre(?:r)? (?:la )?lista|despliega(?:r)?|abre(?:r)? (?:el )?menu|muestra (?:las )?opciones|despliega el menu)", t):
        J._key("alt", "down"); return True
    if re.fullmatch(r"(?:cierra (?:la )?lista|cierra (?:el )?menu|escape|cancela(?:r)?)", t):
        J._key("esc"); return True

    # Flechas (botones de opción, listas, deslizadores)
    if re.fullmatch(r"(?:abajo|baja|siguiente opcion|siguiente opción|bajar)", t):
        J._key("down"); return True
    if re.fullmatch(r"(?:arriba|sube|opcion anterior|opción anterior|subir)", t):
        J._key("up"); return True
    if re.fullmatch(r"(?:derecha|a la derecha|aumenta(?:r)?)", t):
        J._key("right"); return True
    if re.fullmatch(r"(?:izquierda|a la izquierda|disminuye(?:r)?|reduce)", t):
        J._key("left"); return True
    if re.fullmatch(r"(?:primero|al principio|inicio)", t):
        J._key("home"); return True
    if re.fullmatch(r"(?:ultimo|ultima|al final|final)", t):
        J._key("end"); return True

    # Elegir una opción por su texto: «elige Grado once», «selecciona azul»
    m = re.match(r"^\s*(?:elige|escoge|selecciona|opcion|opción|pon)\s+(.+)$", text, re.I)
    if m and skills.pyautogui is not None:
        valor = m.group(1).strip(" .,:")
        if skills.pyperclip:                      # pegar es más fiable con tildes y espacios
            try:
                old = skills.pyperclip.paste()
            except Exception:
                old = None
            skills.pyperclip.copy(valor)
            skills.pyautogui.hotkey("ctrl", "v")
            if old is not None:
                threading.Timer(0.6, lambda: skills.pyperclip.copy(old)).start()
        else:
            skills.pyautogui.write(valor, interval=0.02)
        J.log_terminal(f"Opción: {valor}", "DICTADO")
        return True

    # Enviar / aceptar
    if re.fullmatch(r"(?:enviar(?: (?:el )?formulario)?|acepta(?:r)?|confirma(?:r)?)", t):
        J._key("enter"); return True

    # Borrar
    if re.fullmatch(r"(?:borra(?:r)? (?:el )?campo|limpia(?:r)? (?:el )?campo)", t):
        J._key("ctrl", "a"); J._key("delete"); return True
    if re.fullmatch(r"(?:borra(?:r)?|borrar lo ultimo|retrocede)", t):
        if skills.pyautogui:
            skills.pyautogui.press("backspace", presses=12)
        return True
    return False


def handle_dictation(text):
    t = J.normalize(text)
    if re.search(J.DICTATION_STOP_RE, t):
        J._set_dictation(False)
        J.reply("Dictado finalizado.", "PC")
        return
    if re.fullmatch(r"(?:activa(?:r)?|modo|empieza) (?:el )?(?:modo )?matematic[ao]s?", t):
        J.dictation_math.set()
        J.reply("Modo matemático activado: diré los números y símbolos como fórmula.", "PC")
        return
    if re.fullmatch(r"(?:desactiva(?:r)?|quita|modo) (?:el )?(?:modo )?(?:matematic[ao]s?|normal|texto)", t):
        J.dictation_math.clear()
        J.reply("Dictado de texto normal.", "PC")
        return
    if re.fullmatch(r"(?:nueva linea|salto de linea|nuevo renglon|enter)", t):
        J._key("enter")
        return
    # Navegación de formularios HTML por voz (incluye controles especiales)
    if J.dictation_control(t, text):
        return
    try:
        out = skills.transcribe_math(text) if J.dictation_math.is_set() else text
        skills.dictation_type(out)
        J.log_terminal(f"Dictado: {out}", "DICTADO")
    except skills.SkillError as e:
        J.reply(str(e), "PC")
    except Exception as e:
        J.log_terminal(f"Error de dictado: {e}", "ERROR")


# Desde el celular no se ve qué hay abierto ni quién está delante del equipo: además de las acciones
# delicadas (apagar, reiniciar…), no se cierran programas ni se escribe en ventanas, ni se crean rutinas.
REMOTE_BLOCKED = {
    "cerrar_app": "Desde el celular no cierro programas: podría perderse trabajo sin guardar.",
    "escribir": "Desde el celular no escribo en la ventana del equipo: no sé qué hay abierto.",
    "crear_rutina": "Las rutinas se crean desde el equipo: podrían lanzar órdenes sin nadie delante.",
    "instalar_actualizacion": "Las actualizaciones se instalan desde el equipo: me reinicio y desde aquí no verías si algo falla.",
}
_REMOTE_DELETE_RE = re.compile(r"\b(?:borra|borrar|elimina|eliminar|olvida|olvidate|vacia|vaciar|limpia|tacha|restaura|restaurar)\b.*"
                               r"\b(?:nota|notas|memoria|pendientes|rutina|rutinas|historial|conversacion|todo|curso|cursos|"
                               r"asistencia|copia|copias|respaldo|lista|listas)\b")


def remote_blocked(name, args=None):
    """El motivo si esta acción no se hace desde el celular; None si se puede."""
    sk = skills.REGISTRY.get(name)
    if sk is not None and sk.dangerous:
        return "Por seguridad, eso (apagar, reiniciar, cerrar sesión, borrar…) no lo hago desde el celular."
    if name == "ventana" and J.normalize((args or {}).get("accion", "")).startswith("cerr"):
        return J.REMOTE_BLOCKED["cerrar_app"]
    return J.REMOTE_BLOCKED.get(name)


def run_skill(name, args, confirmed=False):
    sk = skills.REGISTRY.get(name)
    if not sk:
        return False
    if getattr(J._tl, "remote", False):
        why = J.remote_blocked(name, args)
        if why:
            J.log_terminal(f"Desde el celular no: {name} {json.dumps(args or {}, ensure_ascii=False)}", "AVISO")
            J.reply(why + " Hazlo en el equipo o pídemelo de viva voz.", "TELEGRAM")
            return True
    if sk.dangerous and not confirmed:
        J.pending.update(skill=name, args=args, expires=time.time() + 25)
        J.reply(sk.confirm_text(args) + " Di «confirmar» o «cancelar».", "PC")
        return True
    J.log_terminal(f"Acción: {name} {json.dumps(args, ensure_ascii=False)}", "PC")
    J.learn_note(name, args)                         # 7.4: aprende tus costumbres
    J._run_skill_guarded(name, sk, args)
    return True


def _deliver_skill(name, args, box):
    if "err" in box:
        e = box["err"]
        if getattr(e, "need", None):
            J.followup.update(skill=name, args=dict(args or {}), need=e.need,
                            expires=time.time() + 45)
        J.reply(str(e), "PC")
    elif "exc" in box:
        J.log_terminal(f"Fallo en la habilidad {name}: {box['exc']}", "ERROR")
        J.reply("No pude completar esa acción.", "PC")
    else:
        J.reply(box.get("out") or "Hecho.", "PC")


def _run_skill_guarded(name, sk, args):
    """Ejecuta la acción en su propio hilo. Si se cuelga (una ventana que no responde,
    una web que no carga...), Jarvis no se queda bloqueado: sigue con las demás órdenes
    y da el resultado cuando llegue."""
    box, lock, state = {}, threading.Lock(), {"done": False, "late": False}

    def work():
        try:
            box["out"] = sk.run(args)
        except skills.SkillError as e:
            box["err"] = e
        except Exception as e:
            box["exc"] = e
        with lock:
            state["done"] = True
            late = state["late"]
        if late:
            J._deliver_skill(name, args, box)

    t = threading.Thread(target=work, daemon=True, name=f"skill-{name}")
    t.start()
    t.join(J.SKILL_TIMEOUT)
    with lock:
        if not state["done"]:
            state["late"] = True
    if state["late"]:
        J.log_terminal(f"La acción {name} tarda más de {J.SKILL_TIMEOUT} s; sigo atendiendo.", "AVISO")
        J.reply("Eso está tardando más de lo normal. Te aviso cuando termine.", "PC")
    else:
        J._deliver_skill(name, args, box)


__all__ = [
    'REMOTE_BLOCKED',
    'SENSITIVE_TITLES',
    '_REMOTE_DELETE_RE',
    '_capture_screen',
    '_copilot_worker',
    '_deliver_skill',
    '_foreground_title',
    '_idle_seconds',
    '_key',
    '_run_skill_guarded',
    '_screen_changed',
    '_vision_cfg',
    '_vision_chunks',
    '_work_context',
    'copilot',
    'copilot_tick',
    'describe_screen',
    'dictation_control',
    'handle_dictation',
    'remote_blocked',
    'run_skill',
    'screen_assist',
    'set_copilot',
]
