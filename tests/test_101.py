"""Pruebas de la 10.1: las Valoraciones Periódicas de Desempeño calculadas exactamente como en Zeti."""
import pytest

import zeti

# Filas reales de la planilla de Zeti (Trigonometría 10, periodo 1): Conocer, Hacer, Ser, Autoevaluación → Val, VL
FILAS = [((3.5, 3.3, 3.0, 3.5), (1.23, 0.99, 0.90, 0.18), 3.3, "B"),
         ((3.2, 3.0, 3.0, 3.5), (1.12, 0.90, 0.90, 0.18), 3.1, "B"),
         ((4.8, 4.6, 4.6, 4.5), (1.68, 1.38, 1.38, 0.23), 4.7, "S"),
         ((4.4, 4.2, 4.0, 4.0), (1.54, 1.26, 1.20, 0.20), 4.2, "A"),
         ((3.7, 3.7, 3.6, 3.7), (1.30, 1.11, 1.08, 0.19), 3.7, "B"),
         ((3.7, 3.5, 3.6, 3.8), (1.30, 1.05, 1.08, 0.19), 3.6, "B"),
         ((4.7, 4.5, 4.4, 4.0), (1.65, 1.35, 1.32, 0.20), 4.5, "S")]


@pytest.mark.parametrize("notas,partes,val,letra", FILAS)
def test_igual_que_zeti(notas, partes, val, letra):
    ns = [{"actividad": a, "nota": n, "fecha": "2026-03-01"} for a, n in zip(("Quiz", "Taller", "Actitud", "Autoevaluación"), notas)]
    v = zeti.valoracion(ns)
    assert tuple(v["partes"][d] for d in ("conocer", "hacer", "ser", "auto")) == partes
    assert v["val"] == val and v["letra"] == letra and v["faltan"] == []


def test_acumulado_y_lo_que_falta():
    assert zeti.vra(2.5, 2) == 1.5 and zeti.vra(2.2, 2) == 2.4 and zeti.vra(2.9, 2) == 0.3
    assert zeti.vra(3.1, 2) is None and zeti.vra(1.0, 2) == 6.1
    assert zeti.final([4.7, 4.5]) == 3.1


def test_dimensiones_y_escala():
    assert [zeti.infer_dim(x) for x in ("quiz de fracciones", "taller 2", "participación", "autoevaluación", "ser", "nota")] == \
        ["conocer", "hacer", "ser", "auto", "ser", "conocer"]
    assert zeti.infer_dim("quiz", "hacer") == "hacer"                          # la dimensión guardada manda
    assert [zeti.letter(x) for x in (4.5, 4.4, 4.0, 3.9, 3.0, 2.9)] == ["S", "A", "A", "B", "B", "Bj"]
    assert zeti.parse_weights("40, 30, 25, 5")["conocer"] == 40 and zeti.parse_weights("1,2")["conocer"] == 35


def test_pesos_en_ajustes(jv):
    assert jv._validate("zeti_weights", "40 30 25 5") == "40,30,25,5"
    with pytest.raises(ValueError):
        jv._validate("zeti_weights", "40,30,30,5")


def test_nota_por_voz_dice_la_dimension(jv, monkeypatch, tmp_path):
    import seguimiento
    monkeypatch.setattr(seguimiento, "_path", str(tmp_path / "n.json"))
    monkeypatch.setattr(seguimiento, "data", {})
    monkeypatch.setitem(jv.aula.data, "cursos", {"7A": ["Juan Pérez"]})
    jv._rec.clear()
    jv.process_command("ponle 4,5 a juan pérez en el taller de fracciones de 7A")
    assert "Hacer" in jv._rec.said()
