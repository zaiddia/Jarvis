"""Jarvis llena las plataformas por ti (12.2). Lógica pura, sin Jarvis.

Jarvis abre la plataforma (Zeti u otra) en su propio navegador; tú entras con tu usuario (Jarvis nunca escribe ni ve
contraseñas). En la planilla, Jarvis lee los campos de la página (con la fila y la columna de cada uno), la IA decide
qué nota va en cada campo y Jarvis COMPRUEBA cada asignación antes de escribir: que el estudiante de la fila sea el
que la IA dice y que el valor sea exactamente el que tiene en su seguimiento. Lo que no cuadra no se escribe.
Nunca pulsa «Guardar» por su cuenta: te muestra lo que llenó y espera a que lo digas.
"""
import difflib
import re
import unicodedata

# Marca cada campo visible con data-jarvis-id y devuelve su contexto (fila, columna, etiqueta). Se ejecuta en la página.
EXTRACT_JS = r"""
() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none"; };
  const clean = (t) => (t || "").replace(/\s+/g, " ").trim().slice(0, 120);
  const out = []; let n = 0;
  const password = [...document.querySelectorAll("input[type=password]")].some(vis);
  for (const e of document.querySelectorAll("input, select, textarea")) {
    const ty = (e.getAttribute("type") || "").toLowerCase();
    if (["hidden", "password", "submit", "button", "checkbox", "radio", "file", "image", "reset"].includes(ty) || !vis(e) || e.disabled || e.readOnly) continue;
    const id = "j" + (++n); e.setAttribute("data-jarvis-id", id);
    let label = e.getAttribute("aria-label") || e.getAttribute("placeholder") || e.getAttribute("title") || "";
    if (e.id) { const l = document.querySelector(`label[for="${CSS.escape(e.id)}"]`); if (l) label = l.innerText; }
    let fila = "", columna = "";
    const td = e.closest("td, th"), tr = e.closest("tr");
    if (tr) fila = clean([...tr.cells].filter((c) => !c.querySelector("input, select, textarea")).map((c) => c.innerText).join(" | "));
    if (td && tr) { const table = tr.closest("table"); const idx = td.cellIndex;
      const head = table && (table.tHead ? table.tHead.rows[table.tHead.rows.length - 1] : table.rows[0]);
      if (head && head !== tr && head.cells[idx]) columna = clean(head.cells[idx].innerText); }
    if (!fila) { const box = e.closest("[class*=row], [class*=fila], li, .item, div"); if (box) fila = clean(box.innerText); }
    out.push({ id, tag: e.tagName.toLowerCase(), name: e.getAttribute("name") || "", label: clean(label), fila, columna,
               valor: e.tagName === "SELECT" ? (e.options[e.selectedIndex] || {}).text || "" : e.value || "",
               opciones: e.tagName === "SELECT" ? [...e.options].map((o) => clean(o.text)).slice(0, 12) : [] });
    if (n >= 600) break;
  }
  return { password, campos: out, titulo: document.title, url: location.href };
}
"""

SAVE_RX = re.compile(r"^\s*(?:guardar|grabar|guardar cambios|guardar notas|guardar calificaciones|actualizar|save|enviar|registrar)\s*$", re.I)


def norm(text):
    t = unicodedata.normalize("NFD", str(text or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", t)).strip()


def fmt(v, comma=True):
    """3.5 → «3,5» (o «3.5»); enteros sin decimales."""
    if isinstance(v, (int, float)):
        s = str(int(v)) if float(v) == int(v) and not isinstance(v, float) else f"{float(v):.1f}"
        return s.replace(".", ",") if comma else s
    return str(v)


def student_values(seguimiento_rows, promedio=None, fallas=None):
    """Lo que Jarvis sabe de un estudiante: {«nombre de la actividad»: nota, «definitiva»: promedio, «fallas»: n}."""
    vals = {}
    for r in seguimiento_rows or []:
        a = str(r.get("actividad", "")).strip()
        if a and r.get("nota") is not None:
            vals[a] = float(r["nota"])
    if promedio is not None:
        vals["definitiva"] = round(float(promedio), 1)
    if fallas is not None:
        vals["fallas"] = int(fallas)
    return vals


def prompt(campos, data, comma=True):
    lines = [f"{c['id']} | fila: {c['fila'][:80]} | columna: {c['columna'] or c['label'] or c['name']}" + (f" | ya tiene: {c['valor']}" if c["valor"] else "")
             + (f" | opciones: {', '.join(c['opciones'])}" if c["opciones"] else "") for c in campos]
    datos = "\n".join(f"- {n}: " + "; ".join(f"{k} = {fmt(v, comma)}" for k, v in vals.items()) for n, vals in data.items())
    return f"""Estás llenando la planilla de notas de una plataforma escolar. Estos son los campos de la página (id | fila | columna):
{chr(10).join(lines)}

Estos son los datos de cada estudiante (de su seguimiento):
{datos}

Decide qué dato va en cada campo: el estudiante sale de la FILA del campo y el dato, de la COLUMNA (una actividad, la \
definitiva o las fallas). Si un campo no corresponde claramente a un dato, no lo incluyas. No inventes valores.
Responde SOLO un JSON: {{"asignaciones": [{{"campo": "j5", "estudiante": "nombre tal como aparece en los datos", "dato": "nombre del dato", \
"valor": "4,5"}}], "nota": "una frase si algo no encaja (o vacío)"}}"""


def _name_in(name, text):
    """¿El nombre del estudiante está en el texto de la fila? (al menos dos palabras, o una si el nombre es de una)."""
    ws = [w for w in norm(name).split() if len(w) > 2]
    tx = set(norm(text).split())
    hits = sum(1 for w in ws if w in tx or any(difflib.SequenceMatcher(None, w, t).ratio() > 0.88 for t in tx))
    return hits >= min(2, len(ws)) if ws else False


def check(asig, campos, data, comma=True):
    """Comprueba cada asignación de la IA. → (para escribir [{"campo", "valor", "estudiante", "dato", "cambia"}], rechazadas [motivos])."""
    by_id = {c["id"]: c for c in campos}
    names = {norm(n): n for n in data}
    ok, bad, used = [], [], set()
    for a in (asig or [])[:800]:
        if not isinstance(a, dict):
            continue
        cid, est, dato = str(a.get("campo", "")), str(a.get("estudiante", "")), str(a.get("dato", ""))
        c = by_id.get(cid)
        if not c or cid in used:
            continue
        real = names.get(norm(est)) or next((names[k] for k in difflib.get_close_matches(norm(est), list(names), n=1, cutoff=0.85)), None)
        if not real:
            bad.append(f"{est}: no está en tu lista")
            continue
        if not _name_in(real, c["fila"] + " " + c["label"]):
            bad.append(f"{real}: la fila del campo no es la suya")
            continue
        vals = data[real]
        key = next((k for k in vals if norm(k) == norm(dato)), None)
        if not key:
            m = difflib.get_close_matches(norm(dato), [norm(k) for k in vals], n=1, cutoff=0.8)
            key = next((k for k in vals if m and norm(k) == m[0]), None)
        if not key:
            bad.append(f"{real}: no tengo «{dato}»")
            continue
        valor = fmt(vals[key], comma)
        if c["opciones"] and not any(norm(o) == norm(valor) for o in c["opciones"]):
            bad.append(f"{real}: «{valor}» no es una opción de la lista")
            continue
        used.add(cid)
        ok.append({"campo": cid, "valor": valor, "estudiante": real, "dato": key,
                   "cambia": bool(c["valor"]) and norm(c["valor"]) != norm(valor) and norm(c["valor"]).replace(",", ".") != norm(valor).replace(",", ".")})
    return ok, bad


def summary(ok, bad, total_students):
    est = {x["estudiante"] for x in ok}
    t = f"Llené {len(ok)} campo{'s' if len(ok) != 1 else ''} de {len(est)} estudiante{'s' if len(est) != 1 else ''}"
    t += f" (de {total_students} en tu lista)" if total_students else ""
    ch = [x for x in ok if x["cambia"]]
    if ch:
        t += f"; {len(ch)} ya tenía{'n' if len(ch) != 1 else ''} otro valor y lo cambié (resaltado en naranja)"
    t += "."
    if bad:
        t += f" No escribí {len(bad)}: " + "; ".join(bad[:4]) + ("…" if len(bad) > 4 else "") + "."
    return t + " Revisa la pantalla: lo que llené está resaltado. No guardé nada: di «guarda la planilla» o pulsa tú «Guardar»."
