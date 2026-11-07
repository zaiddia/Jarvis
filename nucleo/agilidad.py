"""12.1: Jarvis más inteligente, veloz e interactivo.

  · Cero silencio: si la IA va a tardar, Jarvis dice al instante una frase corta («A ver…», «Voy con eso…») y la
    respuesta entra encadenada. Las frases ya están en la caché de la voz: suenan sin esperar a internet.
  · Fin de turno: si la frase quedó colgando («haz un quiz de… eh…»), espera un momento a que termines en vez de cortarte.
  · Órdenes encadenadas: «pon un temporizador de 10 minutos, abre la pizarra y muéstrales el QR» → tres órdenes.
  · Dos cerebros: lo simple lo contesta un modelo rápido de tu misma cuenta y lo difícil el potente; si el rápido
    duda, le pasa la pregunta al potente.
  · Respuestas interactivas: «¿qué pasa si Juan saca 4 en el último periodo?» llega como un panel con deslizadores,
    resultados que se recalculan, tabla y botones.
La lógica está en agil.py, cerebro.py y panel.py. Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import threading
import time

import agil
import cerebro
import panel
from nucleo import J

J.PREWARM_PHRASES.extend(a for a in agil.all_acks() if a not in J.PREWARM_PHRASES)     # quedan listas en la caché de la voz


# ============================================================================ CERO SILENCIO
class _Ack:
    def __init__(self, text):
        self.done_ev = threading.Event()
        self.said = ""
        ms = int(J.settings.get("ack_ms", 700))
        self.t = threading.Timer(ms / 1000.0, self._fire, args=(text,))
        self.t.daemon = True
        self.t.start()

    def _fire(self, text):
        if self.done_ev.is_set():
            return
        self.said = agil.ack_for(text, last=_ack_state["last"])
        _ack_state["last"] = self.said
        J.speak(self.said)
        J.log_terminal(f"(mientras pienso: «{self.said}»)", "RAPIDEZ")

    def done(self):
        self.done_ev.set()
        self.t.cancel()


class _NoAck:
    said = ""

    def done(self):
        pass


_ack_state = {"last": ""}


def ack_start(text):
    """Empieza a contar: si en ack_ms no se ha dicho nada, Jarvis dice la frase de espera. → objeto con .done()."""
    if (not J.settings.get("ack_enabled", True) or getattr(J._tl, "remote", False) or getattr(J._tl, "live", False)
            or getattr(J._tl, "capture", None) is not None or not J.settings.get("tts_enabled", True)):
        return _NoAck()
    return _Ack(text)


# ============================================================================ FIN DE TURNO
turn = {"text": "", "timer": None, "until": 0.0}


def turn_merge(final):
    """Si había una frase a medias esperando, la une con lo que acabas de decir."""
    if turn["text"] and time.time() < turn["until"] + 0.5:
        first = turn["text"]
        _turn_clear()
        merged = agil.merge(first, final)
        J.log_terminal(f"(uní tu frase: «{merged}»)", "VOZ")
        return merged
    return final


def _turn_clear():
    if turn["timer"]:
        turn["timer"].cancel()
    turn.update(text="", timer=None, until=0.0)


def turn_hold(final):
    """Si la frase quedó colgando, la guarda y espera un poco a que termines. True si la guardó."""
    if not J.settings.get("turn_smart", True) or J.dictation_on.is_set() or not agil.incomplete(final):
        return False
    hold = float(J.settings.get("turn_hold", 1.6))
    _turn_clear()
    turn.update(text=final, until=time.time() + hold)
    J.wake_until = time.time() + hold                 # lo que digas ahora sigue siendo para Jarvis, sin repetir «Jarvis»
    J.convo["kind"] = "turno"
    J.refresh_mode()

    def go():
        if turn["text"] == final:
            _turn_clear()
            J.log_terminal("(no siguió la frase: la atiendo así)", "VOZ")
            J.submit_command(final, "voz")
    turn["timer"] = threading.Timer(hold + 0.4, go)
    turn["timer"].daemon = True
    turn["timer"].start()
    J.log_terminal(f"(«{final}»… espero a que termines)", "VOZ")
    return True


# ============================================================================ ÓRDENES ENCADENADAS
def chain_split(text):
    if not J.settings.get("chain_enabled", True) or getattr(J._tl, "chained", False) or J.dictation_on.is_set():
        return [text]
    return agil.split(text)


def run_chain(parts):
    J.log_terminal("Varias órdenes en una frase: " + " | ".join(parts), "COMPRENSIÓN")
    J._tl.chained = True
    try:
        for p in parts:
            J.process_command(p)
    finally:
        J._tl.chained = False


# ============================================================================ DOS CEREBROS
brain = {"key": "", "fast": "", "checking": False, "last": ""}


def fast_model():
    """El modelo rápido de tu cuenta: el de Ajustes, o uno elegido solo de tu lista de modelos. "" = no hay."""
    if not J.settings.get("brain_enabled", True):
        return ""
    want = str(J.settings.get("ai_fast_model", "")).strip()
    if want == "off":
        return ""
    cfg = J._ai_cfg()
    if cfg["kind"] == "ollama" or cfg.get("offline"):
        return ""
    if want:
        return want if want != cfg["model"] else ""
    key = f"{cfg['ai_provider']}|{cfg['model']}"
    if brain["key"] != key and not brain["checking"]:
        brain["checking"] = True

        def look():
            try:
                brain["fast"] = cerebro.fast_model_for(cfg["model"], J.ai_list_models(cfg))
            except Exception:
                brain["fast"] = ""
            brain["key"] = key
            brain["checking"] = False
            if brain["fast"]:
                J.log_terminal(f"Dos cerebros: lo simple lo contesta {brain['fast']}; lo difícil, {cfg['model']}.", "IA")
        threading.Thread(target=look, daemon=True, name="cerebro-rapido").start()
        return ""
    return brain["fast"] if brain["key"] == key else ""


def brain_for(text):
    """El modelo para esta pregunta: el rápido si es simple (y hay uno), o "" (el principal)."""
    if cerebro.classify(text) != "rapido":
        brain["last"] = "profundo"
        return ""
    fm = fast_model()
    brain["last"] = "rapido" if fm else "profundo"
    return fm


# ============================================================================ RESPUESTAS INTERACTIVAS
def panel_answer(text):
    """Responde con un panel interactivo en el HUD. True si lo hizo."""
    if not J.settings.get("panel_enabled", True) or getattr(J._tl, "remote", False) or J.state.get("ai") != "ok":
        return False
    ack = ack_start(text)
    try:
        raw = J.ai_chat([{"role": "system", "content": J.settings["system_prompt"] + J._user_ctx(text)},
                         {"role": "user", "content": panel.prompt(text)}], json_mode=True, max_tokens=2500)
        p = panel.clean(J._extract_json(raw))
    except Exception as e:
        ack.done()
        J.log_terminal(f"Panel interactivo: {e}; respondo normal.", "AVISO")
        return False
    ack.done()
    J.socketio.emit("panel", p)
    J.reply(p["resumen"] or f"Te dejé «{p['titulo']}» en el panel: mueve los valores y mira cómo cambia.", "PANEL")
    return True


__all__ = ['_Ack', '_NoAck', '_ack_state', '_turn_clear', 'ack_start', 'agil', 'brain', 'brain_for', 'cerebro', 'chain_split', 'fast_model',
           'panel', 'panel_answer', 'run_chain', 'turn', 'turn_hold', 'turn_merge']
