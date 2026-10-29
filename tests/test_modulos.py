"""Pruebas de los módulos sueltos (sin la interfaz): horarios de rutinas, memoria y actualizaciones."""
import datetime
import os
import tempfile

import pytest

import actualizar
import perfil
import rutinas


# ----------------------------------------------------------------------------- rutinas: «cuándo»
@pytest.mark.parametrize("texto,esperado", [
    ("07:30", "07:30"),
    ("7:30 de lunes a viernes", "07:30 lun-vie"),
    ("lun-vie 07:30", "07:30 lun-vie"),
    ("7 de la mañana entre semana", "07:00 lun-vie"),
    ("9 pm", "21:00"),
    ("9:45 p.m.", "21:45"),
    ("12 am", "00:00"),
    ("12 de la noche", "00:00"),
    ("8:15 los fines de semana", "08:15 sab,dom"),
    ("6 de la tarde los martes y jueves", "18:00 mar,jue"),
    ("10:00 todos los días", "10:00"),
    ("al iniciar", "al iniciar"),
    ("al encender el equipo", "al iniciar"),
    ("al volver", "al volver"),
    ("cuando regrese", "al volver"),
])
def test_cuando(texto, esperado):
    w = rutinas.parse_when(texto)
    assert w and w["text"] == esperado


@pytest.mark.parametrize("texto", ["", "25:00", "cuando quieras", "7:75"])
def test_cuando_no_valido(texto):
    assert rutinas.parse_when(texto) is None


def test_rutina_a_su_hora():
    rutinas.routines[:] = [{"nombre": "Buenos días", "frases": [], "pasos": ["decir hola"], "cuando": "07:30 lun-vie"}]
    lunes = datetime.datetime(2026, 11, 2, 7, 31)          # lunes
    sabado = datetime.datetime(2026, 11, 7, 7, 31)
    assert [r["nombre"] for r in rutinas.due(lunes, {})] == ["Buenos días"]
    assert rutinas.due(lunes, {"Buenos días": "2026-11-02"}) == []           # ya se lanzó hoy
    assert rutinas.due(sabado, {}) == []                                     # no toca el sábado
    assert rutinas.due(lunes.replace(hour=7, minute=45), {}) == []           # pasaron más de 10 minutos
    assert rutinas.due(lunes.replace(hour=7, minute=29), {}) == []           # aún no


def test_rutina_guarda_cuando():
    d = tempfile.mkdtemp()
    rutinas.configure(d)
    r = rutinas.upsert("Bienvenida", "", "decir hola\nqué tengo pendiente", cuando="al volver")
    assert r["cuando"] == "al volver"
    assert [x["nombre"] for x in rutinas.with_kind("volver")] == ["Bienvenida"]
    with pytest.raises(ValueError):
        rutinas.upsert("Mala", "", "decir hola", cuando="cuando quieras")


# ----------------------------------------------------------------------------- memoria
@pytest.fixture
def memoria():
    perfil.configure(tempfile.mkdtemp())
    perfil.clear()
    return perfil


@pytest.mark.parametrize("frase", [
    "mi hermana se llama Ana", "me gusta el vallenato", "tengo dos gatos", "mi perro se llama Rocky",
    "trabajo en el colegio San José", "mi color favorito es el azul", "soy alérgico al maní", "prefiero respuestas cortas",
])
def test_detecta(memoria, frase):
    assert memoria.detect(frase)


@pytest.mark.parametrize("frase", [
    "me gusta esto", "me gusta esta canción", "llama a mamá", "¿cómo se llama mi hermana?", "abre spotify",
    "recuérdame en 5 minutos", "me gusta",
])
def test_no_detecta(memoria, frase):
    assert memoria.detect(frase) is None


def test_corrige_y_contesta(memoria):
    memoria.add("mi hermana se llama Ana")
    memoria.add("mi perro se llama Rocky")
    f = memoria.add("mi hermana se llama Laura")
    assert f["corrige"]
    assert len(memoria.facts) == 2
    assert memoria.answer("¿cómo se llama mi hermana?") == "Tu hermana se llama Laura."
    assert "Rocky" in memoria.answer("¿cómo se llama mi perro?")
    assert "no me lo has dicho" in memoria.answer("¿cómo se llama mi abuela?").lower()
    assert memoria.answer("¿cuál es la capital de Francia?") is None


def test_segunda_persona():
    assert perfil.to_second_person("Mi hermana se llama Ana") == "Tu hermana se llama Ana"
    assert perfil.to_second_person("Trabajo en el colegio") == "Trabajas en el colegio"
    assert perfil.to_second_person("mi trabajo es lejos") == "tu trabajo es lejos"


def test_relevante(memoria):
    for i in range(60):
        memoria.add(f"me gusta la fruta número {i}")
    memoria.add("mi hermana se llama Ana")
    for i in range(10):
        memoria.add(f"prefiero el color {i}")
    rel = [f["texto"] for f in memoria.relevant("¿qué le regalo a mi hermana?")]
    assert "mi hermana se llama Ana" in rel
    assert len(rel) <= 32


# ----------------------------------------------------------------------------- actualizaciones
def test_verifica_descarga(tmp_path):
    p = tmp_path / "a.zip"
    p.write_bytes(b"hola jarvis")
    good = actualizar.sha256_of(str(p))
    actualizar.verify(str(p), {"size": 11, "sha256": good})
    with pytest.raises(actualizar.UpdateError):
        actualizar.verify(str(p), {"size": 12, "sha256": good})
    with pytest.raises(actualizar.UpdateError):
        actualizar.verify(str(p), {"size": 11, "sha256": "0" * 64})
    actualizar.verify(str(p), {"size": 0, "sha256": ""})     # sin datos publicados: no se puede comprobar


def test_versiones():
    assert actualizar.parse_version("v6.8") > actualizar.parse_version("6.7")
    assert actualizar.parse_version("6.10") > actualizar.parse_version("6.9")
    assert not actualizar.parse_version("6.7") > actualizar.parse_version("v6.7")
