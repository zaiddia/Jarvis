"""12.2: Jarvis llena las plataformas por ti (Zeti u otra), con tu aprobación.

«Pasa las notas de 7A a Zeti»: Jarvis abre la plataforma en su propio navegador (Edge o Chrome, con un perfil aparte
que recuerda tu sesión). Tú entras con tu usuario y abres la planilla; di «llénala» y Jarvis lee los campos, la IA
decide qué va en cada uno, Jarvis comprueba cada nota contra tu seguimiento y escribe solo lo que cuadra, resaltado.
«Guarda la planilla» pulsa el botón de guardar; nunca lo hace por su cuenta. Jamás escribe contraseñas.
La lógica está en llenador.py. Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import os
import queue
import re
import threading

import aula
import llenador
import seguimiento
from nucleo import J

agent = {"thread": None, "q": None, "page": None, "ctx": None, "pw": None, "curso": "", "filled": [], "busy": False}


# ============================================================================ EL NAVEGADOR DE JARVIS (un hilo propio)
def _worker():
    while True:
        fn, box = agent["q"].get()
        try:
            box["r"] = fn()
        except Exception as e:                          # se devuelve el error al que llamó
            box["e"] = e
        box["ev"].set()


def _run(fn, timeout=180):
    """Ejecuta fn en el hilo del navegador (Playwright solo admite un hilo) y espera el resultado."""
    if agent["thread"] is None or not agent["thread"].is_alive():
        agent["q"] = queue.Queue()
        agent["thread"] = threading.Thread(target=_worker, daemon=True, name="navegador-jarvis")
        agent["thread"].start()
    box = {"ev": threading.Event()}
    agent["q"].put((fn, box))
    if not box["ev"].wait(timeout):
        raise TimeoutError("el navegador no respondió a tiempo")
    if "e" in box:
        raise box["e"]
    return box.get("r")


def _agent_launch():
    from playwright.sync_api import sync_playwright
    if agent["ctx"] is not None:
        try:
            agent["ctx"].pages                           # sigue vivo
            if agent["page"] is None or agent["page"].is_closed():
                agent["page"] = agent["ctx"].pages[0] if agent["ctx"].pages else agent["ctx"].new_page()
            return agent["page"]
        except Exception:
            agent.update(ctx=None, page=None)
    if agent["pw"] is None:
        agent["pw"] = sync_playwright().start()
    prof = os.path.join(J.CONFIG_DIR, "navegador_agente")
    os.makedirs(prof, exist_ok=True)
    want = str(J.settings.get("agent_browser") or ("msedge" if J.IS_WIN else "chrome"))
    headless = bool(J.settings.get("agent_headless", False))
    tries = ([{"executable_path": want}] if os.path.isfile(want) else [{"channel": want}]) + [{"channel": "chrome"}, {"channel": "msedge"}, {}]
    last = None
    for kw in tries:
        try:
            agent["ctx"] = agent["pw"].chromium.launch_persistent_context(prof, headless=headless, viewport=None if not headless else
                                                                           {"width": 1366, "height": 860}, args=["--start-maximized"], **kw)
            break
        except Exception as e:
            last = e
    if agent["ctx"] is None:
        raise RuntimeError(f"no pude abrir el navegador ({str(last)[:120]})")
    agent["page"] = agent["ctx"].pages[0] if agent["ctx"].pages else agent["ctx"].new_page()
    return agent["page"]


def browser_open(url):
    def go():
        pg = _agent_launch()
        pg.goto(url, wait_until="domcontentloaded", timeout=60000)
        pg.bring_to_front()
        return pg.url
    return _run(go)


def browser_close():
    def stop():
        try:
            if agent["ctx"] is not None:
                agent["ctx"].close()
        finally:
            agent.update(ctx=None, page=None)
            if agent["pw"] is not None:
                try:
                    agent["pw"].stop()
                except Exception:
                    pass
                agent["pw"] = None
    if agent["thread"] is not None and agent["thread"].is_alive():
        _run(stop, 30)


def _all_frames_extract():
    """Campos de la página y de sus marcos (muchas plataformas ponen la planilla en un iframe)."""
    pg = agent["page"]
    if pg is None or pg.is_closed():
        raise RuntimeError("el navegador de Jarvis está cerrado")
    out, password, n = [], False, 0
    for fr in pg.frames:
        try:
            d = fr.evaluate(llenador.EXTRACT_JS)
        except Exception:
            continue
        password = password or d["password"]
        for c in d["campos"]:
            n += 1
            c["frame"] = fr
            c["fid"] = c["id"]
            c["id"] = f"j{n}"
            out.append(c)
    return out, password


# ============================================================================ LLENAR
def course_data(curso):
    """{estudiante: {actividad: nota, definitiva, fallas}} del curso (o «curso · asignatura»)."""
    names = list(aula.students(curso))
    names += [n for n in seguimiento.data.get(curso, {}) if n not in names]
    fallas = J._absences(curso)
    out = {}
    for n in names:
        rows = seguimiento.data.get(curso, {}).get(n, [])
        avg = seguimiento.average(curso, n) if rows else None
        vals = llenador.student_values(rows, avg, fallas.get(n, 0))
        if vals:
            out[n] = vals
    return out


def fill_page(curso):
    """Lee la planilla abierta, decide con la IA y escribe lo que se comprobó. → frase del resultado."""
    data = J.course_data(curso)
    if not data:
        return f"No tengo notas de {curso} en el seguimiento."
    campos, password = _run(_all_frames_extract)
    if password and not campos:
        return "La página pide usuario y contraseña: entra tú (yo nunca escribo contraseñas) y abre la planilla; luego di «llénala»."
    if not campos:
        return "No veo campos para llenar en esta página. Abre la planilla de notas y di «llénala»."
    comma = bool(J.settings.get("zeti_comma", True))
    plain = [{k: v for k, v in c.items() if k != "frame"} for c in campos]
    raw = J.ai_chat([{"role": "user", "content": llenador.prompt(plain, data, comma)}], json_mode=True, max_tokens=8000)
    d = J._extract_json(raw)
    ok, bad = llenador.check(d.get("asignaciones") if isinstance(d, dict) else [], plain, data, comma)
    by_id = {c["id"]: c for c in campos}
    changes = [x for x in ok if x["cambia"]]           # 12.4: lo que ya tenía otro valor no se cambia sin tu permiso
    ok = [x for x in ok if not x["cambia"]]

    def write(items=None):
        for x in (ok if items is None else items):
            c = by_id[x["campo"]]
            loc = c["frame"].locator(f'[data-jarvis-id="{c["fid"]}"]')
            if c["tag"] == "select":
                loc.select_option(label=next(o for o in c["opciones"] if llenador.norm(o) == llenador.norm(x["valor"])))
            else:
                loc.fill(x["valor"])
            loc.evaluate("(e, ch) => { e.style.outline = ch ? '3px solid #ff9f1a' : '3px solid #ffd400'; e.style.background = ch ? '#fff0d6' : '#fffbe0'; }",
                         x["cambia"])
    _run(write)
    agent["filled"] = ok
    msg = llenador.summary(ok, bad, len(data))
    if changes:
        lines = [f"{x['estudiante']} ({x['dato']}): {by_id[x['campo']]['valor']} → {x['valor']}" for x in changes]
        msg += (f" Hay {len(changes)} nota{'s' if len(changes) != 1 else ''} que ya tenía{'n' if len(changes) != 1 else ''} otro valor en la plataforma: "
                "no las cambié; te las dejé para que las apruebes.")

        def apply_changes():
            _run(lambda: write(changes))
            agent["filled"] = agent["filled"] + changes
            J.notify(f"Cambié {len(changes)} nota{'s' if len(changes) != 1 else ''} (resaltadas en naranja). Revisa y di «guarda la planilla».", "PLATAFORMA")
        J.request_approval("plataforma", f"Cambiar {len(changes)} nota{'s' if len(changes) != 1 else ''} que ya estaba{'n' if len(changes) != 1 else ''} en la "
                           f"plataforma ({curso})", "\n".join(lines[:40]), on_ok=apply_changes,
                           on_no=lambda: J.notify("Vale, dejé esas notas como estaban en la plataforma.", "PLATAFORMA"), ttl=3 * 3600, quiet=True)
    return msg


def save_page():
    """Pulsa el botón de guardar de la planilla. → frase."""
    def click():
        pg = agent["page"]
        if pg is None or pg.is_closed():
            return "El navegador de Jarvis está cerrado."
        for fr in pg.frames:
            btns = fr.locator("button, input[type=submit], input[type=button], a[role=button], a.btn")
            for i in range(min(btns.count(), 200)):
                b = btns.nth(i)
                try:
                    txt = (b.inner_text(timeout=500) or b.get_attribute("value") or "").strip()
                except Exception:
                    continue
                if llenador.SAVE_RX.match(txt) and b.is_visible():
                    b.click()
                    return f"Pulsé «{txt}». Revisa en la página que la plataforma confirme que guardó."
        return "No encontré el botón de guardar: púlsalo tú, por favor."
    return _run(click)


def _alive():
    """¿Está abierto el navegador de Jarvis con su página? (se pregunta en su propio hilo)."""
    if agent["ctx"] is None:
        return False
    try:
        return bool(_run(lambda: agent["page"] is not None and not agent["page"].is_closed(), 10))
    except Exception:
        return False


# ============================================================================ VOZ
_PF_FILL = re.compile(r"\b(?:pasa|sube|lleva|copia|llena|registra|digita)\s+(?:las\s+)?(?:notas|calificaciones|definitivas|fallas)\s+(?:de|del)\s+(.+?)\s+"
                      r"(?:a|en)\s+(?:la\s+)?(zeti|plataforma|planilla|pagina)\b")
_PF_GO = re.compile(r"^(?:jarvis\s+)?(?:llenala|llena la planilla|llena las notas|ya estoy en la planilla|listo,? llena(?:la)?|ahora llena(?:la)?)$")
_PF_SAVE = re.compile(r"^(?:jarvis\s+)?(?:guarda(?:la)?|guarda la planilla|guarda las notas|graba la planilla|ya revise,? guarda(?:la)?)$")
_PF_CLOSE = re.compile(r"\bcierra (?:el|tu) navegador\b|\bcierra el navegador de jarvis\b")
_PF_URL = re.compile(r"\babre la plataforma\s+(https?://\S+)")


def _fill_now(curso):
    if agent["busy"]:
        J.reply("Ya estoy llenando la planilla.", "PLATAFORMA")
        return
    agent["busy"] = True
    J.reply(f"Leo la planilla y la lleno con las notas de {curso}…", "PLATAFORMA")

    def work():
        try:
            msg = fill_page(curso)
        except J.AIError as e:
            msg = J.ai_error_reply(e)
        except Exception as e:
            msg = f"No pude llenar la planilla: {str(e)[:160]}"
        finally:
            agent["busy"] = False
        J.notify(msg, "PLATAFORMA")
    if getattr(J._tl, "capture", None) is not None:
        work()
    else:
        J.start_job("Llenando la planilla", work, "plataforma")


def platform_voice(text, t):
    m = _PF_URL.search(text) if _PF_URL.search(t) else None
    if m:
        try:
            J.browser_open(m.group(1).rstrip(".,"))
        except Exception as e:
            J.reply(f"No pude abrir el navegador: {e}. Instala el componente con instalar.bat.", "PLATAFORMA")
            return True
        J.reply("Abrí la plataforma en mi navegador. Entra con tu usuario y abre la planilla.", "PLATAFORMA")
        return True
    m = _PF_FILL.search(t)
    if m:
        curso = J._resolve_course(m.group(1).strip()) or ""
        if not curso:
            J.reply(f"No encuentro el curso «{m.group(1)}».", "PLATAFORMA")
            return True
        if J.state.get("ai") != "ok":
            J.reply("Para leer la planilla necesito la IA conectada.", "PLATAFORMA")
            return True
        agent["curso"] = curso
        if J._alive():
            _fill_now(curso)
            return True
        url = J.settings["zeti_url"] if m.group(2) == "zeti" or not J.settings.get("platform_url") else J.settings["platform_url"]
        try:
            J.browser_open(url)
        except Exception as e:
            J.reply(f"No pude abrir el navegador de Jarvis ({str(e)[:100]}). Si falta el componente, ejecuta instalar.bat.", "PLATAFORMA")
            return True
        J.reply(f"Abrí la plataforma en mi navegador. Entra con tu usuario (yo no escribo contraseñas), abre la planilla de {curso} y di «llénala». "
                "Yo no guardo nada hasta que me digas.", "PLATAFORMA")
        return True
    if _PF_GO.match(t) and agent["ctx"] is not None:
        if not agent["curso"]:
            J.reply("¿De qué curso? Di «pasa las notas de 7A a Zeti».", "PLATAFORMA")
            return True
        _fill_now(agent["curso"])
        return True
    if _PF_SAVE.match(t) and agent["filled"]:          # 12.4: guardar notas oficiales siempre con tu «sí»
        filled = list(agent["filled"])
        est = {x["estudiante"] for x in filled}

        def do_save():
            try:
                J.notify(save_page(), "PLATAFORMA")
            except Exception as e:
                J.notify(f"No pude pulsar guardar: {e}", "PLATAFORMA")
            agent["filled"] = []
        ch = sum(1 for x in filled if x["cambia"])
        J.request_approval("plataforma", f"Guardar en la plataforma {len(filled)} nota{'s' if len(filled) != 1 else ''} de {len(est)} "
                           f"estudiante{'s' if len(est) != 1 else ''} ({agent['curso'] or 'la planilla'})",
                           (f"{ch} cambian un valor que ya estaba. " if ch else "") + "Revisa la pantalla antes de aprobar: lo que llené está resaltado.",
                           on_ok=do_save, on_no=lambda: J.notify("Vale, no guardé. Puedes revisar y pulsar tú «Guardar».", "PLATAFORMA"), ttl=3600,
                           say=f"¿Guardo en la plataforma las {len(filled)} notas que llené{' (' + str(ch) + ' cambian un valor que ya estaba)' if ch else ''}? "
                               "Di «sí» o «no».")
        return True
    if _PF_CLOSE.search(t) and agent["ctx"] is not None:
        browser_close()
        J.reply("Cerré mi navegador. Tu sesión queda recordada para la próxima vez.", "PLATAFORMA")
        return True
    return False


__all__ = ['_PF_CLOSE', '_PF_FILL', '_PF_GO', '_PF_SAVE', '_PF_URL', '_alive', '_all_frames_extract', '_fill_now', '_agent_launch', '_run', '_worker', 'agent',
           'browser_close', 'browser_open', 'course_data', 'fill_page', 'llenador', 'platform_voice', 'save_page']
