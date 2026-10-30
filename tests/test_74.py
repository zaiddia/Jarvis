"""Pruebas de la 7.4: aprende tus costumbres, memoria buscable y tareas programadas."""
import datetime
import json
import os
import tempfile
import time

import aprendizaje
import recuerdos
import tareas

D = datetime.datetime


# ----------------------------------------------------------------------------- aprender
def _acts(days=4, start=D(2026, 10, 19, 7, 30)):
    out = []
    for d in range(days):
        t0 = (start + datetime.timedelta(days=d)).timestamp()
        out += [{"ts": t0, "key": 'abrir_app:{"nombre": "word"}', "text": "abre word"},
                {"ts": t0 + 40, "key": 'volumen:{"accion": "fijar", "nivel": "30"}', "text": "volumen al 30"},
                {"ts": t0 + 90, "key": "spotify:{}", "text": "pon música para concentrarse"}]
    return out


def test_secuencia_repetida():
    s = aprendizaje.find_sequence(_acts(3))
    assert s and s["texts"] == ["abre word", "volumen al 30", "pon música para concentrarse"] and s["days"] == 3
    assert aprendizaje.find_sequence(_acts(2)) is None                       # 2 días no bastan
    known = [['abrir_app:{"nombre": "word"}', 'volumen:{"accion": "fijar", "nivel": "30"}', "spotify:{}"]]
    assert aprendizaje.find_sequence(_acts(4), known_steps=known) is None    # ya es una rutina
    rep = [{"ts": 1e9 + i * 10 + d * 86400, "key": "volumen:{}", "text": "sube"} for d in range(4) for i in range(3)]
    assert aprendizaje.find_sequence(rep) is None                            # repetir lo mismo no es rutina


def test_secuencia_separada_por_mucho_tiempo_no_cuenta():
    acts = []
    for d in range(4):
        t0 = D(2026, 10, 19 + d, 7, 30).timestamp()
        acts += [{"ts": t0, "key": "a:{}", "text": "a"}, {"ts": t0 + 3600, "key": "b:{}", "text": "b"}]
    assert aprendizaje.find_sequence(acts) is None


def test_habito_de_horario():
    acts = _acts(4)
    h = aprendizaje.find_time_habit(acts, now=D(2026, 10, 24).timestamp())
    assert h and h["at"] == (7, 30) and h["weekdays"] and h["text"] in ("abre word", "volumen al 30", "pon música para concentrarse")
    assert aprendizaje.find_time_habit(acts[:6], now=D(2026, 10, 24).timestamp()) is None


def test_correccion():
    c = aprendizaje.find_correction(['volumen:{"accion": "fijar", "nivel": "40"}', None], ["volumen al 40", "decir hola"],
                                    'volumen:{"accion": "fijar", "nivel": "25"}', "volumen al 25")
    assert c == {"index": 0, "old": "volumen al 40", "new": "volumen al 25"}
    assert aprendizaje.find_correction(['volumen:{"accion": "fijar", "nivel": "40"}'], ["volumen al 40"],
                                       'volumen:{"accion": "subir"}', "sube el volumen") is None


def test_aprender_en_jarvis(jv, monkeypatch, tmp_path):
    aprendizaje.configure(str(tmp_path))
    rec = jv._rec
    jv.settings["learn_enabled"] = True
    jv._tl.cmd_text = "abre word"
    jv.learn_note("abrir_app", {"nombre": "word"})
    assert aprendizaje.data["acciones"][-1]["text"] == "abre word"
    jv._tl.remote = True                                  # desde el celular no se aprende
    n = len(aprendizaje.data["acciones"])
    jv.learn_note("volumen", {"accion": "subir"})
    jv._tl.remote = False
    assert len(aprendizaje.data["acciones"]) == n
    # propuesta de rutina y respuesta «sí, llámala modo escribir»
    seq = aprendizaje.find_sequence(_acts(3))
    created = {}
    monkeypatch.setattr(jv.rutinas, "upsert", lambda nombre, frases, pasos, old=None, cuando="": created.update(n=nombre, p=pasos, c=cuando))
    rec.clear()
    jv._offer("rutina", seq, "¿La guardo?")
    assert rec.replies[-1][1] == "APRENDE"
    assert jv.learn_answer("si llamala modo escribir")
    assert created["n"] == "Modo escribir" and created["p"].splitlines() == seq["texts"]
    assert seq["id"] in aprendizaje.data["hechas"]
    assert not jv.learn_answer("si")                     # ya no hay propuesta pendiente
    # «no» = no volver a proponerla
    habit = {"id": "hora:x@07:30", "key": "x", "text": "abre word", "at": (7, 30), "weekdays": True, "days": 4}
    jv._offer("horario", habit, "¿Lo hago solo?")
    assert jv.learn_answer("no gracias") and "hora:x@07:30" in aprendizaje.data["rechazadas"]
    jv._offer("horario", habit, "¿Lo hago solo?")
    assert jv.learn_answer("si")
    assert created["c"] == "07:30 lun-vie"


def test_correccion_tras_una_rutina(jv, monkeypatch, tmp_path):
    aprendizaje.configure(str(tmp_path))
    r = {"nombre": "Modo clase", "frases": ["modo clase"], "pasos": ["volumen al 40", "decir listo"], "cuando": ""}
    offers = []
    monkeypatch.setattr(jv, "_offer", lambda kind, data, text: offers.append((kind, data)))

    class T:                                              # el Timer se ejecuta al momento
        def __init__(self, s, f):
            self.f = f

        def start(self):
            self.f()
    monkeypatch.setattr(jv.threading if hasattr(jv, "threading") else __import__("threading"), "Timer", T)
    jv.learn_routine_done(r)
    jv._tl.cmd_text = "volumen al 25"
    jv.learn_note("volumen", {"accion": "fijar", "nivel": "25"})
    assert offers and offers[0][0] == "corregir" and offers[0][1]["new"] == "volumen al 25"


# ----------------------------------------------------------------------------- memoria buscable
def test_ocultar_secretos():
    r = recuerdos.redact("mi contraseña es Hola123, correo zaid@x.com y clave AIzaSyA1234567890abcdefgh, tarjeta 4111 1111 1111 1111")
    for secret in ("Hola123", "zaid@x.com", "AIzaSyA1234567890abcdefgh", "4111"):
        assert secret not in r


def test_fechas():
    hoy = datetime.date(2026, 10, 30)                     # viernes
    assert recuerdos.date_range("¿qué te dije ayer?", hoy)[:2] == (datetime.date(2026, 10, 29),) * 2
    assert recuerdos.date_range("la semana pasada", hoy)[:2] == (datetime.date(2026, 10, 19), datetime.date(2026, 10, 25))
    assert recuerdos.date_range("en septiembre", hoy)[:2] == (datetime.date(2026, 9, 1), datetime.date(2026, 9, 30))
    assert recuerdos.date_range("el lunes", hoy)[:2] == (datetime.date(2026, 10, 26),) * 2
    assert recuerdos.date_range("sobre el examen", hoy) == (None, None, "")


def test_buscar_en_el_historial(tmp_path):
    recuerdos.configure(str(tmp_path))
    rows = [(D(2026, 10, 21, 9, 0), "user", "el examen de 7A es el viernes y vale el 30 por ciento"),
            (D(2026, 10, 21, 9, 0, 3), "jarvis", "Anotado: examen de 7A el viernes."),
            (D(2026, 10, 22, 10, 0), "user", "pon música para concentrarse"),
            (D(2026, 10, 29, 11, 0), "user", "las calificaciones de 8B se entregan el lunes"),
            (D(2026, 9, 3, 8, 0), "user", "mi contraseña es secreta123")]
    for dt, role, text in rows:
        recuerdos.log(role, text, now=dt)
    hoy = datetime.date(2026, 10, 30)
    hits = recuerdos.search("¿qué te dije la semana pasada sobre los exámenes de 7A?", today=hoy)
    assert hits and "examen de 7A" in hits[0]["x"] and hits[0]["r"] == "u" and "Anotado" in hits[0].get("after", "")
    assert not any("8B" in h["x"] for h in hits)          # fuera de «la semana pasada»
    hits = recuerdos.search("calificaciones", today=hoy)
    assert hits[0]["x"].startswith("las calificaciones")
    assert all("secreta123" not in e["x"] for e in recuerdos.load())
    assert "21 de octubre" in recuerdos.spoken(recuerdos.search("examen 7a", today=hoy), hoy)
    # por significado: un «embed» falso que sabe que «prueba» y «examen» son lo mismo
    def embed(texts):
        return [[1.0, 0.0] if ("examen" in x or "prueba" in x) else [0.0, 1.0] for x in texts]
    hits = recuerdos.search("la prueba", embed=embed, embed_tag="falso", today=hoy)
    assert hits and "examen" in hits[0]["x"]
    assert os.path.exists(os.path.join(str(tmp_path), "historial", "vectores-falso.json"))
    recuerdos.clear()
    assert recuerdos.load() == []


def test_recordar_por_voz(jv, tmp_path):
    recuerdos.configure(str(tmp_path))
    recuerdos.log("user", "la reunión de padres es el jueves a las 3", now=D.now() - datetime.timedelta(days=2))
    rec = jv._rec
    rec.clear()
    jv.state["ai"] = "error"
    jv.process_command("busca en mi memoria la reunión de padres")
    assert rec.replies and rec.replies[-1][1] == "MEMORIA" and "jueves" in rec.replies[-1][0]
    rec.clear()
    jv.state["ai"] = "ok"
    jv.process_command("¿qué te dije sobre la reunión de padres?")
    assert rec.ai and "reunión de padres es el jueves" in rec.ai[-1][0]         # la IA recibe lo encontrado
    jv.state["ai"] = "unknown"


# ----------------------------------------------------------------------------- tareas programadas
def test_entender_tareas():
    p = tareas.parse_voice("cada lunes a las 6 de la tarde resume mis pendientes y mándamelo al celular")
    assert p == {"orden": "resume mis pendientes", "cuando": "18:00 lun", "entrega": "celular"}
    p = tareas.parse_voice("de lunes a viernes a las 6:30 de la mañana dime qué tengo hoy")
    assert p == {"orden": "dime qué tengo hoy", "cuando": "06:30 lun-vie", "entrega": "voz"}
    p = tareas.parse_voice("los martes y jueves a las 2 de la tarde dime qué tengo pendiente y mándamelo al celular y dímelo también")
    assert p["cuando"] == "14:00 mar,jue" and p["entrega"] == "ambos" and p["orden"] == "dime qué tengo pendiente"
    assert tareas.parse_voice("cada viernes a las 5 pm investiga noticias de educación y envíamelo por telegram")["orden"] == "investiga noticias de educación"
    for no in ("recuérdame cada lunes a las 6 llamar a mamá", "pon un temporizador de 5 minutos",
               "cada lunes resume mis pendientes", "todos los días a las 7"):
        assert tareas.parse_voice(no) is None, no


def test_tareas_a_su_hora(tmp_path):
    tareas.configure(str(tmp_path))
    x = tareas.add("dime el clima", "07:00 lun-vie", "celular")
    viernes = D(2026, 10, 30, 7, 3)
    assert [t["id"] for t in tareas.due(viernes)] == [x["id"]]
    assert tareas.due(D(2026, 10, 31, 7, 3)) == []          # sábado
    assert tareas.due(D(2026, 10, 30, 7, 20)) == []         # pasados 10 minutos
    assert tareas.missed(D(2026, 10, 30, 9, 0))[0]["_missed"]
    tareas.mark_done(x["id"], viernes.date())
    assert tareas.due(viernes) == [] and tareas.missed(D(2026, 10, 30, 9, 0)) == []
    tareas.configure(str(tmp_path))                          # se guardan
    assert tareas.tasks[0]["orden"] == "dime el clima"
    tareas.set_active(x["id"], False)
    assert tareas.due(D(2026, 11, 2, 7, 1)) == []
    assert tareas.remove(x["id"]) and tareas.tasks == []


def test_ejecutar_tarea_y_entregar(jv, monkeypatch):
    sent, said = [], []
    monkeypatch.setattr(jv, "telegram_run", lambda text: "Tienes 2 pendientes: llamar al banco y revisar talleres.")
    monkeypatch.setattr(jv, "telegram_send", lambda text, chat=None: (sent.append(text), True)[1])
    monkeypatch.setattr(jv, "reply", lambda text, origin="JARVIS": said.append((text, origin)))
    monkeypatch.setitem(jv.settings, "telegram_token", "123:abc")
    monkeypatch.setitem(jv.settings, "telegram_chat", "42")
    jv.run_task({"id": "1", "orden": "resume mis pendientes", "entrega": "celular"})
    assert sent and "2 pendientes" in sent[0] and not said
    jv.run_task({"id": "2", "orden": "resume mis pendientes", "entrega": "ambos"})
    assert len(sent) == 2 and said[-1][1] == "TAREA"
    monkeypatch.setitem(jv.settings, "telegram_token", "")
    jv.run_task({"id": "3", "orden": "resume mis pendientes", "entrega": "celular"})   # sin Telegram: en voz alta
    assert len(sent) == 2 and len(said) == 2


def test_tareas_desde_ajustes(jv, tmp_path):
    tareas.configure(str(tmp_path))
    r = jv.handle_tasks_add({"orden": "dime el clima", "cuando": "7:30 de lunes a viernes", "entrega": "voz"})
    assert r["ok"] and r["task"]["cuando"] == "07:30 lun-vie"
    assert not jv.handle_tasks_add({"orden": "x", "cuando": "cuando quieras"})["ok"]
    tid = r["task"]["id"]
    assert jv.handle_tasks_toggle({"id": tid, "on": False})["tasks"][0]["activa"] is False
    assert jv.handle_tasks_remove({"id": tid})["tasks"] == []


def test_copia_incluye_lo_nuevo(tmp_path):
    import respaldo
    src, out, dst = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    (src / "historial").mkdir(parents=True)
    (src / "tareas.json").write_text(json.dumps([{"id": "1", "orden": "dime el clima", "cuando": "07:00"}]), encoding="utf-8")
    (src / "aprendizaje.json").write_text(json.dumps({"acciones": [], "rechazadas": [], "hechas": []}), encoding="utf-8")
    (src / "historial" / "2026-10.jsonl").write_text('{"ts": "2026-10-01T08:00:00", "r": "u", "x": "hola"}\n', encoding="utf-8")
    r = respaldo.create(str(src), str(out), {})
    assert {"tareas", "aprendizaje", "historial"} <= set(r["parts"])
    done = respaldo.restore(r["path"], str(dst), ["tareas", "aprendizaje", "historial"])
    assert set(done) == {"tareas", "aprendizaje", "historial"}
    assert (dst / "historial" / "2026-10.jsonl").exists()


def test_ninguna_parte_pisa_nombres_de_otra():
    """Cada parte de nucleo/ se mezcla con jarvis.py: dos con el mismo nombre se pisarían en silencio
    (le pasó a «_NAME_RE» al escribir la 7.4)."""
    import ast
    import collections
    import glob
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    defs = collections.defaultdict(list)
    for f in [os.path.join(root, "jarvis.py")] + glob.glob(os.path.join(root, "nucleo", "*.py")):
        for st in ast.parse(open(f, encoding="utf-8").read()).body:
            names = []
            if isinstance(st, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
                names = [st.name]
            elif isinstance(st, ast.Assign):
                names = [n.id for x in st.targets for n in ast.walk(x) if isinstance(n, ast.Name)]
            for n in names:
                defs[n].append(os.path.basename(f))
    dup = {n: v for n, v in defs.items() if len(set(v)) > 1 and n not in ("__all__", "J")}
    assert not dup, dup
