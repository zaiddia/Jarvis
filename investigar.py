"""Investigación con fuentes (7.5): «investiga a fondo la deforestación en la Amazonía» → un documento con citas.

Pasos (jarvis.py hace las peticiones):
  1. Plan: 3 búsquedas distintas sobre el tema (con la IA; sin ella, variantes fijas).
  2. Busca en internet (DuckDuckGo, como «busca en internet…») y junta hasta 8 fuentes distintas.
  3. Lee cada página y saca su texto principal.
  4. La IA escribe un informe en español con cada dato citado [1], [2]… y sin inventar.
  5. Se guarda como Word (o HTML) en Documentos\\Jarvis\\Investigaciones, con la lista de fuentes y sus enlaces.
"""
import datetime
import html
import json
import re
import unicodedata
import urllib.parse

MAX_SOURCES = 8
MAX_CHARS = 3500

_SKIP_HOSTS = ("youtube.com", "youtu.be", "facebook.com", "instagram.com", "tiktok.com", "x.com", "twitter.com",
               "pinterest.", "linkedin.com", "amazon.", "mercadolibre.")


def plan_prompt(topic):
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
            return qs[:4]
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
    css = ("body{font-family:Segoe UI,Arial,sans-serif;max-width:820px;margin:40px auto;padding:0 20px;line-height:1.6;color:#1b2430}"
           "h1{color:#0b5f7a}h2{color:#0b5f7a;border-bottom:1px solid #d5e3ea;padding-bottom:4px;margin-top:28px}"
           ".meta{color:#667}.res{background:#eef7fb;border-left:4px solid #2ab3d6;padding:12px 16px}"
           "sup a{text-decoration:none;color:#0b7fa3}li{margin:4px 0}")
    return (f"<!doctype html><html lang='es'><head><meta charset='utf-8'><title>{esc(report['titulo'])}</title>"
            f"<style>{css}</style></head><body>" + "\n".join(body) + "</body></html>")
