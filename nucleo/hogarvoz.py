"""Mi día a día (12.15): lo de hogar.py por voz, los avisos, los recibos, el menú, el audio y los viajes.

- Vencimientos: «el SOAT se vence el 15 de marzo», «¿qué se me vence este mes?», «¿cuándo declaro renta?».
- Recibos: el clip del HUD → «Registrar recibo» (o «registra el recibo»): valor, fecha, negocio y garantía.
- Medicamentos: «recuérdame tomar losartán a las 8 y a las 8 de la noche», «ya me la tomé», «compré 30 pastillas de losartán».
- Citas: «tengo cita con el odontólogo el 20 a las 3 de la tarde».
- Cumpleaños: «el cumpleaños de mi mamá es el 3 de mayo», «escríbele un mensaje de cumpleaños a Ana», «ideas de regalo para Ana».
- Presupuesto: «mi presupuesto de comida es de 800 mil», «¿cómo voy con el presupuesto?», «¿qué suscripciones tengo?».
- Comidas: «arma el menú de la semana», «¿qué cocino con arroz, pollo y tomate?».
- Audio: «convierte este PDF en audio» (el archivo que subiste) o «convierte en audio https://…».
- Viajes: «me voy a Cartagena del 20 al 24 de noviembre», «mi vuelo sale a las 6 de la mañana».
"""
import asyncio
import datetime
import json
import os
import re
import tempfile
import threading
import time

import adjuntos
import documentos
import hogar as H
import infodia
import investigar
import vidadiaria as vd
from nucleo import J

D = datetime.date
_hg = {"started": False, "win": None, "last_receipt": None}
_CATS = {"comida": "Comida", "mercado": "Comida", "alimentacion": "Comida", "transporte": "Transporte", "servicios": "Servicios", "salud": "Salud",
         "educacion": "Educación", "hogar": "Hogar", "casa": "Hogar", "ocio": "Ocio", "salidas": "Ocio", "diversion": "Ocio", "otros": "Otros"}
_CUR = {"estados unidos": "USD", "united states": "USD", "espana": "EUR", "francia": "EUR", "italia": "EUR", "alemania": "EUR", "portugal": "EUR",
        "mexico": "MXN", "brasil": "BRL", "argentina": "ARS", "chile": "CLP", "peru": "PEN", "ecuador": "USD", "panama": "USD", "reino unido": "GBP",
        "canada": "CAD", "japon": "JPY"}


def _say(msg, origin="MI DÍA", telegram=False):
    J.notify(msg, origin)
    if telegram and J.settings.get("telegram_alerts") and J.telegram_ready():
        threading.Thread(target=J.telegram_send, args=("🔔 " + msg,), daemon=True).start()


# ============================================================================ 1. VENCIMIENTOS
_V_ADD = re.compile(r"^(?:jarvis[ ,]+)?(?:anota|guarda|apunta|registra|recuerdame|avisame)?\s*(?:que\s+)?(?:el |la |los |las |mi |mis )?"
                    r"(.+?)\s+(?:se\s+)?(?:me\s+)?(?:vence|vencen|caduca|caducan|expira|expiran|hay que renovar(?:lo|la)?)\s+(.+)$")
_V_ASK = re.compile(r"\bque (?:se me vence|se vence|vence|documentos? (?:se me )?vencen?)\b|\bmis vencimientos\b|\bque tengo por renovar\b|"
                    r"\b(?:proximos|siguientes) vencimientos\b")
_V_WHEN = re.compile(r"^(?:jarvis[ ,]+)?cuando (?:se )?(?:me )?(?:vence|caduca|expira|hay que renovar)\s+(?:el |la |mi |los |las )?(.+?)\??$")
_V_DEL = re.compile(r"^(?:jarvis[ ,]+)?(?:borra|elimina|quita)\s+(?:el\s+)?vencimiento\s+(?:del?\s+|de la\s+)?(.+)$")
_V_RENOVE = re.compile(r"^(?:jarvis[ ,]+)?ya renove\s+(?:el |la |mi )?(.+?)(?:\s+(?:hasta|vence|y vence|nuevo vencimiento)\s+(.+))?$")
_RENTA = re.compile(r"\b(?:cuando|que dia|fecha (?:de|para)) (?:declaro|tengo que declarar|debo declarar|me toca declarar|(?:la )?declaracion de) renta\b|"
                    r"\bcuando (?:es|vence) (?:mi |la )?declaracion de renta\b")
_DIGITS = re.compile(r"\b(?:los )?(?:dos )?ultimos (?:dos )?digitos de mi (?:cedula|nit) son (\d)\s?(\d)\b")


def venc_voice(text, t):
    m = _DIGITS.search(t)
    if m:
        H.data.setdefault("avisados", {})["perfil:digitos"] = m.group(1) + m.group(2)
        H.save()
        J.reply(f"Guardado: los últimos dígitos de tu cédula son {m.group(1)}{m.group(2)}. Pregúntame «¿cuándo declaro renta?».", "VENCIMIENTOS")
        return True
    if _RENTA.search(t):
        dig = H.data.get("avisados", {}).get("perfil:digitos")
        if not dig:
            J.reply("Dime los dos últimos dígitos de tu cédula («los últimos dígitos de mi cédula son 45») y busco tu fecha en el calendario de la DIAN. "
                    "Cuando la sepas, di «la declaración de renta se vence el …» y te aviso con tiempo.", "VENCIMIENTOS")
            return True
        J.web_search(H.renta_digits_query(D.today().year, dig))
        return True
    if _V_ASK.search(t):
        items = H.venc_soon(within=31 if "mes" in t else 60)
        if not items:
            n = len(H.data["venc"])
            J.reply("No se te vence nada en los próximos dos meses." + (" Di «el SOAT se vence el …» para agregar uno." if not n else ""), "VENCIMIENTOS")
            return True
        J.reply(" ".join(H.venc_text(x, left) for x, left in items[:6]), "VENCIMIENTOS")
        return True
    m = _V_WHEN.match(t)
    if m:
        x = H.find("venc", m.group(1))
        if x:
            J.reply(H.venc_text(x, (D.fromisoformat(x["fecha"]) - D.today()).days), "VENCIMIENTOS")
            return True
        return False
    m = _V_DEL.match(t)
    if m:
        x = H.find("venc", m.group(1))
        J.reply(f"Borré el vencimiento de {x['nombre']}." if x and H.remove("venc", x["id"]) else "No encontré ese vencimiento.", "VENCIMIENTOS")
        return True
    m = _V_RENOVE.match(t)
    if m and H.find("venc", m.group(1)):
        x = H.find("venc", m.group(1))
        d = H.parse_date(m.group(2) or "", future=True) if m.group(2) else H.add_months(D.fromisoformat(x["fecha"]), 12)
        x["fecha"] = d.isoformat()
        H.save()
        J.reply(f"Listo: {x['nombre']} ahora vence {H.spoken_date(d)}.", "VENCIMIENTOS")
        return True
    m = _V_ADD.match(t)
    if m:
        d = H.parse_date(m.group(2))
        name = m.group(1).strip()
        if not d or len(name) > 60 or re.search(r"\b(?:plazo|tiempo|paciencia)\b", name):
            return False
        if H.venc_type(name) == "otro" and not re.match(r"^(?:jarvis[ ,]+)?(?:anota|guarda|apunta|registra|recuerdame|avisame)\b", t):
            return False                                  # «la tarea vence el viernes» no es un documento tuyo
        x = H.venc_add(name, d)
        J.reply(f"Anotado: {x['nombre']} vence {H.spoken_date(d)}. Te aviso 30 días, 7 días y un día antes.", "VENCIMIENTOS")
        return True
    return False


# ============================================================================ 2. RECIBOS
def _extract_receipt(it):
    text, img = J.content_for_ai(it, 12000)
    if img is not None:
        raw = J._vision_text(H.RECEIPT_PROMPT, img, 900)
    else:
        raw = J.ai_chat([{"role": "user", "content": H.RECEIPT_PROMPT + "\n\nRecibo:\n" + text[:8000]}], json_mode=True, max_tokens=700)
    return H.parse_receipt(J._extract_json(raw))


def receipt_from(it):
    """Lee el recibo (foto o PDF que subiste) y lo anota en tus gastos; si es un aparato, guarda la garantía. → mensaje."""
    r = _extract_receipt(it)
    concepto = r["concepto"] if not r["negocio"] or r["negocio"].lower() in r["concepto"].lower() else f"{r['concepto']} ({r['negocio']})"
    g = vd.add_expense(r["total"], concepto, r["fecha"])
    _hg["last_receipt"] = g["id"]
    msg = f"Anoté {vd.money(r['total'])} en {g['concepto']} ({g['categoria']}), del {r['fecha'].day} de {H.MESES[r['fecha'].month - 1]}."
    if r["garantia"] and r["meses"]:
        until = H.add_months(r["fecha"], r["meses"])
        H.venc_add(f"Garantía {r['producto'] or r['concepto']}", until, "garantia", nota=f"Comprado en {r['negocio']}" if r["negocio"] else "")
        msg += f" Guardé la garantía hasta {H.spoken_date(until)}; guarda la factura."
    tot, _by, _n = vd.spent("mes")
    return msg + f" Este mes llevas {vd.money(tot)}. Si leí mal el valor, di «borra el último gasto»."


_R_VOICE = re.compile(r"\b(?:registra|anota|guarda|lee)(?:me)?\s+(?:este|el|esta|la|ese|esa)\s+(?:recibo|factura|tiquete|cuenta de cobro)\b")
_EXPORT = re.compile(r"\b(?:exporta|pasa|saca|descarga)(?:me)?\s+(?:mis\s+|los\s+)?gastos(?:\s+del\s+mes(?:\s+pasado)?|\s+de\s+este\s+mes)?\s+(?:a|en)\s+(?:un\s+)?excel\b")


def receipt_voice(text, t):
    if _R_VOICE.search(t):
        its = [i for i in adjuntos.recent(1800, 6) if i["tipo"] in ("imagen", "pdf", "texto", "word")]
        if not its:
            J.reply("Sube la foto del recibo con el clip del HUD (o desde Mi día) y dime «registra el recibo».", "GASTOS")
            return True
        it = its[-1]
        J.reply("Leyendo el recibo…", "GASTOS")

        def work():
            try:
                J.reply(receipt_from(it), "GASTOS")
            except ValueError as e:
                J.reply(f"No pude leer el recibo: {e}", "GASTOS")
            except J.AIError as e:
                J.reply(J.ai_error_reply(e), "GASTOS")
        J.start_job("Leyendo el recibo", work, "recibo")
        return True
    if _EXPORT.search(t):
        path = export_month(D.today() if "pasado" not in t else D.today().replace(day=1) - datetime.timedelta(days=1))
        if not path:
            J.reply("No hay gastos anotados en ese mes.", "GASTOS")
            return True
        J.generated_files.add(path)
        if J.IS_WIN:
            try:
                os.startfile(path)
            except OSError:
                pass
        J.reply("Listo: tus gastos del mes en Excel, en la carpeta Documentos.", "GASTOS")
        return True
    return False


def export_month(day):
    a = day.replace(day=1).isoformat()
    b = (H.add_months(day.replace(day=1), 1) - datetime.timedelta(days=1)).isoformat()
    items = [g for g in vd.data["gastos"] if a <= g["fecha"] <= b]
    if not items:
        return ""
    rows = [[g["fecha"], g["concepto"], g["categoria"], g["monto"]] for g in sorted(items, key=lambda x: x["fecha"])]
    rows.append(["", "TOTAL", "", sum(g["monto"] for g in items)])
    m = {"titulo": f"Gastos {H.MESES[day.month - 1]} {day.year}", "columnas": ["Fecha", "Concepto", "Categoría", "Valor (COP)"], "filas": rows}
    return documentos.build("excel", "table", m, J.settings["output_dir"])


# ============================================================================ 3. MEDICAMENTOS Y CITAS
_MEDWORD = r"pastillas?|tabletas?|capsulas?|jarabe|gotas|inhalador|insulina|medicamentos?|medicina|remedio|antibiotico|\d+\s?(?:mg|ml|mcg)"
_M_ADD = re.compile(r"^(?:jarvis[ ,]+)?(?:recuerdame|avisame(?: para)?|anota(?: que)?|programa(?: el recordatorio de)?)\s+(?:que\s+)?(?:debo\s+|tengo que\s+|hay que\s+)?"
                    r"(?:tomar(?:me)?|darle|dar|aplicar(?:me|le)?|ponerme|ponerle)\s+(.+)$")
_M_TAKEN = re.compile(r"^(?:jarvis[ ,]+)?(?:ya\s+)?(?:me\s+(?:la|lo|las|los)\s+tome|me\s+tome\s+(?:el |la |los |las |mi |mis )?(.+)|"
                      r"(?:le\s+)?di\s+(?:el |la |los |las |su |sus )?(.+?)(?:\s+a\s+.+)?|ya\s+(?:le\s+)?(?:la|lo|las|los)\s+di)$")
_M_ASK = re.compile(r"\b(?:que|cuales) (?:medicamentos|pastillas|remedios|medicinas) (?:tengo|tomo|me tomo|me toca)\b|\bmis (?:medicamentos|pastillas)\b|"
                    r"\b(?:ya )?me tome (?:todas )?(?:las pastillas|los medicamentos)( de hoy)?\b|\bque me (?:toca|falta) tomar\b")
_M_STOCK = re.compile(r"^(?:jarvis[ ,]+)?(?:compre|tengo|me quedan|quedan|traje)\s+(\d+)\s+(?:pastillas|tabletas|capsulas|dosis|sobres)\s+(?:de|del)\s+(.+)$")
_M_DEL = re.compile(r"^(?:jarvis[ ,]+)?(?:ya no (?:tomo|me tomo|le doy)|borra el medicamento|quita el medicamento|deje de tomar|termine (?:el|la))\s+(?:el |la |los |las )?(.+)$")
_C_WORD = r"medic[oa]|doctor|doctora|odontolog[oa]|dentista|eps|dermatolog[oa]|pediatra|ginecolog[oa]|oftalmolog[oa]|optometr[ai]|cardiolog[oa]|psicolog[oa]|" \
          r"fisioterapia|terapia|laboratorio|examen(?:es)? de (?:sangre|laboratorio|orina)|vacuna|control (?:medico|prenatal|de (?:presion|azucar|crecimiento))|especialista|cita medica|odontologia|nutricionista"
_C_ADD = re.compile(rf"^(?:jarvis[ ,]+)?(?:tengo|anota|agenda|apunta|recuerdame)?\s*(?:que tengo\s+)?(?:una\s+)?(?:cita|consulta|control|examen|vacuna)\b(.+)$")
_C_ASK = re.compile(r"\b(?:que|cuales) citas (?:medicas )?tengo\b|\bmis citas(?: medicas)?\b|\bcuando (?:es|tengo) (?:la|mi) cita\b")


def _orig(text, piece):
    """El trozo como lo escribiste (con tildes y mayúsculas): «losartan» → «losartán»."""
    words, want = str(text).split(), H.norm(piece).split()
    n = len(want)
    for i in range(len(words) - n + 1):
        if H.norm(" ".join(words[i:i + n])).split() == want:
            return " ".join(w.strip(".,;:!?¿¡") for w in words[i:i + n])
    return piece


def _persona(t):
    m = re.search(r"\b(?:a|para|de)\s+mi\s+(mama|papa|hijo|hija|esposa|esposo|abuela|abuelo|hermano|hermana|novia|novio|tia|tio|suegra|suegro|bebe|perro|gato)\b", t)
    return m.group(1) if m else ""


def _med_times(t):
    m = re.search(r"\bcada\s+(\d{1,2}|ocho|seis|doce|cuatro)\s+horas?(?:\s+desde\s+las\s+(.+?))?(?=\s+(?:por|durante|tengo|me quedan|para|a mi)\b|$)", t)
    if m:
        n = {"ocho": 8, "seis": 6, "doce": 12, "cuatro": 4}.get(m.group(1)) or int(m.group(1))
        first = H.parse_time("a las " + m.group(2)) if m.group(2) else "08:00"
        if first and m.group(2) and not re.search(r"tarde|noche|pm|p m", m.group(2)) and int(first[:2]) >= 13:
            first = f"{int(first[:2]) - 12:02d}{first[2:]}"          # «desde las 6» de un tratamiento: de la mañana
        return H.every_hours(n, first or "08:00")
    hours = []
    for seg in re.findall(r"a las\s+\d{1,2}(?:\s+y\s+(?:media|cuarto)|\s+\d{2})?(?:\s+(?:de la manana|de la tarde|de la noche|am|pm))?", t):
        h = H.parse_time(seg)
        if h:
            hours.append(h)
    if re.search(r"\b(?:en|por) la manana\b", t) and not hours:
        hours.append("08:00")
    if re.search(r"\b(?:en|por) la noche\b", t) and len(hours) < 2:
        hours.append("20:00")
    if re.search(r"\bal mediodia\b", t):
        hours.append("12:00")
    return sorted(set(hours))


def med_voice(text, t):
    m = _M_STOCK.match(t)
    if m:
        med = H.find("meds", m.group(2))
        if med:
            med["stock"] = int(med.get("stock") or 0) + int(m.group(1)) if t.startswith(("compre", "traje", "jarvis compre")) else int(m.group(1))
            H.save()
            dl = H.med_days_left(med)
            J.reply(f"Listo: {med['nombre']} tiene {med['stock']} pastillas" + (f", alcanzan para {dl} días." if dl is not None else "."), "MEDICAMENTOS")
            return True
        return False
    m = _M_ADD.match(t)
    if m:
        body = m.group(1)
        times = _med_times(body)
        daily = re.search(r"\b(?:todos los dias|cada dia|diario|diariamente|cada \d+ horas|cada (?:ocho|seis|doce|cuatro) horas)\b", body)
        if not times or not (daily or re.search(rf"\b(?:{_MEDWORD})\b", body) or len(times) >= 2):
            return False                                  # «recuérdame tomar agua a las 3» lo atienden los recordatorios
        name = re.split(r"\s+(?:cada|a las|todos los dias|cada dia|diario|en la manana|en la noche|por la manana|por la noche|al mediodia|por \d+|durante|"
                        r"tengo|me quedan|a mi|para mi|y a las)\b", body)[0]
        name = re.sub(r"^(?:el|la|los|las|mi|mis|su|sus|una|un)\s+", "", name).strip(" .,")
        dosis = (re.search(rf"\b(\d+\s?(?:mg|ml|mcg|gotas|tabletas?|pastillas?|capsulas?)|media pastilla|una pastilla|dos pastillas)\b", body) or [None, ""])[1] or ""
        name = re.sub(rf"\s*\b{re.escape(dosis)}\b", "", name).strip() if dosis else name
        name = re.sub(r"^(?:de|del)\s+|\s+(?:de|del|y)$", "", name).strip() or "medicamento"
        name = _orig(text, name)
        name = name[:1].upper() + name[1:]
        st = re.search(r"\b(?:tengo|me quedan|quedan)\s+(\d+)\b", body)
        dias = re.search(r"\b(?:por|durante)\s+(\d+)\s+dias\b", body)
        try:
            med = H.med_add(name, times, dosis, _persona(body), int(st.group(1)) if st else None, 1,
                            D.today() + datetime.timedelta(days=int(dias.group(1)) - 1) if dias else None)
        except ValueError as e:
            J.reply(str(e), "MEDICAMENTOS")
            return True
        quien = f" a tu {med['persona']}" if med["persona"] else ""
        J.reply(f"Listo: te aviso para {'darle' if quien else 'tomar'} {med['nombre']}{quien} a las " + ", ".join(H.hour_spoken(h) for h in med["horas"])
                + (f", hasta el {D.fromisoformat(med['hasta']).day} de {H.MESES[D.fromisoformat(med['hasta']).month - 1]}" if med.get("hasta") else "")
                + ". Cuando te la tomes, di «ya me la tomé»." + (" Dime cuántas pastillas tienes para avisarte cuándo comprar." if med.get("stock") is None else ""),
                "MEDICAMENTOS")
        return True
    m = _M_TAKEN.match(t)
    if m and H.data["meds"]:
        named = (m.group(1) or m.group(2) or "").strip()
        med = H.find("meds", named) if named else None
        if named and not med:
            return False
        if not med:
            now = datetime.datetime.now()
            pend = [x for x in H.data["meds"] if H.med_active(x) and H.med_last_due(x, now) not in x.get("tomas", {}).get(now.date().isoformat(), [])
                    and H.med_last_due(x, now) <= now.strftime("%H:%M")]
            med = pend[0] if pend else None
        if not med:
            J.reply("Ya tenías todo marcado por ahora.", "MEDICAMENTOS")
            return True
        h, stock = H.med_taken(med)
        dl = H.med_days_left(med)
        J.reply(f"Anotado: {med['nombre']} de las {H.hour_spoken(h)}." + (f" Quedan {stock} pastillas ({dl} días)." if stock is not None else ""), "MEDICAMENTOS")
        return True
    if _M_ASK.search(t):
        if not H.data["meds"]:
            J.reply("No tienes medicamentos anotados. Di «recuérdame tomar losartán a las 8 de la mañana todos los días».", "MEDICAMENTOS")
            return True
        today = D.today().isoformat()
        parts = []
        for x in H.data["meds"]:
            if not H.med_active(x):
                continue
            done = x.get("tomas", {}).get(today, [])
            falta = [h for h in x["horas"] if h not in done]
            parts.append(f"{x['nombre']}" + (f" ({x['persona']})" if x.get("persona") else "") + ": "
                         + ("todo tomado hoy" if not falta else "falta " + ", ".join(H.hour_spoken(h) for h in falta))
                         + (f", quedan {x['stock']} pastillas" if x.get("stock") is not None else ""))
        J.reply("; ".join(parts) + ".", "MEDICAMENTOS")
        return True
    m = _M_DEL.match(t)
    if m:
        med = H.find("meds", m.group(1))
        if med:
            H.remove("meds", med["id"])
            J.reply(f"Quité {med['nombre']}: ya no te aviso.", "MEDICAMENTOS")
            return True
    return False


def cita_voice(text, t):
    if _C_ASK.search(t):
        cs = H.citas_soon(within=30)
        J.reply(" ".join(H.cita_text(c, H.spoken_date(D.fromisoformat(c["fecha"]))) for c in cs[:5]) if cs else "No tienes citas en los próximos 30 días.",
                "CITAS")
        return True
    m = _C_ADD.match(t)
    if not m or not re.search(rf"\b(?:{_C_WORD})\b", t):
        return False
    d = H.parse_date(m.group(1))
    if not d:
        return False
    body = m.group(1)
    que = re.split(r"\s+(?:el\s+\d|para el|manana|pasado manana|hoy|a las|en la|en el)\b", body)[0].strip(" .,") or "cita médica"
    que = re.sub(r"^(?:con|de|en|para)\s+", "", que)
    lugar = (re.search(r"\ben\s+(?:la|el)\s+((?:eps|clinica|hospital|centro|consultorio|laboratorio)[\w\s]{0,40}?)(?=\s+(?:el|a las|manana)|$)", body) or [None, ""])[1]
    que = _orig(text, que)
    c = H.cita_add(("Cita " if not H.norm(que).startswith(("cita", "control", "examen", "vacuna")) else "") + que, d, H.parse_time(body), lugar.strip(), _persona(body))
    J.reply(f"Anotada: {c['que']} {H.spoken_date(d)}" + (f" a las {H.hour_spoken(c['hora'])}" if c.get("hora") else "")
            + ". Te aviso la víspera y el mismo día.", "CITAS")
    return True


# ============================================================================ 4. CUMPLEAÑOS
_B_ADD = re.compile(rf"^(?:jarvis[ ,]+)?(?:anota|guarda|apunta|recuerda)?\s*(?:que\s+)?(?:el\s+)?cumpleanos\s+de\s+(?:mi\s+)?(.+?)\s+es\s+(?:el\s+)?(\d{{1,2}}|primero)\s+de\s+({H._MES_RE})(?:\s+de\s+(\d{{4}}))?$|"
                    rf"^(?:jarvis[ ,]+)?(?:mi\s+)?(.+?)\s+cumple(?:\s+anos)?\s+(?:el\s+)?(\d{{1,2}}|primero)\s+de\s+({H._MES_RE})(?:\s+de\s+(\d{{4}}))?$")
_B_ASK = re.compile(r"\b(?:que|cuales|proximos) cumpleanos\b|\bquien cumple (?:anos )?(?:este mes|pronto|esta semana|hoy)\b|\bcumpleanos (?:que vienen|del mes)\b")
_B_WHEN = re.compile(r"^(?:jarvis[ ,]+)?cuando (?:es el cumpleanos de|cumple(?: anos)?)\s+(?:mi\s+)?(.+?)\??$")
_B_MSG = re.compile(r"\b(?:escribe(?:le|me)?|hazme|redacta(?:me)?|preparame)\s+(?:un\s+)?(?:mensaje|saludo|felicitacion)(?:\s+de\s+cumpleanos)?\s+(?:para|a)\s+(?:mi\s+)?(.+?)$")
_B_GIFT = re.compile(r"\bideas? (?:de|para) (?:un\s+)?regalo (?:para|a)\s+(?:mi\s+)?(.+?)(?:\s+(?:de|por|hasta|con)\s+(?:unos?\s+)?(\d[\d.,]*\s*(?:mil|millones?)?)(?:\s+pesos)?)?$")


def cumple_voice(text, t):
    m = _B_ADD.match(t)
    if m:
        g = m.groups()
        name, day, mon, year = (g[0], g[1], g[2], g[3]) if g[0] else (g[4], g[5], g[6], g[7])
        if len(name) > 40:
            return False
        mes = (H.MESES.index(mon) if mon in H.MESES else 8) + 1
        rel = {"mama": "Mamá", "papa": "Papá", "tia": "Tía", "tio": "Tío", "bebe": "Bebé", "abuela": "Abuela", "abuelo": "Abuelo"}
        shown = rel.get(name.strip()) or _orig(text, name.strip())
        c = H.cumple_add(shown[:1].upper() + shown[1:], mes, 1 if day == "primero" else int(day), int(year) if year else None,
                         name if name in ("mama", "papa", "hijo", "hija", "esposa", "esposo", "abuela", "abuelo", "hermano", "hermana") else "")
        nd = H.next_birthday(c)
        J.reply(f"Anotado: {c['nombre']} cumple {H.spoken_date(nd)}" + (f" ({H.age_on(c, nd)} años)" if c.get("anio") else "")
                + ". Te aviso 3 días antes y ese día, con un mensaje listo si quieres.", "CUMPLEAÑOS")
        return True
    if _B_ASK.search(t):
        items = H.cumples_soon(within=7 if "semana" in t else 31)
        J.reply(("Próximos cumpleaños: " + "; ".join(f"{c['nombre']} {H.spoken_date(d)}" for c, d, _ in items[:8]) + ".") if items
                else "No hay cumpleaños en los próximos 30 días." + ("" if H.data["cumples"] else " Di «el cumpleaños de mi mamá es el 3 de mayo»."), "CUMPLEAÑOS")
        return True
    m = _B_WHEN.match(t)
    if m:
        c = H.find("cumples", m.group(1))
        if c:
            d = H.next_birthday(c)
            J.reply(f"{c['nombre']} cumple {H.spoken_date(d)}" + (f": {H.age_on(c, d)} años." if c.get("anio") else "."), "CUMPLEAÑOS")
            return True
        return False
    m = _B_MSG.search(t)
    if m and not re.search(r"cumple|felicita|saludo", t):     # «un mensaje para el arrendador» no es de cumpleaños
        c = H.find("cumples", m.group(1))
        nd = H.next_birthday(c) if c and c.get("mes") else None
        if not nd or (nd - D.today()).days > 3:
            m = None
    if m:
        c = H.find("cumples", m.group(1)) or {"nombre": m.group(1).strip().capitalize(), "relacion": "", "anio": None}
        d = H.next_birthday(c) if c.get("mes") else D.today()
        try:
            msg = J.ai_chat([{"role": "user", "content": H.greeting_prompt(c, d)}], max_tokens=200).strip().strip('"')
        except Exception:
            msg = f"¡Feliz cumpleaños, {c['nombre']}! Que este nuevo año te traiga salud, alegrías y muchos momentos bonitos. Un abrazo grande."
        J.reply(f"Te propongo este mensaje (envíalo tú): «{msg}»", "CUMPLEAÑOS")
        J.card("cumple", f"Para {c['nombre']}", msg, "🎂", secs=30)
        return True
    m = _B_GIFT.search(t)
    if m:
        c = H.find("cumples", m.group(1)) or {"nombre": m.group(1).strip(), "relacion": ""}
        tope = vd.parse_amount(m.group(2)) if m.group(2) else None
        try:
            ideas = J.ai_chat([{"role": "user", "content": H.gift_prompt(c, vd.money(tope) if tope else None)}], max_tokens=400).strip()
        except J.AIError as e:
            J.reply(J.ai_error_reply(e), "CUMPLEAÑOS")
            return True
        J.reply(f"Ideas de regalo para {c['nombre']}:\n{ideas}", "CUMPLEAÑOS")
        return True
    return False


# ============================================================================ 5. PRESUPUESTO Y SUSCRIPCIONES
_BU_SET = re.compile(r"^(?:jarvis[ ,]+)?(?:mi\s+)?(?:presupuesto|tope|limite)\s+(?:de|para|en)\s+(\w+)\s+(?:es|sera|va a ser|queda en)\s+(?:de\s+)?(.+?)(?:\s+(?:al|por|cada)\s+mes)?$|"
                     r"^(?:jarvis[ ,]+)?(?:pon|ponme|define|fija)\s+(?:un\s+)?(?:presupuesto|tope|limite)\s+(?:de\s+)?(.+?)\s+(?:en|para)\s+(\w+)(?:\s+(?:al|por|cada)\s+mes)?$")
_BU_ASK = re.compile(r"\bcomo (?:voy|va|vamos) (?:con|en) (?:el|mi) presupuesto\b|\bmi presupuesto\b|\bme (?:estoy pasando|pase) del presupuesto\b")
_SUB_ASK = re.compile(r"\b(?:que|cuales) suscripciones\b|\bmis suscripciones\b|\bcuanto (?:pago|gasto|se me va) en suscripciones\b|\bcobros (?:mensuales|que se repiten)\b")


def _cat(word):
    w = H.norm(word)
    return _CATS.get(w) or (vd.category(w) if vd.category(w) != "Otros" else ("Otros" if w == "otros" else ""))


def budget_voice(text, t):
    m = _BU_SET.match(vd.norm(text))
    if m:
        cat_w, amt_w = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
        cat, amt = _cat(cat_w), vd.parse_amount(amt_w)
        if not cat or not amt:
            J.reply("Dime la categoría (comida, transporte, servicios, salud, educación, hogar, ocio u otros) y el valor, por ejemplo "
                    "«mi presupuesto de comida es de 800 mil».", "PRESUPUESTO")
            return True
        H.budget_set(cat, amt)
        _tot, by, _n = vd.spent("mes")
        g = by.get(cat, 0)
        J.reply(f"Listo: {vd.money(amt)} al mes para {cat}. Llevas {vd.money(g)} ({round(100 * g / amt)} %). Te aviso al llegar al 80 % y al 100 %.",
                "PRESUPUESTO")
        return True
    if _BU_ASK.search(t):
        _tot, by, _n = vd.spent("mes")
        st = H.budget_status(by)
        if not st:
            J.reply("Aún no tienes presupuesto. Di «mi presupuesto de comida es de 800 mil».", "PRESUPUESTO")
            return True
        today = D.today()
        last = (H.add_months(today.replace(day=1), 1) - datetime.timedelta(days=1)).day
        J.reply(f"Vas en el día {today.day} de {last}. " + "; ".join(
            f"{c}: {vd.money(g)} de {vd.money(tp)} ({p} %{', te pasaste' if p >= 100 else ', ojo' if p >= 80 else ''})" for c, g, tp, p in st) + ".",
            "PRESUPUESTO")
        return True
    if _SUB_ASK.search(t):
        subs = H.subscriptions(vd.data["gastos"], vd.data["pagos"])
        if not subs:
            J.reply("No veo cobros que se repitan todavía. Cuando anotes los gastos de cada mes (o tus pagos fijos con valor), los detecto.", "PRESUPUESTO")
            return True
        total = sum(s["monto"] for s in subs)
        J.reply("Lo que se repite cada mes: " + "; ".join(f"{s['nombre']} {vd.money(s['monto'])}" for s in subs[:8])
                + f". Suman {vd.money(total)} al mes, {vd.money(total * 12)} al año. ¿Hay alguno que ya no uses?", "PRESUPUESTO")
        return True
    return False


# ============================================================================ 6. COMIDAS
_MEAL = re.compile(r"\b(?:arma|armame|haz|hazme|planea|planeame|crea|creame|prepara|preparame|dame)\s+(?:el\s+|un\s+)?(?:menu|plan de comidas|minuta)"
                   r"(?:\s+(?:de|para)\s+(?:la|esta)\s+semana|\s+semanal)?\b")
_COOK = re.compile(r"^(?:jarvis[ ,]+)?que (?:cocino|preparo|hago de (?:comer|almuerzo|cena|desayuno)|puedo (?:cocinar|preparar|hacer))(?:\s+hoy)?\s+con\s+(.+?)\??$")


def make_menu(personas=2, presupuesto=None, gustos="", tengo=""):
    raw = J.ai_chat([{"role": "user", "content": H.meals_prompt(7, personas, presupuesto, gustos, tengo)}], json_mode=True, max_tokens=3000)
    m = H.meals_validate(J._extract_json(raw))
    H.data["comidas"] = m
    H.save()
    if m["lista"]:
        vd.add_items("mercado", [f"{x['item']}" + (f" ({x['cantidad']})" if x["cantidad"] else "") for x in m["lista"]])
    return m


def meal_voice(text, t):
    m = _COOK.match(t)
    if m:
        try:
            J.reply(J.ai_chat([{"role": "user", "content": H.cook_prompt(m.group(1))}], max_tokens=600).strip(), "COCINA")
        except J.AIError as e:
            J.reply(J.ai_error_reply(e), "COCINA")
        return True
    if not _MEAL.search(t) or "clase" in t:
        return False
    pers = re.search(r"\bpara\s+(\d+|dos|tres|cuatro|cinco)\s+personas\b", t)
    personas = {"dos": 2, "tres": 3, "cuatro": 4, "cinco": 5}.get(pers.group(1)) or int(pers.group(1)) if pers else 2
    pres = re.search(r"\b(?:presupuesto|con|por)\s+(?:de\s+)?(\d[\d.,]*\s*(?:mil|millones?))\b", t)
    gustos = (re.search(r"\b(?:sin|vegetariano|vegano|bajo en \w+|sin \w+)\b.*$", t) or [""])[0]
    J.reply("Armando el menú de la semana y la lista de mercado…", "COCINA")

    def work():
        try:
            mm = make_menu(personas, vd.money(vd.parse_amount(pres.group(1))) if pres else None, gustos)
            hoy = mm["dias"][0]
            J.reply(f"Listo el menú de 7 días para {personas} personas. Hoy: {hoy['almuerzo']} de almuerzo y {hoy['cena']} de cena. "
                    f"Puse {len(mm['lista'])} cosas en la lista del mercado" + (f" (unos {vd.money(mm['costo'])})" if mm["costo"] else "")
                    + ". Todo el menú está en «Mi día».", "COCINA")
        except J.AIError as e:
            J.reply(J.ai_error_reply(e), "COCINA")
        except ValueError as e:
            J.reply(f"No me salió bien el menú: {e}", "COCINA")
    J.start_job("Armando el menú", work, "menu")
    return True


# ============================================================================ 7. DOCUMENTOS EN AUDIO
def chunks(text, size=3500):
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n(?=## )", text) if p.strip()]
    out, cur = [], ""
    for p in paras:
        p = p.lstrip("# ").strip()
        while len(p) > size:                                       # párrafo enorme: por frases
            cut = p.rfind(". ", 0, size)
            cut = cut + 1 if cut > size // 2 else size
            if cur:
                out.append(cur)
                cur = ""
            out.append(p[:cut].strip())
            p = p[cut:].strip()
        if len(cur) + len(p) + 2 > size and cur:
            out.append(cur)
            cur = p
        else:
            cur = (cur + "\n\n" + p).strip()
    if cur:
        out.append(cur)
    return out


def _hg_synth(text, path_base):
    """MP3 con la voz de Edge (con internet) o WAV con Piper (sin internet). → ruta."""
    if J.edge_tts is not None and not J.is_offline():
        path = path_base + ".mp3"
        asyncio.run(J.edge_tts.Communicate(text, J.settings.get("tts_voice") or "es-CO-GonzaloNeural").save(path))
        return path
    path = path_base + ".wav"
    J._piper_synth(text, path, 0, 0)
    return path


def text_to_audio(title, text, out_dir=None, progress=None):
    """Convierte el texto en audio por partes, en la carpeta Audios/<título>. → (carpeta, [rutas])."""
    text = re.sub(r"[ \t]+", " ", text).strip()
    if len(text) < 40:
        raise ValueError("no encontré texto para leer (si es una foto o un PDF escaneado, primero «Sacar el texto»)")
    parts = chunks(text[:400_000])
    folder = os.path.join(out_dir or J.settings["output_dir"], "Audios", documentos.oficina.safe_filename(title)[:60])
    os.makedirs(folder, exist_ok=True)
    paths = []
    for i, p in enumerate(parts, 1):
        if progress:
            progress(i, len(parts))
        paths.append(_hg_synth(p, os.path.join(folder, f"{i:02d} - {documentos.oficina.safe_filename(title)[:40]}")))
    return folder, paths


_AU_VOICE = re.compile(r"\b(?:convierte|pasa|lee|leeme|vuelve|transforma)(?:me|lo|la)?\s+(?:este|el|esta|la|ese|esa)\s+(?:pdf|documento|archivo|libro|articulo|word|texto|lectura)"
                       r"\s+(?:en|a)\s+(?:un\s+)?(?:audio|mp3|audiolibro|podcast)\b|\b(?:convierte|pasa)(?:me)?\s+(?:en|a)\s+audio\b")
_HG_URL = re.compile(r"https?://\S+")


def audio_from_item(it):
    text = adjuntos.text_of(it, 400_000) if it["tipo"] != "imagen" else ""
    if it["tipo"] == "imagen" or adjuntos.is_scanned(it, text):
        text = J.ocr(it, 30)
    return _audio_job(os.path.splitext(it["nombre"])[0], text)


def _audio_job(title, text):
    def work():
        try:
            folder, paths = text_to_audio(title, text, progress=lambda i, n: J.socketio.emit("audio_progress", {"i": i, "n": n, "t": title}))
            for p in paths:
                J.generated_files.add(p)
            mins = round(len(text.split()) / 150)
            J.notify(f"Listo el audio de «{title}»: {len(paths)} parte{'s' if len(paths) != 1 else ''}, unos {max(1, mins)} minutos, "
                     f"en la carpeta Audios.", "AUDIO")
            if J.IS_WIN:
                try:
                    os.startfile(folder)
                except OSError:
                    pass
        except ValueError as e:
            J.notify(f"No pude hacer el audio: {e}", "AUDIO")
        except Exception as e:
            J.note_error("AUDIO", e)
            J.notify(f"No pude hacer el audio: {e}", "AUDIO")
    J.start_job(f"Audio de «{title[:40]}»", work, "audio")
    return None


def audio_voice(text, t):
    if not _AU_VOICE.search(t):
        return False
    url = _HG_URL.search(text)
    if url:
        J.reply("Leyendo la página para pasarla a audio…", "AUDIO")
        try:
            page = investigar.page_text(J._get_text(url.group(0), timeout=15), 200_000)
        except Exception as e:
            J.reply(f"No pude abrir esa página: {e}", "AUDIO")
            return True
        title = re.sub(r"^https?://(?:www\.)?", "", url.group(0)).split("/")[0]
        _audio_job(title, page)
        return True
    its = [i for i in adjuntos.recent(3600, 6) if i["tipo"] in ("pdf", "word", "texto", "powerpoint", "imagen")]
    if not its:
        J.reply("Sube el PDF o el documento con el clip del HUD y dime «convierte este PDF en audio» (o pégame el enlace del artículo).", "AUDIO")
        return True
    J.reply(f"Convirtiendo «{its[-1]['nombre']}» en audio. Te aviso cuando esté.", "AUDIO")
    audio_from_item(its[-1])
    return True


# ============================================================================ 9. VIAJES
_TRIP = re.compile(rf"^(?:jarvis[ ,]+)?(?:me voy|viajo|nos vamos|vamos|voy)\s+(?:de viaje\s+)?(?:para|a)\s+(.+?)\s+(?:del?|desde el)\s+(\d{{1,2}})(?:\s+de\s+({H._MES_RE}))?"
                   rf"\s+(?:al|hasta el|y regreso el|y vuelvo el)\s+(\d{{1,2}})(?:\s+de\s+({H._MES_RE}))?(.*)$")
_FLIGHT = re.compile(r"^(?:jarvis[ ,]+)?(?:mi |el )?vuelo(?:\s+([a-z]{2}\s?\d{2,4}))?\s+(?:sale|es)\s+(?:a las|el .+ a las)\s+(.+)$")
_TRIP_ASK = re.compile(r"\bmis viajes\b|\b(?:que|cuales) viajes tengo\b|\bcuando (?:me voy|viajo)\b")


def _forecast(dest, d1, d2):
    """(máxima, mínima, lluvia %) de los días del viaje si están en el pronóstico (hasta 16 días). → (tmax, tmin, rain, lugar)."""
    try:
        g = J._geo(dest)
        if not g:
            return None, None, None, None
        url = infodia.forecast_url(g["lat"], g["lon"]).replace(infodia.FORECAST_URL, J.FORECAST_URL).replace("forecast_days=3", "forecast_days=16")
        d = json.loads(J._get_text(url)).get("daily") or {}
        days = d.get("time") or []
        idx = [i for i, x in enumerate(days) if d1.isoformat() <= x <= d2.isoformat()]
        if not idx:
            return None, None, None, g
        mx = max(d["temperature_2m_max"][i] for i in idx)
        mn = min(d["temperature_2m_min"][i] for i in idx)
        rain = max((d.get("precipitation_probability_max") or [0] * len(days))[i] or 0 for i in idx)
        return mx, mn, rain, g
    except Exception as e:
        J.log_terminal(f"Clima del viaje: {e}", "AVISO")
        return None, None, None, None


def trip_voice(text, t):
    m = _TRIP.match(t)
    if m:
        dest = m.group(1).strip(" .,").title()
        today = D.today()
        mon2 = m.group(5) or m.group(3)
        mon1 = m.group(3) or mon2
        d1 = H.parse_date(f"{m.group(2)} de {mon1}" if mon1 else f"el {m.group(2)}", today)
        d2 = H.parse_date(f"{m.group(4)} de {mon2}" if mon2 else f"el {m.group(4)}", today)
        if not d1 or not d2:
            return False
        if d2 < d1:
            d2 = H.add_months(d2, 1)
        J.reply(f"Preparo tu viaje a {dest}…", "VIAJES")

        def work():
            tmax, tmin, rain, g = _forecast(dest, d1, d2)
            country = H.norm((g or {}).get("place", "").split(",")[-1]) if g else ""
            intl = bool(country) and country != "colombia"
            cur = _CUR.get(country, "")
            tr = H.trip_add(dest, d1, d2, internacional=intl, moneda=cur)
            hv = H.parse_time(m.group(6) or "")
            if hv:
                tr["hora_vuelo"] = hv
                H.save()
            items = H.packing_list(tr, tmax, tmin, rain)
            vd.add_items(tr["lista"], items)
            msg = f"Listo tu viaje a {dest} {H.spoken_date(d1)} al {d2.day} de {H.MESES[d2.month - 1]}. Hice la lista «{tr['lista']}» con {len(items)} cosas"
            if tmax is not None:
                msg += f"; el pronóstico dice entre {round(tmin)} y {round(tmax)} grados" + (f" y {round(rain)} % de lluvia" if rain else "")
            msg += ". Te recuerdo los documentos dos días antes"
            msg += " y el check-in un día antes del vuelo." if hv else "; dime «mi vuelo sale a las …» para avisarte del check-in."
            if intl and cur:
                try:
                    msg += " " + J._rate_text(cur)
                except Exception:
                    pass
            J.reply(msg, "VIAJES")
        J.start_job("Preparando el viaje", work, "viaje")
        return True
    m = _FLIGHT.match(t)
    if m and H.data["viajes"]:
        tr = sorted(H.data["viajes"], key=lambda x: x["desde"])[-1]
        hv = H.parse_time("a las " + m.group(2) if not m.group(2).startswith("a las") else m.group(2))
        if not hv:
            return False
        tr.update(hora_vuelo=hv, vuelo=(m.group(1) or tr.get("vuelo") or "").upper())
        H.save()
        J.reply(f"Anotado: el vuelo a {tr['destino']} sale a las {H.hour_spoken(hv)}. Te aviso para el check-in un día antes y para salir al aeropuerto.",
                "VIAJES")
        return True
    if _TRIP_ASK.search(t):
        vs = [v for v in H.data["viajes"] if v["hasta"] >= D.today().isoformat()]
        J.reply(" ".join(f"{v['destino']}: {H.spoken_date(D.fromisoformat(v['desde']))}." for v in vs) if vs else "No tienes viajes anotados.", "VIAJES")
        return True
    return False


# ============================================================================ TODO JUNTO
def mi_dia_voice(text, t):
    if re.search(r"\b(?:abre|abreme|muestra|muestrame)\s+(?:mi dia|mi dia a dia|el panel de mi dia)\b", t):
        open_midia_page()
        J.reply("Te abrí «Mi día»: vencimientos, medicamentos, citas, cumpleaños, presupuesto, menú y viajes.", "MI DÍA")
        return True
    for fn in (med_voice, venc_voice, cita_voice, cumple_voice, budget_voice, receipt_voice, meal_voice, audio_voice, trip_voice):
        try:
            if fn(text, t):
                return True
        except Exception as e:
            J.note_error("MI DÍA", e, text)
            J.reply("Algo falló con eso; quedó en el registro de errores.", "MI DÍA")
            return True
    return False


def brief_midia(today=None):
    today = today or D.today()
    out = []
    v = [(x, left) for x, left in H.venc_soon(today, 7)]
    if v:
        out.append("Vencimientos: " + " ".join(H.venc_text(x, left) for x, left in v[:3]))
    cs = [c for c in H.data["citas"] if c["fecha"] in (today.isoformat(), (today + datetime.timedelta(days=1)).isoformat())]
    out += [H.cita_text(c, "hoy" if c["fecha"] == today.isoformat() else "mañana") for c in cs[:2]]
    bs = H.cumples_soon(today, 3)
    if bs:
        out.append("Cumpleaños: " + "; ".join(f"{c['nombre']} {'hoy' if left == 0 else H.spoken_date(d, today)}" for c, d, left in bs) + ".")
    meds = [m for m in H.data["meds"] if H.med_active(m, today)]
    if meds:
        out.append(f"Hoy hay {sum(len(m['horas']) for m in meds)} tomas de medicamentos; te aviso a cada hora.")
    return out


def _midia_worker():
    time.sleep(60)
    while True:
        try:
            now = datetime.datetime.now()
            for m, h in H.meds_due(now):
                quien = f" a tu {m['persona']}" if m.get("persona") else ""
                _say(f"Es hora de {'darle' if quien else 'tomar'} {m['nombre']}" + (f" ({m['dosis']})" if m.get("dosis") else "") + f"{quien}. "
                     "Cuando lo hagas, di «ya me la tomé».", "MEDICAMENTOS", True)
            for m, h in H.meds_missed(now):
                _say(f"¿Ya {'le diste' if m.get('persona') else 'te tomaste'} {m['nombre']} de las {H.hour_spoken(h)}? No lo tengo marcado.", "MEDICAMENTOS")
            if 7 <= now.hour <= 21:
                for m, left in H.meds_refill(now.date()):
                    _say(f"Quedan pocas pastillas de {m['nombre']}: alcanzan para {left} día{'s' if left != 1 else ''}. Es buen momento para comprar.",
                         "MEDICAMENTOS", True)
                for x, left in H.venc_to_warn(now.date()):
                    _say(H.venc_text(x, left) + (" Renuévalo a tiempo." if left > 0 else ""), "VENCIMIENTOS", True)
                for c, d, left in H.cumples_to_warn(now.date()):
                    _say((f"Hoy cumple años {c['nombre']}" if left == 0 else f"{c['nombre']} cumple años {H.spoken_date(d)}")
                         + (f" ({H.age_on(c, d)})" if c.get("anio") else "") + ". Di «escríbele un mensaje de cumpleaños a " + c["nombre"] + "».",
                         "CUMPLEAÑOS", left == 0)
                _tot, by, _n = vd.spent("mes")
                for cat, g, tope, pct, lvl in H.budget_to_warn(by, now.date()):
                    _say(f"Presupuesto de {cat}: llevas {vd.money(g)} de {vd.money(tope)} ({pct} %)." + (" Te pasaste." if lvl == 100 else ""), "PRESUPUESTO")
            for c, cuando in H.citas_to_warn(now):
                _say(H.cita_text(c, cuando), "CITAS", True)
            for tr, kind in H.trips_to_warn(now):
                _say(H.trip_text(tr, kind), "VIAJES", True)
        except Exception as e:
            J.note_error("MI DÍA", e)
        time.sleep(60)


def midia_start():
    H.configure(J.CONFIG_DIR)
    if not _hg["started"]:
        _hg["started"] = True
        threading.Thread(target=_midia_worker, daemon=True, name="mi-dia").start()


# ============================================================================ PÁGINA «MI DÍA»
@J.app.route("/mi-dia")
def midia_page():
    from flask import render_template
    return render_template("midia.html", version=J.VERSION, asset_v=getattr(J, "ASSET_V", ""), look=J.settings.get("look", "clasico"))


def open_midia_page():
    J._open_page("/mi-dia", "Mi día", _hg)


def _midia_state():
    today = D.today()
    _tot, by, _n = vd.spent("mes")
    venc = [dict(x, faltan=(D.fromisoformat(x["fecha"]) - today).days, tipo_txt=H.VENC_TIPOS.get(x["tipo"], ("Documento",))[0])
            for x in sorted(H.data["venc"], key=lambda v: v["fecha"])]
    meds = [dict(m, dias=H.med_days_left(m), hoy=m.get("tomas", {}).get(today.isoformat(), []), activo=H.med_active(m, today)) for m in H.data["meds"]]
    cumples = [dict(c, proximo=H.next_birthday(c, today).isoformat(), faltan=(H.next_birthday(c, today) - today).days, edad=H.age_on(c, H.next_birthday(c, today)))
               for c in H.data["cumples"]]
    return {"venc": venc, "tipos": {k: v[0] for k, v in H.VENC_TIPOS.items()}, "meds": meds,
            "citas": [c for c in H.data["citas"] if c["fecha"] >= today.isoformat()],
            "cumples": sorted(cumples, key=lambda c: c["faltan"]), "presupuesto": [list(x) for x in H.budget_status(by)],
            "gastado": by, "total_mes": _tot, "cats": [c for c, _ in vd.CATS] + ["Otros"],
            "subs": H.subscriptions(vd.data["gastos"], vd.data["pagos"]), "comidas": H.data.get("comidas") or {},
            "viajes": [v for v in H.data["viajes"] if v["hasta"] >= today.isoformat()],
            "hoy": today.isoformat()}


@J.socketio.on("open_midia_page")
def handle_open_midia(data=None):
    open_midia_page()
    return {"ok": True}


@J.socketio.on("midia_state")
def handle_midia_state(data=None):
    return _midia_state()


def _date_of(v):
    try:
        return D.fromisoformat(str(v)[:10])
    except ValueError:
        raise ValueError("falta la fecha")


@J.socketio.on("midia_save")
def handle_midia_save(data=None):
    d = data or {}
    sec = d.get("seccion")
    try:
        if sec == "venc":
            if not str(d.get("nombre") or "").strip():
                raise ValueError("ponle un nombre")
            H.venc_add(d["nombre"], _date_of(d.get("fecha")), d.get("tipo"), str(d.get("nota") or ""))
        elif sec == "meds":
            horas = [h.strip() for h in re.split(r"[,\s]+", str(d.get("horas") or "")) if h.strip()]
            horas = [f"{int(h.split(':')[0]):02d}:{h.split(':')[1]}" for h in horas if re.fullmatch(r"\d{1,2}:\d{2}", h)]
            st = str(d.get("stock") or "").strip()
            H.med_add(str(d.get("nombre") or "").strip() or "medicamento", horas, str(d.get("dosis") or ""), str(d.get("persona") or ""),
                      int(st) if st.isdigit() else None, int(d.get("por_toma") or 1), _date_of(d["hasta"]) if d.get("hasta") else None)
        elif sec == "citas":
            hora = str(d.get("hora") or "")
            H.cita_add(str(d.get("que") or "Cita").strip(), _date_of(d.get("fecha")), hora if re.fullmatch(r"\d{2}:\d{2}", hora) else "",
                       str(d.get("lugar") or ""), str(d.get("persona") or ""))
        elif sec == "cumples":
            f = _date_of(d.get("fecha"))
            H.cumple_add(str(d.get("nombre") or "").strip() or "?", f.month, f.day, f.year if d.get("con_anio") else None, str(d.get("relacion") or ""))
        elif sec == "presupuesto":
            amt = vd.parse_amount(str(d.get("tope") or ""))
            if not amt:
                raise ValueError("escribe el valor, por ejemplo 800000")
            H.budget_set(str(d.get("cat")), amt)
        elif sec == "viajes":
            d1, d2 = _date_of(d.get("desde")), _date_of(d.get("hasta"))
            tr = H.trip_add(str(d.get("destino") or "").strip() or "Viaje", d1, d2, internacional=bool(d.get("internacional")))
            hv = str(d.get("hora_vuelo") or "")
            if re.fullmatch(r"\d{2}:\d{2}", hv):
                tr["hora_vuelo"] = hv
                H.save()
            vd.add_items(tr["lista"], H.packing_list(tr))
        else:
            return {"ok": False, "error": "sección desconocida"}
    except (ValueError, KeyError) as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, **_midia_state()}


@J.socketio.on("midia_delete")
def handle_midia_delete(data=None):
    d = data or {}
    if d.get("seccion") == "presupuesto":
        H.data["presupuesto"].pop(str(d.get("id")), None)
        H.save()
    elif d.get("seccion") in ("venc", "meds", "citas", "cumples", "viajes"):
        H.remove(d["seccion"], str(d.get("id")))
    return _midia_state()


@J.socketio.on("midia_taken")
def handle_midia_taken(data=None):
    m = next((x for x in H.data["meds"] if x["id"] == str((data or {}).get("id"))), None)
    if m:
        H.med_taken(m)
    return _midia_state()


@J.socketio.on("midia_upload")
def handle_midia_upload(data=None):
    """Un recibo (para anotarlo) o un documento (para pasarlo a audio), subido en la página."""
    import base64
    f = data or {}
    try:
        m = re.match(r"data:[^;]*;base64,(.+)$", str(f.get("data") or ""), re.S)
        raw = base64.b64decode(m.group(1) if m else "")
        if not raw:
            raise ValueError("vino vacío")
        it = adjuntos.add(str(f.get("name") or "archivo"), raw)
    except (ValueError, OSError) as e:
        return {"ok": False, "error": str(e)}
    if f.get("para") == "audio":
        audio_from_item(it)
        return {"ok": True, "msg": "Convirtiendo en audio; te aviso cuando esté (carpeta Audios)."}
    try:
        return {"ok": True, "msg": receipt_from(it), **_midia_state()}
    except ValueError as e:
        return {"ok": False, "error": f"No pude leer el recibo: {e}"}
    except J.AIError as e:
        return {"ok": False, "error": J.ai_error_reply(e)}


@J.socketio.on("midia_menu")
def handle_midia_menu(data=None):
    d = data or {}
    try:
        make_menu(int(d.get("personas") or 2), d.get("presupuesto") or None, str(d.get("gustos") or "")[:200], str(d.get("tengo") or "")[:300])
    except J.AIError as e:
        return {"ok": False, "error": J.ai_error_reply(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, **_midia_state()}


__all__ = [
    '_AU_VOICE', '_BU_ASK', '_BU_SET', '_B_ADD', '_B_ASK', '_B_GIFT', '_B_MSG', '_B_WHEN', '_CATS', '_COOK', '_CUR', '_C_ADD', '_C_ASK', '_C_WORD',
    '_DIGITS', '_EXPORT', '_FLIGHT', '_MEAL', '_MEDWORD', '_M_ADD', '_M_ASK', '_M_DEL', '_M_STOCK', '_M_TAKEN', '_RENTA', '_R_VOICE', '_SUB_ASK',
    '_TRIP', '_TRIP_ASK', '_HG_URL', '_V_ADD', '_V_ASK', '_V_DEL', '_V_RENOVE', '_V_WHEN', '_audio_job', '_cat', '_date_of', '_extract_receipt',
    '_forecast', '_hg', '_med_times', '_orig', '_midia_state', '_midia_worker', '_persona', '_say', '_hg_synth', 'audio_from_item', 'audio_voice',
    'brief_midia', 'budget_voice', 'chunks', 'cita_voice', 'cumple_voice', 'export_month', 'handle_midia_delete', 'handle_midia_menu',
    'handle_midia_save', 'handle_midia_state', 'handle_midia_taken', 'handle_midia_upload', 'handle_open_midia', 'make_menu', 'meal_voice',
    'med_voice', 'mi_dia_voice', 'midia_page', 'midia_start', 'open_midia_page', 'receipt_from', 'receipt_voice', 'text_to_audio', 'trip_voice',
    'venc_voice',
]
