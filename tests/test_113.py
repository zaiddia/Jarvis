"""Pruebas de la 11.3: solucionario paso a paso verificado con SymPy y laboratorio interactivo."""
import json
import os

import pytest

import time

import verificar


def _wait(jv, text):
    for _ in range(300):
        if text in jv._rec.said():
            return
        time.sleep(0.02)


def test_verificacion_con_sympy():
    assert verificar.check({"tipo": "ecuacion", "expr": "x^2 - 5x + 6 = 0", "resultado": "x = 2 o x = 3"})["ok"] is True
    bad = verificar.check({"tipo": "ecuacion", "expr": "2x + 3 = 7", "resultado": "x = 5"})
    assert bad["ok"] is False and bad["correcto"] == "x = 2"
    assert verificar.check({"tipo": "expresion", "expr": "3/4 + 1/2", "resultado": "5/4"})["ok"]
    assert verificar.check({"tipo": "expresion", "expr": "3/4 + 1/2", "resultado": "4/6"})["correcto"] == "5/4"
    assert verificar.check({"tipo": "derivada", "expr": "x^3", "resultado": "3x^2"})["ok"]
    assert verificar.check({"tipo": "integral", "expr": "2x", "resultado": "x^2 + C"})["ok"]
    assert verificar.check({"tipo": "sistema", "expr": "x + y = 5; x - y = 1", "resultado": "x = 3, y = 2"})["ok"]
    assert verificar.check({"tipo": "ninguna"})["ok"] is None
    for evil in ("__import__('os').system('x')", "x.__class__", "pi.n()", "open('a')", "lambda: 1"):
        assert verificar.check({"tipo": "expresion", "expr": evil, "resultado": "1"})["ok"] is None       # nunca se ejecuta texto libre
    assert verificar.split_problems("2x+3=7; x^2-5x+6=0") == ["2x+3=7", "x^2-5x+6=0"]


SOL = {"soluciones": [
    {"problema": "2x + 3 = 7", "pasos": ["Restar 3: 2x = 4", "Dividir entre 2: x = 2"], "respuesta": "x = 2",
     "verificacion": {"tipo": "ecuacion", "expr": "2x + 3 = 7", "resultado": "x = 2"}},
    {"problema": "x² − 5x + 6 = 0", "pasos": ["Factorizar: (x − 1)(x − 6)", "x = 1 o x = 6"], "respuesta": "x = 1 o x = 6",
     "verificacion": {"tipo": "ecuacion", "expr": "x^2 - 5x + 6 = 0", "resultado": "x = 1 o x = 6"}},
    {"problema": "Explica qué es una función", "pasos": ["Es una relación…"], "respuesta": "…", "verificacion": {"tipo": "ninguna"}}]}


def test_solucionario_corrige_a_la_ia(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv, "_open_doc", lambda p: False)
    calls = []

    def fake(msgs, **k):
        calls.append(msgs[0]["content"])
        if "hay un error" in msgs[0]["content"]:
            return json.dumps({"pasos": ["Factorizar: (x − 2)(x − 3) = 0", "x = 2 o x = 3"], "respuesta": "x = 2, x = 3"})
        return json.dumps(SOL)
    monkeypatch.setattr(jv, "ai_chat", fake)
    jv._rec.clear()
    jv.process_command("resuelve paso a paso: 2x + 3 = 7; x² − 5x + 6 = 0; explica qué es una función")
    _wait(jv, "Listo el solucionario")
    s = jv._rec.said()
    assert "3 problemas, 1 verificados con SymPy y 1 corregido" in s
    assert any("x = 2, x = 3" in c for c in calls if "hay un error" in c)
    from docx import Document
    path = next(os.path.join(r, f) for r, _, fs in os.walk(tmp_path) for f in fs if f.startswith("Solucionario"))
    text = "\n".join(p.text for p in Document(path).paragraphs)
    assert "✔ Verificado con SymPy" in text and "⚠ Corregido" in text and "(x − 2)(x − 3)" in text


def test_solucionario_del_ultimo_taller(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv, "_open_doc", lambda p: False)
    jv.last_material.update(m={"titulo": "Taller de ecuaciones", "ejercicios": [{"enunciado": "2x + 3 = 7"}]}, kind="taller", curso="7A")
    seen = []
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: seen.append(msgs[0]["content"]) or json.dumps({"soluciones": SOL["soluciones"][:1]}))
    jv._rec.clear()
    jv.process_command("haz el solucionario del taller")
    _wait(jv, "Listo el solucionario")
    assert "1 verificados" in jv._rec.said() and "1. 2x + 3 = 7" in seen[0]


def test_laboratorio(jv, monkeypatch):
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda u, *a, **k: opened.append(u))
    jv._rec.clear()
    jv.process_command("abre el laboratorio de la parábola")
    assert opened[-1].endswith("/lab/parabola") and "parábola" in jv._rec.said()
    jv.process_command("abre el simulador de probabilidad")
    assert opened[-1].endswith("/lab/dados")
    c = jv.app.test_client()
    for name in jv.LABS:
        page = c.get(f"/lab/{name}").get_data(as_text=True)
        assert f'const LAB = "{name}"' in page
    assert "Laboratorio de matemáticas" in c.get("/lab").get_data(as_text=True)
