"""Investigación con fuentes (7.5): «investiga a fondo la deforestación en la Amazonía» → un documento con citas.

Pasos (jarvis.py hace las peticiones):
  1. Plan: 3 búsquedas distintas sobre el tema (con la IA; sin ella, variantes fijas).
  2. Busca en internet (DuckDuckGo, como «busca en internet…») y junta hasta 8 fuentes distintas.
  3. Lee cada página y saca su texto principal.
  4. La IA escribe un informe en español con cada dato citado [1], [2]… y sin inventar.
  5. Se guarda como Word (o HTML) en Documentos\\Jarvis\\Investigaciones, con la lista de fuentes y sus enlaces.
"""
import datetime
import difflib
import html
import json
import re
import unicodedata
import urllib.parse

import confianza

MAX_SOURCES = 8
MAX_CHARS = 3500

_SKIP_HOSTS = ("youtube.com", "youtu.be", "facebook.com", "instagram.com", "tiktok.com", "x.com", "twitter.com",
               "pinterest.", "linkedin.com", "amazon.", "mercadolibre.")


def plan_prompt(topic, n=3):
    if n > 3:
        return ("Vas a investigar en internet a fondo. Tema: «" + topic + "».\n"
                f"Escribe {n} búsquedas distintas y concretas (en español; una o dos pueden ser en inglés si ayuda) que juntas cubran "
                "el tema desde varios lados: qué es, datos y cifras recientes, causas, consecuencias, opiniones distintas y aplicaciones. "
                'Responde SOLO con JSON: {"busquedas": ["…", "…"]}')
    return ("Vas a investigar en internet para un docente. Tema: «" + topic + "».\n"
            "Escribe 3 búsquedas distintas y concretas (en español; una puede ser en inglés si ayuda) que juntas cubran "
            "el tema: qué es, datos y cifras recientes, y causas/consecuencias o aplicaciones. Responde SOLO con JSON: "
            '{"busquedas": ["…", "…", "…"]}')


def parse_plan(text, topic):
    try:
        m = re.search(r"\{.*\}", str(text), re.S)
        d = json.loads(m.group(0) if m else text)
        qs = [str(q).strip() for q in d.get("busquedas", []) if str(q).strip()]
        if qs:
            return qs[:10]
    except Exception:
        pass
    return default_plan(topic)


def default_plan(topic):
    return [topic, f"{topic} qué es causas consecuencias", f"{topic} datos cifras {datetime.date.today().year}"]


def host(url):
    try:
        h = urllib.parse.urlparse(url).hostname or ""
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


def merge_results(groups, limit=MAX_SOURCES):
    """Junta los resultados de varias búsquedas: sin repetir página ni (casi) sitio, alternando búsquedas."""
    out, seen_url, per_host = [], set(), {}
    i = 0
    while len(out) < limit and any(i < len(g) for g in groups):
        for g in groups:
            if i >= len(g) or len(out) >= limit:
                continue
            r = g[i]
            u = r.get("url", "")
            h = host(u)
            if not u.startswith("http") or u in seen_url or any(s in h for s in _SKIP_HOSTS) or per_host.get(h, 0) >= 2:
                continue
            seen_url.add(u)
            per_host[h] = per_host.get(h, 0) + 1
            out.append(r)
        i += 1
    return out


_DROP = re.compile(r"<(script|style|noscript|nav|header|footer|aside|form|svg|iframe)\b.*?</\1\s*>", re.I | re.S)
_BLOCK = re.compile(r"<(p|h[1-4]|li|blockquote|td)\b[^>]*>(.*?)</\1\s*>", re.I | re.S)


def page_text(raw_html, limit=MAX_CHARS):
    """El texto principal de una página: párrafos, títulos y listas (sin menús ni publicidad)."""
    h = _DROP.sub(" ", raw_html or "")
    parts = []
    for tag, inner in _BLOCK.findall(h):
        t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", inner))).strip()
        if len(t) < (25 if tag.lower() in ("li", "td") else 40):
            continue
        if re.search(r"cookies|suscr[ií]bete|newsletter|derechos reservados|iniciar sesi[oó]n|publicidad", t, re.I):
            continue
        parts.append(("## " if tag.lower().startswith("h") else "") + t)
        if sum(len(p) for p in parts) > limit:
            break
    text = "\n".join(parts)
    if len(text) < 200:                                # páginas sin <p>: todo el texto visible
        text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h))).strip()
    return text[:limit]


def report_prompt(topic, sources):
    blocks = []
    for i, s in enumerate(sources, 1):
        blocks.append(f"[{i}] {s['titulo']} — {s['fuente']} ({s['url']})\n{s.get('texto') or s.get('resumen', '')}")
    today = datetime.date.today().isoformat()
    return ("Eres Jarvis, el asistente de investigación de un docente en Colombia. Hoy es " + today + ".\n"
            f"Tema: «{topic}».\n\nFUENTES (texto sacado de cada página):\n\n" + "\n\n".join(blocks) +
            "\n\nEscribe un informe en español, claro y bien organizado, usando SOLO estas fuentes. Reglas:\n"
            "- Cada dato, cifra o afirmación lleva su cita con el número de la fuente: [1], [2]… (puede llevar varias).\n"
            "- No inventes nada. Si las fuentes se contradicen o falta información, dilo.\n"
            "- Formato (texto simple, sin tablas):\n"
            "TÍTULO: (una línea)\n"
            "RESUMEN: (3 a 5 frases)\n"
            "Después, 3 a 5 secciones, cada una empezando con «## » y su título, con párrafos cortos o viñetas «- ».\n"
            "Termina con una sección «## Para llevar al aula» con 3 ideas de actividades basadas en lo investigado.\n"
            "No escribas la lista de fuentes: la añado yo.")


def parse_report(text, topic):
    """{"titulo", "resumen", "secciones": [(titulo, [líneas])]} a partir de lo que escribió la IA."""
    t = str(text or "").replace("\r", "")
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    m = re.search(r"^\s*T[ÍI]TULO:\s*(.+)$", t, re.M | re.I)
    titulo = m.group(1).strip() if m else topic[:1].upper() + topic[1:]
    m = re.search(r"^\s*RESUMEN:\s*(.+?)(?=^\s*##\s|\Z)", t, re.M | re.S | re.I)
    resumen = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    secciones = []
    for sm in re.finditer(r"^\s*##\s*(.+?)\n(.*?)(?=^\s*##\s|\Z)", t, re.M | re.S):
        lines = [ln.rstrip() for ln in sm.group(2).strip().splitlines() if ln.strip()]
        secciones.append((sm.group(1).strip(), lines))
    if not resumen and not secciones:
        resumen = re.sub(r"\s+", " ", t).strip()[:1500]
    return {"titulo": titulo, "resumen": resumen, "secciones": secciones}


def used_citations(report):
    txt = report["resumen"] + " " + " ".join(" ".join(ls) for _, ls in report["secciones"])
    return sorted({int(n) for n in re.findall(r"\[(\d{1,2})\]", txt)})


def fallback_report(topic, sources):
    """Sin IA: un informe con lo que dice cada fuente (sigue siendo útil y está citado)."""
    secs = []
    for i, s in enumerate(sources, 1):
        txt = (s.get("texto") or s.get("resumen") or "").split("\n")
        lines = [ln.replace("## ", "") for ln in txt if ln.strip()][:4]
        secs.append((s["titulo"][:90], [f"{ln[:400]} [{i}]" for ln in lines] or [f"(sin texto) [{i}]"]))
    return {"titulo": topic[:1].upper() + topic[1:], "resumen": f"Lo que dicen {len(sources)} fuentes sobre {topic} "
            "(sin IA conectada: es un resumen de cada una, no un análisis).", "secciones": secs}


def safe_filename(text):
    t = unicodedata.normalize("NFC", str(text))
    t = re.sub(r'[<>:"/\\|?*\x00-\x1f.,;¿?¡!]', "", t).strip()
    return re.sub(r"\s+", " ", t)[:60] or "investigacion"


def spoken_summary(report, n_sources, where):
    first = re.split(r"(?<=[.!?])\s+", re.sub(r"\s*\[\d+(?:\]\s*\[\d+)*\]", "", report["resumen"]))[:2]
    return (" ".join(first).strip() + f" Te dejé el informe completo con {n_sources} fuentes en {where}.").strip()


def to_html(report, sources, topic):
    esc = html.escape

    def cite(s):
        return re.sub(r"\[(\d{1,2})\]", r'<sup><a href="#f\1">[\1]</a></sup>', esc(s))
    body = [f"<h1>{esc(report['titulo'])}</h1>", f"<p class='meta'>Investigación de Jarvis · {datetime.date.today():%d/%m/%Y} · "
            f"tema: {esc(topic)}</p>"]
    if report["resumen"]:
        body.append(f"<div class='res'><b>Resumen.</b> {cite(report['resumen'])}</div>")
    for title, lines in report["secciones"]:
        body.append(f"<h2>{esc(title)}</h2>")
        items = [ln for ln in lines if ln.lstrip().startswith(("-", "•", "*"))]
        for ln in lines:
            if ln in items:
                continue
            body.append(f"<p>{cite(ln)}</p>")
        if items:
            body.append("<ul>" + "".join(f"<li>{cite(ln.lstrip('-•* '))}</li>" for ln in items) + "</ul>")
    body.append("<h2>Fuentes</h2><ol>" + "".join(
        f"<li id='f{i}'>{esc(s['titulo'])} — {esc(s['fuente'])}. <a href='{esc(s['url'])}'>{esc(s['url'])}</a></li>"
        for i, s in enumerate(sources, 1)) + "</ol>")
    if report.get("nota") or report.get("evidencia"):                # 12.39
        body.append("<h2>Cómo se comprobó</h2>" + (f"<p class='meta'>{esc(report['nota'])}</p>" if report.get("nota") else "") +
                    "<ul>" + "".join(f"<li>{cite(ln)}</li>" for ln in report.get("evidencia") or []) + "</ul>")
    css = ("body{font-family:Segoe UI,Arial,sans-serif;max-width:820px;margin:40px auto;padding:0 20px;line-height:1.6;color:#1b2430}"
           "h1{color:#0b5f7a}h2{color:#0b5f7a;border-bottom:1px solid #d5e3ea;padding-bottom:4px;margin-top:28px}"
           ".meta{color:#667}.res{background:#eef7fb;border-left:4px solid #2ab3d6;padding:12px 16px}"
           "sup a{text-decoration:none;color:#0b7fa3}li{margin:4px 0}")
    return (f"<!doctype html><html lang='es'><head><meta charset='utf-8'><title>{esc(report['titulo'])}</title>"
            f"<style>{css}</style></head><body>" + "\n".join(body) + "</body></html>")


# ============================================================================ 12.39: INVESTIGACIÓN QUE COMPRUEBA SUS CITAS
# Cada dato es: lo que se afirma, de qué fuente y las PALABRAS EXACTAS de la página que lo dicen. Esas palabras se
# buscan con código en el texto guardado de la página (no se le pregunta a la IA si «está de acuerdo»). Lo que no
# aparece se descarta; el informe se escribe solo con lo comprobado y cada [n] se renumera; uno que no apunta a nada
# queda como [?].
def budget_size(minutes):
    """(búsquedas, fuentes, rondas de repaso) según el tiempo que le das."""
    m = max(0, int(minutes or 0))
    if m <= 0:
        return 3, MAX_SOURCES, 0
    return min(10, 3 + m // 2), min(16, 8 + m), (1 if m >= 4 else 0) + (1 if m >= 10 else 0)


def _norm_q(s):
    s = unicodedata.normalize("NFKC", str(s or "")).lower()
    s = s.replace("“", '"').replace("”", '"').replace("«", '"').replace("»", '"').replace("’", "'").replace("‘", "'")
    s = re.sub(r"[–—‐-]", "-", s)
    s = re.sub(r"\[\d+\]|\.\.\.|…", " ", s)
    s = re.sub(r"[\"'()\[\]]", " ", s)
    return re.sub(r"\s+", " ", s).strip(" .,;:")


def quote_support(quote, page):
    """«exacta», «casi» (≥ 92 % igual a un trozo de la página: tildes, comillas o una palabra distinta) o «no»."""
    q, p = _norm_q(quote), _norm_q(page)
    if len(q.split()) < 4 or not p:
        return "no"
    if q in p:
        return "exacta"
    qw, pw = q.split(), p.split()
    n = len(qw)
    firsts = set(qw[:3])
    best = 0.0
    for i, w in enumerate(pw):
        if w not in firsts:
            continue
        for start in (i, i - 1, i - 2):
            if start < 0:
                continue
            chunk = " ".join(pw[start:start + n])
            r = difflib.SequenceMatcher(None, q, chunk, autojunk=False).ratio()
            if r > best:
                best = r
                if best >= 0.97:
                    return "casi"
    return "casi" if best >= 0.92 else "no"


def findings_prompt(topic, sources, known=()):
    blocks = []
    for i, s in enumerate(sources, 1):
        if s.get("leida"):
            blocks.append(f"[{i}] {s['titulo']} — {s['fuente']}\n" + confianza.wrap(s.get("texto", ""), f"FUENTE {i}"))
    have = ("\nYa tengo estos datos (no los repitas):\n" + "\n".join(f"- {d}" for d in list(known)[:40])) if known else ""
    return ("Vas a sacar los DATOS que sirven para un informe sobre «" + topic + "».\n\n" + "\n\n".join(blocks) + have +
            "\n\nPara cada dato importante (cifras, fechas, definiciones, causas, efectos, opiniones de expertos): qué afirma, el número "
            "de la fuente y una CITA: de 8 a 40 palabras COPIADAS LETRA POR LETRA de esa fuente (sin cambiar ni resumir nada; "
            "si no puedes copiarlo exacto, no pongas ese dato). Entre 6 y 25 datos, de varias fuentes. Responde SOLO con JSON:\n"
            '{"datos": [{"dato": "…", "fuente": 1, "cita": "…"}]}' + confianza.RULE)


def parse_findings(text, n_sources):
    try:
        m = re.search(r"\{.*\}", str(text), re.S)
        d = json.loads(m.group(0) if m else text)
    except Exception:
        return []
    out = []
    for x in (d.get("datos") or [])[:40]:
        if not isinstance(x, dict):
            continue
        try:
            f = int(x.get("fuente"))
        except (TypeError, ValueError):
            continue
        dato, cita = str(x.get("dato") or "").strip()[:500], str(x.get("cita") or "").strip()[:600]
        if dato and cita and 1 <= f <= n_sources:
            out.append({"dato": dato, "fuente": f, "cita": cita})
    return out


def verify_findings(findings, sources):
    """→ (comprobados, descartados). Cada uno con "check": exacta/casi, o "motivo" del descarte."""
    ok, bad = [], []
    seen = set()
    for x in findings:
        s = sources[x["fuente"] - 1]
        key = _norm_q(x["cita"])[:120]
        if key in seen:
            continue
        seen.add(key)
        if not s.get("leida"):
            bad.append(dict(x, motivo="solo tenía el resumen del buscador, no la página"))
            continue
        r = quote_support(x["cita"], s.get("texto", ""))
        if r == "no":
            bad.append(dict(x, motivo="la cita no está en la página"))
        else:
            ok.append(dict(x, check=r))
    return ok, bad


def review_prompt(topic, findings):
    return ("Investigo «" + topic + "». Estos son los datos que ya comprobé:\n" + "\n".join(f"- {x['dato']}" for x in findings[:40]) +
            "\n\n¿Qué preguntas importantes del tema quedan sin responder o con una sola fuente? Escribe 2 o 3 búsquedas nuevas para "
            'cubrirlas. Responde SOLO con JSON: {"faltan": ["…"], "busquedas": ["…", "…"]}')


def verified_report_prompt(topic, findings, sources):
    lines = [f"- {x['dato']} [{x['fuente']}]" for x in findings]
    names = "\n".join(f"[{i}] {s['titulo']} — {s['fuente']}" for i, s in enumerate(sources, 1))
    today = datetime.date.today().isoformat()
    return ("Eres Jarvis. Hoy es " + today + f". Escribe un informe en español sobre «{topic}» usando SOLO estos datos COMPROBADOS "
            "(cada uno ya trae el número de su fuente):\n" + "\n".join(lines) + "\n\nFuentes:\n" + names +
            "\n\nReglas:\n- Cada afirmación lleva el número de la fuente del dato en que se apoya: [1], [2]… "
            "No afirmes nada que no esté en esa lista, ni vayas más allá de lo que dice.\n"
            "- Si los datos se contradicen o falta algo, dilo.\n"
            "- Formato (texto simple, sin tablas):\nTÍTULO: (una línea)\nRESUMEN: (3 a 5 frases)\n"
            "Después, 3 a 5 secciones que empiecen con «## » y su título, con párrafos cortos o viñetas «- ».\n"
            "Termina con «## Para llevar al aula» con 3 ideas de actividades basadas en lo investigado.\nNo escribas la lista de fuentes.")


def _report_lines(report):
    yield report["resumen"]
    for _t, ls in report["secciones"]:
        yield from ls


def check_report(report, findings):
    """Lo que hace el código después de escribir: las citas [n] que no apuntan a una fuente con datos comprobados quedan
    como [?]; luego se renumeran 1, 2, 3… en el orden en que aparecen. → (informe, mapa viejo→nuevo, cuántas [?])."""
    good = {x["fuente"] for x in findings}
    order, bad = [], [0]

    def scan(txt):
        for n in re.findall(r"\[(\d{1,2})\]", txt):
            n = int(n)
            if n in good and n not in order:
                order.append(n)
    for ln in _report_lines(report):
        scan(ln)
    for x in findings:                                  # las fuentes con datos que el texto no citó, al final (están en la evidencia)
        if x["fuente"] not in order:
            order.append(x["fuente"])
    new = {old: i for i, old in enumerate(order, 1)}

    def fix(txt):
        def rep(m):
            n = int(m.group(1))
            if n in new:
                return f"[{new[n]}]"
            bad[0] += 1
            return "[?]"
        return re.sub(r"\[(\d{1,2})\]", rep, txt)
    out = {"titulo": report["titulo"], "resumen": fix(report["resumen"]),
           "secciones": [(t, [fix(ln) for ln in ls]) for t, ls in report["secciones"]]}
    return out, new, bad[0]


def renumber_sources(sources, mapping):
    inv = sorted(mapping.items(), key=lambda kv: kv[1])
    return [sources[old - 1] for old, _new in inv]


def evidence_lines(findings, mapping):
    """«dato — «cita» [n]» para el anexo «Cómo se comprobó»."""
    out = []
    for x in sorted(findings, key=lambda x: mapping.get(x["fuente"], 99)):
        mark = "" if x.get("check") == "exacta" else " (casi textual)"
        out.append(f"{x['dato']} — «{x['cita']}»{mark} [{mapping.get(x['fuente'], '?')}]")
    return out


def check_note(ok, bad, unknown_cites, flagged=0):
    parts = [f"{len(ok)} datos comprobados palabra por palabra en su fuente"]
    if bad:
        parts.append(f"{len(bad)} descartados porque la cita no estaba en la página o solo había el resumen del buscador")
    if unknown_cites:
        parts.append(f"{unknown_cites} cita{'s' if unknown_cites != 1 else ''} sin respaldo marcada{'s' if unknown_cites != 1 else ''} con [?]")
    if flagged:
        parts.append(f"{flagged} fuente{'s' if flagged != 1 else ''} traía{'n' if flagged != 1 else ''} instrucciones escondidas para la IA; no las seguí")
    return "Comprobación: " + "; ".join(parts) + "."
