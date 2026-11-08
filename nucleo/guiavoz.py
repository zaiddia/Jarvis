"""Guía de Jarvis y autoprueba (12.16).

- Página /guia: todo lo que Jarvis sabe hacer, por grupos, con buscador y botón «Probar» en cada ejemplo.
- «¿Qué puedes hacer con el presupuesto?» responde con los ejemplos que coinciden. «Abre la guía».
- Autoprueba: revisa en tu equipo, sin cambiar nada, que las funciones nuevas tengan lo que necesitan; sale en la
  prueba completa y en el panel de salud («haz la autoprueba»).
"""
import importlib.util
import os
import re

import guia
import hogar
import misapps
import skills
from nucleo import J

_gv = {"win": None}


# ============================================================================ GUÍA
def guide():
    return guia.build(J.CAPABILITIES)


@J.app.route("/guia")
def jarvis_guide_page():
    from flask import render_template
    return render_template("guia_jarvis.html", version=J.VERSION, asset_v=getattr(J, "ASSET_V", ""), look=J.settings.get("look", "clasico"))


def open_guide_page():
    J._open_page("/guia", "Guía", _gv)


@J.socketio.on("open_guide_page")
def handle_open_guide(data=None):
    open_guide_page()
    return {"ok": True}


@J.socketio.on("guide_data")
def handle_guide_data(data=None):
    g = guide()
    return {"categorias": g, "total": guia.count(g), "version": J.VERSION}


@J.socketio.on("guide_try")
def handle_guide_try(data=None):
    cmd = re.sub(r"\s+", " ", str((data or {}).get("cmd") or "")).strip()[:200]
    if not cmd or cmd.startswith("("):
        return {"ok": False}
    J.log_terminal(cmd, "USUARIO")
    J.submit_command(cmd, "texto")
    return {"ok": True}


_GUIA_OPEN = re.compile(r"\b(?:abre|abreme|muestra|muestrame|ensename)\s+(?:la\s+)?(?:guia|lista de ordenes|lista de comandos)(?:\s+de jarvis)?\b|"
                      r"^(?:jarvis\s+)?(?:que (?:puedes|sabes) hacer|que haces|cuales son tus (?:funciones|comandos|ordenes))\??$")
_GUIA_ASK = re.compile(r"\bque (?:puedes|sabes) hacer (?:con|sobre|en|para)\s+(?:el |la |los |las |mi |mis )?(.+?)\??$|"
                     r"\bcomo (?:te )?(?:uso|pido|manejo) (?:el |la |los |las |mi |mis )?(.+?)\??$")


def guide_voice(text, t):
    m = _GUIA_ASK.search(t)
    if m:
        hits = guia.search(guide(), m.group(1) or m.group(2))
        if hits:
            J.reply(guia.spoken(hits), "GUÍA")
            return True
        J.reply("No encontré eso en lo que sé hacer. Abre la guía y búscalo con otras palabras: di «abre la guía».", "GUÍA")
        return True
    if _GUIA_OPEN.search(t):
        open_guide_page()
        J.reply(f"Te abrí la guía: {guia.count(guide())} ejemplos de lo que sé hacer, por grupos. Búscalo o pulsa «Probar».", "GUÍA")
        return True
    return False


# ============================================================================ AUTOPRUEBA
def _has(mod):
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError):
        return False


def features_check():
    """Revisiones de las funciones nuevas en este equipo (solo leer). Mismo formato que system_check."""
    out = []

    def add(grupo, estado, texto, arreglo=""):
        out.append({"grupo": grupo, "estado": estado, "texto": texto, "arreglo": arreglo})
    G = "Funciones nuevas (autoprueba)"
    # Ventanas de Jarvis: selector de archivos («Examinar…») y la píldora
    wv = J.webview
    if wv is None or J.hud.get("window") is None:
        add(G, "aviso", "El HUD corre en el navegador: «Examinar…» y la píldora del borde solo funcionan en la ventana de Jarvis.")
    else:
        fd = getattr(wv, "FileDialog", None) or getattr(wv, "OPEN_DIALOG", None)
        add(G, "ok" if fd is not None else "fallo", "El selector de archivos de Windows está disponible («Examinar…»)." if fd is not None else
            "Esta versión de la ventana no trae selector de archivos: escribe o pega las rutas en Mis aplicaciones.")
        if J.IS_WIN:
            try:
                import ctypes
                scale = round(ctypes.windll.user32.GetDpiForSystem() / 96 * 100)
                add(G, "ok" if scale in (100, 125, 150, 175, 200) else "aviso", f"Zoom de la pantalla: {scale} %; la píldora y el HUD se ajustan a ese tamaño.")
            except Exception:
                pass
    # Mis aplicaciones: rutas que ya no existen
    missing = [a["nombre"] for a in misapps.data["apps"] if a["tipo"] in ("carpeta", "archivo") or (a["tipo"] == "app" and not a.get("appid"))
               if not re.match(r"^(?:https?:|shell:|ms-|\w+:$)", a["destino"]) and ("\\" in a["destino"] or "/" in a["destino"])
               and not os.path.exists(a["destino"])]
    if missing:
        add(G, "aviso", "Tarjetas de Mis aplicaciones que apuntan a algo que ya no está: " + ", ".join(missing[:5]) + ".", "")
    elif misapps.data["apps"]:
        add(G, "ok", f"Las {len(misapps.data['apps'])} tarjetas de Mis aplicaciones apuntan a cosas que existen.")
    add(G, "ok" if skills.app_count() else "aviso", f"Programas del menú Inicio listos para agregar: {skills.app_count()}." if skills.app_count() else
        "Aún no leí los programas del menú Inicio (Ajustes › Control del PC › Actualizar).")
    # Generador de documentos
    libs = {"python-docx (Word)": "docx", "openpyxl (Excel)": "openpyxl", "python-pptx (PowerPoint)": "pptx", "fpdf2 (PDF)": "fpdf"}
    faltan = [n for n, m in libs.items() if not _has(m)]
    add(G, "ok" if not faltan else "fallo", "El generador de documentos tiene todo para los 6 formatos." if not faltan else
        "Al generador le falta: " + ", ".join(faltan) + ". Vuelve a ejecutar instalar.bat.")
    # Audio y voz
    edge = J.edge_tts is not None
    piper = False
    try:
        piper = bool(J.find_piper_voice())
    except Exception:
        pass
    add(G, "ok" if edge or piper else "fallo", "Documentos en audio: " + ("voz de Edge (con internet)" if edge else "") + (" y " if edge and piper else "")
        + ("Piper (sin internet)" if piper else "") + "." if edge or piper else "No hay voz para pasar documentos a audio (falta edge-tts o Piper).")
    # Recibos: IA que ve imágenes
    try:
        cfg, err = J._vision_cfg()
        add(G, "ok" if cfg else "aviso", "La IA puede leer fotos de recibos." if cfg else f"Para leer fotos de recibos: {err}")
    except Exception as e:
        add(G, "aviso", f"No pude revisar la IA que ve imágenes: {e}")
    # Médico del PC
    ps = J.psutil
    add(G, "ok" if ps is not None else "fallo", "El médico del PC puede medir disco, memoria y batería." if ps is not None else "Falta psutil para el médico del PC.")
    if J.IS_WIN:
        code, _ = J._pc_run(["powercfg", "/?"], 15)
        add(G, "ok" if code in (0, 1) else "aviso", "powercfg responde (salud de la batería)." if code in (0, 1) else "powercfg no respondió: no podré medir el desgaste de la batería.")
    # Celular y Google
    if J.settings.get("telegram_remote") and J.settings.get("telegram_token"):
        add(G, "ok" if J.tg.get("ok") else "aviso", "Telegram conectado: puedes mandarle fotos y archivos desde el celular." if J.tg.get("ok") else
            "Telegram está configurado pero no conecta ahora: " + (J.tg.get("error") or "sin respuesta"))
    else:
        add(G, "info", "Telegram no está configurado: actívalo para mandarle fotos de recibos y documentos desde el celular.")
    if J.classroom_client():
        has = "contacts.readonly" in str(J.settings.get("google_scopes") or "")
        add(G, "ok" if has else "aviso", "Google da permiso para leer los cumpleaños de tus contactos." if has else
            "Para traer los cumpleaños de tus contactos, vuelve a pulsar «Conectar con Google» (pide el permiso nuevo) y activa la People API.")
    contacts = skills._parse_contacts() if hasattr(skills, "_parse_contacts") else {}
    add(G, "ok" if contacts else "info", f"Contactos para compartir por WhatsApp: {len(contacts)}." if contacts else
        "Para compartir listas o menús por WhatsApp, agrega tus contactos en Ajustes › Cuentas y mensajes.")
    try:
        path = os.path.join(J.CONFIG_DIR, "mi_dia.json")
        hogar.save()
        add(G, "ok" if os.path.exists(path) or not any(hogar.data[k] for k in ("venc", "meds", "citas", "cumples")) else "fallo",
            "Mi día guarda bien sus datos.")
    except Exception as e:
        add(G, "fallo", f"Mi día no pudo guardar: {e}")
    return out


_AUTO = re.compile(r"\b(?:haz|hazme|corre|ejecuta)\s+(?:la\s+)?autoprueba\b|\bprueba (?:las )?funciones nuevas\b|\bautoprueba\b")


def autotest_voice(text, t):
    if not _AUTO.search(t):
        return False
    items = features_check()
    bad = [i for i in items if i["estado"] == "fallo"]
    warn = [i for i in items if i["estado"] == "aviso"]
    okn = len([i for i in items if i["estado"] == "ok"])
    msg = f"Autoprueba: {okn} cosas funcionan."
    if bad:
        msg += " No funciona: " + " ".join(i["texto"] for i in bad[:3])
    if warn:
        msg += " Para revisar: " + " ".join(i["texto"] for i in warn[:3])
    J.reply(msg + (" El detalle está en el panel de salud." if bad or warn else " Todo en orden."), "AUTOPRUEBA")
    if bad or warn:
        try:
            J.open_health_panel()
        except Exception:
            pass
    return True


__all__ = ['_AUTO', '_GUIA_ASK', '_GUIA_OPEN', '_gv', '_has', 'autotest_voice', 'features_check', 'guide', 'jarvis_guide_page', 'guide_voice',
           'handle_guide_data', 'handle_guide_try', 'handle_open_guide', 'open_guide_page']
