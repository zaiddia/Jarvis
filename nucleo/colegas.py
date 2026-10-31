"""10.0: kit para colegas (exportar e importar lo que le enseñaste a Jarvis) y reuniones de área (agenda y acta de lo
que dictas, punto por punto).

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import json
import os
import re

import aula
import banco
import clasevivo
import compromisos
import habilidades
import kit
import lecciones
import reunion
import rutinas
import seguimiento
import semana
from nucleo import J


# ============================================================================ KIT PARA COLEGAS
def kit_build():
    return kit.build(rutinas.routines, habilidades.snapshot(), lecciones.items, clasevivo.data.get("actividades", []),
                     clasevivo.data.get("planes", []), banco.items, J.settings["aula_docente"] or J.settings["address_name"],
                     rutinas.DEFAULTS)


def kit_export(say=True):
    k = J.kit_build()
    path = kit.save(k, J.settings["output_dir"])
    J.generated_files.add(path)
    if say:
        J.reply(kit.summary(k) + " Lo guardé en Documentos, Jarvis, Kit para colegas: compártelo por correo o WhatsApp. "
                "No lleva nada de tus estudiantes. Tu colega lo importa en Ajustes › Agente › Kit para colegas.", "KIT")
    return path, k


def kit_import(text):
    """Suma el kit a lo que ya tienes. Devuelve {parte: cuántos se agregaron}."""
    k = kit.parse(text)
    origin = f"kit de {k['autor']}" if k["autor"] else "kit"
    added = dict.fromkeys(kit.PARTS, 0)
    have = {rutinas.normalize(r["nombre"]) for r in rutinas.routines}
    for r in k["rutinas"]:
        name = str(r["nombre"]).strip()[:60]
        if rutinas.normalize(name) in have:
            continue
        try:                                           # sin «cuándo»: una rutina ajena nunca se lanza sola
            rutinas.upsert(name, ", ".join(str(f) for f in (r.get("frases") or [])), "\n".join(str(p) for p in r["pasos"]))
            added["rutinas"] += 1
        except ValueError:
            pass
    have_sk = {habilidades.normalize(x["nombre"]) for x in habilidades.skills}
    for h in k["habilidades"]:
        if habilidades.normalize(str(h.get("nombre", ""))) in have_sk:
            continue
        try:
            habilidades.install(json.dumps(h, ensure_ascii=False))
            added["habilidades"] += 1
        except (ValueError, OSError):
            pass
    for t in k["lecciones"]:
        if lecciones.add(t, origin):
            added["lecciones"] += 1
    known = {clasevivo.norm(a["actividad"]) for a in clasevivo.data.get("actividades", [])}
    for a in k["actividades"]:
        if clasevivo.norm(a["actividad"]) not in known:
            res = a.get("resultado")
            clasevivo.record_outcome(str(a.get("tema", ""))[:120], origin, str(a["actividad"])[:600],
                                     int(res) if isinstance(res, (int, float)) else None)
            added["actividades"] += 1
    have_plans = {clasevivo.norm(str(p.get("tema", "")) + " " + str(p.get("titulo", ""))) for p in clasevivo.data.get("planes", [])}
    for p in k["planes"]:
        if clasevivo.norm(str(p.get("tema", "")) + " " + str(p.get("titulo", ""))) not in have_plans:
            clasevivo.remember_plan(p, origin)
            added["planes"] += 1
    by = {}
    for q in k["banco"]:
        by.setdefault((str(q.get("tema", "")), str(q.get("grado", ""))), []).append(q)
    for (tema, grado), qs in by.items():
        added["banco"] += banco.add_quiz({"tema": tema, "grado": grado, "preguntas": qs})
    return k, added


def kit_added_text(k, added):
    parts = [kit.label(p, n) for p, n in added.items() if n]
    who = f" de {k['autor']}" if k["autor"] else ""
    return (f"Importé el kit{who}: " + ", ".join(parts) + ".") if parts else f"El kit{who} no trae nada que no tuvieras ya."


@J.socketio.on("kit")
def handle_kit(data=None):
    d = data or {}
    try:
        if d.get("export"):
            path, k = J.kit_export(say=False)
            return {"ok": True, "path": path, "summary": kit.summary(k)}
        if d.get("preview"):
            return {"ok": True, "summary": kit.summary(kit.parse(str(d["preview"])))}
        if d.get("import"):
            k, added = J.kit_import(str(d["import"]))
            msg = J.kit_added_text(k, added)
            J.log_terminal(msg, "KIT")
            return {"ok": True, "summary": msg}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "summary": kit.summary(J.kit_build())}


_KIT_EXP = re.compile(r"\b(?:exporta|exportame|comparte|compartir|prepara|preparame|haz|hazme|crea|creame|genera|generame|arma|armame)\s+"
                      r"(?:mi|un|el)\s+kit\b|\bkit para (?:mis )?colegas\b")
_KIT_IMP = re.compile(r"\b(?:importa|importar|instala|instalar|cargar|carga)\s+(?:un|el|este)\s+kit\b|\bcomo (?:importo|instalo) un kit\b")


def kit_voice(text, t):
    if _KIT_IMP.search(t):
        J.reply("Para importar el kit de un colega: Ajustes › Agente › Kit para colegas › «Importar un kit», y eliges el archivo. "
                "Te muestro qué trae antes de sumarlo.", "KIT")
        return True
    if not _KIT_EXP.search(t):
        return False
    J.kit_export()
    return True


# ============================================================================ REUNIONES DE ÁREA
meeting = {"st": None, "agenda": [], "agenda_nombre": ""}


def _meeting_path():
    return os.path.join(J.CONFIG_DIR, "reunion.json")


def _meeting_save():
    try:
        with open(_meeting_path(), "w", encoding="utf-8") as f:
            json.dump(meeting, f, ensure_ascii=False)
    except (OSError, TypeError):
        pass


def _meeting_ctx():
    """Datos tuyos que suelen tratarse en la reunión de área."""
    parts = []
    left = semana.days_left(J.settings["period_end"]) if J.settings.get("period_end") else None
    if left is not None and left >= 0:
        parts.append(f"faltan {left} días para cerrar el periodo")
    for c in sorted(set(aula.data.get("cursos", {})) | set(seguimiento.data), key=aula.course_sort_key)[:24]:
        names = sorted(set(aula.students(c)) | set(seguimiento.data.get(c, {})))
        r = seguimiento.at_risk(c, names, J._absences(c), J.settings["risk_grade"], J.settings["risk_absences"])
        if r:
            parts.append(f"{len(r)} estudiantes en riesgo en {c}")
    return "; ".join(parts)


_AG_RE = re.compile(r"\b(?:prepara|preparame|haz|hazme|arma|armame|organiza|organizame)\s+(?:la\s+|una\s+)?agenda\s+(?:de|para)\s+(?:la\s+)?"
                    r"(reunion(?:\s+de\s+(?:area|departamento|docentes|profesores|grado|ciencias|matematicas|humanidades)[\w ]*?)?)"
                    r"(?:\s+(?:sobre|con|con los puntos|puntos|para tratar)\s*:?\s*(.+))?$")
_MT_START = re.compile(r"^(?:jarvis\s+)?(?:empieza|inicia|abre|comienza|empecemos)\s+(?:el\s+)?acta(?:\s+de\s+(?:la\s+)?(.+))?$|"
                       r"^(?:jarvis\s+)?(?:empieza|inicia|comienza|empecemos)\s+la\s+(reunion(?:\s+de\s+.+)?)$")
_MT_END = re.compile(r"^(?:jarvis\s+)?(?:termina|cierra|finaliza|terminamos)\s+(?:el\s+acta|la\s+reunion)\b")
_MT_ADD = re.compile(r"^(?:anota en el acta|en el acta|para el acta|acta)\s*(?:que)?\s*[:,]?\s*(.+)$")
_MT_DIRECT = re.compile(r"^(?:asistentes|asisten|acuerdo|acordamos|se acuerda|se acordo|tarea para|compromiso de|compromiso para)\b|"
                        r"\b(?:se encarga de|queda encargad[oa] de|se compromete a)\b|^(?:yo\s+)?me encargo de\b")
_MT_ASK = re.compile(r"\bque (?:llevo|hay|tengo) en el acta\b|\bcomo va el acta\b")


def _mt_tail(text, t, tail_plain):
    """El final de la frase original (con mayúsculas y tildes) que corresponde a tail_plain."""
    n = len(tail_plain)
    return text.strip()[-n:] if n and len(text.strip()) >= n else tail_plain


def meeting_voice(text, t):
    m = _AG_RE.search(t)
    if m:
        nombre = m.group(1).strip().capitalize().replace("Reunion", "Reunión").replace("area", "área")
        puntos = reunion.parse_agenda(_mt_tail(text, t, m.group(2))) if m.group(2) else []
        J.reply("Organizo la agenda…", "REUNIÓN")
        J.meeting_agenda(nombre, puntos)
        return True
    st = meeting["st"]
    m = _MT_START.match(t)
    if m:
        nombre = (m.group(1) or m.group(2) or "reunión de área").strip()
        nombre = nombre[:1].upper() + nombre[1:]
        nombre = nombre.replace("Reunion", "Reunión").replace(" area", " área")
        meeting["st"] = reunion.new(nombre, meeting["agenda"])
        _meeting_save()
        J.reply(f"Acta abierta: {nombre}" + (f", con la agenda de {len(meeting['agenda'])} puntos" if meeting["agenda"] else "") +
                ". Dime «asistentes: …», «anota en el acta que…», «acuerdo: …» o «tarea para Luis: …». Al final, «termina el acta».", "REUNIÓN")
        return True
    if not st:
        return False
    if _MT_END.match(t):
        J.reply("Cierro el acta y la redacto…", "REUNIÓN")
        if getattr(J._tl, "capture", None) is not None:
            J.meeting_close()
        else:
            J.start_job("Redactando el acta", J.meeting_close, "acta")
        return True
    if _MT_ASK.search(t):
        J.reply(f"Llevo {len(st['asistentes'])} asistentes, {len(st['puntos'])} notas, {len(st['acuerdos'])} acuerdos y "
                f"{len(st['tareas'])} compromisos." + (f" Lo último: {st['puntos'][-1]}." if st["puntos"] else ""), "REUNIÓN")
        return True
    m = _MT_ADD.match(t)
    if m or _MT_DIRECT.search(t):
        body = _mt_tail(text, t, m.group(1)) if m else text
        kind, val = reunion.add(st, body)
        _meeting_save()
        J.reply({"asistentes": f"Anotados {len(val)} asistentes.", "acuerdo": "Acuerdo anotado.",
                 "tarea": f"Compromiso para {val['quien'] if isinstance(val, dict) else ''} anotado.",
                 "punto": "Anotado."}[kind], "REUNIÓN")
        return True
    return False


def meeting_agenda(nombre, puntos):
    agenda = list(puntos)
    if J.state.get("ai") == "ok":
        try:
            raw = J.ai_chat([{"role": "user", "content": reunion.agenda_prompt(nombre, "; ".join(puntos), J._meeting_ctx()) + J.lessons_ctx()}],
                            json_mode=True, max_tokens=700)
            got = [str(x).strip() for x in (J._extract_json(raw).get("agenda") or []) if str(x).strip()][:10]
            if got:
                agenda = got
        except Exception:
            pass
    if not agenda:
        agenda = ["Verificación de asistencia", "Lectura del acta anterior", "Varios"]
    meeting.update(agenda=agenda, agenda_nombre=nombre)
    _meeting_save()
    path = ""
    if J.Document is not None:
        path = reunion.agenda_docx(nombre, agenda, J.settings["output_dir"], J.Document, institucion=J.settings["aula_institucion"])
        J.generated_files.add(path)
    J.reply(f"Agenda de la {nombre.lower()}: " + "; ".join(f"{i}. {a}" for i, a in enumerate(agenda, 1)) + "." +
            (" La guardé en Documentos, Jarvis, Actas." if path else "") + " Cuando empiece, di «empieza el acta» y la uso.", "REUNIÓN")
    return agenda


def meeting_close():
    st = meeting["st"]
    if not st:
        return ""
    st["on"] = False
    fin = datetime.datetime.now().strftime("%H:%M")
    desarrollo = None
    if J.state.get("ai") == "ok" and st["puntos"]:
        try:
            raw = J.ai_chat([{"role": "user", "content": reunion.minutes_prompt(st)}], json_mode=True, max_tokens=2500)
            desarrollo = [str(x).strip() for x in (J._extract_json(raw).get("desarrollo") or []) if str(x).strip()] or None
        except Exception:
            desarrollo = None
    path = ""
    if J.Document is not None:
        path = reunion.build_docx(st, J.settings["output_dir"], J.Document, desarrollo, J.settings["aula_institucion"], fin)
        J.generated_files.add(path)
        J._open_doc(path)
    mine = [x for x in st["tareas"] if x["quien"] == "Yo"]
    for x in mine:                                     # tus compromisos quedan en «¿qué compromisos tengo?»
        compromisos.add(x["que"] + (f" para el {x['cuando']}" if x["cuando"] and x["cuando"] not in x["que"].lower() else ""), "reunión")
    meeting.update(st=None, agenda=[], agenda_nombre="")
    _meeting_save()
    J.notify(f"Listo el acta de la {st['nombre'].lower()}: {len(st['asistentes'])} asistentes, {len(st['acuerdos'])} acuerdos y "
             f"{len(st['tareas'])} compromisos" + (f" ({len(mine)} tuyos, ya los anoté)" if mine else "") +
             (". La abrí: revísala antes de firmarla." if path else "."), "REUNIÓN")
    return path


def colleagues_start():
    try:
        with open(_meeting_path(), encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            meeting.update({k: d.get(k, meeting[k]) for k in meeting})
    except (OSError, ValueError):
        pass


__all__ = ['_AG_RE', '_KIT_EXP', '_KIT_IMP', '_MT_ADD', '_MT_ASK', '_MT_DIRECT', '_MT_END', '_MT_START', '_meeting_ctx', '_meeting_path',
           '_meeting_save', '_mt_tail', 'colleagues_start', 'handle_kit', 'kit_added_text', 'kit_build', 'kit_export', 'kit_import',
           'kit_voice', 'meeting', 'meeting_agenda', 'meeting_close', 'meeting_voice']
