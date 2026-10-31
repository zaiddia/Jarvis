"""11.2: ruta de dominio de cada estudiante (los temas del periodo en orden; no avanza hasta dominar) y tarjetas de
memoria con repaso espaciado en la práctica del celular, exportables a Anki o Quizlet.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import html
import os
import re
import datetime
import urllib.parse

import aula
import banco
import diarioclase
import dominio
import practica
from nucleo import J


# ============================================================================ RUTA DE DOMINIO
def course_route(curso):
    """Los temas del periodo en curso, en orden: de la planeación anual; si no hay, de la malla del diario de clase."""
    keys = [curso] + ([curso.split(" · ")[0]] if " · " in curso else []) + [k for k in J.anual.data["planes"] if k.split(" · ")[0] == curso]
    for k in keys:
        plan = J.anual.data["planes"].get(k)
        if plan:
            p = min(max(1, J.where_now()[1]), len(plan["periodos"]))
            temas = [s["tema"] for s in plan["periodos"][p - 1]["semanas"]]
            break
    else:
        m = next((diarioclase.data["mallas"].get(k) for k in keys if diarioclase.data["mallas"].get(k)), None)
        temas = [s["tema"] for s in (m or {}).get("semanas", [])]
    out = []
    for t in temas:
        if not re.search(r"\b(?:refuerzo|evaluaci[oó]n del periodo|examen final|semana de evaluaci)", t, re.I) and t not in out:
            out.append(t)
    return out[:20]


def route_status(curso, est):
    r = J.course_route(curso)
    return dominio.status(r, practica.student(curso, est)["temas"]) if r else []


def route_current(curso, est):
    r = J.course_route(curso)
    return dominio.current(r, practica.student(curso, est)["temas"]) if r else None


def route_view(curso):
    r = J.course_route(curso)
    studs = {e: practica.data["cursos"].get(curso, {}).get(e, {}).get("temas", {}) for e in aula.students(curso)}
    if not r:
        return r, {}, []
    rows, per = dominio.course_view(r, studs)
    return r, rows, per


@J.app.route("/ruta/<path:curso>")
def route_page(curso):
    route, rows, per = J.route_view(curso)
    icon = {"dominado": "✔", "actual": "▶", "bloqueado": "🔒"}
    color = {"dominado": "#1d5c3c", "actual": "#1d4f6b", "bloqueado": "#141c26"}
    head = "".join(f"<th title='{html.escape(t)}'>{i + 1}</th>" for i, t in enumerate(route))
    body = "".join("<tr><td class='n'>" + html.escape(e) + "</td>" + "".join(
        f"<td style='background:{color[s['estado']]}' title='{html.escape(s['tema'])}: {s['estado']}'>{icon[s['estado']]}</td>" for s in st) + "</tr>"
        for e, st in sorted(rows.items(), key=lambda kv: -sum(1 for s in kv[1] if s["estado"] == "dominado")))
    legend = "".join(f"<li><b>{i + 1}.</b> {html.escape(p['tema'])} — <span>{p['dominan']}/{p['total']} lo dominan</span></li>" for i, p in enumerate(per))
    return (f"<!DOCTYPE html><html lang='es'><head><meta charset='UTF-8'><title>Ruta · {html.escape(curso)}</title><style>"
            "body{margin:0;padding:20px;background:#03060c;color:#e6f6ff;font-family:system-ui,sans-serif}h1{color:#2ee6ff;font-size:22px}"
            "table{border-collapse:separate;border-spacing:3px;font-size:14px}td,th{padding:6px 8px;text-align:center;border-radius:5px}"
            "td.n{text-align:left;white-space:nowrap}th{color:#7d95ab}ol,ul{color:#c9d6e2;font-size:14px;line-height:1.6}span{color:#3dff9a}"
            f"</style></head><body><h1>Ruta de dominio · {html.escape(curso.replace(' · ', ' – '))}</h1>"
            + (f"<table><tr><th></th>{head}</tr>{body}</table><ul>{legend}</ul>" if route else
               "<p>Este curso aún no tiene ruta: haz la planeación anual («haz la planeación anual de …») o guarda la malla del periodo.</p>")
            + "</body></html>")


# ============================================================================ TARJETAS (REPASO ESPACIADO)
def _card_public(curso, est):
    lst = dominio.due(curso, est)
    if not lst:
        return {"ok": True, "fin": True, "msg": "¡No tienes tarjetas pendientes por hoy! 🎉"}
    tema, c = lst[0]
    return {"ok": True, "id": c["id"], "tema": tema, "frente": c["frente"], "reverso": c["reverso"], "quedan": len(lst)}


@J.mobile_app.route("/p/<code>/tarjetas", methods=["POST"])
def cards_next(code):
    from flask import request
    tok = J._tok(code, (request.get_json(silent=True) or {}).get("k"))
    if not tok:
        return {"ok": False, "msg": "Vuelve a entrar con tu nombre y PIN."}
    return J._card_public(J.ps["curso"], tok["est"])


@J.mobile_app.route("/p/<code>/tarjeta", methods=["POST"])
def cards_answer(code):
    from flask import request
    d = request.get_json(silent=True) or {}
    tok = J._tok(code, d.get("k"))
    if not tok:
        return {"ok": False, "msg": "Vuelve a entrar con tu nombre y PIN."}
    ids = {c["id"] for _t, c in dominio.all_cards(J.ps["curso"])}
    if str(d.get("id")) in ids:
        dominio.review(J.ps["curso"], tok["est"], str(d["id"]), bool(d.get("sabia")))
    return J._card_public(J.ps["curso"], tok["est"])


def make_deck(curso, tema):
    """Genera (IA) o arma (banco) el mazo de un tema. → cuántas tarjetas nuevas."""
    cards = []
    if J.state.get("ai") == "ok":
        try:
            g = aula.grade_of(curso)
            raw = J.ai_chat([{"role": "user", "content": dominio.cards_prompt(tema, f"{g}°" if g else "bachillerato", J._subject(curso))}],
                            json_mode=True, max_tokens=3000)
            cards = dominio.clean_cards(J._extract_json(raw))
        except Exception as e:
            J.log_terminal(f"Tarjetas: {getattr(e, 'why', e)}", "AVISO")
    if not cards:
        qs = banco.search(tema, "", 10)
        cards = dominio.clean_cards({"tarjetas": [{"frente": q["enunciado"], "reverso": q["opciones"]["abcd".index(str(q.get("respuesta", "a"))[:1].lower())]
                                                   if str(q.get("respuesta", "a"))[:1].lower() in "abcd" and len(q.get("opciones") or []) > 3 else ""}
                                                  for q in qs]})
    return dominio.add_deck(curso, tema, cards)


_RU_ASK = re.compile(r"\bcomo va la ruta(?: de dominio)?(?:\s+(?:de|del|en)\s+(.+))?$|\bquien(?:es)? domina(?:n)?\b.*?(?:\s+en\s+(.+))?$|\bmuestra la ruta(?: de dominio)?(?:\s+de\s+(.+))?$")
_TJ_MAKE = re.compile(r"\b(?:haz|hazme|crea|creame|genera|prepara|preparame)\s+(?:las\s+|unas\s+)?tarjetas(?:\s+de memoria)?\s+(?:de|sobre)\s+(.+?)"
                      r"(?:\s+(?:para|de|en)\s+((?:grado\s+)?(?:\d{1,2}\s?[a-z]?|sexto|septimo|octavo|noveno|undecimo|decimo|once)\b.*))?$")
_TJ_ROUTE = re.compile(r"\b(?:haz|hazme|crea|genera|prepara)\s+(?:las\s+)?tarjetas\s+de\s+(?:la\s+)?ruta(?:\s+de\s+(.+))?$")
_TJ_EXP = re.compile(r"\bexporta(?:r|me)?\s+(?:las\s+)?tarjetas(?:\s+de\s+(.+?))?\s+(?:a|para)\s+(anki|quizlet)\b")
_TJ_ASK = re.compile(r"\bcomo van las tarjetas(?:\s+de\s+(.+))?$")


def _course_of(spoken):
    c = J._resolve_course((spoken or "").strip())
    return (J.grade_key(c, spoken or "", ask=False) or c) if c else ""


def mastery_voice(text, t):
    m = _TJ_ROUTE.search(t)
    if m:
        c = _course_of(m.group(1))
        route = J.course_route(c) if c else []
        if not route:
            J.reply(f"{c or 'Ese curso'} aún no tiene ruta: haz la planeación anual o guarda la malla del periodo.", "RUTA")
            return True
        J.reply(f"Preparo las tarjetas de los {len(route)} temas de la ruta de {c}…", "RUTA")

        def work():
            n = sum(J.make_deck(c, tema) for tema in route)
            J.notify(f"Listas {n} tarjetas de memoria de la ruta de {c}. Aparecen en la práctica del celular («Repasar tarjetas»); «exporta las "
                     f"tarjetas de {c} a Anki» si las quieres allá.", "RUTA")
        if getattr(J._tl, "capture", None) is not None:
            work()
        else:
            J.start_job("Preparando tarjetas", work, "tarjetas")
        return True
    m = _TJ_MAKE.search(t)
    if m:
        c = _course_of(m.group(2) or "")
        if not c:
            J.reply("¿Para qué curso? Por ejemplo: «haz tarjetas de fracciones para 7A».", "RUTA")
            return True
        tema = re.sub(r"^(?:el|la|los|las)\s+", "", m.group(1).strip())
        n = J.make_deck(c, tema)
        J.reply(f"Listas {n} tarjetas de «{tema}» para {c}. Cada estudiante las repasa en la práctica del celular: si la sabe, vuelve en 1, 3, "
                "7, 14 y 30 días; si no, mañana." if n else "No pude armar las tarjetas (necesito la IA o preguntas del banco sobre ese tema).", "RUTA")
        return True
    m = _TJ_EXP.search(t)
    if m:
        c = _course_of(m.group(1) or "") or J.ps["curso"]
        if not dominio.all_cards(c):
            J.reply(f"{c or 'Ese curso'} no tiene tarjetas todavía.", "RUTA")
            return True
        app = "Anki" if m.group(2) == "anki" else "Quizlet"
        path = os.path.join(J.settings["output_dir"], "Exportaciones", f"Tarjetas {c.replace(' · ', ' ')} para {app} {datetime.date.today():%Y-%m-%d}.txt")
        n = dominio.export_tsv(c, path)
        J.generated_files.add(path)
        J.reply(f"Listas {n} tarjetas de {c} para {app}. " + ("En Anki: Archivo › Importar y escoge este archivo (separado por tabuladores)."
                if app == "Anki" else "En Quizlet: Crear › Importar, pega el contenido y escoge «Tabulador» entre término y definición."), "RUTA")
        return True
    m = _TJ_ASK.search(t)
    if m:
        c = _course_of(m.group(1) or "") or J.ps["curso"]
        st = dominio.stats(c)
        if not st:
            J.reply("Nadie ha repasado tarjetas todavía en ese curso.", "RUTA")
            return True
        J.reply(f"Tarjetas de {c}: {len(st)} estudiantes repasando; " + "; ".join(f"{e}: {v['firmes']} firmes de {v['vistas']}"
                for e, v in sorted(st.items(), key=lambda kv: -kv[1]["firmes"])[:6]) + ".", "RUTA")
        return True
    m = _RU_ASK.search(t)
    if m:
        c = _course_of(next((g for g in m.groups() if g), "")) or J.ps["curso"] or aula.data.get("activo", "")
        route, rows, per = J.route_view(c)
        if not route:
            J.reply(f"{c or 'Ese curso'} aún no tiene ruta de dominio: haz la planeación anual o guarda la malla del periodo.", "RUTA")
            return True
        try:
            import webbrowser
            webbrowser.open(J.URL + "/ruta/" + urllib.parse.quote(c))
        except Exception:
            pass
        top = sorted(per, key=lambda p: p["dominan"])
        J.reply(f"Ruta de {c} ({len(route)} temas): " + "; ".join(f"«{p['tema']}» {p['dominan']}/{p['total']}" for p in per[:6]) +
                (f". El que menos dominan: «{top[0]['tema']}»." if top else "") + " Abrí el mapa de la ruta.", "RUTA")
        return True
    return False


def mastery_start():
    dominio.configure(J.CONFIG_DIR)


__all__ = ['_RU_ASK', '_TJ_ASK', '_TJ_EXP', '_TJ_MAKE', '_TJ_ROUTE', '_card_public', '_course_of', 'cards_answer', 'cards_next', 'course_route',
           'dominio', 'make_deck', 'mastery_start', 'mastery_voice', 'route_current', 'route_page', 'route_status', 'route_view']
