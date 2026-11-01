"""11.8: HUD de alto impacto. El HUD distinto en cada momento del día (antes, en clase, entre clases, después, en la
noche), una sola bandeja de acciones, respuestas con fórmulas y botones (proyectar, Word, más corto, en voz, graficar),
proyectar cualquier cosa con un clic, la paleta que sabe qué toca ahora, el orbe que informa y «Lo que hice hoy» con
deshacer.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import os
import re
import shutil
import time

import aprobaciones
import aula
import bitacora
import horario
import informes
import mathtext
import momento
import notas
import seguimiento
from nucleo import J

MATH_RULE = (" Si escribes fórmulas o expresiones matemáticas, ponlas entre signos de dólar en LaTeX, por ejemplo $\\frac{3}{4}$, "
             "$x^2 + 3x - 4 = 0$ o $\\sqrt{25} = 5$; el resto del texto, normal.")
_snooze = {}                    # bandeja: clave → hasta cuándo no se muestra
proj = {"now": None}            # lo que está en el proyector: {"kind", "title", "text" | "img"}


# ============================================================================ MOMENTO DEL DÍA
def _mins_to(hhmm, now):
    h, m = map(int, hhmm.split(":"))
    return int((datetime.datetime.combine(now.date(), datetime.time(h, m)) - now).total_seconds() // 60)


def _course_base(curso):
    return str(curso or "").split(" · ")[0].strip()


def _topic_for(curso, materia=""):
    """El tema de esta semana en la planeación anual de ese curso (si la hay)."""
    base = _course_base(curso)
    try:
        keys = [k for k in J.anual.data["planes"] if _course_base(k) == base]
        if len(keys) > 1 and materia:
            keys = [k for k in keys if J.normalize(materia)[:5] in J.normalize(k)] or keys
        for k in keys:
            st = J.plan_status(k)
            if st and st.get("tema_semana"):
                return st["tema_semana"]
    except Exception:
        pass
    return ""


def _roster(curso):
    base = _course_base(curso)
    names = list(aula.data.get("cursos", {}).get(base, []))
    if not names:
        return None
    today = datetime.date.today().isoformat()
    out_today = set(aula.data.get("asistencia", {}).get(base, {}).get(today, []))
    key = curso if curso in informes.data else base
    pos = {}
    for n in names:
        pos[n] = sum(1 for e in informes.data.get(key, {}).get(n, []) if e.get("fecha") == today and e.get("tipo") == "positiva")
    return {"curso": base, "clave": key, "estudiantes": [{"n": n, "falta": n in out_today, "pos": pos[n]} for n in names[:60]]}


def moment_card(now, out):
    x = horario.now_class(now)
    m = momento.moment(now, horario.today(now), bool(x), bool(J.live_class.get("on")), J.settings.get("attention_from", 6),
                       J.settings.get("attention_to", 17))
    card = {"id": m["id"], "titulo": m["titulo"], "acciones": []}
    nx = m["siguiente"]
    if m["id"] == "clase":
        cur = (x or {}).get("curso") or J.live_class.get("curso") or aula.data.get("activo", "")
        card.update(curso=cur, hasta=(x or {}).get("fin", ""), falta=_mins_to(x["fin"], now) if x else None,
                    tema=J.live_class.get("tema") or _topic_for(cur, (x or {}).get("materia", "")))
        card["lista"] = _roster(cur)
        card["acciones"] = [{"t": "Escoger estudiante", "cmd": "escoge un estudiante"}, {"t": "Grupos de 4", "cmd": "haz grupos de 4"},
                            {"t": "Temporizador 5 min", "cmd": "pon un temporizador de 5 minutos"}, {"t": "Ticket de salida", "cmd": "lanza el ticket de salida"},
                            {"t": "Proyector", "cmd": "modo proyector"}]
    elif m["id"] in ("preparar", "inicio", "entre") and nx:
        tema = _topic_for(nx.get("curso", ""), nx.get("materia", ""))
        card.update(siguiente=horario.label(nx), en=m["en"], a_las=nx["inicio"], tema=tema, curso=nx.get("curso", ""), quedan=m["quedan"])
        prep = (f"haz un plan de clase sobre {tema} para {nx.get('curso', '')}" if tema else f"prepárame la próxima clase de {nx.get('curso', '')}").strip()
        card["acciones"] = [{"t": "Prepárame esto", "cmd": prep}, {"t": "Ticket de salida", "cmd": "lanza el ticket de salida"},
                            {"t": "Proyector", "cmd": "modo proyector"}]
        if m["id"] == "entre":
            card["acciones"] += [{"t": "Calificar hojas", "cmd": "califica las hojas"}, {"t": "¿Qué necesita mi atención?", "cmd": "¿qué necesita mi atención?"}]
    elif m["id"] in ("cierre", "jornada"):
        card["acciones"] = [{"t": "¿Qué necesita mi atención?", "cmd": "¿qué necesita mi atención?"}, {"t": "Calificar hojas", "cmd": "califica las hojas"},
                            {"t": "Mis pendientes", "cmd": "¿qué tengo pendiente?"}]
        cur = aula.data.get("activo", "")
        if cur:
            card["acciones"].append({"t": f"Notas de {cur} a Zeti", "cmd": f"exporta las notas de {cur} para Zeti"})
    elif m["id"] == "noche":
        tm = now + datetime.timedelta(days=1)
        clases = []
        for it in horario.today(tm):
            tema = _topic_for(it.get("curso", ""), it.get("materia", ""))
            clases.append({"t": horario.label(it), "a_las": it["inicio"], "tema": tema, "curso": it.get("curso", ""),
                           "cmd": (f"haz un plan de clase sobre {tema} para {it.get('curso', '')}" if tema else f"prepárame la próxima clase de {it.get('curso', '')}").strip()})
        card["manana"] = clases
        card["acciones"] = [{"t": "¿Qué tengo mañana?", "cmd": "¿qué tengo mañana?"}, {"t": "Mis pendientes", "cmd": "¿qué tengo pendiente?"}]
        if now.weekday() == 6:
            card["acciones"].insert(0, {"t": "Prepárame la semana", "cmd": "prepárame la semana"})
    else:                                              # día libre
        card["acciones"] = [{"t": "¿Cómo viene la semana?", "cmd": "¿cómo viene la semana?"}, {"t": "Mis pendientes", "cmd": "¿qué tengo pendiente?"}]
    return card


# ============================================================================ BANDEJA ÚNICA
def inbox(now=None):
    """Aprobaciones y lo que necesita tu atención, en una sola lista: [{"k", "tipo", "p", "t", "id"?, "cmd"?}]."""
    now = now or datetime.datetime.now()
    ts = time.time()
    out = [{"k": f"ap:{a['id']}", "tipo": "aprobar", "p": 0, "t": a["titulo"][:140], "id": a["id"]} for a in aprobaciones.pending()]
    try:
        for x in J.attention_items(now):
            if x["k"].startswith("ap:") or _snooze.get(x["k"], 0) > ts:
                continue
            out.append({"k": x["k"], "tipo": "atencion", "p": x.get("p", 2), "t": x["t"][:140], "cmd": x.get("cmd", "")})
    except Exception as e:
        J.note_error("HUD", e)
    return out[:12]


@J.socketio.on("inbox_snooze")
def handle_inbox_snooze(data=None):
    k = str((data or {}).get("k") or "")
    if k:
        _snooze[k] = time.time() + (3 * 3600 if (data or {}).get("horas") == 3 else 18 * 3600)
    return {"ok": True, "bandeja": J.inbox()}


# ============================================================================ LISTA DEL CURSO EN CLASE
@J.socketio.on("roster_act")
def handle_roster_act(data=None):
    d = data or {}
    curso, est, act = str(d.get("curso") or ""), str(d.get("est") or ""), str(d.get("action") or "")
    base = _course_base(curso)
    if est not in aula.data.get("cursos", {}).get(base, []):
        return {"ok": False, "error": "No encuentro a ese estudiante en el curso."}
    try:
        if act in ("falla", "presente"):
            if aula.data.get("activo") != base:
                aula.set_active(base)
            aula.mark(est, act == "presente")
            msg = f"{est}: {'falla' if act == 'falla' else 'presente'}."
        elif act == "positiva":
            key = curso if curso in seguimiento.data or curso in informes.data else base
            informes.add(key, est, "Participó en clase" + (f" ({d.get('tema')})" if d.get("tema") else "") + ".", tipo="positiva")
            msg = f"Anoté la participación de {est}."
        elif act == "obs" and str(d.get("texto") or "").strip():
            key = curso if curso in seguimiento.data or curso in informes.data else base
            informes.add(key, est, str(d["texto"]).strip()[:500])
            msg = f"Anoté en el observador de {est}."
        else:
            return {"ok": False, "error": "Acción desconocida."}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "msg": msg, "lista": _roster(curso)}


# ============================================================================ BOTONES DE LAS RESPUESTAS
def _word_from(text, title="Respuesta de Jarvis"):
    doc = J.Document()
    doc.add_heading(title, 1)
    for line in mathtext.plain(text).split("\n"):
        ln = line.strip()
        if not ln:
            continue
        m = re.match(r"^(?:[-•*·]|\d+[.)])\s+(.*)$", ln)
        if m:
            doc.add_paragraph(re.sub(r"\*\*|`", "", m.group(1)), style="List Bullet")
        else:
            doc.add_paragraph(re.sub(r"\*\*|`", "", ln))
    folder = os.path.join(J.settings["output_dir"], "Respuestas")
    os.makedirs(folder, exist_ok=True)
    first = re.sub(r'[\\/:*?"<>|$\n]+', " ", mathtext.plain(text)).strip()[:50] or "respuesta"
    path = os.path.join(folder, f"{first} {datetime.datetime.now():%Y-%m-%d %H%M%S}.docx")
    doc.save(path)
    return path


@J.socketio.on("msg_action")
def handle_msg_action(data=None):
    d = data or {}
    text, act = str(d.get("text") or "")[:20000], str(d.get("action") or "")
    if not text.strip():
        return {"ok": False}
    if act == "proyectar":
        J.project_show({"kind": "texto", "text": text, "title": str(d.get("title") or "")})
        return {"ok": True}
    if act == "voz":
        J.speak(text, force=True)
        return {"ok": True}
    if act == "word":
        if J.Document is None:
            return {"ok": False, "error": "Falta python-docx."}
        p = J._word_from(text)
        J.generated_files.add(p)
        return {"ok": True}
    if act == "graficar":
        f = mathtext.graphable(text)
        if not f:
            return {"ok": False, "error": "No encontré una función para graficar."}
        J.submit_command(f"grafica {f}", "texto")
        return {"ok": True}
    if act == "corto":
        if J.state.get("ai") != "ok":
            return {"ok": False, "error": "Necesito la IA conectada."}

        def work():
            try:
                r = J.ai_chat([{"role": "user", "content": "Resume esto en 2 o 3 frases claras, sin perder lo importante (fórmulas entre $…$):\n\n" + text}],
                              max_tokens=400).strip()
                J.reply(r, "JARVIS")
            except J.AIError as e:
                J.notify(J.ai_error_reply(e), "JARVIS")
        J.start_job("Resumiendo", work, "corto")
        return {"ok": True}
    return {"ok": False, "error": "Acción desconocida."}


# ============================================================================ PROYECTAR CON UN CLIC
def project_show(item):
    """item: {"kind": "texto"|"imagen", "text"?, "img" (id de /archivo)?, "title"?}."""
    item = {k: item.get(k) for k in ("kind", "text", "img", "title") if item.get(k) is not None}
    item["t"] = time.time()
    proj["now"] = item
    J.socketio.emit("projector_show", item)
    J.socketio.emit("projecting", {"on": True, "kind": item["kind"], "title": (item.get("title") or mathtext.plain(item.get("text") or "")[:60])})
    if J.hud.get("proj_win") is None and not J.hud.get("proj_open"):
        try:
            J._open_projector()
            J.hud["proj_open"] = True
        except Exception:
            pass


@J.socketio.on("project_show")
def handle_project_show(data=None):
    d = data or {}
    if d.get("path"):
        order = list(getattr(J.generated_files, "order", ()))
        p = str(d["path"])
        if p not in order:
            return {"ok": False, "error": "No encuentro esa imagen."}
        J.project_show({"kind": "imagen", "img": order.index(p), "title": str(d.get("title") or os.path.basename(p))})
    elif d.get("text"):
        J.project_show({"kind": "texto", "text": str(d["text"])[:20000], "title": str(d.get("title") or "")})
    else:
        return {"ok": False}
    return {"ok": True}


@J.socketio.on("project_clear")
def handle_project_clear(data=None):
    proj["now"] = None
    J.socketio.emit("projector_show", {"kind": "nada"})
    J.socketio.emit("projecting", {"on": False})
    return {"ok": True}


@J.socketio.on("projector_now")
def handle_projector_now(data=None):
    return proj["now"] or {"kind": "nada"}


_PROJ_THIS = re.compile(r"^(?:jarvis\s+)?(?:proyecta(?:lo|la|me)?|muestra(?:lo|la)?|pon(?:lo|la)?)\s*(?:eso|esto|la respuesta|la ultima respuesta|la imagen|"
                        r"la formula|lo que dijiste)?\s*(?:en (?:el |la )?(?:proyector|tablero|televisor|tv|pantalla grande))\b|^(?:jarvis\s+)?proyecta(?:lo|la)?\s*"
                        r"(?:eso|esto|la respuesta|la imagen|la formula)?$")


def beam_voice(text, t):
    if not _PROJ_THIS.search(t):
        return False
    if not re.search(r"\b(?:proyectalo|proyectala|proyecta|ponlo|ponla|muestralo|muestrala|eso|esto|respuesta|imagen|formula|dijiste)\b", t):
        return False
    want_img = "imagen" in t
    order = list(getattr(J.generated_files, "order", ()))
    imgs = [i for i, p in enumerate(order) if os.path.splitext(p)[1].lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif")]
    last_txt = next((c["text"] for c in reversed(list(J.chat_buffer)) if c.get("role") != "user" and len(c.get("text", "")) > 3), "")
    if want_img and imgs:
        J.project_show({"kind": "imagen", "img": imgs[-1], "title": os.path.basename(order[imgs[-1]])})
        J.reply("Listo, la imagen está en el proyector.", "PROYECTOR")
    elif last_txt:
        J.project_show({"kind": "texto", "text": last_txt})
        J.reply("Listo, en el proyector.", "PROYECTOR")
    elif imgs:
        J.project_show({"kind": "imagen", "img": imgs[-1]})
        J.reply("Listo, la imagen está en el proyector.", "PROYECTOR")
    else:
        return False
    return True


# ============================================================================ PALETA INTELIGENTE
def smart_palette(now=None):
    """Las órdenes de ahora (según el momento y el curso), con los huecos ya llenos cuando se sabe con qué."""
    now = now or datetime.datetime.now()
    out = []
    try:
        card = J.moment_card(now, {})
    except Exception:
        card = {"acciones": []}
    for a in card.get("acciones", []):
        out.append({"t": a["cmd"], "g": "Ahora", "label": a["t"]})
    for c in card.get("manana", [])[:4]:
        out.append({"t": c["cmd"], "g": "Mañana", "label": f"Preparar {c['t']}"})
    cur = card.get("curso") or aula.data.get("activo", "")
    if cur:
        base = _course_base(cur)
        out += [{"t": f"exporta las notas de {base} para Zeti", "g": "Curso " + base}, {"t": f"¿quiénes están en riesgo en {base}?", "g": "Curso " + base},
                {"t": f"activa la práctica de {base}", "g": "Curso " + base}, {"t": f"mapa de {base}", "g": "Curso " + base}]
    for a in aprobaciones.pending()[:3]:
        out.append({"t": f"sí {a['id']}", "g": "Por aprobar", "label": f"Aprobar: {a['titulo'][:60]}"})
    return out


# ============================================================================ LO QUE HICE HOY (CON DESHACER)
_installed = {"ok": False}


def _remove_obj(lst, obj, save):
    for i, x in enumerate(lst):
        if x is obj:
            del lst[i]
            save()
            return


def install_journal():
    """Envuelve las acciones que cambian tus datos para anotarlas en «Lo que hice hoy» con su deshacer."""
    if _installed["ok"]:
        return
    _installed["ok"] = True
    orig_grade, orig_obs, orig_note, orig_mark, orig_resolve = seguimiento.add, informes.add, notas.add, aula.mark, aprobaciones.resolve

    def grade(curso, estudiante, actividad, nota, origen="voz", fecha=None, dim=None):
        r = orig_grade(curso, estudiante, actividad, nota, origen, fecha, dim)
        try:
            lst = seguimiento.data[curso][estudiante]
            obj = lst[-1]
            nn = str(round(float(nota), 1)).replace(".", ",")
            act = str(actividad or "nota")[:40]
            bitacora.add(f"Anoté {nn} a {estudiante} en «{act}» ({curso})", "nota",
                         undo=lambda: _remove_obj(seguimiento.data.get(curso, {}).get(estudiante, []), obj, seguimiento.save),
                         group=("nota", curso, act, origen), group_text=lambda n: f"Anoté {n} notas de «{act}» ({curso})")
        except Exception:
            pass
        return r

    def obs(curso, estudiante, texto, fecha=None, tipo=None):
        r = orig_obs(curso, estudiante, texto, fecha, tipo)
        try:
            bitacora.add(("Participación de " if r.get("tipo") == "positiva" and str(texto).startswith("Participó") else "Observador de ") +
                         f"{estudiante} ({curso}): {r['texto'][:60]}", "observador",
                         undo=lambda: _remove_obj(informes.data.get(curso, {}).get(estudiante, []), r, informes.save))
        except Exception:
            pass
        return r

    def note(texto, now=None):
        n = orig_note(texto, now)
        try:
            bitacora.add(f"Pendiente: {n['texto'][:80]}", "pendiente", undo=lambda: notas.delete(n["id"]))
        except Exception:
            pass
        return n

    def mark(name, present):
        cur_before = aula.data.get("activo")
        day = aula.data.get("asistencia", {}).get(cur_before, {}).get(datetime.date.today().isoformat(), [])
        was_absent = name in day
        r = orig_mark(name, present)
        try:
            if was_absent == (not present):
                return r                               # no cambió nada
            cur, d0 = r[0], datetime.date.today().isoformat()

            def back():
                lst = aula.data.setdefault("asistencia", {}).setdefault(cur, {}).setdefault(d0, [])
                if was_absent and name not in lst:
                    lst.append(name)
                elif not was_absent and name in lst:
                    lst.remove(name)
                aula.save()
            bitacora.add(f"{'Falla' if not present else 'Presente'}: {name} ({cur})", "asistencia", undo=back,
                         group=("asis", cur, present), group_text=lambda n: f"{'Fallas' if not present else 'Presentes'}: {n} estudiantes ({cur})")
        except Exception:
            pass
        return r

    def resolve(aid, ok, por="voz", now=None):
        i = orig_resolve(aid, ok, por, now)
        if i:
            bitacora.add(("Aprobaste: " if ok else "Rechazaste: ") + i["titulo"][:120], "aprobacion")
        return i

    seguimiento.add, informes.add, notas.add, aula.mark, aprobaciones.resolve = grade, obs, note, mark, resolve


def journal_file(path):
    """Un archivo nuevo de Jarvis: se puede «deshacer» llevándolo a la papelera de Jarvis (no se borra)."""
    if any(e["tipo"] == "archivo" and e.get("ruta") == path for e in bitacora.entries[-20:]):
        return

    def to_trash():
        if not os.path.exists(path):
            return
        bin_dir = os.path.join(J.settings["output_dir"], "Papelera de Jarvis")
        os.makedirs(bin_dir, exist_ok=True)
        shutil.move(path, os.path.join(bin_dir, os.path.basename(path)))
        J.generated_files.discard(path)
    e = bitacora.add(f"Creé «{os.path.basename(path)}»", "archivo", undo=to_trash)
    e["ruta"] = path


def journal_list():
    return [{k: e[k] for k in ("id", "hora", "texto", "tipo", "deshecho", "puede", "n")} for e in reversed(bitacora.today())][:60]


@J.socketio.on("journal")
def handle_journal(data=None):
    return {"items": J.journal_list()}


@J.socketio.on("journal_undo")
def handle_journal_undo(data=None):
    ok, msg = bitacora.undo(int((data or {}).get("id") or 0))
    if ok:
        J.log_terminal(msg, "DESHACER")
    J.socketio.emit("journal", {"items": J.journal_list()})
    return {"ok": ok, "msg": msg, "items": J.journal_list()}


_UNDO_RE = re.compile(r"^(?:jarvis\s+)?(?:deshaz(?:lo)?|deshacer|deshaz eso|deshaz lo ultimo|deshaz la ultima accion|devuelve(?:lo)? como estaba|"
                      r"anula lo ultimo|cancela lo ultimo que hiciste)\b")
_DID_RE = re.compile(r"\bque (?:has hecho|hiciste|me hiciste) hoy\b|\blo que hiciste hoy\b|\bque cosas hiciste\b")


def journal_voice(text, t):
    if _DID_RE.search(t):
        J.reply(bitacora.spoken(bitacora.today()), "HOY HICE")
        return True
    if not _UNDO_RE.match(t):
        return False
    e = bitacora.last_undoable()
    if not e:
        J.reply("No tengo nada reciente que pueda deshacer.", "DESHACER")
        return True
    ok, msg = bitacora.undo(e["id"])
    J.socketio.emit("journal", {"items": J.journal_list()})
    J.reply(msg + ".", "DESHACER")
    return True


@J.socketio.on("hud_text_size")
def handle_hud_text_size(data=None):
    v = str((data or {}).get("size") or "")
    if v not in ("normal", "grande", "proyector"):
        order = ["normal", "grande", "proyector"]
        v = order[(order.index(J.settings.get("hud_text_size", "normal")) + 1) % 3]
    J.apply_settings({"hud_text_size": v})
    return {"size": J.settings.get("hud_text_size", v)}


# ============================================================================ TODO JUNTO PARA EL PANEL
def hudpro_extras(now, out):
    out["momento"] = J.moment_card(now, out)
    out["bandeja"] = J.inbox(now)
    out["hice"] = J.journal_list()[:6]
    c = out.get("clase") or {}
    lc = out.get("en_clase") or {}
    out["orbe"] = {"progreso": (c.get("progreso") if c.get("ahora") else None), "pendientes": len(out["bandeja"]),
                   "clase": (lc.get("clase") or {}).get("curso") or (out["momento"].get("curso") if out["momento"]["id"] == "clase" else ""),
                   "falta": c.get("falta")}
    out["proyectando"] = bool(proj["now"])
    return out


def hudpro_start():
    J.install_journal()


__all__ = ['MATH_RULE', '_DID_RE', '_mins_to', '_PROJ_THIS', '_UNDO_RE', '_course_base', '_installed', '_remove_obj', '_roster', '_snooze', '_topic_for', '_word_from',
           'bitacora', 'handle_hud_text_size', 'handle_inbox_snooze', 'handle_journal', 'handle_journal_undo', 'handle_msg_action', 'handle_project_clear', 'handle_project_show',
           'handle_projector_now', 'handle_roster_act', 'hudpro_extras', 'hudpro_start', 'inbox', 'install_journal', 'journal_file', 'journal_list',
           'journal_voice', 'mathtext', 'moment_card', 'momento', 'proj', 'project_show', 'beam_voice', 'smart_palette']
