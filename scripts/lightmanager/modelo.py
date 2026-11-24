"""Lo que LightManager sabe de cada luz, sin depender de Maya.

``Luz`` es una foto de una luz de la escena: la lee ``Servicios`` y la usa el
panel. Para cambiar algo se pasa por ``Gestor``, que escribe en Maya.
"""

# Tipos de luz: clave interna -> (clave de texto, tipo de nodo de la forma, tiene temperatura propia,
# qué significa el tamaño).
TIPOS = {
    "area": ("tipo_area", "aiAreaLight", True, "escala"),
    "sol": ("tipo_sol", "directionalLight", True, "angulo"),
    "cielo": ("tipo_cielo", "aiSkyDomeLight", False, None),
    "foco": ("tipo_foco", "spotLight", True, "radio"),
    "punto": ("tipo_punto", "pointLight", True, "radio"),
    "fotometrica": ("tipo_fotometrica", "aiPhotometricLight", True, "radio"),
    "malla": ("tipo_malla", "aiMeshLight", True, None),
    "portal": ("tipo_portal", "aiLightPortal", False, "escala"),
    "area_maya": ("tipo_area_maya", "areaLight", True, "escala"),
    "volumen": ("tipo_volumen", "volumeLight", True, "escala"),
}
TIPO_DE_NODO = {v[1]: k for k, v in TIPOS.items()}
TIPOS_DE_ARNOLD = ("area", "cielo", "fotometrica", "malla", "portal")
# Luces que se ven como «prácticas»: lámparas que están dentro de la escena.
PRACTICAS = ("foco", "punto", "fotometrica", "malla")

PAPELES = ("Clave", "Relleno", "Contra", "Ambiente", "Prácticas", "Ventanas", "Efecto")
ZONA_GENERAL = "Escena"


class Luz(object):
    """Foto de una luz. ``nodo`` es el transform (nombre largo o corto único)."""

    CAMPOS = ("nodo", "tipo", "encendida", "solo", "pasos", "kelvin", "usa_kelvin", "color", "tamano",
              "muestras", "grupo", "papel", "zona", "gemela", "ies", "posicion", "rotacion", "escala",
              "objetivo", "visible_camara", "decay", "hdri", "rotacion_cielo", "portal_modo", "esquema", "visible", "cielo_fisico")

    def __init__(self, nodo, tipo, **campos):
        self.nodo = nodo
        self.tipo = tipo
        self.encendida = True
        self.solo = False
        self.pasos = 0.0
        self.kelvin = 6500
        self.usa_kelvin = TIPOS.get(tipo, (None, None, False))[2]
        self.color = (1.0, 1.0, 1.0)
        self.tamano = 1.0
        self.muestras = 1
        self.grupo = ""
        self.papel = ""
        self.zona = ""
        self.gemela = ""
        self.ies = ""
        self.posicion = (0.0, 0.0, 0.0)
        self.rotacion = (0.0, 0.0, 0.0)
        self.escala = (1.0, 1.0, 1.0)
        self.objetivo = None
        self.visible_camara = False
        self.decay = 2
        self.hdri = ""
        self.rotacion_cielo = 0.0
        self.portal_modo = 0
        self.esquema = ""   # esquema que la creó (para «Reemplazar»)
        self.cielo_fisico = False  # domo con cielo físico de Arnold en vez de HDRI
        self.visible = True  # visibilidad real en Maya (encendida y no apagada por un solo)
        for clave, valor in campos.items():
            if clave not in self.CAMPOS:
                raise AttributeError("Luz no tiene el campo «{}»".format(clave))
            setattr(self, clave, valor)

    # --- nombres -------------------------------------------------------------------------
    @property
    def nombre(self):
        """Nombre corto, sin ruta ni el prefijo LM_."""
        corto = self.nodo.split("|")[-1]
        return corto[3:] if corto.startswith("LM_") else corto

    @property
    def texto_tipo(self):
        return TIPOS.get(self.tipo, ("tipo_otra",))[0]

    @property
    def tiene_temperatura(self):
        return TIPOS.get(self.tipo, (None, None, False))[2]

    @property
    def tipo_tamano(self):
        return TIPOS.get(self.tipo, (None, None, False, None))[3]

    @property
    def es_practica(self):
        return self.tipo in PRACTICAS

    @property
    def es_cielo(self):
        return self.tipo == "cielo"

    @property
    def emite(self):
        """Los portales no emiten luz: solo guían la del cielo."""
        return self.tipo != "portal"

    def copia(self):
        return Luz(**{c: getattr(self, c) for c in self.CAMPOS})

    def como_dict(self):
        return {c: (list(v) if isinstance(v, tuple) else v) for c, v in
                ((c, getattr(self, c)) for c in self.CAMPOS)}

    @classmethod
    def de_dict(cls, datos):
        campos = {}
        for c, v in datos.items():
            if c in cls.CAMPOS:
                campos[c] = tuple(v) if isinstance(v, list) else v
        return cls(**campos)

    def __repr__(self):
        return "Luz({}, {})".format(self.nodo, self.tipo)


def activa(luz, luces):
    """True si la luz cuenta en el render: encendida y, si hay alguna en solo, ella también."""
    if not luz.encendida:
        return False
    if any(l.solo and l.encendida for l in luces):
        return luz.solo
    return True


def agrupar(luces, por="papel"):
    """[(grupo, [luces])] por ``papel``, ``zona``, ``tipo`` o ``grupo`` (de luz/AOV), en orden estable."""
    orden = []
    grupos = {}
    for luz in luces:
        if por == "tipo":
            clave = luz.texto_tipo
        else:
            clave = getattr(luz, por) or ""
        if clave not in grupos:
            grupos[clave] = []
            orden.append(clave)
        grupos[clave].append(luz)
    if por == "papel":
        orden.sort(key=lambda g: (PAPELES.index(g) if g in PAPELES else len(PAPELES), g == "", g))
    elif por == "zona":
        orden.sort(key=lambda g: (g == "", g == ZONA_GENERAL, g.lower()))
    return [(g, grupos[g]) for g in orden]
