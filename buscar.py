"""Búsqueda web hablada: Jarvis busca en internet, lee los primeros resultados y los resume
en voz, con la fuente. Usa DuckDuckGo (HTML, sin clave) y, si falla, Google Noticias.

jarvis.py hace las peticiones; aquí solo se arman direcciones y se interpreta el resultado.
"""
import html
import re
import urllib.parse

DDG = "https://duckduckgo.com/html/"
DDG_LITE = "https://lite.duckduckgo.com/lite/"


def search_url(query, lite=False):
    q = urllib.parse.urlencode({"q": query, "kl": "co-es"})
    return (DDG_LITE if lite else DDG) + "?" + q


_RESULT = re.compile(r'result__a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)
_SNIPPET = re.compile(r'result__snippet[^>]*>(.*?)</a>', re.I | re.S)
_LITE_LINK = re.compile(r'<a[^>]*class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)


def _clean(h):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", h or ""))).strip()


def _real_url(href):
    """DuckDuckGo envuelve los enlaces: //duckduckgo.com/l/?uddg=<url real>."""
    m = re.search(r"[?&]uddg=([^&]+)", href or "")
    if m:
        return urllib.parse.unquote(m.group(1))
    if href and href.startswith("//"):
        return "https:" + href
    return href or ""


def parse_results(html_text, limit=6):
    """[{titulo, url, resumen, fuente}] a partir del HTML de DuckDuckGo."""
    out, seen = [], set()
    links = _RESULT.findall(html_text or "")
    snips = _SNIPPET.findall(html_text or "")
    if not links:                                      # versión «lite»
        links = _LITE_LINK.findall(html_text or "")
        snips = []
    for i, (href, title) in enumerate(links):
        url = _real_url(href)
        title = _clean(title)
        if not title or not url.startswith("http"):
            continue
        host = urllib.parse.urlsplit(url).netloc.replace("www.", "")
        if host in seen:
            continue
        seen.add(host)
        out.append({"titulo": title, "url": url, "fuente": host,
                    "resumen": _clean(snips[i]) if i < len(snips) else ""})
        if len(out) >= limit:
            break
    return out


def prompt(query, results):
    bloques = []
    for r in results:
        linea = f"- {r['titulo']} ({r['fuente']})"
        if r["resumen"]:
            linea += f": {r['resumen']}"
        bloques.append(linea)
    return ("Eres Jarvis, el asistente de un docente en Colombia. El usuario preguntó: "
            f"«{query}».\nEstos son resultados de una búsqueda en internet de hoy:\n"
            + "\n".join(bloques) +
            "\n\nResponde a su pregunta en voz alta, en español, de forma clara y breve (2 a 5 frases), "
            "usando solo lo que aparezca en los resultados. Si hay fechas o cifras, menciónalas. Nombra la "
            "fuente principal cuando ayude. Si los resultados no responden la pregunta, dilo con sinceridad. "
            "Sin listas ni markdown: es para escucharse. Termina sin preguntas.")


def spoken_fallback(query, results, n=3):
    if not results:
        return f"No encontré resultados claros sobre {query}."
    tops = [f"{r['titulo']}, de {r['fuente']}" for r in results[:n]]
    return f"Esto encontré sobre {query}: " + ". ".join(tops) + "."


def sources(results, n=3):
    return [{"titulo": r["titulo"], "url": r["url"], "fuente": r["fuente"]} for r in results[:n]]
