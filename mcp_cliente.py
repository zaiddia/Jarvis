"""Conectores MCP (Model Context Protocol): enchufa a Jarvis apps y servicios sin programarlos uno a uno.

MCP es el estándar que usan Claude, Goose, Jan o AnythingLLM para dar herramientas a la IA. Cada «servidor
MCP» (de Notion, de una base de datos, de la hora, de lo que sea) ofrece herramientas; Jarvis se las enseña
a su IA y, cuando le pides algo que encaja, la IA elige la herramienta y Jarvis la usa.

Configuración (el mismo formato que Claude Desktop):
    {"mcpServers": {
        "hora":   {"command": "uvx", "args": ["mcp-server-time"]},
        "remoto": {"url": "https://ejemplo.com/mcp", "headers": {"Authorization": "Bearer …"}}
    }}

Admite servidores locales (stdio: Jarvis los arranca) y remotos (HTTP «streamable»). Este módulo solo habla
el protocolo: jarvis.py decide cuándo usar cada herramienta y pide confirmación.
"""
import itertools
import json
import os
import queue
import subprocess
import threading
import time
import urllib.error
import urllib.request

PROTOCOL = "2025-06-18"
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
_ids = itertools.count(1)


class MCPError(Exception):
    pass


def parse_config(text):
    """Texto JSON de Ajustes → {nombre: {"command", "args", "env"} | {"url", "headers"}}. Lanza ValueError."""
    text = (text or "").strip()
    if not text:
        return {}
    try:
        d = json.loads(text)
    except ValueError as e:
        raise ValueError(f"La configuración MCP no es un JSON válido: {e}")
    servers = d.get("mcpServers", d) if isinstance(d, dict) else None
    if not isinstance(servers, dict):
        raise ValueError("La configuración MCP debe ser {\"mcpServers\": {\"nombre\": {…}}}.")
    out = {}
    for name, c in servers.items():
        if not isinstance(c, dict):
            raise ValueError(f"El servidor «{name}» debe ser un objeto.")
        name = str(name).strip()[:40]
        if not name or not all(ch.isalnum() or ch in "-_" for ch in name):
            raise ValueError(f"Nombre de servidor no válido: «{name}» (usa letras, números, - o _).")
        if c.get("disabled"):
            continue
        if c.get("url"):
            url = str(c["url"]).strip()
            if not url.startswith(("https://", "http://127.0.0.1", "http://localhost")):
                raise ValueError(f"«{name}»: la url debe ser https:// (o local).")
            out[name] = {"url": url, "headers": {str(k): str(v) for k, v in (c.get("headers") or {}).items()}}
        elif c.get("command"):
            out[name] = {"command": str(c["command"]), "args": [str(a) for a in (c.get("args") or [])],
                         "env": {str(k): str(v) for k, v in (c.get("env") or {}).items()}}
        else:
            raise ValueError(f"«{name}» necesita «command» (local) o «url» (remoto).")
    return out


class _Stdio:
    def __init__(self, name, cfg, log):
        self.name, self.log = name, log
        env = dict(os.environ, **cfg.get("env", {}))
        cmd = [cfg["command"], *cfg.get("args", [])]
        try:
            self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      env=env, creationflags=CREATE_NO_WINDOW, bufsize=0,
                                      shell=(os.name == "nt" and cfg["command"].lower() in ("npx", "npm", "uvx", "node")))
        except OSError as e:
            raise MCPError(f"no pude arrancar «{cfg['command']}»: {e}")
        self.pending, self.lock = {}, threading.Lock()
        threading.Thread(target=self._read, daemon=True, name=f"mcp-{name}").start()
        threading.Thread(target=self._drain, daemon=True, name=f"mcp-{name}-err").start()

    def _drain(self):
        for line in iter(self.p.stderr.readline, b""):
            pass                                   # los servidores escriben su registro aquí; no lo necesitamos

    def _read(self):
        for raw in iter(self.p.stdout.readline, b""):
            try:
                msg = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            if "id" in msg and ("result" in msg or "error" in msg):
                q = self.pending.pop(msg["id"], None)
                if q:
                    q.put(msg)
            elif "id" in msg and "method" in msg:   # el servidor nos pide algo: no lo ofrecemos
                self._send({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": "no disponible"}})
        for q in list(self.pending.values()):
            q.put({"error": {"message": "el servidor se cerró"}})

    def _send(self, obj):
        data = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
        with self.lock:
            self.p.stdin.write(data)
            self.p.stdin.flush()

    def request(self, method, params=None, timeout=30):
        if self.p.poll() is not None:
            raise MCPError("el servidor no está en marcha")
        i = next(_ids)
        q = queue.Queue()
        self.pending[i] = q
        try:
            self._send({"jsonrpc": "2.0", "id": i, "method": method, "params": params or {}})
        except OSError as e:
            self.pending.pop(i, None)
            raise MCPError(f"no pude escribirle al servidor: {e}")
        try:
            msg = q.get(timeout=timeout)
        except queue.Empty:
            self.pending.pop(i, None)
            raise MCPError(f"el servidor tardó más de {timeout} s")
        if "error" in msg:
            raise MCPError(str((msg["error"] or {}).get("message", msg["error"])))
        return msg.get("result") or {}

    def notify(self, method, params=None):
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def close(self):
        try:
            self.p.terminate()
        except Exception:
            pass


class _Http:
    def __init__(self, name, cfg, log):
        self.name, self.url, self.headers, self.session, self.log = name, cfg["url"], cfg.get("headers", {}), None, log

    def _post(self, obj, timeout=30):
        h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
             "MCP-Protocol-Version": PROTOCOL, **self.headers}
        if self.session:
            h["Mcp-Session-Id"] = self.session
        req = urllib.request.Request(self.url, data=json.dumps(obj).encode("utf-8"), headers=h, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                self.session = r.headers.get("Mcp-Session-Id") or self.session
                body = r.read().decode("utf-8", "replace")
                ctype = r.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            raise MCPError(f"el servidor respondió {e.code}" + (" (¿falta el token?)" if e.code in (401, 403) else ""))
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise MCPError(f"no llego al servidor: {getattr(e, 'reason', e)}")
        if not body.strip():
            return {}
        if "text/event-stream" in ctype:
            for line in body.splitlines():
                if line.startswith("data:"):
                    try:
                        msg = json.loads(line[5:].strip())
                    except ValueError:
                        continue
                    if msg.get("id") == obj.get("id"):
                        return msg
            return {}
        return json.loads(body)

    def request(self, method, params=None, timeout=30):
        i = next(_ids)
        msg = self._post({"jsonrpc": "2.0", "id": i, "method": method, "params": params or {}}, timeout)
        if "error" in msg:
            raise MCPError(str((msg["error"] or {}).get("message", msg["error"])))
        return msg.get("result") or {}

    def notify(self, method, params=None):
        try:
            self._post({"jsonrpc": "2.0", "method": method, "params": params or {}})
        except MCPError:
            pass

    def close(self):
        pass


class Server:
    """Un servidor MCP conectado, con sus herramientas."""

    def __init__(self, name, cfg, version="", log=print):
        self.name, self.cfg, self.log = name, cfg, log
        self.tools, self.error, self.conn = [], "", None
        self.version = version

    def start(self):
        try:
            self.conn = (_Http if "url" in self.cfg else _Stdio)(self.name, self.cfg, self.log)
            self.conn.request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                             "clientInfo": {"name": "Jarvis", "version": self.version}}, timeout=60)
            self.conn.notify("notifications/initialized")
            tools, cursor = [], None
            for _ in range(10):
                r = self.conn.request("tools/list", {"cursor": cursor} if cursor else {})
                tools += r.get("tools") or []
                cursor = r.get("nextCursor")
                if not cursor:
                    break
            self.tools = [t for t in tools if isinstance(t, dict) and t.get("name")]
            self.error = ""
        except MCPError as e:
            self.error = str(e)
            self.close()
        return self

    @property
    def ok(self):
        return self.conn is not None and not self.error

    def call(self, tool, args, timeout=60):
        if not self.ok:
            raise MCPError(self.error or "no conectado")
        r = self.conn.request("tools/call", {"name": tool, "arguments": args or {}}, timeout=timeout)
        return result_text(r), bool(r.get("isError"))

    def close(self):
        if self.conn:
            self.conn.close()
        self.conn = None


def result_text(r, limit=8000):
    """El contenido de una respuesta de herramienta, en texto."""
    out = []
    for c in r.get("content") or []:
        if c.get("type") == "text":
            out.append(str(c.get("text", "")))
        elif c.get("type") == "resource":
            res = c.get("resource") or {}
            out.append(str(res.get("text") or res.get("uri") or ""))
        elif c.get("type") in ("image", "audio"):
            out.append(f"[{c['type']}]")
    if not out and r.get("structuredContent") is not None:
        out.append(json.dumps(r["structuredContent"], ensure_ascii=False))
    text = "\n".join(x for x in out if x).strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def tool_id(server, tool):
    return f"mcp__{server}__{tool}"


def split_id(tid):
    if not str(tid).startswith("mcp__"):
        return None
    rest = str(tid)[5:]
    if "__" not in rest:
        return None
    s, t = rest.split("__", 1)
    return s, t


def describe(server, tool, max_desc=160):
    """Una línea para el enrutador de la IA: «- mcp__hora__get_time(timezone*): Obtiene la hora…»."""
    schema = tool.get("inputSchema") or {}
    props = schema.get("properties") or {}
    req = set(schema.get("required") or [])
    args = ", ".join(f"{k}{'*' if k in req else ''}" for k in list(props)[:8])
    desc = " ".join(str(tool.get("description", "")).split())[:max_desc]
    return f"- {tool_id(server, tool['name'])}({args}): {desc} [conector {server}]"


class Hub:
    """Todos los servidores configurados."""

    def __init__(self, version="", log=print):
        self.version, self.log = version, log
        self.servers = {}
        self.lock = threading.Lock()

    def configure(self, text):
        cfg = parse_config(text)
        with self.lock:
            old = self.servers
            self.servers = {}
        for s in old.values():
            s.close()
        for name, c in cfg.items():
            s = Server(name, c, self.version, self.log).start()
            with self.lock:
                self.servers[name] = s
            self.log(f"MCP «{name}»: " + (f"{len(s.tools)} herramientas." if s.ok else f"no conecta ({s.error})."))
        return self.status()

    def status(self):
        return [{"nombre": n, "ok": s.ok, "error": s.error, "herramientas": [t["name"] for t in s.tools]}
                for n, s in self.servers.items()]

    def catalog(self, limit=40):
        lines = []
        for n, s in self.servers.items():
            if s.ok:
                lines += [describe(n, t) for t in s.tools]
        return lines[:limit]

    def find(self, tid):
        p = split_id(tid)
        if not p or p[0] not in self.servers:
            return None
        s = self.servers[p[0]]
        return s if any(t["name"] == p[1] for t in s.tools) else None

    def call(self, tid, args):
        s = self.find(tid)
        if not s:
            raise MCPError("esa herramienta no existe")
        t0 = time.time()
        text, is_err = s.call(split_id(tid)[1], args)
        self.log(f"MCP {tid} ({time.time() - t0:.1f} s){' con error' if is_err else ''}")
        return text, is_err

    def close(self):
        for s in self.servers.values():
            s.close()
