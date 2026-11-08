"""Google Calendar y Google Drive con tu cuenta de Google (8.7).

Calendar: crea eventos directo en tu calendario (con enlace de Meet si la reunión es virtual) y lee tus próximos
eventos sin el enlace .ics. Drive: sube a una carpeta «Jarvis» de tu Drive los materiales que Jarvis crea (puede
convertirlos a Documentos o Presentaciones de Google). Con el permiso «drive.file», Jarvis solo ve los archivos que él
mismo sube: nunca el resto de tu Drive.
"""
import datetime
import json
import mimetypes
import os
import uuid

CAL_API = "https://www.googleapis.com/calendar/v3/"
DRIVE_API = "https://www.googleapis.com/drive/v3/"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
SCOPES = ["https://www.googleapis.com/auth/calendar.events", "https://www.googleapis.com/auth/drive.file"]
TZ = "America/Bogota"
GOOGLE_TYPES = {".docx": "application/vnd.google-apps.document", ".pptx": "application/vnd.google-apps.presentation",
                ".xlsx": "application/vnd.google-apps.spreadsheet"}


def has(granted, scope):
    return scope in str(granted or "")


# ----------------------------------------------------------------------------- Calendar
def event_body(ev, meet=False):
    """ev con el formato de eventos.validate → cuerpo para la API de Calendar."""
    d = datetime.date.fromisoformat(ev["fecha"])
    body = {"summary": ev["titulo"], "location": ev.get("lugar", ""), "description": ev.get("descripcion", ""),
            "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 30}]}}
    if ev.get("hora"):
        h, m = map(int, ev["hora"].split(":"))
        a = datetime.datetime.combine(d, datetime.time(h, m))
        b = a + datetime.timedelta(minutes=int(ev.get("duracion_min") or 60))
        body["start"] = {"dateTime": a.isoformat(timespec="seconds"), "timeZone": TZ}
        body["end"] = {"dateTime": b.isoformat(timespec="seconds"), "timeZone": TZ}
    else:
        body["start"] = {"date": d.isoformat()}
        body["end"] = {"date": (d + datetime.timedelta(days=1)).isoformat()}
    if meet:
        body["conferenceData"] = {"createRequest": {"requestId": uuid.uuid4().hex,
                                                    "conferenceSolutionKey": {"type": "hangoutsMeet"}}}
    return body


def create_event(client, ev, meet=False):
    path = "calendars/primary/events" + ("?conferenceDataVersion=1" if meet else "")
    return client.call("POST", path, body=event_body(ev, meet), base=CAL_API)


def meet_link(created):
    for e in (created.get("conferenceData") or {}).get("entryPoints") or []:
        if e.get("entryPointType") == "video":
            return e.get("uri", "")
    return created.get("hangoutLink", "")


def list_events(client, days=32, now=None):
    """Eventos de ayer a +days con el mismo formato que calendario.fetch."""
    now = now or datetime.datetime.now().astimezone()
    start = (now - datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = now + datetime.timedelta(days=days)
    d = client.call("GET", "calendars/primary/events", {"timeMin": start.isoformat(), "timeMax": end.isoformat(),
                                                       "singleEvents": "true", "orderBy": "startTime", "maxResults": 250},
                    base=CAL_API)
    out = []
    for e in d.get("items") or []:
        if e.get("status") == "cancelled":
            continue
        s, f = e.get("start", {}), e.get("end", {})
        allday = "date" in s and "dateTime" not in s
        if allday:
            a, b = s["date"], f.get("date", s["date"])
        else:
            a = datetime.datetime.fromisoformat(s["dateTime"].replace("Z", "+00:00")).astimezone().isoformat()
            b = datetime.datetime.fromisoformat(f.get("dateTime", s["dateTime"]).replace("Z", "+00:00")).astimezone().isoformat()
        out.append({"uid": "g:" + e.get("id", ""), "titulo": (e.get("summary") or "(sin título)").strip(),
                    "lugar": (e.get("location") or "").strip(), "inicio": a, "fin": b, "todo_el_dia": allday, "cal": "google"})
    return out


# ----------------------------------------------------------------------------- Drive
def multipart(meta, data, mime):
    bnd = "jarvis" + uuid.uuid4().hex
    body = (f"--{bnd}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(meta)}\r\n"
            f"--{bnd}\r\nContent-Type: {mime}\r\n\r\n").encode() + data + f"\r\n--{bnd}--\r\n".encode()
    return body, f"multipart/related; boundary={bnd}"


def ensure_folder(client, folder_id=""):
    """Id de la carpeta «Jarvis» (la crea si no existe o si la borraste)."""
    if folder_id:
        try:
            f = client.call("GET", f"files/{folder_id}", {"fields": "id,trashed"}, base=DRIVE_API)
            if not f.get("trashed"):
                return folder_id
        except Exception:
            pass
    f = client.call("POST", "files", {"fields": "id"}, body={"name": "Jarvis", "mimeType": "application/vnd.google-apps.folder"},
                    base=DRIVE_API)
    return f["id"]


def upload(client, path, folder_id, convert=False):
    ext = os.path.splitext(path)[1].lower()
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    name = os.path.basename(path)
    meta = {"name": os.path.splitext(name)[0] if convert and ext in GOOGLE_TYPES else name, "parents": [folder_id]}
    if convert and ext in GOOGLE_TYPES:
        meta["mimeType"] = GOOGLE_TYPES[ext]
    with open(path, "rb") as f:
        body, ctype = multipart(meta, f.read(), mime)
    return client.raw("POST", UPLOAD + "?uploadType=multipart&fields=id,name,webViewLink,mimeType", body, ctype)


def ensure_subfolder(client, parent, name, folder_id=""):
    if folder_id:
        try:
            f = client.call("GET", f"files/{folder_id}", {"fields": "id,trashed"}, base=DRIVE_API)
            if not f.get("trashed"):
                return folder_id
        except Exception:
            pass
    f = client.call("POST", "files", {"fields": "id"}, body={"name": name, "parents": [parent],
                                                              "mimeType": "application/vnd.google-apps.folder"}, base=DRIVE_API)
    return f["id"]


def list_folder(client, folder_id):
    """Los archivos (que subió Jarvis) de una carpeta, más nuevos primero."""
    d = client.call("GET", "files", {"q": f"'{folder_id}' in parents and trashed=false", "orderBy": "createdTime desc",
                                     "fields": "files(id,name,createdTime,size)", "pageSize": 100}, base=DRIVE_API)
    return d.get("files") or []


def download(client, file_id, limit=64 * 1024 * 1024):
    """12.8: el contenido de un archivo que subió Jarvis (por ejemplo, una copia de seguridad). → bytes."""
    import urllib.error
    import urllib.request
    req = urllib.request.Request(DRIVE_API + f"files/{file_id}?alt=media", headers={"Authorization": f"Bearer {client._access()}"})
    try:
        with client.opener(req, timeout=120) as r:
            return r.read(limit)
    except urllib.error.HTTPError as e:
        raise OSError(f"Google respondió {e.code} al descargar")
    except urllib.error.URLError as e:
        raise OSError(f"sin conexión con Google ({e.reason})")


def delete(client, file_id):
    client.call("DELETE", f"files/{file_id}", base=DRIVE_API)


def share_link(client, file_id):
    """Cualquiera con el enlace puede verlo (solo lectura)."""
    client.call("POST", f"files/{file_id}/permissions", body={"role": "reader", "type": "anyone"}, base=DRIVE_API)
    f = client.call("GET", f"files/{file_id}", {"fields": "webViewLink"}, base=DRIVE_API)
    return f.get("webViewLink", "")


# 12.16.2: sin la cuenta de Google conectada, un mensaje claro en vez de «'NoneType' object has no attribute 'call'»
NO_GOOGLE = ("tu cuenta de Google no está conectada. Ve a Ajustes › Cuentas y mensajes › Cuenta de Google y pulsa «Conectar con Google» "
             "(con el permiso de Drive)")


def needs_client(fn):
    import functools

    import classroom

    @functools.wraps(fn)
    def wrap(client, *a, **k):
        if client is None:
            raise classroom.ClassroomError(NO_GOOGLE)
        return fn(client, *a, **k)
    return wrap


for _n in ("create_event", "list_events", "ensure_folder", "upload", "ensure_subfolder", "list_folder", "download", "delete", "share_link"):
    globals()[_n] = needs_client(globals()[_n])
