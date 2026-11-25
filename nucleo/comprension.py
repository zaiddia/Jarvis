"""12.27: Jarvis entiende lenguaje natural, no solo sus frases de siempre.

Antes: si la frase no calzaba con una de sus reglas, la IA solo podía elegir entre unas 38 acciones y 72 órdenes del PC;
el resto de lo que sabe hacer (la guía tiene cientos de frases) era invisible para ella, y lo que sonaba a pregunta
(«¿me ayudas con…?») iba directo a una charla.

Ahora, cuando ninguna regla la reconoce, la IA «traduce» lo que dijiste a la orden de Jarvis que corresponde —con tus
datos: horas, montos, nombres— y esa orden pasa por el camino de siempre. Así sirve cualquier habilidad que ya existe:
  «oye, mañana tengo que llevar el carro al taller temprano, no me dejes olvidarlo» → «recuérdame mañana a las 7 llevar el carro al taller»
  «lo del súper ayer fueron como 85 lucas» → «gasté 85 mil en mercado»
Si no está seguro entre dos cosas, pregunta en una línea con las dos órdenes completas. Si la orden traducida borra,
apaga, envía o paga algo que tú no dijiste con esas palabras, te pide permiso primero. Las preguntas de saber
(«¿qué es…?», «¿por qué…?») siguen yendo directo a la IA, sin este paso.
"""
import json
import os
import re

import catalogo_docente
import frasesnl
import guia
import selector
from nucleo import J

NL_K = 30                                                  # ejemplos que ve la IA (los más parecidos a tu frase)…
_KNOW = re.compile(r"^(?:jarvis\s+)?(?:que es(?! mejor| peor| mas barato| mas caro)|que son|que significa|que fue|quien es|quien fue|quienes son|por que|porque|como funciona|"
                   r"como se (?:dice|escribe|hace|calcula|pronuncia)|explica|explicame|define|definicion de|diferencia entre|"
                   r"cual es (?:la|el) (?:capital|diferencia|significado|origen)|cuando (?:fue|nacio|murio|empezo|termino)|"
                   r"donde (?:queda|esta ubicad)|cuentame (?:sobre|de|acerca)|hablame (?:de|sobre)|que opinas|que piensas)\b")
_CHAT = re.compile(r"^(?:hola|buenas|buenos dias|buenas tardes|buenas noches|gracias|muchas gracias|ok|vale|listo|jaja\w*|"
                   r"como estas|que tal|chao|adios|hasta luego|te quiero|eres genial|bien|muy bien|perfecto)\b(?:\s+jarvis)?$")
_RISKY = re.compile(r"\b(?:borra\w*|elimina\w*|apaga\w*|reinicia\w*|desinstala\w*|formatea\w*|cierra\w*|envia\w*|manda\w*|"
                    r"publica\w*|paga\w*|vacia\w*|cancela\w*|bloquea\w*|suspende\w*|transfiere\w*|desconecta\w*|restaura\w*)\b")
nl_state = {"last": None}                                  # lo último que entendió (para el registro y las pruebas)


def nl_examples(text, k=NL_K):
    """Las frases de Jarvis más parecidas a lo que dijiste (de la guía y de las órdenes del asistente)."""
    seen, items = set(), []
    general = J.current_mode() == "general"
    for cat in J.guide():
        if general and cat["id"] == "colegio":
            continue
        for g in cat["grupos"]:
            exs = [e["t"] for e in g["ejemplos"] if e["probar"]]
            for e in exs:
                if general and catalogo_docente.school_explicit(e):      # 12.36: en modo general, ningún ejemplo del colegio
                    continue
                if e not in seen:
                    seen.add(e)
                    items.append((e, f"{re.sub(r'[(][0-9.]+[)]', '', g['nombre'])}: {e}"))
    for o in J.ASSISTANT_ORDERS:
        if o not in seen:
            seen.add(o)
            items.append((o, o))
    if J.current_mode() == "docente":                     # 12.36: la base de datos docente, solo en modo docente
        for label, f in catalogo_docente.examples():
            if f not in seen:
                seen.add(f)
                items.append((f, label))
    # 12.36: solo por palabras (sin pedir «embeddings» a la nube): una llamada de red menos por frase; la IA igual ve
    # una frase de cada habilidad debajo, así que no se le escapa ninguna.
    return selector.choose(text, items, k=k, embed=None, tag="")


def nl_catalog(text):
    """Lo que ve la IA: las más parecidas a tu frase y, debajo, una frase de cada habilidad (así no se le escapa ninguna
    aunque no haya palabras en común: «85 lucas en el súper» no comparte palabras con «gasté 20 mil en almuerzo»)."""
    try:
        local = J._is_local_ai()
    except Exception:
        local = False
    if local:                                             # 12.34: la IA de tu equipo es más lenta leyendo: menos ejemplos
        return nl_examples(text, k=18), []
    near = nl_examples(text)
    general = J.current_mode() == "general"
    rest = []
    for cat in J.guide():
        if general and cat["id"] == "colegio":
            continue
        for g in cat["grupos"]:
            exs = [e["t"] for e in g["ejemplos"] if e["probar"]]
            if exs and not set(exs) & set(near):
                rest.append(_closest(text, exs))          # 12.33: de cada habilidad, la frase más parecida (no la primera)
    return near, rest


def _closest(text, exs):
    words = {w[:5] for w in J.normalize(text).split() if len(w) > 2}
    return max(exs, key=lambda e: (len(words & {w[:5] for w in J.normalize(e).split() if len(w) > 2}), -exs.index(e)))


def nl_prompt(text, examples, more=()):
    ex = "\n".join(f"- {e}" for e in examples)
    return ("Eres la parte de Jarvis que entiende lo que la persona quiere. Jarvis es un asistente de voz en español (Colombia) "
            "que hace cosas en el PC y en la vida diaria, y las reconoce con frases como estas:\n" + ex + "\n"
            + (("Otras cosas que sabe hacer (una frase de cada una): " + " · ".join(more) + "\n") if more else "") + "\n"
            f"La persona dijo: «{text}»\n\n"
            "Si pide que Jarvis HAGA o CONSULTE algo que cubre una de esas frases, devuelve en «orden» ESA frase de la lista, con "
            "su misma forma y sus mismas palabras clave, cambiando solo los datos de la persona (horas, montos, nombres, lugares). "
            "Nunca devuelvas la frase de la persona tal cual ni con otras palabras: Jarvis solo reconoce la forma de la lista. "
            "Ejemplos: «la pantalla está muy oscura» → «brillo al 90»; «libera espacio en el disco» → «limpia los temporales»; "
            "«me tomé un tinto de 3500» → «gasté 3500 en tinto»; «en qué se me va la plata» → «resumen del mes».\n"
            "Las preguntas sobre las cosas de la persona (su agenda, sus gastos, sus medicamentos, sus citas, sus listas, su PC, "
            "su correo) SÍ son órdenes: «qué medicinas tomo» → «qué medicamentos tengo».\n"
            "Conserva «hoy», «mañana», «el viernes», «en 10 minutos» tal cual. No inventes datos que la persona no dijo. Si dice "
            "«lucas» o «barras», son miles de pesos.\n"
            "Si es una pregunta de saber general, una charla o algo que esas frases no cubren, no lo conviertas (tipo «pregunta» "
            "o «charla»).\nSi dudas entre dos órdenes, pide aclarar con las dos completas.\n"
            'Responde SOLO con JSON: {"tipo": "orden" | "pregunta" | "charla" | "aclarar", "orden": "…", '
            '"opciones": ["…", "…"], "seguro": true}')


def nl_parse(raw):
    """Lo que devolvió la IA, ya limpio. → {"tipo", "orden", "opciones", "seguro"}."""
    try:
        d = J._extract_json(raw) if not isinstance(raw, dict) else raw
    except Exception:
        d = None
    if not isinstance(d, dict):
        return {"tipo": "pregunta", "orden": "", "opciones": [], "seguro": False}
    tipo = str(d.get("tipo") or "").strip().lower()
    tipo = tipo if tipo in ("orden", "pregunta", "charla", "aclarar") else "pregunta"
    orden = re.sub(r"\s+", " ", str(d.get("orden") or "")).strip(" «»\"'.")[:300]
    ops = [re.sub(r"\s+", " ", str(o)).strip(" «»\"'.")[:200] for o in (d.get("opciones") or []) if str(o).strip()][:3]
    if tipo == "orden" and not orden:
        tipo = "pregunta"
    if tipo == "aclarar" and len(ops) < 2:
        tipo, orden = ("orden", ops[0] if ops else orden) if (ops or orden) else ("pregunta", "")
    return {"tipo": tipo, "orden": orden, "opciones": ops, "seguro": d.get("seguro") is not False}


def nl_should_try(text, t):
    if not J.settings.get("nl_understand", True) or getattr(J._tl, "nl_pass", False):
        return False
    if J.state.get("ai") != "ok" or len(t.split()) < 2 or _KNOW.match(t) or _CHAT.match(t):
        return False
    return True


def nl_risky(orden, t):
    """¿La orden traducida hace algo delicado que la persona no dijo con esas palabras?"""
    for m in _RISKY.finditer(J.normalize(orden)):
        if m.group(0)[:5] not in t:
            return True
    return False


def nl_run(orden):
    """Pasa la orden traducida por el camino de siempre. → True si alguna regla la atendió."""
    J._tl.nl_pass, J._tl.nl_missed = True, False
    try:
        J.process_command(orden)
        return not J._tl.nl_missed
    finally:
        J._tl.nl_pass, J._tl.nl_missed = False, False


_FILLER = re.compile(r"^(?:oye|mira|ey|hey|bueno|pues|uy|ush|vea|ve|ay|resulta que|es que|fijate que|sabes que|necesito que|quiero que|"
                     r"me gustaria|tengo que|no me dejes|ayudame (?:a|con)|porfa|por favor|quisiera|seria bueno|me haces el favor|"
                     r"acuerdate|no se me puede|se me|me toca|me llego|me llegaron|ando|estoy)\b")
_starters = {"set": None}


def nl_starters():
    """Las primeras palabras de las órdenes de Jarvis («pon», «abre», «recuérdame»…): si la frase empieza así, primero las reglas."""
    if _starters["set"] is None:
        words = set()
        for cat in J.guide():
            for g in cat["grupos"]:
                for e in g["ejemplos"]:
                    if not e["t"].startswith("("):
                        w = J.normalize(e["t"]).split()
                        if w and w[0] not in ("que", "cual", "cuales", "como", "cuanto", "cuantos", "cuando", "donde", "quien", "el", "la",
                                              "los", "las", "mi", "mis", "un", "una", "tengo", "me", "ya", "no", "si", "hoy", "manana"):
                            words.add(w[0][:5])
        for o in J.ASSISTANT_ORDERS:
            w = J.normalize(o).split()
            if w:
                words.add(w[0][:5])
        for v in ("recibe", "abre", "activa", "desactiva", "lanza", "habilita", "empieza", "inicia", "termina", "cierra", "pon", "quita",
                  "sube", "baja", "crea", "haz", "genera", "prepara", "arma", "busca", "muestra", "lee", "dime", "dame", "cuenta", "calcula",
                  "convierte", "traduce", "manda", "envia", "escribe", "redacta", "anota", "apunta", "agrega", "anade", "borra", "elimina",
                  "guarda", "recuerda", "avisa", "programa", "cambia", "conecta", "desconecta", "instala", "desinstala", "actualiza",
                  "revisa", "compara", "organiza", "planea", "califica", "toma", "pasa", "llama", "marca", "silencia", "reproduce",
                  "pausa", "sigue", "deten", "descarga", "comparte", "exporta", "importa", "imprime", "proyecta", "copia", "pega",
                  "selecciona", "minimiza", "maximiza", "apaga", "reinicia", "enciende", "prende", "limpia", "mueve", "renombra",
                  "registra", "elige", "escoge", "sortea", "lanza", "usa", "modo", "temporizador", "alarma", "recordatorio"):
            words.add(v[:5])
        _starters["set"] = words
    return _starters["set"]


_LEAD = re.compile(r"^(?:(?:jarvis|oye|mira|ey|hey|bueno|pues|porfa|por favor|uy|ve|vea|ay)\b[ ,]*)+")


def nl_conversational(t):
    """12.29: ¿suena a conversación más que a orden? Entonces la IA entiende ANTES que las reglas (no después)."""
    w = re.sub(r"^(?:jarvis|oye jarvis|hola jarvis)[ ,]+", "", t).split()
    if len(w) < 4 or _KNOW.match(" ".join(w)) or _CHAT.match(" ".join(w)):
        return False
    rest = _LEAD.sub("", " ".join(w)).split()
    if rest and len(rest) <= 6 and rest[0][:5] in nl_starters():   # 12.36: «oye, sube el volumen»: orden corta de siempre (instantánea)
        return False
    if _FILLER.match(" ".join(w)):
        return True
    return len(w) >= 7 and w[0][:5] not in nl_starters()     # por la raíz: «escríbeme» y «escribe» son la misma orden


_RETRY = ("La orden «{o}» no la reconoce Jarvis. Escoge la frase de la lista que más se parezca a lo que pidió la persona, "
          "con la misma forma, y cámbiale solo los datos (horas, montos, nombres). Si ninguna sirve, responde tipo «pregunta».")


def _nl_ask(text, retry_of=""):
    old = getattr(J._tl, "fast_model", "")
    J._tl.fast_model = J.fast_model()                     # el modelo rápido: esto es solo entender, no responder
    try:
        msgs = [{"role": "user", "content": nl_prompt(text, *nl_catalog(text))}]
        if retry_of:
            msgs += [{"role": "assistant", "content": json.dumps({"tipo": "orden", "orden": retry_of}, ensure_ascii=False)},
                     {"role": "user", "content": _RETRY.format(o=retry_of)}]
        return nl_parse(J.ai_chat(msgs, json_mode=True, max_tokens=220))
    finally:
        J._tl.fast_model = old


nl_pending = {"ops": [], "until": 0.0}                    # opciones que Jarvis acaba de ofrecer al aclarar (2 minutos)
_PICK = re.compile(r"^(?:la |el |por la |por el )?(primera|primero|segunda|segundo|tercera|tercero|1|2|3|uno|dos|tres|opcion (?:1|2|3|uno|dos|tres))"
                   r"(?: opcion| esa| porfa| por favor)?$")


def nl_offer(ops):
    """Pregunta cuál de las órdenes quiere: en voz, en el chat y como botones en el HUD."""
    import time
    nl_pending.update(ops=list(ops), until=time.time() + 120)
    J.reply("¿Cuál de estas? " + " o ".join(f"«{o}»" for o in ops) + ". Toca una o dime «la primera» o «la segunda».", "COMPRENSIÓN")
    J.socketio.emit("nl_options", {"opciones": list(ops)})


def nl_pick(t):
    """«la primera», «la 2»… justo después de una aclaración. → True si la atendió."""
    import time
    if not nl_pending["ops"] or time.time() > nl_pending["until"]:
        return False
    m = _PICK.match(t)
    if not m:
        nl_pending.update(ops=[], until=0.0)              # dijo otra cosa: la aclaración ya pasó
        return False
    k = {"primera": 0, "primero": 0, "1": 0, "uno": 0, "segunda": 1, "segundo": 1, "2": 1, "dos": 1, "tercera": 2, "tercero": 2,
         "3": 2, "tres": 2}[m.group(1).split()[-1]]
    ops = nl_pending["ops"]
    nl_pending.update(ops=[], until=0.0)
    if k >= len(ops):
        J.reply(f"Solo te di {len(ops)} opciones.", "COMPRENSIÓN")
        return True
    if not nl_run(ops[k]):
        J.reply(f"No supe hacer «{ops[k]}».", "COMPRENSIÓN")
    return True


def _nl_do(orden, text, t):
    """Hace la orden traducida (o pide permiso si es delicada). → True si quedó atendida."""
    J.log_terminal(f"Entendí «{text.strip()}» como «{orden}».", "COMPRENSIÓN")
    if not getattr(J._tl, "remote", False):
        J.card("tip", "Entendí", orden, "🧠", secs=6)
    return nl_run(orden)


def nl_understand(text, t, early=False):
    """La capa de comprensión. → True si ya quedó atendido; False para seguir (con las reglas si early, si no con la IA de siempre).
    early (12.29): se llama ANTES de las reglas para frases que suenan a conversación."""
    if getattr(J._tl, "nl_tried", "") == t:
        return False
    if J.r55_memo_try(text, t):                           # 12.55: una frase que ya entendió antes va directo, sin preguntarle a la IA
        return True
    if not nl_should_try(text, t):
        return False
    if early and not nl_conversational(t):
        return False
    J._tl.nl_tried = t                                    # una sola vez por frase (si la primera pasada no la hizo, no repite)
    ack = J.ack_start(text)
    try:
        d = _nl_ask(text)
    except Exception as e:
        J.log_terminal(f"Comprensión: no pude preguntarle a la IA ({getattr(e, 'why', e)}); sigo como siempre.", "COMPRENSIÓN")
        return False
    finally:
        ack.done()
    nl_state["last"] = dict(d, frase=text, antes=early)
    J._tl.nl_verdict = d["tipo"]                          # 12.36: si no era orden, la respuesta va directo (sin enrutador)
    if d["tipo"] == "aclarar":
        nl_offer(d["opciones"])
        return True
    if d["tipo"] == "orden" and J.normalize(d["orden"]) == t:   # 12.33: la devolvió sin traducir: que lo intente con una de la lista
        try:
            d = _nl_ask(text, retry_of=d["orden"])
        except Exception:
            return False
        nl_state["last"] = dict(d, frase=text, antes=early, reintento="(sin traducir)")
    if d["tipo"] != "orden" or J.normalize(d["orden"]) == t:
        return False
    orden = d["orden"]
    if (not d["seguro"] or nl_risky(orden, t)) and getattr(J._tl, "live", False):
        J.request_approval("orden", f"¿Hago «{orden}»?", f"Lo entendí de: «{text.strip()}»", quiet=True,
                           on_ok=lambda: nl_run(orden) or J.reply(f"No supe hacer «{orden}».", "COMPRENSIÓN"))
        J.reply(f"Entendí «{orden}», pero antes necesito su permiso. Pregúntale si quiere que lo haga; si dice que sí, llama a "
                "ejecutar_orden con la orden «sí».", "COMPRENSIÓN")   # (en vivo no se habla encima de Gemini)
        return True
    if not d["seguro"] or nl_risky(orden, t):
        J.request_approval("orden", f"¿Hago «{orden}»?", f"Lo entendí de: «{text.strip()}»",
                           on_ok=lambda: nl_run(orden) or J.reply(f"No supe hacer «{orden}».", "COMPRENSIÓN"),
                           on_no=lambda: J.reply("Vale, no lo hago. Dímelo con otras palabras.", "COMPRENSIÓN"),
                           say=f"Entendí: {orden}. ¿Lo hago? Di «sí» o «no».")
        return True
    if _nl_do(orden, text, t):
        J.r55_memo_put(t, orden)
        return True
    try:                                                  # 12.29: segundo intento, diciéndole qué no sirvió
        d2 = _nl_ask(text, retry_of=orden)
    except Exception:
        d2 = {"tipo": "pregunta", "orden": ""}
    nl_state["last"] = dict(d2, frase=text, antes=early, reintento=orden)
    if d2["tipo"] == "orden" and d2["orden"] and J.normalize(d2["orden"]) not in (t, J.normalize(orden)):
        if nl_risky(d2["orden"], t) or not d2["seguro"]:
            return False
        if _nl_do(d2["orden"], text, t):
            J.r55_memo_put(t, d2["orden"])
            return True
    J.log_terminal(f"«{orden}» tampoco la reconocí; " + ("sigo con las reglas." if early else "lo respondo con la IA."), "COMPRENSIÓN")
    return False


# ============================================================================ PRUEBA DE COMPRENSIÓN (12.29)
NL_TEST_N = 40                                            # frases por prueba (la completa: todas)
NL_TEST_PAUSE = 4.5                                       # segundos entre preguntas: la cuota gratis de Gemini es de pocas por minuto
NL_TEST_WAIT = 65                                         # si responde «cuota agotada», espera esto y repite (una vez)
_NLT = re.compile(r"\b(?:haz|hazme|corre|ejecuta|inicia|empieza|lanza)\s+(?:la\s+|una\s+)?prueba de comprension(?:\s+(completa|rapida|corta))?\b|"
                  r"\bque tan bien me entiendes\b")
nl_test_state = {"busy": False, "last": None}


def nl_test_run(n=NL_TEST_N, pause=NL_TEST_PAUSE, seed=None):
    """Pasa frases del banco por la comprensión con TU IA, sin ejecutar nada. → {"n", "bien", "aclaro", "mal", "filas", "corte"}."""
    import random
    import time
    rows = frasesnl.rows()
    if n and n < len(rows):
        rows = random.Random(seed).sample(rows, n)
    res = {"n": 0, "bien": 0, "aclaro": 0, "mal": 0, "filas": [], "corte": "", "saltadas": 0}
    import time as _t
    for i, (nat, can, _alt) in enumerate(rows):
        d = None
        for attempt in (0, 1):
            try:
                d = _nl_ask(nat)
                break
            except Exception as e:
                kind = getattr(e, "kind", "")
                if kind in ("quota", "balance", "server") and attempt == 0:      # 12.33: límite por minuto: espera y repite
                    J.log_terminal(f"Prueba de comprensión: la IA dijo «{getattr(e, 'why', e)}»; espero {NL_TEST_WAIT} s.", "COMPRENSIÓN")
                    if J.net.get("watch", True):
                        _t.sleep(NL_TEST_WAIT)
                    continue
                if kind in ("quota", "balance", "key", "config", "net", "offline") or res["n"] == 0:
                    res["corte"] = str(getattr(e, "why", e))[:160]
                else:
                    res["saltadas"] += 1                  # un error suelto no cuenta como «no entendió»
                d = None
                break
        if res["corte"]:
            break
        if d is None:
            continue
        nota = frasesnl.grade(d, can, nat)
        res["n"] += 1
        res[{"bien": "bien", "aclaró": "aclaro", "mal": "mal"}[nota]] += 1
        got = d.get("orden") or " / ".join(d.get("opciones") or []) or f"({d.get('tipo')})"
        res["filas"].append((nota, nat, got, can))
        if pause and i < len(rows) - 1 and J.net.get("watch", True):      # (en las pruebas no se espera)
            time.sleep(pause)
    return res


def nl_test_report(res):
    import datetime
    import os
    pct = round(100 * (res["bien"] + res["aclaro"]) / res["n"]) if res["n"] else 0
    head = (f"Prueba de comprensión — {datetime.datetime.now():%Y-%m-%d %H:%M} — {J._ai_cfg().get('label', 'IA')} · v{J.VERSION}\n"
            f"Entendió bien {res['bien']} de {res['n']}" + (f", y en {res['aclaro']} preguntó entre opciones (una era la buena)" if res["aclaro"] else "")
            + f". Acierto: {pct} %.\n" + (f"Se cortó: {res['corte']} (las que no alcanzó no cuentan).\n" if res["corte"] else "")
            + (f"{res['saltadas']} frases no se calificaron por un error de la IA.\n" if res.get("saltadas") else "") + "\n")
    mark = {"bien": "✓", "aclaró": "≈", "mal": "✗"}
    lines = [f"{mark[n]} «{nat}»\n    entendió: {got}\n    esperaba: {can}" for n, nat, got, can in
             sorted(res["filas"], key=lambda r: {"mal": 0, "aclaró": 1, "bien": 2}[r[0]])]
    folder = J.settings["output_dir"]
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"Prueba de comprensión {datetime.date.today():%Y-%m-%d}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(lines) + "\n\nNada de esto se ejecutó: solo se le preguntó a la IA qué entendería.\n")
    return path, pct


def nl_test_voice(text, t):
    m = _NLT.search(t)
    if not m:
        return False
    if nl_test_state["busy"]:
        J.reply("Ya estoy haciendo la prueba de comprensión. Te aviso cuando termine.", "COMPRENSIÓN")
        return True
    if J.state.get("ai") != "ok":
        J.reply("Para la prueba de comprensión necesito la IA conectada (Ajustes › Inteligencia artificial).", "COMPRENSIÓN")
        return True
    full = m.group(1) == "completa"
    n = 0 if full else NL_TEST_N
    total = len(frasesnl.rows()) if full else NL_TEST_N
    J.reply(f"Le paso {total} frases dichas como habla la gente a {J._ai_cfg().get('label', 'tu IA')}, sin ejecutar nada; "
            f"tarda unos {max(1, round(total * (NL_TEST_PAUSE + 1.5) / 60))} minutos (voy despacio para no gastar tu cuota por minuto). "
            "Te aviso al terminar.", "COMPRENSIÓN")

    def work():
        nl_test_state["busy"] = True
        try:
            res = nl_test_run(n)
            if not res["n"]:
                J.notify(f"No pude hacer la prueba de comprensión: {res['corte'] or 'la IA no respondió'}.", "COMPRENSIÓN")
                return
            path, pct = nl_test_report(res)
            nl_test_state["last"] = dict(res, pct=pct, ruta=path)
            J.generated_files.add(path)
            if J.IS_WIN:
                try:
                    os.startfile(path)
                except OSError:
                    pass
            J.notify(f"Prueba de comprensión: entendí bien {res['bien'] + res['aclaro']} de {res['n']} frases ({pct} %)"
                     + (f"; se cortó antes: {res['corte']}" if res["corte"] else "") + ". Te dejé el detalle en Documentos.", "COMPRENSIÓN")
        finally:
            nl_test_state["busy"] = False
    J.start_job("Prueba de comprensión", work, "comprension")
    return True


__all__ = ['_LEAD', 'NL_K', 'NL_TEST_N', 'NL_TEST_WAIT', '_closest', 'NL_TEST_PAUSE', '_NLT', 'nl_test_report', 'nl_test_run', 'nl_test_state', 'nl_test_voice', '_CHAT', '_FILLER', '_KNOW', '_PICK', '_RETRY', '_RISKY', '_nl_ask', '_nl_do', '_starters', 'nl_catalog', 'nl_conversational', 'nl_offer', 'nl_pending', 'nl_pick', 'nl_starters', 'nl_examples', 'nl_parse', 'nl_prompt', 'nl_risky', 'nl_run', 'nl_should_try',
           'nl_state', 'nl_understand']
