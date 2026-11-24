"""Une LightManager con Maya: panel acoplable, menú, órdenes, estante y avisos de la escena."""

import os

from maya import cmds, mel

import lightmanager
from lightmanager import pack
from lightmanager.ajustes import Ajustes
from lightmanager.gestor import ErrorLightManager, Gestor
from lightmanager.i18n import t
from lightmanager.qt import QtCore, QtGui, QtWidgets, destruir, shiboken, sigue_vivo, ventana_maya

CONTROL = "LightManagerWorkspaceControl"
MENU = "LightManagerMenu"
COMANDOS = {
    "LightManagerPanel": ("cmd_panel", "alternar()"),
    "LightManagerTresPuntos": ("cmd_tres_puntos", "tres_puntos()"),
    "LightManagerComprobar": ("cmd_comprobar", "comprobar()"),
    "LightManagerQuitarSolos": ("cmd_quitar_solos", "quitar_solos()"),
    "LightManagerApuntar": ("cmd_apuntar", "apuntar()"),
}
# Eventos que pueden cambiar las luces: se vuelve a leer la escena (agrupando los avisos).
EVENTOS_LUCES = ("Undo", "Redo", "DagObjectCreated", "NameChanged", "parentChanged", "ActiveViewChanged")
EVENTOS_ESCENA = ("SceneOpened", "NewSceneOpened")

_estado = {"panel": None, "ajustes": None, "gestor": None, "servicios": None, "visor": None, "trabajos": [],
           "pendiente": False}


# --- objetos compartidos -------------------------------------------------------------------

def carpeta_preferencias():
    return os.path.join(cmds.internalVar(userAppDir=True), "lightmanager")


def ajustes():
    if _estado["ajustes"] is None:
        _estado["ajustes"] = Ajustes(carpeta_preferencias())
    return _estado["ajustes"]


def servicios():
    if _estado["servicios"] is None:
        from lightmanager.maya_servicios import ServiciosMaya
        _estado["servicios"] = ServiciosMaya()
    return _estado["servicios"]


def gestor():
    if _estado["gestor"] is None:
        _estado["gestor"] = Gestor(servicios(), ajustes())
        _estado["gestor"].refrescar()
    return _estado["gestor"]


def visor():
    if _estado["visor"] is None:
        from lightmanager.visor import VisorMaya
        _estado["visor"] = VisorMaya()
    return _estado["visor"]


def panel():
    p = _estado["panel"]
    return p if sigue_vivo(p) else None


def recargar_ajustes():
    """MantiTools lo llama después de cambiar los ajustes desde su ventana central."""
    ajustes().cargar()
    _refrescar()


# --- panel acoplable -------------------------------------------------------------------------

def restaurar():
    """Maya lo llama al crear (o recuperar) el panel: mete el panel dentro."""
    from maya import OpenMayaUI as omui
    from lightmanager.panel import PanelLightManager
    puntero = omui.MQtUtil.getCurrentParent()
    padre = shiboken.wrapInstance(int(puntero), QtWidgets.QWidget)
    p = panel()
    if p is None:
        v = visor()
        p = PanelLightManager(gestor(), v, padre_dialogos=ventana_maya())
        v.al_terminar = p.apuntar_terminado
        _estado["panel"] = p
    padre.layout().addWidget(p)


def mostrar():
    if cmds.workspaceControl(CONTROL, exists=True):
        cmds.workspaceControl(CONTROL, edit=True, restore=True, visible=True)
        if panel() is None:
            cmds.deleteUI(CONTROL)
        else:
            _refrescar()
            return panel()
    cmds.workspaceControl(CONTROL, label="LightManager", retain=False, floating=True, initialWidth=440,
                          initialHeight=860, minimumWidth=320,
                          uiScript="import lightmanager.interfaz_maya as m\nm.restaurar()",
                          closeCommand="import lightmanager.interfaz_maya as m\nm.al_cerrar()")
    return panel()


def alternar():
    if cmds.workspaceControl(CONTROL, exists=True) and cmds.workspaceControl(CONTROL, query=True, visible=True):
        cmds.workspaceControl(CONTROL, edit=True, visible=False)
    else:
        mostrar()


def al_cerrar():
    p = panel()
    if p is not None:
        p.cerrar()
    try:
        from lightmanager import vista
        vista.borrar()
    except Exception:
        pass
    _estado["panel"] = None


def _refrescar():
    _estado["pendiente"] = False
    g = _estado["gestor"]
    if g is None:
        return
    try:
        g.refrescar()
        p = panel()
        if p is not None:
            p.refrescar(leer=False)
    except Exception as error:  # pragma: no cover - que un fallo no deje Maya con errores en cada clic
        print("LightManager | {}".format(error))


def _refrescar_luego():
    if not _estado["pendiente"]:
        _estado["pendiente"] = True
        cmds.evalDeferred(_refrescar, lowestPriority=True)


def _seleccion_cambiada():
    p = panel()
    if p is not None:
        try:
            p.sincronizar_desde_maya()
        except Exception:
            pass


def _escena_abierta():
    g = _estado["gestor"]
    if g is not None:
        g.refrescar()
    p = panel()
    if p is not None:
        p.seleccion = []
        if p.vista_maya is not None:
            try:  # la cámara de arriba es de la escena anterior: se vuelve a crear y encuadrar
                from lightmanager import vista
                vista.usar_camara("arriba")
                vista.encuadrar()
            except Exception:
                pass
    _refrescar()


# --- órdenes ---------------------------------------------------------------------------------------

def _avisar(texto):
    servicios().aviso(texto)


def _con_errores(funcion, *args):
    try:
        return funcion(*args)
    except ErrorLightManager as error:
        _avisar(t(error.clave, **error.valores))
    except Exception as error:
        cmds.warning("LightManager: {}".format(error))
    return None


def tres_puntos():
    """Pone el esquema de tres puntos alrededor de lo seleccionado (o de la escena)."""
    from lightmanager import esquemas as esq
    g = gestor()
    g.refrescar()
    if _con_errores(g.aplicar_esquema, esq.buscar(g.esquemas(), "tres_puntos")) is not None:
        _avisar(t("hecho_esquema", nombre=esq.buscar(g.esquemas(), "tres_puntos").nombre))
    _refrescar()


def comprobar():
    p = mostrar()
    if p is not None:
        p.pestanas.setCurrentIndex(5)


def quitar_solos():
    g = gestor()
    g.refrescar()
    _con_errores(g.quitar_solos)
    _refrescar()


def apuntar(modo="luz"):
    """Apunta en el visor la luz seleccionada (Radial y atajos)."""
    p = mostrar()
    if p is not None:
        p.sincronizar_desde_maya()
        p.botones_apuntar[modo].setChecked(True)
        p.apuntar(modo, True)


def abrir_guia():
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ruta = os.path.join(raiz, "GUIA_DE_USO.md")
    QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(ruta))


def _icono():
    from lightmanager.iconos import asegurar_icono
    return asegurar_icono(carpeta_preferencias())


def anadir_a_estanteria():
    try:
        estanterias = mel.eval("$tmp = $gShelfTopLevel")
        pestana = cmds.tabLayout(estanterias, query=True, selectTab=True)
        cmds.shelfButton(parent="{}|{}".format(estanterias, pestana), label="LightManager",
                         annotation=t("cmd_panel"), image=_icono(), sourceType="python",
                         command="import lightmanager.interfaz_maya as m\nm.alternar()",
                         doubleClickCommand="import lightmanager.interfaz_maya as m\nm.tres_puntos()")
        _avisar(t("estanteria_hecho", estanteria=pestana))
    except Exception as error:
        QtWidgets.QMessageBox.warning(ventana_maya(), "LightManager", str(error))


# --- menú --------------------------------------------------------------------------------------------

def _crear_ordenes():
    for nombre, (clave, llamada) in COMANDOS.items():
        codigo = "import lightmanager.interfaz_maya as m\nm.{}".format(llamada)
        if cmds.runTimeCommand(nombre, exists=True):
            cmds.runTimeCommand(nombre, edit=True, command=codigo, commandLanguage="python", annotation=t(clave))
        else:
            cmds.runTimeCommand(nombre, command=codigo, commandLanguage="python", annotation=t(clave),
                                category="Custom Scripts.LightManager")


def _crear_menu():
    pack.crear_menu(MENU, "LightManager")
    cmds.menuItem(label=t("menu_panel"), command=lambda *_: mostrar(), annotation=t("cmd_panel"))
    cmds.menuItem(label=t("menu_tres_puntos"), command=lambda *_: tres_puntos(), annotation=t("cmd_tres_puntos"))
    cmds.menuItem(label=t("menu_comprobar"), command=lambda *_: comprobar())
    cmds.menuItem(label=t("menu_quitar_solos"), command=lambda *_: quitar_solos())
    cmds.menuItem(divider=True)
    if not pack.en_pack():  # dentro de MantiTools el estante lo pone el pack
        cmds.menuItem(label=t("menu_estanteria"), command=lambda *_: anadir_a_estanteria())
    cmds.menuItem(label=t("menu_guia"), command=lambda *_: abrir_guia())
    cmds.menuItem(divider=True)
    cmds.menuItem(label=t("menu_acerca", version=lightmanager.__version__), enable=False)


def iniciar():
    _crear_ordenes()
    if cmds.about(batch=True):
        return
    _crear_menu()
    trabajos = [cmds.scriptJob(event=["SelectionChanged", _seleccion_cambiada])]
    for evento in EVENTOS_ESCENA:
        trabajos.append(cmds.scriptJob(event=[evento, _escena_abierta]))
    for evento in EVENTOS_LUCES:
        try:
            trabajos.append(cmds.scriptJob(event=[evento, _refrescar_luego]))
        except Exception:
            pass
    _estado["trabajos"] = trabajos


def detener():
    for trabajo in _estado["trabajos"]:
        if cmds.scriptJob(exists=trabajo):
            cmds.scriptJob(kill=trabajo, force=True)
    _estado["trabajos"] = []
    p = panel()
    if p is not None:
        p.cerrar()
    if cmds.workspaceControl(CONTROL, exists=True):
        cmds.deleteUI(CONTROL)
    try:
        from lightmanager import vista
        vista.borrar()
    except Exception:
        pass
    if p is not None:
        destruir(p)
    if _estado["visor"] is not None:
        _estado["visor"].cancelar()
    _estado.update({"panel": None, "gestor": None, "visor": None})
    pack.quitar_menu(MENU)
