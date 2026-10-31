"""Guía viva por QR y podcast de repaso (11.4). Lógica pura, sin Jarvis.

· Guía viva: un tema convertido en una guía interactiva para el celular: explicación, ejemplo resuelto paso a paso,
  figura, laboratorio para explorar, tarjetas de memoria y un mini quiz al final que suma a la ruta de dominio.
· Podcast de repaso: un guion de 3 a 5 minutos con dos voces (Laura y Mateo) que conversan sobre el tema; se graba
  con las voces de Edge y queda en MP3.
"""
import datetime
import json
import os
import re
import threading

_lock = threading.Lock()
_path = None
data = {"guias": {}, "podcasts": {}}     # guias: {code: {"curso", "tema", "guia", "creado", "abierta", "lectores": {est: {"ok", "total"}}}}
VOICES = {"Laura": "es-CO-SalomeNeural", "Mateo": "es-CO-GonzaloNeural"}


def configure(config_dir):
    global _path
    _path = os.path.join(config_dir, "guias_vivas.json")
    load()


def load():
    global data
    try:
        with open(_path, encoding="utf-8") as f:
            d = json.load(f)
        data = d if isinstance(d, dict) and "guias" in d else {"guias": {}, "podcasts": {}}
        data.setdefault("podcasts", {})
    except (OSError, ValueError, TypeError):
        data = {"guias": {}, "podcasts": {}}


def save():
    if not _path:
        return
    try:
        with _lock:
            tmp = _path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, _path)
    except OSError:
        pass


# ----------------------------------------------------------------------------- guía viva
def guide_prompt(tema, grado, asignatura="Matemáticas", labs=()):
    return (f"Crea una guía de estudio interactiva para el celular sobre «{tema}» ({asignatura}, grado {grado}, Colombia). Lenguaje claro "
            "y cercano, párrafos cortos, texto plano sin LaTeX (usa x², √9, 3/4). Bloques en orden: 1) explicación (2 a 4 párrafos cortos con un "
            "ejemplo de la vida cotidiana), 2) ejemplo resuelto paso a paso, 3) si ayuda, una figura, 4) tarjetas de memoria (4 a 6), 5) mini "
            "quiz de 4 preguntas de opción múltiple con explicación."
            + (f" Si encaja, agrega un bloque «lab» con uno de estos laboratorios interactivos: {', '.join(labs)}." if labs else "") +
            ' Responde SOLO con JSON: {"titulo": str, "bloques": [{"tipo": "explicacion", "texto": str} | {"tipo": "ejemplo", "enunciado": str, '
            '"pasos": [str], "respuesta": str} | {"tipo": "grafica", "grafica": {…como las figuras: funcion, plano, triangulo, circulo, '
            'rectangulo, barras o torta…}, "pie": str} | {"tipo": "lab", "nombre": str, "texto": str} | {"tipo": "tarjetas", "tarjetas": '
            '[{"frente": str, "reverso": str}]} | {"tipo": "quiz", "preguntas": [{"enunciado": str, "opciones": [str, str, str, str], '
            '"respuesta": "a"|"b"|"c"|"d", "explicacion": str}]}]}')


def clean_guide(d, labs=(), graph_clean=None):
    if not isinstance(d, dict) or not isinstance(d.get("bloques"), list):
        raise ValueError("la guía no vino en el formato esperado")
    out = []
    for b in d["bloques"][:12]:
        if not isinstance(b, dict):
            continue
        t = str(b.get("tipo", "")).lower()
        if t == "explicacion" and str(b.get("texto", "")).strip():
            out.append({"tipo": t, "texto": str(b["texto"]).strip()[:3000]})
        elif t == "ejemplo" and b.get("pasos"):
            out.append({"tipo": t, "enunciado": str(b.get("enunciado", ""))[:600], "pasos": [str(p)[:400] for p in b["pasos"]][:10],
                        "respuesta": str(b.get("respuesta", ""))[:300]})
        elif t == "grafica" and graph_clean:
            g = graph_clean(b.get("grafica"))
            if g:
                out.append({"tipo": t, "grafica": g, "pie": str(b.get("pie", ""))[:200]})
        elif t == "lab" and str(b.get("nombre", "")) in labs:
            out.append({"tipo": t, "nombre": str(b["nombre"]), "texto": str(b.get("texto", ""))[:300]})
        elif t == "tarjetas":
            cs = [{"frente": str(c.get("frente", ""))[:300], "reverso": str(c.get("reverso", ""))[:300]} for c in (b.get("tarjetas") or [])
                  if isinstance(c, dict) and c.get("frente") and c.get("reverso")][:8]
            if cs:
                out.append({"tipo": t, "tarjetas": cs})
        elif t == "quiz":
            qs = []
            for q in (b.get("preguntas") or [])[:6]:
                ops = [str(o)[:200] for o in (q.get("opciones") or [])][:4] if isinstance(q, dict) else []
                r = str(q.get("respuesta", "")).lower()[:1] if isinstance(q, dict) else ""
                if len(ops) == 4 and r in "abcd" and r and str(q.get("enunciado", "")).strip():
                    qs.append({"enunciado": str(q["enunciado"])[:500], "opciones": ops, "respuesta": "abcd".index(r),
                               "explicacion": str(q.get("explicacion", ""))[:400]})
            if qs:
                out.append({"tipo": t, "preguntas": qs})
    if not any(b["tipo"] == "explicacion" for b in out):
        raise ValueError("la guía no trae explicación")
    return {"titulo": str(d.get("titulo") or "")[:120], "bloques": out}


def public_guide(g):
    """La guía para el celular, sin las respuestas del quiz."""
    out = []
    for b in g["bloques"]:
        if b["tipo"] == "quiz":
            out.append({"tipo": "quiz", "preguntas": [{"enunciado": q["enunciado"], "opciones": q["opciones"]} for q in b["preguntas"]]})
        elif b["tipo"] == "grafica":
            out.append({"tipo": "grafica", "pie": b["pie"]})
        else:
            out.append(b)
    return {"titulo": g["titulo"], "bloques": out}


def grade_quiz(g, answers):
    qs = [q for b in g["bloques"] if b["tipo"] == "quiz" for q in b["preguntas"]]
    res = []
    for i, q in enumerate(qs):
        a = answers[i] if i < len(answers) else None
        res.append({"ok": a == q["respuesta"], "correcta": q["respuesta"], "explicacion": q["explicacion"]})
    return res


# ----------------------------------------------------------------------------- podcast
def podcast_prompt(tema, grado, asignatura="Matemáticas", minutos=4):
    words = int(minutos * 140)
    return (f"Escribe el guion de un podcast de repaso de {minutos} minutos (unas {words} palabras) para estudiantes de grado {grado} en "
            f"Colombia sobre «{tema}» ({asignatura}). Dos presentadores jóvenes y amables, Laura y Mateo, conversan: empiezan con una "
            "pregunta curiosa, explican la idea con un ejemplo cotidiano, resuelven un ejercicio en voz alta (diciendo los números con "
            "palabras cuando haga falta, sin símbolos raros), aclaran un error típico y cierran con un reto para pensar. Frases cortas, "
            'naturales para escuchar. Responde SOLO con JSON: {"titulo": str, "lineas": [{"quien": "Laura"|"Mateo", "texto": str}]}')


def clean_script(d):
    lines = []
    for l in (d.get("lineas") or [])[:80] if isinstance(d, dict) else []:
        if isinstance(l, dict) and str(l.get("texto", "")).strip():
            who = "Mateo" if str(l.get("quien", "")).strip().lower().startswith("m") else "Laura"
            txt = re.sub(r"[*_#`]", "", str(l["texto"]).strip())[:900]
            lines.append({"quien": who, "texto": txt})
    if len(lines) < 4:
        raise ValueError("el guion es muy corto")
    return {"titulo": str(d.get("titulo") or "Podcast de repaso")[:120], "lineas": lines}


def podcast_path(out_dir, curso, titulo):
    folder = os.path.join(out_dir, "Podcasts")
    os.makedirs(folder, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|]+', " ", f"{titulo} {curso}").strip()[:90]
    return os.path.join(folder, f"{safe} {datetime.date.today():%Y-%m-%d}.mp3")
