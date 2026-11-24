"""``Servicios`` hechos con Maya y Arnold (MtoA).

Los nombres de atributo de Arnold han cambiado entre versiones de MtoA (``aiExposure``
o ``exposure``…), así que cada valor se busca entre varios candidatos.
"""

import base64
import contextlib
import math
import os
import subprocess

from maya import cmds

from lightmanager import geometria as geo
from lightmanager import nombres, unidades
from lightmanager.modelo import TIPO_DE_NODO, TIPOS, Luz
from lightmanager.servicios import Servicios
from lightmanager.zonas import Zona

TIPOS_NODO = tuple(v[1] for v in TIPOS.values())

# Candidatos de atributo de la forma de la luz.
A_EXPOSICION = ("aiExposure", "exposure")
A_MUESTRAS = ("aiSamples", "samples")
A_USA_KELVIN = ("aiUseColorTemperature", "useColorTemperature")
A_KELVIN = ("aiColorTemperature", "colorTemperature")
A_GRUPO = ("aiAov", "aov")
A_CAMARA = ("aiCamera", "camera")
A_NORMALIZAR = ("aiNormalize", "normalize")
A_RADIO = ("aiRadius", "radius")
A_ANGULO = ("aiAngle", "angle")
A_IES = ("aiFilename", "filename")
A_PORTAL = ("aiPortalMode", "portalMode", "portal_mode")
A_SOMBRAS = ("aiCastShadows", "castShadows")

# Atributos propios en el transform.
LM = {
    "encendida": ("lmEncendida", "bool"),
    "solo": ("lmSolo", "bool"),
    "papel": ("lmPapel", "string"),
    "zona": ("lmZona", "string"),
    "gemela": ("lmGemela", "string"),
    "esquema": ("lmEsquema", "string"),
    "objetivo": ("lmObjetivo", "double3"),
}
ATTR_ZONA = "lmZonaNombre"


def _attr(nodo, candidatos):
    for c in candidatos:
        if cmds.attributeQuery(c, node=nodo, exists=True):
            return "{}.{}".format(nodo, c)
    return None


def _leer(nodo, candidatos, defecto=None):
    a = _attr(nodo, candidatos)
    if a is None:
        return defecto
    try:
        v = cmds.getAttr(a)
    except Exception:
        return defecto
    if isinstance(v, list) and len(v) == 1 and isinstance(v[0], tuple):
        return v[0]
    return v


def _poner(nodo, candidatos, valor, tipo=None):
    a = _attr(nodo, candidatos)
    if a is None:
        return False
    try:
        if cmds.getAttr(a, lock=True):
            return False
        if tipo:
            cmds.setAttr(a, valor, type=tipo)
        elif isinstance(valor, (tuple, list)):
            cmds.setAttr(a, *valor)
        else:
            cmds.setAttr(a, valor)
        return True
    except Exception:
        return False


def _asegurar_lm(transform, campo):
    nombre, tipo = LM[campo]
    if not cmds.attributeQuery(nombre, node=transform, exists=True):
        if tipo == "string":
            cmds.addAttr(transform, longName=nombre, dataType="string")
        elif tipo == "double3":
            cmds.addAttr(transform, longName=nombre, attributeType="double3")
            for eje in "XYZ":
                cmds.addAttr(transform, longName=nombre + eje, attributeType="double", parent=nombre)
        else:
            cmds.addAttr(transform, longName=nombre, attributeType=tipo, defaultValue=1 if campo == "encendida" else 0)
    return "{}.{}".format(transform, nombre)


def _leer_lm(transform, campo, defecto):
    nombre, tipo = LM[campo]
    if not cmds.attributeQuery(nombre, node=transform, exists=True):
        return defecto
    v = cmds.getAttr("{}.{}".format(transform, nombre))
    if tipo == "double3":
        return tuple(v[0]) if v else defecto
    if tipo == "string":
        return v or ""
    return bool(v)


def _poner_lm(transform, campo, valor):
    a = _asegurar_lm(transform, campo)
    tipo = LM[campo][1]
    if tipo == "string":
        cmds.setAttr(a, valor or "", type="string")
    elif tipo == "double3":
        if valor is None:
            if cmds.attributeQuery(LM[campo][0], node=transform, exists=True):
                cmds.deleteAttr(a)
            return
        cmds.setAttr(a, *valor)
    else:
        cmds.setAttr(a, bool(valor))


def _transform(forma):
    padres = cmds.listRelatives(forma, parent=True, fullPath=True) or []
    return padres[0] if padres else forma


def _forma(transform):
    formas = cmds.listRelatives(transform, shapes=True, fullPath=True, noIntermediate=True) or []
    for f in formas:
        if cmds.nodeType(f) in TIPOS_NODO:
            return f
    return formas[0] if formas else transform


def _corto(nodo):
    return nodo.split("|")[-1]


def _unico(nodo):
    """Nombre corto si es único; si no, la ruta completa."""
    corto = _corto(nodo)
    return corto if len(cmds.ls(corto) or []) == 1 else nodo


def _mtoa():
    try:
        if not cmds.pluginInfo("mtoa", query=True, loaded=True):
            cmds.loadPlugin("mtoa", quiet=True)
        return True
    except Exception:
        return False


class ServiciosMaya(Servicios):
    en_maya = True

    def __init__(self):
        self._cajas = None

    # --- luces ---------------------------------------------------------------------------
    def luces(self):
        formas = cmds.ls(type=list(TIPOS_NODO), long=True) or []
        resultado = []
        vistos = set()
        for forma in formas:
            if cmds.getAttr(forma + ".intermediateObject") if cmds.attributeQuery(
                    "intermediateObject", node=forma, exists=True) else False:
                continue
            t = _transform(forma)
            if t in vistos:
                continue
            vistos.add(t)
            try:
                resultado.append(self._leer_luz(t, forma))
            except Exception as error:  # una luz rara no debe vaciar la lista
                print("LightManager | no se pudo leer {}: {}".format(t, error))
        return resultado

    def _leer_luz(self, t, forma):
        tipo = TIPO_DE_NODO.get(cmds.nodeType(forma), "area")
        intensidad = _leer(forma, ("intensity",), 1.0) or 0.0
        exposicion = _leer(forma, A_EXPOSICION, 0.0) or 0.0
        visible = bool(cmds.getAttr(t + ".visibility"))
        color = _leer(forma, ("color",), (1.0, 1.0, 1.0))
        usa_k = bool(_leer(forma, A_USA_KELVIN, False))
        kelvin = _leer(forma, A_KELVIN, None)
        if kelvin is None or not usa_k:
            kelvin = unidades.rgb_a_kelvin(color) if isinstance(color, tuple) else 6500
        escala = tuple(cmds.getAttr(t + ".scale")[0])
        if tipo in ("area", "portal", "area_maya", "volumen"):
            tamano = max(escala[0], escala[1]) * 2.0
        elif tipo == "sol":
            tamano = _leer(forma, A_ANGULO, 0.0) or 0.0
        else:
            tamano = _leer(forma, A_RADIO, 0.0) or 0.0
        hdri, fisico = "", False
        if tipo == "cielo":
            entradas = cmds.listConnections(forma + ".color", source=True, destination=False) or []
            for nodo in entradas:
                tn = cmds.nodeType(nodo)
                if tn == "file":
                    hdri = cmds.getAttr(nodo + ".fileTextureName") or ""
                elif tn == "aiPhysicalSky":
                    fisico = True
        ies = _leer(forma, A_IES, "") if tipo == "fotometrica" else ""
        return Luz(
            _unico(t), tipo,
            encendida=_leer_lm(t, "encendida", visible),
            solo=_leer_lm(t, "solo", False),
            visible=visible,
            pasos=unidades.pasos(float(intensidad), float(exposicion)) if intensidad > 0 else unidades.PASOS_MIN,
            kelvin=int(round(kelvin)),
            usa_kelvin=usa_k,
            color=tuple(color) if isinstance(color, tuple) else (1.0, 1.0, 1.0),
            tamano=float(tamano),
            muestras=int(_leer(forma, A_MUESTRAS, 1) or 1),
            grupo=_leer(forma, A_GRUPO, "") or "",
            papel=_leer_lm(t, "papel", ""),
            zona=_leer_lm(t, "zona", ""),
            gemela=_leer_lm(t, "gemela", ""),
            esquema=_leer_lm(t, "esquema", ""),
            objetivo=_leer_lm(t, "objetivo", None),
            ies=ies or "",
            posicion=tuple(cmds.xform(t, query=True, worldSpace=True, translation=True)),
            rotacion=tuple(cmds.xform(t, query=True, worldSpace=True, rotation=True)),
            escala=escala,
            visible_camara=bool(_leer(forma, A_CAMARA, 0)),
            decay=int(_leer(forma, ("decayRate",), 2) if tipo in ("punto", "foco", "area_maya", "volumen") else 2),
            hdri=hdri,
            rotacion_cielo=float(cmds.getAttr(t + ".rotateY")) % 360.0 if tipo == "cielo" else 0.0,
            portal_modo=int(_leer(forma, A_PORTAL, 0) or 0) if tipo == "cielo" else 0,
            cielo_fisico=fisico,
        )

    def escribir(self, nodo, campos):
        t = nodo
        forma = _forma(t)
        for campo, valor in campos.items():
            if campo == "nombre":
                nuevo = cmds.rename(t, nombres.limpio(valor) if not valor.startswith(nombres.PREFIJO)
                                    else valor)
                t = _unico(cmds.ls(nuevo, long=True)[0])
                forma = _forma(t)
            elif campo == "visible":
                cmds.setAttr(t + ".visibility", bool(valor))
            elif campo in ("encendida", "solo", "papel", "gemela", "esquema", "objetivo"):
                _poner_lm(t, campo, valor)
            elif campo == "zona":
                _poner_lm(t, "zona", valor)
            elif campo == "pasos":
                intensidad = _leer(forma, ("intensity",), 1.0) or 1.0
                if intensidad <= 0:
                    _poner(forma, ("intensity",), 1.0)
                    intensidad = 1.0
                if not _poner(forma, A_EXPOSICION, unidades.exposicion_para(valor, intensidad)):
                    _poner(forma, ("intensity",), unidades.multiplicador(valor))
            elif campo == "kelvin":
                if _attr(forma, A_KELVIN):
                    _poner(forma, A_USA_KELVIN, True)
                    _poner(forma, A_KELVIN, float(valor))
                else:
                    _poner(forma, ("color",), unidades.kelvin_a_rgb(valor))
            elif campo == "usa_kelvin":
                _poner(forma, A_USA_KELVIN, bool(valor))
            elif campo == "color":
                _poner(forma, A_USA_KELVIN, False)
                _poner(forma, ("color",), tuple(valor))
            elif campo == "tamano":
                self._poner_tamano(t, forma, float(valor))
            elif campo == "muestras":
                _poner(forma, A_MUESTRAS, int(valor))
            elif campo == "grupo":
                _poner(forma, A_GRUPO, valor or "", "string")
            elif campo == "ies":
                _poner(forma, A_IES, valor or "", "string")
            elif campo == "posicion":
                cmds.xform(t, worldSpace=True, translation=tuple(valor))
            elif campo == "rotacion":
                cmds.setAttr(t + ".rotateOrder", 0)
                cmds.xform(t, worldSpace=True, rotation=tuple(valor))
            elif campo == "escala":
                cmds.setAttr(t + ".scale", *valor)
            elif campo == "visible_camara":
                _poner(forma, A_CAMARA, 1.0 if valor else 0.0)
            elif campo == "decay":
                _poner(forma, ("decayRate",), int(valor))
            elif campo == "hdri":
                self._poner_hdri(forma, valor)
            elif campo == "rotacion_cielo":
                cmds.setAttr(t + ".rotateY", float(valor))
            elif campo == "portal_modo":
                _poner(forma, A_PORTAL, int(valor))
        return t

    def _poner_tamano(self, t, forma, valor):
        tipo = TIPO_DE_NODO.get(cmds.nodeType(forma), "area")
        if tipo in ("area", "portal", "area_maya", "volumen"):
            actual = cmds.getAttr(t + ".scale")[0]
            mayor = max(actual[0], actual[1]) or 1.0
            k = (valor * 0.5) / mayor
            cmds.setAttr(t + ".scale", actual[0] * k, actual[1] * k, actual[2] if tipo != "volumen" else actual[2] * k)
        elif tipo == "sol":
            _poner(forma, A_ANGULO, valor)
        else:
            _poner(forma, A_RADIO, valor)

    def _poner_hdri(self, forma, ruta):
        entradas = cmds.listConnections(forma + ".color", source=True, destination=False) or []
        archivo = next((n for n in entradas if cmds.nodeType(n) == "file"), None)
        if not ruta:
            if archivo:
                cmds.disconnectAttr(archivo + ".outColor", forma + ".color")
            return
        if archivo is None:
            for n in entradas:  # quita un cielo físico si lo había
                cmds.disconnectAttr(n + ".outColor", forma + ".color")
            archivo = cmds.shadingNode("file", asTexture=True, isColorManaged=True, name="LM_hdri")
            cmds.connectAttr(archivo + ".outColor", forma + ".color", force=True)
        cmds.setAttr(archivo + ".fileTextureName", ruta, type="string")
        try:
            cmds.setAttr(archivo + ".colorSpace", "Raw" if ruta.lower().endswith(".tx") else "scene-linear Rec.709-sRGB",
                         type="string")
        except Exception:
            pass

    def crear(self, datos):
        datos = dict(datos)
        tipo = datos.pop("tipo")
        nombre = datos.pop("nombre")
        t = self._crear_nodo(tipo)
        t = cmds.rename(t, nombre)
        t = _unico(cmds.ls(t, long=True)[0])
        forma = _forma(t)
        _poner(forma, A_NORMALIZAR, True)
        if tipo in ("punto", "foco", "area_maya", "volumen"):
            _poner(forma, ("decayRate",), 2)
        if tipo != "cielo":
            _poner(forma, A_CAMARA, 0.0)
        if tipo == "foco":
            _poner(forma, ("coneAngle",), 50.0)
            _poner(forma, ("penumbraAngle",), 10.0)
        _poner_lm(t, "encendida", True)
        datos.setdefault("visible", True)
        datos.setdefault("usa_kelvin", TIPOS[tipo][2])
        if "tamano" in datos and tipo == "area" and "escala" in datos:
            datos.pop("tamano")
        if tipo == "portal":
            datos.pop("pasos", None)
        t = self.escribir(t, datos)
        grupo = self._grupo(nombres.GRUPO_LUCES)
        if tipo != "malla":
            try:
                t = _unico(cmds.parent(t, grupo)[0])
            except Exception:
                pass
        return t

    def _crear_nodo(self, tipo):
        nodo = TIPOS[tipo][1]
        if tipo in ("area", "cielo", "fotometrica", "portal"):
            _mtoa()
            try:
                import mtoa.utils as mu
                forma, transform = mu.createLocator(nodo, asLight=True)
                return transform
            except Exception:
                forma = cmds.shadingNode(nodo, asLight=True)
                return _transform(forma)
        if tipo == "sol":
            return _transform(cmds.directionalLight())
        if tipo == "foco":
            return _transform(cmds.spotLight())
        if tipo == "punto":
            return _transform(cmds.pointLight())
        if tipo == "area_maya":
            return _transform(cmds.shadingNode("areaLight", asLight=True))
        raise ValueError(tipo)

    def _grupo(self, nombre):
        if not cmds.objExists(nombre):
            cmds.group(empty=True, name=nombre, world=True)
        return nombre

    def borrar(self, nodos):
        existentes = [n for n in nodos if cmds.objExists(n)]
        if existentes:
            cmds.delete(existentes)

    def duplicar(self, nodo):
        copia = cmds.duplicate(nodo, returnRootsOnly=True)[0]
        return _unico(cmds.ls(copia, long=True)[0])

    # --- selección y escena --------------------------------------------------------------
    def seleccionar(self, nodos):
        existentes = [n for n in nodos if cmds.objExists(n)]
        if existentes:
            cmds.select(existentes, replace=True)
        else:
            cmds.select(clear=True)

    def seleccion(self):
        return [_unico(n) for n in (cmds.ls(selection=True, long=True, transforms=True) or [])]

    def caja(self, nodos):
        nodos = [n for n in nodos if cmds.objExists(n)]
        if not nodos:
            return None
        try:
            b = cmds.exactWorldBoundingBox(nodos, ignoreInvisible=True)
        except Exception:
            return None
        if b[0] > b[3]:
            return None
        return (b[0], b[1], b[2]), (b[3], b[4], b[5])

    def _mallas(self):
        """[(transform, caja)] de la geometría visible (sin zonas)."""
        resultado = []
        for forma in cmds.ls(type=("mesh", "nurbsSurface", "subdiv"), long=True, noIntermediate=True) or []:
            t = _transform(forma)
            if "|" + nombres.GRUPO_ZONAS in t or _corto(t).startswith("LM_zona_"):
                continue
            try:
                if not cmds.getAttr(t + ".visibility"):
                    continue
                b = cmds.exactWorldBoundingBox(forma)
            except Exception:
                continue
            resultado.append((t, ((b[0], b[1], b[2]), (b[3], b[4], b[5]))))
        return resultado

    def caja_escena(self):
        return geo.caja_union([c for _, c in self._mallas()])

    def camara_render(self):
        candidatas = []
        for forma in cmds.ls(type="camera", long=True) or []:
            if cmds.getAttr(forma + ".orthographic"):
                continue
            t = _transform(forma)
            candidatas.append((bool(cmds.getAttr(forma + ".renderable")), _corto(t) != "persp", t))
        if not candidatas:
            return None, None
        candidatas.sort(reverse=True)
        t = candidatas[0][2]
        return _corto(t), tuple(cmds.xform(t, query=True, worldSpace=True, translation=True))

    def ventanas_seleccionadas(self):
        """Huecos a partir de caras seleccionadas (agrupadas por objeto) o de objetos enteros."""
        huecos = []
        escena = self.caja_escena()
        centro_escena = geo.centro(escena) if escena else (0.0, 0.0, 0.0)
        caras = cmds.filterExpand(selectionMask=34, fullPath=True) or []
        por_objeto = {}
        for c in caras:
            por_objeto.setdefault(c.split(".")[0], []).append(c)
        for objeto, lista in por_objeto.items():
            b = cmds.exactWorldBoundingBox(lista)
            normales = []
            for cara in lista:
                texto = cmds.polyInfo(cara, faceNormals=True)[0].split()
                n = (float(texto[-3]), float(texto[-2]), float(texto[-1]))
                m = cmds.xform(objeto, query=True, worldSpace=True, matrix=True)
                normales.append((n[0] * m[0] + n[1] * m[4] + n[2] * m[8], n[0] * m[1] + n[1] * m[5] + n[2] * m[9],
                                 n[0] * m[2] + n[1] * m[6] + n[2] * m[10]))
            normal = geo.unitario(tuple(sum(n[i] for n in normales) for i in range(3)))
            huecos.append(self._hueco((b[0], b[1], b[2]), (b[3], b[4], b[5]), normal, centro_escena, objeto))
        objetos = [n for n in (cmds.ls(selection=True, long=True, transforms=True) or []) if n not in por_objeto]
        for objeto in objetos:
            if not cmds.listRelatives(objeto, allDescendents=True, type="mesh"):
                continue
            b = cmds.exactWorldBoundingBox(objeto)
            mn, mx = (b[0], b[1], b[2]), (b[3], b[4], b[5])
            medidas = [mx[i] - mn[i] for i in range(3)]
            eje = 0 if medidas[0] < medidas[2] else 2
            normal = (1.0, 0.0, 0.0) if eje == 0 else (0.0, 0.0, 1.0)
            huecos.append(self._hueco(mn, mx, normal, centro_escena, objeto))
        return huecos

    @staticmethod
    def _hueco(mn, mx, normal, centro_escena, objeto):
        centro = geo.centro((mn, mx))
        # La normal tiene que mirar hacia fuera de la casa (lejos del centro de la escena).
        if geo.punto(normal, geo.resta(centro, centro_escena)) < 0:
            normal = geo.escala(normal, -1.0)
        medidas = [mx[i] - mn[i] for i in range(3)]
        alto = medidas[1] if abs(normal[1]) < 0.7 else max(medidas[0], medidas[2])
        horizontales = [medidas[0], medidas[2]]
        ancho = max(horizontales) if abs(normal[1]) < 0.7 else min(medidas[0], medidas[2])
        return centro, normal, max(ancho, 1e-3), max(alto, 1e-3), _corto(objeto)

    def objetos_seleccionados(self):
        resultado = []
        for t in cmds.ls(selection=True, long=True, transforms=True) or []:
            if cmds.listRelatives(t, shapes=True, type=list(TIPOS_NODO)):
                continue
            c = self.caja([t])
            if c:
                resultado.append((_unico(t), c))
        return resultado

    def crear_luz_de_malla(self, objeto, nombre):
        _mtoa()
        import mtoa.utils as mu
        cmds.select(objeto, replace=True)
        mu.createMeshLight()
        formas = cmds.ls(selection=True, long=True) or []
        luz = None
        for n in formas:
            for f in [n] + (cmds.listRelatives(n, shapes=True, fullPath=True) or []):
                if cmds.nodeType(f) == "aiMeshLight":
                    luz = _transform(f)
        if luz is None:
            todas = cmds.ls(type="aiMeshLight", long=True) or []
            luz = _transform(todas[-1])
        t = cmds.rename(luz, nombre)
        t = _unico(cmds.ls(t, long=True)[0])
        _poner_lm(t, "encendida", True)
        _poner_lm(t, "papel", "Prácticas")
        return t

    # --- enlaces -------------------------------------------------------------------------
    def objetos_enlazables(self):
        vistos = []
        for t, _ in self._mallas():
            vistos.append((_unico(t), _corto(t)))
        return sorted(vistos, key=lambda x: x[1].lower())

    def estado_enlace(self, luz, objeto):
        forma = _forma(luz)
        try:
            iluminados = set(cmds.lightlink(query=True, light=forma, transforms=True, shapes=False) or [])
        except Exception:
            return 2
        if _corto(objeto) not in {_corto(n) for n in iluminados}:
            return 0
        try:
            sombras = set(cmds.lightlink(query=True, light=forma, shadow=True, transforms=True, shapes=False) or [])
        except Exception:
            return 2
        return 2 if _corto(objeto) in {_corto(n) for n in sombras} else 1

    def poner_enlace(self, luz, objeto, estado):
        forma = _forma(luz)
        if estado == 0:
            cmds.lightlink(b=True, light=forma, object=objeto)
            cmds.lightlink(b=True, light=forma, object=objeto, shadow=True)
        elif estado == 1:
            cmds.lightlink(make=True, light=forma, object=objeto)
            cmds.lightlink(b=True, light=forma, object=objeto, shadow=True)
            self._usar_enlaces_de_sombra()
        else:
            cmds.lightlink(make=True, light=forma, object=objeto)
            cmds.lightlink(make=True, light=forma, object=objeto, shadow=True)

    @staticmethod
    def _usar_enlaces_de_sombra():
        """Arnold tiene que leer los enlaces de sombra de Maya (por defecto siguen a los de luz)."""
        try:
            if cmds.objExists("defaultArnoldRenderOptions"):
                cmds.setAttr("defaultArnoldRenderOptions.shadowLinking", 2)
        except Exception:
            pass

    # --- zonas ----------------------------------------------------------------------------
    def zonas(self):
        resultado = []
        for t in cmds.ls("*." + ATTR_ZONA, objectsOnly=True, long=True) or []:
            nombre = cmds.getAttr(t + "." + ATTR_ZONA) or _corto(t)
            caja = self.caja([t])
            if caja:
                resultado.append(Zona(nombre, caja, _unico(t)))
        return resultado

    def crear_zona(self, nombre, caja):
        mn, mx = caja
        puntos = [(-.5, -.5, -.5), (.5, -.5, -.5), (.5, -.5, .5), (-.5, -.5, .5), (-.5, -.5, -.5), (-.5, .5, -.5),
                  (.5, .5, -.5), (.5, -.5, -.5), (.5, .5, -.5), (.5, .5, .5), (.5, -.5, .5), (.5, .5, .5),
                  (-.5, .5, .5), (-.5, -.5, .5), (-.5, .5, .5), (-.5, .5, -.5)]
        t = cmds.curve(degree=1, point=puntos, name=nombres.de_zona(nombre))
        cmds.addAttr(t, longName=ATTR_ZONA, dataType="string")
        cmds.setAttr(t + "." + ATTR_ZONA, nombre, type="string")
        c = geo.centro(caja)
        cmds.xform(t, worldSpace=True, translation=c)
        cmds.setAttr(t + ".scale", max(mx[0] - mn[0], 1e-3), max(mx[1] - mn[1], 1e-3), max(mx[2] - mn[2], 1e-3))
        forma = cmds.listRelatives(t, shapes=True, fullPath=True)[0]
        cmds.setAttr(forma + ".overrideEnabled", 1)
        cmds.setAttr(forma + ".overrideRGBColors", 1)
        cmds.setAttr(forma + ".overrideColorRGB", 0.29, 0.61, 0.82)
        # Rótulo con el nombre, encima de la caja, sin flecha.
        try:
            rotulo = cmds.annotate(t, text=nombre, point=(c[0], mx[1], c[2]))
            cmds.setAttr(rotulo + ".displayArrow", 0)
            rt = _transform(rotulo)
            cmds.parent(rt, t)
            cmds.rename(rt, nombres.de_zona(nombre) + "_rotulo")
        except Exception:
            pass
        try:
            t = cmds.parent(t, self._grupo(nombres.GRUPO_ZONAS))[0]
        except Exception:
            pass
        return _unico(cmds.ls(t, long=True)[0])

    def borrar_zona(self, nodo):
        if cmds.objExists(nodo):
            cmds.delete(nodo)

    def grupos_outliner(self):
        resultado = []
        for t in cmds.ls(assemblies=True, long=True) or []:
            corto = _corto(t)
            if corto in ("persp", "top", "front", "side") or corto.startswith(nombres.PREFIJO):
                continue
            if cmds.listRelatives(t, shapes=True):
                continue  # un objeto suelto, no un grupo
            if not cmds.listRelatives(t, allDescendents=True, type="mesh"):
                continue
            resultado.append((corto.replace("_", " "), self.caja([t])))
        return resultado

    # --- cielo, sol y render ---------------------------------------------------------------
    def cielo_fisico(self, nodo, azimut, altura, norte, activo=True):
        from lightmanager import sol as solar
        forma = _forma(nodo)
        _mtoa()
        entradas = cmds.listConnections(forma + ".color", source=True, destination=False) or []
        cielo = next((n for n in entradas if cmds.nodeType(n) == "aiPhysicalSky"), None)
        if cielo is None:
            for n in entradas:
                cmds.disconnectAttr(n + ".outColor", forma + ".color")
            cielo = cmds.shadingNode("aiPhysicalSky", asTexture=True, name="LM_cielo_fisico")
            cmds.connectAttr(cielo + ".outColor", forma + ".color", force=True)
        # Con «useDegrees» apagado, el cielo usa directamente la dirección del sol:
        # así no dependemos de cómo mide Arnold el azimut.
        v = solar.vector_escena(azimut, max(altura, -5.0), norte)
        # La dirección se da en el espacio del domo: se quita el giro del domo.
        giro = math.radians(cmds.getAttr(nodo + ".rotateY"))
        x = v[0] * math.cos(-giro) + v[2] * math.sin(-giro)
        z = -v[0] * math.sin(-giro) + v[2] * math.cos(-giro)
        if not _poner(cielo, ("useDegrees", "use_degrees"), False):
            _poner(cielo, ("elevation",), max(altura, 0.0))
            _poner(cielo, ("azimuth",), (azimut + norte) % 360.0)
        _poner(cielo, ("sunDirection", "sun_direction"), (x, v[1], z))
        _poner(cielo, ("enableSun", "enable_sun"), False)  # el sol lo pone la luz direccional
        _poner(cielo, ("intensity",), 1.0 if altura > -2 else 0.05)

    def quitar_cielo_fisico(self, nodo):
        forma = _forma(nodo)
        for n in cmds.listConnections(forma + ".color", source=True, destination=False) or []:
            if cmds.nodeType(n) == "aiPhysicalSky":
                cmds.disconnectAttr(n + ".outColor", forma + ".color")

    def crear_aovs_grupos(self, grupos):
        if not grupos or not _mtoa():
            return []
        try:
            import mtoa.aovs as aovs
            interfaz = aovs.AOVInterface()
            if not cmds.objExists("aiAOV_RGBA"):
                interfaz.addAOV("RGBA")
            cmds.setAttr("aiAOV_RGBA.lightGroups", 1)
            if cmds.attributeQuery("lightGroupsList", node="aiAOV_RGBA", exists=True):
                cmds.setAttr("aiAOV_RGBA.lightGroupsList", " ".join(grupos), type="string")
        except Exception as error:
            self.aviso(str(error))
            return []
        return ["RGBA_" + g for g in grupos]

    def convertir_tx(self, ruta):
        maketx = self._maketx()
        if not maketx or not os.path.exists(ruta):
            return None
        destino = os.path.splitext(ruta)[0] + ".tx"
        try:
            subprocess.check_call([maketx, "-v", "-u", "--oiio", "--monochrome-detect", "--constant-color-detect",
                                   "--opaque-detect", "-o", destino, ruta])
        except Exception as error:
            self.aviso(str(error))
            return None
        return destino if os.path.exists(destino) else None

    @staticmethod
    def _maketx():
        try:
            carpeta = os.path.dirname(cmds.pluginInfo("mtoa", query=True, path=True))
        except Exception:
            return None
        for base in (os.path.join(carpeta, "..", "bin"), carpeta):
            for nombre in ("maketx", "maketx.exe"):
                r = os.path.normpath(os.path.join(base, nombre))
                if os.path.exists(r):
                    return r
        return None

    def miniatura(self, ruta, destino, ancho=160):
        import maya.api.OpenMaya as om
        try:
            imagen = om.MImage()
            imagen.readFromFile(ruta)
            w, h = imagen.getSize()
            if not w or not h:
                return False
            imagen.resize(ancho, max(1, int(ancho * h / float(w))), True)
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            imagen.writeToFile(destino, "png")
            return os.path.exists(destino)
        except Exception:
            return False

    def info_comprobaciones(self, luces):
        info = {"encerradas": []}
        mallas = self._mallas()
        for l in luces:
            if not l.es_practica or l.tipo == "malla":
                continue
            for t, caja in mallas:
                if geo.tamano(caja) > 3.0 * max(l.tamano * 10, 0.5):
                    continue  # una habitación entera no es una pantalla
                if geo.dentro(l.posicion, caja) and self.estado_enlace(l.nodo, t) == 2:
                    info["encerradas"].append((l.nodo, _unico(t)))
                    break
        return info

    # --- datos, deshacer y avisos ---------------------------------------------------------
    def leer_dato(self, clave):
        valor = cmds.fileInfo(clave, query=True)
        if not valor:
            return ""
        try:
            return base64.b64decode(valor[0].encode("ascii")).decode("utf-8")
        except Exception:
            return ""

    def escribir_dato(self, clave, valor):
        cmds.fileInfo(clave, base64.b64encode((valor or "").encode("utf-8")).decode("ascii"))

    @contextlib.contextmanager
    def bloque(self, nombre="LightManager"):
        cmds.undoInfo(openChunk=True, chunkName=nombre)
        try:
            yield
        finally:
            cmds.undoInfo(closeChunk=True)

    def abrir_bloque(self, nombre="LightManager"):
        cmds.undoInfo(openChunk=True, chunkName=nombre)

    def cerrar_bloque(self):
        cmds.undoInfo(closeChunk=True)

    def aviso(self, texto):
        cmds.inViewMessage(assistMessage=texto, position="topCenter", fade=True, fadeStayTime=2500)
        print("LightManager | " + texto)

    def carpeta_proyecto(self):
        return cmds.workspace(query=True, rootDirectory=True) or ""
