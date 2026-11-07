"""Acciones de la ventana (12.10): lo que haces a mano con el teclado, como orden de voz. Lógica pura.

Cada orden es una acción FIJA (un atajo de teclado conocido) sobre la ventana que nombras o la que tienes delante:
nunca teclea texto ni mueve el mouse por su cuenta. «Cierra la pestaña del explorador» pone al frente el Explorador
y cierra su pestaña; «cierra la pestaña de Chrome», la de Chrome.
"""
import re
import unicodedata

# programa → procesos (y clase de ventana del Explorador)
APPS = {
    "explorador": ("explorer.exe",), "explorador de archivos": ("explorer.exe",), "carpeta": ("explorer.exe",), "archivos": ("explorer.exe",),
    "chrome": ("chrome.exe",), "google chrome": ("chrome.exe",), "edge": ("msedge.exe",), "firefox": ("firefox.exe",), "brave": ("brave.exe",),
    "opera": ("opera.exe",), "navegador": ("chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"),
    "terminal": ("windowsterminal.exe",), "consola": ("windowsterminal.exe",), "bloc de notas": ("notepad.exe",), "notepad": ("notepad.exe",),
    "visual studio code": ("code.exe",), "vs code": ("code.exe",), "code": ("code.exe",), "word": ("winword.exe",), "excel": ("excel.exe",),
    "powerpoint": ("powerpnt.exe",),
}
TABBED = {"explorer.exe", "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "windowsterminal.exe", "notepad.exe", "code.exe"}
EXPLORER_CLASS = "CabinetWClass"

TAB_KEYS = {"cerrar": ("ctrl", "w"), "nueva": ("ctrl", "t"), "siguiente": ("ctrl", "tab"), "anterior": ("ctrl", "shift", "tab"),
            "reabrir": ("ctrl", "shift", "t")}
TAB_SAID = {"cerrar": "Cerré la pestaña", "nueva": "Abrí una pestaña nueva", "siguiente": "Pestaña siguiente", "anterior": "Pestaña anterior",
            "reabrir": "Reabrí la última pestaña cerrada"}

# (id, patrón, teclas, solo_en, respuesta). solo_en: "explorer" (Explorador), "" (la ventana del frente) o "sistema" (Windows).
ACTIONS = [
    ("carpeta_arriba", r"\b(?:sube|subir|ve|vete|ir)\s+(?:a\s+)?(?:una\s+carpeta|la\s+carpeta\s+de\s+arriba|un\s+nivel)\b|\bcarpeta\s+(?:de\s+arriba|superior|padre)\b",
     ("alt", "up"), "explorer", "Subí una carpeta."),
    ("carpeta_atras", r"\b(?:carpeta\s+anterior|vuelve\s+a\s+la\s+carpeta\s+anterior|atras\s+en\s+el\s+explorador)\b", ("alt", "left"), "explorer",
     "Volví a la carpeta anterior."),
    ("carpeta_nueva", r"\b(?:crea|haz|nueva)\s+(?:una\s+)?(?:carpeta\s+nueva|nueva\s+carpeta)\b|^nueva carpeta$", ("ctrl", "shift", "n"), "explorer",
     "Creé una carpeta nueva: escribe su nombre."),
    ("vista_detalles", r"\b(?:vista|ver)\s+(?:de\s+|en\s+)?detalles\b|\bmuestra(?:lo)?\s+en\s+detalles\b", ("ctrl", "shift", "6"), "explorer",
     "Vista de detalles."),
    ("vista_iconos", r"\b(?:iconos\s+grandes|vista\s+de\s+iconos)\b", ("ctrl", "shift", "2"), "explorer", "Iconos grandes."),
    ("vista_previa", r"\b(?:panel\s+de\s+)?vista\s+previa\b", ("alt", "p"), "explorer", "Vista previa."),
    ("renombrar", r"^(?:jarvis\s+)?(?:renombra|cambia(?:le)?\s+el\s+nombre)(?:\s+(?:esto|eso|el archivo|la carpeta|lo seleccionado))?$", ("f2",), "",
     "Listo para renombrar: escribe el nombre nuevo."),
    ("propiedades", r"^(?:jarvis\s+)?(?:muestra\s+las\s+)?propiedades(?:\s+del?\s+(?:archivo|carpeta|esto))?$", ("alt", "enter"), "", "Propiedades."),
    ("guardar", r"^(?:jarvis\s+)?guarda(?:r)?\s+(?:el\s+archivo|el\s+documento|esto|los\s+cambios|lo\s+que\s+hice)$", ("ctrl", "s"), "", "Guardado."),
    ("seleccionar_todo", r"^(?:jarvis\s+)?selecciona(?:r)?\s+todo$", ("ctrl", "a"), "", "Seleccioné todo."),
    ("copiar", r"^(?:jarvis\s+)?copia(?:r)?\s+(?:eso|esto|lo\s+seleccionado|la\s+seleccion)$", ("ctrl", "c"), "", "Copiado."),
    ("pegar", r"^(?:jarvis\s+)?pega(?:r)?\s+(?:eso|esto|aqui|lo\s+copiado)$", ("ctrl", "v"), "", "Pegado."),
    ("imprimir", r"^(?:jarvis\s+)?imprime\s+(?:esto|eso|el\s+documento|la\s+pagina)$", ("ctrl", "p"), "", "Te abrí la ventana de impresión."),
    ("zoom_mas", r"^(?:jarvis\s+)?(?:acerca|amplia|agranda|haz\s+zoom)(?:\s+(?:la\s+pagina|el\s+texto|esto|la\s+letra))?$", ("ctrl", "+"), "", "Más grande."),
    ("zoom_menos", r"^(?:jarvis\s+)?(?:aleja|achica|reduce)(?:\s+(?:la\s+pagina|el\s+texto|esto|la\s+letra))?$", ("ctrl", "-"), "", "Más pequeño."),
    ("zoom_normal", r"\b(?:zoom|tamano)\s+normal\b|\brestablece\s+el\s+zoom\b", ("ctrl", "0"), "", "Tamaño normal."),
    ("ventana_izq", r"\b(?:pon|manda|mueve|ajusta)\s+(?:la\s+|esta\s+)?ventana\s+(?:a\s+la\s+|al\s+lado\s+)?izquierd[oa]\b", ("win", "left"), "",
     "Ventana a la izquierda."),
    ("ventana_der", r"\b(?:pon|manda|mueve|ajusta)\s+(?:la\s+|esta\s+)?ventana\s+(?:a\s+la\s+|al\s+lado\s+)?derech[oa]\b", ("win", "right"), "",
     "Ventana a la derecha."),
    ("otro_monitor", r"\b(?:pasa|manda|mueve|lleva)\s+(?:la\s+|esta\s+)?ventana\s+(?:a\s+la\s+|al\s+)?(?:otra\s+pantalla|otro\s+monitor|segunda\s+pantalla|"
                     r"videobeam|proyector)\b", ("win", "shift", "right"), "", "La pasé a la otra pantalla."),
    ("escritorio_nuevo", r"\b(?:crea|abre|nuevo)\s+(?:un\s+)?(?:escritorio\s+virtual(?:\s+nuevo)?|nuevo\s+escritorio)\b", ("win", "ctrl", "d"), "sistema",
     "Escritorio virtual nuevo."),
    ("escritorio_sig", r"\b(?:siguiente|otro)\s+escritorio\b|\bescritorio\s+(?:de\s+la\s+)?derecha\b", ("win", "ctrl", "right"), "sistema", "Siguiente escritorio."),
    ("escritorio_ant", r"\bescritorio\s+anterior\b|\bescritorio\s+(?:de\s+la\s+)?izquierda\b", ("win", "ctrl", "left"), "sistema", "Escritorio anterior."),
    ("escritorio_cerrar", r"\bcierra\s+(?:este\s+|el\s+)?escritorio\s+virtual\b", ("win", "ctrl", "f4"), "sistema", "Cerré el escritorio virtual."),
    ("vista_tareas", r"\b(?:vista\s+de\s+tareas|muestra(?:me)?\s+todas\s+las\s+ventanas)\b", ("win", "tab"), "sistema", "Vista de tareas."),
    ("portapapeles", r"\b(?:historial\s+del\s+portapapeles|abre\s+el\s+portapapeles|lo\s+que\s+he\s+copiado)\b", ("win", "v"), "sistema",
     "Historial del portapapeles."),
    ("recorte", r"\b(?:recorte\s+de\s+pantalla|recorta\s+(?:la\s+)?pantalla|captura\s+de\s+una\s+parte|captura\s+parcial)\b", ("win", "shift", "s"),
     "sistema", "Elige la parte de la pantalla."),
    ("emojis", r"\b(?:abre\s+los\s+emojis|panel\s+de\s+emojis|ponme\s+un\s+emoji)\b", ("win", "."), "sistema", "Panel de emojis."),
    ("explorador", r"^(?:jarvis\s+)?abre\s+(?:el\s+)?explorador(?:\s+de\s+archivos)?$", ("win", "e"), "sistema", "Abrí el Explorador de archivos."),
]
_COMPILED = [(a, re.compile(p), k, s, r) for a, p, k, s, r in ACTIONS]
_TAB = re.compile(r"\b(cierra|cerrar|abre|abreme|nueva|siguiente|otra|anterior|reabre|recupera)\b.*?\bpesta[nñ]a\b(?:\s+(?:nueva|siguiente|anterior))?"
                  r"(?:\s+(?:del?|en\s+el|en\s+la|en)\s+(.+))?$")


def norm(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s+.\-]", " ", "".join(c for c in t if unicodedata.category(c) != "Mn"))).strip()


def app_procs(name):
    """«el explorador», «Chrome» → procesos; () si no es un programa conocido."""
    n = re.sub(r"^(?:el|la|los|las)\s+", "", norm(name)).strip()
    return APPS.get(n, ())


def parse_tab(t):
    """«cierra la pestaña del explorador» → {"accion": "cerrar", "app": "explorador"}; None si no es de pestañas."""
    t = norm(t)
    m = _TAB.search(t)
    if not m:
        return None
    v = m.group(1)
    whole = t
    accion = ("cerrar" if v.startswith("cerr") or v == "cierra" else "reabrir" if v in ("reabre", "recupera") else
              "siguiente" if v in ("siguiente", "otra") else "anterior" if v == "anterior" else "nueva")
    if re.search(r"pesta[nñ]a\s+siguiente", whole):
        accion = "siguiente"
    elif re.search(r"pesta[nñ]a\s+anterior", whole):
        accion = "anterior"
    elif re.search(r"pesta[nñ]a\s+nueva|nueva\s+pesta[nñ]a", whole) and accion != "cerrar":
        accion = "nueva"
    app = (m.group(2) or "").strip()
    if app and not app_procs(app):
        return None if accion != "cerrar" else {"accion": accion, "app": ""}
    return {"accion": accion, "app": re.sub(r"^(?:el|la)\s+", "", app)}


def parse_action(t):
    """→ (id, teclas, solo_en, respuesta) o None."""
    t = norm(t)
    for aid, rx, keys, scope, said in _COMPILED:
        if rx.search(t):
            return aid, keys, scope, said
    return None


def pick_window(windows, procs, explorer_only=False):
    """De skills.list_windows(): la primera ventana (la más reciente) de esos procesos."""
    for w in windows:
        proc = str(w.get("proc", "")).lower()
        if proc in procs and (not explorer_only or w.get("cls") == EXPLORER_CLASS or proc != "explorer.exe"):
            if proc == "explorer.exe" and w.get("cls") != EXPLORER_CLASS:
                continue                                 # el escritorio y la barra de tareas también son «explorer.exe»
            return w
    return None
