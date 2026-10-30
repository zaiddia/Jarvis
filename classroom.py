"""Google Classroom (7.8): tareas, entregas, anuncios y notas de tus cursos.

Conexión: creas en Google Cloud un «ID de cliente OAuth» de tipo «App de escritorio» (Jarvis te guía) y pegas el ID y
el secreto en Ajustes. Al pulsar «Conectar», se abre Google para que autorices; Jarvis recibe el permiso en tu propio
equipo (127.0.0.1) y guarda solo el «token de actualización». No guarda tu contraseña.

Permisos que pide: ver tus clases, ver las tareas y entregas, ver la lista de estudiantes y publicar anuncios (los
anuncios siempre pasan por el centro de aprobaciones).
"""
import base64
import datetime
import hashlib
import json
import os
import re
import secrets
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
API = "https://classroom.googleapis.com/v1/"
SCOPES = ["https://www.googleapis.com/auth/classroom.courses.readonly",
          "https://www.googleapis.com/auth/classroom.coursework.students.readonly",
          "https://www.googleapis.com/auth/classroom.rosters.readonly",
          "https://www.googleapis.com/auth/classroom.profile.emails",
          "https://www.googleapis.com/auth/classroom.announcements"]


class ClassroomError(Exception):
    pass


def norm(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    return re.sub(r"[^\w\s]", " ", "".join(c for c in t if unicodedata.category(c) != "Mn")).strip()


# ----------------------------------------------------------------------------- OAuth (con PKCE)
def pkce():
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


def auth_url(client_id, redirect_uri, state, challenge):
    return AUTH + "?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": " ".join(SCOPES),
        "access_type": "offline", "prompt": "consent", "state": state, "code_challenge": challenge,
        "code_challenge_method": "S256"})


def _post_form(url, data, opener=None):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(), method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise ClassroomError(f"Google respondió {e.code}: {body[:200]}")
    except urllib.error.URLError as e:
        raise ClassroomError(f"sin conexión con Google ({e.reason})")


def exchange(client_id, client_secret, code, redirect_uri, verifier, opener=None):
    d = _post_form(TOKEN, {"client_id": client_id, "client_secret": client_secret, "code": code, "code_verifier": verifier,
                           "grant_type": "authorization_code", "redirect_uri": redirect_uri}, opener)
    if not d.get("refresh_token"):
        raise ClassroomError("Google no devolvió el permiso permanente; vuelve a conectar.")
    return d


class Client:
    """Llamadas a la API con renovación automática del token."""

    def __init__(self, client_id, client_secret, refresh_token, opener=None):
        self.cid, self.secret, self.refresh = client_id, client_secret, refresh_token
        self.opener = opener or urllib.request.urlopen
        self.token, self.exp = "", 0.0

    def _access(self):
        if self.token and time.time() < self.exp - 60:
            return self.token
        d = _post_form(TOKEN, {"client_id": self.cid, "client_secret": self.secret, "refresh_token": self.refresh,
                               "grant_type": "refresh_token"}, self.opener)
        self.token, self.exp = d["access_token"], time.time() + int(d.get("expires_in", 3600))
        return self.token

    def call(self, method, path, params=None, body=None):
        url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
        req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"Bearer {self._access()}", "Content-Type": "application/json"})
        try:
            with self.opener(req, timeout=25) as r:
                txt = r.read().decode()
                return json.loads(txt) if txt.strip() else {}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code in (401, 403):
                raise ClassroomError("Google no da permiso: vuelve a conectar Classroom en Ajustes. " + body[:120])
            raise ClassroomError(f"Classroom respondió {e.code}: {body[:200]}")
        except urllib.error.URLError as e:
            raise ClassroomError(f"sin conexión con Classroom ({e.reason})")

    def pages(self, path, key, params=None, limit=10):
        out, params = [], dict(params or {})
        for _ in range(limit):
            d = self.call("GET", path, params)
            out += d.get(key) or []
            if not d.get("nextPageToken"):
                break
            params["pageToken"] = d["nextPageToken"]
        return out

    # --------------------------------------------------------------------- lo que usa Jarvis
    def courses(self):
        return self.pages("courses", "courses", {"teacherId": "me", "courseStates": "ACTIVE", "pageSize": 50})

    def coursework(self, course_id):
        return self.pages(f"courses/{course_id}/courseWork", "courseWork", {"pageSize": 50}, limit=3)

    def students(self, course_id):
        return {s["userId"]: s.get("profile", {}).get("name", {}).get("fullName", s["userId"])
                for s in self.pages(f"courses/{course_id}/students", "students", {"pageSize": 100})}

    def submissions(self, course_id, cw_id):
        return self.pages(f"courses/{course_id}/courseWork/{cw_id}/studentSubmissions", "studentSubmissions",
                          {"pageSize": 100})

    def announce(self, course_id, text):
        return self.call("POST", f"courses/{course_id}/announcements", body={"text": text, "state": "PUBLISHED"})


# ----------------------------------------------------------------------------- ayudas
def find_course(courses, spoken):
    """El curso que nombras («7A», «séptimo A», «matemáticas de 7A»)."""
    s = norm(spoken)
    s = re.sub(r"\bseptimo\b", "7", s)
    for word, num in (("sexto", "6"), ("octavo", "8"), ("noveno", "9"), ("decimo", "10"), ("once", "11"), ("quinto", "5")):
        s = re.sub(rf"\b{word}\b", num, s)
    s = re.sub(r"\b(\d{1,2})\s+([a-z])\b", r"\1\2", s)
    best, score = None, 0
    for c in courses:
        name = norm(c.get("name", "") + " " + c.get("section", ""))
        name = re.sub(r"\b(\d{1,2})\s+([a-z])\b", r"\1\2", name)
        toks = [t for t in s.split() if len(t) > 1]
        sc = sum(2 if re.search(rf"\b{re.escape(t)}\b", name) else 0 for t in toks)
        if sc > score:
            best, score = c, sc
    return best


def find_work(works, spoken):
    s = set(w for w in norm(spoken).split() if len(w) > 3)
    best, score = None, 0
    for w in works:
        sc = len(s & set(norm(w.get("title", "")).split()))
        if sc > score:
            best, score = w, sc
    if best is None and works:
        best = sorted(works, key=lambda w: w.get("updateTime", ""), reverse=True)[0]
    return best


def due_of(w):
    d = w.get("dueDate")
    if not d:
        return None
    t = w.get("dueTime") or {}
    try:
        return datetime.datetime(d["year"], d["month"], d["day"], t.get("hours", 23), t.get("minutes", 59))
    except (KeyError, ValueError):
        return None


def missing(subs, names):
    """Quién no ha entregado (ni le han devuelto) la tarea."""
    out = []
    for s in subs:
        if s.get("state") not in ("TURNED_IN", "RETURNED"):
            out.append(names.get(s.get("userId"), s.get("userId", "?")))
    return sorted(out)


def to_scale(points, max_points, lo=1.0, hi=5.0):
    """Puntos de Classroom → escala colombiana (1.0 a 5.0)."""
    if points is None or not max_points:
        return None
    return round(lo + (hi - lo) * max(0.0, min(1.0, float(points) / float(max_points))), 1)
