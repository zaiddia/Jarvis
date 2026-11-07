"""12.0: geometría en 3D y realidad aumentada en el navegador del celular, sin instalar nada.

Los estudiantes escanean un QR y ven el sólido (prisma, pirámide, cono, cilindro, esfera…) en su celular: lo giran, lo
cortan con un plano (y ven la sección y su área), lo despliegan (desarrollo plano) y miden (áreas, volumen, caras,
vértices y aristas). Con «📷 Sobre mi pupitre» el sólido aparece sobre la foto de su pupitre (o sobre la cámara en vivo
cuando el navegador lo permite). El dibujo 3D lo hace la propia página: funciona sin internet.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import io
import re

from nucleo import J

SOLIDS = {"cubo": r"cubo|hexaedro", "ortoedro": r"prisma rectangular|ortoedro|caja|paralelepipedo", "prisma": r"prismas?",
          "piramide": r"piramides?", "cilindro": r"cilindros?", "cono": r"conos?", "esfera": r"esferas?|bola|pelota"}


def _kind(t):
    for k in ("ortoedro", "cubo", "piramide", "cilindro", "cono", "esfera", "prisma"):
        if re.search(rf"\b(?:{SOLIDS[k]})\b", t):
            return k
    return ""


@J.app.route("/solidos")
@J.app.route("/solidos/<kind>")
def solids_page(kind=""):
    from flask import render_template
    return render_template("solidos.html", kind=kind if kind in SOLIDS else "")


@J.mobile_app.route("/s3d", methods=["GET"])
@J.mobile_app.route("/s3d/<kind>", methods=["GET"])
def solids_mobile(kind=""):
    from flask import render_template
    return render_template("solidos.html", kind=kind if kind in SOLIDS else "")


@J.app.route("/solidos-qr.png")
def solids_qr():
    import qrcode
    from flask import Response, request
    k = request.args.get("k", "")
    buf = io.BytesIO()
    qrcode.make(J._lan("/s3d" + (f"/{k}" if k in SOLIDS else "")), box_size=10, border=2).save(buf, format="PNG")
    return Response(buf.getvalue(), mimetype="image/png", headers={"Cache-Control": "no-store"})


_S3_RE = re.compile(r"\b(?:abre|abreme|muestra|muestrame|muestrales|pon|ponme|ensename|ensenales|proyecta|lanza)\s+(?:los\s+|el\s+|la\s+|un\s+|una\s+)?"
                    r"(?:solidos?(?:\s+geometricos)?|cuerpos geometricos|geometria|figuras?|cubo|hexaedro|prismas?(?:\s+rectangular)?|ortoedro|piramides?|"
                    r"cilindros?|conos?|esferas?)\b.*\b(?:3d|tres de|en tres dimensiones|realidad aumentada|aumentada|celular|celulares)\b|"
                    r"\b(?:geometria|solidos) en realidad aumentada\b|\bsolidos (?:en )?3d\b")


def solids_voice(text, t):
    if not _S3_RE.search(t):
        return False
    k = _kind(t)
    phones = bool(re.search(r"\b(?:celular|celulares|estudiantes|qr|realidad aumentada|aumentada)\b", t))
    if phones:
        if J._need_lan():
            return True
        J._open_projector()
        J.socketio.emit("ticket", {"open": True, "url": J._lan("/s3d" + (f"/{k}" if k else "")), "qr": "/solidos-qr.png?k=" + k, "tipo": "solidos",
                                   "tema": "Sólidos en 3D" + (f" · {k}" if k else ""), "n": 0})
        J.reply("El QR está en el proyector: lo abren en el navegador del celular, sin instalar nada. Lo giran con el dedo, «✂ Corte» muestra "
                "la sección, «📐 Desplegar» el desarrollo plano y «📷 Sobre mi pupitre» lo pone sobre la foto de su pupitre.", "SÓLIDOS")
        return True
    J.open_window("/solidos" + (f"/{k}" if k else ""), "Sólidos")
    J.reply("Abrí los sólidos en 3D" + (f" con el {k}" if k else "") + ". Para que los estudiantes lo vean en el celular: «muéstrales los sólidos en 3D "
            "en el celular».", "SÓLIDOS")
    return True


__all__ = ['SOLIDS', '_S3_RE', '_kind', 'solids_mobile', 'solids_page', 'solids_qr', 'solids_voice']
