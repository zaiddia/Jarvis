"""Subtítulos .srt (12.25). Lógica pura: de líneas con marca de tiempo a un archivo de subtítulos.

Los tiempos vienen de la IA (frase por frase, «[mm:ss] texto») o de Whisper (exactos). Aquí se limpian, se ordenan,
se les pone duración y se parten las líneas largas.
"""
import re

_STAMP = re.compile(r"^\s*[\[(]?\s*(?:(\d{1,2}):)?(\d{1,3}):(\d{2})(?:[.,]\d+)?\s*[\])]?\s*[-–—:]?\s*(.*\S)\s*$")
MAX_SECS, MIN_SECS, LINE = 7.0, 1.0, 42


def parse_stamped(text, offset=0.0, limit=None):
    """«[01:23] hola a todos» por línea → [(segundo de inicio, texto)]. Descarta marcas imposibles (fuera del trozo o
    que retroceden). offset: dónde empieza este trozo dentro de la grabación."""
    out, last = [], -1.0
    for line in str(text or "").splitlines():
        m = _STAMP.match(line)
        if not m:
            if out and line.strip() and not line.strip().startswith(("```", "#")):
                out[-1] = (out[-1][0], out[-1][1] + " " + line.strip())      # frase que siguió en otra línea
            continue
        t = int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        body = re.sub(r"\s+", " ", m.group(4)).strip()
        if not body or body.lower().strip(" .()") == "nada":
            continue
        if limit is not None and t > limit + 5:
            continue
        if t < last:
            t = last
        last = t
        out.append((offset + t, body))
    return out


def spread(text, start, secs):
    """Sin marcas de tiempo: reparte el texto de ese trozo en frases, proporcional a su largo (aproximado)."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?…])\s+|\n+", str(text or "")) if p.strip()]
    total = sum(len(p) for p in parts) or 1
    out, t = [], float(start)
    for p in parts:
        out.append((t, p))
        t += secs * len(p) / total
    return out


def _wrap(text):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > LINE:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines


def cues(stamped, total=None, ends=None):
    """[(inicio, texto)] → [(inicio, fin, [líneas])]. Cada subtítulo dura hasta el siguiente (máximo 7 s) y lleva como
    mucho 2 líneas de 42 letras; lo que no cabe pasa a otro subtítulo repartiendo el tiempo."""
    stamped = sorted(stamped, key=lambda x: x[0])
    out = []
    for i, (t0, text) in enumerate(stamped):
        nxt = stamped[i + 1][0] if i + 1 < len(stamped) else (total if total and total > t0 else t0 + MAX_SECS)
        end = ends[i] if ends else min(nxt, t0 + MAX_SECS)
        end = max(end, t0 + MIN_SECS)
        if i + 1 < len(stamped):
            end = min(end, max(stamped[i + 1][0], t0 + 0.3))          # nunca pisa al siguiente
        lines = _wrap(re.sub(r"^(?:Persona \d+|Hablante \d+)\s*:\s*", "", text))
        blocks = [lines[k:k + 2] for k in range(0, len(lines), 2)] or [[""]]
        step = (end - t0) / len(blocks)
        for k, blk in enumerate(blocks):
            out.append((t0 + k * step, t0 + (k + 1) * step, blk))
    return [c for c in out if any(c[2])]


def _ts(s):
    ms = int(round(max(0.0, s) * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def to_srt(cs):
    return "\n".join(f"{n}\n{_ts(a)} --> {_ts(b)}\n" + "\n".join(lines) + "\n" for n, (a, b, lines) in enumerate(cs, 1))
