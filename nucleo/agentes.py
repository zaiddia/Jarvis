"""7.6: centro de aprobaciones y proyectos de varios pasos con sub-agentes.

  · Aprobaciones (aprobaciones.py): lo importante que Jarvis va a hacer por su cuenta te lo pregunta primero; se
    responde por voz («sí», «no 3»), en el HUD, el reactor, el panel del celular o Telegram. Queda en el registro.
  · Proyectos (proyectos.py): «prepárame la semana de 7A sobre fracciones» → plan de pasos → lo apruebas → los
    sub-agentes hacen cada paso (en paralelo cuando se puede) y todo queda en una carpeta.
Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import json
import os
import re
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

import aprobaciones
import aula
import diario
import oficina
import proyectos
from nucleo import J

# ============================================================================ CENTRO DE APROBACIONES
_callbacks = {}            # id -> (al aprobar, al rechazar)
BARE_WINDOW = 180          # «sí» a secas vale para la última pedida en los últimos 3 minutos


def request_approval(tipo, titulo, detalle="", on_ok=None, on_no=None, ttl=900, say=None):
    """Pide permiso. on_ok/on_no se ejecutan (en otro hilo) al responder. Devuelve la aprobación."""
    item = aprobaciones.add(tipo, titulo, detalle, ttl)
    _callbacks[item["id"]] = (on_ok, on_no)
    J.notice_add(f"Por aprobar: {titulo}", "aprobar", "APROBAR")    # 9.2: campana del HUD
    remote = getattr(J._tl, "remote", False)
    msg = say or f"{titulo}. ¿Lo apruebas? Di «sí» o «no»."
    J.reply(msg + ("" if not remote else f" (Responde «sí {item['id']}» o «no {item['id']}».)"), "APROBAR")
    J.orb_feed.update(alert_seq=J.orb_feed["alert_seq"] + 1, alert=f"Por aprobar: {titulo}"[:300])
    J.socketio.emit("approvals", {"pending": aprobaciones.pending()})
    if J.telegram_ready() and J.settings["approvals_telegram"] and not remote:
        threading.Thread(target=J.telegram_send, daemon=True,
                         args=(f"🟡 Aprobación {item['id']}: {titulo}\n{detalle[:800]}\n\nResponde «sí {item['id']}» o «no {item['id']}».",)).start()
    elif J.whatsapp_ready() and J.settings["approvals_telegram"] and not remote:
        threading.Thread(target=J.whatsapp_send, daemon=True,
                         args=(f"🟡 Jarvis espera tu aprobación: {titulo}. Respóndela por voz, en el panel del celular o en Ajustes.",)).start()
    return item


def resolve_approval(aid, ok, por="voz"):
    item = aprobaciones.resolve(aid, ok, por)
    if not item:
        return None
    on_ok, on_no = _callbacks.pop(aid, (None, None))
    fn = on_ok if ok else on_no
    if fn:
        threading.Thread(target=fn, daemon=True, name=f"aprobacion-{aid}").start()
    J.socketio.emit("approvals", {"pending": aprobaciones.pending()})
    return item


_YES_ID = re.compile(r"^(?:si|aprueba\w*|apruebo|dale|hazlo|adelante|ok|okay|de acuerdo|claro)(?:\s+(?:la|el|numero|#))?\s*(\d{1,2})?\s*$")
_NO_ID = re.compile(r"^(?:no|rechaza\w*|rechazo|cancela\w*|mejor no)(?:\s+(?:la|el|numero|#))?\s*(\d{1,2})?\s*$")


def approvals_answer(t):
    """«sí», «sí 3», «aprueba la 3», «no 2». True si respondió una aprobación."""
    m_yes, m_no = _YES_ID.match(t), _NO_ID.match(t)
    m = m_yes or m_no
    if not m:
        return False
    via = getattr(J._tl, "via", None)
    if via in ("enlace", "mcp", "tarea"):              # solo tú apruebas: no un enlace, otra IA ni una tarea
        if aprobaciones.pending():
            J.log_terminal(f"Intento de aprobar desde {via}: ignorado.", "AVISO")
        return False
    if m.group(1):
        item = aprobaciones.get(int(m.group(1)))
        if not item or item["estado"] != "pendiente":
            J.reply(f"No tengo ninguna aprobación pendiente con el número {m.group(1)}.", "APROBAR")
            return True
    else:
        item = aprobaciones.latest()
        if not item or time.time() - item["creada"] > BARE_WINDOW:
            return False                               # «sí» a secas: no es para mí
    por = "celular" if getattr(J._tl, "remote", False) else "voz"
    ok = bool(m_yes)
    resolve_approval(item["id"], ok, por)
    J.reply(("Aprobado: " if ok else "Rechazado: ") + item["titulo"] + ".", "APROBAR")
    return True


_APPROVALS_LIST = re.compile(r"\b(?:que tengo (?:por|para|pendiente de) aprobar|aprobaciones pendientes|que (?:me )?falta (?:por )?aprobar)\b")
_HISTORY = re.compile(r"\bque (?:has hecho|hiciste) (?:por tu cuenta|solo|tu solo|sin mi)\b|\bregistro de acciones\b")


def approvals_voice(text, t):
    if _APPROVALS_LIST.search(t):
        p = aprobaciones.pending()
        if not p:
            J.reply("No tienes nada pendiente de aprobar.", "APROBAR")
        else:
            J.reply(f"Tienes {len(p)} por aprobar: " + "; ".join(f"la {i['id']}, {i['titulo']}" for i in p[-5:]) +
                    ". Di «sí» con el número para aprobarla.", "APROBAR")
        return True
    if _HISTORY.search(t):
        days = 7 if re.search(r"\bsemana\b", t) else 1
        J.reply(aprobaciones.spoken_history(aprobaciones.history(days)), "APROBAR")
        return True
    return False


def _approvals_worker():
    while True:
        time.sleep(30)
        try:
            for item in aprobaciones.expire():
                _callbacks.pop(item["id"], None)
                J.log_terminal(f"Nadie aprobó «{item['titulo']}»: no lo hago.", "APROBAR")
        except Exception as e:
            J.log_terminal(f"Aprobaciones: {e}", "AVISO")


# ============================================================================ PROYECTOS CON SUB-AGENTES
project_run = {"st": None, "cancel": False, "busy": False}


def _docx_text(path, title, text):
    doc = J.Document()
    doc.add_heading(title, 0)
    for block in re.split(r"\n{2,}", str(text).strip()):
        b = block.strip()
        if b.startswith("#"):
            doc.add_heading(b.lstrip("# ").strip(), 1)
        elif all(ln.strip().startswith(("-", "•", "*")) for ln in b.splitlines()):
            for ln in b.splitlines():
                doc.add_paragraph(ln.strip().lstrip("-•* "), style="List Bullet")
        else:
            doc.add_paragraph(b)
    doc.save(path)
    return path


def run_step(st, step):
    """Un sub-agente: hace un paso y devuelve {"archivo", "resumen"}. Lanza excepción si falla."""
    folder = st["carpeta"]
    os.makedirs(folder, exist_ok=True)
    ctx = proyectos.context_for(st, step)
    pedido = step["pedido"] + (f"\n\nUsa también lo que salió de los pasos anteriores:\n{ctx}" if ctx else "")
    tipo = step["tipo"]
    if tipo == "investigar":
        out = J.research(step["pedido"], sync=True, folder=folder, full=True)
        if not out.get("path"):
            raise RuntimeError(out.get("msg") or "no encontré fuentes")
        return {"archivo": out["path"], "resumen": out.get("resumen", "")}
    if tipo in aula.KINDS:
        prompt = aula.build_prompt(tipo, pedido, aula.detect_count(step["pedido"]), "", "") + J.lessons_ctx()
        last = None
        for _ in range(2):
            try:
                m = aula.validate(tipo, J._extract_json(J.ai_chat([{"role": "user", "content": prompt}], json_mode=True,
                                                                   max_tokens=8000)), step["pedido"])
                if tipo in ("quiz", "saber"):
                    J.banco.add_quiz(m)
                    J.remember_quiz(m)
                path = aula.build_docx(tipo, m, folder, J.Document, J.settings["aula_docente"],
                                       J.settings["aula_institucion"], aula.data.get("activo", ""))
                return {"archivo": path, "resumen": json.dumps(m, ensure_ascii=False)[:2500]}
            except (ValueError, TypeError) as e:
                last = e
        raise RuntimeError(f"la IA no devolvió un material válido ({last})")
    if tipo == "imagen":
        path = J.make_image(step["pedido"], folder)
        return {"archivo": path, "resumen": f"Imagen: {step['pedido']}"}
    if tipo == "presentacion":
        grade = oficina.detect_grade(J.normalize(step["pedido"]))
        prompt = oficina.pptx_prompt(pedido, 8, grade)
        m = oficina.pptx_validate(J._extract_json(J.ai_chat([{"role": "user", "content": prompt}], json_mode=True,
                                                            max_tokens=6000)), step["pedido"])
        path = oficina.build_pptx(m, folder, J.settings["aula_docente"], J.settings["aula_institucion"], grade)
        return {"archivo": path, "resumen": json.dumps(m, ensure_ascii=False)[:1500]}
    # texto libre
    txt = J.ai_chat([{"role": "system", "content": J.settings["system_prompt"] + J._user_ctx(step["pedido"])},
                     {"role": "user", "content": pedido + "\n\nEscríbelo completo, listo para usar, en español. Usa "
                      "«## » para los subtítulos y «- » para las viñetas. Sin comentarios sobre lo que haces."}],
                    max_tokens=3000)
    path = os.path.join(folder, proyectos.safe_name(step["titulo"]) + ".docx")
    return {"archivo": _docx_text(path, step["titulo"], txt), "resumen": txt[:2500]}


def _card(st):
    titles = [p["titulo"] for p in st["pasos"]]
    idx = next((i for i, p in enumerate(st["pasos"]) if p["estado"] == "en marcha"),
               sum(1 for p in st["pasos"] if p["estado"] == "hecho"))
    J.card("rutina", st["nombre"], proyectos.progress_text(st), "◆", secs=30, steps=titles, step=min(idx, len(titles) - 1))


def run_project(st):
    """Lleva el proyecto hasta el final: los pasos listos, en paralelo (como mucho N a la vez)."""
    if project_run["busy"]:
        J.reply("Ya estoy con otro proyecto; espera a que termine o di «cancela el proyecto».", "PROYECTO")
        return
    project_run.update(st=st, cancel=False, busy=True)
    st["estado"] = "en marcha"
    for p in st["pasos"]:
        if p["estado"] == "en marcha":                 # se había quedado a medias: se repite
            p["estado"] = "pendiente"
    proyectos.save(st)
    aprobaciones.log("hecha", texto=f"empecé el proyecto «{st['nombre']}»")
    workers = max(1, min(4, int(J.settings["project_parallel"])))
    try:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="subagente") as ex:
            running = {}
            while True:
                if project_run["cancel"]:
                    break
                for step in proyectos.ready_steps(st):
                    if len(running) >= workers:
                        break
                    step.update(estado="en marcha", inicio=time.time())
                    running[ex.submit(J.run_step, st, step)] = step
                    J.log_terminal(f"Sub-agente: {step['titulo']}", "PROYECTO")
                proyectos.save(st)
                _card(st)
                if not running:
                    break
                done, _ = wait(list(running), timeout=5, return_when=FIRST_COMPLETED)
                for fut in done:
                    step = running.pop(fut)
                    try:
                        res = fut.result()
                        step.update(estado="hecho", archivo=res.get("archivo", ""), resumen=res.get("resumen", ""),
                                    fin=time.time())
                        J.generated_files.add(step["archivo"])
                    except Exception as e:
                        step.update(estado="error", error=str(e)[:300], fin=time.time())
                        J.log_terminal(f"Paso «{step['titulo']}»: {e}", "AVISO")
                    proyectos.save(st)
        if project_run["cancel"]:
            st["estado"] = "cancelado"
            msg = f"Cancelé el proyecto «{st['nombre']}». Lo que ya estaba hecho quedó en su carpeta."
        else:
            st.update(estado="terminado", terminado=time.time())
            _write_index(st)
            msg = proyectos.summary_text(st)
            if J.IS_WIN and J.settings["aula_open_docs"] and os.path.isdir(st["carpeta"]):
                try:
                    os.startfile(st["carpeta"])
                except OSError:
                    pass
        proyectos.save(st)
        aprobaciones.log("hecha", texto=msg)
        diario.log("orden", f"proyecto: {st['nombre']}")
        J.notify(msg, "PROYECTO")
        _card(st)
    finally:
        project_run.update(busy=False)


def _write_index(st):
    lines = [f"Proyecto: {st['nombre']}", f"Pedido: {st['pedido']}", ""]
    for i, p in enumerate(st["pasos"], 1):
        mark = {"hecho": "✓", "error": "✗", "omitido": "–"}.get(p["estado"], "·")
        lines.append(f"{mark} {i}. {p['titulo']}" + (f"  →  {os.path.basename(p['archivo'])}" if p["archivo"] else "")
                     + (f"  ({p['error']})" if p["error"] else ""))
    try:
        os.makedirs(st["carpeta"], exist_ok=True)
        with open(os.path.join(st["carpeta"], "Resumen del proyecto.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except OSError:
        pass


def plan_project(goal):
    """Planea con la IA y pide aprobación para hacerlo. Devuelve el plan (o None)."""
    try:
        raw = J.ai_chat([{"role": "user", "content": proyectos.plan_prompt(goal, J._user_ctx(goal)[:1200])}],
                        json_mode=True, max_tokens=1500)
        plan = proyectos.validate_plan(J._extract_json(raw), goal)
    except Exception as e:
        J.reply(f"No pude planear el proyecto: {getattr(e, 'why', e)}. Prueba a decirlo con más detalle.", "PROYECTO")
        return None

    def go():
        st = proyectos.new(goal, plan, J.settings["output_dir"])
        J.reply(f"Empiezo el proyecto «{plan['nombre']}». Te aviso cuando termine; pregúntame «¿cómo va el proyecto?» "
                "cuando quieras.", "PROYECTO")
        J.run_project(st)
    J.request_approval("proyecto", f"Hacer el proyecto «{plan['nombre']}» ({len(plan['pasos'])} pasos)",
                       proyectos.spoken_plan(plan), on_ok=go,
                       on_no=lambda: J.reply("Vale, no lo hago. Puedes pedírmelo de otra forma.", "PROYECTO"),
                       say=proyectos.spoken_plan(plan) + " ¿Lo hago así? Di «sí» o «no».")
    return plan


_PRJ_STATUS = re.compile(r"\b(?:como va|como vas con|en que va|estado de)l? (?:el )?proyecto\b")
_PRJ_CANCEL = re.compile(r"\b(?:cancela|deten|detén|para|parar|detener)\s+(?:el )?proyecto\b")
_PRJ_RESUME = re.compile(r"\b(?:continua|sigue|retoma|reanuda)\s+(?:con )?(?:el )?proyecto\b")


def project_voice(text, t):
    if _PRJ_STATUS.search(t):
        st = project_run["st"] if project_run["busy"] else (proyectos.load_all() or [None])[-1]
        J.reply(proyectos.progress_text(st) if st else "No tengo ningún proyecto.", "PROYECTO")
        return True
    if _PRJ_CANCEL.search(t):
        if project_run["busy"]:
            project_run["cancel"] = True
            J.reply("Vale, cancelo el proyecto en cuanto terminen los pasos que están en marcha.", "PROYECTO")
        else:
            J.reply("No hay ningún proyecto en marcha.", "PROYECTO")
        return True
    if _PRJ_RESUME.search(t):
        left = proyectos.unfinished()
        if not left:
            J.reply("No tengo ningún proyecto a medias.", "PROYECTO")
        elif project_run["busy"]:
            J.reply("Ya estoy con un proyecto.", "PROYECTO")
        else:
            J.reply(f"Continúo el proyecto «{left[-1]['nombre']}».", "PROYECTO")
            threading.Thread(target=J.run_project, args=(left[-1],), daemon=True).start()
        return True
    if not proyectos.is_project(t):
        return False
    if J.state.get("ai") != "ok":
        J.reply("Para hacer proyectos de varios pasos necesito la IA conectada (Ajustes › IA).", "PROYECTO")
        return True
    if project_run["busy"]:
        J.reply("Ya estoy con un proyecto. Pregúntame cómo va, o di «cancela el proyecto».", "PROYECTO")
        return True
    if getattr(J._tl, "capture", None) is None:
        J.reply("Lo planeo y te digo los pasos antes de empezar.", "PROYECTO")
    J.plan_project(text)
    return True


def _projects_at_start():
    for st in proyectos.unfinished():
        st["estado"] = "interrumpido"
        proyectos.save(st)
    left = proyectos.unfinished()
    if left:
        st = left[-1]
        hechos = sum(1 for p in st["pasos"] if p["estado"] == "hecho")
        J.request_approval("proyecto", f"Continuar el proyecto «{st['nombre']}» ({hechos} de {len(st['pasos'])} pasos hechos)",
                           proyectos.progress_text(st), on_ok=lambda: J.run_project(st),
                           say=f"Dejé a medias el proyecto «{st['nombre']}». ¿Lo continúo? Di «sí» o «no».", ttl=3600)


# ============================================================================ AJUSTES Y CELULAR
def agent_info():
    return {"pending": aprobaciones.pending(), "history": aprobaciones.history(3)[-40:],
            "projects": [{k: p.get(k) for k in ("id", "nombre", "estado", "carpeta", "creado")} |
                         {"hechos": sum(1 for s in p["pasos"] if s["estado"] == "hecho"), "total": len(p["pasos"])}
                         for p in proyectos.load_all()[-12:]][::-1],
            "running": project_run["st"]["id"] if project_run["busy"] and project_run["st"] else ""}


@J.socketio.on("agent_info")
def handle_agent_info(data=None):
    return agent_info()


@J.socketio.on("approval_resolve")
def handle_approval_resolve(data=None):
    d = data or {}
    item = resolve_approval(int(d.get("id", 0) or 0), bool(d.get("ok")), "ajustes")
    if item:
        J.reply(("Aprobado: " if d.get("ok") else "Rechazado: ") + item["titulo"] + ".", "APROBAR")
    return {"ok": bool(item), **agent_info()}


@J.socketio.on("project_action")
def handle_project_action(data=None):
    d = data or {}
    pid, action = str(d.get("id", "")), d.get("action")
    st = next((p for p in proyectos.load_all() if p["id"] == pid), None)
    if action == "cancel" and project_run["busy"]:
        project_run["cancel"] = True
    elif action == "resume" and st and not project_run["busy"]:
        threading.Thread(target=J.run_project, args=(st,), daemon=True).start()
    elif action == "open" and st and J.IS_WIN and os.path.isdir(st["carpeta"]):
        os.startfile(st["carpeta"])
    return agent_info()


@J.mobile_app.route("/api/aprobar", methods=["POST"])
def mobile_approve():
    J._mobile_ok()
    from flask import request
    d = request.get_json(silent=True) or {}
    item = resolve_approval(int(d.get("id", 0) or 0), bool(d.get("ok")), "celular")
    if item:
        J.reply(("Aprobado desde el celular: " if d.get("ok") else "Rechazado desde el celular: ") + item["titulo"] + ".", "APROBAR")
    return {"ok": bool(item)}


def agents_start():
    aprobaciones.configure(J.CONFIG_DIR)
    proyectos.configure(J.CONFIG_DIR)
    threading.Thread(target=J._approvals_worker, daemon=True).start()
    threading.Timer(15.0, J._projects_at_start).start()


__all__ = [
    'BARE_WINDOW', '_APPROVALS_LIST', '_HISTORY', '_NO_ID', '_PRJ_CANCEL', '_PRJ_RESUME', '_PRJ_STATUS', '_YES_ID',
    '_approvals_worker', '_callbacks', '_card', '_docx_text', '_projects_at_start', '_write_index', 'agent_info',
    'agents_start', 'approvals_answer', 'approvals_voice', 'handle_agent_info', 'handle_approval_resolve',
    'handle_project_action', 'mobile_approve', 'plan_project', 'project_run', 'project_voice', 'request_approval',
    'resolve_approval', 'run_project', 'run_step',
]
