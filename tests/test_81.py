"""Pruebas de la 8.1: Google Forms, retroalimentación de entregas y horario de clases."""
import datetime
import json

import threading
import time

import formularios
import horario
import seguimiento

QUIZ = {"titulo": "Evaluación: fracciones", "tema": "fracciones", "instrucciones": "Marca una.",
        "preguntas": [{"enunciado": "¿1/2 + 1/2?", "opciones": ["1", "2", "1/4", "0"], "respuesta": "a", "explicacion": "Suma."},
                      {"enunciado": "¿Mitad de 8?", "opciones": ["2", "4", "4", "6"], "respuesta": "b", "explicacion": ""}]}


def _wait_approvals():
    for _ in range(100):
        if not any(t.name.startswith("aprobacion") and t.is_alive() for t in threading.enumerate()):
            return
        time.sleep(0.02)


def test_formulario_peticiones():
    reqs = formularios.batch_requests(QUIZ)
    assert reqs[0]["updateSettings"]["settings"]["quizSettings"]["isQuiz"] is True
    assert reqs[0]["updateSettings"]["settings"]["emailCollectionType"] == "VERIFIED"
    items = [r["createItem"]["item"] for r in reqs if "createItem" in r]
    assert len(items) == 2
    q0 = items[0]["questionItem"]["question"]
    assert q0["grading"]["correctAnswers"]["answers"][0]["value"] == "1" and q0["grading"]["whenWrong"]["text"] == "Suma."
    opts = [o["value"] for o in items[1]["questionItem"]["question"]["choiceQuestion"]["options"]]
    assert len(set(o.lower() for o in opts)) == 4                       # sin opciones repetidas
    assert items[1]["questionItem"]["question"]["grading"]["correctAnswers"]["answers"][0]["value"] == "4"


def test_notas_de_forms():
    resp = [{"respondentEmail": "Juan@colegio.edu.co", "totalScore": 1, "lastSubmittedTime": "2026-10-01T10:00:00Z"},
            {"respondentEmail": "juan@colegio.edu.co", "totalScore": 2, "lastSubmittedTime": "2026-10-01T11:00:00Z"},
            {"respondentEmail": "ana@colegio.edu.co", "lastSubmittedTime": "2026-10-01T10:00:00Z"}]
    s = formularios.scores(resp, 2)
    assert s == {"juan@colegio.edu.co": 5.0, "ana@colegio.edu.co": 1.0}
    named, unknown = formularios.match_names(s, {"juan@colegio.edu.co": "Juan Pérez"})
    assert named == {"Juan Pérez": 5.0} and unknown == ["ana@colegio.edu.co"]


class FakeClient:
    def __init__(self):
        self.forms, self.updates, self.announced = [], [], []

    def form_create(self, body):
        self.forms.append(body)
        return {"formId": "F1", "responderUri": "https://forms.gle/x"}

    def form_update(self, fid, reqs):
        self.updates.append(reqs)

    def form_responses(self, fid):
        return [{"respondentEmail": "juan@c.co", "totalScore": 2}]

    def roster_emails(self, cid):
        return {"juan@c.co": "Juan Pérez"}

    def coursework(self, cid):
        return [{"id": "W1", "title": "Taller de fracciones", "workType": "SHORT_ANSWER_QUESTION", "description": "Explica 1/2"}]

    def students(self, cid):
        return {"u1": "Juan Pérez", "u2": "Ana Gómez"}

    def submissions(self, cid, wid):
        return [{"userId": "u1", "state": "TURNED_IN", "shortAnswerSubmission": {"answer": "Es la mitad"}},
                {"userId": "u2", "state": "CREATED"}]

    def announce(self, cid, text):
        self.announced.append(text)


def _setup(jv, monkeypatch, tmp_path):
    c = FakeClient()
    monkeypatch.setattr(jv, "classroom_client", lambda: c)
    monkeypatch.setattr(jv, "classroom_courses", lambda force=False: [{"id": "C7", "name": "7A", "section": ""}])
    monkeypatch.setattr(jv, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(jv, "_open_link", lambda url: None)
    monkeypatch.setattr(jv, "_open_doc", lambda p: False)
    said = []
    monkeypatch.setattr(jv, "notify", lambda text, origin="JARVIS": said.append(text))
    monkeypatch.setattr(seguimiento, "_path", str(tmp_path / "notas.json"))
    monkeypatch.setattr(seguimiento, "data", {})
    return c, said


def test_quiz_a_forms_y_notas(jv, monkeypatch, tmp_path):
    c, said = _setup(jv, monkeypatch, tmp_path)
    jv.remember_quiz(QUIZ)
    jv._tl.capture = []
    try:
        jv.process_command("pasa el quiz a Google Forms para 7A")
    finally:
        jv._tl.capture = None
    assert c.forms[0]["info"]["title"] == "Evaluación: fracciones" and len(c.updates) == 1
    assert "Google Forms" in said[-1]
    saved = json.loads((tmp_path / "formularios.json").read_text(encoding="utf-8"))
    assert saved[0]["id"] == "F1" and saved[0]["curso"] == "7A" and saved[0]["n"] == 2
    assert jv.aprobaciones.latest()["titulo"].startswith("Publicar el formulario")
    jv.process_command("sí")
    _wait_approvals()
    assert c.announced and "forms.gle" in c.announced[0]
    jv._rec.clear()
    jv.process_command("trae las notas del formulario de fracciones de 7A")
    assert "Traje 1 nota" in jv._rec.said()
    assert seguimiento.average("7A", "Juan Pérez") == 5.0


def test_retroalimentacion(jv, monkeypatch, tmp_path):
    c, said = _setup(jv, monkeypatch, tmp_path)
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: json.dumps({"revision": [{"id": 0, "nota": "4,2", "comentario": "Bien, explica más."}]}))
    jv._tl.capture = []
    try:
        jv.process_command("revisa las respuestas del taller de fracciones en Classroom de 7A")
    finally:
        jv._tl.capture = None
    a = jv.aprobaciones.latest()
    assert "Taller de fracciones" in a["titulo"] and "Juan Pérez: 4,2" in a["detalle"]
    jv.process_command("sí")
    _wait_approvals()
    assert seguimiento.average("7A", "Juan Pérez") == 4.2
    if jv.Document is not None:
        assert list((tmp_path / "Retroalimentación").iterdir())


def test_retroalimentacion_valida():
    assert jv_valid({"revision": [{"id": 0, "nota": 9}, {"id": 1, "nota": "3,5", "comentario": "ok"}, {"id": 7, "nota": 3}]}) == \
        {1: {"nota": 3.5, "comentario": "ok"}}


def jv_valid(d):
    from nucleo import aulaconecta
    return aulaconecta.feedback_validate(d, 2)


# ----------------------------------------------------------------------------- horario
def test_horario(tmp_path, monkeypatch):
    monkeypatch.setattr(horario, "_path", str(tmp_path / "horario.json"))
    items, bad = horario.parse_text("lunes 7:00-7:55 7A Matemáticas\nlunes 8:00-8:55 9B Física\n# nota\nmartes cualquier cosa")
    assert len(items) == 2 and bad == ["martes cualquier cosa"]
    horario.set_all(items)
    mon = datetime.datetime(2026, 11, 2, 7, 30)                       # lunes
    assert horario.now_class(mon)["curso"] == "7A"
    nx, day = horario.next_class(mon)
    assert nx["curso"] == "9B" and day == mon.date()
    nx, day = horario.next_class(datetime.datetime(2026, 11, 2, 10, 0))
    assert day == datetime.date(2026, 11, 9)                           # el lunes siguiente
    assert "2 clases" in horario.spoken_day(horario.today(mon))
    assert horario.parse_text(horario.to_text())[0] == items


def test_horario_por_voz(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(horario, "_path", str(tmp_path / "horario.json"))
    monkeypatch.setattr(horario, "items", [])
    rec = jv._rec
    rec.clear()
    jv.process_command("los martes de 1 a 2 tengo 9B física")
    assert "martes de 13:00 a 14:00, 9B física" in rec.said()
    rec.clear()
    jv.process_command("¿cuál es mi próxima clase?")
    assert "9B física" in rec.said()
    made = []
    monkeypatch.setattr(jv, "generate_material", lambda req, kind=None, count=None, grade="", topic="": made.append((kind, grade, topic)))
    jv.process_command("prepárame la próxima clase de leyes de Newton")
    assert made == [("plan", "9B", "leyes de newton")]


def test_aviso_antes_de_clase(jv, monkeypatch):
    monkeypatch.setattr(horario, "items", [{"dia": 0, "inicio": "07:00", "fin": "07:55", "curso": "7A", "materia": "Mate"}])
    monkeypatch.setitem(jv.settings, "schedule_warn", True)
    monkeypatch.setitem(jv.settings, "schedule_auto_course", False)
    alerts = []
    monkeypatch.setattr(jv, "alert", lambda text, origin="JARVIS": alerts.append(text))
    jv._sched_state["warned"] = ""
    assert jv.schedule_tick(datetime.datetime(2026, 11, 2, 6, 50)) is None      # faltan 10 min
    assert jv.schedule_tick(datetime.datetime(2026, 11, 2, 6, 56))
    assert jv.schedule_tick(datetime.datetime(2026, 11, 2, 6, 57)) is None      # una sola vez
    assert alerts == ["En 5 minutos: 7A Mate."]
