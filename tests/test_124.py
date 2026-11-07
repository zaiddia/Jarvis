"""Pruebas de la 12.4: el mapa de errores protegido como las notas, guardar en la plataforma solo con tu «sí»
(y sin cambiar notas que ya estaban) e instalar programas solo con tu «sí»."""
import datos
import procedimiento
import respaldo
import sincronizar


def test_mapa_de_errores_protegido(jv, monkeypatch, tmp_path):
    from nucleo.proteccion import STUDENT_FILES
    assert STUDENT_FILES["mapa_errores.json"] is procedimiento
    assert "mapa_errores.json" in respaldo.FILES and "mapa_errores.json" in sincronizar.FILES
    assert jv._RELOAD["mapa_errores.json"] == "procedimiento"
    monkeypatch.setitem(jv.settings, "protect_students", True)
    monkeypatch.setitem(jv.settings, "data_key", datos.new_key())
    procedimiento.configure(str(tmp_path))
    procedimiento.record("7A", "Ana Gómez", {"error": {"categoria": "signo", "explicacion": "cambió el signo", "paso": 2}, "problema": "3x+4=19"})
    raw = open(tmp_path / "mapa_errores.json", "rb").read()
    assert datos.is_encrypted(raw) and "Ana".encode() not in raw              # cifrado: no se lee el nombre
    procedimiento.load()
    assert procedimiento.data["cursos"]["7A"][0]["estudiante"] == "Ana Gómez" and not procedimiento.locked
    monkeypatch.setitem(jv.settings, "data_key", datos.new_key())
    procedimiento.load()
    assert procedimiento.locked and procedimiento.data["cursos"] == {}
    procedimiento.save()                                                      # bloqueado: no lo pisa
    assert open(tmp_path / "mapa_errores.json", "rb").read() == raw
    procedimiento.configure(str(tmp_path / "limpio"))                         # que no afecte a otras pruebas
    procedimiento.locked = False


class _Loc:
    def __init__(self, log, fid):
        self.log, self.fid = log, fid

    def fill(self, v):
        self.log.append((self.fid, v))

    def select_option(self, label):
        self.log.append((self.fid, label))

    def evaluate(self, *a):
        pass


class _Frame:
    def __init__(self, log):
        self.log = log

    def locator(self, sel):
        return _Loc(self.log, sel.split('"')[1])


def test_planilla_sin_cambiar_lo_que_ya_estaba_y_guardar_con_si(jv, monkeypatch):
    written, asked = [], []
    fr = _Frame(written)
    campos = [{"id": "j1", "fid": "a1", "tag": "input", "name": "", "label": "", "fila": "Ana Gómez", "columna": "Definitiva", "valor": "", "opciones": [],
               "frame": fr},
              {"id": "j2", "fid": "a2", "tag": "input", "name": "", "label": "", "fila": "Luis Rojas", "columna": "Definitiva", "valor": "3,0", "opciones": [],
               "frame": fr}]
    import nucleo.plataformas as pf
    monkeypatch.setattr(pf, "_run", lambda fn, timeout=180: fn())
    monkeypatch.setattr(pf, "_all_frames_extract", lambda: (campos, False))
    monkeypatch.setattr(jv, "course_data", lambda c: {"Ana Gómez": {"definitiva": 4.5}, "Luis Rojas": {"definitiva": 4.0}})
    monkeypatch.setattr(jv, "ai_chat", lambda *a, **k: '{"asignaciones": [{"campo": "j1", "estudiante": "Ana Gómez", "dato": "definitiva", "valor": "4,5"}, '
                        '{"campo": "j2", "estudiante": "Luis Rojas", "dato": "definitiva", "valor": "4,0"}]}')
    monkeypatch.setitem(jv.settings, "zeti_comma", True)
    monkeypatch.setattr(jv, "request_approval", lambda tipo, titulo, detalle="", on_ok=None, on_no=None, **k: asked.append((tipo, titulo, detalle, on_ok)))
    msg = jv.fill_page("7A")
    assert written == [("a1", "4,5")]                                          # la que ya tenía 3,0 no se tocó
    assert "no las cambié" in msg and asked[0][0] == "plataforma" and "Luis Rojas (definitiva): 3,0 → 4,0" in asked[0][2]
    asked[0][3]()                                                              # apruebas el cambio
    assert written[-1] == ("a2", "4,0")
    # guardar: pide permiso, no pulsa nada todavía
    saved = []
    monkeypatch.setattr(pf, "save_page", lambda: saved.append(1) or "Pulsé «Guardar».")
    monkeypatch.setitem(jv.agent, "curso", "7A")
    jv._rec.clear()
    assert jv.platform_voice("guarda la planilla", "guarda la planilla")
    assert not saved and asked[-1][0] == "plataforma" and asked[-1][1].startswith("Guardar en la plataforma 2 notas de 2 estudiantes")
    asked[-1][3]()
    assert saved == [1] and jv.agent["filled"] == []


def test_instalar_solo_con_si(jv, monkeypatch):
    asked, jobs = [], []
    monkeypatch.setattr(jv, "request_approval", lambda tipo, titulo, detalle="", on_ok=None, on_no=None, **k: asked.append((tipo, titulo, on_ok)))
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": jobs.append(label))
    monkeypatch.setattr(jv, "IS_WIN", True)
    jv.local_brain_voice("instala ollama", "instala ollama")
    assert asked and asked[-1][0] == "instalar" and not jobs
    asked[-1][2]()
    assert jobs == ["Instalando Ollama"]
    monkeypatch.setattr(jv, "kokoro_ready", lambda: False)
    jobs.clear()
    jv.kokoro_job["busy"] = False
    assert jv.local_voice_voice("instala la voz kokoro", "instala la voz kokoro")
    assert asked[-1][0] == "instalar" and "Kokoro" in asked[-1][1] and not jobs
    asked[-1][2]()
    assert jobs == ["Instalando la voz Kokoro"]
    jv.kokoro_job["busy"] = False
