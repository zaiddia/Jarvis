"""12.50: Estudio de cine. De una idea a una película corta: guion por escenas, personajes y escenarios con una ficha fija
(se repite igual en cada escena, así no cambian de cara ni de ropa), instrucciones listas para pegar en Google Flow o Meta
Vibes, y el montaje final (clips en orden + narración + subtítulos + música opcional) con ffmpeg.

Funciones puras: sin Jarvis, sin red. El montaje recibe la ruta de ffmpeg.
"""
import html
import json
import os
import re
import subprocess

MAX_SCENES = 20
CLIP_EXT = (".mp4", ".mov", ".webm", ".mkv", ".m4v")
W, H, FPS = 1280, 720, 30


def prompt(idea, curso="", escenas=8, estilo=""):
    return (
        "Eres guionista y director de cortometrajes educativos. Escribe una película corta a partir de esta idea"
        + (f" para estudiantes de {curso}" if curso else "") + f": «{idea}».\n"
        f"Haz {escenas} escenas de 5 a 8 segundos (cada una será un clip de video generado con IA)."
        + (f" Estilo visual pedido: {estilo}." if estilo else "") + "\n"
        "Reglas:\n"
        "- Los personajes y escenarios llevan una FICHA visual fija y muy concreta (edad, cara, pelo, ropa con colores, rasgos "
        "únicos; para escenarios: lugar, luz, colores, época). La ficha se copiará igual en cada escena: no la cambies.\n"
        "- Máximo 3 personajes y 4 escenarios. Nada de personajes famosos, marcas ni obras con derechos de autor.\n"
        "- Cada escena: qué pasa (una acción visible), qué personajes salen, en qué escenario, el plano de cámara "
        "(plano general, medio, primer plano, travelling…), una frase corta de narración en español (la dice el narrador) "
        "y, si hace falta, un diálogo corto.\n"
        "- Apto para el colegio: sin violencia gráfica ni nada inapropiado.\n"
        "Responde SOLO con JSON: {\"titulo\": str, \"sinopsis\": str, \"estilo_visual\": str, "
        "\"personajes\": [{\"nombre\": str, \"ficha\": str}], \"escenarios\": [{\"nombre\": str, \"ficha\": str}], "
        "\"escenas\": [{\"titulo\": str, \"escenario\": str, \"personajes\": [str], \"accion\": str, \"camara\": str, "
        "\"narracion\": str, \"dialogo\": str, \"segundos\": int}]}")


def _t(v, n=400):
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def clean(d):
    """Valida el guion de la IA. Lanza ValueError si no sirve."""
    if not isinstance(d, dict):
        raise ValueError("la IA no devolvió un guion")
    pers = [{"nombre": _t(p.get("nombre"), 40), "ficha": _t(p.get("ficha"), 500)} for p in d.get("personajes") or []
            if isinstance(p, dict) and _t(p.get("nombre"))][:3]
    esc = [{"nombre": _t(p.get("nombre"), 60), "ficha": _t(p.get("ficha"), 500)} for p in d.get("escenarios") or []
           if isinstance(p, dict) and _t(p.get("nombre"))][:4]
    scenes = []
    for i, s in enumerate(d.get("escenas") or []):
        if not isinstance(s, dict) or not _t(s.get("accion")):
            continue
        try:
            secs = int(s.get("segundos") or 6)
        except (TypeError, ValueError):
            secs = 6
        scenes.append({"n": len(scenes) + 1, "titulo": _t(s.get("titulo"), 80) or f"Escena {i + 1}",
                       "escenario": _t(s.get("escenario"), 60), "personajes": [_t(x, 40) for x in s.get("personajes") or [] if _t(x)][:3],
                       "accion": _t(s.get("accion"), 500), "camara": _t(s.get("camara"), 80), "narracion": _t(s.get("narracion"), 300),
                       "dialogo": _t(s.get("dialogo"), 300), "segundos": max(4, min(10, secs))})
    scenes = scenes[:MAX_SCENES]
    if not scenes:
        raise ValueError("el guion no trae escenas")
    return {"titulo": _t(d.get("titulo"), 100) or "Mi película", "sinopsis": _t(d.get("sinopsis"), 600),
            "estilo_visual": _t(d.get("estilo_visual"), 200) or "animación 3D estilo película familiar, colores vivos",
            "personajes": pers, "escenarios": esc, "escenas": scenes}


def _ficha(items, name):
    low = name.lower()
    return next((x["ficha"] for x in items if x["nombre"].lower() == low), "") or next(
        (x["ficha"] for x in items if low and (low in x["nombre"].lower() or x["nombre"].lower() in low)), "")


def image_prompt(g, sc):
    """La instrucción de la imagen de la escena, con las fichas copiadas tal cual (personajes consistentes)."""
    parts = [f"Estilo: {g['estilo_visual']}."]
    place = _ficha(g["escenarios"], sc["escenario"])
    parts.append(f"Escenario: {sc['escenario']}" + (f" — {place}" if place else "") + ".")
    for p in sc["personajes"]:
        f = _ficha(g["personajes"], p)
        parts.append(f"Personaje {p}" + (f": {f}" if f else "") + ".")
    parts.append(f"Momento: {sc['accion']}")
    if sc["camara"]:
        parts.append(f"Plano: {sc['camara']}.")
    parts.append("Formato horizontal 16:9, sin texto ni letreros en la imagen.")
    return " ".join(parts)


def anim_prompt(g, sc):
    """La instrucción para animar la escena (Flow: Omni Flash/Veo; Meta Vibes)."""
    txt = f"{image_prompt(g, sc)} Movimiento: {sc['accion']}"
    if sc["camara"]:
        txt += f" Cámara: {sc['camara']}."
    if sc["dialogo"]:
        txt += f" Diálogo en español: {sc['dialogo']}"
    txt += f" Duración: {sc['segundos']} segundos. Mantén exactamente la misma apariencia de los personajes."
    return txt


def project_text(g):
    out = [g["titulo"].upper(), "", g["sinopsis"], "", f"Estilo visual: {g['estilo_visual']}", "", "PERSONAJES"]
    out += [f"- {p['nombre']}: {p['ficha']}" for p in g["personajes"]]
    out += ["", "ESCENARIOS"] + [f"- {e['nombre']}: {e['ficha']}" for e in g["escenarios"]] + [""]
    for sc in g["escenas"]:
        out += [f"ESCENA {sc['n']}: {sc['titulo']} ({sc['segundos']} s)", f"Narración: {sc['narracion']}",
                f"Imagen: {image_prompt(g, sc)}", f"Animación: {anim_prompt(g, sc)}", ""]
    out += ["CÓMO TERMINARLA", "1. Pega cada «Animación» en Google Flow (o la «Imagen» y luego anímala) o en Meta Vibes.",
            "2. Descarga cada clip a la carpeta «clips» de este proyecto con su número: escena 1, escena 2…",
            "3. Dile a Jarvis «arma la película» y la une con narración y subtítulos."]
    return "\n".join(out)


def project_html(g, clips_dir=""):
    """Página con un botón «Copiar» en cada instrucción (se abre en el navegador, sin internet)."""
    e = html.escape

    def block(label, text, i):
        return (f'<div class="b"><div class="h"><b>{label}</b><button onclick="cp({i})">Copiar</button></div>'
                f'<textarea id="t{i}" readonly>{e(text)}</textarea></div>')
    rows, k = [], 0
    for sc in g["escenas"]:
        rows.append(f'<section><h2>Escena {sc["n"]}: {e(sc["titulo"])} <small>{sc["segundos"]} s</small></h2>'
                    f'<p class="n">Narración: {e(sc["narracion"])}</p>')
        rows.append(block("Para animar (Flow o Vibes)", anim_prompt(g, sc), k))
        rows.append(block("Solo la imagen", image_prompt(g, sc), k + 1))
        rows.append("</section>")
        k += 2
    fichas = "".join(f"<li><b>{e(p['nombre'])}</b>: {e(p['ficha'])}</li>" for p in g["personajes"] + g["escenarios"])
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><title>{e(g['titulo'])}</title><style>
body{{font-family:system-ui,Segoe UI,sans-serif;max-width:900px;margin:24px auto;padding:0 16px;background:#0f1420;color:#e8edf5}}
h1{{margin-bottom:4px}}section{{background:#182031;border-radius:12px;padding:12px 16px;margin:14px 0}}
.b{{margin:8px 0}}.h{{display:flex;justify-content:space-between;align-items:center}}
textarea{{width:100%;min-height:90px;background:#0b0f18;color:#e8edf5;border:1px solid #2c3a55;border-radius:8px;padding:8px;font:14px/1.4 system-ui}}
button{{background:#f5b942;border:0;border-radius:8px;padding:6px 14px;font-weight:600;cursor:pointer}}.n{{color:#9fb3d1}}
small{{color:#9fb3d1;font-weight:400}}.ok{{background:#5fd38d}}</style></head><body>
<h1>{e(g['titulo'])}</h1><p>{e(g['sinopsis'])}</p>
<p><b>Cómo terminarla:</b> copia «Para animar» en Google Flow (labs.google/flow) o en Meta Vibes, descarga cada clip a la carpeta
<code>{e(clips_dir or 'clips')}</code> con su número (escena 1, escena 2…) y dile a Jarvis «arma la película».</p>
<details><summary>Fichas de personajes y escenarios</summary><ul>{fichas}</ul></details>
{''.join(rows)}
<script>function cp(i){{var t=document.getElementById('t'+i);t.select();var ok=function(){{var b=t.parentNode.querySelector('button');
b.textContent='Copiado';b.className='ok';setTimeout(function(){{b.textContent='Copiar';b.className=''}},1500)}};
if(navigator.clipboard){{navigator.clipboard.writeText(t.value).then(ok,function(){{document.execCommand('copy');ok()}})}}
else{{document.execCommand('copy');ok()}}}}</script></body></html>"""


def clip_order(files, n_scenes):
    """Los clips en el orden de las escenas: por el número en el nombre («escena 3», «03.mp4»); los que no lo tienen,
    después, por fecha. files: [(ruta, fecha)]. → [ruta]."""
    numbered, rest = {}, []
    for path, mtime in files:
        name = os.path.splitext(os.path.basename(path))[0].lower()
        m = re.search(r"(?:escena|scene|clip|toma)\s*[_-]?\s*(\d{1,2})\b", name) or re.fullmatch(r"\D*?(\d{1,2})", name)
        k = int(m.group(1)) if m else 0
        if 1 <= k <= max(n_scenes, MAX_SCENES) and k not in numbered:
            numbered[k] = path
        else:
            rest.append((mtime, path))
    out = [numbered[k] for k in sorted(numbered)]
    out += [p for _, p in sorted(rest)]
    return out


def media_info(ffmpeg, path):
    """(segundos, ¿trae audio?) leyendo lo que dice ffmpeg del archivo."""
    r = subprocess.run([ffmpeg, "-hide_banner", "-i", path], capture_output=True, text=True, errors="replace",
                       creationflags=0x08000000 if os.name == "nt" else 0, timeout=60)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr)
    secs = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0
    return secs, bool(re.search(r"Stream #\S+.*Audio:", r.stderr))


def scene_cmd(ffmpeg, clip, clip_secs, clip_audio, narr, narr_secs, out, music_vol=0.3):
    """El comando ffmpeg de una escena: video a 1280×720 y 30 cuadros, la narración encima (el sonido del clip, más bajo);
    si la narración es más larga que el clip, se congela el último cuadro."""
    dur = max(clip_secs, (narr_secs + 0.4) if narr else 0.0, 1.0)
    extra = max(0.0, dur - clip_secs)
    v = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={FPS}"
         + (f",tpad=stop_mode=clone:stop_duration={extra:.2f}" if extra > 0.05 else "") + ",format=yuv420p[v]")
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-i", clip]
    if narr:
        cmd += ["-i", narr]
    else:
        cmd += ["-f", "lavfi", "-t", f"{dur:.2f}", "-i", "anullsrc=r=44100:cl=stereo"]
    a1 = "[1:a]aformat=sample_rates=44100:channel_layouts=stereo,apad[n]"
    if clip_audio:
        a = f"{a1};[0:a]aformat=sample_rates=44100:channel_layouts=stereo,volume={music_vol if narr else 1.0},apad[c];[n][c]amix=inputs=2:duration=longest:normalize=0[a]"
    else:
        a = a1.replace("[n]", "[a]")
    cmd += ["-filter_complex", f"{v};{a}", "-map", "[v]", "-map", "[a]", "-t", f"{dur:.2f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac", "-b:a", "160k", "-ar", "44100", out]
    return cmd, dur


def srt(entries):
    """entries: [(inicio, fin, texto)] → texto .srt."""
    def ts(s):
        ms = int(round(s * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    return "\n".join(f"{i}\n{ts(a)} --> {ts(b)}\n{t}\n" for i, (a, b, t) in enumerate(entries, 1) if t)


def safe_name(text):
    s = re.sub(r"[^\w áéíóúñÁÉÍÓÚÑ-]", "", str(text or "")).strip()
    return re.sub(r"\s+", " ", s)[:60] or "Pelicula"


def save_project(g, folder):
    os.makedirs(os.path.join(folder, "clips"), exist_ok=True)
    with open(os.path.join(folder, "proyecto.json"), "w", encoding="utf-8") as f:
        json.dump(g, f, ensure_ascii=False, indent=1)
    with open(os.path.join(folder, "guion y escenas.txt"), "w", encoding="utf-8") as f:
        f.write(project_text(g))
    page = os.path.join(folder, "escenas para copiar.html")
    with open(page, "w", encoding="utf-8") as f:
        f.write(project_html(g, os.path.join(folder, "clips")))
    return page
