"""Aplicar ajustes y rutas/eventos web del HUD y de Ajustes.

Parte de Jarvis (antes dentro de jarvis.py). Los nombres globales de Jarvis se usan como J.<nombre>.
"""
from flask import abort
from flask import render_template
from flask import request
from flask_socketio import emit
import actualizar
import aula
import calendario
import correo
import datetime
import diario
import envivo
import notas
import os
import perfil
import re
import respaldo
import rutinas
import skills
import threading
import recuerdos
import time
import uuid
import webbrowser

from nucleo import J


# =============================================================================
# AJUSTES: APLICAR CAMBIOS
# =============================================================================
def apply_settings(data):
    errors = []
    data = dict(data or {})

    if "autostart" in data:
        want = bool(data.pop("autostart"))
        if want != J.autostart_enabled():
            try:
                J.set_autostart(want)
            except Exception as e:
                errors.append(f"Autoinicio: {e}")

    for k in J.SECRET_FIELDS:                      # campo vacío = conservar la clave guardada
        if data.pop(f"{k}_clear", False):
            data[k] = ""
        elif not str(data.get(k) or "").strip():
            data.pop(k, None)

    changed = set()
    with J.settings_lock:
        for k, v in data.items():
            if k not in J.DEFAULT_SETTINGS or k in ("hud_x", "hud_y"):
                continue
            try:
                nv = J._validate(k, v)
            except Exception as e:
                errors.append(f"{k}: {e}")
                continue
            if J.settings[k] != nv:
                J.settings[k] = nv
                changed.add(k)
        if changed:
            try:
                J.save_settings_file()
            except Exception as e:
                errors.append(f"No se pudo guardar config.json: {e}")

    if changed & {"mic_enabled", "mic_device", "wake_word_enabled", "wake_words",
                  "stt_backend", "whisper_model"}:
        J.mic_restart.set()
    if changed & {"morning_enabled", "morning_time"}:
        J.reschedule()
    if "tts_enabled" in changed and J.audio_ready:
        J.set_state(tts="ok" if J.settings["tts_enabled"] else "off")
        if not J.settings["tts_enabled"]:
            J.stop_speech()
    if "calendar_urls" in changed:
        threading.Thread(target=J.cal_refresh, kwargs={"force": True}, daemon=True).start()
    if changed & {"copilot_enabled", "copilot_interval"}:
        J.set_state(copilot=J.settings["copilot_enabled"])
        if "copilot_enabled" in changed:
            J.log_terminal("Copiloto " + (f"activado: miraré tu pantalla cada {J.settings['copilot_interval']} min."
                                        if J.settings["copilot_enabled"] else "desactivado."), "COPILOTO")
    if changed & J.AI_SETTING_KEYS:
        J.chat_history.clear()
        threading.Thread(target=J.check_ai, args=(True,), daemon=True).start()
    if "hud_on_top" in changed and J.hud["window"] is not None:
        J.hud["window"].on_top = J.settings["hud_on_top"]
    if "hud_position" in changed:
        J.hud_reposition()
    if changed & {"diary_enabled", "diary_days"}:
        diario.configure(J.CONFIG_DIR, J.settings["diary_enabled"], J.settings["diary_days"])
    if "mcp_servers" in changed:
        J.mcp_reconfigure()
    if "mcp_server_enabled" in changed:
        J.mcp_server_apply()
    if changed & {"history_enabled", "history_days"}:
        recuerdos.configure(J.CONFIG_DIR, J.settings["history_enabled"], J.settings["history_days"])
    if "windows_integration" in changed:
        threading.Thread(target=J.windows_apply, daemon=True).start()
    if changed & {"mobile_enabled", "mobile_port"}:
        if J.settings["mobile_enabled"] and not J.settings["mobile_token"]:
            J.settings["mobile_token"] = uuid.uuid4().hex[:24]
            J.save_settings_file()
        threading.Thread(target=J.mobile_apply, daemon=True).start()
    if changed:
        J.log_terminal(f"Ajustes guardados ({len(changed)} cambios).", "SISTEMA")
    return errors


# =============================================================================
# RUTAS Y EVENTOS WEB
# =============================================================================
@J.app.route("/")
def index():
    return render_template("hud.html", version=J.VERSION)


@J.socketio.on("calendar_test")
def handle_calendar_test(data):
    urls = calendario.clean_urls((data or {}).get("calendar_urls") or J.settings["calendar_urls"])
    if not urls:
        return {"ok": False, "error": "Pega primero el enlace iCal de tu calendario."}
    try:
        evs, errs = calendario.fetch(urls)
    except ImportError:
        return {"ok": False, "error": "Falta un componente para leer calendarios: ejecuta instalar.bat otra vez."}
    nx = calendario.upcoming(limit=1, events=evs)
    hoy = calendario.on_day(datetime.date.today(), evs)
    return {"ok": not errs or bool(evs), "errors": errs, "count": len(evs), "today": len(hoy),
            "next": J._event_line(nx[0]) if nx else ""}


@J.socketio.on("rutinas_get")
def handle_rutinas_get(data=None):
    return {"rutinas": rutinas.routines}


@J.socketio.on("rutinas_save")
def handle_rutinas_save(data):
    d = data or {}
    try:
        rutinas.upsert(d.get("nombre"), d.get("frases"), d.get("pasos"), d.get("old"), d.get("cuando", ""))
    except ValueError as e:
        return {"ok": False, "error": str(e), "rutinas": rutinas.routines}
    return {"ok": True, "rutinas": rutinas.routines}


@J.socketio.on("rutinas_delete")
def handle_rutinas_delete(data):
    rutinas.delete((data or {}).get("nombre", ""))
    return {"ok": True, "rutinas": rutinas.routines}


@J.socketio.on("rutinas_defaults")
def handle_rutinas_defaults(data=None):
    rutinas.restore_defaults()
    return {"ok": True, "rutinas": rutinas.routines}


@J.socketio.on("rutinas_run")
def handle_rutinas_run(data):
    r = next((x for x in rutinas.routines if x["nombre"] == (data or {}).get("nombre")), None)
    if not r:
        return {"ok": False, "error": "No encontré esa rutina."}
    J.run_routine(r)
    return {"ok": True}


@J.socketio.on("notes_get")
def handle_notes_get(data=None):
    return {"notes": J.notes_snapshot()}


@J.socketio.on("notes_add")
def handle_notes_add(data):
    try:
        notas.add((data or {}).get("texto", ""))
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    J._notes_changed()
    return {"ok": True, "notes": J.notes_snapshot()}


@J.socketio.on("notes_done")
def handle_notes_done(data):
    d = data or {}
    notas.set_done(str(d.get("id")), bool(d.get("done", True)))
    J._notes_changed()
    return {"ok": True, "notes": J.notes_snapshot()}


@J.socketio.on("notes_delete")
def handle_notes_delete(data):
    notas.delete(str((data or {}).get("id")))
    J._notes_changed()
    return {"ok": True, "notes": J.notes_snapshot()}


@J.socketio.on("notes_clear_done")
def handle_notes_clear_done(data=None):
    notas.clear_done()
    J._notes_changed()
    return {"ok": True, "notes": J.notes_snapshot()}


@J.app.route("/aula")
def aula_page():
    return render_template("aula.html", version=J.VERSION)


def _aula_state():
    return {"ok": True, **aula.snapshot(), "view": J.aula_ui["view"], "last": J.aula_ui["last"],
            "docente": J.settings["aula_docente"], "institucion": J.settings["aula_institucion"],
            "open_docs": J.settings["aula_open_docs"], "auto_open": J.settings["aula_auto_open"],
            "theme": J.settings["theme"], "busy": J.material_job["busy"], "mic": J.state.get("mic"),
            "native": J.hud.get("aula_win") is not None, "camera_index": J.settings["camera_index"],
            "review_busy": J.review_state["busy"]}


def _aula_call(fn, *a, **k):
    try:
        fn(*a, **k)
        return J._aula_state()
    except ValueError as e:
        return {"ok": False, "error": str(e), **J._aula_state(), "ok": False}


@J.socketio.on("aula_get")
def handle_aula_get(data=None):
    return J._aula_state()


@J.socketio.on("aula_save_course")
def handle_aula_save_course(data):
    d = data or {}
    return J._aula_call(aula.save_course, d.get("name"), d.get("text"), d.get("old"))


@J.socketio.on("aula_delete_course")
def handle_aula_delete_course(data):
    return J._aula_call(aula.delete_course, (data or {}).get("name"))


@J.socketio.on("aula_set_active")
def handle_aula_set_active(data):
    return J._aula_call(aula.set_active, (data or {}).get("name"))


@J.socketio.on("aula_pick")
def handle_aula_pick(data=None):
    return J._aula_call(J.aula_pick)


@J.socketio.on("aula_reset_pick")
def handle_aula_reset_pick(data=None):
    return J._aula_call(aula.reset_pick)


@J.socketio.on("aula_groups")
def handle_aula_groups(data):
    d = data or {}
    size, count = aula.to_int(str(d.get("size") or "")), aula.to_int(str(d.get("count") or ""))
    return J._aula_call(J.aula_groups, size=None if count else (size or 4), count=count)


@J.socketio.on("aula_mark")
def handle_aula_mark(data):
    d = data or {}
    res = J._aula_call(aula.mark, d.get("name"), bool(d.get("present")))
    J.aula_ui["attendance_until"] = time.time() + 3 * 3600
    return res


@J.socketio.on("aula_export")
def handle_aula_export(data=None):
    return J._aula_call(J.aula_export_attendance)


@J.socketio.on("aula_material")
def handle_aula_material(data):
    d = data or {}
    kind = d.get("kind") if d.get("kind") in aula.KINDS else "quiz"
    tema = str(d.get("tema") or "").strip()[:200]
    if not tema:
        return {"ok": False, "error": "Escribe el tema."}
    grado = str(d.get("grado") or "").strip()[:40]
    cantidad = aula.to_int(str(d.get("cantidad") or "")) or None
    extra = str(d.get("extra") or "").strip()[:600]
    request_text = f"{aula.KINDS[kind][0]} sobre {tema}" + (f" para grado {grado}" if grado else "") \
        + (f". Indicaciones: {extra}" if extra else "")
    J.generate_material(request_text, kind, cantidad, grado, tema)
    return {"ok": True}


@J.socketio.on("review_capture")
def handle_review_capture(data):
    src = (data or {}).get("source")
    try:
        path = J.capture_camera() if src == "camara" else J.capture_screen_for_review()
        J._set_review_image(path, src)
        return {"ok": True, "preview": J._preview_b64(path)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"No pude capturar: {e}"}


@J.socketio.on("review_upload")
def handle_review_upload(data):
    try:
        path = J.load_uploaded_image((data or {}).get("data", ""))
        J._set_review_image(path, "imagen")
        return {"ok": True, "preview": J._preview_b64(path)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"No pude abrir la imagen: {e}"}


@J.socketio.on("review_run")
def handle_review_run(data):
    d = data or {}
    if not J.review_state["path"]:
        return {"ok": False, "error": "Primero toma una foto, captura la pantalla o sube una imagen."}
    J.start_review("actual", estudiante=str(d.get("estudiante") or "")[:80], que=str(d.get("que") or "")[:200],
                 clave=str(d.get("clave") or "")[:3000], grado=str(d.get("grado") or "")[:40])
    return {"ok": True}


@J.socketio.on("aula_teacher")
def handle_aula_teacher(data):
    d = data or {}
    errs = J.apply_settings({k: d[k] for k in ("aula_docente", "aula_institucion", "aula_open_docs",
                                             "aula_auto_open", "camera_index") if k in d})
    return {"ok": not errs, "error": "; ".join(errs)}


@J.socketio.on("aula_open")
def handle_aula_open(data):
    path = str((data or {}).get("path", ""))
    if path in J.generated_files and os.path.exists(path) and J.IS_WIN:   # solo lo que generó Jarvis
        os.startfile(path)


@J.socketio.on("aula_open_folder")
def handle_aula_open_folder(data=None):
    folder = os.path.join(J.settings["output_dir"], "Material de clase")
    os.makedirs(folder, exist_ok=True)
    if J.IS_WIN:
        os.startfile(folder)
    else:
        webbrowser.open(f"file://{folder}")


@J.socketio.on("aula_fullscreen")
def handle_aula_fullscreen(data=None):
    w = J.hud.get("aula_win")
    if w is not None:
        try:
            w.toggle_fullscreen()
        except Exception:
            pass


@J.app.route("/bienvenida")
def welcome_page():
    return render_template("bienvenida.html", version=J.VERSION)


@J.app.route("/ajustes")
def settings_page():
    return render_template("settings.html", version=J.VERSION, providers=J.PROVIDERS)


@J.app.route("/api/ping")
def api_ping():
    if request.remote_addr not in ("127.0.0.1", "::1"):
        abort(403)
    return f"jarvis {J.VERSION}"


@J.app.route("/api/show")
def api_show():
    if request.remote_addr not in ("127.0.0.1", "::1"):
        abort(403)
    J.hud_show()
    return "ok"


@J.socketio.on("connect")
def handle_connect():
    emit("bootstrap", {
        "logs": list(J.log_buffer),
        "chat": list(J.chat_buffer),
        "state": dict(J.state),
        "settings": J.public_settings(),
        "size": J.hud["size"],
        "native": J.hud["window"] is not None,
        "dictation": J.dictation_on.is_set(),
        "timers": J._timers_snapshot(),
    })


def _bak_list():
    return {"folder": J.backup_folder(), "items": respaldo.listing(J.backup_folder())[:30]}


@J.socketio.on("backup_list")
def handle_backup_list(data=None):
    return {"ok": True, **J._bak_list()}


@J.socketio.on("backup_create")
def handle_backup_create(data=None):
    try:
        res = J.make_backup("manual")
        return {"ok": True, "name": res["name"], "summary": J._backup_summary(res),
                "with_secrets": res["with_secrets"], **J._bak_list()}
    except Exception as e:
        return {"ok": False, "error": f"No se pudo guardar la copia: {e}"}


@J.socketio.on("backup_import")
def handle_backup_import(data=None):
    """Copia elegida desde otro lugar (USB, correo…): se valida y se guarda en la carpeta de copias."""
    import base64
    data = data or {}
    try:
        raw = base64.b64decode(str(data.get("b64", "")), validate=True)
    except Exception:
        return {"ok": False, "error": "No se pudo leer el archivo."}
    if len(raw) > respaldo.MAX_BYTES:
        return {"ok": False, "error": "Ese archivo es demasiado grande para ser una copia de Jarvis."}
    folder = J.backup_folder()
    os.makedirs(folder, exist_ok=True)
    name = f"Jarvis respaldo importado {datetime.datetime.now():%Y-%m-%d %H%M%S}.zip"
    path = os.path.join(folder, name)
    with open(path, "wb") as f:
        f.write(raw)
    try:
        info = respaldo.inspect(path)
    except respaldo.BackupError as e:
        os.remove(path)
        return {"ok": False, "error": str(e)}
    return {"ok": True, "info": info, **J._bak_list()}


@J.socketio.on("backup_restore")
def handle_backup_restore(data=None):
    data = data or {}
    try:
        res = J.restore_backup(data.get("name"), list(data.get("parts") or []))
        return {**res, **J._bak_list()}
    except respaldo.BackupError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        J.log_terminal(f"Restaurar copia: {e}", "ERROR")
        return {"ok": False, "error": f"No se pudo restaurar: {e}"}


@J.socketio.on("backup_open_folder")
def handle_backup_open_folder(data=None):
    folder = J.backup_folder()
    os.makedirs(folder, exist_ok=True)
    if J.IS_WIN:
        os.startfile(folder)
    else:
        webbrowser.open(f"file://{folder}")


@J.socketio.on("telegram_test")
def handle_telegram_test(data=None):
    return J.telegram_test()


@J.socketio.on("quake_test")
def handle_quake_test(data=None):
    return J.quake_test()


@J.socketio.on("get_profile")
def handle_get_profile(data=None):
    return {"facts": perfil.snapshot()}


@J.socketio.on("delete_fact")
def handle_delete_fact(data):
    perfil.delete(str((data or {}).get("id", "")))
    return {"facts": perfil.snapshot()}


@J.socketio.on("clear_profile")
def handle_clear_profile(data=None):
    perfil.clear()
    return {"facts": perfil.snapshot()}


@J.socketio.on("email_test")
def handle_email_test(data=None):
    addr = J.settings["email_address"].strip()
    if not correo.valid_sender(addr):
        return {"ok": False, "msg": "Escribe tu dirección de correo (Gmail) y guarda."}
    if not J.settings["email_app_password"].strip():
        return {"ok": False, "msg": "Falta la contraseña de aplicación (16 letras)."}
    host, port = correo.SMTP.get(addr.split("@")[-1].lower(), ("smtp.gmail.com", 587))
    import smtplib, ssl
    try:
        with smtplib.SMTP(host, port, timeout=20) as sm:
            sm.ehlo(); sm.starttls(context=ssl.create_default_context())
            sm.login(addr, J.settings["email_app_password"].strip())
        return {"ok": True, "msg": f"Conexión correcta con {host}. Ya puedes dictar correos."}
    except smtplib.SMTPAuthenticationError:
        return {"ok": False, "msg": "Tu cuenta rechazó la contraseña. Usa una «contraseña de aplicación» de 16 letras, no tu clave normal."}
    except Exception as e:
        return {"ok": False, "msg": f"No pude conectar: {e}"}


@J.socketio.on("weather_preview")
def handle_weather_preview(data=None):
    city = str((data or {}).get("city") or "").strip()
    if not city and not J.settings["weather_city"].strip():
        return {"ok": False, "msg": "Escribe tu ciudad arriba (por ejemplo, Bogotá) y guarda."}
    txt = J.weather_text(city)
    ok = not txt.lower().startswith(("no ", "ahora no", "para darte"))
    if ok:
        J.speak(txt)
    return {"ok": ok, "msg": txt}


@J.socketio.on("live_test")
def handle_live_test(data=None):
    return J.live_test()


@J.socketio.on("system_check")
def handle_system_check(data=None):
    items = J.run_system_check(speak_it=False)
    return {"items": items, "at": J.check_state["at"], "report": J.check_report(items)}


@J.socketio.on("update_check")
def handle_update_check(data=None):
    try:
        info = J.check_updates()
        return {"ok": True, "info": info, "status": J.update_status()}
    except actualizar.UpdateError as e:
        return {"ok": False, "error": str(e), "status": J.update_status()}
    except Exception as e:
        return {"ok": False, "error": f"No pude consultar GitHub: {e}", "status": J.update_status()}


@J.socketio.on("update_apply")
def handle_update_apply(data=None):
    if J.upd["busy"]:
        return {"ok": False, "error": "Ya se está actualizando."}
    threading.Thread(target=J.install_update, daemon=True).start()
    return {"ok": True}


@J.socketio.on("update_rollback")
def handle_update_rollback(data=None):
    return J.rollback_update()


@J.socketio.on("get_settings")
def handle_get_settings():
    return {
        "settings": J.public_settings(),
        "voices": J.SPANISH_VOICES,
        "themes": [(k, v[0]) for k, v in J.THEMES.items()],
        "positions": list(J.HUD_POSITIONS.items()),
        "autostart_supported": J.autostart_supported(),
        "config_path": J.CONFIG_PATH,
        "log_path": J.LOG_PATH,
        "portable": J.PORTABLE,
        "env_path": J.ENV_PATH if J.env_overrides else "",
        "alarm_found": J.resolve_alarm_sound() or "",
        "piper_installed": J.PIPER_INSTALLED,
        "piper_found": J.find_piper_voice() or "",
        "whisper_installed": J._whisper_installed(),
        "stt_refine_mode": J.stt_refine_mode(),
        "whisper_models": J.WHISPER_SIZES,
        "gemini_tts_voices": J.GEMINI_TTS_VOICES,
        "gemini_tts_models": J.GEMINI_TTS_MODELS,
        "gemini_key_set": bool(J._gemini_for_stt()),
        "update": J.update_status(),
        "profile": perfil.snapshot(),
        "email_info": {"sender_ok": correo.valid_sender(J.settings["email_address"]),
                       "pass": bool(J.settings["email_app_password"].strip())},
        "tg_info": {"ok": J.tg["ok"], "remote": J.settings["telegram_remote"], "error": J.tg["error"],
                    "token": bool(J.settings["telegram_token"].strip()), "chat": bool(J.settings["telegram_chat"].strip())},
        "live_info": {"mode": J.live_mode(), "why": J.live["why"], "ws": J._ws_installed(),
                      "key": bool(J._live_order(include_paused=True)), "model": J._live_load().get("combo", [""])[0],
                      "keys": {p: bool(J._live_key(p)) for p in J.LIVE_PROVIDERS},
                      "openai_voices": envivo.OPENAI_VOICES, "deepgram_voices": envivo.DEEPGRAM_VOICES},
        "offline_info": {"offline": J.net["offline"], "local_model": J.local_ai_model(refresh=True),
                         "piper": bool(J.PIPER_INSTALLED and J.find_piper_voice())},
        "default_system_prompt": J.DEFAULT_SYSTEM_PROMPT,
        "providers": {k: {"short": v["short"], "kind": v["kind"], "default_model": v.get("model", "")}
                      for k, v in J.PROVIDERS.items()},
        "capabilities": J.CAPABILITIES,
        "app_count": skills.app_count(),
        "apps_ready": skills.apps_ready(),
        "skills": [{"name": s.name, "desc": s.desc, "dangerous": s.dangerous}
                   for s in skills.REGISTRY.values()],
        "version": J.VERSION,
    }


@J.socketio.on("save_settings")
def handle_save_settings(data):
    errors = J.apply_settings(data)
    pub = J.public_settings()
    J.socketio.emit("settings_updated", pub)
    return {"ok": not errors, "errors": errors, "settings": pub}


@J.socketio.on("list_models")
def handle_list_models(data):
    data = dict(data or {})
    test = bool(data.pop("test", False))
    try:
        if test:                                      # botón «Probar»: prueba una respuesta real
            return {"ok": True, **J.ai_test(data)}
        cfg = J._ai_cfg(data)
        models = J.ai_list_models(cfg)
        return {"ok": True, "models": models,
                "recommended": J._recommend_model(cfg["ai_provider"], models) if models else ""}
    except J.AIError as e:
        return {"ok": False, "error": e.why if e.kind != "bad" else str(e), "models": []}


@J.socketio.on("open_url")
def handle_open_url(data):
    """Abre en el navegador la página para crear la clave (solo las de los proveedores)."""
    url = str((data or {}).get("url", ""))
    if url in {p.get("key_url") for p in J.PROVIDERS.values()}:
        webbrowser.open(url)


@J.socketio.on("open_fix")
def handle_open_fix(data):
    """Botón «Arreglar» de la prueba completa: solo abre ajustes de Windows (ms-settings:)."""
    url = str((data or {}).get("url", ""))
    if re.fullmatch(r"ms-settings:[a-z0-9-]+", url) and J.IS_WIN:
        try:
            os.startfile(url)
        except OSError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True}
    return {"ok": False, "error": "No permitido."}


@J.socketio.on("list_voices")
def handle_list_voices():
    if J.edge_tts is None:
        return {"ok": False, "error": "Edge-TTS no está instalado.", "voices": J.SPANISH_VOICES}
    try:
        return {"ok": True, "voices": J.list_edge_voices()}
    except Exception as e:
        return {"ok": False, "error": f"Sin conexión con el servicio de voces: {e}", "voices": J.SPANISH_VOICES}


@J.socketio.on("preview_voice")
def handle_preview_voice(data):
    data = data or {}
    if not J.audio_ready:
        return {"ok": False, "error": "El audio de salida no está disponible."}
    backend = data.get("backend") or J.settings["tts_backend"]
    gem = {}
    if backend == "gemini":
        if not J._gemini_for_stt():
            return {"ok": False, "error": "Para la voz de Gemini guarda primero tu clave de Gemini (Ajustes › IA)."}
        J._gtts["pause_until"] = 0.0                       # probar = reintentar aunque estuviera en pausa
        for k in ("gemini_tts_voice", "gemini_tts_model", "gemini_tts_style"):
            if data.get(k) is not None:
                try:
                    gem[k] = J._validate(k, data[k])       # se prueba con lo elegido, sin guardarlo
                except Exception:
                    return {"ok": False, "error": "Opción de voz de Gemini no válida."}
    if backend == "piper":
        if not J._ensure_piper():
            return {"ok": False, "error": "Piper no está instalado (pip install piper-tts)."}
        if not J.find_piper_voice():
            return {"ok": False, "error": "No hay voz de Piper. Ejecuta descargar_voz.py."}
    try:
        voice = J._validate("tts_voice", data.get("voice", J.settings["tts_voice"]))
        rate, volume, pitch = (J._validate(k, data.get(k, J.settings[k]))
                               for k in ("tts_rate", "tts_volume", "tts_pitch"))
    except Exception as e:
        return {"ok": False, "error": str(e)}
    J.stop_speech()
    J.speak("Hola, soy Jarvis. Así sonará mi voz con esta configuración.",
          voice=voice, rate=rate, volume=volume, pitch=pitch, force=True, backend=backend, gemini=gem)
    return {"ok": True}


@J.socketio.on("list_mics")
def handle_list_mics():
    try:
        return {"ok": True, "devices": J.list_mics()}
    except Exception as e:
        return {"ok": False, "error": str(e), "devices": []}


@J.socketio.on("reindex_apps")
def handle_reindex_apps():
    try:
        return {"ok": True, "count": skills.index_apps()}
    except Exception as e:
        return {"ok": False, "error": str(e), "count": skills.app_count()}


@J.socketio.on("test_alarm")
def handle_test_alarm(data):
    path = J.resolve_alarm_sound((data or {}).get("path", ""))
    if not path:
        return {"ok": False, "error": "No encontré el sonido. Pon sirena.mp3 en la carpeta «recursos» o indica la ruta."}
    if not J.audio_ready:
        return {"ok": False, "error": "El audio de salida no está disponible."}
    J.stop_speech()
    J.play_sound(path, max_seconds=5)
    return {"ok": True, "path": path}


@J.socketio.on("toggle_mic")
def handle_toggle_mic():
    J.toggle_mic()
    return {"mic_enabled": J.settings["mic_enabled"]}


@J.socketio.on("open_output")
def handle_open_output():
    path = J.settings["output_dir"]
    os.makedirs(path, exist_ok=True)
    if hasattr(os, "startfile"):
        os.startfile(path)
        return {"ok": True}
    return {"ok": False, "error": f"Abre manualmente: {path}"}


@J.socketio.on("clear_history")
def handle_clear_history():
    J.clear_memory()
    J.chat_buffer.clear()
    J.log_terminal("Conversación reiniciada.", "SISTEMA")
    return {"ok": True}


@J.socketio.on("manual_command")
def handle_manual_command(data):
    cmd = str((data or {}).get("command", "")).strip()[:1000]
    if not cmd:
        return
    J.log_terminal(cmd, "USUARIO")
    m = re.match(r"^\s*whatsapp\s+(\+\d{8,15})\s+(.+)$", cmd, re.I | re.S)
    if m:
        J.push_chat("user", cmd, "texto")
        threading.Thread(target=J.send_whatsapp_message, args=m.groups(), daemon=True).start()
        return
    J.submit_command(cmd, "texto")


@J.socketio.on("stop_voice")
def handle_stop_voice():
    J.stop_speech()


@J.socketio.on("hud_set_size")
def handle_hud_set_size(data):
    J.hud_set_size(str((data or {}).get("size", "compacto")))


_drag = {"lock": threading.Lock(), "n": 0}


def _hud_hwnd():
    if not J.IS_WIN:
        return 0
    import ctypes
    return ctypes.windll.user32.FindWindowW(None, J.HUD_TITLE)


@J.socketio.on("hud_drag")
def handle_hud_drag(data):
    """Arrastre del HUD (ver hud.js). En Windows se mueve con SetWindowPos desde este hilo,
    fuera del evento de ratón de WebView2, que es donde Windows rechazaba el movimiento."""
    win = J.hud["window"]
    if win is None:
        return
    try:
        phase = str(data.get("phase"))
        x, y = float(data.get("x", 0)), float(data.get("y", 0))
        dpr = float(data.get("dpr") or 1) or 1
        n = int(data.get("n", 0))
    except (TypeError, ValueError, AttributeError):
        return
    with J._drag["lock"]:
        if phase == "start":
            pos = None
            if J.IS_WIN:
                import ctypes
                from ctypes import wintypes
                r = wintypes.RECT()
                hwnd = J._hud_hwnd()
                if hwnd and ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r)):
                    pos = (r.left, r.top)
                J._drag.update(hwnd=hwnd, scale=dpr)       # Windows: píxeles físicos
            if pos is None:
                pos = (J.hud["x"], J.hud["y"])
                J._drag.update(hwnd=0, scale=1)            # pywebview: píxeles lógicos
            J._drag.update(sx=x, sy=y, pos=pos, n=n, active=True)
            J.hud["ignore_moves_until"] = 0
            return
        if not J._drag.get("active") or n <= J._drag["n"]:  # mensaje viejo o desordenado
            return
        J._drag["n"] = n
        nx = int(J._drag["pos"][0] + round((x - J._drag["sx"]) * J._drag["scale"]))
        ny = int(J._drag["pos"][1] + round((y - J._drag["sy"]) * J._drag["scale"]))
        if phase == "end":
            J._drag["active"] = False
    try:
        if J._drag.get("hwnd"):
            import ctypes
            # SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
            ctypes.windll.user32.SetWindowPos(J._drag["hwnd"], 0, nx, ny, 0, 0, 0x0001 | 0x0004 | 0x0010)
        else:
            win.move(nx, ny)
    except Exception as e:
        J.log_terminal(f"No se pudo mover el HUD: {e}", "AVISO")


@J.socketio.on("hud_hide")
def handle_hud_hide():
    J.hud_hide()


@J.socketio.on("open_settings")
def handle_open_settings():
    J.open_settings_window()


@J.socketio.on("close_settings")
def handle_close_settings():
    J.close_settings_window()


@J.socketio.on("shutdown")
def handle_shutdown():
    J.quit_app()


__all__ = [
    '_aula_call',
    '_aula_state',
    '_bak_list',
    '_drag',
    '_hud_hwnd',
    'api_ping',
    'api_show',
    'apply_settings',
    'aula_page',
    'handle_aula_delete_course',
    'handle_aula_export',
    'handle_aula_fullscreen',
    'handle_aula_get',
    'handle_aula_groups',
    'handle_aula_mark',
    'handle_aula_material',
    'handle_aula_open',
    'handle_aula_open_folder',
    'handle_aula_pick',
    'handle_aula_reset_pick',
    'handle_aula_save_course',
    'handle_aula_set_active',
    'handle_aula_teacher',
    'handle_backup_create',
    'handle_backup_import',
    'handle_backup_list',
    'handle_backup_open_folder',
    'handle_backup_restore',
    'handle_calendar_test',
    'handle_clear_history',
    'handle_clear_profile',
    'handle_close_settings',
    'handle_connect',
    'handle_delete_fact',
    'handle_email_test',
    'handle_get_profile',
    'handle_get_settings',
    'handle_hud_drag',
    'handle_hud_hide',
    'handle_hud_set_size',
    'handle_list_mics',
    'handle_list_models',
    'handle_list_voices',
    'handle_live_test',
    'handle_manual_command',
    'handle_notes_add',
    'handle_notes_clear_done',
    'handle_notes_delete',
    'handle_notes_done',
    'handle_notes_get',
    'handle_open_fix',
    'handle_open_output',
    'handle_open_settings',
    'handle_open_url',
    'handle_preview_voice',
    'handle_quake_test',
    'handle_reindex_apps',
    'handle_review_capture',
    'handle_review_run',
    'handle_review_upload',
    'handle_rutinas_defaults',
    'handle_rutinas_delete',
    'handle_rutinas_get',
    'handle_rutinas_run',
    'handle_rutinas_save',
    'handle_save_settings',
    'handle_shutdown',
    'handle_stop_voice',
    'handle_system_check',
    'handle_telegram_test',
    'handle_test_alarm',
    'handle_toggle_mic',
    'handle_update_apply',
    'handle_update_check',
    'handle_update_rollback',
    'handle_weather_preview',
    'index',
    'settings_page',
    'welcome_page',
]
