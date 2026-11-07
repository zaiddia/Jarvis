"""Mis aplicaciones (12.14): la página de tarjetas, abrirlas con tus frases, grupos y horario.

- Página /aplicaciones: tarjetas con nombre, tipo, frases, ruta; Probar, Editar, Eliminar, «+».
- «Examinar…» abre el selector de archivos de Windows (tú escoges el programa o la carpeta).
- Las frases de las tarjetas se atienden antes que las demás órdenes (son tuyas).
- Grupos («modo clase» abre varias tarjetas) y horario (Campus los lunes a las 6:50).
"""
import os
import re
import threading
import time

import misapps
import skills
from nucleo import J

apps_ui = {"win": None, "fired": {}, "started": False}
_BROWSERS = [("", "El que estés usando"), ("brave.exe", "Brave"), ("chrome.exe", "Chrome"), ("msedge.exe", "Edge"),
             ("firefox.exe", "Firefox"), ("opera.exe", "Opera"), ("vivaldi.exe", "Vivaldi")]


def _builtin_phrases():
    out = set()
    for k in list(skills.BUILTIN_APPS) + list(skills.SITES) + list(skills.FOLDERS):
        out.update({k, f"abre {k}", f"abrir {k}", f"abre el {k}", f"abre la {k}"})
    out.update({"modo sigilo", "mostrar panel", "para", "silencio", "callate", "modo clase", "modo examen", "modo proyector"})
    return out


# ============================================================================ ABRIR
def _launch_one(x, browser=""):
    d, tipo = x["destino"], x["tipo"]
    if tipo == "web":
        used = skills.open_url(d, browser or x.get("navegador") or "")
        return f"en {used}" if used else ""
    if tipo in ("carpeta", "archivo") and not d.lower().startswith("shell:") and not os.path.exists(d):
        raise skills.SkillError(f"No encuentro «{d}». ¿Lo moviste? Edita la tarjeta «{x['nombre']}».")
    if x.get("appid"):
        skills._launch_app("appid", d)
    else:
        skills._launch(d)
    if tipo == "carpeta":
        skills.context["explorer_t"] = time.time()
    return ""


def launch_item(x, browser=""):
    """Abre una tarjeta o un grupo. → lo que se dice."""
    misapps.used(x["id"])
    if "items" in x:                                           # grupo
        cards = [c for c in (misapps.get(i) for i in x["items"]) if c]
        errs = []

        def go():
            for c in cards:
                try:
                    _launch_one(c, browser)
                except Exception as e:
                    errs.append(str(e))
                    J.log_terminal(f"Grupo «{x['nombre']}»: {e}", "AVISO")
                time.sleep(0.8)                                 # que cada programa alcance a abrir
        threading.Thread(target=go, daemon=True, name="grupo-apps").start()
        return f"Abriendo «{x['nombre']}»: " + ", ".join(c["nombre"] for c in cards) + "."
    extra = _launch_one(x, browser)
    return f"Abriendo {x['nombre']}{' ' + extra if extra else ''}."


def apps_open_hook(q):
    """skills.open_app: «abre campus», «abre música en brave» buscan primero en tus tarjetas."""
    browser = ""
    m = re.match(r"^(.+?)\s+en\s+(?:el\s+)?(?:navegador\s+)?(" + "|".join(sorted(skills.BROWSER_PROCS, key=len, reverse=True)) + r")$", q)
    if m:
        q, browser = m.group(1).strip(), skills.BROWSER_PROCS[m.group(2)]
    x = misapps.match_name(q)
    if not x or (browser and x.get("tipo") != "web" and "items" not in x):
        return None
    return launch_item(x, browser)


# ============================================================================ PROBAR UNA FRASE (sin abrir nada)
def try_phrase(text):
    x = misapps.match_phrase(text)
    if x:
        return {"ok": True, "quien": "tarjeta", "id": x["id"], "texto": _what(x, "Abriría tu " + ("grupo" if "items" in x else "tarjeta"))}
    t = misapps.norm(text)
    m = re.match(r"^(?:abre|abrir|abreme|inicia|lanza|ejecuta|pon|ponme)\s+(?:el |la |los |las |mi |mis )?(.+)$", t)
    if m:
        q = skills.clean_target(m.group(1))
        x = misapps.match_name(q)
        if x:
            return {"ok": True, "quien": "tarjeta", "id": x["id"], "texto": _what(x, "Abriría tu " + ("grupo" if "items" in x else "tarjeta"))}
        custom = skills._custom_commands()
        k = skills._best_match(q, custom, 0.85)
        if k:
            return {"ok": True, "quien": "atajo", "texto": f"Abriría tu atajo de Ajustes «{k}» → {custom[k]}."}
        if q in skills.BUILTIN_APPS:
            return {"ok": True, "quien": "jarvis", "texto": f"Abriría {skills.BUILTIN_APPS[q][0]} (programa de Windows que Jarvis ya conoce)."}
        for table, what in ((skills.SITES, "la web"), (skills.FOLDERS, "la carpeta")):
            k = skills._best_match(q, table, 0.85)
            if k:
                return {"ok": True, "quien": "jarvis", "texto": f"Abriría {what} «{k}» (Jarvis ya la conoce)."}
        k = skills._best_match(q, skills._apps, 0.8) if skills._apps else None
        if k:
            return {"ok": True, "quien": "jarvis", "texto": f"Abriría «{skills._apps[k][0]}» del menú Inicio."}
        return {"ok": True, "quien": "nada", "texto": f"No encuentro «{q}» en tus tarjetas ni en los programas: Jarvis te diría que no lo encontró. "
                                                      "Puedes crear una tarjeta con esa frase."}
    return {"ok": True, "quien": "orden", "texto": "No es de tus aplicaciones: Jarvis la tomará como una orden normal (o se la pasará a la IA)."}


def _what(x, lead):
    if "items" in x:
        names = [c["nombre"] for c in (misapps.get(i) for i in x["items"]) if c]
        return f"{lead} «{x['nombre']}»: abre {', '.join(names)}."
    where = {"web": "la web", "app": "el programa", "carpeta": "la carpeta", "archivo": "el archivo"}[x["tipo"]]
    br = next((n for p, n in _BROWSERS if p and p == x.get("navegador")), "")
    return f"{lead} «{x['nombre']}»: {where} {x['destino']}" + (f" en {br}" if br else "") + "."


# ============================================================================ VOZ
_AP_PAGE = re.compile(r"\b(?:abre|abreme|muestra|muestrame|ensename|abrir)\s+(?:el |la |los |mis |mi )?"
                      r"(?:control de aplicaciones|mis aplicaciones|aplicaciones guardadas|panel de aplicaciones|mis atajos|atajos)\b")


def apps_voice(text, t):
    if _AP_PAGE.search(t):
        open_apps_page()
        n = len(misapps.data["apps"])
        J.reply(f"Te abrí tus aplicaciones: {n} {'tarjeta' if n == 1 else 'tarjetas'}. Pulsa «+» para agregar otra.", "PC")
        return True
    x = misapps.match_phrase(text)
    if not x:
        return False
    try:
        J.reply(launch_item(x), "PC")
    except skills.SkillError as e:
        J.reply(str(e), "PC")
    except Exception as e:
        J.reply(f"No pude abrir «{x['nombre']}»: {e}", "PC")
    return True


# ============================================================================ HORARIO
def _apps_worker():
    while True:
        try:
            for x in misapps.due(fired=apps_ui["fired"]):
                J.log_terminal(f"Horario: abro «{x['nombre']}» ({misapps.describe_schedule(x['horario'])}).", "PC")
                try:
                    launch_item(x)
                    J.notice_add(f"Abrí «{x['nombre']}» como lo programaste.", "aviso", "PC")
                except Exception as e:
                    J.log_terminal(f"Horario de «{x['nombre']}»: {e}", "AVISO")
            cut = time.time() - 2 * 86400
            for k in [k for k, v in apps_ui["fired"].items() if v < cut]:
                apps_ui["fired"].pop(k, None)
        except Exception as e:
            J.log_terminal(f"Horario de aplicaciones: {e}", "AVISO")
        time.sleep(30)


def apps_start():
    misapps.configure(J.CONFIG_DIR)
    import_custom()
    skills.configure(apps_open=apps_open_hook)
    if not apps_ui["started"]:
        apps_ui["started"] = True
        threading.Thread(target=_apps_worker, daemon=True, name="horario-apps").start()


def import_custom():
    """Los atajos escritos en Ajustes (nombre = destino) pasan a tarjetas y el campo queda vacío para los nuevos."""
    text = str(J.settings.get("custom_commands") or "")
    if not text.strip():
        return 0
    n = misapps.import_text(text)
    with J.settings_lock:
        J.settings["custom_commands"] = ""
        try:
            J.save_settings_file()
        except Exception:
            pass
    if n:
        J.log_terminal(f"Pasé {n} atajo(s) de Ajustes a «Mis aplicaciones».", "PC")
    return n


# ============================================================================ PÁGINA
@J.app.route("/aplicaciones")
def apps_page():
    from flask import render_template
    return render_template("aplicaciones.html", version=J.VERSION, asset_v=getattr(J, "ASSET_V", ""), look=J.settings.get("look", "clasico"))


def _state():
    favs = J.favorites() if hasattr(J, "favorites") else []
    out = {"apps": misapps.data["apps"], "grupos": misapps.data["grupos"], "tipos": misapps.TIPOS, "navegadores": _BROWSERS,
           "dias": misapps.DIAS, "favoritos": favs, "top": [x["id"] for x in misapps.most_used(5)], "windows": bool(J.IS_WIN),
           "examinar": apps_ui["win"] is not None}
    for x in out["apps"] + out["grupos"]:
        x["horario_txt"] = misapps.describe_schedule(x.get("horario"))
    return out


def open_apps_page():
    J._open_page("/aplicaciones", "Mis aplicaciones", apps_ui)


def _open_page(path, title, holder):
    if J.webview is not None and J.hud.get("window") is not None:
        try:
            holder["win"] = J.webview.create_window(f"Jarvis · {title}", J.URL + path, width=1240, height=820, min_size=(720, 520),
                                                    background_color="#03060c")
            return
        except Exception as e:
            J.note_error("VENTANA", e)
    import webbrowser
    webbrowser.open(J.URL + path)


@J.socketio.on("open_apps_page")
def handle_open_apps_page(data=None):
    open_apps_page()
    return {"ok": True}


@J.socketio.on("apps_state")
def handle_apps_state(data=None):
    return _state()


@J.socketio.on("apps_save")
def handle_apps_save(data=None):
    d = data or {}
    try:
        rec = misapps.upsert_group(d) if d.get("grupo") else misapps.upsert(d)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "id": rec["id"], "avisos": misapps.conflicts(rec["frases"], rec["id"], _builtin_phrases()), **_state()}


@J.socketio.on("apps_check")
def handle_apps_check(data=None):
    d = data or {}
    return {"avisos": misapps.conflicts(d.get("frases") or [], str(d.get("id") or ""), _builtin_phrases())}


@J.socketio.on("apps_delete")
def handle_apps_delete(data=None):
    return {"ok": misapps.remove(str((data or {}).get("id") or "")), **_state()}


@J.socketio.on("apps_test")
def handle_apps_test(data=None):
    x = misapps.get(str((data or {}).get("id") or ""))
    if not x:
        return {"ok": False, "error": "No encuentro esa tarjeta."}
    try:
        return {"ok": True, "msg": launch_item(x)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@J.socketio.on("apps_try")
def handle_apps_try(data=None):
    return try_phrase(str((data or {}).get("frase") or "")[:200])


@J.socketio.on("apps_installed")
def handle_apps_installed(data=None):
    if not skills.apps_ready() and J.IS_WIN:
        threading.Thread(target=skills.index_apps, daemon=True).start()
    have = {(a["destino"]) for a in misapps.data["apps"]}
    out = [{"nombre": name, "destino": target, "appid": kind == "appid", "ya": target in have}
           for name, kind, target in sorted(skills._apps.values(), key=lambda v: v[0].lower())]
    return {"apps": out[:600], "listo": skills.apps_ready()}


@J.socketio.on("apps_fav")
def handle_apps_fav(data=None):
    x = misapps.get(str((data or {}).get("id") or ""))
    if not x:
        return {"ok": False}
    r = J.handle_favorite_toggle({"cmd": x["frases"][0]})
    return {"ok": True, "favoritos": r.get("favorites", [])}


@J.socketio.on("apps_browse")
def handle_apps_browse(data=None):
    """El selector de archivos de Windows, en la ventana de Mis aplicaciones. Tú escoges; Jarvis solo recibe la ruta."""
    win = apps_ui["win"]
    if win is None or J.webview is None:
        return {"ok": False, "error": "Escribe o pega la ruta (el selector solo funciona en la ventana de Jarvis)."}
    folder = (data or {}).get("tipo") == "carpeta"
    try:
        FD = getattr(J.webview, "FileDialog", None)
        kind = (FD.FOLDER if folder else FD.OPEN) if FD else (J.webview.FOLDER_DIALOG if folder else J.webview.OPEN_DIALOG)
        types = () if folder else (("Programas (*.exe;*.lnk;*.bat)", "Todos los archivos (*.*)") if (data or {}).get("tipo") == "app"
                                   else ("Todos los archivos (*.*)",))
        res = win.create_file_dialog(kind, allow_multiple=False, file_types=types) if types else win.create_file_dialog(kind)
    except Exception as e:
        return {"ok": False, "error": f"No se pudo abrir el selector: {e}"}
    if not res:
        return {"ok": False, "cancel": True}
    path = res[0] if isinstance(res, (list, tuple)) else str(res)
    name = os.path.splitext(os.path.basename(path.rstrip("\\/")))[0] or path
    return {"ok": True, "ruta": path, "nombre": name[:1].upper() + name[1:]}


__all__ = [
    '_AP_PAGE',
    '_BROWSERS',
    '_apps_worker',
    '_builtin_phrases',
    '_launch_one',
    '_open_page',
    '_state',
    '_what',
    'apps_open_hook',
    'apps_page',
    'apps_start',
    'apps_ui',
    'apps_voice',
    'handle_apps_browse',
    'handle_apps_check',
    'handle_apps_delete',
    'handle_apps_fav',
    'handle_apps_installed',
    'handle_apps_save',
    'handle_apps_state',
    'handle_apps_test',
    'handle_apps_try',
    'handle_open_apps_page',
    'import_custom',
    'launch_item',
    'open_apps_page',
    'try_phrase',
]
