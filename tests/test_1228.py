"""12.28: historias, cuentos y textos en Word (antes Jarvis decía «no puedo»)."""
import sys

import pytest

import documentos


@pytest.fixture
def gen(jv, monkeypatch, tmp_path):
    g = sys.modules["nucleo.generador"]
    monkeypatch.setitem(jv.settings, "assistant_mode", "general")
    monkeypatch.setitem(jv.state, "ai", "ok")
    got, shown, spoken = [], [], []

    def draft(opts):
        got.append(opts)
        return {"id": "d1", "formato": opts["formato"], "plantilla": opts["plantilla"]}
    monkeypatch.setattr(g, "make_draft", draft)
    monkeypatch.setattr(g, "save_draft", lambda did: {"titulo": "El dragón de la montaña", "texto": "Había una vez un dragón…",
                                                      "ruta": str(tmp_path / "x.docx")})
    monkeypatch.setattr(g.threading, "Thread", lambda target, daemon=True, name="": type("T", (), {"start": lambda s: target()})())
    monkeypatch.setattr(jv, "show", lambda text, origin: shown.append((origin, text)))
    monkeypatch.setattr(jv, "speak", lambda text, *a, **k: spoken.append(text))
    monkeypatch.setitem(g.gen, "busy", False)
    return got, shown, spoken


@pytest.mark.parametrize("frase, plantilla, formato, pedido", [
    ("redacta una historia en Word", "creativo", "word", "redacta una historia"),
    ("escribe una historia de un dragón en word", "creativo", "word", "escribe una historia de un dragón"),
    ("escríbeme un cuento de piratas y guárdalo en word", "creativo", "word", "escríbeme un cuento de piratas"),
    ("crea un documento de word con una historia de amor", "creativo", "word", "crea un documento con una historia de amor"),
    ("redacta un discurso para la graduación en un documento de word", "creativo", "word", "redacta un discurso para la graduación"),
    ("escribe una historia corta en pdf", "creativo", "pdf", "escribe una historia corta"),
    ("hazme un documento sobre el reciclaje", "libre", "word", "hazme un documento sobre el reciclaje"),
    ("redacta una carta para mi jefe en word", "libre", "word", "redacta una carta para mi jefe"),
    ("me puedes escribir un ensayo sobre la paz en word", "creativo", "word", "escribe un ensayo sobre la paz"),   # «me puedes…» → orden
])
def test_textos_en_word(jv, ask, gen, frase, plantilla, formato, pedido):
    got, shown, spoken = gen
    assert ask(frase)[0] == "DOCUMENTOS"
    o = got[-1]
    assert (o["plantilla"], o["formato"], o["pedido"]) == (plantilla, formato, pedido)
    assert o["encabezado"] is False and o["curso"] == ""                    # en modo general, sin membrete del colegio
    if plantilla == "creativo":
        assert shown[-1] == ("DOCUMENTOS", "El dragón de la montaña\n\nHabía una vez un dragón…") and "en el chat" in spoken[-1]


def test_sin_formato_lo_escribe_en_el_chat(jv, ask, gen):
    for f in ("redacta una historia", "escríbeme un poema para mi mamá", "me puedes escribir un cuento de piratas"):
        jv._rec.clear()
        jv.process_command(f)
        assert jv._rec.ai and any(w in jv._rec.ai[-1][0] for w in ("escrib", "escríb", "redacta")) and not gen[0]   # directo a la IA, que ahora sí lo escribe


def test_lo_demas_sigue_igual(jv, ask, gen):
    assert ask("escríbele un correo a la coordinadora diciendo que llego tarde")[0] == "CORREO"
    assert ask("hazme un quiz de fracciones")[0] == "MATERIAL" and ask("crea una presentación sobre el reciclaje")[0] == "DOCUMENTOS"   # 12.36: en modo general no es «para clase»
    assert not gen[0]


def test_la_ia_ya_no_dice_que_no_puede(jv, monkeypatch):
    rule = jv.ACTION_RULE
    assert "escríbelo completo aquí" in rule and "nunca digas que no puede crear archivos de Word" in rule
    assert "o un texto (una historia, un poema, una carta…)" in jv.DEFAULT_SYSTEM_PROMPT
    monkeypatch.setitem(jv.settings, "assistant_mode", "general")
    p = documentos.build_prompt("word", "creativo", "una historia de un dragón")
    assert "escritor y redactor" in p and "docente" not in p and "Texto creativo" in p
    monkeypatch.setitem(jv.settings, "assistant_mode", "docente")
    assert "docente experto" in documentos.build_prompt("word", "informe", "informe del periodo")
    assert documentos.ok_format("creativo", "word") and not documentos.ok_format("creativo", "excel")
