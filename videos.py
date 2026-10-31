"""Quiz desde un video de YouTube (11.5). Lógica pura, sin Jarvis.

Se lee la transcripción (subtítulos) del video: de la página de YouTube o, si no se puede, la que pegues (en YouTube:
«…más» › «Mostrar transcripción», copiar). Con ella se arma el quiz con el minuto exacto de cada respuesta y una guía
de pausas para ver el video en clase.
"""
import datetime
import html
import json
import os
import re

_ID = re.compile(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/|live/)|youtu\.be/)([A-Za-z0-9_-]{11})")


def video_id(text):
    m = _ID.search(str(text or ""))
    return m.group(1) if m else None


def mmss(sec):
    sec = int(sec)
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}" if sec >= 3600 else f"{sec // 60:02d}:{sec % 60:02d}"


def caption_tracks(page_html):
    """Las pistas de subtítulos que anuncia la página del video: [{"lang", "url", "auto"}]."""
    m = re.search(r'"captionTracks":(\[.*?\])', page_html)
    if not m:
        return []
    try:
        tracks = json.loads(m.group(1))
    except ValueError:
        return []
    out = []
    for t in tracks:
        url = t.get("baseUrl", "")
        if url.startswith("https://"):
            out.append({"lang": t.get("languageCode", ""), "url": url, "auto": t.get("kind") == "asr"})
    return out


def pick_track(tracks):
    """Español primero (escrito por personas antes que automático), luego cualquiera."""
    order = sorted(tracks, key=lambda t: (not t["lang"].startswith("es"), t["auto"]))
    return order[0] if order else None


def title_of(page_html):
    m = re.search(r"<title>(.*?)</title>", page_html, re.S)
    return html.unescape(re.sub(r"\s*-\s*YouTube\s*$", "", m.group(1)).strip()) if m else ""


def parse_timedtext(raw):
    """El XML (o JSON «json3») de los subtítulos → [(segundo, texto)]."""
    out = []
    raw = str(raw or "")
    if raw.lstrip().startswith("{"):
        try:
            for ev in json.loads(raw).get("events", []):
                txt = "".join(s.get("utf8", "") for s in ev.get("segs", []) or []).strip()
                if txt:
                    out.append((ev.get("tStartMs", 0) / 1000.0, txt))
        except ValueError:
            return []
        return out
    for m in re.finditer(r'<(?:text|p)\s+[^>]*?(?:start|t)="([\d.]+)"[^>]*>(.*?)</(?:text|p)>', raw, re.S):
        start = float(m.group(1))
        if "t=" in m.group(0)[:20] and "start" not in m.group(0)[:30]:
            start /= 1000.0
        txt = html.unescape(re.sub(r"<[^>]+>", "", html.unescape(m.group(2)))).replace("\n", " ").strip()
        if txt:
            out.append((start, txt))
    return out


def parse_pasted(text):
    """La transcripción pegada de YouTube («0:12» en una línea y el texto en la siguiente, o en la misma)."""
    out, cur = [], None
    for line in str(text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\s*(.*)$", line)
        if m:
            cur = int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
            if m.group(4):
                out.append((cur, m.group(4)))
        elif cur is not None:
            out.append((cur, line))
    if not out and len(str(text).split()) > 40:            # sin marcas de tiempo: igual sirve, sin minutos
        out = [(0, str(text).strip())]
    return out


def as_prompt_text(segs, limit=14000):
    """«[01:23] texto…» agrupado cada ~20 s, recortado al límite."""
    lines, block, t0 = [], [], None
    for s, txt in segs:
        if t0 is not None and s - t0 >= 20:
            lines.append(f"[{mmss(t0)}] " + " ".join(block))
            block, t0 = [], None
        if t0 is None:
            t0 = s
        block.append(txt)
    if block:
        lines.append(f"[{mmss(t0 or 0)}] " + " ".join(block))
    out = "\n".join(lines)
    return out[:limit]


def quiz_prompt(titulo, transcript, n=8, grado="", asignatura=""):
    return (f"Esta es la transcripción con marcas de tiempo de un video educativo («{titulo}»). Crea un quiz de {n} preguntas de opción "
            f"múltiple (4 opciones, una correcta) para estudiantes{(' de grado ' + grado) if grado else ''}{(' de ' + asignatura) if asignatura else ''} "
            "en Colombia, SOLO con lo que dice el video; cada pregunta con el «minuto» (mm:ss) donde está la respuesta y una explicación corta. "
            "Además, una guía de 3 a 5 pausas para verlo en clase: el minuto y una pregunta para hacerle al curso en esa pausa, y un resumen de "
            'tres frases. Responde SOLO con JSON: {"titulo": str, "tema": str, "resumen": str, "preguntas": [{"enunciado": str, "opciones": '
            '[str, str, str, str], "respuesta": "a"|"b"|"c"|"d", "explicacion": str, "minuto": "mm:ss"}], "pausas": [{"minuto": "mm:ss", '
            f'"pregunta": str}}]}}\nTranscripción:\n{transcript}')


def clean_quiz(d, n=8):
    if not isinstance(d, dict):
        raise ValueError("el quiz no vino en el formato esperado")
    qs = []
    for q in (d.get("preguntas") or [])[: n + 4]:
        if not isinstance(q, dict):
            continue
        ops = [str(o)[:300] for o in (q.get("opciones") or [])][:4]
        r = str(q.get("respuesta", "")).lower()[:1]
        if len(ops) == 4 and r in "abcd" and r and str(q.get("enunciado", "")).strip():
            mi = re.match(r"^\s*(\d{1,2}:\d{2}(?::\d{2})?)", str(q.get("minuto", "")))
            qs.append({"enunciado": str(q["enunciado"])[:600], "opciones": ops, "respuesta": r, "explicacion": str(q.get("explicacion", ""))[:400],
                       "minuto": mi.group(1) if mi else ""})
    if len(qs) < 2:
        raise ValueError("el quiz no trae preguntas válidas")
    pausas = [{"minuto": str(p.get("minuto", ""))[:8], "pregunta": str(p.get("pregunta", ""))[:300]} for p in (d.get("pausas") or [])
              if isinstance(p, dict) and p.get("pregunta")][:6]
    return {"titulo": str(d.get("titulo") or "Quiz del video")[:120], "tema": str(d.get("tema") or "")[:120], "resumen": str(d.get("resumen") or "")[:800],
            "preguntas": qs[:n], "pausas": pausas}


def docx(q, url, out_dir, Document, docente="", curso=""):
    from docx.shared import Pt
    doc = Document()
    doc.add_heading(q["titulo"], 0)
    doc.add_paragraph(" · ".join(x for x in (curso, docente) if x))
    if url:
        doc.add_paragraph(f"Video: {url}")
    if q["resumen"]:
        doc.add_paragraph(q["resumen"])
    doc.add_heading("Preguntas", 1)
    for i, p in enumerate(q["preguntas"], 1):
        para = doc.add_paragraph()
        para.add_run(f"{i}. ").bold = True
        para.add_run(p["enunciado"])
        for letter, o in zip("abcd", p["opciones"]):
            doc.add_paragraph(f"   {letter}) {o}")
    if q["pausas"]:
        doc.add_heading("Guía para verlo en clase (pausas)", 1)
        for p in q["pausas"]:
            doc.add_paragraph(f"⏸ {p['minuto']} — {p['pregunta']}", style="List Bullet")
    doc.add_page_break()
    doc.add_heading("Clave (con el minuto del video)", 1)
    for i, p in enumerate(q["preguntas"], 1):
        r = doc.add_paragraph()
        r.add_run(f"{i}. {p['respuesta']})").bold = True
        r.add_run(f"  [{p['minuto'] or '—'}]  {p['explicacion']}").font.size = Pt(10)
    folder = os.path.join(out_dir, "Material de clase")
    os.makedirs(folder, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|]+', " ", q["titulo"]).strip()[:80] or "Quiz del video"
    path = os.path.join(folder, f"{safe} {datetime.date.today():%Y-%m-%d}.docx")
    doc.save(path)
    return path
