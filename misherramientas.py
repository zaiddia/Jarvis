"""12.52: herramientas a tu medida. «Créame una herramienta para llevar el préstamo de calculadoras»: la IA escribe una
mini-app de una sola página (HTML + JS) que funciona sin internet y guarda sus datos en el navegador de este equipo.

Por seguridad, la página se guarda con una política que le impide conectarse a cualquier sitio (no puede mandar tus
datos a ninguna parte ni cargar código de afuera). Funciones puras.
"""
import html
import re

CSP = ("<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; script-src 'unsafe-inline'; "
       "style-src 'unsafe-inline'; img-src data: blob:; font-src data:; media-src data: blob:; connect-src 'none'; "
       "form-action 'none'; frame-src 'none'; base-uri 'none'\">")
MAX_HTML = 120_000


def prompt(pedido):
    return (
        f"Crea una mini-aplicación web de UNA sola página para un docente colombiano: «{pedido}».\n"
        "Reglas obligatorias:\n"
        "- Un solo archivo HTML con <style> y <script> adentro. Nada externo: ni CDN, ni fuentes de Google, ni imágenes de "
        "internet, ni fetch/XMLHttpRequest/WebSocket. Funciona sin internet.\n"
        "- Guarda los datos en localStorage con una clave propia, y trae botones para exportar a CSV y para borrar todo "
        "(con confirmación dentro de la página, sin alert/confirm del navegador).\n"
        "- En español, letra grande y clara, botones grandes, que se vea bien en el computador y en el proyector.\n"
        "- No pidas nombres reales: deja que el docente los escriba o los pegue.\n"
        "- Sin texto de relleno ni explicaciones fuera del HTML.\n"
        "Responde SOLO con el HTML completo, empezando por <!DOCTYPE html>.")


def extract_html(raw):
    """El HTML de la respuesta (quita ``` y texto alrededor). ValueError si no hay."""
    s = str(raw or "")
    m = re.search(r"```(?:html)?\s*(.*?)```", s, re.S | re.I)
    if m:
        s = m.group(1)
    i = s.lower().find("<!doctype html")
    if i < 0:
        i = s.lower().find("<html")
    if i < 0:
        raise ValueError("la IA no devolvió la página de la herramienta")
    s = s[i:]
    j = s.lower().rfind("</html>")
    return s[: j + 7] if j >= 0 else s


def harden(page):
    """Sin red: política que bloquea conexiones, sin <script src>, <link> ni recursos de afuera."""
    p = page[:MAX_HTML]
    p = re.sub(r"<script\b[^>]*\bsrc\s*=[^>]*>\s*</script\s*>", "", p, flags=re.I)
    p = re.sub(r"<link\b[^>]*>", "", p, flags=re.I)
    p = re.sub(r"<meta[^>]+http-equiv\s*=\s*[\"']?(?:refresh|content-security-policy)[^>]*>", "", p, flags=re.I)
    p = re.sub(r"(<(?:img|iframe|audio|video|source|embed|object)\b[^>]*?\s(?:src|data)\s*=\s*[\"'])https?://[^\"']*", r"\1", p, flags=re.I)
    if re.search(r"<head\b[^>]*>", p, re.I):
        p = re.sub(r"(<head\b[^>]*>)", r"\1" + CSP.replace("\\", r"\\"), p, count=1, flags=re.I)
    else:
        p = re.sub(r"(<html\b[^>]*>)", r"\1<head>" + CSP.replace("\\", r"\\") + "</head>", p, count=1, flags=re.I)
    if not re.search(r"<meta[^>]+charset", p, re.I):
        p = p.replace(CSP, CSP + "<meta charset=\"utf-8\">", 1)
    return p


def title_of(page, pedido):
    m = re.search(r"<title>(.*?)</title>", page, re.I | re.S)
    t = html.unescape(m.group(1)).strip() if m else ""
    return re.sub(r"\s+", " ", t or pedido)[:70]


def safe_name(text):
    s = re.sub(r"[^\w áéíóúñÁÉÍÓÚÑ-]", "", str(text or "")).strip()
    return re.sub(r"\s+", " ", s)[:60] or "Herramienta"
