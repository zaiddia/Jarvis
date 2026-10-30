"""Jarvis dentro de Windows: menú del clic derecho, enlaces jarvis://, Win+R «jarvis», lista de saltos de la
barra de tareas y notificaciones nativas.

Todo va en la parte del registro del usuario (HKEY_CURRENT_USER): no pide permisos de administrador, no
toca el Explorador por dentro y se quita entero con remove(). jarvis.py decide cuándo instalarlo; aquí está
el plan (comprobable en cualquier sistema) y la parte que habla con Windows.
"""
import base64
import os
import re
import subprocess
import urllib.parse
from xml.sax.saxutils import escape as _xml

IS_WIN = os.name == "nt"
APP_ID = "Zaiddia.Jarvis"                   # identidad de Jarvis para la barra de tareas y las notificaciones
SCHEME = "jarvis"
CREATE_NO_WINDOW = 0x08000000 if IS_WIN else 0

# El submenú «Jarvis ›» del clic derecho (escritorio y fondo de carpetas) y la lista de saltos del icono.
MENU = [
    ("01mostrar", "Mostrar Jarvis", "jarvis://mostrar"),
    ("02escribir", "Escribir una orden…", "jarvis://escribir"),
    ("03clase", "Modo clase", "jarvis://rutina/Modo clase"),
    ("04timer", "Temporizador de 5 minutos", "jarvis://temporizador/5"),
    ("05pendiente", "¿Qué tengo pendiente?", "jarvis://orden/qué tengo pendiente"),
    ("06mic", "Pausar o reanudar el micrófono", "jarvis://microfono"),
    ("07prueba", "Prueba completa", "jarvis://prueba"),
    ("08ajustes", "Ajustes de Jarvis", "jarvis://ajustes"),
]
JUMP = [m for m in MENU if m[0] in ("02escribir", "03clase", "04timer", "06mic", "08ajustes")]

# Acciones que entiende un enlace jarvis://acción/argumento
ACTIONS = {"mostrar", "ocultar", "alternar", "escuchar", "escribir", "rutina", "temporizador", "orden", "microfono", "prueba", "ajustes",
           "posponer", "bienvenida"}
MAX_ARG = 300

CLASSES = r"Software\Classes"
KEYS_OWNED = [                               # lo que remove() borra (y solo esto)
    CLASSES + r"\DesktopBackground\Shell\Jarvis",
    CLASSES + r"\Directory\Background\shell\Jarvis",
    CLASSES + r"\jarvis",
    CLASSES + "\\AppUserModelId\\" + APP_ID,
    r"Software\Microsoft\Windows\CurrentVersion\App Paths\jarvis.exe",
]


def parse_link(url):
    """«jarvis://rutina/Modo%20clase» → ("rutina", "Modo clase"). None si no es un enlace válido."""
    url = str(url or "").strip().strip('"')
    m = re.match(r"^jarvis:(?://)?([a-z]+)/?(.*)$", url, re.I)
    if not m:
        return None
    action = m.group(1).lower()
    if action not in ACTIONS:
        return None
    arg = urllib.parse.unquote(m.group(2)).strip().strip("/")
    arg = re.sub(r"[\x00-\x1f\x7f]", " ", arg)[:MAX_ARG].strip()
    if action == "temporizador":
        if not re.fullmatch(r"\d{1,3}", arg) or not 1 <= int(arg) <= 600:
            return None
    if action == "posponer":
        m2 = re.fullmatch(r"(\d{1,3})/(.{1,200})", arg)
        if not m2 or not 1 <= int(m2.group(1)) <= 240:
            return None
    if action in ("rutina", "orden") and not arg:
        return None
    return action, arg


def make_link(action, arg=""):
    return f"{SCHEME}://{action}" + (("/" + urllib.parse.quote(arg, safe="/")) if arg else "")


def find_link(argv):
    """El enlace jarvis:// entre los argumentos del programa (así lo abre Windows), o None."""
    for a in argv[1:]:
        if str(a).lower().startswith("jarvis:"):
            return a
    return None


def launcher(frozen, executable, script):
    """El programa y los argumentos con los que Windows debe abrir Jarvis."""
    if frozen:
        return executable, []
    pyw = os.path.join(os.path.dirname(executable), "pythonw.exe")
    return (pyw if os.path.exists(pyw) or not IS_WIN else executable), [script]


def _cmd(exe, args, extra):
    return " ".join(f'"{x}"' for x in [exe, *args, extra])


def registry_plan(exe, args, icon, app_paths_target=None):
    """[(clave, {valor: dato})] para registrar Jarvis en Windows. "" = el valor por defecto de la clave."""
    plan = []
    for base in (CLASSES + r"\DesktopBackground\Shell\Jarvis", CLASSES + r"\Directory\Background\shell\Jarvis"):
        plan.append((base, {"MUIVerb": "Jarvis", "Icon": icon, "SubCommands": "", "Position": "Top"}))
        for key, label, url in MENU:
            plan.append((base + "\\shell\\" + key, {"MUIVerb": label}))
            plan.append((base + "\\shell\\" + key + "\\command", {"": _cmd(exe, args, url)}))
    plan.append((CLASSES + r"\jarvis", {"": "URL:Jarvis", "URL Protocol": ""}))
    plan.append((CLASSES + r"\jarvis\DefaultIcon", {"": icon}))
    plan.append((CLASSES + r"\jarvis\shell\open\command", {"": _cmd(exe, args, "%1")}))
    plan.append((CLASSES + "\\AppUserModelId\\" + APP_ID, {"DisplayName": "Jarvis", "IconUri": icon}))
    plan.append((r"Software\Microsoft\Windows\CurrentVersion\App Paths\jarvis.exe",
                 {"": app_paths_target or exe, "Path": os.path.dirname(app_paths_target or exe)}))
    return plan


# ----------------------------------------------------------------------------- registro (solo Windows)
def apply(plan):
    import winreg
    for key, values in plan:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_WRITE) as k:
            for name, data in values.items():
                winreg.SetValueEx(k, name, 0, winreg.REG_SZ, data)
    _refresh_shell()


def _delete_tree(root, key):
    import winreg
    try:
        with winreg.OpenKey(root, key, 0, winreg.KEY_ALL_ACCESS) as k:
            while True:
                try:
                    sub = winreg.EnumKey(k, 0)
                except OSError:
                    break
                _delete_tree(root, key + "\\" + sub)
        winreg.DeleteKey(root, key)
    except FileNotFoundError:
        pass


def remove():
    import winreg
    for key in KEYS_OWNED:
        _delete_tree(winreg.HKEY_CURRENT_USER, key)
    _refresh_shell()


def installed():
    if not IS_WIN:
        return False
    import winreg
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLASSES + r"\jarvis\shell\open\command"))
        return True
    except OSError:
        return False


def _refresh_shell():
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)     # SHCNE_ASSOCCHANGED
    except Exception:
        pass


def set_app_id():
    """Identidad propia en la barra de tareas (antes de crear ventanas): así la lista de saltos es de Jarvis
    y no de «Python»."""
    if not IS_WIN:
        return False
    try:
        import ctypes
        return ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID) == 0
    except Exception:
        return False


def set_jump_list(exe, args, icon, items=None):
    """Tareas del clic derecho en el icono de Jarvis en la barra de tareas. Necesita pywin32."""
    import pythoncom
    from win32com.propsys import propsys, pscon
    from win32com.shell import shell
    pythoncom.CoInitialize()
    try:
        dl = pythoncom.CoCreateInstance(shell.CLSID_DestinationList, None, pythoncom.CLSCTX_INPROC_SERVER,
                                        shell.IID_ICustomDestinationList)
        dl.SetAppID(APP_ID)
        dl.BeginList()
        col = pythoncom.CoCreateInstance(shell.CLSID_EnumerableObjectCollection, None,
                                         pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IObjectCollection)
        for _, label, url in (items or JUMP):
            link = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER,
                                              shell.IID_IShellLink)
            link.SetPath(exe)
            link.SetArguments(" ".join(f'"{a}"' for a in [*args, url]))
            link.SetIconLocation(icon, 0)
            store = link.QueryInterface(propsys.IID_IPropertyStore)
            store.SetValue(pscon.PKEY_Title, propsys.PROPVARIANTType(label))
            store.Commit()
            col.AddObject(link)
        dl.AddUserTasks(col)
        dl.CommitList()
    finally:
        pythoncom.CoUninitialize()


def shortcut_paths():
    """Accesos directos de Jarvis (escritorio, menú Inicio y el anclado en la barra de tareas)."""
    appdata, home = os.environ.get("APPDATA", ""), os.path.expanduser("~")
    cands = [os.path.join(home, "Desktop", "Jarvis.lnk"), os.path.join(home, "OneDrive", "Desktop", "Jarvis.lnk"),
             os.path.join(home, "Escritorio", "Jarvis.lnk"),
             os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Jarvis.lnk"),
             os.path.join(appdata, "Microsoft", "Internet Explorer", "Quick Launch", "User Pinned", "TaskBar", "Jarvis.lnk")]
    return [p for p in cands if os.path.isfile(p)]


def stamp_shortcuts(paths=None):
    """Pone la identidad de Jarvis en sus accesos directos, para que el icono anclado y la ventana abierta sean
    el mismo botón de la barra de tareas (y tengan la lista de saltos). Necesita pywin32."""
    import pythoncom
    from win32com.propsys import propsys, pscon
    from win32com.shell import shell
    pythoncom.CoInitialize()
    done = 0
    try:
        for p in paths if paths is not None else shortcut_paths():
            try:
                link = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER,
                                                  shell.IID_IShellLink)
                pf = link.QueryInterface(pythoncom.IID_IPersistFile)
                pf.Load(p, 2)                                  # STGM_READWRITE
                store = link.QueryInterface(propsys.IID_IPropertyStore)
                store.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType(APP_ID))
                store.Commit()
                pf.Save(p, True)
                done += 1
            except Exception:
                continue
    finally:
        pythoncom.CoUninitialize()
    return done


def clear_jump_list():
    import pythoncom
    from win32com.shell import shell
    pythoncom.CoInitialize()
    try:
        dl = pythoncom.CoCreateInstance(shell.CLSID_DestinationList, None, pythoncom.CLSCTX_INPROC_SERVER,
                                        shell.IID_ICustomDestinationList)
        dl.DeleteList(APP_ID)
    finally:
        pythoncom.CoUninitialize()


# ----------------------------------------------------------------------------- notificaciones nativas
def toast_xml(title, text, buttons=(), launch="jarvis://mostrar"):
    """La notificación de Windows en su formato. buttons: [(texto, enlace jarvis://…)] (como mucho 3)."""
    acts = "".join(f'<action content="{_xml(label, {chr(34): "&quot;"})}" activationType="protocol" '
                   f'arguments="{_xml(url, {chr(34): "&quot;"})}"/>' for label, url in list(buttons)[:3])
    return (f'<toast activationType="protocol" launch="{_xml(launch, {chr(34): "&quot;"})}">'
            f'<visual><binding template="ToastGeneric"><text>{_xml(title)}</text><text>{_xml(text)}</text>'
            f'</binding></visual>' + (f"<actions>{acts}</actions>" if acts else "") +
            '<audio silent="true"/></toast>')


def toast_script(xml):
    x = xml.replace("'", "''")
    return ("[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
            "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null;"
            "$d = New-Object Windows.Data.Xml.Dom.XmlDocument;"
            f"$d.LoadXml('{x}');"
            f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{APP_ID}')"
            ".Show([Windows.UI.Notifications.ToastNotification]::new($d))")


def toast(title, text, buttons=(), launch="jarvis://mostrar"):
    """Muestra la notificación (sin ventana de consola). Devuelve True si se pudo lanzar."""
    if not IS_WIN:
        return False
    enc = base64.b64encode(toast_script(toast_xml(title, text, buttons, launch)).encode("utf-16-le")).decode()
    try:
        subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                          "-EncodedCommand", enc], creationflags=CREATE_NO_WINDOW,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False
