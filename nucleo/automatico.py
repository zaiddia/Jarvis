"""12.32: avisos por evento (correo de alguien, evento nuevo en el calendario, dólar que cruza un valor) y proyectos que
se repiten solos y se comparan con la vez anterior. La lógica está en automaticos.py."""
import datetime
import re
import threading
import time

import automaticos as A
import calendario
import proyectos
from nucleo import J

_auto = {"last_price": {}, "seeded": False, "t_mail": 0.0, "t_price": 0.0}


def _alert(text, phone=False):
    J.notify(text, "AVISOS")
    if phone:
        try:
            if J.telegram_ready():
                J.telegram_send(text)
            elif J.whatsapp_ready():
                J.whatsapp_send(text)
        except Exception as e:
            J.log_terminal(f"Aviso al celular: {e}", "AVISO")


def check_mail(msgs):
    """Revisa correos nuevos contra las reglas de correo. → cuántos avisos dio."""
    rules = [r for r in A.data["reglas"] if r["tipo"] == "correo"]
    seen = A.data["vistos"]["mail"]
    n = 0
    fresh = [m for m in msgs if (m.get("uid") or m.get("msgid")) and (m.get("uid") or m.get("msgid")) not in seen]
    for m in fresh:
        seen.append(m.get("uid") or m.get("msgid"))
        if not _auto["seeded"]:
            continue                                     # la primera pasada solo aprende lo que ya estaba
        for r in rules:
            if A.mail_matches(r, m):
                J._alert(f"📧 Correo de {m.get('de_nombre') or m.get('de')}: «{m.get('asunto')}».", r.get("celular"))
                n += 1
                break
    del seen[:-400]
    return n


def _ev_what(ev):
    try:
        return calendario.what(ev)
    except Exception:
        return str(ev.get("titulo") or "un evento")


def check_calendar(events, now=None):
    now = now or datetime.datetime.now()
    rules = [r for r in A.data["reglas"] if r["tipo"] == "calendario"]
    if not rules:
        return 0
    seen = A.data["vistos"]["cal"]
    n = 0
    for ev in events:
        k = A.event_key(ev)
        if k in seen:
            continue
        seen.append(k)
        if not _auto["seeded"] or str(ev.get("inicio", ""))[:10] < now.date().isoformat():
            continue
        r = rules[0]
        J._alert(f"📅 Nuevo en tu calendario: {_ev_what(ev)} ({str(ev.get('inicio', ''))[:16].replace('T', ' ')}).", r.get("celular"))
        if r.get("vispera"):
            A.data["recordados"].append({"k": k, "dia": str(ev.get("inicio", ""))[:10], "que": _ev_what(ev), "celular": r.get("celular"), "hecho": False})
        n += 1
    del seen[:-600]
    tomorrow = (now.date() + datetime.timedelta(days=1)).isoformat()
    if now.hour >= 18:
        for x in A.data["recordados"]:
            if not x["hecho"] and x["dia"] == tomorrow:
                x["hecho"] = True
                J._alert(f"⏰ Mañana: {x['que']}.", x.get("celular"))
                n += 1
    A.data["recordados"] = [x for x in A.data["recordados"] if x["dia"] >= now.date().isoformat()]
    return n


def price_now(asset):
    trm, fx, crypto = J.fx_rates(asset in ("BTC", "ETH"))
    if not trm:
        return None
    if asset == "USD":
        return float(trm[0])
    import divisas
    return divisas.cop_per(asset, trm[0], fx, crypto)


def check_prices():
    n = 0
    for r in [r for r in A.data["reglas"] if r["tipo"] == "precio"]:
        try:
            v = J.price_now(r["activo"])
        except Exception:
            continue
        last = _auto["last_price"].get(r["id"], r.get("ultimo_valor"))
        if A.price_crossed(r, v, last):
            J._alert(f"💱 {A.describe(r).split(',')[0].replace('Cuando ', '').capitalize()}: ahora está a ${v:,.0f}.".replace(",", "."), r.get("celular"))
            n += 1
        _auto["last_price"][r["id"]] = v
        r["ultimo_valor"] = v
    return n


def auto_tick(now=None):
    """Una pasada de todo (el hilo la llama cada minuto)."""
    now = now or datetime.datetime.now()
    t = time.time()
    if any(r["tipo"] == "correo" for r in A.data["reglas"]) and t - _auto["t_mail"] > 300:
        _auto["t_mail"] = t
        try:
            check_mail(J.mail_fetch_recent(days=1))
        except Exception as e:
            J.log_terminal(f"Avisos de correo: {e}", "AVISO")
    try:
        check_calendar(calendario.cache.get("events") or [], now)
    except Exception as e:
        J.log_terminal(f"Avisos del calendario: {e}", "AVISO")
    if any(r["tipo"] == "precio" for r in A.data["reglas"]) and t - _auto["t_price"] > 900:
        _auto["t_price"] = t
        check_prices()
    _auto["seeded"] = True
    for r in A.data["recurrentes"]:
        if A.due(r, now) and len(J.project_runs) < J.MAX_PROJECTS:
            r["ultimo"] = now.date().isoformat()
            A.save()
            threading.Thread(target=J.run_recurring, args=(r,), daemon=True, name="recurrente").start()
    A.save()


def run_recurring(r):
    """Corre el proyecto programado y lo compara con la vez anterior."""
    st = proyectos.new(r["pedido"], r["plan"], J.settings["output_dir"])
    st["recurrente"] = r["id"]
    J.run_project(st)
    rep = st.get("informe")
    if not rep:
        return st
    text = proyectos.report_text(rep)
    prev = r.get("ultimo_texto") or ""
    if prev:
        try:
            cmp = J.ai_chat([{"role": "user", "content": A.compare_prompt(prev, text, r["pedido"])}], max_tokens=1000).strip()
            rep["secciones"].insert(0, {"titulo": "Frente a la vez anterior", "texto": cmp})
            J._report_docx(st, rep)
            proyectos.save(st)
            J._alert(f"🔁 {st['nombre']}: {cmp[:600]}", True)
        except Exception as e:
            J.log_terminal(f"Comparar con la vez anterior: {getattr(e, 'why', e)}", "AVISO")
    r["ultimo_texto"] = text[:12000]
    r["veces"] = r.get("veces", 0) + 1
    A.save()
    return st


def _auto_worker():
    while True:
        time.sleep(60)
        if not J.net.get("watch", True):
            continue
        try:
            auto_tick()
        except Exception as e:
            J.log_terminal(f"Automáticos: {e}", "AVISO")


_AUTO_LIST = re.compile(r"\b(?:mis|cuales son mis|que)\s+(?:avisos? automaticos?|avisos? por evento|reglas de avisos?|proyectos? (?:que se repiten|recurrentes|programados))\b")
_AUTO_DEL = re.compile(r"\b(?:borra|elimina|quita|cancela)\s+(?:el\s+)?(aviso automatico|aviso por evento|proyecto programado|proyecto recurrente)\s+(\d+)\b")


def auto_voice(text, t):
    if _AUTO_LIST.search(t):
        rs = A.data["reglas"]
        rc = A.data["recurrentes"]
        if not rs and not rc:
            J.reply("No tienes avisos por evento ni proyectos programados. Prueba: «cuando me llegue un correo de la coordinadora, "
                    "avísame al celular» o «cada lunes a las 7, investiga el precio de la canasta y hazme un informe».", "AVISOS")
        else:
            J.reply(" ".join([f"Aviso {r['id']}: {A.describe(r)}" for r in rs] +
                             [f"Proyecto programado {r['id']}: «{r['pedido']}», {A.when_text(r)}." for r in rc]) +
                    " Para quitar uno: «borra el aviso automático 2» o «borra el proyecto programado 1».", "AVISOS")
        return True
    m = _AUTO_DEL.search(t)
    if m:
        if "aviso" in m.group(1):
            hit = A.remove_rule(m.group(2))
            J.reply(f"Quité el aviso: {A.describe(hit)}" if hit else "No encontré ese aviso. Di «mis avisos automáticos».", "AVISOS")
        else:
            hit = next((x for x in A.data["recurrentes"] if str(x["id"]) == m.group(2)), None)
            if hit:
                A.data["recurrentes"].remove(hit)
                A.save()
            J.reply(f"Quité el proyecto programado «{hit['pedido']}»." if hit else "No encontré ese proyecto programado.", "AVISOS")
        return True
    r = A.parse_rule(text)                                # (con el texto tal cual: «4.200» no es «4 200»)
    if r:
        if r["tipo"] == "correo" and not J.mail_method():
            J.reply("Para avisarte de correos necesito tu correo conectado: di «conecta el correo».", "AVISOS")
            return True
        if r["tipo"] == "calendario" and not J.cal_configured():
            J.reply("Para avisarte de eventos nuevos necesito tu calendario: conéctalo en Ajustes › Cuentas y mensajes.", "AVISOS")
            return True
        r = A.add_rule(r)
        phone = ""
        if r.get("celular") and not (J.telegram_ready() or J.whatsapp_ready()):
            phone = " Ojo: para el celular necesito Telegram o WhatsApp conectado (di «conecta el WhatsApp»)."
        J.reply("Listo. " + A.describe(r) + phone, "AVISOS")
        return True
    rr = A.parse_recurring(text)
    if rr:
        if J.state.get("ai") != "ok":
            J.reply("Para los proyectos programados necesito la IA conectada.", "AVISOS")
            return True
        J.reply(f"Lo planeo una vez y te digo los pasos; luego lo hago {A.when_text(rr)} y lo comparo con la vez anterior.", "AVISOS")
        J.start_job("Planeando el proyecto programado", lambda: plan_recurring(rr), "recurrente")
        return True
    return False


def plan_recurring(rr):
    try:
        general = J.current_mode() == "general"
        raw = J.ai_chat([{"role": "user", "content": proyectos.plan_prompt(rr["pedido"], J._user_ctx(rr["pedido"])[:1200], general)}],
                        json_mode=True, max_tokens=1500)
        plan = proyectos.validate_plan(J._extract_json(raw), rr["pedido"])
    except Exception as e:
        J.reply(f"No pude planearlo: {getattr(e, 'why', e)}.", "AVISOS")
        return

    def ok():
        item = dict(rr, plan=plan, id=max([x.get("id", 0) for x in A.data["recurrentes"]] + [0]) + 1, veces=0, ultimo="")
        A.data["recurrentes"].append(item)
        A.save()
        J.reply(f"Programado: «{plan['nombre']}», {A.when_text(item)}. Cada vez te mando el informe al celular y qué cambió frente a "
                "la anterior. Para quitarlo: «borra el proyecto programado " + str(item["id"]) + "».", "AVISOS")
    J.request_approval("proyecto", f"Programar «{plan['nombre']}» {A.when_text(rr)}", proyectos.spoken_plan(plan), on_ok=ok,
                       on_no=lambda: J.reply("Vale, no lo programo.", "AVISOS"),
                       say=proyectos.spoken_plan(plan) + f" Lo haría {A.when_text(rr)}. ¿Lo programo? Di «sí» o «no».")


def auto_start():
    A.configure(J.CONFIG_DIR)
    threading.Thread(target=_auto_worker, daemon=True, name="automaticos").start()


__all__ = ['_AUTO_DEL', '_AUTO_LIST', '_alert', '_auto', '_auto_worker', 'auto_start', 'auto_tick', 'auto_voice', 'check_calendar',
           'check_mail', 'check_prices', 'plan_recurring', 'price_now', 'run_recurring']
