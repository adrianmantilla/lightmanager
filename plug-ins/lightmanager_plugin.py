"""Plugin de Maya para LightManager.

Aparece en el Plug-in Manager como «lightmanager_plugin». Al cargarlo crea el menú
LightManager en la barra de Maya y las órdenes para el Editor de atajos; al
descargarlo lo quita todo. El instalador lo marca para que se cargue solo.
"""

import maya.api.OpenMaya as om
from maya import cmds


def maya_useNewAPI():
    pass


def initializePlugin(objeto):
    import lightmanager
    plugin = om.MFnPlugin(objeto, "LightManager", lightmanager.__version__, "Any")
    try:
        from lightmanager import interfaz_maya
        cmds.evalDeferred(interfaz_maya.iniciar, lowestPriority=True)
    except Exception as error:
        cmds.warning("LightManager no se pudo cargar: {}".format(error))
    return plugin


def uninitializePlugin(objeto):
    try:
        from lightmanager import interfaz_maya
        interfaz_maya.detener()
    except Exception:
        pass
