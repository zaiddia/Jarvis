"""12.40: comprador inteligente.

«Quiero comprar un portátil de unos 2 millones para trabajar y ver películas», «ayúdame a escoger una nevera de 1,5
millones», «¿qué celular me recomiendas de 800 mil?»: busca en tiendas de Colombia, comprueba con código que el precio de
cada producto está de verdad en su página, descarta lo que no o lo que se sale del presupuesto, y arma una comparación
(Word) con pros, contras y una recomendación para tu uso. Después: «vigila el precio del 2» (o «del recomendado») y te
avisa si baja. «¿Qué precios estoy vigilando?», «deja de vigilar el precio del portátil».
"""
import datetime
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import comprador as CM
import investigar
from nucleo import J

CM_ORIGIN = "COMPRAS"
_cm = {"busy": False, "last": None, "lock": threading.Lock()}
WATCH_EVERY = 12 * 3600
DROP_MIN = 0.03                   # avisa si baja al menos 3 %


def _cm_path():
    return os.path.join(J.CONFIG_DIR, "precios_vigilados.json")


def watched():
    try:
        with open(_cm_path(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _cm_save(items):
    tmp = _cm_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _cm_path())


# ---------------------------------------------------------------- comparar
def shop(req, sync=False):
    if J.is_offline():
        J.reply("Para comparar precios necesito internet, y ahora no hay.", CM_ORIGIN)
        return None
    if J.state.get("ai") != "ok":
        J.reply("Para comparar productos necesito la IA conectada.", CM_ORIGIN)
        return None
    if _cm["busy"]:
        J.reply("Ya estoy comparando otra compra; espera a que termine.", CM_ORIGIN)
        return None
    out = {}

    def work():
        _cm["busy"] = True
        try:
            out.update(J._shop_run(req) or {})
        except Exception as e:
            J.reply(f"No pude terminar la comparación: {e}", CM_ORIGIN)
        finally:
            _cm["busy"] = False
    J.reply(f"Busco {req['producto']}" + (f" de hasta {CM.cop(req['presupuesto'])}" if req["presupuesto"] else "") +
            (f" para {req['uso']}" if req["uso"] else "") + " en Alkosto, Ktronix, Éxito, Falabella y Mercado Libre. Compruebo cada "
            "precio en su página y te armo una comparación; me toma uno o dos minutos.", CM_ORIGIN)
    if sync:
        work()
        return out
    J.start_job("Comparando compras", work, "compras")
    return None


def _shop_run(req):
    sources = J._sources_for_more(CM.queries(req), 14)
    if not sources:
        J.reply(f"No encontré {req['producto']} en las tiendas. Prueba con otras palabras (marca o tipo).", CM_ORIGIN)
        return {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        sources = list(ex.map(J._read_page, sources))
    raw = J.ai_chat([{"role": "user", "content": CM.extract_prompt(req, sources)}], json_mode=True, max_tokens=3500)
    ok, bad = CM.verify_products(CM.parse_products(raw, len(sources)), sources, req["presupuesto"])
    ok = ok[:8]
    if not ok:
        why = ("todos se salían del presupuesto" if bad and all("presupuesto" in b["motivo"] for b in bad) else
               "no pude comprobar ningún precio en las páginas")
        J.reply(f"No te doy una comparación porque {why}. Prueba con otro presupuesto o más detalles (marca, tamaño).", CM_ORIGIN)
        return {"productos": [], "descartados": len(bad)}
    cmp_ = None
    try:
        cmp_ = CM.parse_compare(J.ai_chat([{"role": "user", "content": CM.compare_prompt(req, ok)}], json_mode=True, max_tokens=2500), len(ok))
    except Exception as e:
        J.log_terminal(f"Comparador: la IA no pudo comparar ({e}).", "AVISO")
    path = J._shop_doc(req, ok, bad, cmp_)
    _cm["last"] = {"req": req, "productos": ok, "rec": (cmp_ or {}).get("recomendado", 0), "t": time.time()}
    if path:
        J.generated_files.add(path)
        J._open_doc(path)
    J.reply(CM.spoken(req, ok, cmp_) + f" La tabla completa quedó en Word (Documentos › Jarvis › Compras). Si quieres, di «vigila el precio "
            f"del {(cmp_ or {}).get('recomendado') or 1}» y te aviso si baja.", CM_ORIGIN)
    return {"productos": ok, "descartados": len(bad), "comparacion": cmp_, "path": path}


def _shop_doc(req, ok, bad, cmp_):
    D = getattr(J.Document, "original", J.Document)
    if D is None:
        return ""
    doc = D()
    doc.add_heading(f"Comparación: {req['producto']}", 0)
    doc.add_paragraph(" · ".join(x for x in (f"Presupuesto: {CM.cop(req['presupuesto'])}" if req["presupuesto"] else "",
                                             f"Para: {req['uso']}" if req["uso"] else "",
                                             f"Precios vistos el {datetime.date.today():%d/%m/%Y} (cambian; confírmalos antes de pagar)") if x))
    if cmp_ and cmp_.get("recomendado"):
        r = ok[cmp_["recomendado"] - 1]
        doc.add_heading("La recomendación", 1)
        doc.add_paragraph(f"{r['nombre']} — {CM.cop(r['precio'])} en {r['tienda']}. {cmp_['por_que']}")
    tb = doc.add_table(rows=1, cols=6)
    tb.style = "Table Grid"
    for i, h in enumerate(("#", "Producto", "Precio", "Tienda", "Pros", "Contras")):
        tb.rows[0].cells[i].text = h
    for i, x in enumerate(ok, 1):
        per = (cmp_ or {}).get("por", {}).get(i, {})
        cells = tb.add_row().cells
        cells[0].text = str(i)
        cells[1].text = x["nombre"] + (f"\n{x['specs']}" if x["specs"] else "") + (f"\n{per['para_quien']}" if per.get("para_quien") else "")
        cells[2].text = CM.cop(x["precio"]) + (" (se pasa un poco)" if x.get("sobre") else "")
        cells[3].text = f"{x['tienda']}\n{x['url']}"
        cells[4].text = "\n".join(f"+ {p}" for p in per.get("pros", [])) or "—"
        cells[5].text = "\n".join(f"− {p}" for p in per.get("contras", [])) or "—"
    if cmp_ and cmp_.get("consejos"):
        doc.add_heading("Antes de comprar", 1)
        for c in cmp_["consejos"]:
            doc.add_paragraph(c, style="List Bullet")
    doc.add_heading("Cómo se comprobó", 1)
    doc.add_paragraph(f"Cada precio de la tabla aparece en la página de su tienda (lo revisó el código, no la IA). "
                      f"{len(bad)} producto{'s' if len(bad) != 1 else ''} se descartaron: "
                      + ("; ".join(f"{b['nombre'][:50]} ({b['motivo']})" for b in bad[:8]) if bad else "ninguno") + ".")
    folder = os.path.join(J.settings["output_dir"], "Jarvis", "Compras")
    os.makedirs(folder, exist_ok=True)
    safe = re.sub(r"[^\w\s-]", "", req["producto"])[:50].strip() or "compra"
    path = os.path.join(folder, f"Comparación - {safe} - {datetime.date.today():%Y-%m-%d}.docx")
    doc.save(path)
    return path


# ---------------------------------------------------------------- vigilar precios
def watch_add(prod):
    with _cm["lock"]:
        items = [x for x in watched() if x["url"] != prod["url"]]
        items.append({"nombre": prod["nombre"], "url": prod["url"], "tienda": prod.get("tienda", ""), "precio_inicial": prod["precio"],
                      "ultimo": prod["precio"], "minimo": prod["precio"], "visto": time.time(), "desde": datetime.date.today().isoformat()})
        _cm_save(items)


def price_watch_check(it):
    """→ precio nuevo si bajó lo suficiente (y lo avisa), 0 si no."""
    page = investigar.page_text(J._get_public(it["url"], timeout=15)[:1500000], limit=200000)
    now = CM.current_price(page, it["ultimo"])
    it["visto"] = time.time()
    if not now:
        return 0
    dropped = now <= it["ultimo"] * (1 - DROP_MIN)
    it["ultimo"] = now
    it["minimo"] = min(it.get("minimo", now), now)
    if dropped:
        J.notify(f"Bajó de precio: {it['nombre']} ahora está en {CM.cop(now)} en {it['tienda'] or 'la tienda'} "
                 f"(estaba en {CM.cop(it['precio_inicial'])} cuando empecé a vigilarlo). Confírmalo en la página antes de comprar.", CM_ORIGIN)
        return now
    return 0


def watch_tick():
    if J.is_offline():
        return 0
    with _cm["lock"]:
        items = watched()
    n = 0
    for it in items:
        if time.time() - it.get("visto", 0) < WATCH_EVERY:
            continue
        try:
            if J.cm_watch_check(it):
                n += 1
        except Exception as e:
            it["visto"] = time.time()
            J.log_terminal(f"Vigilar precio de {it['nombre']}: {e}", "AVISO")
    with _cm["lock"]:
        cur = {x["url"]: x for x in watched()}
        for it in items:
            if it["url"] in cur:
                cur[it["url"]] = it
        _cm_save(list(cur.values()))
    return n


_WATCH = re.compile(r"\b(?:vigila|vigilame|sigue|avisame (?:si baja|cuando baje))\w*\s+(?:el\s+)?(?:precio\s+)?(?:del?|de la|de el)?\s*"
                    r"(?:(?:numero|opcion|producto)\s+)?(\d{1,2}|primero|segundo|tercero|recomendado|mas barato)\b")
_WLIST = re.compile(r"\bque precios (?:estas vigilando|vigilas|sigues)\b|\bprecios vigilados\b")
_WSTOP = re.compile(r"\b(?:deja de vigilar|no vigiles mas|quita)\s+(?:el\s+)?precio\s+(?:del?|de la)?\s*(.+)$")
_CM_ORD = {"primero": 1, "segundo": 2, "tercero": 3}


def shop_voice(text, t):
    m = _WATCH.search(t)
    if m and _cm["last"]:
        last = _cm["last"]
        w = m.group(1)
        k = last["rec"] if w == "recomendado" else 1 if w == "mas barato" else _CM_ORD.get(w) or int(w)
        if not 1 <= k <= len(last["productos"]):
            J.reply(f"En la comparación hay {len(last['productos'])} productos; dime un número entre 1 y {len(last['productos'])}.", CM_ORIGIN)
            return True
        p = last["productos"][k - 1]
        watch_add(p)
        J.reply(f"Listo: vigilo el precio de {p['nombre']} en {p['tienda']} (hoy {CM.cop(p['precio'])}). Lo reviso dos veces al día y te "
                "aviso si baja.", CM_ORIGIN)
        return True
    if _WLIST.search(t):
        items = watched()
        J.reply("Vigilo: " + "; ".join(f"{x['nombre']} ({x['tienda']}): {CM.cop(x['ultimo'])}, desde {CM.cop(x['precio_inicial'])}" for x in items) + "."
                if items else "No estoy vigilando precios. Primero pide una comparación, por ejemplo «quiero comprar un celular de 800 mil».", CM_ORIGIN)
        return True
    m = _WSTOP.search(t)
    if m:
        q = CM.norm(m.group(1))
        with _cm["lock"]:
            items = watched()
            keep = [x for x in items if not any(w in CM.norm(x["nombre"]) for w in q.split() if len(w) > 3)]
            _cm_save(keep)
        J.reply(f"Dejé de vigilar {len(items) - len(keep)} precio{'s' if len(items) - len(keep) != 1 else ''}." if len(keep) < len(items)
                else "No encontré ese producto entre los que vigilo.", CM_ORIGIN)
        return True
    req = CM.parse_request(t)
    if req:
        req["producto"] = CM.with_accents(text, req["producto"])
        req["uso"] = CM.with_accents(text, req["uso"]) if req["uso"] else ""
        if getattr(J._tl, "capture", None) is not None:
            shop(req, sync=True)
        else:
            shop(req)
        return True
    return False


def cm_watch_check(it):
    return price_watch_check(it)


__all__ = ['DROP_MIN', 'CM_ORIGIN', 'WATCH_EVERY', '_CM_ORD', '_WATCH', '_WLIST', '_WSTOP', '_cm', '_cm_path', '_cm_save', '_shop_doc', '_shop_run',
           'cm_watch_check', 'shop', 'shop_voice', 'watch_add', 'price_watch_check', 'watch_tick', 'watched']
