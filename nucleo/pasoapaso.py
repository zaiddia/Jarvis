"""12.0: revisar el procedimiento escrito a mano paso a paso, mapa de errores del curso y refuerzo justo para ese error.

«Jarvis, revisa el procedimiento de Juan» (cámara), «… en la pantalla», o el botón «Revisar procedimiento» de una foto
que subes al chat. «¿Cuál es el mapa de errores de 9A?», «prepara el refuerzo del error más común de 9A».
La lógica está en procedimiento.py. Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import os
import re

import aula
import procedimiento
from nucleo import J

proc_state = {"busy": False, "last": None}


def _proc_vision_json(prompt, path, max_tokens=3000):
    cfg, err = J._vision_cfg()
    if not cfg:
        raise ValueError(err)
    J.thinking += 1
    J.refresh_mode()
    try:
        if cfg["kind"] == "ollama":
            r = J.ollama.Client(host=cfg["ollama_host"], timeout=300).chat(
                model=J.settings["vision_model"].strip() or "moondream", format="json", options={"num_predict": 1500},
                messages=[{"role": "user", "content": prompt, "images": [path]}])
            raw = r["message"]["content"]
        else:
            J._need_key(cfg)
            raw = J._with_fallback(cfg, lambda c: J._cloud_chat(c, [{"role": "user", "content": prompt}], json_mode=True, image_path=path,
                                                                max_tokens=max_tokens))
    finally:
        J.thinking -= 1
        J.refresh_mode()
    return J._extract_json(raw)


def analyze_steps(read, grado=""):
    """De la transcripción a la revisión: SymPy paso a paso, la IA explica el primer error. → resultado."""
    res = dict(read)
    res["chequeo"] = procedimiento.check_chain(read["pasos"], read["problema"])
    err = procedimiento.first_error(res["chequeo"])
    res["error"] = None
    if err:
        try:
            d = J._extract_json(J.ai_chat([{"role": "user", "content": procedimiento.explain_prompt(read["problema"], err["de"], err["a"],
                                                                                                    err["paso"], grado)}],
                                          json_mode=True, max_tokens=600))
        except Exception:
            d = {}
        res["error"] = procedimiento.clean_explain(d, err["de"], err["a"], err["paso"])
    res["respuesta_ok"], res["correcta"] = procedimiento.final_check(read["problema"], read["respuesta"], read["pasos"])
    return res


def review_procedure(path, estudiante="", curso="", que=""):
    """Lee la foto, revisa cada paso y lo anota en el mapa de errores. → (resultado, ruta del Word o "")."""
    g = aula.grade_of(curso) if curso else None
    grado = f"{g}°" if g else ""
    read = procedimiento.clean_read(J._proc_vision_json(procedimiento.read_prompt(que, grado, estudiante), path))
    if not read["legible"]:
        return dict(read, chequeo=[], error=None, respuesta_ok=None), ""
    res = analyze_steps(read, grado)
    procedimiento.record(curso, estudiante, res, tema=que or read["problema"][:80])
    doc = ""
    if J.Document is not None:
        doc = procedimiento.docx(res, path, J.settings["output_dir"], J.Document, estudiante, curso.replace(" · ", " – "),
                                 J.settings["aula_docente"])
        J.generated_files.add(doc)
    proc_state["last"] = {"res": res, "curso": curso, "estudiante": estudiante}
    return res, doc


def start_procedure(source="actual", estudiante="", curso="", que="", voice=False):
    if proc_state["busy"]:
        J.reply("Ya estoy revisando un procedimiento; espera un momento.", "PROCEDIMIENTO")
        return
    if J.state.get("ai") != "ok":
        J.reply("Para leer el procedimiento necesito la IA con visión conectada.", "PROCEDIMIENTO")
        return
    proc_state["busy"] = True
    curso = curso or aula.data.get("activo", "")

    def work():
        try:
            if source == "camara":
                if voice:
                    J.reply("Pon la hoja frente a la cámara, con buena luz. Tomo la foto en 3 segundos.", "PROCEDIMIENTO")
                J._set_review_image(J.capture_camera(wait=3.5 if voice else 0), "camara")
            elif source == "pantalla":
                J._set_review_image(J.capture_screen_for_review(), "pantalla")
            path = J.review_state["path"]
            if not path or not os.path.exists(path):
                raise ValueError("Primero toma una foto, captura la pantalla o sube una imagen al chat.")
            res, doc = review_procedure(path, estudiante, curso, que)
            J.notify(procedimiento.spoken(res, estudiante) + (" El detalle paso a paso está en el Word." if doc else ""), "PROCEDIMIENTO")
            if doc:
                J._open_doc(doc)
        except J.AIError as e:
            J.notify(J.ai_error_reply(e), "PROCEDIMIENTO")
        except ValueError as e:
            J.notify(str(e), "PROCEDIMIENTO")
        finally:
            proc_state["busy"] = False
    if getattr(J._tl, "capture", None) is not None:
        work()
    else:
        J.start_job("Revisando el procedimiento", work, "procedimiento")


def review_folder(folder, curso=""):
    """Revisa todas las fotos de una carpeta (el nombre del archivo es el del estudiante). → [(nombre, resultado)]."""
    out = []
    for f in sorted(os.listdir(folder)):
        if not f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            continue
        name = re.sub(r"[_-]+", " ", os.path.splitext(f)[0]).strip().title()
        try:
            res, _doc = review_procedure(os.path.join(folder, f), name, curso)
            out.append((name, res))
        except Exception as e:
            out.append((name, {"legible": False, "fallo": str(e)}))
    return out


_PR_RE = re.compile(r"\b(?:revisa|revisame|corrige|corrigeme|mira|chequea|verifica)\s+(?:el|los|este|ese)?\s*"
                    r"(?:procedimientos?|desarrollos?|paso a paso)(?:\s+(?:de|del estudiante|de la estudiante)\s+(.+?))?"
                    r"(?:\s+(?:en|con|por)\s+(?:la\s+)?(pantalla|camara|foto|imagen))?$")
_MAP_RE = re.compile(r"\b(?:mapa de errores|en que se equivocan|que errores (?:tienen|cometen)|errores (?:mas )?comunes)\b"
                     r"(?:\s+(?:de|en|del curso)\s+(.+))?")
_REF_RE = re.compile(r"\b(?:prepara|preparame|haz|hazme|arma|genera)\s+(?:el\s+|un\s+)?(?:refuerzo|taller de refuerzo)\s+"
                     r"(?:del|para el|sobre el|de)\s+(?:error|errores)(?:\s+mas comun(?:es)?)?(?:\s+(?:de|en)\s+(.+))?$")


def _proc_course(s):
    s = (s or "").strip()
    return (J._resolve_course(s) or "") if s else (aula.data.get("activo") or "")


def procedure_voice(text, t):
    m = _PR_RE.search(t)
    if m:
        quien, medio = (m.group(1) or "").strip(), m.group(2) or ""
        estudiante, curso = "", aula.data.get("activo", "")
        if quien and quien not in ("este", "esta", "esto", "aqui"):
            try:
                c, names = aula.active()
                estudiante, _ = aula.find_student(quien, names)
                curso = c or curso
            except ValueError:
                pass
            estudiante = estudiante or quien.title()
        recent_img = J.review_state.get("path") and medio in ("foto", "imagen")
        source = "pantalla" if medio == "pantalla" else "actual" if recent_img else "camara"
        try:
            import adjuntos
            last = adjuntos.recent(600)
            if medio in ("", "foto", "imagen") and last and last[-1]["tipo"] == "imagen":
                J._set_review_image(last[-1]["ruta"], "imagen")          # la foto que acabas de subir al chat
                source = "actual"
        except Exception:
            pass
        start_procedure(source, estudiante, curso, voice=True)
        return True
    m = _MAP_RE.search(t)
    if m and ("mapa" in t or (m.group(1) and J._resolve_course(m.group(1).strip()))):
        curso = _proc_course(m.group(1))
        if not curso:
            J.reply("¿De qué curso? Por ejemplo: «mapa de errores de 9A».", "PROCEDIMIENTO")
            return True
        mp = procedimiento.error_map(curso)
        J.socketio.emit("error_map", {"curso": curso, **mp})
        J.reply(procedimiento.spoken_map(curso, mp), "PROCEDIMIENTO")
        return True
    m = _REF_RE.search(t)
    if m:
        curso = _proc_course(m.group(1))
        mp = procedimiento.error_map(curso) if curso else {"categorias": []}
        if not mp["categorias"]:
            J.reply(f"No tengo errores anotados de {curso or 'ese curso'} todavía. Primero revisa algunos procedimientos.", "PROCEDIMIENTO")
            return True
        cat, n, names = mp["categorias"][0]
        temas = sorted({e["tema"] for e in procedimiento.data["cursos"].get(curso, []) if e["categoria"] == cat and e["tema"]})[:3]
        pedido = (f"taller de refuerzo para estudiantes que {procedimiento.CATEGORIAS[cat]}"
                  + (f" (ejercicios como: {'; '.join(temas)})" if temas else "")
                  + ". Empieza con un ejemplo resuelto que muestre el error típico y cómo evitarlo, luego ejercicios graduados"
                    " de menos a más difícil, y al final uno para que expliquen con sus palabras por qué se hace así.")
        J.reply(f"Lo más común en {curso} es {procedimiento.CORTO[cat]} ({n} estudiante{'s' if n != 1 else ''}: "
                f"{', '.join(names[:6])}{'…' if len(names) > 6 else ''}). Preparo el taller de refuerzo justo para eso.", "PROCEDIMIENTO")
        g = aula.grade_of(curso)
        J.generate_material(pedido, kind="taller", grade=f"{g}° (curso {curso})" if g else "", topic=procedimiento.CORTO[cat])
        return True
    return False


def procedure_start():
    procedimiento.configure(J.CONFIG_DIR)


__all__ = ['_MAP_RE', '_PR_RE', '_REF_RE', '_proc_course', '_proc_vision_json', 'analyze_steps', 'proc_state', 'procedimiento', 'procedure_start',
           'procedure_voice', 'review_folder', 'review_procedure', 'start_procedure']
