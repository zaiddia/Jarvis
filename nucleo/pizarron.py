"""12.0: pizarra inteligente en el proyector.

Escribes con el mouse, una tableta o el celular (que sirve de lápiz inalámbrico por la wifi del salón). Con «✨ Reconocer»
(o «Jarvis, reconoce lo que escribí») la IA lee la letra matemática, Jarvis la pasa a fórmula bonita, verifica la cuenta
con SymPy y grafica la función si escribiste una. Los estudiantes ven la pizarra en vivo en su celular con un QR, y al
terminar queda guardada como apuntes en PDF.

La lógica está en pizarra.py. Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import io
import os
import re
import secrets
import tempfile
import time

import animar
import mathtext
import pizarra
from nucleo import J

board = pizarra.new_board()
board_meta = {"code": secrets.token_urlsafe(5), "pen": secrets.token_urlsafe(8), "rec_n": 0, "busy": False, "title": "Pizarra"}


def open_window(path, title):
    """Una página de Jarvis en su propia ventana (para llevarla al proyector) o en el navegador."""
    url = J.URL + path
    if J.webview is not None and J.hud.get("window") is not None:
        try:
            J.webview.create_window(f"Jarvis · {title}", url, width=1280, height=720, min_size=(640, 360), background_color="#0e1116")
            return
        except Exception as e:
            J.note_error("VENTANA", e)
    import webbrowser
    webbrowser.open(url)


def _emit_board():
    J.socketio.emit("board", pizarra.snapshot(board))


def _urls():
    return {"ver": J._lan(f"/pz/{board_meta['code']}"), "lapiz": J._lan(f"/pz/{board_meta['code']}/lapiz?t={board_meta['pen']}")}


# ============================================================================ RECONOCER
def render_new_strokes(pad=0.03):
    """La zona con lo escrito desde el último reconocimiento, como imagen (trazos claros sobre fondo oscuro).
    → (ruta png, (x0, y0, x1, y1) normalizado) o (None, None)."""
    from PIL import Image, ImageDraw
    pg = board["pages"][board["page"]]
    new = [s for s in pg["strokes"] if s.get("n", 0) > board_meta["rec_n"] and s["p"]]
    if not new:
        new = [s for s in pg["strokes"][-12:] if s["p"]]
    if not new:
        return None, None
    xs = [p[0] for s in new for p in s["p"]]
    ys = [p[1] for s in new for p in s["p"]]
    x0, y0, x1, y1 = max(0, min(xs) - pad), max(0, min(ys) - pad), min(1, max(xs) + pad), min(1, max(ys) + pad)
    W, H = 1600, 900
    bw, bh = max(1, (x1 - x0) * W), max(1, (y1 - y0) * H)
    k = min(1400 / bw, 700 / bh, 3.0)
    im = Image.new("RGB", (int(bw * k) + 40, int(bh * k) + 40), (14, 17, 22))
    d = ImageDraw.Draw(im)
    for s in new:
        pts = [((p[0] - x0) * W * k + 20, (p[1] - y0) * H * k + 20) for p in s["p"]]
        if len(pts) > 1:
            d.line(pts, fill=(240, 240, 240), width=max(3, int(s["w"] * k * 1.2)), joint="curve")
        else:
            x, y = pts[0]
            d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=(240, 240, 240))
    fd, path = tempfile.mkstemp(suffix=".png", prefix="jarvis_pizarra_")
    os.close(fd)
    im.save(path)
    return path, (x0, y0, x1, y1)


def recognize(img_path=None, bbox=None):
    """Lee lo escrito, lo verifica y lo pone como tarjeta al lado. → la tarjeta."""
    if img_path is None:
        img_path, bbox = render_new_strokes()
        if not img_path:
            raise ValueError("No hay nada escrito para reconocer.")
    try:
        rec = pizarra.clean_recognized(J._proc_vision_json(pizarra.recognize_prompt(), img_path, 800))
    finally:
        try:
            os.remove(img_path)
        except OSError:
            pass
    item = {"latex": rec["latex"], "plano": rec["plano"], "texto": rec["texto"], "tipo": rec["tipo"], "nota": "", "ok": None, "graph": None}
    if rec["tipo"] != "texto" and rec["plano"]:
        v = pizarra.verify(rec)
        item.update(nota=v["nota"], ok=v["ok"])
        fx = pizarra.function_of(rec)
        if fx:
            try:
                item["graph"] = pizarra.sample(fx)
                item["nota"] = item["nota"] or "Gráfica de y = " + animar.pretty(fx)
            except Exception:
                pass
    x0, y0, x1, y1 = bbox or (0.05, 0.05, 0.3, 0.2)
    item["x"], item["y"] = (x1 + 0.02, y0) if x1 < 0.62 else (x0, min(0.78, y1 + 0.02))
    board_meta["rec_n"] = board.get("seq", 0)
    item = pizarra.add_item(board, item)
    _emit_board()
    return item


def _recognize_job(say=False):
    if board_meta["busy"]:
        return {"ok": False, "error": "Ya estoy leyendo la pizarra."}
    board_meta["busy"] = True
    try:
        it = recognize()
        if say:
            msg = (mathtext.speech("$" + it["latex"] + "$") if it.get("latex") else it.get("plano") or it.get("texto") or "")
            J.reply(("Escribiste: " + msg + ". " if msg else "") + (it.get("nota") or ""), "PIZARRA")
        return {"ok": True, "item": it}
    except J.AIError as e:
        return {"ok": False, "error": J.ai_error_reply(e)}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        board_meta["busy"] = False


# ============================================================================ PÁGINA DEL PROYECTOR
@J.app.route("/pizarra")
def board_page():
    from flask import render_template
    return render_template("pizarra.html", asset_v=getattr(J, "ASSET_V", ""), colors=pizarra.COLORS)


@J.app.route("/pizarra-qr.png")
def board_qr():
    import qrcode
    from flask import Response, request
    which = request.args.get("q", "ver")
    url = _urls()["lapiz" if which == "lapiz" else "ver"]
    buf = io.BytesIO()
    qrcode.make(url, box_size=10, border=2).save(buf, format="PNG")
    return Response(buf.getvalue(), mimetype="image/png", headers={"Cache-Control": "no-store"})


@J.socketio.on("board_get")
def handle_board_get(data=None):
    try:
        urls = _urls()
    except Exception:
        urls = {"ver": "", "lapiz": ""}
    return {**pizarra.snapshot(board), "urls": urls, "title": board_meta["title"]}


@J.socketio.on("board_points")
def handle_board_points(data=None):
    d = data or {}
    st = pizarra.add_points(board, d.get("id", ""), d.get("p") or [], d.get("c", ""), d.get("w", 3))
    if st:
        J.socketio.emit("board_pts", {"id": st["id"], "p": d.get("p") or [], "c": st["c"], "w": st["w"], "n": st["n"], "ver": board["ver"],
                                      "from": d.get("from", "")})
    return {"ok": bool(st)}


@J.socketio.on("board_action")
def handle_board_action(data=None):
    d = data or {}
    a = str(d.get("a", ""))
    if a == "undo":
        pizarra.undo(board)
    elif a == "erase":
        pizarra.erase(board, d.get("id", ""))
    elif a == "clear":
        pizarra.clear_page(board)
    elif a in ("nueva", "siguiente", "anterior"):
        pizarra.go_page(board, a)
    elif a == "reconocer":
        if J.state.get("ai") != "ok":
            return {"ok": False, "error": "Para reconocer la letra necesito la IA con visión conectada."}
        J.start_job("Leyendo la pizarra", lambda: _recognize_job(), "pizarra")
        return {"ok": True, "working": True}
    elif a == "pdf":
        path = save_pdf()
        return {"ok": True, "path": path, "name": os.path.basename(path)}
    elif a == "proyectar_qr":
        show_qr(d.get("q", "ver"))
    else:
        return {"ok": False}
    _emit_board()
    return {"ok": True}


def save_pdf():
    name = re.sub(r"[^\w\s-]", "", f"{board_meta['title']} {time.strftime('%Y-%m-%d %H%M')}").strip()
    path = os.path.join(J.settings["output_dir"], "Pizarras", name + ".pdf")
    pizarra.render_pdf(board, path, board_meta["title"])
    J.generated_files.add(path)
    return path


def show_qr(which="ver"):
    url = _urls()["lapiz" if which == "lapiz" else "ver"]
    J.socketio.emit("board_qr", {"url": url, "qr": f"/pizarra-qr.png?q={which}&t={int(time.time())}", "q": which})


# ============================================================================ CELULARES (wifi del salón)
def _code_ok(code):
    from flask import abort
    if str(code) != board_meta["code"]:
        abort(404)


def _pen_ok():
    import hmac
    from flask import abort, request
    if not hmac.compare_digest(str(request.args.get("t", "")), board_meta["pen"]):
        abort(403)


@J.mobile_app.route("/pz/<code>", methods=["GET"])
def board_view(code):
    from flask import render_template
    _code_ok(code)
    return render_template("pizarra_movil.html", code=code, pen="", mode="ver")


@J.mobile_app.route("/pz/<code>/datos", methods=["GET"])
def board_data(code):
    from flask import request
    _code_ok(code)
    v = request.args.get("v", "")
    if v == str(board["ver"]):
        return {"ver": board["ver"], "same": True}
    snap = pizarra.snapshot(board)
    snap["items"] = [{k: i.get(k) for k in ("id", "x", "y", "plano", "texto", "nota", "ok", "graph", "latex")} for i in snap["items"]]
    return snap


@J.mobile_app.route("/pz/<code>/lapiz", methods=["GET"])
def board_pen(code):
    from flask import render_template, request
    _code_ok(code)
    _pen_ok()
    return render_template("pizarra_movil.html", code=code, pen=request.args.get("t", ""), mode="lapiz")


@J.mobile_app.route("/pz/<code>/trazo", methods=["POST"])
def board_pen_points(code):
    from flask import request
    _code_ok(code)
    _pen_ok()
    d = request.get_json(silent=True) or {}
    return handle_board_points({**d, "from": "celular"})


@J.mobile_app.route("/pz/<code>/accion", methods=["POST"])
def board_pen_action(code):
    from flask import request
    _code_ok(code)
    _pen_ok()
    d = request.get_json(silent=True) or {}
    if d.get("a") not in ("undo", "clear", "nueva", "siguiente", "anterior", "reconocer"):
        return {"ok": False}
    return handle_board_action({"a": d["a"]})


# ============================================================================ VOZ
_BD_OPEN = re.compile(r"\b(?:abre|abreme|pon|ponme|muestra|activa|saca)\s+(?:la\s+)?pizarra(?:\s+inteligente|\s+digital|\s+del proyector)?\b")
_BD_REC = re.compile(r"\b(?:reconoce|reconoceme|pasa a formula|pasame a formula|verifica)\s+(?:lo que (?:escribi|acabo de escribir)|la pizarra|lo escrito)\b")
_BD_PDF = re.compile(r"\b(?:guarda|exporta|pasa)\s+(?:la\s+)?pizarra(?:\s+(?:en|a|como)\s+(?:pdf|apuntes))?\b|\bapuntes de la pizarra\b")
_BD_CLEAR = re.compile(r"\b(?:borra|limpia)\s+(?:la\s+)?pizarra\b")
_BD_PEN = re.compile(r"\b(?:celular|telefono|movil)\s+(?:como|de)\s+lapiz\b|\blapiz (?:inalambrico|del celular)\b|\bescribir (?:con|desde) el celular\b")
_BD_SHARE = re.compile(r"\b(?:comparte|muestra)\s+la\s+pizarra\s+(?:a|con)\s+los\s+estudiantes\b|\bqr de la pizarra\b")
_BD_PAGE = re.compile(r"\b(?:nueva pagina|otra pagina|pagina nueva)\s+(?:de|en)\s+la pizarra\b|\bpizarra nueva\b")


def _board_used():
    return any(p["strokes"] or p["items"] for p in board["pages"])


def pizarra_voice(text, t):
    if _BD_OPEN.search(t) and not _BD_PDF.search(t):
        m = re.search(r"\b(?:de|sobre|para)\s+(.+)$", t)
        if m and not re.search(r"\b(?:proyector|clase)\b", m.group(1)):
            board_meta["title"] = "Pizarra · " + m.group(1)[:50]
        J.open_window("/pizarra", "Pizarra")
        J.reply("Abrí la pizarra: escribe con el mouse o la tableta. «✨ Reconocer» pasa tu letra a fórmula, verifica la cuenta y grafica. "
                "Para escribir desde el celular: «usa el celular como lápiz».", "PIZARRA")
        return True
    if not _board_used() and not _BD_PEN.search(t) and not _BD_SHARE.search(t):
        return False                                   # sin nada escrito, «lee/guarda la pizarra» es el tablero de verdad (cámara)
    if _BD_REC.search(t):
        if J.state.get("ai") != "ok":
            J.reply("Para reconocer la letra necesito la IA con visión conectada.", "PIZARRA")
            return True
        J.start_job("Leyendo la pizarra", lambda: _recognize_job(say=True), "pizarra")
        return True
    if _BD_PDF.search(t):
        path = save_pdf()
        J._open_doc(path)
        J.reply(f"Guardé la pizarra como apuntes en PDF ({len(board['pages'])} página{'s' if len(board['pages']) != 1 else ''}): "
                "Documentos, Jarvis, Pizarras.", "PIZARRA")
        return True
    if _BD_CLEAR.search(t):
        pizarra.clear_page(board)
        _emit_board()
        J.reply("Pizarra limpia.", "PIZARRA")
        return True
    if _BD_PAGE.search(t):
        pizarra.go_page(board, "nueva")
        _emit_board()
        J.reply(f"Página {board['page'] + 1} de la pizarra.", "PIZARRA")
        return True
    if _BD_PEN.search(t) or _BD_SHARE.search(t):
        if J._need_lan():
            return True
        pen = bool(_BD_PEN.search(t))
        show_qr("lapiz" if pen else "ver")
        J.reply("Escanea el QR de la pizarra con TU celular (no lo proyectes): ese será tu lápiz." if pen else
                "En la pizarra está el QR: los estudiantes la ven en vivo en su celular.", "PIZARRA")
        return True
    return False


__all__ = ['_BD_CLEAR', '_BD_OPEN', '_BD_PAGE', '_BD_PDF', '_BD_PEN', '_BD_REC', '_BD_SHARE', '_code_ok', '_emit_board', '_pen_ok', '_recognize_job',
           '_board_used', '_urls', 'board', 'board_data', 'board_meta', 'board_page', 'board_pen', 'board_pen_action',
           'animar', 'board_pen_points', 'board_qr', 'board_view', 'pizarra_voice', 'handle_board_action', 'handle_board_get', 'handle_board_points', 'mathtext', 'open_window',
           'pizarra', 'recognize', 'render_new_strokes', 'save_pdf', 'show_qr']
