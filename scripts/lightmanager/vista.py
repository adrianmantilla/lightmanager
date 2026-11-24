"""Visor de Maya dentro del panel (modo Escena): la escena desde arriba, con sus luces.

Es un ``modelPanel`` de verdad metido en el panel de Qt, así que se ve lo mismo que
en Maya (Viewport 2.0 con las luces de la escena) y se puede seleccionar y mover
como en cualquier visor. Tiene dos cámaras: ``LM_camara_cenital`` (ortográfica, desde
arriba, encuadra la escena) y la cámara de render. La luz real de Arnold se ve con el
IPR de RenderDesk.
"""

from maya import OpenMayaUI as omui
from maya import cmds

from lightmanager import geometria as geo
from lightmanager.i18n import t
from lightmanager.qt import QtWidgets, shiboken

PANEL = "LightManagerVistaPanel"
CAMARA = "LM_camara_cenital"
_estado = {"panel": None}


def _caja_escena():
    from lightmanager.interfaz_maya import servicios
    return servicios().caja_escena() or ((-5.0, 0.0, -5.0), (5.0, 3.0, 5.0))


def camara_cenital():
    """La cámara ortográfica de arriba (la crea si no existe). Devuelve el transform."""
    if not cmds.objExists(CAMARA):
        transform, forma = cmds.camera(orthographic=True, name=CAMARA)
        if transform != CAMARA:
            transform = cmds.rename(transform, CAMARA)
        cmds.setAttr(transform + ".rotate", -90, 0, 0, type="double3")
        cmds.setAttr(transform + ".hiddenInOutliner", True)
        forma = cmds.listRelatives(transform, shapes=True)[0]
        cmds.setAttr(forma + ".renderable", False)
        encuadrar()
    return CAMARA


def encuadrar():
    """Pone la cámara de arriba sobre toda la escena."""
    if not cmds.objExists(CAMARA):
        return
    caja = _caja_escena()
    c = geo.centro(caja)
    ancho = max(caja[1][0] - caja[0][0], caja[1][2] - caja[0][2], 1.0) * 1.15
    cmds.setAttr(CAMARA + ".translate", c[0], caja[1][1] + ancho, c[2], type="double3")
    forma = cmds.listRelatives(CAMARA, shapes=True)[0]
    cmds.setAttr(forma + ".orthographicWidth", ancho)
    cmds.setAttr(forma + ".farClipPlane", ancho * 4 + caja[1][1] - caja[0][1])


def _camara_render():
    for forma in cmds.ls(type="camera") or []:
        if cmds.getAttr(forma + ".renderable"):
            return cmds.listRelatives(forma, parent=True)[0]
    return "persp"


def usar_camara(cual):
    if not cmds.modelPanel(PANEL, exists=True):
        return
    camara = camara_cenital() if cual == "arriba" else _camara_render()
    cmds.modelEditor(PANEL, edit=True, camera=camara)


def crear(padre):
    """Widget con la barra (Arriba | Cámara | Encuadrar) y el visor de Maya."""
    if cmds.modelPanel(PANEL, exists=True):
        cmds.deleteUI(PANEL, panel=True)
    contenedor = QtWidgets.QWidget(padre)
    capa = QtWidgets.QVBoxLayout(contenedor)
    capa.setContentsMargins(0, 0, 0, 0)
    capa.setSpacing(2)

    barra = QtWidgets.QHBoxLayout()
    barra.setContentsMargins(6, 4, 6, 0)
    for texto, ayuda, funcion in ((t("vista_arriba"), t("vista_arriba_ayuda"), lambda: usar_camara("arriba")),
                                  (t("vista_camara"), t("vista_camara_ayuda"), lambda: usar_camara("render")),
                                  (t("vista_encuadrar"), t("vista_encuadrar_ayuda"), encuadrar)):
        b = QtWidgets.QToolButton()
        b.setText(texto)
        b.setToolTip(ayuda)
        b.clicked.connect(lambda _=False, f=funcion: f())
        barra.addWidget(b)
    barra.addStretch(1)
    capa.addLayout(barra)

    hueco = QtWidgets.QWidget()
    hueco.setObjectName("LightManagerVistaHueco")
    capa_hueco = QtWidgets.QVBoxLayout(hueco)
    capa_hueco.setObjectName("LightManagerVistaCapa")
    capa_hueco.setContentsMargins(0, 0, 0, 0)
    capa.addWidget(hueco, 1)

    nombre_capa = omui.MQtUtil.fullName(int(shiboken.getCppPointer(capa_hueco)[0]))
    cmds.setParent(nombre_capa)
    marco = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel(PANEL, label="LightManager", menuBarVisible=False, parent=marco)
    cmds.modelEditor(panel, edit=True, camera=camara_cenital(), displayAppearance="smoothShaded",
                     displayLights="all", shadows=False, grid=False, headsUpDisplay=False,
                     cameras=False, nurbsCurves=True, lights=True, manipulators=True, selectionHiliteDisplay=True)
    puntero = omui.MQtUtil.findControl(marco)
    if puntero:
        capa_hueco.addWidget(shiboken.wrapInstance(int(puntero), QtWidgets.QWidget))
    _estado["panel"] = panel
    encuadrar()
    return contenedor


def borrar():
    if cmds.modelPanel(PANEL, exists=True):
        cmds.deleteUI(PANEL, panel=True)
    _estado["panel"] = None
