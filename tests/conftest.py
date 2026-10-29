"""Arnés de las pruebas de comprensión de Jarvis.

Importa jarvis.py de verdad, pero sustituye lo que tendría efectos (hablar, ejecutar acciones del PC,
llamar a la IA, internet, abrir ventanas) por grabadoras. Así cada prueba sabe QUIÉN atendió una frase
(una acción del PC, una rutina, un módulo o la IA) sin que el equipo haga nada.
"""
import os
import sys
import tempfile

# Ajustes, notas y memoria de prueba en una carpeta temporal (nunca los del usuario).
_TMP = tempfile.mkdtemp(prefix="jarvis-pruebas-")
os.environ["APPDATA"] = _TMP
os.environ["JARVIS_PRUEBAS"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

_real_stdout = sys.__stdout__


class Recorder:
    def __init__(self):
        self.clear()

    def clear(self):
        self.replies, self.skills, self.routines, self.ai, self.other = [], [], [], [], []

    def who(self):
        if self.skills:
            return "skill:" + self.skills[0][0]
        if self.routines:
            return "rutina:" + self.routines[0]
        if self.ai:
            return "IA:orden" if any(route for _, route in self.ai) else "IA"
        if self.other:
            return self.other[0]
        if self.replies:
            return self.replies[0][1]
        return "nada"

    def said(self):
        return " ".join(t for t, _ in self.replies)


@pytest.fixture(scope="session")
def jv():
    import jarvis
    sys.stdout = sys.stderr = _real_stdout          # jarvis manda la salida a su registro: la devolvemos
    rec = Recorder()
    jarvis._rec = rec
    jarvis.reply = lambda text, origin="JARVIS": rec.replies.append((str(text), origin))
    jarvis.speak = lambda *a, **k: None
    jarvis.push_chat = lambda *a, **k: None
    jarvis.socketio.emit = lambda *a, **k: None

    def run_skill(name, args, confirmed=False):
        sk = jarvis.skills.REGISTRY.get(name)
        if sk is None:
            return False
        if getattr(jarvis._tl, "remote", False) and jarvis.remote_blocked(name, args):
            rec.other.append("bloqueado")              # igual que el real: desde el celular, no
            return True
        if sk.dangerous and not confirmed:          # igual que el real: pide confirmación
            jarvis.pending.update(skill=name, args=args, expires=jarvis.time.time() + 25)
            rec.replies.append((sk.confirm_text(args), "CONFIRMAR"))
            rec.other.append("confirmar:" + name)
            return True
        rec.skills.append((name, dict(args or {})))
        return True
    jarvis.run_skill = run_skill
    jarvis.run_routine = lambda r: rec.routines.append(r["nombre"])
    jarvis.ask_ai = lambda prompt, route=False: (rec.ai.append((prompt, route)), ("chat", "(respuesta de la IA)"))[1]
    jarvis.answer_question_streaming = lambda prompt: rec.ai.append((prompt, False))
    jarvis.run_system_check = lambda speak_it=True: (rec.other.append("prueba completa"), [])[1]
    for name in ("describe_screen", "screen_assist", "read_selection_aloud", "morning_report", "generate_steam_doc",
                 "open_settings_window", "hud_show", "hud_hide", "set_copilot", "start_review", "web_search",
                 "make_backup", "install_update", "show_system_check"):
        if hasattr(jarvis, name):
            setattr(jarvis, name, (lambda n: lambda *a, **k: rec.other.append(n))(name))
    jarvis.add_timer = lambda seconds, label="": rec.other.append("temporizador")
    jarvis.trigger_alarm = lambda seconds, label="Recordatorio": rec.other.append("recordatorio")

    jarvis.webbrowser.open = lambda *a, **k: rec.other.append("abrir")
    jarvis.ai_chat = lambda *a, **k: (_ for _ in ()).throw(jarvis.AIError("sin IA en las pruebas", kind="config"))

    def no_net(*a, **k):
        raise OSError("sin internet en las pruebas")
    jarvis._get_text = no_net
    jarvis.check_updates = lambda: {"newer": False, "version": jarvis.VERSION, "notes": ""}
    jarvis.telegram_send = lambda *a, **k: True
    return jarvis


@pytest.fixture
def ask(jv):
    """ask(frase) -> (quién la atendió, lo que dijo)."""
    def _ask(text, phone=False):
        rec = jv._rec
        rec.clear()
        if phone:                                  # como un mensaje de Telegram: por el telegram_run real
            out = jv.telegram_run(text)
            if not (rec.replies or rec.skills or rec.ai or rec.other or rec.routines):
                rec.other.append("bloqueado" if out.startswith("Por seguridad") else "nada")
                rec.replies.append((out, "TELEGRAM"))
        else:
            jv.process_command(text)
        return rec.who(), rec.said()
    return _ask


# En GitHub, los fallos salen como anotaciones (se ven en la página de la compilación), de diez en diez.
_failures = []


def pytest_runtest_logreport(report):
    if report.failed and report.when == "call":
        msg = str(report.longrepr).strip().splitlines()
        last = next((l for l in reversed(msg) if "AssertionError" in l or l.startswith("E ")), msg[-1] if msg else "")
        _failures.append(f"{report.nodeid.split('::')[-1]}: {last.strip()[:300]}")


def pytest_sessionfinish(session, exitstatus):
    if os.environ.get("GITHUB_ACTIONS") != "true" or not _failures:
        return
    for k in range(0, min(len(_failures), 100), 10):
        chunk = "\n".join(_failures[k:k + 10]).replace("%", "%25").replace("\r", "").replace("\n", "%0A")
        _real_stdout.write(f"::error title=Pruebas de Jarvis ({k + 1}-{min(k + 10, len(_failures))} de {len(_failures)})::{chunk}\n")
    _real_stdout.flush()
