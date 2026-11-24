"""12.50: Estudio de cine. «Jarvis, crea una película sobre el ciclo del agua para quinto»: la IA (la de trabajos pesados)
escribe el guion, las fichas de personajes y escenarios y las instrucciones de cada escena; queda una página con botones
«Copiar» para pegarlas en Google Flow o Meta Vibes. Cuando bajas los clips a la carpeta del proyecto, «arma la película»
los une con la narración de Jarvis, subtítulos y música si pusiste una.

Jarvis no maneja esas páginas: tú pegas y descargas. La lógica está en cine.py. Los nombres globales se usan como J.<nombre>.
"""
import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
import time

import animar
import cine
from nucleo import J

cine_state = {"busy": False, "pct": 0, "titulo": "", "last": ""}
_CINE_N = {"tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "doce": 12, "quince": 15}


def cine_dir():
    return os.path.join(J.settings["output_dir"], "Cine")


def cine_last_project():
    """La carpeta del proyecto más reciente (el de esta sesión o el último guardado)."""
    if cine_state["last"] and os.path.exists(os.path.join(cine_state["last"], "proyecto.json")):
        return cine_state["last"]
    found = sorted(glob.glob(os.path.join(cine_dir(), "*", "proyecto.json")), key=os.path.getmtime)
    return os.path.dirname(found[-1]) if found else ""


def cine_create(idea, curso="", escenas=8, estilo=""):
    """Guion + fichas + escenas → carpeta del proyecto. → (carpeta, página, guion)."""
    raw = J.ai_chat([{"role": "user", "content": cine.prompt(idea, curso, escenas, estilo)}], json_mode=True, max_tokens=6000)
    g = cine.clean(J._extract_json(raw))
    folder = os.path.join(cine_dir(), cine.safe_name(g["titulo"]) + time.strftime(" %Y-%m-%d %H%M"))
    page = cine.save_project(g, folder)
    cine_state["last"] = folder
    return folder, page, g


def _music_in(folder):
    for ext in ("mp3", "m4a", "wav", "ogg"):
        hits = [p for p in glob.glob(os.path.join(folder, f"*.{ext}"))]
        if hits:
            return sorted(hits)[0]
    return ""


def cine_assemble(folder, progress=None, synth=None):
    """Une los clips de «clips» en orden, con la narración de cada escena, subtítulos y música (si hay un .mp3 en la
    carpeta del proyecto). → {"mp4", "srt", "clips", "segundos", "voz"}."""
    ffmpeg = animar.ffmpeg_exe()
    if not ffmpeg:
        raise ValueError("falta el componente de video (imageio-ffmpeg)")
    with open(os.path.join(folder, "proyecto.json"), encoding="utf-8") as f:
        g = json.load(f)
    clips_dir = os.path.join(folder, "clips")
    files = [(p, os.path.getmtime(p)) for p in glob.glob(os.path.join(clips_dir, "*")) if p.lower().endswith(cine.CLIP_EXT)]
    clips = cine.clip_order(files, len(g["escenas"]))
    if not clips:
        raise ValueError(f"no hay clips en la carpeta «clips» del proyecto ({clips_dir})")
    synth = synth or J._synth
    work = tempfile.mkdtemp(prefix="jarvis-cine-")
    parts, subs, t, voz = [], [], 0.0, 0
    try:
        for i, clip in enumerate(clips):
            sc = g["escenas"][i] if i < len(g["escenas"]) else {"narracion": ""}
            if progress:
                progress(i / (len(clips) + 1), f"escena {i + 1}")
            narr, narr_s = None, 0.0
            if sc.get("narracion"):
                try:
                    narr = synth(sc["narracion"], os.path.join(work, f"n{i:02d}"))
                except Exception:
                    narr = None
                if narr:
                    narr_s = cine.media_info(ffmpeg, narr)[0]
                    voz += 1
            secs, has_audio = cine.media_info(ffmpeg, clip)
            out = os.path.join(work, f"s{i:02d}.mp4")
            cmd, dur = cine.scene_cmd(ffmpeg, clip, secs or 5.0, has_audio, narr, narr_s, out)
            subprocess.run(cmd, check=True, capture_output=True, creationflags=animar._no_window(), timeout=600)
            parts.append(out)
            if sc.get("narracion"):
                subs.append((t + 0.2, t + max(1.0, min(dur, (narr_s or dur) + 0.3)), sc["narracion"]))
            t += dur
        if progress:
            progress(len(clips) / (len(clips) + 1), "uniendo")
        lst = os.path.join(work, "lista.txt")
        with open(lst, "w", encoding="utf-8") as f:
            f.write("".join(f"file '{p.replace(os.sep, '/')}'\n" for p in parts))
        joined = os.path.join(work, "unida.mp4")
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined],
                       check=True, capture_output=True, creationflags=animar._no_window(), timeout=600)
        srt_path = os.path.join(folder, cine.safe_name(g["titulo"]) + ".srt")
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(cine.srt(subs))
        final = os.path.join(folder, cine.safe_name(g["titulo"]) + ".mp4")
        music = _music_in(folder)
        cmd = [ffmpeg, "-y", "-loglevel", "error", "-i", joined]
        if music:
            cmd += ["-stream_loop", "-1", "-i", music, "-i", srt_path, "-filter_complex",
                    "[1:a]aformat=sample_rates=44100:channel_layouts=stereo,volume=0.12[m];[0:a][m]amix=inputs=2:duration=first:normalize=0[a]",
                    "-map", "0:v", "-map", "[a]", "-map", "2:s", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k"]
        else:
            cmd += ["-i", srt_path, "-map", "0:v", "-map", "0:a", "-map", "1:s", "-c:v", "copy", "-c:a", "copy"]
        cmd += ["-c:s", "mov_text", "-metadata:s:s:0", "language=spa", final]
        subprocess.run(cmd, check=True, capture_output=True, creationflags=animar._no_window(), timeout=600)
        return {"mp4": final, "srt": srt_path, "clips": len(clips), "escenas": len(g["escenas"]), "segundos": t, "voz": voz,
                "musica": bool(music), "titulo": g["titulo"]}
    finally:
        shutil.rmtree(work, ignore_errors=True)


_CINE_GRADES = r"(?:grado\s+)?(?:\d{1,2}\s?[a-z]?|sexto|septimo|octavo|noveno|decimo|undecimo|once|primero|segundo|tercero|cuarto|quinto)"
_CINE_NEW = re.compile(r"^(?:jarvis\s+)?(?:haz|hazme|crea|creame|escribe|escribeme|prepara|preparame|arma|armame|produce|inventa)\s+"
                       r"(?:una|un)\s+(?:pelicula|peli|cortometraje|corto animado|corto|cortico animado)"
                       r"(?:\s+(?:corta|animada|educativa|de (?:\d{1,2}|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|doce|quince) escenas))*"
                       r"\s+(?:sobre|de|acerca de|que (?:cuente|trate|explique)(?: de| sobre)?)\s+(.+?)"
                       rf"(?:\s+(?:para|en)\s+(?:el\s+|los\s+de\s+)?({_CINE_GRADES})\b.*)?$")
_CINE_BUILD = re.compile(r"\b(?:arma|armame|monta|montame|une|uneme|junta|edita|termina|terminame|finaliza|ensambla)\s+"
                         r"(?:la\s+|mi\s+)?(?:pelicula|peli|cortometraje|los clips(?: de la pelicula)?)\b")
_CINE_OPEN = re.compile(r"\b(?:abre|muestrame|ensename|dame)\s+(?:las\s+)?(?:escenas|el guion|el proyecto)\s+de\s+la\s+pelicula\b|"
                        r"\babre\s+(?:el\s+)?estudio de cine\b")


def _cine_scenes(t):
    m = re.search(r"\bde (\d{1,2}|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|doce|quince) escenas\b", t)
    if not m:
        return 8
    n = _CINE_N.get(m.group(1)) or int(m.group(1))
    return max(3, min(cine.MAX_SCENES, n))


def cine_voice(text, t):
    if _CINE_OPEN.search(t):
        folder = cine_last_project()
        if not folder:
            J.reply("Todavía no hay películas. Dime, por ejemplo, «crea una película sobre el ciclo del agua para quinto».", "CINE")
        else:
            J._open_doc(os.path.join(folder, "escenas para copiar.html"))
            J.reply("Abrí las escenas de la película para copiar.", "CINE")
        return True
    if _CINE_BUILD.search(t):
        return _cine_build_start()
    m = _CINE_NEW.match(t)
    if not m or re.search(r"https?://|youtu", t):
        return False
    idea = re.sub(r"\s+de (?:\d{1,2}|\w+) escenas$", "", m.group(1).strip())
    curso = ""
    if m.group(2):
        curso = J._resolve_course(m.group(2)) or m.group(2)
    if cine_state["busy"]:
        J.reply(f"Ya estoy trabajando en «{cine_state['titulo']}». Te aviso al terminar.", "CINE")
        return True
    if J.state.get("ai") != "ok":
        J.reply("Para escribir el guion necesito la IA conectada.", "CINE")
        return True
    n = _cine_scenes(t)
    cine_state.update(busy=True, pct=0, titulo=idea)
    J.reply(f"Escribo la película sobre «{idea}»: {n} escenas, con personajes que no cambian de una escena a otra. "
            "Te aviso cuando estén listas para pegar en Google Flow o Meta Vibes.", "CINE")

    def work():
        try:
            folder, page, g = cine_create(idea, curso, n)
        except J.AIError as e:
            J.notify(J.ai_error_reply(e), "CINE")
            return
        except Exception as e:
            J.notify(f"No pude escribir la película: {getattr(e, 'why', e)}", "CINE")
            return
        finally:
            cine_state["busy"] = False
        J.generated_files.add(page)
        J._open_doc(page)
        J.notify(f"Lista la película «{g['titulo']}»: {len(g['escenas'])} escenas y {len(g['personajes'])} personajes. Te abrí la "
                 "página con un botón «Copiar» en cada escena: pégalas en Google Flow o en Meta Vibes y descarga cada clip a la "
                 "carpeta «clips» del proyecto con su número (escena 1, escena 2…). Luego dime «arma la película».", "CINE")
    J.start_job("Escribiendo la película", work, "cine")
    return True


def _cine_build_start():
    folder = cine_last_project()
    if not folder:
        J.reply("No encuentro ninguna película. Primero dime «crea una película sobre…».", "CINE")
        return True
    if cine_state["busy"]:
        J.reply("Ya estoy trabajando en la película; te aviso al terminar.", "CINE")
        return True
    clips = [p for p in glob.glob(os.path.join(folder, "clips", "*")) if p.lower().endswith(cine.CLIP_EXT)]
    if not clips:
        J._open_doc(os.path.join(folder, "clips"))
        J.reply("La carpeta «clips» de la película está vacía. Te la abrí: descarga ahí los videos de Flow o Vibes con su "
                "número (escena 1, escena 2…) y vuelve a decirme «arma la película».", "CINE")
        return True
    if not animar.ffmpeg_exe():
        J.reply("Me falta el componente de video. Actualiza Jarvis o ejecuta instalar.bat (instala imageio-ffmpeg).", "CINE")
        return True
    cine_state.update(busy=True, pct=0, titulo=os.path.basename(folder))
    J.reply(f"Armo la película con {len(clips)} clip(s): les pongo mi narración, subtítulos y música si dejaste una. Te aviso.", "CINE")

    def prog(p, _stage):
        cine_state["pct"] = int(p * 100)

    def work():
        try:
            r = cine_assemble(folder, prog)
        except Exception as e:
            err = getattr(e, "stderr", b"") or b""
            J.log_terminal(f"Película: {e} {err[-300:] if isinstance(err, bytes) else ''}", "CINE")
            J.notify(f"No pude armar la película: {str(getattr(e, 'why', e))[:160]}", "CINE")
            return
        finally:
            cine_state["busy"] = False
        J.generated_files.add(r["mp4"])
        J._open_doc(r["mp4"])
        mins, secs = divmod(int(r["segundos"]), 60)
        extra = ""
        if r["clips"] < r["escenas"]:
            extra = f" Ojo: el guion tiene {r['escenas']} escenas y solo encontré {r['clips']} clips."
        J.notify(f"Lista la película «{r['titulo']}»: {mins} min {secs:02d} s con {r['clips']} escenas"
                 + (", narrada con mi voz" if r["voz"] else "") + (" y música" if r["musica"] else "")
                 + ", con subtítulos. Quedó en la carpeta del proyecto, en Documentos, Jarvis, Cine." + extra, "CINE")
    J.start_job("Armando la película", work, "cine-montaje")
    return True


__all__ = ["cine_state", "cine_dir", "cine_last_project", "cine_create", "cine_assemble", "cine_voice", "_cine_build_start",
           "_CINE_NEW", "_CINE_BUILD", "_CINE_OPEN", "_CINE_GRADES", "_cine_scenes", "_CINE_N", "_music_in"]
