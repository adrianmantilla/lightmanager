"""Clics en el visor de Maya: «Apuntar», «Colocar en superficie», «Repetir» y zonas con un rectángulo.

Usa un ``draggerContext``: mientras está activo, cada clic lanza un rayo desde la
cámara del visor y busca la malla más cercana que toca (punto y normal). Esc o
cambiar de herramienta lo termina.
"""

import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui
from maya import cmds

from lightmanager.panel import Visor

CONTEXTO = "LightManagerClicCtx"


def _rayo(x, y):
    """(origen, dirección, posición de la cámara) del rayo que pasa por el píxel (x, y) del visor activo."""
    vista = omui.M3dView.active3dView()
    cerca, lejos = vista.viewToWorld(int(x), int(y))
    direccion = om.MVector(lejos - cerca).normal()
    camara = om.MFnCamera(vista.getCamera())
    ojo = camara.eyePoint(om.MSpace.kWorld)
    if camara.isOrtho():
        ojo = cerca
    return cerca, direccion, (ojo.x, ojo.y, ojo.z)


def _mallas_visibles():
    lista = om.MSelectionList()
    for forma in cmds.ls(type="mesh", noIntermediate=True, long=True) or []:
        if forma.split("|")[-1].startswith("LM_"):
            continue
        try:
            if not cmds.getAttr(forma + ".visibility"):
                continue
            lista.add(forma)
        except Exception:
            continue
    for i in range(lista.length()):
        try:
            camino = lista.getDagPath(i)
        except Exception:
            continue
        if camino.isVisible():
            yield camino


def tocar(x, y):
    """(punto, normal, cámara) de la superficie bajo el píxel (x, y), o None si no hay nada."""
    origen, direccion, camara = _rayo(x, y)
    mejor = None
    fuente = om.MFloatPoint(origen.x, origen.y, origen.z)
    rayo = om.MFloatVector(direccion.x, direccion.y, direccion.z)
    for camino in _mallas_visibles():
        malla = om.MFnMesh(camino)
        try:
            resultado = malla.closestIntersection(fuente, rayo, om.MSpace.kWorld, 1e7, False)
        except Exception:
            continue
        if not resultado:
            continue
        punto, parametro, cara = resultado[0], resultado[1], resultado[2]
        if cara is None or cara < 0:
            continue
        if mejor is None or parametro < mejor[0]:
            normal, _ = malla.getClosestNormal(om.MPoint(punto), om.MSpace.kWorld)
            mejor = (parametro, (punto.x, punto.y, punto.z), (normal.x, normal.y, normal.z))
    if mejor is None:
        # Nada debajo: se toma el suelo (y = 0).
        if abs(direccion.y) < 1e-6:
            return None
        k = -origen.y / direccion.y
        if k < 0:
            return None
        p = origen + direccion * k
        return (p.x, p.y, p.z), (0.0, 1.0, 0.0), camara
    n = om.MVector(*mejor[2])
    # Que la normal mire hacia la cámara (caras dadas la vuelta).
    if n * direccion > 0:
        n = -n
    return mejor[1], (n.x, n.y, n.z), camara


class VisorMaya(Visor):
    disponible = True

    def __init__(self):
        self._funcion = None
        self._repetir = False
        self._rectangulo = False
        self._anterior = None
        self._inicio = None
        self.al_terminar = None   # el panel pone aquí qué hacer al salir de la herramienta

    def crear_vista(self, padre):
        try:
            from lightmanager import vista
            return vista.crear(padre)
        except Exception as error:  # pragma: no cover - sin visor: el panel sigue
            print("LightManager | no se pudo crear la vista: {}".format(error))
            return None

    def encuadrar(self):
        from lightmanager import vista
        vista.encuadrar()

    def pedir_clic(self, texto, funcion, repetir=False):
        self._funcion, self._repetir, self._rectangulo = funcion, repetir, False
        return self._entrar(texto)

    def pedir_rectangulo(self, texto, funcion):
        self._funcion, self._repetir, self._rectangulo = funcion, False, True
        return self._entrar(texto)

    def _entrar(self, texto):
        try:
            if cmds.draggerContext(CONTEXTO, exists=True):
                cmds.deleteUI(CONTEXTO)
            cmds.draggerContext(CONTEXTO, pressCommand=self._pulsar, releaseCommand=self._soltar,
                                finalize=self._salir, cursor="crossHair", space="screen",
                                undoMode="sequential", name=CONTEXTO)
            actual = cmds.currentCtx()
            if actual != CONTEXTO:
                self._anterior = actual
            cmds.setToolTo(CONTEXTO)
            cmds.inViewMessage(assistMessage=texto, position="topCenter", fade=True, fadeStayTime=3000)
        except Exception as error:
            print("LightManager | {}".format(error))
            return False
        return True

    def _pulsar(self):
        self._inicio = cmds.draggerContext(CONTEXTO, query=True, anchorPoint=True)

    def _soltar(self):
        fin = cmds.draggerContext(CONTEXTO, query=True, dragPoint=True)
        funcion = self._funcion
        if funcion is None:
            return
        try:
            if self._rectangulo:
                caja = self._caja(self._inicio or fin, fin)
                if caja is not None:
                    cmds.evalDeferred(lambda: funcion(caja))
            else:
                golpe = tocar(fin[0], fin[1])
                if golpe is not None:
                    funcion(*golpe)
        finally:
            if not self._repetir:
                cmds.evalDeferred(self.cancelar)

    def _caja(self, a, b):
        """Caja de la zona a partir de dos esquinas en pantalla, con la altura de la escena."""
        p1, p2 = tocar(a[0], a[1]), tocar(b[0], b[1])
        if p1 is None or p2 is None:
            return None
        from lightmanager.interfaz_maya import servicios
        escena = servicios().caja_escena() or ((0, 0, 0), (1, 3, 1))
        (x1, _, z1), (x2, _, z2) = p1[0], p2[0]
        if abs(x2 - x1) < 1e-3 or abs(z2 - z1) < 1e-3:
            return None
        return ((min(x1, x2), escena[0][1], min(z1, z2)), (max(x1, x2), escena[1][1], max(z1, z2)))

    def _salir(self):
        self._funcion = None
        if self.al_terminar is not None:
            try:
                self.al_terminar()
            except Exception:
                pass

    def cancelar(self):
        self._funcion = None
        try:
            if cmds.currentCtx() == CONTEXTO:
                cmds.setToolTo(self._anterior or "selectSuperContext")
        except Exception:
            pass
