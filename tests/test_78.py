"""Pruebas de la 7.8: Google Classroom, seguimiento por estudiante, banco de preguntas y memoria editable."""
import datetime
import io
import json
import time
import urllib.parse

import aprobaciones
import banco
import classroom
import perfil
import recuerdos
import seguimiento


# ----------------------------------------------------------------------------- Classroom
class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class FakeGoogle:
    """Hace de Google: token, clases, tareas, estudiantes, entregas y anuncios."""

    def __init__(self):
        self.calls, self.announced = [], []

    def __call__(self, req, timeout=0):
        url, method = req.full_url, req.get_method()
        self.calls.append((method, url))
        if url.startswith(classroom.TOKEN):
            body = urllib.parse.parse_qs(req.data.decode())
            assert body["grant_type"][0] in ("refresh_token", "authorization_code")
            return Resp(json.dumps({"access_token": "AT", "expires_in": 3600, "refresh_token": "RT"}).encode())
        assert req.headers["Authorization"] == "Bearer AT"
        if "/announcements" in url and method == "POST":
            self.announced.append(json.loads(req.data))
            return Resp(b"{}")
        if url.startswith(classroom.API + "courses?"):
            return Resp(json.dumps({"courses": [{"id": "c7", "name": "Matemáticas 7A"}, {"id": "c8", "name": "Matemáticas 8B"}]}).encode())
        if "/courseWork?" in url:
            soon = datetime.date.today() + datetime.timedelta(days=2)
            return Resp(json.dumps({"courseWork": [
                {"id": "w1", "title": "Taller de fracciones", "maxPoints": 100, "dueDate": {"year": soon.year, "month": soon.month, "day": soon.day}},
                {"id": "w2", "title": "Quiz de decimales", "maxPoints": 10}]}).encode())
        if "/students?" in url:
            return Resp(json.dumps({"students": [{"userId": "u1", "profile": {"name": {"fullName": "Ana Gómez"}}},
                                                 {"userId": "u2", "profile": {"name": {"fullName": "Juan Pérez"}}}]}).encode())
        if "/studentSubmissions" in url:
            return Resp(json.dumps({"studentSubmissions": [{"userId": "u1", "state": "TURNED_IN", "assignedGrade": 90},
                                                           {"userId": "u2", "state": "CREATED"}]}).encode())
        raise AssertionError(url)


def test_cliente_classroom():
    g = FakeGoogle()
    c = classroom.Client("cid", "sec", "RT", opener=g)
    courses = c.courses()
    assert [x["name"] for x in courses] == ["Matemáticas 7A", "Matemáticas 8B"]
    assert classroom.find_course(courses, "septimo a")["id"] == "c7" and classroom.find_course(courses, "8B")["id"] == "c8"
    works = c.coursework("c7")
    w = classroom.find_work(works, "el taller de fracciones")
    assert w["id"] == "w1" and classroom.due_of(w)
    assert classroom.missing(c.submissions("c7", "w1"), c.students("c7")) == ["Juan Pérez"]
    assert classroom.to_scale(90, 100) == 4.6 and classroom.to_scale(None, 10) is None
    assert sum(1 for m, u in g.calls if u.startswith(classroom.TOKEN)) == 1          # el token se reutiliza
    url = classroom.auth_url("cid", "http://127.0.0.1:5/oauth", "st", "ch")
    assert "code_challenge=ch" in url and "access_type=offline" in url and "classroom.announcements" in urllib.parse.unquote(url)
    v, ch = classroom.pkce()
    assert 43 <= len(v) <= 128 and "=" not in ch


def test_classroom_por_voz(jv, monkeypatch, tmp_path):
    aprobaciones.configure(str(tmp_path))
    seguimiento.configure(str(tmp_path))
    g = FakeGoogle()
    for k, v in {"classroom_client_id": "cid", "classroom_client_secret": "sec", "classroom_refresh": "RT", "approvals_telegram": False}.items():
        monkeypatch.setitem(jv.settings, k, v)
    jv.cr_state.update(client=classroom.Client("cid", "sec", "RT", opener=g), key="cid" + "RT", courses=[], courses_t=0)
    rec = jv._rec
    rec.clear()
    jv.process_command("¿qué tareas tengo en Classroom de 7A?")
    assert rec.replies[-1][1] == "CLASSROOM" and "Taller de fracciones" in rec.replies[-1][0]
    jv.process_command("¿quién no ha entregado el taller de fracciones en Classroom de 7A?")
    assert "Juan Pérez" in rec.replies[-1][0] and "Ana" not in rec.replies[-1][0]
    jv.process_command("trae las notas de Classroom de 7A")
    notas = {x["actividad"]: x["nota"] for x in seguimiento.data["Matemáticas 7A"]["Ana Gómez"]}
    assert notas["Taller de fracciones"] == 4.6 and "Juan Pérez" not in seguimiento.data["Matemáticas 7A"]
    jv.process_command("publica en Classroom de 7A que mañana hay examen de fracciones")
    assert not g.announced and "¿Lo publico?" in rec.replies[-1][0]
    jv.process_command("sí")
    for _ in range(100):
        if g.announced:
            break
        time.sleep(0.02)
    assert g.announced == [{"text": "Mañana hay examen de fracciones", "state": "PUBLISHED"}]


def test_classroom_sin_conectar(jv, monkeypatch):
    monkeypatch.setitem(jv.settings, "classroom_refresh", "")
    rec = jv._rec
    rec.clear()
    jv.process_command("¿qué tareas tengo en Classroom?")
    assert "no está conectado" in rec.replies[-1][0]


# ----------------------------------------------------------------------------- seguimiento
def test_notas_y_riesgo(tmp_path):
    seguimiento.configure(str(tmp_path))
    assert seguimiento.parse_grade("4,5") == 4.5 and seguimiento.parse_grade("tres punto cinco") == 3.5
    assert seguimiento.parse_grade("7") is None and seguimiento.parse_grade("cinco") == 5.0
    assert seguimiento.parse_voice_grade("ponle 4,5 a juan perez en el quiz de fracciones de 7a") == \
        (4.5, "juan perez", "quiz de fracciones", "7a")
    assert seguimiento.parse_voice_grade("ponle tres a ana")[:2] == (3.0, "ana")
    seguimiento.add("7A", "Juan Pérez", "quiz", 2.5)
    seguimiento.add("7A", "Juan Pérez", "taller", 3.0)
    seguimiento.add("7A", "Ana Gómez", "quiz", 4.8)
    assert seguimiento.average("7A", "Juan Pérez") == 2.7          # 10.1: como Zeti (quiz en Conocer 35 %, taller en Hacer 30 %)
    risk = seguimiento.at_risk("7A", ["Juan Pérez", "Ana Gómez", "Luis"], {"Luis": 4}, 3.0, 3)
    assert risk == [("Juan Pérez", ["promedio 2,7"]), ("Luis", ["4 fallas"])]
    assert "2 estudiantes en riesgo" in seguimiento.spoken_risk("7A", risk)
    seguimiento.configure(str(tmp_path))                     # se guarda
    assert len(seguimiento.data["7A"]["Juan Pérez"]) == 2


def test_seguimiento_por_voz(jv, monkeypatch, tmp_path):
    seguimiento.configure(str(tmp_path))
    monkeypatch.setitem(jv.aula.data, "cursos", {"7A": ["Juan Pérez", "Ana Gómez", "Luis Rojas"]})
    monkeypatch.setitem(jv.aula.data, "activo", "7A")
    monkeypatch.setitem(jv.aula.data, "asistencia", {"7A": {"2026-10-01": ["Luis Rojas"], "2026-10-02": ["Luis Rojas"],
                                                            "2026-10-03": ["Luis Rojas"]}})
    rec = jv._rec
    rec.clear()
    jv.process_command("ponle 2,5 a Juan en el quiz de fracciones")
    assert "Anotado: 2,5 a Juan Pérez" in rec.replies[-1][0]
    jv.process_command("¿cómo va Juan en 7A?")
    assert "promedio 2,5" in rec.replies[-1][0]
    jv.process_command("¿quiénes están en riesgo en 7A?")
    assert "Juan Pérez" in rec.replies[-1][0] and "Luis Rojas (3 fallas)" in rec.replies[-1][0]
    rec.clear()
    jv.process_command("¿cómo va el proyecto?")
    assert rec.replies[-1][1] == "PROYECTO"                     # no es un estudiante


def test_resumen_de_riesgo_los_viernes(jv, monkeypatch, tmp_path):
    seguimiento.configure(str(tmp_path))
    monkeypatch.setitem(jv.aula.data, "cursos", {"7A": ["Juan Pérez"]})
    seguimiento.add("7A", "Juan Pérez", "quiz", 2.0)
    alerts = []
    monkeypatch.setattr(jv, "alert", lambda text, origin="JARVIS": alerts.append(text))
    jv._risk_state["week"] = ""
    assert jv.risk_check(datetime.datetime(2026, 10, 29, 15, 0)) is None          # jueves: no
    assert jv.risk_check(datetime.datetime(2026, 10, 30, 15, 0))                  # viernes por la tarde
    assert jv.risk_check(datetime.datetime(2026, 10, 30, 16, 0)) is None          # una vez por semana
    assert alerts and "Juan Pérez" in alerts[0]


# ----------------------------------------------------------------------------- banco de preguntas
QUIZ = {"titulo": "Fracciones", "grado": "7", "tema": "fracciones equivalentes", "preguntas": [
    {"enunciado": f"¿Cuánto es {i}/2 + {i}/2?", "opciones": [str(i), "1", "2", "3"], "respuesta": "a", "explicacion": ""} for i in range(1, 7)]}


def test_banco(tmp_path):
    banco.configure(str(tmp_path))
    assert banco.add_quiz(QUIZ) == 6 and banco.add_quiz(QUIZ) == 0          # sin repetir
    assert banco.count() == 6 and banco.count("fracciones") == 6 and banco.count("historia de roma") == 0
    q = banco.build_quiz("fracciones", 4)
    assert len(q["preguntas"]) == 4 and q["tema"] == "fracciones"
    used = [x["usos"] for x in banco.items]
    assert sorted(used) == [0, 0, 1, 1, 1, 1]
    q2 = banco.build_quiz("fracciones", 2)                                    # las menos usadas primero
    assert all(p["enunciado"] in {x["enunciado"] for x in banco.items if x["usos"] == 1} for p in q2["preguntas"])
    assert banco.build_quiz("historia de roma", 5) is None


def test_banco_por_voz(jv, monkeypatch, tmp_path):
    banco.configure(str(tmp_path))
    banco.add_quiz(QUIZ)
    built = []
    monkeypatch.setattr(jv.aula, "build_docx", lambda kind, m, *a, **k: built.append(m) or str(tmp_path / "q.docx"))
    monkeypatch.setattr(jv, "_open_doc", lambda p: False)
    rec = jv._rec
    rec.clear()
    jv.process_command("¿cuántas preguntas tengo de fracciones?")
    assert "6 preguntas de fracciones" in rec.replies[-1][0]
    if jv.Document is not None:
        jv.process_command("haz un quiz de 5 preguntas de fracciones con el banco")
        assert built and len(built[0]["preguntas"]) == 5 and not rec.ai


# ----------------------------------------------------------------------------- memoria editable
def test_memoria_editable(jv, tmp_path):
    f = perfil.add("mi hija se llama Sara")
    perfil.update(f["id"], "mi hija se llama Sofía")
    assert any(x["texto"] == "Mi hija se llama Sofía" or x["texto"] == "mi hija se llama Sofía" for x in perfil.snapshot())
    r = jv.handle_profile_edit({"texto": "trabajo en el colegio Simón Bolívar"})
    assert any("Simón Bolívar" in x["texto"] for x in r["facts"])
    recuerdos.configure(str(tmp_path))
    recuerdos.log("user", "el examen de 7A vale 30 por ciento", now=datetime.datetime(2026, 10, 20, 9, 0))
    recuerdos.log("user", "otra cosa", now=datetime.datetime(2026, 10, 20, 9, 1))
    items = jv.handle_history_search({"q": "examen 7A"})["items"]
    assert items and "30 por ciento" in items[0]["x"]
    assert jv.handle_history_delete({"ts": items[0]["ts"], "x": items[0]["x"]})["ok"]
    assert not jv.handle_history_search({"q": "examen 7A"})["items"]
    info = jv.handle_habits_info({"unreject": True})
    assert info["rechazadas"] == 0


def test_recuerdos_espontaneos(jv, monkeypatch, tmp_path):
    recuerdos.configure(str(tmp_path))
    old = datetime.datetime.now() - datetime.timedelta(days=5)
    recuerdos.log("user", "el examen final de 7A vale el 30 por ciento de la nota", now=old)
    recuerdos.log("user", "pon música para concentrarme", now=old)
    recuerdos.log("user", "qué hora es", now=old)
    monkeypatch.setitem(jv.settings, "history_enabled", True)
    monkeypatch.setitem(jv.settings, "memory_proactive", True)
    jv._recall_cache["t"] = 0
    ctx = jv.recall_ctx("¿cuánto vale el examen final de 7A?")
    assert "30 por ciento" in ctx and "hace" not in ctx[:3]
    assert jv.recall_ctx("¿qué tiempo hace en Medellín hoy?") == ""
    monkeypatch.setitem(jv.settings, "memory_proactive", False)
    assert jv.recall_ctx("¿cuánto vale el examen final de 7A?") == ""
