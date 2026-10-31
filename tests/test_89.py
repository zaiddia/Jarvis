"""Pruebas de la 8.9: datos de estudiantes cifrados (con clave de recuperación) y copias de seguridad en Drive."""
import json
import zipfile

import pytest

import classroom
import datos
import gservicios
import respaldo
import seguimiento
import sincronizar

pytestmark = pytest.mark.skipif(not datos.available(), reason="sin la librería cryptography")


def test_cifrado_ida_y_vuelta(tmp_path, monkeypatch):
    monkeypatch.setattr(datos, "_cfg", dict(datos._cfg))                       # no tocar la configuración de Jarvis
    k = datos.new_key()
    datos.configure(lambda: k, lambda: True)
    p = tmp_path / "notas_estudiantes.json"
    datos.write_json(str(p), {"7A": {"Juan Pérez": [{"nota": 2.5}]}})
    raw = p.read_bytes()
    assert raw.startswith(datos.MARK) and b"Juan" not in raw
    assert datos.read_json(str(p)) == {"7A": {"Juan Pérez": [{"nota": 2.5}]}}
    assert datos.file_state(str(p)) == "cifrado"
    datos.configure(lambda: datos.new_key(), lambda: True)                    # otra clave
    with pytest.raises(datos.DataLocked):
        datos.read_json(str(p))
    assert datos.file_state(str(p)) == "bloqueado"
    datos.configure(lambda: "", lambda: False)
    datos.write_json(str(tmp_path / "x.json"), {"a": 1})
    assert json.loads((tmp_path / "x.json").read_text(encoding="utf-8")) == {"a": 1}
    assert datos.read_json(str(tmp_path / "no.json")) is None


@pytest.fixture
def protegido(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(jv, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(seguimiento, "_path", str(tmp_path / "notas_estudiantes.json"))
    monkeypatch.setattr(seguimiento, "data", {"7A": {"Juan Pérez": [{"actividad": "q", "nota": 2.0, "fecha": "", "origen": "voz"}]}})
    monkeypatch.setattr(seguimiento, "locked", False)
    for m in (jv.aula, jv.informes, jv.diarioclase):
        monkeypatch.setattr(m, "_path", str(tmp_path / ("x-" + m.__name__ + ".json")))
        monkeypatch.setattr(m, "locked", False)
    monkeypatch.setitem(jv.settings, "protect_students", False)
    monkeypatch.setitem(jv.settings, "data_key", "")
    monkeypatch.setattr(jv, "apply_settings", lambda d: jv.settings.update(d) or {"ok": True})
    return tmp_path


def test_proteger_y_abrir_en_otro_equipo(jv, protegido):
    r = jv.protect_students(True)
    assert r["ok"] and jv.settings["data_key"] and jv.settings["protect_students"]
    raw = (protegido / "notas_estudiantes.json").read_bytes()
    assert raw.startswith(datos.MARK) and "Juan".encode() not in raw
    key = jv.settings["data_key"]
    # «otro equipo»: otra clave → bloqueado, y no se sobrescribe
    jv.settings["data_key"] = datos.new_key()
    seguimiento.load()
    assert seguimiento.locked and seguimiento.data == {}
    seguimiento.add("7A", "Ana", "x", 4.0)                                    # no debe pisar el archivo bueno
    assert (protegido / "notas_estudiantes.json").read_bytes() == raw
    assert jv.students_locked() == ["notas_estudiantes.json"]
    assert jv.extra_checks() and any("otra clave" in i["texto"] for i in jv.extra_checks())
    r = jv.unlock_students(key)
    assert r["ok"] and not seguimiento.locked and "Juan Pérez" in seguimiento.data["7A"]
    assert not jv.unlock_students("no-es-una-clave")["ok"]
    r = jv.protect_students(False)
    assert r["ok"] and b"Juan" in (protegido / "notas_estudiantes.json").read_bytes()


def test_respaldo_y_sincronizacion_con_datos_cifrados(jv, protegido, tmp_path):
    jv.protect_students(True)
    res = respaldo.create(str(protegido), str(tmp_path / "bak"), jv.settings, jv.SECRET_FIELDS, False, "8.9", "manual")
    with zipfile.ZipFile(res["path"]) as z:
        assert z.read("notas_estudiantes.json").startswith(datos.MARK)
        assert "data_key" not in json.loads(z.read("config.json"))            # la clave nunca va en la copia
    assert "seguimiento" in res["counts"]
    dest = tmp_path / "nuevo"
    respaldo.restore(res["path"], str(dest), ["seguimiento"])
    assert (dest / "notas_estudiantes.json").read_bytes().startswith(datos.MARK)
    assert sincronizar._valid(str(protegido / "notas_estudiantes.json"))


class FakeDrive:
    def __init__(self):
        self.calls, self.deleted = [], []

    def call(self, method, path, params=None, body=None, base=classroom.API):
        self.calls.append((method, path))
        if method == "DELETE":
            self.deleted.append(path)
            return {}
        if path == "files" and method == "POST":
            return {"id": "SUB" if body.get("parents") else "ROOT"}
        if path == "files":
            return {"files": [{"id": f"z{i}", "name": f"Jarvis respaldo {i}.zip"} for i in range(12)]}
        return {"id": "?", "trashed": True}

    def raw(self, method, url, data, ctype):
        return {"id": "UP", "name": "Jarvis respaldo nuevo.zip"}


def test_copia_en_drive(jv, monkeypatch, tmp_path):
    g = FakeDrive()
    monkeypatch.setattr(jv, "classroom_client", lambda: g)
    monkeypatch.setitem(jv.settings, "google_scopes", " ".join(classroom.SCOPES))
    monkeypatch.setitem(jv.settings, "drive_folder_id", "")
    monkeypatch.setitem(jv.settings, "drive_backup_folder_id", "")
    monkeypatch.setitem(jv.settings, "drive_backup_keep", 10)
    monkeypatch.setattr(jv, "apply_settings", lambda d: jv.settings.update(d) or {"ok": True})
    z = tmp_path / "Jarvis respaldo.zip"
    z.write_bytes(b"PK")
    assert jv.backup_to_drive(str(z)) == "Jarvis respaldo nuevo.zip"
    assert jv.settings["drive_backup_folder_id"] == "SUB" and len(g.deleted) == 2       # deja las 10 últimas
    monkeypatch.setattr(jv, "make_backup", lambda kind="manual": {"path": str(z)})
    jv._rec.clear()
    jv.process_command("haz una copia de seguridad en Drive")
    assert "Respaldos" in jv._rec.said()
    assert gservicios.list_folder(g, "SUB")
