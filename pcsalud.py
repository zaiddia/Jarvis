"""Médico del PC (12.15): evaluar lo que se mide del equipo y decir qué hacer. Lógica pura.

nucleo/medicopc.py mide (disco, memoria, arranque, batería, actualizaciones, antivirus, tiempo encendido) y muestra el panel.
Cada revisión → {"id", "titulo", "estado": ok|aviso|fallo|info, "valor", "detalle", "arreglo": [acciones]}.
"""
import re


def gb(n):
    return f"{n / 1e9:.1f} GB".replace(".", ",")


def check(cid, titulo, estado, valor, detalle="", arreglo=None):
    return {"id": cid, "titulo": titulo, "estado": estado, "valor": valor, "detalle": detalle, "arreglo": arreglo or []}


def eval_disks(disks):
    """disks: [(punto, libre, total)]."""
    if not disks:
        return check("disco", "Disco", "info", "No pude leer los discos")
    worst, parts = "ok", []
    for mp, free, total in disks:
        pct = 100 * free / total if total else 100
        st = "fallo" if free < 5e9 or pct < 5 else "aviso" if free < 15e9 or pct < 12 else "ok"
        worst = max(worst, st, key=["ok", "aviso", "fallo"].index)
        parts.append(f"{mp}: {gb(free)} libres de {gb(total)} ({pct:.0f} %)")
    det = {"fallo": "Casi sin espacio: Windows se pone lento y no puede actualizarse.", "aviso": "Poco espacio libre.", "ok": "Espacio suficiente."}[worst]
    return check("disco", "Disco", worst, "; ".join(parts), det,
                 [["temporales", "Borrar temporales"], ["ms-settings:storagesense", "Sensor de almacenamiento"]] if worst != "ok" else [])


def eval_memory(percent, total, heavy):
    """heavy: [(nombre, bytes)]."""
    st = "fallo" if percent >= 90 else "aviso" if percent >= 80 else "ok"
    top = ", ".join(f"{n} ({gb(b)})" for n, b in heavy[:3])
    return check("memoria", "Memoria", st, f"{percent:.0f} % en uso de {gb(total)}", ("Lo que más consume: " + top) if top else "",
                 [["cerrar_top", "Cerrar lo que más consume"]] if st != "ok" and heavy else [])


def eval_startup(items):
    on = [x for x in items if x.get("activo")]
    st = "aviso" if len(on) > 8 else "ok"
    return check("inicio", "Arranque de Windows", st, f"{len(on)} programas arrancan con Windows",
                 "Muchos programas al encender hacen lento el arranque; apaga los que no necesites." if st == "aviso" else
                 "Pocos programas al encender.", [["inicio", "Ver y apagar programas"]])


def wear_from_report(xml_text):
    """Del informe de batería (powercfg /batteryreport /xml): (capacidad de diseño, capacidad actual) en mWh, o None."""
    d = re.search(r"<DesignCapacity>(\d+)</DesignCapacity>", xml_text or "")
    f = re.search(r"<FullChargeCapacity>(\d+)</FullChargeCapacity>", xml_text or "")
    if not d or not f or int(d.group(1)) <= 0:
        return None
    return int(d.group(1)), int(f.group(1))


def eval_battery(percent, plugged, caps):
    if percent is None:
        return check("bateria", "Batería", "info", "Es un equipo de escritorio (sin batería)")
    val = f"{percent:.0f} %" + (" · cargando" if plugged else "")
    if not caps:
        return check("bateria", "Batería", "ok" if percent > 20 or plugged else "aviso", val, "No pude leer el desgaste.")
    design, full = caps
    health = max(0, min(100, round(100 * full / design)))
    st = "fallo" if health < 60 else "aviso" if health < 80 else "ok"
    det = (f"Salud: {health} % de su capacidad original. "
           + {"fallo": "Está muy desgastada: dura bastante menos; considera cambiarla.", "aviso": "Algo desgastada: es normal con los años.",
              "ok": "En buen estado."}[st])
    return check("bateria", "Batería", st, val, det, [["ms-settings:batterysaver", "Opciones de batería"]] if st != "ok" else [])


def av_from_state(name, state):
    """productState de SecurityCenter2 → (activo, al día)."""
    try:
        s = int(state)
    except (TypeError, ValueError):
        return None
    return {"nombre": name, "activo": ((s >> 12) & 0xF) in (1, 3), "al_dia": ((s >> 4) & 0xF) == 0}


def eval_antivirus(avs):
    if avs is None:
        return check("antivirus", "Antivirus", "info", "No pude consultar la seguridad de Windows")
    act = [a for a in avs if a and a["activo"]]
    if not act:
        return check("antivirus", "Antivirus", "fallo", "Ningún antivirus activo", "Activa la Seguridad de Windows (Defender).",
                     [["windowsdefender:", "Abrir Seguridad de Windows"]])
    old = [a for a in act if not a["al_dia"]]
    return check("antivirus", "Antivirus", "aviso" if old else "ok", ", ".join(a["nombre"] for a in act),
                 "Sus definiciones están desactualizadas." if old else "Activo y al día.",
                 [["windowsdefender:", "Abrir Seguridad de Windows"]] if old else [])


def eval_updates(n):
    if n is None:
        return check("actualizaciones", "Actualizaciones de Windows", "info", "Revisando…", "Tarda un minuto la primera vez.",
                     [["ms-settings:windowsupdate", "Abrir Windows Update"]])
    if n < 0:
        return check("actualizaciones", "Actualizaciones de Windows", "info", "No pude consultar", "",
                     [["ms-settings:windowsupdate", "Abrir Windows Update"]])
    return check("actualizaciones", "Actualizaciones de Windows", "aviso" if n else "ok",
                 f"{n} pendiente{'s' if n != 1 else ''}" if n else "Al día", "Instálalas cuando no estés trabajando." if n else "",
                 [["ms-settings:windowsupdate", "Abrir Windows Update"]] if n else [])


def eval_uptime(hours):
    days = hours / 24
    st = "aviso" if days >= 7 else "ok"
    return check("encendido", "Tiempo encendido", st, f"{days:.0f} días" if days >= 1 else f"{hours:.0f} horas",
                 "Reiniciar de vez en cuando libera memoria y termina actualizaciones." if st == "aviso" else "")


def score(checks):
    pts = {"ok": 100, "aviso": 60, "fallo": 15}
    vals = [pts[c["estado"]] for c in checks if c["estado"] in pts]
    return round(sum(vals) / len(vals)) if vals else 0


def spoken(checks):
    bad = [c for c in checks if c["estado"] == "fallo"]
    warn = [c for c in checks if c["estado"] == "aviso"]
    s = score(checks)
    if not bad and not warn:
        return f"Tu PC está bien: {s} de 100. Nada urgente."
    out = f"Tu PC está en {s} de 100."
    if bad:
        out += " Lo urgente: " + "; ".join(f"{c['titulo'].lower()}, {c['valor']}" for c in bad) + "."
    if warn:
        out += " Para revisar: " + "; ".join(f"{c['titulo'].lower()} ({c['valor']})" for c in warn[:3]) + "."
    return out + " Los arreglos están en el panel del médico del PC."
