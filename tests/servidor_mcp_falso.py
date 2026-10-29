"""Servidor MCP mínimo para las pruebas (habla el protocolo por stdio, como uno de verdad)."""
import json
import sys

TOOLS = [{"name": "sumar", "description": "Suma dos números", "inputSchema": {"type": "object",
          "properties": {"a": {"type": "number"}, "b": {"type": "number"}}, "required": ["a", "b"]}},
         {"name": "saludo", "description": "Saluda a alguien", "inputSchema": {"type": "object", "properties": {"nombre": {"type": "string"}}}}]

for line in sys.stdin:
    try:
        m = json.loads(line)
    except ValueError:
        continue
    if "id" not in m:
        continue
    i, method, p = m["id"], m.get("method"), m.get("params") or {}
    if method == "initialize":
        r = {"protocolVersion": p.get("protocolVersion"), "capabilities": {"tools": {}}, "serverInfo": {"name": "falso", "version": "1"}}
    elif method == "tools/list":
        r = {"tools": TOOLS}
    elif method == "tools/call":
        a = p.get("arguments") or {}
        if p.get("name") == "sumar":
            r = {"content": [{"type": "text", "text": str(a.get("a", 0) + a.get("b", 0))}]}
        else:
            r = {"content": [{"type": "text", "text": f"Hola, {a.get('nombre', 'nadie')}"}]}
    else:
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": i, "error": {"code": -32601, "message": "no"}}) + "\n")
        sys.stdout.flush()
        continue
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": i, "result": r}) + "\n")
    sys.stdout.flush()
