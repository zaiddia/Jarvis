"""Pruebas de la 12.58: «¿qué canción está sonando?» (controles multimedia de Windows) y «llama a Juan» (Enlace Móvil)."""
import skills

OUT = ("@@Spotify.exe|Paused|Otra|Alguien|\n@@Spotify.exe|Playing|Tusa|Karol G, Nicki Minaj|KG0516\n"
       "@@MSEdge|Paused|Shakira - Acróstico - YouTube||\nbasura")


def test_parse_que_suena():
    assert skills.parse("¿Qué canción está sonando?") == ("que_suena", {})
    assert skills.parse("cómo se llama esta canción") == ("que_suena", {})
    assert skills.parse("quién canta esta canción") == ("que_suena", {})
    assert skills.parse("qué suena ahora") == ("que_suena", {})
    i = skills.parse_now_playing(OUT)
    assert i == {"app": "Spotify", "playing": True, "titulo": "Tusa", "artista": "Karol G, Nicki Minaj", "album": "KG0516"}
    assert skills.now_playing_text(i) == "Está sonando «Tusa» de Karol G, Nicki Minaj en Spotify."
    p = skills.parse_now_playing("@@MSEdge|Paused|Shakira - Acróstico - YouTube||")
    assert skills.now_playing_text(p) == "Está en pausa «Shakira - Acróstico» en Edge. Di «pausa» para que siga."
    assert skills.parse_now_playing("") is None and "no escucho el audio" in skills.now_playing_text(None)


def test_que_suena_corre(monkeypatch):
    class R:
        stdout = OUT.encode("utf-8")
    monkeypatch.setattr(skills.subprocess, "run", lambda *a, **k: R())
    assert "Tusa" in skills.REGISTRY["que_suena"].fn()


def test_parse_llamar():
    assert skills.parse("llama a Juan") == ("llamar", {"contacto": "Juan"})
    assert skills.parse("llámale a mi mamá") == ("llamar", {"contacto": "mamá"})
    assert skills.parse("haz una llamada a Pedro") == ("llamar", {"contacto": "Pedro"})
    assert skills.parse("llama al +57 300 123 4567") == ("llamar", {"contacto": "+57 300 123 4567"})
    assert skills.parse("llama a Juan por WhatsApp") is None
    assert skills.parse("llama la atención a 7B") is None
    assert skills.REGISTRY["llamar"].dangerous                     # siempre pregunta antes


def test_llamar_corre(monkeypatch):
    opened = []
    monkeypatch.setitem(skills._ctx, "contacts", lambda: "Juan = +573001112233\nMamá = +573009998877")
    monkeypatch.setattr(skills.os, "startfile", lambda u: opened.append(u), raising=False)
    assert "Llamando a Juan" in skills.REGISTRY["llamar"].fn(contacto="Juan")
    assert opened == ["tel:+573001112233"]
    assert "+573009998877" in skills.REGISTRY["llamar"].confirm_text({"contacto": "mamá"})
    try:
        skills.REGISTRY["llamar"].fn(contacto="Rodolfo")
        assert False
    except skills.SkillError as e:
        assert "No tengo el número" in str(e)


def test_llamar_en_jarvis(jv, monkeypatch):
    monkeypatch.setitem(skills._ctx, "contacts", lambda: "Juan = +573001112233")
    jv._rec.clear()
    jv.process_command("llama a Juan")
    assert jv._rec.who() == "confirmar:llamar" and "+573001112233" in jv._rec.said()
    jv._rec.clear()
    jv.process_command("llama a Rodolfo")
    assert "No tengo el número de «Rodolfo»" in jv._rec.said() and not jv._rec.other
    assert "Enlace Móvil" in jv.remote_blocked("llamar")


def test_que_suena_en_jarvis(jv):
    jv._rec.clear()
    jv.process_command("¿qué canción está sonando?")
    assert jv._rec.who() == "skill:que_suena" and not jv._rec.ai
