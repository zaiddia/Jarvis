"""12.11: dólar, euro y criptomonedas en vivo. «¿A cómo está el dólar?» (TRM oficial del día), «precio del euro»,
«¿cuánto vale el bitcoin?», «¿cuánto son 50 dólares en pesos?», «convierte 200 mil pesos a dólares», y los gastos en otra
moneda: «gasté 50 dólares en un curso» queda anotado en pesos con la TRM del día.
La lógica está en divisas.py. Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import json
import time

import divisas
import vidadiaria
from nucleo import J

_fx_cache = {"t": 0.0, "trm": None, "fx": {}, "crypto": {}, "ct": 0.0}


def fx_rates(need_crypto=False):
    """(TRM, vigencia, otras monedas, cripto). En caché 30 min (la TRM cambia una vez al día)."""
    now = time.time()
    if now - _fx_cache["t"] > 1800 or not _fx_cache["trm"]:
        trm = divisas.parse_trm(json.loads(J._get_text(divisas.TRM_URL)))
        fx = {}
        try:
            fx = divisas.parse_fx(json.loads(J._get_text(divisas.FX_URL)))
        except Exception:
            pass
        if not trm and fx.get("COP"):                   # sin datos.gov.co: la de referencia internacional
            trm = (fx["COP"], "", "")
        _fx_cache.update(t=now, trm=trm, fx=fx)
    if need_crypto and now - _fx_cache["ct"] > 300:
        try:
            _fx_cache.update(crypto=divisas.parse_crypto(json.loads(J._get_text(divisas.CRYPTO_URL))), ct=now)
        except Exception:
            pass
    return _fx_cache["trm"], _fx_cache["fx"], _fx_cache["crypto"]


def _rate_text(cur):
    trm, fx, crypto = fx_rates(cur in ("BTC", "ETH"))
    if not trm:
        return "No pude consultar el dólar ahora."
    if cur == "USD":
        val, desde, hasta = trm
        return (f"El dólar está a {divisas.fmt(val, 'COP')} (TRM oficial" + (f", vigente hasta el {hasta[8:10]}/{hasta[5:7]}" if hasta else "") + ").")
    per = divisas.cop_per(cur, trm[0], fx, crypto)
    if not per:
        return f"No pude consultar el precio del {divisas.NAMES.get(cur, cur)} ahora."
    if cur in ("BTC", "ETH"):
        usd = (crypto.get(cur) or {}).get("USD")
        return f"Un {divisas.NAMES[cur]} vale {divisas.fmt(per, 'COP')}" + (f" (unos {divisas.fmt(usd, 'USD')})." if usd else ".")
    return f"El {divisas.NAMES[cur][:-1]} está a {divisas.fmt(per, 'COP')}."


def money_voice(text, t):
    fe = divisas.foreign_expense(text)
    if fe:
        amt, cur, concept = fe
        try:
            trm, fx, crypto = fx_rates(cur in ("BTC", "ETH"))
            cop = divisas.convert(amt, cur, "COP", trm[0], fx, crypto) if trm else None
        except Exception:
            cop = None
        if not cop:
            J.reply(f"No pude consultar el cambio ahora para pasar {divisas.fmt(amt, cur)} a pesos. Dímelo en pesos, por ejemplo «gasté 200 mil en…».",
                    "GASTOS")
            return True
        sym = {"USD": "US$", "EUR": "€"}.get(cur, cur + " ")
        g = vidadiaria.add_expense(round(cop), f"{concept} ({sym}{amt:g})")
        tot, _by, _n = vidadiaria.spent("mes")
        J.reply(f"Anotado: {divisas.fmt(amt, cur)} son {divisas.fmt(cop, 'COP')} con el cambio de hoy, en {g['categoria']}. "
                f"Este mes llevas {vidadiaria.money(tot)}.", "GASTOS")
        return True
    conv = divisas.parse_conversion(text)
    cur = "" if conv else divisas.asks_rate(text)
    if not conv and not cur:
        return False
    if J.is_offline():
        J.reply("Sin internet no puedo consultar el cambio de hoy.", "DIVISAS")
        return True
    try:
        if conv:
            amt, src, dst = conv
            trm, fx, crypto = fx_rates("BTC" in (src, dst) or "ETH" in (src, dst))
            res = divisas.convert(amt, src, dst, trm[0], fx, crypto) if trm else None
            J.reply(f"{divisas.fmt(amt, src)} son {divisas.fmt(res, dst)} con el cambio de hoy." if res else
                    "No pude consultar ese cambio ahora.", "DIVISAS")
        else:
            J.reply(_rate_text(cur), "DIVISAS")
    except Exception as e:
        J.log_terminal(f"Divisas: {e}", "DIVISAS")
        J.reply("No pude consultar el cambio ahora; prueba en un momento.", "DIVISAS")
    return True


__all__ = ['_fx_cache', '_rate_text', 'fx_rates', 'money_voice']
