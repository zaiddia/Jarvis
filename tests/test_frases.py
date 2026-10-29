"""Pruebas de comprensión: cada línea de frases.txt dice qué debe hacer Jarvis con una frase.

    frase => skill:volumen            la atiende esa acción del PC
    frase => rutina:Modo clase        lanza esa rutina
    frase => IA                       se la pasa a la inteligencia artificial
    frase => MEMORIA                  la atiende el módulo que responde con ese origen (MEMORIA, TIMER, RUTINA…)
    frase => skill:volumen :: subir   además, lo dicho o los datos de la acción contienen ese texto
    cel: frase => …                   la orden llega desde el celular (Telegram)
Varias respuestas válidas con «|»; «!IA» = cualquiera menos la IA. Las líneas con # son comentarios.
Las líneas se ejecutan en orden: la memoria y las rutinas que se crean sirven a las siguientes.
"""
import os
import re

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))


def _cases():
    out = []
    with open(os.path.join(HERE, "frases.txt"), encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#") or " => " not in line:
                continue
            phrase, expected = line.split(" => ", 1)
            must = ""
            if " :: " in expected:
                expected, must = expected.split(" :: ", 1)
            out.append(pytest.param(phrase.strip(), expected.strip(), must.strip(), id=f"{n}: {phrase.strip()[:50]}"))
    return out


def _norm(s):
    import unicodedata
    s = unicodedata.normalize("NFD", str(s).lower())
    return re.sub(r"\s+", " ", "".join(c for c in s if unicodedata.category(c) != "Mn")).strip()


@pytest.mark.parametrize("phrase,expected,must", _cases())
def test_frase(ask, jv, phrase, expected, must):
    phone = phrase.startswith("cel: ")
    if phone:
        phrase = phrase[5:]
    who, said = ask(phrase, phone=phone)
    options = [o.strip() for o in expected.split("|")]
    ok = any(o == who or (o.startswith("!") and who != o[1:]) or (o.endswith("*") and who.startswith(o[:-1])) for o in options)
    detail = said + " " + " ".join(str(a) for _, a in jv._rec.skills)
    assert ok, f"«{phrase}»: esperaba {expected}, la atendió {who} — dijo: {said[:160]}"
    if must:
        assert _norm(must) in _norm(detail), f"«{phrase}»: debía contener «{must}», dijo: {said[:200]} {jv._rec.skills}"
