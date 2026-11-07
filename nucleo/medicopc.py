"""Médico del PC (12.15): mide el equipo, muestra el panel /pc y arregla con tu permiso.

Solo lee el estado de Windows; lo que cambia algo (borrar temporales, cerrar un programa, apagar un programa del arranque)
se hace con tu clic o tu «sí». Nunca pide permisos de administrador.
"""
import os
import re
import tempfile
import threading
import time

import equipo
import pcsalud
from nucleo import J

_md = {"win": None, "updates": None, "upd_t": 0.0, "upd_busy": False, "caps": None, "caps_t": 0.0}


def _ps_json(script, timeout=40):
    code, out = J._pc_ps(script + " | ConvertTo-Json -Compress", timeout)
    if code != 0 or not out.strip():
        return None
    import json
    try:
        return json.loads(out.strip().splitlines()[-1])
    except ValueError:
        return None


def _battery_caps():
    if not J.IS_WIN:
        return None
    if time.time() - _md["caps_t"] < 6 * 3600:
        return _md["caps"]
    path = os.path.join(tempfile.gettempdir(), "jarvis_bateria.xml")
    code, _ = J._pc_run(["powercfg", "/batteryreport", "/xml", "/output", path], 40)
    caps = None
    if code == 0 and os.path.exists(path):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                caps = pcsalud.wear_from_report(f.read())
        except OSError:
            pass
    _md.update(caps=caps, caps_t=time.time())
    return caps


def _antivirus():
    if not J.IS_WIN:
        return None
    d = _ps_json("Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntivirusProduct | Select-Object displayName,productState")
    if d is None:
        return None
    rows = d if isinstance(d, list) else [d]
    return [pcsalud.av_from_state(r.get("displayName", "Antivirus"), r.get("productState")) for r in rows]


def _updates_bg():
    if _md["upd_busy"] or (time.time() - _md["upd_t"] < 3 * 3600 and _md["updates"] is not None):
        return
    _md["upd_busy"] = True

    def go():
        try:
            code, out = J._pc_ps("(New-Object -ComObject Microsoft.Update.Session).CreateUpdateSearcher().Search('IsInstalled=0 and IsHidden=0').Updates.Count",
                                 150)
            m = re.search(r"\b(\d+)\s*$", out.strip()) if code == 0 else None
            _md["updates"] = int(m.group(1)) if m else -1
        except Exception:
            _md["updates"] = -1
        finally:
            _md.update(upd_t=time.time(), upd_busy=False)
            J.socketio.emit("pc_changed", {})
    threading.Thread(target=go, daemon=True, name="pc-actualizaciones").start()


def pc_checks():
    ps = J.psutil
    out = []
    if ps is not None:
        disks = []
        for d in ps.disk_partitions(all=False):
            if "cdrom" in d.opts or not d.fstype:
                continue
            try:
                u = ps.disk_usage(d.mountpoint)
                if u.total >= 4e9:                              # sin particiones pequeñas de sistema o recuperación
                    disks.append((d.mountpoint.rstrip("\\"), u.free, u.total))
            except OSError:
                pass
        out.append(pcsalud.eval_disks(disks))
        vm = ps.virtual_memory()
        heavy = [(equipo.friendly(r["name"]), r["rss"]) for r in J.heavy_processes(3)]
        out.append(pcsalud.eval_memory(vm.percent, vm.total, heavy))
        bat = ps.sensors_battery() if hasattr(ps, "sensors_battery") else None
        out.append(pcsalud.eval_battery(bat.percent if bat else None, bat.power_plugged if bat else False, _battery_caps() if bat else None))
        out.append(pcsalud.eval_uptime((time.time() - ps.boot_time()) / 3600))
    if J.IS_WIN:
        out.append(pcsalud.eval_startup(J.startup_items()))
        out.append(pcsalud.eval_antivirus(_antivirus()))
        _updates_bg()
        out.append(pcsalud.eval_updates(_md["updates"]))
    return out


# ============================================================================ PÁGINA
@J.app.route("/pc")
def pc_page():
    from flask import render_template
    return render_template("pc.html", version=J.VERSION, asset_v=getattr(J, "ASSET_V", ""), look=J.settings.get("look", "clasico"))


def open_pc_page():
    J._open_page("/pc", "Médico del PC", _md)


@J.socketio.on("open_pc_page")
def handle_open_pc(data=None):
    open_pc_page()
    return {"ok": True}


@J.socketio.on("pc_state")
def handle_pc_state(data=None):
    cs = pc_checks()
    return {"checks": cs, "score": pcsalud.score(cs), "inicio": J.startup_items() if J.IS_WIN else [], "windows": J.IS_WIN}


@J.socketio.on("pc_fix")
def handle_pc_fix(data=None):
    a = str((data or {}).get("accion") or "")
    if a == "temporales":
        J._clean_temp("MÉDICO DEL PC")                  # pide tu «sí» con lo que va a liberar
        return {"ok": True, "msg": "Te pedí permiso en el HUD con lo que se liberaría."}
    if a == "cerrar_top":
        J._kill_heaviest("MÉDICO DEL PC")
        return {"ok": True, "msg": "Te pregunté en el HUD antes de cerrarlo."}
    if a == "inicio":
        return {"ok": True, "inicio": J.startup_items()}
    if re.fullmatch(r"ms-settings:[a-z\-]+|windowsdefender:", a) and J.IS_WIN:
        try:
            os.startfile(a)
            return {"ok": True}
        except OSError as e:
            return {"ok": False, "error": str(e)}
    return {"ok": False, "error": "Eso no lo puedo hacer desde aquí."}


@J.socketio.on("pc_startup")
def handle_pc_startup(data=None):
    """Apagar o encender un programa del arranque (los de tu usuario; los del equipo necesitan administrador)."""
    d = data or {}
    item = next((x for x in J.startup_items() if x["nombre"] == d.get("nombre")), None)
    if not item:
        return {"ok": False, "error": "No lo encuentro."}
    if not item["puede"]:
        return {"ok": False, "error": "Ese lo instaló el equipo para todos los usuarios: cámbialo en el Administrador de tareas › Inicio."}
    try:
        J.set_startup(item, bool(d.get("activo")))
    except OSError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "inicio": J.startup_items()}


_PC_VOICE = re.compile(r"\b(?:revisa|chequea|diagnostica|analiza|examina)(?:me)?\s+(?:el|mi|este)\s+(?:pc|computador|portatil|equipo|computadora)\b|"
                       r"\b(?:medico|chequeo|diagnostico|salud|revision)\s+del?\s+(?:pc|computador|portatil|equipo)\b|"
                       r"\bcomo (?:esta|anda|va) (?:el|mi) (?:pc|computador|portatil|equipo)\b|\bsalud de la bateria\b|\bcomo esta la bateria\b")


def pc_doctor_voice(text, t):
    if not _PC_VOICE.search(t):
        return False
    if re.match(r"^(?:jarvis\s+)?(?:abre|abreme|muestra|muestrame)\b", t):
        open_pc_page()
        J.reply("Te abrí el médico del PC.", "MÉDICO DEL PC")
        return True
    J.reply("Revisando tu PC…", "MÉDICO DEL PC")

    def work():
        cs = pc_checks()
        J.reply(pcsalud.spoken(cs), "MÉDICO DEL PC")
        if any(c["estado"] in ("aviso", "fallo") for c in cs):
            open_pc_page()
    J.start_job("Revisando el PC", work, "medico-pc")
    return True


__all__ = ['_PC_VOICE', '_antivirus', '_battery_caps', '_md', '_ps_json', '_updates_bg', 'handle_open_pc', 'handle_pc_fix', 'handle_pc_startup',
           'handle_pc_state', 'open_pc_page', 'pc_checks', 'pc_doctor_voice', 'pc_page']
