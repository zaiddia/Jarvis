"""Pruebas de la 12.50: Estudio de cine (guion con fichas fijas, escenas para copiar y montaje con ffmpeg)."""
import json
import os
import subprocess

import pytest

import cine

G = {"titulo": "La gota viajera", "sinopsis": "Una gota recorre el ciclo del agua.", "estilo_visual": "animación 3D familiar",
     "personajes": [{"nombre": "Gota", "ficha": "gota de agua azul con ojos grandes y bufanda roja"},
                    {"nombre": "Sol", "ficha": "sol sonriente naranja con gafas"}],
     "escenarios": [{"nombre": "Mar", "ficha": "mar turquesa al amanecer"}],
     "escenas": [{"titulo": "Calor", "escenario": "Mar", "personajes": ["Gota", "Sol"], "accion": "El sol calienta a Gota, que sube.",
                  "camara": "plano medio", "narracion": "El sol calienta el mar.", "dialogo": "", "segundos": 30},
                 {"titulo": "Nube", "escenario": "Cielo", "personajes": ["gota"], "accion": "Gota se junta con otras gotas.",
                  "camara": "plano general", "narracion": "Las gotas forman una nube.", "dialogo": "Gota: ¡qué alto!"},
                 {"titulo": "", "accion": ""}]}


def test_guion_y_fichas_fijas():
    g = cine.clean(G)
    assert len(g["escenas"]) == 2 and g["escenas"][0]["segundos"] == 10 and g["escenas"][1]["segundos"] == 6
    p1, p2 = cine.image_prompt(g, g["escenas"][0]), cine.image_prompt(g, g["escenas"][1])
    ficha = "gota de agua azul con ojos grandes y bufanda roja"
    assert ficha in p1 and ficha in p2 and "sol sonriente naranja" in p1 and "mar turquesa" in p1       # la misma ficha siempre
    a = cine.anim_prompt(g, g["escenas"][1])
    assert "Diálogo en español: Gota: ¡qué alto!" in a and "6 segundos" in a and "misma apariencia" in a
    with pytest.raises(ValueError):
        cine.clean({"escenas": []})
    html = cine.project_html(g, "C:/x/clips")
    assert html.count("Copiar</button>") == 4 and "La gota viajera" in html and "<script>" in html
    assert "ESCENA 2: Nube" in cine.project_text(g)


def test_orden_de_los_clips():
    files = [("/c/descarga (2).mp4", 3), ("/c/escena 2.mp4", 9), ("/c/Escena_1.mov", 8), ("/c/otro.mp4", 1), ("/c/03.mp4", 5)]
    assert cine.clip_order(files, 3) == ["/c/Escena_1.mov", "/c/escena 2.mp4", "/c/03.mp4", "/c/otro.mp4", "/c/descarga (2).mp4"]
    assert cine.srt([(0.2, 2.5, "Hola"), (3, 4, "")]).startswith("1\n00:00:00,200 --> 00:00:02,500\nHola")


def _ffmpeg():
    import animar
    return animar.ffmpeg_exe()


@pytest.mark.skipif(not _ffmpeg(), reason="sin ffmpeg")
def test_montaje_real(jv, monkeypatch, tmp_path):
    ff = _ffmpeg()
    g = cine.clean(G)
    folder = tmp_path / "La gota"
    cine.save_project(g, str(folder))
    clips = folder / "clips"
    # dos clips de prueba: uno sin sonido y vertical, otro con sonido
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=360x640:rate=24", "-t", "1.5", str(clips / "escena 1.mp4")], check=True)
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30", "-f", "lavfi", "-i",
                    "sine=frequency=440", "-t", "2", "-shortest", str(clips / "escena 2.mp4")], check=True)

    def synth(text, base):                                                    # «narración» de 2,5 s (más larga que el clip 1)
        p = base + ".wav"
        subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=220", "-t", "2.5", p], check=True)
        return p
    r = jv.cine_assemble(str(folder), synth=synth)
    assert os.path.exists(r["mp4"]) and r["clips"] == 2 and r["voz"] == 2
    secs, audio = cine.media_info(ff, r["mp4"])
    assert audio and 5.0 < secs < 6.5                                         # 2,9 s (congela el final) + 2,9 s
    info = subprocess.run([ff, "-hide_banner", "-i", r["mp4"]], capture_output=True, text=True).stderr
    assert "1280x720" in info and "Subtitle" in info
    assert "El sol calienta el mar." in open(r["srt"], encoding="utf-8").read()


def test_por_voz(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv, "ai_chat", lambda *a, **k: json.dumps(G))
    monkeypatch.setattr(jv, "_open_doc", lambda p: None)
    said = []
    monkeypatch.setattr(jv, "notify", lambda m, o="": said.append(m))
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    jv.cine_state.update(busy=False, last="")
    assert jv._cine_scenes("crea una pelicula de 5 escenas sobre el agua") == 5
    jv._rec.clear()
    jv.process_command("Jarvis, crea una película de 6 escenas sobre el ciclo del agua para quinto")
    assert said and "Lista la película «La gota viajera»" in said[-1]
    folder = jv.cine_last_project()
    assert os.path.exists(os.path.join(folder, "escenas para copiar.html")) and os.path.isdir(os.path.join(folder, "clips"))
    jv._rec.clear()
    jv.process_command("arma la película")                                    # sin clips: lo dice y abre la carpeta
    assert "está vacía" in jv._rec.said()
    jv.cine_state.update(busy=False, last="")
