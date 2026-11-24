"""Lo que LightManager necesita de Maya, en una clase aparte.

``maya_servicios.ServiciosMaya`` lo implementa con ``cmds`` y ``OpenMaya``; las
pruebas usan ``tests/falsos.py``, que guarda la escena en diccionarios. Así todo
lo que decide (``gestor.Gestor``) se puede probar sin Maya.

Campos que entiende ``escribir`` (los de ``modelo.Luz``): ``encendida`` (se guarda
aparte de la visibilidad), ``visible`` (visibilidad real del transform), ``solo``,
``pasos``, ``kelvin``, ``usa_kelvin``, ``color``, ``tamano``, ``muestras``, ``grupo``
(grupo de luz / AOV), ``papel``, ``zona``, ``gemela``, ``ies``, ``posicion``,
``rotacion``, ``escala``, ``objetivo``, ``visible_camara``, ``decay``, ``hdri``,
``rotacion_cielo``, ``portal_modo``, ``esquema`` y ``nombre`` (renombra).
"""

import contextlib


class Servicios(object):
    en_maya = False

    # --- luces ---------------------------------------------------------------------------
    def luces(self):
        """Todas las luces de la escena como ``modelo.Luz``."""
        return []

    def escribir(self, nodo, campos):
        """Cambia campos de una luz. Devuelve el nombre del nodo (cambia si se renombra)."""
        raise NotImplementedError

    def crear(self, datos):
        """Crea una luz. ``datos``: ``nombre``, ``tipo`` y cualquier campo de ``escribir``. Devuelve el nodo."""
        raise NotImplementedError

    def borrar(self, nodos):
        raise NotImplementedError

    def duplicar(self, nodo):
        raise NotImplementedError

    # --- selección y escena -------------------------------------------------------------
    def seleccionar(self, nodos):
        pass

    def seleccion(self):
        """Nodos seleccionados en Maya (transforms)."""
        return []

    def caja(self, nodos):
        """Caja ((min), (max)) de unos nodos, o None."""
        return None

    def caja_escena(self):
        """Caja de toda la geometría (sin luces ni zonas), o None si no hay nada."""
        return None

    def camara_render(self):
        """(nombre, posición) de la cámara de render, o (None, None)."""
        return None, None

    def ventanas_seleccionadas(self):
        """Huecos para portales a partir de la selección: [(centro, normal, ancho, alto, nombre)]."""
        return []

    def objetos_seleccionados(self):
        """Objetos de geometría seleccionados: [(nodo, caja)]."""
        return []

    def crear_luz_de_malla(self, objeto, nombre):
        """Convierte una malla en luz de malla. Devuelve el nodo de la luz."""
        raise NotImplementedError

    # --- enlaces -----------------------------------------------------------------------
    def objetos_enlazables(self):
        """[(nodo, nombre visible)] de los objetos que pueden recibir luz."""
        return []

    def estado_enlace(self, luz, objeto):
        """2 ilumina y hace sombra, 1 ilumina sin sombra, 0 no le afecta."""
        return 2

    def poner_enlace(self, luz, objeto, estado):
        raise NotImplementedError

    # --- zonas -------------------------------------------------------------------------
    def zonas(self):
        """[zonas.Zona] de la escena."""
        return []

    def crear_zona(self, nombre, caja):
        raise NotImplementedError

    def borrar_zona(self, nodo):
        raise NotImplementedError

    def grupos_outliner(self):
        """[(nombre, caja)] de los grupos de primer nivel que tienen geometría."""
        return []

    # --- cielo, sol y render ---------------------------------------------------------------
    def cielo_fisico(self, nodo, azimut, altura, norte, activo=True):
        """Conecta (o actualiza) un cielo físico de Arnold en el domo ``nodo``."""
        pass

    def quitar_cielo_fisico(self, nodo):
        pass

    def crear_aovs_grupos(self, grupos):
        """Crea los AOV de grupos de luz para ``grupos``. Devuelve los nombres creados."""
        return []

    def convertir_tx(self, ruta):
        """Convierte una imagen a .tx con maketx. Devuelve la ruta nueva o None."""
        return None

    def miniatura(self, ruta, destino, ancho=160):
        """Guarda una miniatura PNG de una imagen (HDR/EXR incluidos). True si pudo."""
        return False

    def info_comprobaciones(self, luces):
        """Datos para ``comprobaciones.revisar`` que no están en las luces."""
        return {}

    # --- datos guardados en la escena, deshacer, avisos ---------------------------------------
    def leer_dato(self, clave):
        return ""

    def escribir_dato(self, clave, valor):
        pass

    @contextlib.contextmanager
    def bloque(self, nombre="LightManager"):
        """Todo lo de dentro se deshace con un solo Ctrl+Z."""
        yield

    def abrir_bloque(self, nombre="LightManager"):
        pass

    def cerrar_bloque(self):
        pass

    def aviso(self, texto):
        print("LightManager | " + texto)

    def carpeta_proyecto(self):
        return ""
