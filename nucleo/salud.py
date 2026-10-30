"""8.0: registro de errores con informe para enviar, claves cifradas y revisión guiada de cada conexión.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import os
import re
import sys
import threading

import errores
import secreto
from nucleo import J


# ============================================================================ ERRORES
def _secret_values():
    return [J.settings.get(k, "") for k in J.SECRET_FIELDS]


def health_start():
    errores.configure(J.CONFIG_DIR, _secret_values)
    old_hook = sys.excepthook

    def hook(tp, val, tb):
        try:
            errores.record("SIN CONTROLAR", val, getattr(J._tl, "cmd_text", "") or "")
        except Exception:
            pass
        old_hook(tp, val, tb)
    sys.excepthook = hook

    def thook(args):
        if args.exc_type is SystemExit:
            return
        try:
            errores.record(f"HILO {getattr(args.thread, 'name', '?')}"[:40], args.exc_value)
            J.log_terminal(f"Error en segundo plano: {args.exc_type.__name__}: {args.exc_value}", "ERROR")
        except Exception:
            pass
    threading.excepthook = thook
    threading.Timer(75.0, J._check_after_update).start()
    _migrate_secrets()


def _migrate_secrets():
    """Las claves que estaban sin cifrar en config.json se cifran la primera vez."""
    if not secrets_protected():
        return
    try:
        import json
        with open(J.CONFIG_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return
    if any(isinstance(raw.get(k), str) and raw[k] and not secreto.is_sealed(raw[k]) for k in J.SECRET_FIELDS):
        try:
            J.save_settings_file()
            J.log_terminal("Cifré tus claves con la protección de Windows.", "SEGURIDAD")
        except OSError as e:
            J.note_error("SEGURIDAD", e)


def note_error(origin, error, cmd=""):
    """Para los except de Jarvis: deja constancia del error real (con traza) sin interrumpir."""
    try:
        errores.record(origin, error, cmd or getattr(J._tl, "cmd_text", "") or "")
    except Exception:
        pass


def make_report():
    """(texto, ruta) del informe: prueba completa + últimos errores + final del registro, sin claves."""
    try:
        items = J.run_system_check(speak_it=False)
        check = J.check_report(items)
    except Exception as e:
        check = f"(la prueba completa falló: {e})"
    text = errores.report(J.VERSION, check, J.log_buffer)
    folder = os.path.join(J.settings["output_dir"], "Informes")
    path = ""
    try:
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"Informe de Jarvis {datetime.datetime.now():%Y-%m-%d %H%M}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        path = ""
    return text, path


_REPORT_RE = re.compile(r"\b(?:genera|haz|hazme|crea|prepara|envia|enviame|manda|mandame)\s+(?:el|un)\s+informe\s+(?:de\s+)?"
                        r"(?:errores|fallos|problemas|jarvis|diagnostico)\b")
_ERRORS_RE = re.compile(r"\b(?:has tenido|tuviste|hay|tienes)\s+(?:algun(?:os)?\s+)?(?:errores|fallos)\b|\bque errores\b")


def health_voice(text, t):
    if _REPORT_RE.search(t):
        _, path = J.make_report()
        if getattr(J._tl, "remote", False) and J.telegram_ready() and path:
            try:
                with open(path, "rb") as f:
                    J._tg_call("sendDocument", {"chat_id": J.settings["telegram_chat"].strip()},
                               files={"document": (os.path.basename(path), f.read(), "text/plain")}, timeout=60)
                J.reply("Te mandé el informe por aquí. No lleva tus claves.", "INFORME")
                return True
            except Exception:
                pass
        if path:
            J.generated_files.add(path)
            J._open_doc(path)
        J.reply("Listo: guardé el informe en Documentos, carpeta Jarvis, Informes" + (" y lo abrí" if path else "") +
                ". No lleva tus claves; puedes enviarlo a quien te ayuda con Jarvis.", "INFORME")
        return True
    if _ERRORS_RE.search(t):
        J.reply(errores.spoken(), "INFORME")
        return True
    return False


@J.socketio.on("report_make")
def handle_report_make(data=None):
    text, path = J.make_report()
    return {"text": text, "path": path}


@J.socketio.on("errors_info")
def handle_errors_info(data=None):
    if (data or {}).get("clear"):
        errores.clear()
    return {"items": errores.recent(30)[::-1]}


# ============================================================================ CLAVES CIFRADAS
secrets_lost = []       # claves cifradas que no se pudieron abrir (config.json copiado de otro equipo)


def secrets_protected():
    return bool(J.settings["encrypt_secrets"]) and secreto.available() and not J.PORTABLE


# ============================================================================ REVISIÓN GUIADA DE CONEXIONES
def extra_checks():
    """Más comprobaciones para la prueba completa: solo de lo que tienes configurado."""
    out, s = [], J.settings

    def add(grupo, estado, texto, arreglo=""):
        out.append({"grupo": grupo, "estado": estado, "texto": texto, "arreglo": arreglo})

    G = "Seguridad"
    n_keys = sum(1 for k in J.SECRET_FIELDS if s.get(k))
    if J.PORTABLE:
        add(G, "info", "Modo USB: las claves no se cifran (si se cifraran no funcionarían en otro PC).")
    elif secrets_protected():
        add(G, "ok", f"Tus {n_keys} clave(s) están cifradas: solo tu usuario de Windows puede abrirlas.")
    elif secreto.available():
        add(G, "aviso", "Tus claves se guardan sin cifrar.", "ajustes:acerca")
    if secrets_lost:
        add(G, "fallo", "No pude abrir estas claves (¿copiaste Jarvis de otro equipo?): " + ", ".join(secrets_lost) +
            ". Vuelve a escribirlas en Ajustes.", "ajustes:ia")

    G = "Conexiones"
    if s["whatsapp_phone"] or s["whatsapp_apikey"]:
        ok = J.whatsapp_ready()
        add(G, "ok" if ok else "fallo", "WhatsApp configurado (prueba el envío en Ajustes › Integraciones)." if ok else
            "WhatsApp a medias: falta el número con +57 o la clave de CallMeBot.", "" if ok else "ajustes:integraciones")
    if s["classroom_client_id"]:
        if not s["classroom_refresh"]:
            add(G, "aviso", "Classroom: pusiste el ID pero falta pulsar «Conectar».", "ajustes:memoria")
        else:
            try:
                n = len(J.classroom_courses(force=True))
                add(G, "ok", f"Classroom conectado: {n} clase(s).")
            except Exception as e:
                add(G, "fallo", f"Classroom no responde: {e}", "ajustes:memoria")
    if s["email_read"] and s["email_address"]:
        r = J.handle_mail_test()
        add(G, "ok" if r.get("ok") else "fallo", f"Correo: leo tu bandeja ({r.get('n', 0)} recientes)." if r.get("ok") else
            f"Correo: {r.get('error')}", "" if r.get("ok") else "ajustes:integraciones")
    if s["sync_folder"].strip():
        okf = os.path.isdir(s["sync_folder"].strip())
        add(G, "ok" if okf and not J.sync_state["error"] else "fallo",
            "Sincronización entre equipos activa." if okf and not J.sync_state["error"] else
            (J.sync_state["error"] or f"No encuentro la carpeta {s['sync_folder']}."), "" if okf else "ajustes:agente")
    if J._gemini_for_stt():
        m = ""
        try:
            m = J.image_model()
        except Exception:
            pass
        add(G, "ok" if m else "info", f"Imágenes para clase con {m}." if m else
            "Tu clave de Gemini no tiene modelo de imágenes: «hazme una ilustración…» no funcionará.")
    try:
        for sv in J.mcp_hub.status():
            if not sv.get("ok"):
                add(G, "fallo", f"Conector «{sv.get('nombre')}» no conecta: {sv.get('error') or 'sin respuesta'}.",
                    "ajustes:integraciones")
    except Exception:
        pass

    G = "Errores"
    week = (datetime.datetime.now() - datetime.timedelta(days=7)).isoformat()
    errs = [e for e in errores.recent(200) if e["t"] >= week and e["nivel"] == "error"]
    add(G, "ok" if not errs else "aviso", "Sin errores en los últimos 7 días." if not errs else
        f"{len(errs)} error(es) en los últimos 7 días; el último: {errs[-1]['error'][:140]}. "
        "Pulsa «Enviar informe» para que lo puedan arreglar.", "")
    return out


def _check_after_update():
    """Tras instalar una versión nueva (o el primer día), revisa todo una vez y avisa si algo falla."""
    if J.settings["checked_version"] == J.VERSION:
        return
    try:
        items = J.run_system_check(speak_it=False)
    except Exception as e:
        J.note_error("PRUEBA", e)
        return
    J.settings["checked_version"] = J.VERSION
    try:
        J.save_settings_file()
    except OSError:
        pass
    bad = [i for i in items if i["estado"] == "fallo"]
    if bad:
        msg = (f"Revisé mis sistemas con la versión {J.VERSION}: {len(bad)} cosa(s) por arreglar. La primera: "
               f"{bad[0]['texto']} Las demás, con su botón «Arreglar», en Ajustes › Acerca de.")
        J.push_chat("jarvis", msg, "PRUEBA")
        J.log_terminal(msg, "PRUEBA")


__all__ = [
    '_ERRORS_RE', '_REPORT_RE', '_check_after_update', '_migrate_secrets', '_secret_values', 'extra_checks', 'handle_errors_info',
    'handle_report_make', 'health_start', 'health_voice', 'make_report', 'note_error', 'secrets_lost',
    'secrets_protected',
]
