"""Pruebas de la 11.6: archivos e imágenes subidos al chat (leerlos, preguntarles y convertirlos)."""
import base64
import io
import os
import time

import pytest
from PIL import Image, ImageDraw

import adjuntos
import conversiones


def _url(raw, mime="application/octet-stream"):
    return f"data:{mime};base64," + base64.b64encode(raw).decode()


def _png(color="red", size=(300, 200)):
    buf = io.BytesIO()
    im = Image.new("RGB", size, color)
    ImageDraw.Draw(im).text((10, 10), "Hola", fill="white")
    im.save(buf, "PNG")
    return buf.getvalue()


def _text_pdf(pages=3):
    """PDF con texto real (con la librería docx no se puede; se arma uno mínimo a mano)."""
    objs, kids = [], []
    font = 3 + 2 * pages
    for i in range(pages):
        content = f"BT /F1 18 Tf 72 720 Td (Pagina {i + 1}: el teorema de Pitagoras dice que el cuadrado de la hipotenusa es igual a la suma) Tj ET".encode()
        objs.append((3 + 2 * i, f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R "
                                f"/Resources << /Font << /F1 {font} 0 R >> >> >>".encode()))
        objs.append((4 + 2 * i, b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream"))
        kids.append(f"{3 + 2 * i} 0 R")
    objs = [(1, b"<< /Type /Catalog /Pages 2 0 R >>"), (2, f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {pages} >>".encode())] + objs
    objs.append((font, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"))
    out, offs = io.BytesIO(), {}
    out.write(b"%PDF-1.4\n")
    for n, body in sorted(objs):
        offs[n] = out.tell()
        out.write(b"%d 0 obj\n" % n + body + b"\nendobj\n")
    x = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(offs) + 1))
    for n in sorted(offs):
        out.write(b"%010d 00000 n \n" % offs[n])
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(offs) + 1, x))
    return out.getvalue()


def _scanned_pdf():
    buf = io.BytesIO()
    Image.new("RGB", (600, 800), "white").save(buf, "PDF")
    return buf.getvalue()


def _docx():
    from docx import Document
    d = Document()
    d.add_paragraph("Guía de fracciones para séptimo")
    t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text, t.cell(0, 1).text, t.cell(1, 0).text, t.cell(1, 1).text = "Nombre", "Nota", "Ana", "4.5"
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def _xlsx():
    from openpyxl import Workbook
    wb = Workbook()
    wb.active.title = "Notas"
    for r in (["Nombre", "Nota"], ["Ana", 4.5], ["Luis", 3.2]):
        wb.active.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def ad(tmp_path, monkeypatch):
    adjuntos.items.clear()
    adjuntos.configure(str(tmp_path / "cfg"))
    yield tmp_path
    adjuntos.items.clear()


def test_leer_los_archivos(ad):
    pdf = adjuntos.add("libro.pdf", _text_pdf(3))
    assert pdf["tipo"] == "pdf" and pdf["paginas"] == 3 and pdf["nombre"] == "libro.pdf"
    t = adjuntos.text_of(pdf)
    assert "[Página 2]" in t and "Pitagoras" in t and not adjuntos.is_scanned(pdf, t)
    sc = adjuntos.add("escaneo.pdf", _scanned_pdf())
    assert adjuntos.is_scanned(sc)
    w = adjuntos.add("guia.docx", _docx())
    assert "Guía de fracciones" in adjuntos.text_of(w) and "Ana | 4.5" in adjuntos.text_of(w)
    x = adjuntos.add("notas.xlsx", _xlsx())
    assert "[Hoja «Notas»]" in adjuntos.text_of(x) and "Luis | 3.2" in adjuntos.text_of(x)
    c = adjuntos.add("lista.csv", "Nombre;Nota\nAna;4,5\n".encode())
    assert adjuntos.table_rows(c)[1] == ["Ana", "4,5"]
    assert "PDF «libro.pdf»" in adjuntos.describe(pdf) and "3 página" in adjuntos.describe(pdf)
    with pytest.raises(ValueError):
        adjuntos.add("virus.exe", b"MZ")
    with pytest.raises(ValueError):
        adjuntos.add("grande.pdf", b"x" * (adjuntos.MAX_BYTES + 1))
    assert adjuntos.safe_name("../../a:b.pdf") == "a b.pdf"
    imgs = adjuntos.vision_images(adjuntos.add("foto.png", _png()), str(ad / "v"))
    assert len(imgs) == 1 and imgs[0].endswith(".jpg")


def test_conversiones(ad):
    out = str(ad / "out")
    a, b = adjuntos.add("a.png", _png("red")), adjuntos.add("b.jpg", _png("blue"))
    pdf = conversiones.images_to_pdf([a, b], out)
    import pypdf
    assert len(pypdf.PdfReader(pdf).pages) == 2 and os.path.basename(pdf) == "a y 1 más.pdf"
    assert "png" not in conversiones.options_for([a]) and "jpg" in conversiones.options_for([a])
    j = conversiones.image_to(a, out, "jpg")
    assert j.endswith(".jpg") and Image.open(j).format == "JPEG"
    big = adjuntos.add("grande.png", _png("green", (3000, 2000)))
    small = conversiones.image_to(big, out, "jpg", compress=True)
    assert max(Image.open(small).size) <= 1600
    p = adjuntos.add("libro.pdf", _text_pdf(4))
    parts = conversiones.split_pdf(p, out, 2, 3)
    assert len(parts) == 1 and len(pypdf.PdfReader(parts[0]).pages) == 2
    assert len(conversiones.split_pdf(p, out)) == 4
    r = conversiones.rotate_pdf(p, out, 90)
    assert pypdf.PdfReader(r).pages[0].rotation == 90
    q = adjuntos.add("otro.pdf", _text_pdf(2))
    assert len(pypdf.PdfReader(conversiones.merge_pdfs([p, q], out)).pages) == 6
    pngs = adjuntos.page_images(q, os.path.join(out, "pags"))
    assert len(pngs) == 2 and Image.open(pngs[0]).size[0] > 1000
    from docx import Document
    w, how = conversiones.pdf_to_word(p, out, Document)
    assert how == "texto" and "Pitagoras" in "\n".join(x.text for x in Document(w).paragraphs)
    x = adjuntos.add("notas.xlsx", _xlsx())
    csvp = conversiones.excel_to_csv(x, out)
    assert open(csvp, encoding="utf-8-sig").read().splitlines()[1] == "Ana;4.5"
    c = adjuntos.add("lista.csv", "Nombre;Nota\nAna;4,5\n".encode())
    from openpyxl import load_workbook
    ws = load_workbook(conversiones.csv_to_excel(c, out)).active
    assert ws["A2"].value == "Ana" and ws["B2"].value == 4.5
    w2 = adjuntos.add("guia.docx", _docx())
    if not conversiones._soffice():
        with pytest.raises(conversiones.ConvertError):
            conversiones._to_pdf_office(w2, out)
    assert conversiones.options_for([p, q]) == ["unir"] and conversiones.options_for([a, b]) == ["pdf"]


def _wait(jv, text):
    for _ in range(400):
        if text in jv._rec.said():
            return
        time.sleep(0.02)


def test_subir_y_tarjeta(jv, ad):
    r = jv.handle_attach({"files": [{"name": "foto.png", "data": _url(_png(), "image/png")}]})
    assert r["ok"] and r["preview"].startswith("data:image/jpeg") and r["tipos"] == ["imagen"]
    acts = [a["a"] for a in r["acciones"]]
    assert "describir" in acts and "revisar" in acts and "conv:pdf" in acts and "conv:png" not in acts
    assert jv.review_state["source"] == "adjunto" and jv.review_state["t"] > 0           # «revisa este trabajo» usa la foto subida (12.3: ya derecha)
    r2 = jv.handle_attach({"files": [{"name": "virus.exe", "data": _url(b"MZ")}]})
    assert not r2["ok"] and "no lo puedo leer" in r2["error"]
    a = jv.handle_attach({"files": [{"name": "a.pdf", "data": _url(_text_pdf(1))}]})
    b = jv.handle_attach({"files": [{"name": "b.pdf", "data": _url(_text_pdf(2))}]})
    card = jv.handle_attach_card({"ids": a["ids"] + b["ids"]})
    assert card["ok"] and [x["a"] for x in card["acciones"]] == ["conv:unir", "copia"]          # 12.12: y detectar copia
    assert not jv.handle_attach_action({"ids": ["nada"], "action": "resumir"})["ok"]


def test_convertir_por_voz_y_boton(jv, ad, monkeypatch):
    monkeypatch.setitem(jv.settings, "output_dir", str(ad / "docs"))
    a = jv.handle_attach({"files": [{"name": "a.png", "data": _url(_png("red"), "image/png")}]})
    b = jv.handle_attach({"files": [{"name": "b.png", "data": _url(_png("blue"), "image/png")}]})
    jv.handle_attach_card({"ids": a["ids"] + b["ids"]})                       # el HUD los sube uno por uno y pide la tarjeta de los dos
    jv._rec.clear()
    jv.process_command("únelos en un solo PDF")
    _wait(jv, "en un PDF")
    assert "2 imágenes en un PDF" in jv._rec.said()
    assert os.path.exists(os.path.join(str(ad / "docs"), "Conversiones", "a y 1 más.pdf"))
    jv.handle_attach({"files": [{"name": "libro.pdf", "data": _url(_text_pdf(5))}]})
    jv._rec.clear()
    jv.process_command("pásalo a Word")
    _wait(jv, "Listo el Word")
    assert "con el texto del PDF" in jv._rec.said()
    jv._rec.clear()
    jv.process_command("déjame solo las páginas 2 a 3 del pdf")
    _wait(jv, "Listo el PDF con esas")
    jv._rec.clear()
    pid = adjuntos.recent()[-1]["id"]
    assert jv.handle_attach_action({"ids": [pid], "action": "conv:imagenes"})["ok"]
    _wait(jv, "como imágenes PNG")
    assert "5 páginas" in jv._rec.said()
    # sin archivos recientes no se mete con otras órdenes
    adjuntos.items.clear()
    assert not jv.attachment_voice("pasa las notas del 7-1 a excel", "pasa las notas del 7 1 a excel")


def test_no_se_roba_otras_ordenes(jv, ad):
    jv.handle_attach({"files": [{"name": "guia.docx", "data": _url(_docx())}]})
    for t in ("que hora es", "haz el taller de fracciones para septimo", "pasa las notas del 7 1 a excel", "abre la calculadora"):
        assert not jv.attachment_voice(t, t), t


def test_preguntar_al_archivo(jv, ad, monkeypatch):
    monkeypatch.setitem(jv.state, "ai", "ok")
    prompts = []
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: prompts.append(msgs[0]["content"]) or "Es una guía de fracciones con una tabla de notas.")
    jv.handle_attach({"files": [{"name": "guia.docx", "data": _url(_docx())}]})
    jv._rec.clear()
    jv.process_command("¿De qué trata este documento?")
    _wait(jv, "Es una guía de fracciones")
    assert "Guía de fracciones para séptimo" in prompts[0] and "De qué trata este documento" in prompts[0]
    # imagen: con visión
    seen = []
    monkeypatch.setattr(jv, "_vision_text", lambda prompt, img, max_tokens=2500: seen.append((prompt, img)) or "Hay una ecuación: 2x + 3 = 7.")
    jv.handle_attach({"files": [{"name": "tablero.png", "data": _url(_png(), "image/png")}]})
    jv._rec.clear()
    jv.process_command("qué dice la foto que te subí")
    _wait(jv, "Hay una ecuación")
    assert seen and os.path.exists(seen[0][1]) and "qué dice la foto" in seen[0][0]
    # texto de una imagen (OCR con la IA) → .txt
    monkeypatch.setitem(jv.settings, "output_dir", str(ad / "docs"))
    jv._rec.clear()
    jv.process_command("sácale el texto")
    _wait(jv, "Listo el texto")
    assert "leído con la IA" in jv._rec.said()
    # tabla de una foto → Excel
    monkeypatch.setattr(jv, "_vision_cfg", lambda: ({"kind": "cloud"}, None))
    monkeypatch.setattr(jv, "_vision_text", lambda prompt, img, max_tokens=2500: '{"tablas": [{"nombre": "Notas 7-1", "filas": [["Nombre", "Nota"], ["Ana", "4.5"]]}]}')
    jv._rec.clear()
    jv.process_command("pasa la lista de esta foto a excel")
    _wait(jv, "Saqué 1 tabla")
    from openpyxl import load_workbook
    path = next(os.path.join(r, f) for r, _, fs in os.walk(ad / "docs") for f in fs if f.endswith(".xlsx"))
    ws = load_workbook(path).active
    assert ws.title == "Notas 7-1" and ws["B2"].value == 4.5
