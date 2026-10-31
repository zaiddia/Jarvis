"""7.5: herramientas por significado, habilidades de la comunidad (SKILL.md) e investigación con fuentes.

  · selector.py: la IA solo ve las acciones y conectores que tienen que ver con lo que pides.
  · guias.py: importa habilidades de OpenClaw/Hermes/Claude (solo su texto), con revisor de seguridad.
  · investigar.py: «investiga a fondo X» → informe en Word con cada dato citado y la lista de fuentes.
Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import base64
import datetime
import json
import os
import re
import threading
import time
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor

import buscar
import diario
import guias
import investigar
import recuerdos
import selector
import skills
from nucleo import J

# ============================================================================ 3. HERRAMIENTAS POR SIGNIFICADO
ALWAYS_TOOLS = ("abrir_app", "buscar_web", "youtube", "volumen", "multimedia", "cerrar_app")
tool_stats = {"last": (0, 0)}


def router_catalog(prompt):
    """Las acciones (y conectores) que verá la IA para esta orden, ya en texto para el enrutador."""
    items = [(s.name, f"{s.name} {s.desc} {s.args}") for s in skills.REGISTRY.values() if not s.dangerous]
    lines = {s.name: s.describe() for s in skills.REGISTRY.values() if not s.dangerous}
    for line in J.mcp_hub.catalog(limit=400):
        m = re.match(r"^- (mcp__[\w-]+__[\w.-]+)\(", line)
        if m:
            items.append((m.group(1), line[2:].replace("_", " ")))
            lines[m.group(1)] = line
    total = len(items)
    chosen = [i for i, _ in items]
    # Las acciones propias (35, cortas) van siempre: así «está muy oscuro» sigue encontrando el brillo aunque no haya
    # modelo de significado. Lo que se elige son los conectores, que pueden ser cientos.
    own = [i for i, _ in items if not i.startswith("mcp__")]
    ext = [(i, t) for i, t in items if i.startswith("mcp__")]
    if J.settings["tool_select"] and len(ext) > J.settings["tool_select_max"]:
        tag = J.memory_embed_tag()
        picked = selector.choose(prompt, ext, k=J.settings["tool_select_max"], embed=J.memory_embed if tag else None,
                                 tag="t-" + tag if tag else "")
        chosen = own + picked
    tool_stats["last"] = (len(chosen), total)
    if len(chosen) < total:
        J.log_terminal(f"Herramientas para la IA: {len(chosen)} de {total}.", "IA")
    text = "\n".join(lines[i] for i in chosen)
    if any(i.startswith("mcp__") for i in chosen):
        text += ("\n(Las acciones mcp__… son conectores: «args» lleva los campos que pide cada una; los marcados con * "
                 "son obligatorios.)")
    return text


# ============================================================================ 4. HABILIDADES DE LA COMUNIDAD (SKILL.md)
_pending = {}                   # código -> habilidad revisada, esperando «Instalar»
GUIDE_MIN_WORDS = 2


def guides_for(question, limit=1):
    """Las guías que encajan con la pregunta (por nombre, por palabras o por significado)."""
    gs = guias.listing()
    if not gs or not question:
        return []
    q = recuerdos.norm(question)
    qt = set(recuerdos.tokens(question))
    picked = []
    for g in gs:
        name_words = [w for w in recuerdos.norm(g["nombre"].replace("-", " ")).split() if len(w) > 3]
        if name_words and all(w in q for w in name_words):
            picked.append((2.0, g))
            continue
        overlap = len(qt & set(recuerdos.tokens(g["nombre"].replace("-", " ") + " " + g["descripcion"])))
        if overlap >= GUIDE_MIN_WORDS:
            picked.append((0.5 + 0.1 * overlap, g))
    tag = J.memory_embed_tag()
    if not picked and tag:
        try:
            vecs = J.memory_embed([question] + [g["descripcion"][:500] for g in gs])
            for g, v in zip(gs, vecs[1:]):
                sim = recuerdos.cosine(vecs[0], v)
                if sim >= 0.62:
                    picked.append((sim, g))
        except Exception:
            pass
    picked.sort(key=lambda x: -x[0])
    return [g for _, g in picked[:limit]]


def guides_ctx(question):
    gs = J.guides_for(question)
    if not gs:
        return ""
    J.log_terminal("Uso la habilidad «" + "», «".join(g["nombre"] for g in gs) + "».", "HABILIDAD")
    return "\n\n" + "\n\n".join(guias.for_ai(g) for g in gs)


def _fetch(url, binary=False, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": f"Jarvis/{J.VERSION}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(guias.MAX_ZIP + 1)
    if len(data) > guias.MAX_ZIP:
        raise guias.ImportError_("El archivo es demasiado grande.")
    return data if binary else data.decode("utf-8", "replace")


def fetch_guide(url):
    """{ruta: bytes} desde un enlace: SKILL.md directo, un .zip o una carpeta de GitHub."""
    url = url.strip()
    if not url.startswith("https://"):
        raise guias.ImportError_("El enlace debe empezar por https://")
    gh = guias.github_api_url(url)
    if gh:
        api, _ = gh
        files = {}

        def walk(api_url, prefix, depth):
            items = json.loads(J._fetch(api_url))
            if isinstance(items, dict):
                items = [items]
            for it in items[:60]:
                name = prefix + it.get("name", "")
                if it.get("type") == "dir" and depth < 1:
                    walk(it["url"], name + "/", depth + 1)
                elif it.get("type") == "file":
                    if name.lower().endswith(guias.TEXT_EXT) and it.get("size", 0) <= guias.MAX_MD * 2:
                        files[name] = J._fetch(it["download_url"], binary=True)
                    else:
                        files[name] = b""
        walk(api, "", 0)
        return files
    if url.lower().endswith(".zip"):
        return guias.from_zip(J._fetch(url, binary=True))
    return {"SKILL.md": J._fetch(url, binary=True)}


@J.socketio.on("guias_list")
def handle_guias_list(data=None):
    return {"guias": [{k: g[k] for k in ("slug", "nombre", "descripcion", "origen", "revision")} for g in guias.listing()]}


@J.socketio.on("guias_preview")
def handle_guias_preview(data=None):
    """Revisa una habilidad (archivo .md/.zip en base64, o un enlace) sin instalarla."""
    d = data or {}
    try:
        if d.get("url"):
            files, origen = J.fetch_guide(str(d["url"])), str(d["url"])[:300]
        else:
            raw = base64.b64decode(str(d.get("b64", "")).split(",")[-1])
            name = str(d.get("name", "SKILL.md"))
            files = guias.from_zip(raw) if name.lower().endswith(".zip") else {name if name.lower().endswith(".md") else "SKILL.md": raw}
            origen = name
        prep = guias.prepare(files, origen)
    except guias.ImportError_ as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"No pude leer la habilidad: {e}"}
    code = uuid.uuid4().hex[:12]
    _pending.clear()
    _pending[code] = prep
    exists = any(g["slug"] == prep["slug"] for g in guias.listing())
    return {"ok": True, "code": code, "nombre": prep["meta"]["name"], "descripcion": prep["meta"].get("description", ""),
            "revision": prep["scan"], "reemplaza": exists, "chars": len(prep["body"])}


@J.socketio.on("guias_install")
def handle_guias_install(data=None):
    prep = _pending.pop(str((data or {}).get("code", "")), None)
    if not prep:
        return {"ok": False, "error": "Vuelve a elegir la habilidad."}
    try:
        g = guias.save(prep)
    except guias.ImportError_ as e:
        return {"ok": False, "error": str(e)}
    J.log_terminal(f"Habilidad de la comunidad instalada: {g['nombre']} (riesgo {g['revision']['nivel']}).", "HABILIDAD")
    return {"ok": True, **handle_guias_list()}


@J.socketio.on("guias_delete")
def handle_guias_delete(data=None):
    guias.delete(str((data or {}).get("slug", "")))
    return {"ok": True, **handle_guias_list()}


@J.socketio.on("guias_folder")
def handle_guias_folder(data=None):
    if J.IS_WIN and guias._dir:
        os.makedirs(guias._dir, exist_ok=True)
        os.startfile(guias._dir)


EXAMPLES_DIR = J.get_resource_path("habilidades_comunidad")


def guides_start():
    guias.configure(J.CONFIG_DIR)
    selector.configure(os.path.join(J.CONFIG_DIR, "historial"))
    # la primera vez: las habilidades de ejemplo (formato SKILL.md)
    if not os.path.isdir(guias._dir) and os.path.isdir(EXAMPLES_DIR):
        os.makedirs(guias._dir, exist_ok=True)
        for name in os.listdir(EXAMPLES_DIR):
            p = os.path.join(EXAMPLES_DIR, name, "SKILL.md")
            if os.path.isfile(p):
                with open(p, encoding="utf-8") as f:
                    try:
                        prep = guias.prepare({"SKILL.md": f.read().encode("utf-8")}, "ejemplo de Jarvis")
                        guias.save(prep)
                    except guias.ImportError_:
                        pass


# ============================================================================ 5. INVESTIGACIÓN CON FUENTES
_RESEARCH_RE = re.compile(
    r"^(?:oye |jarvis )?(?:por favor )?(?:investiga(?:me)?|investigame)\b(?! en (?:mi|el) (?:pc|equipo|computador))"
    r"|\b(?:haz(?:me)?|preparame|necesito) (?:una )?investigacion\b|\binvestigacion (?:completa |a fondo |con fuentes )?(?:sobre|de|acerca)\b"
    r"|\b(?:haz(?:me)?|preparame) un informe (?:completo |con fuentes )?(?:sobre|de|acerca)\b|\binvestiga a fondo\b")
_RESEARCH_STRIP = re.compile(
    r"^(?:oye |jarvis )?(?:por favor )?(?:investiga(?:me)?(?: a fondo)?|(?:haz(?:me)?|pr[eé]parame|necesito) (?:una )?investigaci[oó]n"
    r"(?: completa| a fondo| con fuentes)?|(?:haz(?:me)?|pr[eé]parame) un informe(?: completo| con fuentes)?)\s*"
    r"(?:(?:sobre|de|del|acerca de|que|qu[eé]|lo de)\s+)?", re.I)
research_state = {"busy": False}


def research_topic(text):
    q = _RESEARCH_STRIP.sub("", text.strip())
    q = re.sub(r"\s*(?:,\s*)?(?:y\s+)?(?:hazme|haz|dame|preparame|con) (?:un |el )?(?:documento|informe|word|resumen)\b.*$", "", q, flags=re.I)
    q = re.sub(r"\b(?:en internet|en la web|con fuentes|a fondo)\b", "", q, flags=re.I)
    return q.strip(" ,.:¿?¡!")


def research_voice(text, t):
    if not _RESEARCH_RE.search(t):
        return False
    topic = research_topic(text)
    if len(topic) < 3:
        J.reply("¿Sobre qué quieres que investigue?", "INVESTIGA")
        return True
    if getattr(J._tl, "capture", None) is not None:      # desde Telegram, MCP o una tarea: se espera el resultado
        J.reply(J.research(topic, sync=True), "INVESTIGA")
        return True
    J.research(topic)
    return True


def _sources_for(plan):
    groups = []
    for q in plan:
        res = []
        for lite in (False, True):
            try:
                res = buscar.parse_results(J._get_text(buscar.search_url(q, lite=lite), timeout=12), limit=6)
            except Exception as e:
                J.log_terminal(f"Investigación, búsqueda «{q}»: {e}", "AVISO")
            if res:
                break
        groups.append(res)
    return investigar.merge_results(groups)


def _read_page(s):
    try:
        s["texto"] = investigar.page_text(J._get_text(s["url"], timeout=10)[:600000])
    except Exception:
        s["texto"] = ""
    if len(s["texto"]) < 120:
        s["texto"] = s.get("resumen", "")
    return s


def _save_report(report, sources, topic, folder=None):
    folder = folder or os.path.join(J.settings["output_dir"], "Investigaciones")
    os.makedirs(folder, exist_ok=True)
    base = os.path.join(folder, f"Investigación - {investigar.safe_filename(topic)} - {datetime.date.today():%Y-%m-%d}")
    if J.Document is not None:
        doc = J.Document()
        doc.add_heading(report["titulo"], 0)
        doc.add_paragraph(f"Investigación de Jarvis · {datetime.date.today():%d/%m/%Y} · tema: {topic}").italic = True
        if report["resumen"]:
            p = doc.add_paragraph()
            p.add_run("Resumen. ").bold = True
            p.add_run(report["resumen"])
        for title, lines in report["secciones"]:
            doc.add_heading(title, 1)
            for ln in lines:
                s = ln.strip()
                if s.startswith(("-", "•", "*")):
                    doc.add_paragraph(s.lstrip("-•* "), style="List Bullet")
                else:
                    doc.add_paragraph(s)
        doc.add_heading("Fuentes", 1)
        for i, s in enumerate(sources, 1):
            doc.add_paragraph(f"[{i}] {s['titulo']} — {s['fuente']}. {s['url']}")
        path = base + ".docx"
        doc.save(path)
    else:
        path = base + ".html"
        with open(path, "w", encoding="utf-8") as f:
            f.write(investigar.to_html(report, sources, topic))
    return path


def research(topic, sync=False, folder=None, full=False):
    """Investiga a fondo. sync=True: espera y devuelve el texto (Telegram, tareas, MCP).
    folder: dónde guardar el informe; full=True (con sync): devuelve {"msg", "path", "resumen"} (proyectos)."""
    if J.is_offline():
        msg = "Ahora no hay internet, así que no puedo investigar."
        if sync:
            return msg
        J.reply(msg, "INVESTIGA")
        return msg
    if research_state["busy"]:
        msg = "Ya estoy haciendo una investigación; espera a que termine."
        if not sync:
            J.reply(msg, "INVESTIGA")
        return msg
    if not sync:
        J.reply(f"Investigo a fondo sobre {topic}: busco, leo las fuentes y te preparo un informe con citas. "
                "Me toma uno o dos minutos; te aviso cuando esté.", "INVESTIGA")
    out = {}

    def work():
        research_state["busy"] = True
        t0 = time.time()
        try:
            ai_ok = J.state.get("ai") == "ok"
            plan = investigar.default_plan(topic)
            if ai_ok:
                try:
                    plan = investigar.parse_plan(J.ai_chat([{"role": "user", "content": investigar.plan_prompt(topic)}],
                                                           json_mode=True, max_tokens=250), topic)
                except Exception:
                    pass
            sources = J._sources_for(plan)
            if not sources:
                out["msg"] = f"No encontré fuentes en internet sobre {topic}. Prueba con otras palabras."
                return
            with ThreadPoolExecutor(max_workers=6) as ex:
                sources = list(ex.map(J._read_page, sources))
            report = None
            if ai_ok:
                try:
                    txt = J.ai_chat([{"role": "user", "content": investigar.report_prompt(topic, sources)}], max_tokens=2400)
                    report = investigar.parse_report(txt, topic)
                except Exception as e:
                    J.log_terminal(f"Investigación: la IA no pudo escribir el informe ({e}).", "AVISO")
            if not report or (not report["resumen"] and not report["secciones"]):
                report = investigar.fallback_report(topic, sources)
            path = J._save_report(report, sources, topic, folder)
            out["resumen"] = (report["resumen"] + "\n" + "\n".join(
                f"{t}: " + " ".join(ls)[:400] for t, ls in report["secciones"]))[:3000]
            J.generated_files.add(path)
            opened = J._open_doc(path) if not folder else False
            where = "Documentos, carpeta Jarvis, Investigaciones" + ("" if opened else f" ({os.path.basename(path)})")
            out["msg"] = investigar.spoken_summary(report, len(sources), where)
            out["path"] = path
            diario.log("busqueda", f"investigación: {topic}")
            J.log_terminal(f"Investigación «{topic}»: {len(sources)} fuentes, {time.time() - t0:.0f} s → {path}", "INVESTIGA")
        except Exception as e:
            out["msg"] = f"No pude terminar la investigación: {e}"
        finally:
            research_state["busy"] = False
        if not sync:
            J.notify(out["msg"], "INVESTIGA")
            if out.get("path"):
                J.card("aviso", "Investigación lista", topic, "📄", secs=10)

    if sync:
        work()
        return out if full else out.get("msg", "")
    J.start_job("Investigando", work, "investigacion")
    return ""


@J.socketio.on("research_folder")
def handle_research_folder(data=None):
    folder = os.path.join(J.settings["output_dir"], "Investigaciones")
    if J.IS_WIN:
        os.makedirs(folder, exist_ok=True)
        os.startfile(folder)


def tools_start():
    J.guides_start()


__all__ = [
    'ALWAYS_TOOLS', 'EXAMPLES_DIR', 'GUIDE_MIN_WORDS', '_RESEARCH_RE', '_RESEARCH_STRIP', '_fetch', '_pending',
    '_read_page', '_save_report', '_sources_for', 'fetch_guide', 'guides_ctx', 'guides_for', 'guides_start',
    'handle_guias_delete', 'handle_guias_folder', 'handle_guias_install', 'handle_guias_list', 'handle_guias_preview',
    'handle_research_folder', 'research', 'research_state', 'research_topic', 'research_voice', 'router_catalog',
    'tool_stats', 'tools_start',
]
