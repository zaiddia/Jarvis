"""Ensayar la clase con estudiantes simulados (12.0). Lógica pura, sin Jarvis.

Antes de una clase difícil, Jarvis simula 4 o 5 estudiantes con los errores típicos de ESE curso (sacados del mapa de
errores de los procedimientos y de las notas reales, sin nombres reales: a la IA solo le llegan perfiles). Te hacen
preguntas y se equivocan como lo harían ellos; al final, un informe con las confusiones que van a aparecer y cómo
anticiparlas.
"""
import re

NAMES = ["Sofía", "Mateo", "Valentina", "Samuel", "Isabella"]
VOICES = ["es-CO-SalomeNeural", "es-MX-JorgeNeural", "es-MX-DaliaNeural", "es-CO-GonzaloNeural", "es-AR-ElenaNeural"]
BASE = [
    ("le va bien, termina rápido y se aburre si la explicación es lenta; pregunta «¿y eso para qué sirve?»", "alto"),
    ("tiene dudas pero no se atreve a preguntar; cuando habla, dice «no entendí nada» o da respuestas a medias", "bajo"),
    ("participa mucho, a veces sin pensar; responde rápido y se equivoca por afán", "medio"),
    ("necesita ejemplos concretos de la vida real; se pierde con las letras y los símbolos", "medio"),
    ("se distrae fácil y pregunta cosas fuera de tema, pero si algo le interesa se engancha", "bajo"),
]


def personas(errores=None, promedios=None, n=5):
    """Los perfiles de la clase simulada. errores: [(categoría, descripción, n_estudiantes)] del mapa de errores del curso;
    promedios: lista de promedios reales del curso (solo para la proporción de niveles, nunca con nombres)."""
    out = []
    errs = list(errores or [])
    prom = [p for p in (promedios or []) if p is not None]
    bajo = sum(1 for p in prom if p < 3.0) / len(prom) if prom else 0.3
    for i in range(min(n, len(NAMES))):
        perfil, nivel = BASE[i]
        p = {"nombre": NAMES[i], "voz": VOICES[i], "perfil": perfil, "nivel": nivel, "error": ""}
        if i < len(errs):                                   # el error típico real del curso
            p["error"] = errs[i][1]
        out.append(p)
    if bajo > 0.45 and out:                                 # un curso con muchos en bajo: un perfil más con dificultades
        out[0]["perfil"] = "le cuesta seguir el ritmo; pide que le repitan y confunde los pasos"
        out[0]["nivel"] = "bajo"
    return out


def system_prompt(tema, grado, ps):
    desc = "\n".join(f"- {p['nombre']} (nivel {p['nivel']}): {p['perfil']}" + (f". Su error típico: {p['error']}." if p["error"] else "")
                     for p in ps)
    return f"""Simulas una clase de {grado or 'bachillerato'} en Colombia para que un docente ENSAYE su clase sobre «{tema}».
Los estudiantes son:
{desc}
El docente te dirá lo que explica o pregunta, como si estuviera en el salón. Responde como 1 a 3 de esos estudiantes (los que \
reaccionarían de verdad): con su forma de hablar (jóvenes colombianos, naturales, frases cortas), con sus dudas reales y \
cometiendo SUS errores típicos cuando el tema lo permita (no seas un estudiante perfecto). A veces alguien no entiende y lo \
dice; si el docente explica bien, algún estudiante puede entender («¡ahhh, ya!»). Nunca hables como profesor ni des la clase tú.
Responde SOLO un JSON: {{"intervenciones": [{{"quien": "Sofía", "dice": "…"}}], "nota": "qué confusión apareció (para el informe, o vacío)"}}"""


def clean_turn(d, ps):
    names = {p["nombre"] for p in ps}
    d = d if isinstance(d, dict) else {}
    out = []
    for it in (d.get("intervenciones") or [])[:3]:
        if not isinstance(it, dict):
            continue
        q = str(it.get("quien") or "").strip()
        q = next((n for n in names if n.lower() == q.lower()), None)
        dice = re.sub(r"\s+", " ", str(it.get("dice") or "")).strip()[:400]
        if q and dice:
            out.append({"quien": q, "dice": dice})
    return out, str(d.get("nota") or "").strip()[:200]


def report_prompt(tema, grado, ps, historial, notas):
    hist = "\n".join(f"{h['quien']}: {h['dice']}" for h in historial[-40:])
    return f"""Un docente ensayó su clase de «{tema}» ({grado or 'bachillerato'}) con estudiantes simulados. Esta fue la conversación:
{hist}
Confusiones que se notaron: {'; '.join(n for n in notas if n) or '(ninguna anotada)'}
Escribe un informe CORTO y práctico para el docente. Responde SOLO un JSON:
{{"confusiones": ["las 3 a 5 confusiones que probablemente aparecerán en la clase real"],
 "anticipar": ["cómo anticipar cada una (un ejemplo, una pregunta, una representación…)"],
 "preguntas": ["2 o 3 preguntas difíciles que le harán, con una respuesta breve sugerida"],
 "bien": "lo que el docente hizo bien en el ensayo (una frase)",
 "consejo": "el consejo más importante para la clase de mañana (una frase)"}}"""


def clean_report(d):
    d = d if isinstance(d, dict) else {}
    lst = lambda k, n: [re.sub(r"\s+", " ", str(x)).strip()[:300] for x in (d.get(k) or []) if str(x).strip()][:n]
    return {"confusiones": lst("confusiones", 6), "anticipar": lst("anticipar", 6), "preguntas": lst("preguntas", 4),
            "bien": str(d.get("bien") or "").strip()[:300], "consejo": str(d.get("consejo") or "").strip()[:300]}


def spoken_report(r):
    if not r["confusiones"]:
        return "Terminé el ensayo. " + (r["consejo"] or "")
    t = f"Terminé el ensayo. Lo que probablemente va a confundir: {'; '.join(r['confusiones'][:3])}."
    if r["consejo"]:
        t += f" Mi consejo: {r['consejo']}"
    return t


def docx(tema, curso, r, historial, out_dir, Document):
    import datetime
    import os
    folder = os.path.join(out_dir, "Ensayos de clase")
    os.makedirs(folder, exist_ok=True)
    doc = Document()
    doc.add_heading(f"Ensayo de la clase: {tema}", 1)
    doc.add_paragraph(" · ".join(x for x in (curso, datetime.date.today().strftime("%d/%m/%Y")) if x))
    for title, items in (("Confusiones que van a aparecer", r["confusiones"]), ("Cómo anticiparlas", r["anticipar"]),
                         ("Preguntas difíciles", r["preguntas"])):
        if items:
            doc.add_heading(title, 2)
            for x in items:
                doc.add_paragraph(x, style="List Bullet")
    if r["bien"]:
        doc.add_heading("Lo que funcionó", 2)
        doc.add_paragraph(r["bien"])
    if r["consejo"]:
        doc.add_heading("Para mañana", 2)
        doc.add_paragraph(r["consejo"])
    doc.add_heading("La conversación del ensayo", 2)
    for h in historial:
        p = doc.add_paragraph()
        p.add_run(h["quien"] + ": ").bold = True
        p.add_run(h["dice"])
    name = re.sub(r"[^\w\s-]", "", f"Ensayo {tema} {datetime.datetime.now():%Y-%m-%d %H%M}").strip()[:80]
    path = os.path.join(folder, name + ".docx")
    doc.save(path)
    return path
