"""12.0: ensaya la clase con estudiantes simulados.

«Jarvis, ensaya la clase de factorización con 9A»: Jarvis arma 4 o 5 estudiantes con los errores típicos de ese curso
(del mapa de errores y de las notas, sin nombres reales). Hablas o escribes como si estuvieras en el salón y ellos te
responden con su voz, se equivocan como lo harían y preguntan. «Termina el ensayo»: el informe con las confusiones que
van a aparecer y cómo anticiparlas, en Word. La lógica está en ensayo.py.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import re
import time

import aula
import ensayo
import procedimiento
import seguimiento
from nucleo import J

rehearsal = {"on": False, "tema": "", "curso": "", "grado": "", "personas": [], "historial": [], "notas": [], "last": 0.0, "busy": False}
TIMEOUT = 30 * 60


def start_rehearsal(tema, curso=""):
    g = aula.grade_of(curso) if curso else None
    mp = procedimiento.error_map(curso) if curso else {"categorias": []}
    errs = [(c, procedimiento.CATEGORIAS.get(c, c), n) for c, n, _ in mp["categorias"]]
    proms = [seguimiento.average(curso, n) for n in seguimiento.data.get(curso, {})] if curso else []
    ps = ensayo.personas(errs, proms)
    rehearsal.update(on=True, tema=tema, curso=curso, grado=f"{g}°" if g else "", personas=ps, historial=[], notas=[], last=time.time(), busy=False)
    J.socketio.emit("rehearsal", {"on": True, "tema": tema, "personas": [{k: p[k] for k in ("nombre", "perfil", "error")} for p in ps]})
    return ps


def _say_students(turns):
    for it in turns:
        p = next((p for p in rehearsal["personas"] if p["nombre"] == it["quien"]), None)
        rehearsal["historial"].append({"quien": it["quien"], "dice": it["dice"]})
        J.push_chat("jarvis", f"🧑‍🎓 {it['quien']}: {it['dice']}", "ENSAYO")
        J.log_terminal(f"{it['quien']}: {it['dice']}", "ENSAYO")
        J.speak(it["dice"], voice=p["voz"] if p else None, backend="edge", pitch=8)
    J.socketio.emit("rehearsal_turn", {"turns": turns})


def teacher_says(text):
    """Lo que dice el docente → lo que responden los estudiantes simulados."""
    rehearsal["last"] = time.time()
    rehearsal["historial"].append({"quien": "Docente", "dice": text})
    msgs = [{"role": "system", "content": ensayo.system_prompt(rehearsal["tema"], rehearsal["grado"], rehearsal["personas"])}]
    for h in rehearsal["historial"][-18:]:
        msgs.append({"role": "user" if h["quien"] == "Docente" else "assistant", "content": f"{h['quien']}: {h['dice']}"})
    raw = J.ai_chat(msgs, json_mode=True, max_tokens=700)
    turns, nota = ensayo.clean_turn(J._extract_json(raw), rehearsal["personas"])
    if nota:
        rehearsal["notas"].append(nota)
    _say_students(turns)
    return turns


def end_rehearsal():
    """Cierra el ensayo y hace el informe. → (informe, ruta del Word o "")."""
    rehearsal["on"] = False
    J.socketio.emit("rehearsal", {"on": False})
    if len(rehearsal["historial"]) < 2:
        return None, ""
    raw = J.ai_chat([{"role": "user", "content": ensayo.report_prompt(rehearsal["tema"], rehearsal["grado"], rehearsal["personas"],
                                                                       rehearsal["historial"], rehearsal["notas"])}],
                    json_mode=True, max_tokens=1800)
    r = ensayo.clean_report(J._extract_json(raw))
    path = ""
    if J.Document is not None:
        path = ensayo.docx(rehearsal["tema"], rehearsal["curso"], r, rehearsal["historial"], J.settings["output_dir"], J.Document)
        J.generated_files.add(path)
    return r, path


_EN_START = re.compile(r"\b(?:ensaya|ensayemos|ensayar|practica|practiquemos|simula|simulemos)\s+(?:conmigo\s+)?(?:la|mi|una)?\s*clase\s+(?:de|sobre)\s+(.+?)"
                       r"(?:\s+(?:con|para|de|en)\s+((?:grado\s+)?(?:\d{1,2}\s?[a-z]?|sexto|septimo|octavo|noveno|decimo|undecimo|once)\b.*))?$|"
                       r"\bquiero ensayar (?:la|mi) clase\s+(?:de|sobre)\s+(.+?)(?:\s+(?:con|para)\s+(.+))?$")
_EN_END = re.compile(r"^(?:jarvis\s+)?(?:termina|terminar|fin del|acaba|cierra|para|deten)\s*(?:el\s+)?ensayo\b|\bya termine (?:el|la) (?:ensayo|clase)\b|"
                     r"^(?:como me fue en el ensayo)$")
_EN_PAUSE = re.compile(r"^(?:jarvis\s+)?(?:sal|salir|cancela)\s+del?\s+ensayo$")


def rehearsal_capture(text, t):
    """Mientras el ensayo está abierto, lo que dices va para los estudiantes simulados. True si lo atendió."""
    if not rehearsal["on"]:
        return False
    if time.time() - rehearsal["last"] > TIMEOUT:
        rehearsal["on"] = False
        return False
    if _EN_PAUSE.match(t):
        rehearsal["on"] = False
        J.socketio.emit("rehearsal", {"on": False})
        J.reply("Salí del ensayo sin informe.", "ENSAYO")
        return True
    if _EN_END.search(t):
        J.reply("Fin del ensayo. Preparo el informe…", "ENSAYO")

        def work():
            try:
                r, path = end_rehearsal()
            except J.AIError as e:
                J.notify(J.ai_error_reply(e), "ENSAYO")
                return
            if not r:
                J.notify("El ensayo fue muy corto para un informe.", "ENSAYO")
                return
            if path:
                J._open_doc(path)
            J.notify(ensayo.spoken_report(r) + (" El informe completo está en Documentos, Jarvis, Ensayos de clase." if path else ""), "ENSAYO")
        if getattr(J._tl, "capture", None) is None:
            J.start_job("Informe del ensayo", work, "ensayo")
        else:
            work()
        return True
    if rehearsal["busy"]:
        return True
    rehearsal["busy"] = True
    try:
        teacher_says(text.strip())
    except J.AIError as e:
        J.reply(J.ai_error_reply(e), "ENSAYO")
    except Exception as e:
        J.log_terminal(f"Ensayo: {e}", "ERROR")
        J.reply("Los estudiantes se quedaron callados (algo falló). Dilo otra vez.", "ENSAYO")
    finally:
        rehearsal["busy"] = False
    return True


def rehearsal_voice(text, t):
    m = _EN_START.search(t)
    if not m:
        return False
    tema = (m.group(1) or m.group(3) or "").strip()
    spoken = (m.group(2) or m.group(4) or "").strip()
    curso = (J._resolve_course(spoken) if spoken else "") or aula.data.get("activo", "")
    if J.state.get("ai") != "ok":
        J.reply("Para simular a los estudiantes necesito la IA conectada.", "ENSAYO")
        return True
    ps = start_rehearsal(tema, curso)
    J.reply(f"Empieza el ensayo de «{tema}»" + (f" con un {curso} simulado" if curso else "") + ". Tus estudiantes: " +
            ", ".join(p["nombre"] + (f" ({procedimiento._sing(p['error'])})" if p["error"] else "") for p in ps) +
            ". Habla o escribe como si estuvieras en el salón. Cuando acabes: «termina el ensayo».", "ENSAYO")
    return True


__all__ = ['TIMEOUT', '_EN_END', '_EN_PAUSE', '_EN_START', '_say_students', 'end_rehearsal', 'ensayo', 'rehearsal', 'rehearsal_capture',
           'rehearsal_voice', 'start_rehearsal', 'teacher_says']
