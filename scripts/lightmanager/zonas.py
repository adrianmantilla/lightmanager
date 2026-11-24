"""Zonas de la escena (salón, cocina, calle…) y a cuál pertenece cada luz. No depende de Maya.

Maya no sabe qué es una cocina, así que una zona es una caja con nombre: un nodo
``LM_zona_<nombre>`` (una caja de curvas, que no sale en el render) que se crea
desde un grupo del Outliner, dibujándola, o desde la selección. Cada luz
pertenece a la zona más pequeña que la contiene; si no está en ninguna, a
«Escena». Una luz puede fijar su zona a mano y entonces no cambia al moverla.
"""

from lightmanager import geometria as geo
from lightmanager.modelo import ZONA_GENERAL


class Zona(object):
    def __init__(self, nombre, caja, nodo=""):
        self.nombre = nombre
        self.caja = (tuple(caja[0]), tuple(caja[1]))
        self.nodo = nodo

    @property
    def volumen(self):
        mn, mx = self.caja
        return max(1e-9, (mx[0] - mn[0]) * (mx[1] - mn[1]) * (mx[2] - mn[2]))

    def contiene(self, punto):
        return geo.dentro(punto, self.caja)

    def __repr__(self):
        return "Zona({})".format(self.nombre)


def zona_de(punto, zonas):
    """Nombre de la zona más pequeña que contiene ``punto``, o «Escena»."""
    dentro = [z for z in zonas if z.contiene(punto)]
    if not dentro:
        return ZONA_GENERAL
    return min(dentro, key=lambda z: z.volumen).nombre


def caja_con_margen(caja, margen=0.02, alto_minimo=None):
    """Agranda la caja un poco (que una luz pegada al techo siga dentro)."""
    mn, mx = caja
    tam = geo.tamano(caja)
    m = tam * margen
    mn = [mn[0] - m, mn[1] - m, mn[2] - m]
    mx = [mx[0] + m, mx[1] + m, mx[2] + m]
    if alto_minimo is not None and mx[1] - mn[1] < alto_minimo:
        mx[1] = mn[1] + alto_minimo
    return tuple(mn), tuple(mx)


def desde_grupos(grupos):
    """Zonas a partir de grupos del Outliner: [(nombre, caja)] -> [Zona]. Salta los vacíos."""
    return [Zona(nombre, caja_con_margen(caja)) for nombre, caja in grupos if caja]


def reasignar(luces, zonas):
    """Pone ``luz.zona`` según su posición, salvo las que tienen la zona fijada (``zona`` empieza por «=»).

    Devuelve [(luz, zona_antes, zona_despues)] de las que cambian.
    """
    cambios = []
    for luz in luces:
        if luz.zona.startswith("="):
            continue
        if luz.tipo in ("cielo", "sol"):
            nueva = ZONA_GENERAL
        else:
            nueva = zona_de(luz.posicion, zonas)
        if nueva != luz.zona:
            cambios.append((luz, luz.zona, nueva))
            luz.zona = nueva
    return cambios


def nombre_visible(zona):
    """La zona sin la marca de fijada."""
    return zona[1:] if zona.startswith("=") else (zona or ZONA_GENERAL)
