"""Galería de conectores (7.7): añadir conectores MCP con un formulario en vez de escribir JSON.

Cada conector de la galería sabe qué datos pide (una clave, una dirección) y cómo queda su configuración. Al añadirlo
se mezcla con la configuración MCP que ya tienes (el mismo formato de Claude Desktop) y Jarvis lo conecta.
Los conectores locales necesitan Node.js (npx) o uv (uvx) instalados; la galería te dice si faltan.
"""
import json
import re
import shutil

PRESETS = {
    "homeassistant": {
        "nombre": "Home Assistant (tu casa)", "icono": "⌂",
        "descripcion": "Luces, enchufes, clima, escenas y automatizaciones de tu casa: «apaga las luces de la sala», "
                       "«¿qué temperatura hay?». Usa el conector oficial de la comunidad (ha-mcp, unas 90 herramientas).",
        "campos": [{"key": "url", "label": "Dirección del conector", "placeholder": "http://homeassistant.local:8123/api/…",
                    "ayuda": "En Home Assistant: HACS › instala «HA-MCP» › Ajustes › Dispositivos › Añadir integración "
                             "«HA-MCP Server» › Configurar › copia la dirección (connect URL)."}],
        "necesita": "", "confianza": False},
    "github": {
        "nombre": "GitHub", "icono": "⌥",
        "descripcion": "Tus repositorios, issues y pull requests: «¿qué issues nuevos tengo?».",
        "campos": [{"key": "token", "label": "Token personal de GitHub", "secret": True, "placeholder": "github_pat_…",
                    "ayuda": "github.com › Settings › Developer settings › Personal access tokens."}],
        "necesita": "", "confianza": False},
    "notion": {
        "nombre": "Notion", "icono": "▤",
        "descripcion": "Busca y lee tus páginas y bases de datos de Notion, y crea páginas nuevas.",
        "campos": [{"key": "token", "label": "Clave de integración de Notion", "secret": True, "placeholder": "ntn_…",
                    "ayuda": "notion.so/profile/integrations › Nueva integración › copia la clave; luego comparte con "
                             "ella las páginas que quieras que vea."}],
        "necesita": "npx", "confianza": False},
    "todoist": {
        "nombre": "Todoist (tareas)", "icono": "✓",
        "descripcion": "Tus tareas y proyectos de Todoist: «¿qué tengo pendiente en Todoist?», «añade comprar marcadores».",
        "campos": [{"key": "token", "label": "Clave de la API de Todoist", "secret": True, "placeholder": "0123abc…",
                    "ayuda": "Todoist › Configuración › Integraciones › Desarrollador › copia la clave."}],
        "necesita": "npx", "confianza": False},
    "hora": {
        "nombre": "Hora en el mundo", "icono": "◷",
        "descripcion": "La hora en cualquier ciudad y conversión de zonas horarias.",
        "campos": [], "necesita": "uvx", "confianza": True},
    "web": {
        "nombre": "Leer páginas web", "icono": "↯",
        "descripcion": "Le da a la IA una herramienta para abrir y leer una página web concreta cuando se la pides.",
        "campos": [], "necesita": "uvx", "confianza": True},
}


def build(pid, values):
    """(nombre_del_servidor, configuración) para el conector. Lanza ValueError si falta algo."""
    p = PRESETS.get(pid)
    if not p:
        raise ValueError("Ese conector no está en la galería.")
    v = {k: str(x).strip() for k, x in (values or {}).items()}
    for c in p["campos"]:
        if not v.get(c["key"]):
            raise ValueError(f"Falta: {c['label']}.")
    if pid == "homeassistant":
        if not re.match(r"^https?://", v["url"]):
            raise ValueError("La dirección debe empezar por http:// o https://")
        return "casa", {"url": v["url"]}
    if pid == "github":
        return "github", {"url": "https://api.githubcopilot.com/mcp/", "headers": {"Authorization": f"Bearer {v['token']}"}}
    if pid == "notion":
        return "notion", {"command": "npx", "args": ["-y", "@notionhq/notion-mcp-server"], "env": {"NOTION_TOKEN": v["token"]}}
    if pid == "todoist":
        return "todoist", {"command": "npx", "args": ["-y", "@doist/todoist-ai"], "env": {"TODOIST_API_KEY": v["token"]}}
    if pid == "hora":
        return "hora", {"command": "uvx", "args": ["mcp-server-time", "--local-timezone=America/Bogota"]}
    if pid == "web":
        return "web", {"command": "uvx", "args": ["mcp-server-fetch"]}
    raise ValueError("Conector desconocido.")


def _load(text):
    text = (text or "").strip()
    if not text:
        return {"mcpServers": {}}
    d = json.loads(text)
    if "mcpServers" not in d:
        d = {"mcpServers": d}
    return d


def add(config_text, name, cfg):
    d = _load(config_text)
    d["mcpServers"][name] = cfg
    return json.dumps(d, ensure_ascii=False, indent=2)


def remove(config_text, name):
    d = _load(config_text)
    d["mcpServers"].pop(name, None)
    return json.dumps(d, ensure_ascii=False, indent=2) if d["mcpServers"] else ""


def installed(config_text):
    try:
        return sorted(_load(config_text)["mcpServers"])
    except (ValueError, TypeError, AttributeError):
        return []


def missing_tool(pid):
    """«npx» o «uvx» si el conector los necesita y no están instalados; "" si está todo."""
    need = PRESETS.get(pid, {}).get("necesita", "")
    return need if need and not shutil.which(need) else ""


def public():
    return [{"id": k, **{x: v[x] for x in ("nombre", "icono", "descripcion", "campos", "necesita", "confianza")},
             "falta": missing_tool(k)} for k, v in PRESETS.items()]
