"""Tu bandeja de correo (7.7): «¿qué correos importantes tengo?», «lee el de la coordinadora», «contéstale que sí».

Lee por IMAP con la misma «contraseña de aplicación» con la que Jarvis ya envía (Gmail u Outlook). Solo lee, en el
momento en que se lo pides; no borra, no mueve y no marca nada. Responder pasa por el centro de aprobaciones.
"""
import datetime
import email
import email.header
import email.utils
import html
import imaplib
import re

IMAP = {"gmail.com": "imap.gmail.com", "googlemail.com": "imap.gmail.com", "outlook.com": "outlook.office365.com",
        "hotmail.com": "outlook.office365.com", "live.com": "outlook.office365.com"}
_BULK = re.compile(r"no-?reply|noreply|newsletter|notificaci|notification|mailer|marketing|promo|boletin|news@|info@", re.I)


def _dec(v):
    out = []
    for part, enc in email.header.decode_header(v or ""):
        if isinstance(part, bytes):
            try:
                out.append(part.decode(enc or "utf-8", "replace"))
            except LookupError:
                out.append(part.decode("utf-8", "replace"))
        else:
            out.append(part)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def body_text(msg, limit=4000):
    """El texto del correo (prefiere texto plano; si solo hay HTML, lo limpia)."""
    plain, htm = "", ""
    for part in (msg.walk() if msg.is_multipart() else [msg]):
        ctype = part.get_content_type()
        if part.get("Content-Disposition", "").lower().startswith("attachment"):
            continue
        try:
            payload = part.get_payload(decode=True) or b""
            text = payload.decode(part.get_content_charset() or "utf-8", "replace")
        except Exception:
            continue
        if ctype == "text/plain" and not plain:
            plain = text
        elif ctype == "text/html" and not htm:
            htm = text
    if not plain and htm:
        plain = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)\b.*?</\1>", " ", htm, flags=re.S | re.I)))
    # quita lo citado de correos anteriores
    plain = re.split(r"\n(?:El .{5,80} escribió:|On .{5,80} wrote:)", plain)[0]
    plain = "\n".join(ln for ln in plain.splitlines() if not ln.strip().startswith(">"))
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", plain)).strip()[:limit]


def parse(raw, uid=""):
    msg = email.message_from_bytes(raw)
    name, addr = email.utils.parseaddr(_dec(msg.get("From")))
    try:
        dt = email.utils.parsedate_to_datetime(msg.get("Date"))
        if dt.tzinfo:
            dt = dt.astimezone().replace(tzinfo=None)
    except (TypeError, ValueError):
        dt = None
    return {"uid": str(uid), "de": addr.lower(), "de_nombre": name or addr.split("@")[0], "asunto": _dec(msg.get("Subject")) or "(sin asunto)",
            "fecha": dt.isoformat(timespec="minutes") if dt else "", "texto": body_text(msg),
            "msgid": (msg.get("Message-ID") or "").strip(), "masivo": bool(msg.get("List-Unsubscribe")) or bool(_BULK.search(addr))}


def fetch_recent(address, app_password, days=3, limit=25, timeout=20):
    """Los correos recibidos en los últimos días (más nuevos primero). Lanza RuntimeError con un mensaje claro."""
    host = IMAP.get(address.split("@")[-1].lower(), "imap.gmail.com")
    try:
        im = imaplib.IMAP4_SSL(host, timeout=timeout)
    except Exception as e:
        raise RuntimeError(f"no pude conectar con el servidor de correo ({e}).")
    try:
        try:
            im.login(address, app_password)
        except imaplib.IMAP4.error:
            raise RuntimeError("tu cuenta rechazó la contraseña. Usa la «contraseña de aplicación» (la misma con la que "
                               "Jarvis envía correos) y revisa que el acceso IMAP esté activado.")
        im.select("INBOX", readonly=True)                  # solo lectura: no marca nada como leído
        since = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%d-%b-%Y")
        typ, data = im.uid("search", None, f"(SINCE {since})")
        uids = (data[0] or b"").split()[-limit:][::-1]
        out = []
        for uid in uids:
            typ, parts = im.uid("fetch", uid, "(BODY.PEEK[])")
            raw = next((p[1] for p in parts if isinstance(p, tuple)), None)
            if raw:
                out.append(parse(raw, uid.decode()))
        return out
    finally:
        try:
            im.logout()
        except Exception:
            pass


def importance(m, book_addrs=()):
    """Puntuación para ordenar: personas de tu agenda primero, boletines y avisos automáticos al final."""
    s = 0.0
    if m["de"] in book_addrs:
        s += 3
    if m["masivo"]:
        s -= 3
    if re.search(r"urgente|importante|reuni[oó]n|citaci[oó]n|plazo|hoy|mañana|entrega|calificaci", m["asunto"] + " " + m["texto"][:300], re.I):
        s += 1.5
    return s


def triage_prompt(msgs):
    lines = [f"{i + 1}. De {m['de_nombre']} <{m['de']}> ({m['fecha'][5:16].replace('T', ' ')}): «{m['asunto']}» — "
             f"{m['texto'][:300].replace(chr(10), ' ')}" for i, m in enumerate(msgs)]
    return ("Eres Jarvis. Estos son los correos recientes de un docente (los más relevantes primero):\n" + "\n".join(lines) +
            "\n\nDile en voz alta, en 2 a 4 frases, cuáles son importantes y qué piden (quién, qué y para cuándo). "
            "Ignora publicidad y avisos automáticos. Sin listas ni markdown.")


def reply_prompt(m, instruction, sender_name=""):
    return ("Escribe la respuesta a este correo, en español, breve, cordial y profesional (docente en Colombia).\n"
            f"Correo de {m['de_nombre']} — asunto «{m['asunto']}»:\n{m['texto'][:2500]}\n\n"
            f"Lo que quiero responder: {instruction}\n" + (f"Firma: {sender_name}\n" if sender_name else "") +
            'Responde SOLO con JSON: {"cuerpo": "…"}')


def find(msgs, who):
    """El correo más reciente de esa persona (por nombre o dirección)."""
    w = re.sub(r"[^\w@.\s]", " ", str(who).lower()).strip()
    words = [x for x in w.split() if len(x) > 2 and x not in ("del", "las", "los", "correo", "ultimo", "último")]
    for m in msgs:
        hay = (m["de_nombre"] + " " + m["de"] + " " + m["asunto"]).lower()
        if words and all(x in hay for x in words):
            return m
    return None
