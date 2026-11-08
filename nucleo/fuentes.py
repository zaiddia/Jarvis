"""11.5: quiz desde un video de YouTube (con el minuto de cada respuesta y la guía de pausas) y el libro guía del curso
(el PDF que subes en Ajustes, que Jarvis usa como base del material, la planeación y las guías vivas).

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import base64
import re

import aula
import libro
import videos
from nucleo import J


# ============================================================================ QUIZ DESDE YOUTUBE
def video_transcript(vid):
    """(título, segmentos) del video, leyendo sus subtítulos. Lanza ValueError si no se puede."""
    page = J._get_text(f"https://www.youtube.com/watch?v={vid}&hl=es", timeout=20)
    tr = videos.pick_track(videos.caption_tracks(page))
    if not tr:
        raise ValueError("el video no tiene subtítulos que pueda leer")
    raw = J._get_text(tr["url"], timeout=20)
    segs = videos.parse_timedtext(raw)
    if not segs:
        raw = J._get_text(tr["url"] + "&fmt=json3", timeout=20)
        segs = videos.parse_timedtext(raw)
    if not segs:
        raise ValueError("no pude leer los subtítulos del video")
    return videos.title_of(page), segs


def video_quiz(titulo, segs, url="", n=8, curso=""):
    g = aula.grade_of(curso) if curso else None
    raw = J.ai_chat([{"role": "user", "content": videos.quiz_prompt(titulo or "video", videos.as_prompt_text(segs), n, f"{g}°" if g else "",
                                                                     J._subject(curso) if curso else "") + J.lessons_ctx()}],
                    json_mode=True, max_tokens=5000)
    q = videos.clean_quiz(J._extract_json(raw), n)
    path = ""
    if J.Document is not None:
        path = videos.docx(q, url, J.settings["output_dir"], J.Document, J.settings["aula_docente"], curso.replace(" · ", " – "))
        J.generated_files.add(path)
    quiz = {"titulo": q["titulo"], "tema": q["tema"], "instrucciones": "Responde según el video.",
            "preguntas": [{k: p[k] for k in ("enunciado", "opciones", "respuesta", "explicacion")} for p in q["preguntas"]]}
    J.remember_quiz(quiz)                              # «pásalo a Forms», «hojas de respuesta del quiz», Kahoot…
    try:
        J.banco.add_quiz(quiz)
    except Exception:
        pass
    return q, path


_YT_RE = re.compile(r"\b(?:quiz|preguntas|evaluacion|cuestionario|taller|guia)\b")
_YT_PASTE = re.compile(r"^(?:jarvis\s+)?(?:haz(?:me)?\s+(?:un\s+)?)?quiz del video\s*:", re.I)


def video_voice(text, t):
    vid = videos.video_id(text)
    pasted = _YT_PASTE.match(text.strip())
    if not (vid and _YT_RE.search(t)) and not pasted:
        return False
    if J.state.get("ai") != "ok":
        J.reply("Para el quiz del video necesito la IA conectada.", "VIDEO")
        return True
    nm = re.search(r"\b(\d{1,2})\s+preguntas\b", t)
    n = max(3, min(20, int(nm.group(1)))) if nm else 8
    curso = aula.data.get("activo", "")
    url = f"https://www.youtube.com/watch?v={vid}" if vid else ""
    J.reply("Leo el video y armo el quiz…", "VIDEO")

    def work():
        try:
            if pasted:
                segs, titulo = videos.parse_pasted(text.split(":", 1)[1]), "Quiz del video"
                if not segs:
                    raise ValueError("no encontré la transcripción en lo que pegaste")
            else:
                titulo, segs = J.video_transcript(vid)
        except Exception as e:
            J.notify(f"No pude leer el video ({getattr(e, 'why', e)}). En YouTube abre «…más» › «Mostrar transcripción», cópiala y dime "
                     "«quiz del video:» y pégala.", "VIDEO")
            return
        try:
            q, path = J.video_quiz(titulo, segs, url, n, curso)
        except Exception as e:
            J.notify(f"No pude armar el quiz del video: {getattr(e, 'why', e)}", "VIDEO")
            return
        if path:
            J._open_doc(path)
        J.notify(f"Listo «{q['titulo']}»: {len(q['preguntas'])} preguntas con el minuto del video donde está cada respuesta" +
                 (f" y {len(q['pausas'])} pausas para verlo en clase" if q["pausas"] else "") + ". Si quieres: «pásalo a Forms», «a Kahoot» o "
                 "«prepara las hojas de respuesta del quiz para …».", "VIDEO")
    if getattr(J._tl, "capture", None) is not None:
        work()
    else:
        J.start_job("Leyendo el video", work, "video")
    return True


# ============================================================================ LIBRO GUÍA
def book_ctx(query, curso=""):
    if not libro.index["libros"] or not query:
        return ""
    try:
        return libro.context(query, J._subject(curso) if curso else "")
    except Exception:
        return ""


@J.socketio.on("books")
def handle_books(data=None):
    d = data or {}
    if d.get("delete"):
        libro.remove(str(d["delete"]))
    if d.get("upload"):
        try:
            m = re.match(r"data:[^;]*;base64,(.+)$", str(d["upload"]), re.S)
            raw = base64.b64decode(m.group(1) if m else str(d["upload"]))
            pages = libro.extract(raw, str(d.get("filename") or "libro.pdf"))
            bid = libro.add_book(str(d.get("nombre") or d.get("filename") or "Libro guía").rsplit(".", 1)[0], str(d.get("asignatura") or ""), pages,
                                 str(d.get("filename") or ""))
            return {"ok": True, "msg": f"Listo: «{libro.index['libros'][bid]['nombre']}», {len(pages)} páginas.", **_books_list()}
        except ValueError as e:
            return {"ok": False, "msg": str(e), **_books_list()}
    return {"ok": True, **_books_list()}


def _books_list():
    return {"libros": [{"id": k, **v} for k, v in libro.index["libros"].items()], "asignaturas": J.subject_choices()}


_BK_LIST = re.compile(r"\bque libros? guia tengo\b|\bmis libros guia\b")
_BK_ASK = re.compile(r"^(?:jarvis\s+)?(?:busca|buscame|que dice|consulta)\s+(?:en\s+)?(?:el\s+)?libro guia\s*(?:sobre|de|:)?\s*(.+)$")


def book_voice(text, t):
    if _BK_LIST.search(t):
        bs = libro.index["libros"]
        J.reply(("Tus libros guía: " + "; ".join(f"«{v['nombre']}» ({v['paginas']} páginas" + (f", {v['asignatura']}" if v["asignatura"] else "") + ")"
                                                 for v in bs.values()) + ". Los uso como base al preparar material.") if bs else
                "No tienes libros guía. Súbelos en Ajustes › Aula y colegio › Libro guía (PDF, Word o texto).", "LIBRO GUÍA")
        return True
    m = _BK_ASK.match(t)
    if not m:
        return False
    if not libro.index["libros"]:
        J.reply("No tienes libros guía. Súbelos en Ajustes › Aula y colegio › Libro guía.", "LIBRO GUÍA")
        return True
    hits = libro.search(m.group(1), "", 3)
    if not hits:
        J.reply("No encontré ese tema en tus libros guía.", "LIBRO GUÍA")
        return True
    if J.state.get("ai") == "ok":
        try:
            ans = J.ai_chat([{"role": "user", "content": "Responde en 2 a 4 frases, citando la página, SOLO con lo que dicen estas páginas del libro guía. "
                              f"Pregunta: «{m.group(1)}».\n" + "\n---\n".join(f"«{h['libro']}», p. {h['pagina']}: {h['texto'][:1800]}" for h in hits)}],
                            max_tokens=400).strip()
            J.reply(ans, "LIBRO GUÍA")
            return True
        except Exception:
            pass
    J.reply("Lo encontré en: " + "; ".join(f"«{h['libro']}», página {h['pagina']}" for h in hits) + ".", "LIBRO GUÍA")
    return True


def sources_start():
    libro.configure(J.CONFIG_DIR)


__all__ = ['_BK_ASK', '_BK_LIST', '_YT_PASTE', '_YT_RE', '_books_list', 'book_ctx', 'book_voice', 'handle_books', 'libro', 'sources_start', 'video_quiz',
           'video_transcript', 'video_voice', 'videos']
