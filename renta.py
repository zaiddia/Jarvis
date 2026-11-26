"""12.65: ¿debo declarar renta? Lógica pura, sin Jarvis.

Los topes (art. 592 a 594-3 del Estatuto Tributario) se miden en UVT del AÑO GRAVABLE: el año 2025 se declara en 2026 con
la UVT de 2025; el año 2026 se declara en 2027 con la UVT de 2026. Valores de la DIAN (resoluciones anuales).
"""
UVT = {2023: 42412, 2024: 47065, 2025: 49799, 2026: 52374}

TOPES = (                      # (clave, UVT, «igual o superior» o «superior», qué es)
    ("ingresos", 1400, True, "ingresos brutos del año"),
    ("patrimonio", 4500, False, "patrimonio bruto al 31 de diciembre"),
    ("tarjeta", 1400, False, "consumos con tarjeta de crédito"),
    ("compras", 1400, False, "compras y consumos totales"),
    ("consignaciones", 1400, False, "consignaciones, depósitos e inversiones financieras"),
)


def topes(year):
    """→ [(clave, pesos, inclusivo, qué es)] para el año gravable, o None si no tengo la UVT de ese año."""
    u = UVT.get(int(year))
    if not u:
        return None
    return [(k, n * u, inc, what) for k, n, inc, what in TOPES]


def check(year, valores):
    """valores: {clave: pesos} (lo que se sepa). → {"obliga": bool|None, "motivos": [...], "faltan": [...], "topes": [...]}."""
    tp = topes(year)
    if tp is None:
        return {"obliga": None, "motivos": [], "faltan": [], "topes": []}
    motivos, faltan = [], []
    for k, lim, inc, what in tp:
        v = valores.get(k)
        if v is None:
            faltan.append((k, lim, what))
        elif (v >= lim if inc else v > lim):
            motivos.append((k, v, lim, what))
    obliga = True if motivos else (False if not faltan else None)
    return {"obliga": obliga, "motivos": motivos, "faltan": faltan, "topes": tp}


def pesos(n):
    return "$" + f"{int(round(n)):,}".replace(",", ".")


def spoken(year, res):
    if res["obliga"] is None and not res["topes"]:
        return f"Aún no tengo el valor de la UVT de {year}."
    decl = int(year) + 1
    if res["obliga"]:
        why = "; ".join(f"tus {what} ({pesos(v)}) pasan el tope de {pesos(lim)}" for _k, v, lim, what in res["motivos"][:2])
        return f"Sí: por el año {year} debes declarar renta en {decl}, porque {why}."
    base = f"Por lo que me mostraste, por el año {year} no pasas el tope de ingresos ({pesos(res['topes'][0][1])})"
    if res["faltan"]:
        return (base + ", pero me falta saber " + ", ".join(what for _k, _l, what in res["faltan"][:3]) +
                ". Si alguno pasa su tope, también tendrías que declarar en " + f"{decl}.")
    return base + f" ni ningún otro: en principio no estás obligado a declarar en {decl}."


DEDUCCIONES = (
    "dependientes económicos (hijos, cónyuge o padres a cargo): certificado o registro civil",
    "intereses del crédito de vivienda o leasing habitacional: certificado del banco",
    "medicina prepagada o seguro de salud: certificado de la entidad",
    "aportes voluntarios a pensión y a cuentas AFC o AVC: certificado del fondo o del banco",
    "intereses de crédito educativo del ICETEX",
    "GMF (4 x 1000) pagado: certificado del banco (se descuenta la mitad)",
    "facturas electrónicas de tus compras con tu cédula (dan un beneficio pequeño)",
)

PAPELES = (
    "certificado de ingresos y retenciones (formulario 220) del colegio o la secretaría de educación",
    "certificados de tus cuentas, CDT e inversiones al 31 de diciembre (saldos e intereses)",
    "certificados de tus deudas al 31 de diciembre (créditos, tarjetas)",
    "avalúo catastral de tu casa o lote, y el valor de tu vehículo",
    "certificados de las deducciones que vayas a usar",
    "tu RUT actualizado",
)


def certificado_prompt():
    return ("Este es un certificado de ingresos y retenciones, u otro certificado tributario de Colombia. Extrae los valores "
            "en pesos. Responde SOLO con JSON: {\"ano\": number|null, \"ingresos\": number|null (total de pagos o ingresos "
            "brutos), \"retencion\": number|null, \"aportes_salud\": number|null, \"aportes_pension\": number|null, "
            "\"saldo\": number|null (si es certificado bancario: saldo al 31 de diciembre), \"entidad\": str|null}. "
            "No inventes: si un valor no está, null.")
