"""12.0: videos animados de matemáticas al estilo 3Blue1Brown, con la voz de Jarvis y subtítulos.

«Jarvis, hazme un video de 2 minutos que explique el teorema de Pitágoras para noveno»: la IA escribe el guion por
escenas (con un vocabulario cerrado de dibujos), los pasos de álgebra se verifican con SymPy, animar.py lo anima y lo
narra, y queda un MP4 en Documentos › Jarvis › Videos, listo para proyectar o mandar por WhatsApp. Los estudiantes
también lo pueden ver en el celular con un QR.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import asyncio
import io
import os
import re
import secrets
import time

import animar
import aula
import mathtext
from nucleo import J

video_job = {"busy": False, "cancel": False, "pct": 0, "tema": ""}
shared_videos = {}                      # código -> {"mp4", "titulo"} (para verlos en el celular)

_VM_NUM = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "medio": 0.5}


def _videos_dir():
    return os.path.join(J.settings["output_dir"], "Videos")


def _check_pasos(guion):
    """Los pasos de álgebra que la IA puso en los dibujos, verificados con SymPy: si un paso no es equivalente al
    anterior, se corta ahí (en un video para estudiantes no puede haber un paso falso)."""
    import procedimiento
    fixed = 0
    for sc in guion["escenas"]:
        v = sc.get("visual")
        if v and v["tipo"] == "pasos" and len(v["lineas"]) >= 2:
            chk = procedimiento.check_chain(v["lineas"])
            bad = next((i for i, c in enumerate(chk) if c["ok"] is False), None)
            if bad is not None:
                v["lineas"] = v["lineas"][:bad]
                fixed += 1
                if len(v["lineas"]) < 2:
                    sc["formulas"] = (sc["formulas"] + v["lineas"])[:3]
                    sc["visual"] = None
    return fixed


def _synth(text, base):
    """La narración de una escena con la voz de Jarvis (Edge; sin internet, Piper). → ruta del audio o None."""
    text = J._clean_for_speech(mathtext.speech(text))
    if not text:
        return None
    rate = int(J.settings.get("tts_rate", 0))
    if J.edge_tts is not None and not J.is_offline():
        try:
            path = base + ".mp3"
            voice = J.settings.get("tts_voice") or "es-CO-GonzaloNeural"
            asyncio.run(J.edge_tts.Communicate(text, voice, rate=f"{rate:+d}%").save(path))
            if os.path.exists(path) and os.path.getsize(path) > 0:
                return path
        except Exception as e:
            J.log_terminal(f"Video: la voz de Edge falló ({e}); pruebo con la del equipo.", "VIDEO")
    try:
        if J._ensure_piper():
            path = base + ".wav"
            J._piper_synth(text, path, rate, 0)
            return path
    except Exception:
        pass
    return None


def make_video(tema, curso="", minutos=2.0, guion=None, progress=None):
    """Guion (IA) → verificación → animación → MP4. → (resultado de animar.render, guion)."""
    g = aula.grade_of(curso) if curso else None
    if guion is None:
        subj = J._subject(curso) if curso else "Matemáticas"
        raw = J.ai_chat([{"role": "user", "content": animar.prompt(tema, f"{g}°" if g else "", minutos, subj) + J.lessons_ctx()
                          + J.book_ctx(tema, curso)}], json_mode=True, max_tokens=7000)
        guion = animar.clean(J._extract_json(raw))
    fixed = _check_pasos(guion)
    if fixed:
        J.log_terminal(f"Video: {fixed} paso(s) de álgebra no cuadraban con SymPy; los quité.", "VIDEO")
    name = animar.safe_name(guion["titulo"]) + time.strftime(" %Y-%m-%d %H%M")
    out = os.path.join(_videos_dir(), name + ".mp4")
    res = animar.render(guion, out, synth=_synth, progress=progress, cancel=lambda: video_job["cancel"])
    res["corregidos"] = fixed
    return res, guion


def share_video(path, titulo):
    code = secrets.token_urlsafe(5)
    shared_videos[code] = {"mp4": path, "titulo": titulo}
    return code


def _minutes(t):
    m = re.search(r"\b(\d+(?:[.,]\d)?|un|una|dos|tres|cuatro|cinco|medio)\s+minutos?\b", t)
    if not m:
        return 2.0 if not re.search(r"\b(?:corto|cortico|rapido)\b", t) else 1.0
    w = m.group(1)
    n = _VM_NUM.get(w)
    if n is None:
        try:
            n = float(w.replace(",", "."))
        except ValueError:
            n = 2.0
    return max(0.5, min(5.0, n))


_GRADES = r"(?:grado\s+)?(?:\d{1,2}\s?[a-z]?|sexto|septimo|octavo|noveno|decimo|undecimo|once|primero|segundo|tercero|cuarto|quinto)"
_VM_RE = re.compile(r"^(?:jarvis\s+)?(?:haz|hazme|crea|creame|genera|generame|prepara|preparame|arma|armame|produce|realiza)\s+"
                    r"(?:un|el)\s+(?:video|videito)(?:\s+(?:animado|explicativo|corto|cortico|de matematicas|estilo \w+))*"
                    r"(?:\s+de\s+(?:\d+(?:[.,]\d)?|un|una|dos|tres|cuatro|cinco|medio)\s+minutos?)?"
                    r"\s+(?:que\s+expli(?:que|ca)|explicando|para\s+explicar|sobre|acerca\s+de|de)\s+(.+?)"
                    rf"(?:\s+(?:para|en)\s+(?:el\s+|los\s+de\s+)?({_GRADES})\b.*)?$")
_VM_CANCEL = re.compile(r"\b(?:cancela|deten|para)\s+(?:el\s+)?video\b")
_VM_STATUS = re.compile(r"\b(?:como va|cuanto (?:le )?falta (?:a|al)|ya (?:esta|terminaste))\s+(?:el\s+)?video\b")


def video_anim_voice(text, t):
    if _VM_CANCEL.search(t) and video_job["busy"]:
        video_job["cancel"] = True
        J.reply("Cancelo el video.", "VIDEO")
        return True
    if _VM_STATUS.search(t) and video_job["busy"]:
        J.reply(f"Voy en el {video_job['pct']} % del video de «{video_job['tema']}».", "VIDEO")
        return True
    m = _VM_RE.match(t)
    if not m or re.search(r"https?://|youtu|\bquiz\b", t):
        return False
    tema = re.sub(r"^(?:el|la|los|las)\s+", "", m.group(1).strip())
    tema = re.sub(r"\s+(?:de|en)\s+\d+(?:[.,]\d)?\s+minutos?$", "", tema)
    if not tema:
        return False
    curso = ""
    if m.group(2):
        curso = J._resolve_course(m.group(2)) or ""
        if not curso:
            gw = aula.ORDINALES.get(m.group(2).split()[-1], m.group(2).split()[-1])
            curso = f"{gw}°" if gw.isdigit() else ""
    curso = curso or aula.data.get("activo", "")
    minutos = _minutes(t)
    if video_job["busy"]:
        J.reply(f"Ya estoy haciendo el video de «{video_job['tema']}» (va en el {video_job['pct']} %). Te aviso al terminar.", "VIDEO")
        return True
    if J.state.get("ai") != "ok":
        J.reply("Para escribir el guion del video necesito la IA conectada.", "VIDEO")
        return True
    if not animar.ffmpeg_exe():
        J.reply("Me falta el componente de video. Actualiza Jarvis o ejecuta instalar.bat (instala imageio-ffmpeg).", "VIDEO")
        return True
    video_job.update(busy=True, cancel=False, pct=0, tema=tema)
    J.reply(f"Hago el video de «{tema}»: unos {minutos:g} minutos, con dibujos animados, mi voz y subtítulos. "
            "Primero escribo el guion y luego lo animo; tarda unos minutos y te aviso.", "VIDEO")

    def prog(p, _stage):
        video_job["pct"] = int(p * 100)

    def work():
        try:
            res, guion = make_video(tema, curso, minutos, progress=prog)
        except J.AIError as e:
            J.notify(J.ai_error_reply(e), "VIDEO")
            return
        except Exception as e:
            J.notify("Cancelé el video." if video_job["cancel"] else f"No pude hacer el video: {getattr(e, 'why', e)}", "VIDEO")
            return
        finally:
            video_job["busy"] = False
        J.generated_files.add(res["mp4"])
        code = share_video(res["mp4"], guion["titulo"])
        J._open_doc(res["mp4"])
        mins, secs = divmod(int(res["segundos"]), 60)
        J.notify(f"Listo el video «{guion['titulo']}»: {mins} min {secs:02d} s, {res['escenas']} escenas"
                 + (", narrado con mi voz" if res["voz"] else " (sin voz: no hubo motor de voz disponible; lleva subtítulos)")
                 + (f"; quité {res['corregidos']} paso(s) de álgebra que no cuadraban" if res.get("corregidos") else "")
                 + ". Está en Documentos, Jarvis, Videos, con sus subtítulos. Para que lo vean en el celular: «muestra el QR del video».",
                 "VIDEO")
        video_job["last"] = code
    J.start_job("Haciendo el video animado", work, "video")
    return True


_VQR = re.compile(r"\b(?:muestra|pon|proyecta|dame)\s+(?:el\s+)?(?:qr|codigo)\s+del\s+video\b")


def video_qr_voice(text, t):
    if not _VQR.search(t):
        return False
    code = video_job.get("last")
    if not code or code not in shared_videos:
        J.reply("Aún no has hecho un video animado en esta sesión. Dime «hazme un video de 2 minutos sobre …».", "VIDEO")
        return True
    if J._need_lan():
        return True
    J._open_projector()
    J.socketio.emit("ticket", {"open": True, "url": J._lan(f"/v/{code}"), "qr": "/video-qr.png?c=" + code, "tipo": "video",
                               "tema": "Video · " + shared_videos[code]["titulo"], "n": 0})
    J.reply("El QR del video está en el proyector: lo ven en el celular, con subtítulos.", "VIDEO")
    return True


@J.mobile_app.route("/v/<code>", methods=["GET"])
def video_page(code):
    import html
    from flask import abort
    v = shared_videos.get(str(code))
    if not v:
        abort(404)
    return (f"<!DOCTYPE html><html lang='es'><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>{html.escape(v['titulo'])}</title><style>body{{margin:0;padding:14px;background:#0e1116;color:#ecf0f1;font-family:system-ui,sans-serif}}"
            "h1{color:#58c4dd;font-size:19px}video{width:100%;border-radius:10px;background:#000}</style></head><body>"
            f"<h1>▶ {html.escape(v['titulo'])}</h1><video controls playsinline preload='metadata' src='/v/{code}.mp4'>"
            f"<track kind='subtitles' srclang='es' label='Español' src='/v/{code}.vtt' default></video></body></html>")


@J.mobile_app.route("/v/<code>.mp4", methods=["GET"])
def video_file(code):
    from flask import abort, send_file
    v = shared_videos.get(str(code))
    if not v or not os.path.exists(v["mp4"]):
        abort(404)
    return send_file(v["mp4"], mimetype="video/mp4", conditional=True)


@J.mobile_app.route("/v/<code>.vtt", methods=["GET"])
def video_vtt(code):
    from flask import Response, abort
    v = shared_videos.get(str(code))
    srt = os.path.splitext(v["mp4"])[0] + ".srt" if v else ""
    if not v or not os.path.exists(srt):
        abort(404)
    body = open(srt, encoding="utf-8").read()
    body = "WEBVTT\n\n" + re.sub(r"(\d\d:\d\d:\d\d),(\d\d\d)", r"\1.\2", body)
    return Response(body, mimetype="text/vtt")


@J.app.route("/video-qr.png")
def video_qr():
    import qrcode
    from flask import Response, abort, request
    c = request.args.get("c", "")
    if c not in shared_videos:
        abort(404)
    buf = io.BytesIO()
    qrcode.make(J._lan(f"/v/{c}"), box_size=10, border=2).save(buf, format="PNG")
    return Response(buf.getvalue(), mimetype="image/png", headers={"Cache-Control": "no-store"})


__all__ = ['_VM_CANCEL', '_VM_RE', '_VM_STATUS', '_VQR', '_check_pasos', '_minutes', '_synth', '_videos_dir', 'animar', 'make_video',
           'share_video', 'shared_videos', 'video_anim_voice', 'video_file', 'video_job', 'video_page', 'video_qr', 'video_qr_voice', 'video_vtt']
