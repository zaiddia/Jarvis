"""Perfil y trato, descanso, correo, sismos, calendario, rutinas y notas.

Parte de Jarvis (antes dentro de jarvis.py). Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import calendario
import correo
import datetime
import diario
import json
import notas
import os
import perfil
import random
import re
import rutinas
import sismos
import skills
import threading
import time
import urllib.request

from nucleo import J


# =============================================================================
# CÓMO TE TRATA + MEMORIA QUE APRENDE SOLA (perfil). Lógica de perfil en perfil.py.
# =============================================================================
def _user_ctx(question=""):
    ctx = perfil.context_for_ai(question=question) + (diario.today_context() if J.settings["diary_enabled"] else "")
    name = J.settings["address_name"].strip()
    if name:
        ctx += f" Cuando te dirijas al usuario, llámalo «{name}»."
    return ctx


_NAME_RE = re.compile(r"^(?:oye |jarvis )?(?:ll[aá]mame|dime de ahora en adelante|tr[aá]tame de|"
                      r"refi[eé]rete a m[ií] como|me llamo|mi nombre es|puedes llamarme)\s+(.{2,30})$", re.I)


def profile_voice(text, t):
    """Aprende datos del usuario sin que diga «recuerda», y «llámame X»."""
    m = J._NAME_RE.match(t)
    if m and not re.search(r"\b(?:recuerda|anota|apunta)\b", t):
        name = re.sub(r"[.?!]+$", "", text.split(None, 1)[-1]).strip().strip('"').title()[:30]
        # «llámame profe» → toma la última palabra o dos
        raw = text.strip().rstrip(".?!")
        name = raw.split(" ", 1)[1].strip() if " " in raw else raw
        name = re.sub(r"^(?:ll[aá]mame|dime|trátame de|tratame de|refi[eé]rete a m[ií] como|me llamo|"
                      r"mi nombre es|puedes llamarme)\s+", "", name, flags=re.I).strip().strip('"')[:30]
        if name and len(name.split()) <= 3 and not re.search(r"\b(?:para|que|como se|cual|un nombre)\b", name, re.I):
            J.apply_settings({"address_name": name})
            J.reply(f"Listo, te diré {name} de ahora en adelante.", "MEMORIA")
            return True
    # «¿qué sabes de mí?» y preguntas que contesta la memoria: «¿cómo se llama mi hermana?», «¿qué música me gusta?»
    if re.search(r"\bque (?:sabes|recuerdas|has aprendido) (?:de|sobre) mi\b|\bque te he contado\b|\bque sabes de mi vida\b", t):
        J.reply(perfil.summary(), "MEMORIA")
        return True
    ans = perfil.answer(text)
    if ans:
        J.reply(ans, "MEMORIA")
        return True
    forgotten = perfil.forget(text)
    if forgotten:
        J.reply(f"Listo, lo olvidé: {forgotten}.", "MEMORIA")
        J._profile_changed()
        return True
    fact = perfil.detect(text)
    if fact:
        f = perfil.add(fact)
        J._profile_changed()
        if f and f.get("corrige"):
            J.reply(f"Entendido, lo corrijo: {perfil.to_second_person(f['texto']).rstrip('.')}.", "MEMORIA")
        else:
            J.reply(random.choice(["Lo tendré en cuenta.", "Anotado, no lo olvidaré.", "Qué bien saberlo. Lo recordaré."]), "MEMORIA")
        return True
    return False


def _profile_changed():
    J.socketio.emit("profile_updated", perfil.snapshot())


# =============================================================================
# DESCANSAR («Jarvis, descansa» / «despierta»): sigilo con tonos, solo atiende al nombre
# =============================================================================
def _rest_voice(text, t):
    if re.search(r"\b(?:descansa|ponte a descansar|ve a descansar|duerme(?:te)?|ponte en pausa|"
                 r"tomate un descanso|modo descanso)\b", t):
        J.reply("Vale, me voy a descansar. Di «Jarvis, despierta» cuando me necesites.", "SISTEMA")
        J.jarvis_rest["on"] = True
        J.set_state(resting=True)

        def go():
            J.play_sound(J.tono_descanso(), 2)
            time.sleep(1.4)
            J.hud_hide()
        threading.Thread(target=go, daemon=True).start()
        return True
    if J.jarvis_rest["on"] and re.search(r"\b(?:despierta(?:te)?|ya (?:volvi|regrese|estoy)|vuelve|despabilate|"
                                       r"sal del descanso|ya llegue)\b", t):
        J.jarvis_rest["on"] = False
        J.set_state(resting=False)
        J.hud_show()
        J.play_sound(J.tono_despertar(), 2)
        J.reply("Aquí estoy. ¿En qué te ayudo?", "SISTEMA")
        return True
    return False


# =============================================================================
# CORREO POR VOZ (lógica en correo.py). Redacta, lee y, solo si confirmas, envía por Gmail.
# =============================================================================
email_pending = {"to": None, "asunto": "", "cuerpo": "", "expires": 0.0}
_MAIL_RE = re.compile(
    r"\b(?:escrib(?:e|ir|ele|irle)|manda(?:le)?|env(?:ia|iale|iar)|redacta(?:me)?|hazle?|pon(?:le)?)\b"
    r".{0,25}\b(?:correo|email|mail|e-mail|mensaje de correo)\b"
    r"|\b(?:correo|email|mail)\b.{0,20}\b(?:a|para)\b")


def _mail_book():
    return correo.parse_book(J.settings["email_book"])


def email_voice(text, t):
    """«escríbele un correo a la coordinadora diciendo que mañana llego a las 7»."""
    if not J._MAIL_RE.search(t):
        return False
    if not correo.valid_sender(J.settings["email_address"]):
        J.reply("Para enviar correos primero pon tu dirección de Gmail y una «contraseña de aplicación» "
              "en Ajustes, sección Integraciones.", "CORREO")
        return True
    if not J.settings["email_app_password"].strip():
        J.reply("Falta la contraseña de aplicación de tu correo (Ajustes › Integraciones › Correo).", "CORREO")
        return True
    # ¿a quién?
    m = re.search(r"\b(?:a|para)\s+(.+?)\s+(?:que|diciendo|sobre|acerca de|con el (?:tema|asunto)|:)\b", text, re.I)
    quien = m.group(1).strip() if m else ""
    m2 = re.search(r"\b(?:que|diciendo|sobre|acerca de|con el (?:tema|asunto)|:)\s+(.+)$", text, re.I)
    mensaje = m2.group(1).strip() if m2 else ""
    if not quien:
        J.reply("¿A quién le escribo? Dime el nombre de la agenda o el correo.", "CORREO")
        return True
    dest = correo.resolve_recipient(quien, J._mail_book())
    if not dest:
        J.reply(f"No tengo el correo de «{quien}». Agrégalo en Ajustes › Integraciones › Agenda de correos, "
              "o dime el correo completo.", "CORREO")
        return True
    if not mensaje:
        J.reply(f"¿Qué le digo a {dest[0] or dest[1]}?", "CORREO")
        return True
    J.reply("Redacto el correo…", "CORREO")

    def work():
        try:
            prompt = correo.prompt(f"Para {dest[0] or dest[1]}: {mensaje}", J.settings["email_sender_name"])
            raw = J.ai_chat([{"role": "user", "content": prompt}], json_mode=True, max_tokens=900)
            m = correo.validate(J._extract_json(raw))
        except J.AIError as e:
            J.reply(J.ai_error_reply(e), "CORREO")
            return
        except Exception as e:
            J.log_terminal(f"Correo: {e}", "ERROR")
            J.reply("No pude redactar el correo. Inténtalo otra vez.", "CORREO")
            return
        J.email_pending.update(to=dest, asunto=m["asunto"], cuerpo=m["cuerpo"], expires=time.time() + 180)
        J.reply(correo.spoken_preview(dest[0], dest[1], m["asunto"], m["cuerpo"]), "CORREO")
    threading.Thread(target=work, daemon=True, name="correo").start()
    return True


def _email_confirm_pending(t):
    """Si hay un correo esperando confirmación, trata «sí/no» aquí. Devuelve True si lo gestionó."""
    if not (J.email_pending["to"] and time.time() < J.email_pending["expires"]):
        return False
    if re.fullmatch(rf"{J.CONFIRM_RE}(?: .*)?", t) or re.search(r"\b(?:envialo|enviala|mandalo|mandala|enviar|"
                                                              r"si envialo|dale envialo)\b", t):
        dest = J.email_pending["to"]
        asunto, cuerpo = J.email_pending["asunto"], J.email_pending["cuerpo"]
        J.email_pending.update(to=None, expires=0)
        try:
            correo.send(J.settings["email_address"].strip(), J.settings["email_app_password"].strip(),
                        dest[1], asunto, cuerpo, J.settings["email_sender_name"].strip())
            J.reply(f"Correo enviado a {dest[0] or dest[1]}.", "CORREO")
        except Exception as e:
            J.reply(f"No pude enviarlo: {e}", "CORREO")
        return True
    if re.fullmatch(rf"{J.DENY_RE}(?: .*)?", t):
        J.email_pending.update(to=None, expires=0)
        J.reply("Vale, no lo envío.", "CORREO")
        return True
    return False


# =============================================================================
# ALERTA DE SISMOS (datos del USGS, gratis). Lógica en sismos.py.
# =============================================================================
quake = {"seen": set(), "started": 0.0}


def _quake_user_latlon():
    city = J.settings["weather_city"].strip()
    if not city:
        return None
    try:
        g = J._geo(city)
        return (g["lat"], g["lon"]) if g else None
    except Exception:
        return None


def _quake_worker():
    time.sleep(40)
    while True:
        try:
            if J.settings["quake_alerts"] and not J.is_offline():
                J._quake_check()
        except Exception as e:
            J.log_terminal(f"Sismos: {e}", "AVISO")
        time.sleep(90)


def _quake_check():
    user = J._quake_user_latlon()
    nuevos = []
    for url in sismos.FEEDS:
        try:
            for q in sismos.parse(json.loads(J._get_text(url, timeout=12))):
                if q["id"] and q["id"] not in J.quake["seen"]:
                    nuevos.append(q)
        except Exception as e:
            J.log_terminal(f"Sismos ({urllib.parse.urlsplit(url).netloc}): {e}", "AVISO")
    now = time.time()
    first = not J.quake["started"]
    if first:
        J.quake["started"] = now
    for q in nuevos:
        J.quake["seen"].add(q["id"])
        if len(J.quake["seen"]) > 400:
            J.quake["seen"] = set(list(J.quake["seen"])[-200:])
        # al arrancar, no avisar de los que ya habían pasado (solo marcarlos como vistos)
        if first or now - q["time"] / 1000 > 1800:
            continue
        lvl = sismos.level(q, user, J.settings["quake_min_mag"])
        if lvl <= 0:
            continue
        if J.jarvis_rest["on"]:
            J.hud_show()
            J.jarvis_rest["on"] = False
            J.set_state(resting=False)
        J.play_sound(J.tono_sismo_alerta() if lvl >= 2 else J.tono_sismo_aviso(), 4)
        time.sleep(0.2)
        J.alert(sismos.describe(q, lvl, user, now), "SISMO")
        J.log_terminal(f"Sismo detectado (nivel {lvl}): {sismos.short(q)}", "SISMO")


def quake_test():
    if not J.settings["weather_city"].strip():
        return {"ok": True, "msg": "Vigilaré los sismos de Colombia. Para avisarte según qué tan cerca te "
                                   "quedan, escribe tu ciudad arriba en «Clima y noticias»."}
    user = J._quake_user_latlon()
    if not user:
        return {"ok": False, "msg": f"No pude ubicar «{J.settings['weather_city']}». Revisa el nombre de la ciudad."}
    return {"ok": True, "msg": f"Listo. Vigilaré los sismos cerca de {J.settings['weather_city']} y te avisaré "
                               "con un tono y por voz. Los lejanos y pequeños no te molestarán."}



# =============================================================================
# CALENDARIO (Google, Outlook… por su enlace iCal, solo lectura). Lógica en calendario.py.
# =============================================================================
cal_state = {"missing_lib": False}


def _cal_urls():
    return calendario.clean_urls(J.settings["calendar_urls"])


def cal_refresh(force=False):
    urls = J._cal_urls()
    if not urls:
        calendario.cache.update(events=[], errors=[], urls=())
        return calendario.cache
    try:
        before = calendario.cache["fetched"]
        c = calendario.refresh(urls, force=force)
        if c["fetched"] != before:
            for err in c["errors"]:
                J.log_terminal(f"Calendario: {err}", "AVISO")
    except ImportError:
        if not J.cal_state["missing_lib"]:
            J.cal_state["missing_lib"] = True
            J.log_terminal("Para leer el calendario falta un componente: ejecuta instalar.bat otra vez.", "AVISO")
    return calendario.cache


def _cal_worker():
    """Actualiza el calendario cada 10 minutos y avisa antes de cada evento."""
    while True:
        try:
            if J._cal_urls():
                J.cal_refresh()
                for ev, mins in calendario.due_alerts(before_min=J.settings["calendar_notice_min"]):
                    J.hud_show()
                    J.alert(f"En {mins} minuto{'s' if mins != 1 else ''}: {calendario.what(ev)}.", "CALENDARIO")
                    if mins > 0:
                        J.offer_routine_for(str(ev.get("titulo") or calendario.what(ev)))
        except Exception as e:
            J.log_terminal(f"Calendario: {e}", "AVISO")
        time.sleep(30)


def _event_line(ev, with_day=True):
    if ev["todo_el_dia"]:
        d = notas.when_spoken(calendario.as_note(ev)) if with_day else ""
        return (f"{d}, " if d else "") + f"todo el día, {calendario.what(ev)}"
    return f"{notas.when_spoken(calendario.as_note(ev), with_day=with_day)}, {calendario.what(ev)}"


def agenda(scope, with_day=True):
    """Notas + eventos del calendario de ese periodo, ordenados por hora. Lista de frases."""
    today = datetime.date.today()
    d1, d2 = {"hoy": (today, today), "manana": (today + datetime.timedelta(days=1),) * 2,
              "semana": (today, today + datetime.timedelta(days=7))}[scope]
    items = [((n["fecha"] or "9999"), (n.get("hora") or "99:99"), notas.spoken(n, with_day=with_day))
             for n in notas.listing(scope)]
    if J._cal_urls():
        J.cal_refresh()
        for ev in calendario.between(d1, d2):
            hora = "00:00" if ev["todo_el_dia"] else ev["inicio"][11:16]
            items.append((ev["inicio"][:10] if not ev["todo_el_dia"] else max(ev["inicio"][:10], d1.isoformat()),
                          hora, J._event_line(ev, with_day)))
    return [x[2] for x in sorted(items)]


def _say_agenda(scope, vacio, titulo):
    lines = J.agenda(scope, with_day=scope == "semana")
    if not lines:
        J.reply(vacio, "AGENDA")
        return
    if len(lines) > 1:
        lines[-1] = "y " + lines[-1]
    extra = f" Y {len(lines) - 8} cosas más." if len(lines) > 8 else ""
    J.reply(f"{titulo}: " + "; ".join(lines[:8]) + "." + extra, "AGENDA")


def calendar_voice(text, t):
    """«¿cuál es mi próxima clase?», «¿qué sigue?», «actualiza el calendario». True si era para esto."""
    if re.search(r"\b(?:actualiza|recarga|refresca|sincroniza)\b.*\bcalendario\b", t):
        if not J._cal_urls():
            J.reply("Aún no conectaste tu calendario. En Ajustes, sección Memoria, pega su dirección iCal.", "CALENDARIO")
            return True
        c = J.cal_refresh(force=True)
        n = len(calendario.between(datetime.date.today(), datetime.date.today() + datetime.timedelta(days=30)))
        J.reply(f"Calendario actualizado: {n} eventos en el próximo mes."
              + (f" Ojo: {c['errors'][0]}" if c["errors"] else ""), "CALENDARIO")
        return True
    if (re.search(r"\b(?:calendario|agenda)\b", t)
            and re.search(r"\b(?:revisa|mira|muestra|muestrame|dime|consulta|lee|leeme|abre|que|cuales|cuantos|"
                          r"hay|tengo|eventos?|pendientes?|programado)\b", t)
            and not re.search(r"\bproxim[ao]\b", t)):
        scope = "manana" if re.search(r"\bmanana\b", t) else "semana" if re.search(r"\bsemana\b", t) else "hoy"
        if not J._cal_urls():
            J.reply("Aún no conectaste tu calendario. En Ajustes, sección Memoria, pega la «dirección secreta "
                  "en formato iCal» de Google Calendar (o el enlace ICS de Outlook) y pulsa Probar.", "CALENDARIO")
            return True
        J.cal_refresh()
        titles = {"hoy": ("Hoy tienes", "Hoy no tienes nada en el calendario ni en tus notas."),
                  "manana": ("Mañana tienes", "Mañana no tienes nada en el calendario ni en tus notas."),
                  "semana": ("Esta semana tienes", "Esta semana no tienes nada en el calendario ni en tus notas.")}
        J._say_agenda(scope, titles[scope][1], titles[scope][0])
        return True
    m = re.search(r"\b(?:mi |la |el )?proxim[ao] (clase|reunion|evento|cita|actividad|compromiso)\b"
                  r"|\bque (?:sigue|me toca|tengo ahora)\b|\bque (?:hay|tengo) en (?:el|mi) calendario\b", t)
    if not m:
        return False
    if not J._cal_urls():
        if "calendario" in t or m.group(1):
            J.reply("Aún no conectaste tu calendario. En Ajustes, sección Memoria, pega la «dirección secreta "
                  "en formato iCal» de Google Calendar (o el enlace ICS de Outlook).", "CALENDARIO")
            return True
        return False
    J.cal_refresh()
    if "calendario" in t:
        J._say_agenda("hoy", "Hoy no tienes nada en el calendario ni en tus notas.", "Hoy tienes")
        return True
    kw = {"clase": "clase", "reunion": "reuni", "cita": "cita"}.get(m.group(1) or "", "")
    nx = calendario.upcoming(limit=1, keyword=kw)
    fallback = False
    if not nx and kw:
        nx = calendario.upcoming(limit=1)
        fallback = bool(nx)
    if not nx:
        J.reply("No tienes más eventos con hora en tu calendario este mes.", "CALENDARIO")
        return True
    ev = nx[0]
    ini = datetime.datetime.fromisoformat(ev["inicio"])
    fin = datetime.datetime.fromisoformat(ev["fin"])
    if ini <= datetime.datetime.now(ini.tzinfo):
        J.reply(f"Ahora mismo: {calendario.what(ev)}, hasta las {fin.strftime('%H:%M')}.", "CALENDARIO")
    else:
        que = {"clase": "Tu próxima clase", "reunion": "Tu próxima reunión", "cita": "Tu próxima cita"}.get(
            m.group(1) or "", "Lo próximo")
        if fallback:
            que = {"clase": "No veo más clases este mes. Lo próximo", "reunion": "No veo más reuniones este mes. "
                   "Lo próximo", "cita": "No veo más citas este mes. Lo próximo"}.get(m.group(1) or "", "Lo próximo")
        J.reply(f"{que}: {J._event_line(ev)}.", "CALENDARIO")
    return True


# =============================================================================
# RUTINAS CON NOMBRE («modo clase», «fin de clase»…). La lógica está en rutinas.py.
# =============================================================================
rutinas.configure(J.CONFIG_DIR)
routine_state = {"running": None}


def run_routine(r):
    """Ejecuta los pasos en orden, en segundo plano. Cada paso escribe en el HUD pero no
    habla (si no, oirías «Abriendo Word… Volumen al 40…»); solo hablan los pasos «decir»
    y el aviso final. Nunca ejecuta acciones peligrosas ni otras rutinas."""
    if J.routine_state["running"]:
        J.reply(f"Ya estoy ejecutando la rutina {J.routine_state['running']}.", "RUTINA")
        return
    J.learn_note("rutina", {"nombre": r["nombre"]})
    J.routine_state["running"] = r["nombre"]
    J.log_terminal(f"Rutina «{r['nombre']}»: {len(r['pasos'])} pasos.", "RUTINA")
    diario.log("rutina", r["nombre"])
    J.card("rutina", r["nombre"], "En marcha…", "▶", secs=6 + 2 * len(r["pasos"]), steps=r["pasos"], step=0)

    def work():
        saltados, hablo_al_final = [], False
        try:
            for i, step in enumerate(r["pasos"]):
                kind, val = rutinas.step_kind(step)
                hablo_al_final = False
                if kind == "esperar":
                    time.sleep(val)
                    continue
                if kind == "decir":
                    J.reply(val, "RUTINA")
                    hablo_al_final = i == len(r["pasos"]) - 1
                    continue
                direct = skills.parse(val)
                sk = skills.REGISTRY.get(direct[0]) if direct else None
                if sk and sk.dangerous:
                    saltados.append(val)
                    J.log_terminal(f"Rutina: me salto «{val}» (acción delicada; dímela tú directamente).", "AVISO")
                    continue
                if rutinas.find(val):
                    saltados.append(val)
                    J.log_terminal(f"Rutina: me salto «{val}» (una rutina no puede lanzar otra).", "AVISO")
                    continue
                J.log_terminal(f"Paso {i + 1}: {val}", "RUTINA")
                J.card("rutina", r["nombre"], val, "▶", secs=8, steps=r["pasos"], step=i)
                J._tl.quiet = True
                try:
                    J.process_command(val)
                finally:
                    J._tl.quiet = False
                time.sleep(0.6)                     # deja que la ventana o el ajuste termine de aplicarse
        except Exception as e:
            J.log_terminal(f"Rutina «{r['nombre']}»: {e}", "ERROR")
        finally:
            J._tl.quiet = False
            J.routine_state["running"] = None
            J.learn_routine_done(r)
        if saltados:
            n = len(saltados)
            J.reply(f"Rutina {r['nombre']} lista, pero me salté {n} paso{'s' if n != 1 else ''} que no "
                  f"se pueden usar en una rutina. Los ves en el Registro.", "RUTINA")
        elif not hablo_al_final:
            J.reply(f"Rutina {r['nombre']} lista.", "RUTINA")
    threading.Thread(target=work, daemon=True, name="rutina").start()


# Rutinas que se lanzan solas (6.8): a su hora, al iniciar Jarvis o al volver al equipo.
_RT_DONE = os.path.join(J.CONFIG_DIR, "rutinas_hechas.json")


def _rt_done():
    try:
        with open(J._RT_DONE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _rt_mark(nombre):
    d = J._rt_done()
    d[nombre] = datetime.date.today().isoformat()
    try:
        os.makedirs(J.CONFIG_DIR, exist_ok=True)
        with open(J._RT_DONE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
    except OSError:
        pass


def _routine_auto(r, why):
    J.log_terminal(f"Rutina «{r['nombre']}» ({why}).", "RUTINA")
    J.run_routine(r)


def _routines_worker():
    """Cada 20 s: ¿toca alguna rutina por su hora? ¿Acabas de volver al equipo?"""
    idle_max, last_return = 0.0, 0.0
    while True:
        try:
            for r in rutinas.due(datetime.datetime.now(), J._rt_done()):
                if J.routine_state["running"]:
                    break                              # la siguiente vuelta la lanza (tiene 10 minutos)
                J._rt_mark(r["nombre"])
                J._routine_auto(r, "a su hora")
            if rutinas.with_kind("volver"):
                idle = J._idle_seconds()
                idle_max = max(idle_max, idle)
                if idle < 25:
                    if idle_max >= 600 and time.time() - last_return > 3600 and not J.routine_state["running"]:
                        last_return = time.time()
                        for r in rutinas.with_kind("volver")[:1]:
                            J._routine_auto(r, "al volver")
                    idle_max = 0.0
        except Exception as e:
            J.log_terminal(f"Rutinas automáticas: {e}", "AVISO")
        time.sleep(20)


def _routines_at_start():
    for r in rutinas.with_kind("inicio")[:1]:
        J._routine_auto(r, "al iniciar")


@skills.skill("crear_rutina", "Crea o cambia una rutina: varias órdenes de Jarvis seguidas, que se lanzan con su nombre "
              "y, si se indica, solas a una hora o al encender el equipo",
              args="nombre, pasos (órdenes separadas por punto y coma; «decir …» para hablar), "
                   "cuando (opcional: «07:30», «07:30 lun-vie», «al iniciar», «al volver»)",
              windows_only=False)
def crear_rutina(nombre, pasos, cuando=""):
    pasos = str(pasos or "").replace(";", "\n")
    try:
        r = rutinas.upsert(nombre, nombre, pasos, None, cuando)
    except ValueError as e:
        raise skills.SkillError(str(e))
    J.socketio.emit("rutinas_updated", rutinas.routines)
    cuando_txt = rutinas.when_spoken(r["cuando"])
    return (f"Rutina «{r['nombre']}» creada, con {len(r['pasos'])} pasos" +
            (f". Se lanzará sola {cuando_txt}." if cuando_txt else f". Dime «{r['nombre']}» para lanzarla."))


def _upd_confirm(args):
    info = J.upd.get("info") or {}
    v = info.get("version", "nueva")
    return f"¿Instalo la versión {v}? Me reiniciaré en cuanto termine (tarda uno o dos minutos)."


@skills.skill("instalar_actualizacion", "Descarga e instala la versión nueva de Jarvis y lo reinicia",
              dangerous=True, confirm=_upd_confirm, windows_only=False)
def instalar_actualizacion():
    if J.upd["busy"]:
        return "Ya me estoy actualizando."
    threading.Thread(target=J.install_update, daemon=True, name="actualizar").start()
    return "Descargando la actualización. Me reinicio en cuanto termine; ves el avance en Ajustes, sección Acerca de."


def routine_voice(text, t):
    """«modo clase», «activa la rutina fin de clase», «¿qué rutinas tengo?». True si era para esto."""
    if re.search(r"\b(?:que|cuales) rutinas\b|\bmis rutinas\b|\blista de rutinas\b", t):
        if not rutinas.routines:
            J.reply("No tienes rutinas. Créalas en Ajustes, sección Rutinas.", "RUTINA")
        else:
            nombres = [r["nombre"] + (f" ({rutinas.when_spoken(r['cuando'])})" if r.get("cuando") else "")
                       for r in rutinas.routines]
            J.reply(f"Tienes {len(nombres)} rutinas: {', '.join(nombres[:-1]) + ' y ' + nombres[-1] if len(nombres) > 1 else nombres[0]}. "
                  "Dime su nombre para lanzarla.", "RUTINA")
        return True
    if re.search(r"\b(?:crea|creame|haz|nueva|agrega|edita|cambia)\b.*\brutina\b", t):
        # Con la IA conectada, la crea ella a partir de lo que dices («crea una rutina buenos días a las 7…»).
        if J.settings["ai_router"] and J.state.get("ai") == "ok" and not getattr(J._tl, "remote", False):
            result = J.ask_ai(text, route=True)
            if result[0] == "skill":
                J.run_skill(result[1], result[2])
            else:
                J.reply(result[1], "RUTINA")
            return True
        J.open_settings_window()
        J.reply("Las rutinas se crean en Ajustes, sección Rutinas: un nombre, las frases para lanzarla, "
              "una orden por línea y, si quieres, cuándo se lanza sola (por ejemplo 07:30 lun-vie, al iniciar "
              "o al volver). Te abro los ajustes.", "RUTINA")
        return True
    r = rutinas.find(t)
    if r:
        J.run_routine(r)
        return True
    return False


# =============================================================================
# MEMORIA PERSONAL: notas y pendientes («recuerda que…», «¿qué tengo pendiente?»)
#   La lógica está en notas.py; aquí se conecta con la voz, los avisos y la IA.
# =============================================================================
notas.configure(J.CONFIG_DIR)


def _notes_ctx():
    if not J.settings["notes_ai_context"]:
        return ""
    ctx = notas.context_for_ai()
    if J._cal_urls():
        ctx += calendario.context_for_ai(notas.when_spoken)
    return ctx


def _notes_changed():
    J.socketio.emit("notes_updated", J.notes_snapshot())


def notes_snapshot():
    today = datetime.date.today()
    items = sorted(notas.notes, key=lambda n: (n.get("hecho", False), notas._sort_key(n)))
    return [{"id": n["id"], "texto": n["texto"], "que": notas.what(n), "cuando": notas.when_spoken(n, today),
             "fecha": n.get("fecha", ""), "hora": n.get("hora", ""), "hecho": bool(n.get("hecho"))}
            for n in items]


def _say_list(items, vacio, titulo, with_day=True):
    if not items:
        J.reply(vacio, "NOTAS")
        return
    partes = [notas.spoken(n, with_day=with_day) for n in items[:6]]
    if len(partes) > 1:
        partes[-1] = "y " + partes[-1]
    extra = f" Y {len(items) - 6} más en Ajustes, sección Memoria." if len(items) > 6 else ""
    J.reply(f"{titulo}: " + "; ".join(partes) + "." + extra, "NOTAS")


_NOTE_ADD = re.compile(
    r"^(?:por favor )?(?:jarvis )?(?:recuerda(?:me)?|recuerde(?:me)?|acuerdate|no (?:me )?dejes olvidar|"
    r"no (?:te )?olvides|anota(?:me)?|apunta(?:me)?|toma nota|guarda (?:una|esta) nota|agenda(?:me)?|"
    r"ten en cuenta)\b(?:\s+(?:que|de que|de|esto|lo siguiente))?\s*(.*)$")


def notes_voice(text, t):
    """Órdenes de voz de la memoria personal. Devuelve True si la frase era para ella."""
    m = J._NOTE_ADD.match(t)
    if m:
        if J.parse_reminder(t):                      # «recuérdame en 10 minutos…» = alarma de siempre
            return False
        resto_n = m.group(1).strip()
        if not resto_n:
            J.reply("¿Qué quieres que recuerde? Por ejemplo: recuerda que la reunión de padres es el jueves a las 3.", "NOTAS")
            return True
        # mismo número de palabras que el disparador, pero del texto original (con tildes y mayúsculas)
        skip = len(t[:m.start(1)].split())
        original = " ".join(text.split()[skip:]).strip() or resto_n
        n = notas.add(original)
        J._notes_changed()
        cuando = notas.when_spoken(n)
        J.reply(f"Anotado{': ' + cuando if cuando else ''}, {notas.what(n)}."
              + (" Te aviso antes." if n.get("hora") and J.settings["notes_notice_min"] else ""), "NOTAS")
        return True

    scope = None
    if re.search(r"\bque (?:tengo|tenia|hay)(?: anotado| agendado| pendiente)? (?:para )?hoy\b", t):
        scope, vacio, titulo = "hoy", "Para hoy no tienes nada anotado.", "Hoy tienes"
    elif re.search(r"\bque (?:tengo|tenia|hay)(?: anotado| agendado| pendiente)? (?:para )?manana\b", t):
        scope, vacio, titulo = "manana", "Para mañana no tienes nada anotado.", "Mañana tienes"
    elif re.search(r"\bque (?:tengo|tenia|hay)(?: anotado| agendado| pendiente)? (?:para )?esta semana\b", t):
        scope, vacio, titulo = "semana", "Esta semana no tienes nada anotado.", "Esta semana tienes"
    elif re.search(r"\b(?:que|cuales) (?:tengo|tenia|hay|son mis) (?:pendientes?|por hacer|anotado|agendado)\b|"
                   r"\bmis (?:pendientes|notas)\b|\bque (?:notas|pendientes) tengo\b|"
                   r"\blee(?:me)? (?:mis |las )?(?:notas|pendientes)\b|\bque te pedi que (?:recordaras|anotaras)\b", t):
        scope, vacio, titulo = "todo", "No tienes pendientes anotados.", None
    if scope in ("hoy", "manana", "semana"):
        J._say_agenda(scope, vacio, titulo)              # notas + calendario, por hora
        return True
    if scope:
        items = notas.listing(scope)
        J._say_list(items, vacio, titulo or (f"Tienes {len(items)} pendiente" + ("s" if len(items) != 1 else "")),
                  with_day=True)
        if J._cal_urls():
            nx = calendario.upcoming(limit=1)
            if nx:
                J.reply(f"Y en tu calendario, lo próximo: {J._event_line(nx[0])}.", "AGENDA")
        return True

    m = re.match(r"^(?:ya (?:hice|termine|complete|entregue|pase|cumpli|resolvi|compre|llame|envie|fui a|"
                 r"mande|hable con|pague)|tacha|marca como hech[oa]|completa|completado|listo|hecho)\s+(.+)$", t)
    if m:
        n = notas.find(m.group(1)) or notas.find(t)
        if not n:
            return False                            # no hablaba de una nota: que siga el resto
        notas.set_done(n["id"])
        J._notes_changed()
        J.reply(f"Hecho: {notas.what(n)}. Lo taché de tus pendientes.", "NOTAS")
        return True
    m = re.match(r"^(?:borra|elimina|quita|olvida)\s+(?:la nota|el pendiente|el recordatorio|lo)\s+(?:de |sobre |del |que )?(.+)$", t)
    if m:
        n = notas.find(m.group(1))
        if not n:
            J.reply("No encontré esa nota. Dime alguna palabra de lo que anotaste.", "NOTAS")
            return True
        notas.delete(n["id"])
        J._notes_changed()
        J.reply(f"Borrada la nota: {notas.what(n)}.", "NOTAS")
        return True
    if re.search(r"\b(?:borra|limpia|quita)\b.*\b(?:notas|pendientes) (?:hechas|hechos|terminadas|completadas|tachadas)\b", t):
        notas.clear_done()
        J._notes_changed()
        J.reply("Listo, borré las notas que ya estaban hechas.", "NOTAS")
        return True
    return False


def _notes_worker():
    """Avisos de las notas con hora: unos minutos antes y a la hora."""
    while True:
        time.sleep(30)
        try:
            for n, tipo in notas.due_alerts(before_min=J.settings["notes_notice_min"]):
                que = notas.what(n)
                J.hud_show()
                if tipo == "antes":
                    J.alert(f"Recordatorio: en {J.settings['notes_notice_min']} minutos, {que}.", "NOTAS")
                else:
                    J.play_sound(J.resolve_alarm_sound())
                    J.alert(f"Es la hora: {que}.", "NOTAS")
                J._notes_changed()
        except Exception as e:
            J.log_terminal(f"Avisos de notas: {e}", "AVISO")


def notes_today_summary(speak_it=False):
    items = J.agenda("hoy", with_day=False)
    if not items:
        return ""
    txt = "Hoy tienes: " + "; ".join(items[:6]) + "."
    if speak_it:
        J.reply(txt, "NOTAS")
    else:
        J.push_chat("jarvis", "📌 " + txt, "NOTAS")
    return txt


__all__ = [
    '_MAIL_RE',
    '_NAME_RE',
    '_NOTE_ADD',
    '_RT_DONE',
    '_cal_urls',
    '_cal_worker',
    '_email_confirm_pending',
    '_event_line',
    '_mail_book',
    '_notes_changed',
    '_notes_ctx',
    '_notes_worker',
    '_profile_changed',
    '_quake_check',
    '_quake_user_latlon',
    '_quake_worker',
    '_rest_voice',
    '_routine_auto',
    '_routines_at_start',
    '_routines_worker',
    '_rt_done',
    '_rt_mark',
    '_say_agenda',
    '_say_list',
    '_upd_confirm',
    '_user_ctx',
    'agenda',
    'cal_refresh',
    'cal_state',
    'calendar_voice',
    'crear_rutina',
    'email_pending',
    'email_voice',
    'instalar_actualizacion',
    'notes_snapshot',
    'notes_today_summary',
    'notes_voice',
    'profile_voice',
    'quake',
    'quake_test',
    'routine_state',
    'routine_voice',
    'run_routine',
]
