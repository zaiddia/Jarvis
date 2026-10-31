"""Áreas y asignaturas (10.4): un mismo grupo puede tener varias asignaturas tuyas (Matemáticas y Tecnología en 7A).

Las notas de cada asignatura van aparte, como en Zeti: si el curso tiene una sola asignatura tuya, las notas quedan
en el curso («7A»); si tiene varias, en «7A · Tecnología e Informática». La lista de estudiantes es la misma.
"""
import re
import unicodedata

DEFAULT = ("Matemáticas: Matemáticas, Aritmética, Álgebra, Geometría, Estadística, Trigonometría, Cálculo\n"
           "Tecnología e Informática: Tecnología e Informática, Tecnología, Informática, Sistemas")
SEP = " · "
_ALIAS = {"mate": "matematicas", "mates": "matematicas", "matematica": "matematicas", "computacion": "informatica",
          "sistema": "sistemas", "tecno": "tecnologia", "tecnologia e informatica": "tecnologia e informatica"}


def norm(t):
    t = unicodedata.normalize("NFD", str(t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", t)).strip()


def parse(text):
    """«Área: asignatura, asignatura» por línea → [{"area", "asigs"}]."""
    out = []
    for line in str(text or "").splitlines():
        if not line.strip():
            continue
        area, _, rest = line.partition(":")
        area = area.strip()[:60]
        asigs = [x.strip()[:60] for x in rest.split(",") if x.strip()] or [area]
        if area:
            out.append({"area": area, "asigs": asigs})
    return out


def choices(text):
    """Todas las áreas y asignaturas, sin repetir, en orden."""
    seen, out = set(), []
    for a in parse(text):
        for x in [a["area"], *a["asigs"]]:
            if norm(x) not in seen:
                seen.add(norm(x))
                out.append(x)
    return out


def area_of(name, text):
    k = norm(name)
    for a in parse(text):
        if k in {norm(a["area"]), *(norm(x) for x in a["asigs"])}:
            return a["area"]
    return ""


def find(spoken, options, text=""):
    """La asignatura de «options» que se nombra en lo dicho («en tecnología», «de mate»). None si ninguna."""
    t = " " + norm(spoken) + " "
    for k, v in _ALIAS.items():
        t = re.sub(rf"\b{k}\b", v, t)
    best = None
    for o in options:                                  # el nombre completo de la asignatura, el más largo primero
        if f" {norm(o)} " in t and (best is None or len(norm(o)) > len(norm(best))):
            best = o
    if best:
        return best
    for o in options:                                  # o su área («matemáticas» → la asignatura del área en ese curso)
        ar = area_of(o, text)
        if ar and f" {norm(ar)} " in t:
            return o
    for o in options:                                  # o cualquier asignatura del área de o («sistemas» → Tecnología)
        for a in parse(text):
            if norm(o) in {norm(a["area"]), *(norm(x) for x in a["asigs"])} and any(f" {norm(x)} " in t for x in a["asigs"]):
                return o
    return None


def parse_course_subjects(text):
    """«7A: Matemáticas, Tecnología e Informática» por línea → {curso: [asignaturas]}."""
    out = {}
    for line in str(text or "").splitlines():
        c, _, rest = line.partition(":")
        subs = [x.strip()[:60] for x in rest.split(",") if x.strip()]
        if c.strip() and subs:
            out[c.strip()[:40]] = subs
    return out


def key(course, subject, multi):
    return f"{course}{SEP}{subject}" if subject and multi else course


def split(k):
    c, _, s = str(k).partition(SEP)
    return c, s
