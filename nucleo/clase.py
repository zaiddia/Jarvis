"""Aula (cursos, sorteos, grupos, asistencia, material) y revisión de trabajos.

Parte de Jarvis (antes dentro de jarvis.py). Los nombres globales de Jarvis se usan como J.<nombre>.
"""
from flask import request
import aula
import os
import perfil
import re
import revision
import tempfile
import threading
import time
import uuid
import webbrowser

from nucleo import J


# =============================================================================
# AULA: cursos, sorteo, grupos, asistencia, semáforo de ruido y material de clase
#   La lógica está en aula.py; aquí se conecta con la voz, el tablero y la IA.
# =============================================================================
aula.configure(J.CONFIG_DIR)
perfil.configure(J.CONFIG_DIR)
aula_ui = {"last": None, "view": "ruleta", "attendance_until": 0.0}
material_job = {"busy": False}
generated_files = set()                     # solo estos archivos se pueden abrir desde el tablero


def aula_emit(event):
    """Envía algo al tablero y lo recuerda (si el tablero se abre después, lo muestra)."""
    if event.get("type") in ("pick", "groups"):
        J.aula_ui["last"] = event
    if event.get("view"):
        J.aula_ui["view"] = event["view"]
    J.socketio.emit("aula", event)


def open_aula_window(view=None):
    if view:
        J.aula_ui["view"] = view
        J.socketio.emit("aula", {"type": "view", "view": view})
    if J.webview is None or J.hud["window"] is None:
        if not J.hud.get("aula_browser"):
            J.hud["aula_browser"] = True
            webbrowser.open(f"{J.URL}/aula")
        return
    w = J.hud.get("aula_win")
    if w is not None:
        try:
            w.show()
            w.restore()
            return
        except Exception:
            J.hud["aula_win"] = None
    w = J.webview.create_window("Aula · Jarvis", f"{J.URL}/aula", width=1120, height=720,
                              min_size=(640, 420), background_color="#03060c")

    def _closed():
        J.hud["aula_win"] = None
    w.events.closed += _closed
    J.hud["aula_win"] = w


def _maybe_open_board(view):
    if J.settings["aula_auto_open"]:
        J.open_aula_window(view)
    else:
        J.aula_emit({"type": "view", "view": view})


def aula_pick():
    name, quedan, total = aula.pick()
    J.aula_emit({"type": "pick", "name": name, "quedan": quedan, "total": total,
               "curso": aula.data["activo"], "view": "ruleta"})
    J._maybe_open_board("ruleta")
    J.reply(f"Le toca a {name}.", "AULA")


def aula_groups(size=None, count=None):
    cur, groups = aula.make_groups(size=size, count=count)
    J.aula_emit({"type": "groups", "groups": groups, "curso": cur, "view": "grupos"})
    J._maybe_open_board("grupos")
    tam = sorted({len(g) for g in groups})
    J.reply(f"Listo: {len(groups)} grupos de {' y '.join(map(str, tam))} en {cur}. Los muestro en el tablero.", "AULA")


def aula_start_attendance():
    cur, names = aula.active()
    J.aula_ui["attendance_until"] = time.time() + 3 * 3600
    J.open_aula_window("asistencia")
    J.reply(f"Abro la lista de {cur}, con {len(names)} estudiantes. Toca en el tablero a quien falte, "
          "o dime por ejemplo «falta Juan». Al terminar di «guarda la asistencia».", "AULA")


def aula_mark_voice(spoken, present):
    cur, names = aula.active()
    done, unknown = [], []
    for part in re.split(r"\s*,\s*|\s+y\s+", spoken):
        if not part.strip():
            continue
        name, cands = aula.find_student(part, names)
        if name:
            aula.mark(name, present)
            done.append(name)
        elif len(cands) > 1:
            J.reply(f"Hay varios: {', '.join(cands[:4])}. Dime el nombre completo.", "AULA")
            return
        else:
            unknown.append(part)
    J.aula_emit({"type": "attendance", **aula.snapshot()})
    if done:
        J.reply(f"{', '.join(done)}: {'presente' if present else 'ausente'}.", "AULA")
    if unknown:
        J.reply(f"No encontré a {', '.join(unknown)} en {cur}.", "AULA")


def aula_export_attendance():
    path, pres, tot = aula.export_attendance(J.settings["output_dir"])
    J.generated_files.add(path)
    J.aula_emit({"type": "exported", "path": path, "name": os.path.basename(path)})
    J.aula_ui["attendance_until"] = 0.0
    J.reply(f"Asistencia guardada: {pres} de {tot} presentes. El archivo está en la carpeta Asistencia.", "AULA")


def generate_material(request, kind=None, count=None, grade="", topic=""):
    """Genera quiz, taller, rúbrica o plan de clase con la IA y lo guarda en Word."""
    if J.Document is None:
        J.reply("No puedo crear documentos: falta instalar python-docx.", "ERROR")
        return
    kind = kind if kind in aula.KINDS else (aula.detect_kind(request) or "taller")
    label = aula.KINDS[kind][0]
    lo = {"quiz": "la evaluación", "taller": "el taller", "rubrica": "la rúbrica",
          "plan": "el plan de clase"}[kind]
    if J.material_job["busy"]:
        J.reply("Ya estoy preparando otro material. Te aviso cuando termine y luego hago este.", "AULA")
        return
    J.material_job["busy"] = True
    J.reply(f"Preparando {lo}. Te aviso cuando esté listo; suele tardar menos de un minuto.", "AULA")
    J.aula_emit({"type": "material", "status": "working", "label": label})

    def work():
        try:
            prompt = aula.build_prompt(kind, request, count or aula.detect_count(request), grade, topic)
            m, last_err = None, None
            for _ in range(2):                         # un reintento si la IA devuelve algo mal formado
                try:
                    raw = J.ai_chat([{"role": "user", "content": prompt}], json_mode=True, max_tokens=8000)
                    m = aula.validate(kind, J._extract_json(raw), request)
                    break
                except (ValueError, TypeError) as e:
                    last_err = e
            if m is None:
                raise ValueError(str(last_err) or "respuesta no válida")
            path = aula.build_docx(kind, m, J.settings["output_dir"], J.Document, J.settings["aula_docente"],
                                   J.settings["aula_institucion"], aula.data["activo"])
            J.generated_files.add(path)
            J.log_terminal(f"Material guardado en: {path}", "AULA")
            J.aula_emit({"type": "material", "status": "done", "label": label, "title": m["titulo"],
                       "path": path, "name": os.path.basename(path)})
            if J.IS_WIN and J.settings["aula_open_docs"]:
                try:
                    os.startfile(path)
                except OSError:
                    pass
            J.reply(f"Listo {lo}: «{m['titulo']}». Lo guardé en la carpeta Material de clase"
                  + (" y lo abrí." if J.IS_WIN and J.settings["aula_open_docs"] else "."), "AULA")
        except J.AIError as e:
            J.aula_emit({"type": "material", "status": "error", "label": label, "error": e.why})
            J.reply(J.ai_error_reply(e), "AULA")
        except Exception as e:
            J.log_terminal(f"Material de clase: {e}", "ERROR")
            J.aula_emit({"type": "material", "status": "error", "label": label, "error": str(e)})
            J.reply(f"No me salió bien {lo}. Inténtalo otra vez, quizá con un tema más concreto.", "AULA")
        finally:
            J.material_job["busy"] = False
    threading.Thread(target=work, daemon=True, name="material").start()


_AULA_VERB = r"\b(?:crea|creame|haz|hazme|prepara|preparame|genera|generame|disena|disename|elabora|elaborame|redacta|arma|armame)\b"
# Si la frase habla de estas cosas, no es una orden del aula («crea un grupo de WhatsApp»...)
_AULA_NOT = re.compile(r"\b(?:calendario|recordatorio|alarma|carpeta|archivo|correo|whatsapp|telegram|"
                       r"spotify|youtube|steam|contacto|chat|playlist|lista de reproduccion)\b")


def aula_voice(text, t):
    """Órdenes de voz del aula. Devuelve True si la frase era para el aula."""
    if J._AULA_NOT.search(t):
        return False
    try:
        # Material de clase: «crea un quiz de 10 preguntas sobre fracciones para séptimo»
        kind = aula.detect_kind(t)
        # palabras genéricas (actividad, tarea, prueba...) exigen decir el tema con «sobre»
        weak = not re.search(r"\b(?:taller|guia|ficha|quiz|evaluacion|examen|cuestionario|rubrica|"
                             r"plan de clase|planeacion|planificacion|secuencia didactica)\b", t)
        marker = r"\b(?:sobre|acerca)\b" if weak else r"\b(?:sobre|de|del|para|acerca)\b"
        if kind and re.search(J._AULA_VERB, t) and re.search(marker, t):
            J.generate_material(text, kind)
            return True
        # Curso activo: «usa el curso 7A», «cambia al grado séptimo A»
        m = re.search(r"\b(?:usa|usar|cambia|cambiar|pasa|selecciona|estoy con|vamos con|trabaja con)\b"
                      r".*?\b(?:curso|grado)\s+(.+)$", t)
        if m and aula.data["cursos"]:
            cur = aula.find_course(m.group(1))
            if not cur:
                lista = ", ".join(aula.data["cursos"]) or "ninguno todavía"
                J.reply(f"No tengo el curso «{m.group(1)}». Tengo: {lista}.", "AULA")
            else:
                aula.set_active(cur)
                J.aula_emit({"type": "course", **aula.snapshot()})
                J.reply(f"Listo, trabajamos con {cur}: {len(aula.data['cursos'][cur])} estudiantes.", "AULA")
            return True
        if re.search(r"\breinici\w* (?:la )?(?:ruleta|sorteo|lista del sorteo)\b", t):
            aula.reset_pick()
            J.reply("Ruleta reiniciada: todos vuelven a participar.", "AULA")
            return True
        # Grupos: «haz grupos de 4», «forma 5 grupos», «haz parejas»
        if (re.search(r"\b(?:haz|hagan|forma|formar|arma|armar|crea|organiza|divide|dividelos|separa|reparte|hazme)\b", t)
                and re.search(r"\b(?:grupos?|equipos?|parejas|trios)\b", t)):
            size = count = None
            ms = re.search(r"\b(?:grupos?|equipos?) de (\w+)", t)
            mc = re.search(r"\b(\w+) (?:grupos|equipos)\b", t)
            if "parejas" in t:
                size = 2
            elif "trios" in t:
                size = 3
            elif ms and aula.to_int(ms.group(1)):
                size = aula.to_int(ms.group(1))
            elif mc and aula.to_int(mc.group(1)):
                count = aula.to_int(mc.group(1))
            J.aula_groups(size=size or (None if count else 4), count=count)
            return True
        # Sorteo: «escoge un estudiante», «¿quién pasa al tablero?», «otro»
        recien = time.time() - J.aula_ui.get("last_pick", 0) < 900       # sorteaste hace poco
        if (re.search(r"\b(?:escoge|escoja|elige|elija|selecciona|saca|sortea)\b.*\b(?:estudiante|alumno|alumna|"
                      r"alguien|persona)\b", t)
                or re.search(r"\bquien (?:pasa|sigue|responde|lee|sale|contesta)\b", t)
                or (recien and re.fullmatch(r"(?:(?:escoge |elige |saca |dame )?(?:a )?(?:otro|otra)(?: mas)?|"
                                            r"el siguiente|la siguiente|siguiente)", t))
                or re.search(r"\b(?:gira|usa) (?:la )?ruleta\b", t)):
            J.aula_ui["last_pick"] = time.time()
            J.aula_pick()
            return True
        # Asistencia
        if re.search(r"\b(?:llama(?:r)? (?:a )?lista|toma(?:r)? (?:la )?asistencia|pasa(?:r)? lista|lista de asistencia)\b", t):
            J.aula_start_attendance()
            return True
        if re.search(r"\b(?:guarda|exporta|termina|cierra)\b.*\basistencia\b", t):
            J.aula_export_attendance()
            return True
        if time.time() < J.aula_ui["attendance_until"]:
            m = re.match(r"^(?:falta|faltan|ausente|no vino|no esta|no llego|no asistio)\s+(.+)$", t)
            if m:
                J.aula_mark_voice(m.group(1), present=False)
                return True
            m = re.match(r"^(?:llego|presente|ya llego|si vino|vino|si esta)\s+(.+)$", t)
            if m:
                J.aula_mark_voice(m.group(1), present=True)
                return True
        # Semáforo de ruido
        if re.search(r"\bsemaforo\b", t):
            if re.search(r"\b(?:desactiva|apaga|quita|cierra|deten|para)\b", t):
                J.aula_emit({"type": "view", "view": "ruleta"})
                J.reply("Semáforo de ruido apagado.", "AULA")
            else:
                J.open_aula_window("semaforo")
                J.reply("Semáforo de ruido en el tablero. Verde está bien, amarillo es un aviso y rojo, silencio.", "AULA")
            return True
        # Tablero
        if re.search(r"\b(?:abre|muestra|pon|abrir)\b.*\b(?:tablero|pizarra)\b|\bmodo aula\b", t):
            J.open_aula_window()
            J.reply("Tablero del aula abierto. Puedes arrastrarlo al videobeam y ponerlo en pantalla completa.", "AULA")
            return True
    except ValueError as e:
        J.reply(str(e), "AULA")
        return True
    return False


# =============================================================================
# REVISIÓN DE TRABAJOS (cámara, pantalla o imagen). La lógica está en revision.py.
# =============================================================================
review_state = {"path": "", "source": "", "busy": False}


def _revision_tmp():
    return os.path.join(tempfile.gettempdir(), f"jarvis_trabajo_{uuid.uuid4().hex}.png")


def _set_review_image(path, source):
    old = J.review_state.get("path")
    if old and old != path and os.path.basename(old).startswith("jarvis_trabajo_"):
        try:
            os.remove(old)
        except OSError:
            pass
    J.review_state.update(path=path, source=source)


def _preview_b64(path, max_w=900):
    import base64
    import io
    from PIL import Image
    img = Image.open(path).convert("RGB")
    if img.width > max_w:
        img = img.resize((max_w, round(img.height * max_w / img.width)))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def capture_camera(wait=0.0):
    """Toma una foto con la cámara del equipo y devuelve la ruta del PNG."""
    try:
        import cv2
    except ImportError:
        raise ValueError("Para usar la cámara falta un componente. Ejecuta instalar.bat otra vez "
                         "(o en la carpeta de Jarvis: .venv\\Scripts\\pip install opencv-python-headless). "
                         "Mientras tanto puedes usar Pantalla o subir una foto.")
    if wait:
        time.sleep(wait)
    idx = J.settings["camera_index"]
    cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW) if J.IS_WIN else cv2.VideoCapture(idx)
    try:
        if not cap.isOpened():
            raise ValueError("No pude abrir la cámara. Revisa que no la esté usando otra aplicación "
                             "(Teams, Zoom…) y que Windows le dé permiso en Configuración › Privacidad › Cámara.")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        frame, t0 = None, time.time()
        while time.time() - t0 < 1.2:              # la cámara necesita un momento para ajustar luz y foco
            ok, f = cap.read()
            if ok:
                frame = f
        if frame is None:
            raise ValueError("La cámara no entregó imagen. Prueba con otra en el tablero (Revisar › Cámara).")
        path = J._revision_tmp()
        cv2.imwrite(path, frame)
        return path
    finally:
        cap.release()


def capture_screen_for_review():
    """Captura la pantalla a buena resolución, ocultando también el tablero del aula."""
    w = J.hud.get("aula_win")
    hid = False
    if w is not None:
        try:
            w.hide()
            hid = True
        except Exception:
            pass
    try:
        path, _ = J._capture_screen(hide_hud=True, max_w=2000)
    finally:
        if hid:
            try:
                w.show()
            except Exception:
                pass
    return path


def load_uploaded_image(data_url):
    import base64
    import io
    from PIL import Image, ImageOps
    m = re.match(r"^data:image/[\w.+-]+;base64,(.+)$", data_url or "", re.S)
    if not m:
        raise ValueError("Ese archivo no es una imagen. Usa una foto (JPG o PNG); si es un PDF, "
                         "ábrelo en pantalla y usa «Pantalla».")
    raw = base64.b64decode(m.group(1))
    if len(raw) > 15 * 1024 * 1024:
        raise ValueError("La imagen es muy grande (máximo 15 MB).")
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")   # fotos del celular, derechas
    if max(img.size) > 2400:
        img.thumbnail((2400, 2400))
    path = J._revision_tmp()
    img.save(path)
    return path


def review_work(path, estudiante="", que="", clave="", grado=""):
    """Revisa el trabajo de la imagen. Devuelve (resultado, ruta del Word o "")."""
    cfg, err = J._vision_cfg()
    if not cfg:
        raise ValueError(err)
    prompt = revision.build_prompt(que, clave, grado, estudiante)
    msgs = [{"role": "user", "content": prompt}]
    J.thinking += 1
    J.refresh_mode()
    try:
        if cfg["kind"] == "ollama":
            vmodel = J.settings["vision_model"].strip() or "moondream"
            r = J.ollama.Client(host=cfg["ollama_host"], timeout=240).chat(
                model=vmodel, format="json", options={"num_predict": 1500},
                messages=[{"role": "user", "content": prompt, "images": [path]}])
            raw = r["message"]["content"]
        else:
            J._need_key(cfg)
            raw = J._with_fallback(cfg, lambda c: J._cloud_chat(c, msgs, json_mode=True, image_path=path,
                                                            max_tokens=4000))
    finally:
        J.thinking -= 1
        J.refresh_mode()
    res = revision.validate(J._extract_json(raw))
    doc = ""
    if res["legible"] and J.Document is not None:
        doc = revision.save_docx(res, path, J.settings["output_dir"], J.Document, estudiante,
                                 aula.data.get("activo", ""), que, J.settings["aula_docente"])
        J.generated_files.add(doc)
    return res, doc


def start_review(source="actual", estudiante="", que="", clave="", grado="", voice=False):
    """Captura (si hace falta) y revisa en segundo plano. El resultado va al tablero y se dice."""
    if J.review_state["busy"]:
        J.reply("Ya estoy revisando un trabajo; espera un momento.", "REVISION")
        return
    J.review_state["busy"] = True

    def work():
        try:
            if source == "camara":
                if voice:
                    J.reply("Pon la hoja frente a la cámara, con buena luz. Tomo la foto en 3 segundos.", "REVISION")
                J._set_review_image(J.capture_camera(wait=3.5 if voice else 0), "camara")
            elif source == "pantalla":
                J._set_review_image(J.capture_screen_for_review(), "pantalla")
            path = J.review_state["path"]
            if not path or not os.path.exists(path):
                raise ValueError("Primero toma una foto, captura la pantalla o sube una imagen.")
            if voice:
                J._maybe_open_board("revisar")
            J.aula_emit({"type": "review", "status": "working", "preview": J._preview_b64(path), "view": "revisar"})
            res, doc = J.review_work(path, estudiante, que, clave, grado)
            J.aula_emit({"type": "review", "status": "done", "result": res, "doc": doc,
                       "docname": os.path.basename(doc) if doc else "", "estudiante": estudiante})
            J.reply(revision.spoken_summary(res, estudiante), "REVISION")
            if res["legible"] and res["retroalimentacion"]:
                J.push_chat("jarvis", "📝 " + res["retroalimentacion"], "REVISION")
        except J.AIError as e:
            J.aula_emit({"type": "review", "status": "error", "error": e.why})
            J.reply(J.ai_error_reply(e), "REVISION")
        except ValueError as e:
            J.aula_emit({"type": "review", "status": "error", "error": str(e)})
            J.reply(str(e), "REVISION")
        except Exception as e:
            J.log_terminal(f"Revisión de trabajo: {e}", "ERROR")
            J.aula_emit({"type": "review", "status": "error", "error": str(e)})
            J.reply("No pude revisar el trabajo. Inténtalo de nuevo.", "REVISION")
        finally:
            J.review_state["busy"] = False
    threading.Thread(target=work, daemon=True, name="revision").start()


_REVIEW_RE = re.compile(
    r"\b(?:revisa|revisame|revisar|corrige|corrigeme|corregir|califica|calificame|calificar|evalua|evaluame)\b"
    r".*?\b(?:trabajo|taller|examen|evaluacion|prueba|quiz|tarea|cuaderno|hoja|ejercicios?|actividad|guia)\b"
    r"(?:\s+(?:de|del estudiante|de la estudiante|del alumno|de la alumna)\s+(.+?))?"
    r"(?:\s+(?:en|con|por)\s+(?:la\s+)?(pantalla|camara|foto|imagen))?$")


def review_voice(text, t):
    """«revisa el taller de Juan», «califica este examen en la pantalla». True si era para esto."""
    m = J._REVIEW_RE.search(t)
    # «revisa mi trabajo» / «lo que estoy haciendo» es la ayuda con tu pantalla, no un trabajo de estudiante
    if not m or re.search(r"\b(?:mi|mis|lo que estoy)\b", t):
        return False
    quien, medio = (m.group(1) or "").strip(), m.group(2) or ""
    estudiante = ""
    if quien and quien not in ("este", "esta", "esto", "aqui"):
        # «el examen de matemáticas de Juan»: el estudiante es lo último tras «de»
        opciones = [quien] + ([quien.rsplit(" de ", 1)[1]] if " de " in quien else [])
        try:
            _, names = aula.active()
            for op in reversed(opciones):
                estudiante, _c = aula.find_student(op, names)
                if estudiante:
                    break
        except ValueError:
            pass
        estudiante = estudiante or opciones[-1].title()
    source = "pantalla" if medio == "pantalla" else "actual" if medio in ("foto", "imagen") else "camara"
    J.start_review(source, estudiante=estudiante, voice=True)
    return True


__all__ = [
    '_AULA_NOT',
    '_AULA_VERB',
    '_REVIEW_RE',
    '_maybe_open_board',
    '_preview_b64',
    '_revision_tmp',
    '_set_review_image',
    'aula_emit',
    'aula_export_attendance',
    'aula_groups',
    'aula_mark_voice',
    'aula_pick',
    'aula_start_attendance',
    'aula_ui',
    'aula_voice',
    'capture_camera',
    'capture_screen_for_review',
    'generate_material',
    'generated_files',
    'load_uploaded_image',
    'material_job',
    'open_aula_window',
    'review_state',
    'review_voice',
    'review_work',
    'start_review',
]
