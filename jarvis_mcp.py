"""Jarvis como servidor MCP: deja que Claude Desktop (u otra IA compatible con MCP) le dé órdenes a Jarvis.

En Claude Desktop › Configuración › Desarrollador › Editar configuración, añade:
    {"mcpServers": {"jarvis": {"command": "C:\\\\Jarvis\\\\.venv\\\\Scripts\\\\python.exe",
                               "args": ["C:\\\\Jarvis\\\\jarvis_mcp.py"]}}}
(Jarvis te muestra las rutas exactas en Ajustes › Integraciones › Conectores MCP.)

Este programa no hace nada por sí mismo: le pasa la orden al Jarvis que está abierto en tu equipo, por
la dirección local y con un código secreto que solo tu usuario de Windows puede leer. Jarvis aplica las
mismas reglas que con el celular: nada de apagar, cerrar programas, escribir en ventanas ni borrar datos.
"""
import json
import os
import sys
import urllib.error
import urllib.request

VERSION = "1"


def _config_dir():
    here = os.path.dirname(os.path.abspath(__file__))
    if os.path.exists(os.path.join(here, "portable")):
        return os.path.join(here, "datos")
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "Jarvis")


def _link():
    try:
        with open(os.path.join(_config_dir(), "mcp_enlace.json"), encoding="utf-8") as f:
            d = json.load(f)
        return d["url"], d["token"]
    except (OSError, ValueError, KeyError):
        return None, None


def _ask_jarvis(tool, args):
    url, token = _link()
    if not url:
        return "Jarvis no está abierto, o no tiene activado «Dejar que otras IA usen Jarvis (MCP)» en Ajustes.", True
    req = urllib.request.Request(url + "/api/mcp", data=json.dumps({"tool": tool, "args": args}).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "X-Jarvis-Token": token}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read().decode("utf-8"))
        return str(d.get("text", "")), bool(d.get("error"))
    except urllib.error.HTTPError as e:
        return f"Jarvis rechazó la petición ({e.code}).", True
    except (urllib.error.URLError, OSError, ValueError) as e:
        return f"No pude hablar con Jarvis: {getattr(e, 'reason', e)}. ¿Está abierto?", True


TOOLS = [
    {"name": "jarvis_orden",
     "description": "Le da una orden a Jarvis, el asistente de voz del PC del usuario, en español y como la diría una "
                    "persona: «pon un temporizador de 10 minutos», «sube el volumen», «abre Spotify», «¿qué tengo hoy?», "
                    "«recuérdame mañana a las 9 llamar al banco», «pon Despacito en YouTube», «modo clase». Devuelve lo "
                    "que contestó Jarvis. No apaga ni reinicia el equipo, no cierra programas ni borra datos.",
     "inputSchema": {"type": "object", "properties": {"texto": {"type": "string", "description": "La orden en español"}},
                     "required": ["texto"]}},
    {"name": "jarvis_decir",
     "description": "Hace que Jarvis diga algo en voz alta en el PC del usuario (por ejemplo, un aviso).",
     "inputSchema": {"type": "object", "properties": {"texto": {"type": "string"}}, "required": ["texto"]}},
    {"name": "jarvis_estado",
     "description": "Cómo está Jarvis: micrófono, IA, temporizadores en marcha, lo pendiente de hoy y la última conversación.",
     "inputSchema": {"type": "object", "properties": {}}},
]


def _reply(i, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": i}
    if error:
        msg["error"] = {"code": -32603, "message": error}
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        method, i = msg.get("method"), msg.get("id")
        if i is None:
            continue                               # notificaciones: nada que responder
        if method == "initialize":
            _reply(i, {"protocolVersion": (msg.get("params") or {}).get("protocolVersion", "2025-06-18"),
                       "capabilities": {"tools": {}}, "serverInfo": {"name": "jarvis", "version": VERSION}})
        elif method == "tools/list":
            _reply(i, {"tools": TOOLS})
        elif method == "tools/call":
            p = msg.get("params") or {}
            text, err = _ask_jarvis(p.get("name", ""), p.get("arguments") or {})
            _reply(i, {"content": [{"type": "text", "text": text}], "isError": err})
        elif method == "ping":
            _reply(i, {})
        else:
            _reply(i, error=f"método no disponible: {method}")


if __name__ == "__main__":
    main()
