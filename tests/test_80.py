"""Pruebas de la 8.0: registro de errores, informe sin claves, claves cifradas y revisión de conexiones."""
import json
import sys

import pytest

import errores
import secreto


# ----------------------------------------------------------------------------- claves cifradas
def test_secreto_fuera_de_windows_no_toca_nada(monkeypatch):
    monkeypatch.setattr(secreto, "available", lambda: False)
    assert secreto.seal("abc123") == "abc123"
    assert secreto.unseal("abc123") == ("abc123", True)
    assert secreto.unseal("dpapi:xxxx") == ("", False)          # cifrada en otro equipo: no se puede abrir


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI solo existe en Windows")
def test_secreto_dpapi_ida_y_vuelta():
    s = secreto.seal("AIza-mi-clave-ñ")
    assert s.startswith(secreto.PREFIX) and "AIza" not in s
    assert secreto.unseal(s) == ("AIza-mi-clave-ñ", True)
    assert secreto.seal(s) == s                                   # no se cifra dos veces
    assert secreto.seal("x", enabled=False) == "x"
    assert secreto.unseal(secreto.PREFIX + "bm8tdmFsZQ==") == ("", False)


def test_ajustes_cifran_y_descifran(jv, monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    monkeypatch.setattr(jv, "CONFIG_PATH", str(path))
    monkeypatch.setattr(secreto, "available", lambda: True)
    monkeypatch.setattr(secreto, "_crypt", lambda data, protect: data[::-1])   # «cifrado» de prueba
    monkeypatch.setitem(jv.settings, "telegram_token", "123456:ABCDEFG")
    monkeypatch.setitem(jv.settings, "encrypt_secrets", True)
    monkeypatch.setattr(jv, "PORTABLE", False)
    jv.save_settings_file()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["telegram_token"].startswith("dpapi:") and "ABCDEFG" not in raw["telegram_token"]
    assert raw["output_dir"] == jv.settings["output_dir"]        # lo demás, igual
    jv.settings["telegram_token"] = ""
    jv.load_settings()
    assert jv.settings["telegram_token"] == "123456:ABCDEFG" and jv.secrets_lost == []
    # en modo USB se guarda sin cifrar
    monkeypatch.setattr(jv, "PORTABLE", True)
    jv.save_settings_file()
    assert json.loads(path.read_text(encoding="utf-8"))["telegram_token"] == "123456:ABCDEFG"


def test_clave_de_otro_equipo(jv, monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"gemini_api_key": "dpapi:basura"}), encoding="utf-8")
    monkeypatch.setattr(jv, "CONFIG_PATH", str(path))
    monkeypatch.setattr(secreto, "available", lambda: True)

    def broken(data, protect):
        raise OSError("otro equipo")
    monkeypatch.setattr(secreto, "_crypt", broken)
    jv.load_settings()
    assert jv.secrets_lost == ["gemini_api_key"] and jv.settings["gemini_api_key"] == ""
    assert any(i["estado"] == "fallo" and "gemini_api_key" in i["texto"] for i in jv.extra_checks())
    jv.secrets_lost.clear()


# ----------------------------------------------------------------------------- errores
def test_errores_sin_claves(tmp_path):
    errores.configure(str(tmp_path), lambda: ["AIzaSECRETA123", ""])
    try:
        raise ValueError("falló con la clave AIzaSECRETA123 y token=abcdefghijk123")
    except ValueError as e:
        item = errores.record("IA", e, "pregúntale algo")
    assert "AIzaSECRETA123" not in json.dumps(item) and "abcdefghijk123" not in item["error"]
    assert "ValueError" in item["traza"] and item["orden"] == "pregúntale algo"
    assert errores.record("IA", ValueError("falló con la clave AIzaSECRETA123 y token=abcdefghijk123")) is None   # repetido
    errores.record("TELEGRAM", "sin conexión", level="aviso")
    assert [e["origen"] for e in errores.recent()] == ["IA", "TELEGRAM"]
    rep = errores.report("8.0", "Prueba: todo bien", ["[10:00] [JARVIS] hola", "bot123456789:" + "A" * 30])
    assert "ÚLTIMOS ERRORES (2)" in rep and "Prueba: todo bien" in rep and "A" * 30 not in rep
    assert "1 error" in errores.spoken()
    errores.clear()
    assert errores.recent() == [] and "No he tenido errores" in errores.spoken()


def test_error_de_una_orden_queda_registrado(jv, monkeypatch, tmp_path):
    errores.configure(str(tmp_path), jv._secret_values)
    monkeypatch.setattr(jv, "process_command", lambda text: 1 / 0)
    q = []

    class Q:
        def get(self):
            if q:
                raise SystemExit
            q.append(1)
            return "calcula algo raro"
    monkeypatch.setattr(jv, "command_queue", Q())
    with pytest.raises(SystemExit):
        jv._command_worker()
    e = errores.recent()[0]
    assert e["origen"] == "ORDEN" and "ZeroDivisionError" in e["error"] and e["orden"] == "calcula algo raro"


def test_informe_por_voz(jv, monkeypatch, tmp_path):
    errores.configure(str(tmp_path), jv._secret_values)
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setattr(jv, "run_system_check", lambda speak_it=True: [{"grupo": "IA", "estado": "ok", "texto": "bien", "arreglo": ""}])
    monkeypatch.setattr(jv, "_open_doc", lambda p: False)
    rec = jv._rec
    rec.clear()
    jv.process_command("genera el informe de errores")
    assert "Informes" in rec.said()
    files = list((tmp_path / "Informes").iterdir())
    assert len(files) == 1 and "INFORME DE JARVIS" in files[0].read_text(encoding="utf-8")
    rec.clear()
    jv.process_command("¿has tenido errores?")
    assert "errores" in rec.said()


def test_revision_de_conexiones(jv, monkeypatch):
    monkeypatch.setitem(jv.settings, "whatsapp_phone", "+57300")
    monkeypatch.setitem(jv.settings, "whatsapp_apikey", "")
    monkeypatch.setitem(jv.settings, "classroom_client_id", "cid")
    monkeypatch.setitem(jv.settings, "classroom_refresh", "")
    monkeypatch.setitem(jv.settings, "sync_folder", "/no/existe")
    items = jv.extra_checks()
    textos = " ".join(i["texto"] for i in items)
    assert "WhatsApp a medias" in textos and "falta pulsar «Conectar»" in textos and "No encuentro la carpeta" in textos
    assert any(i["grupo"] == "Errores" for i in items)
