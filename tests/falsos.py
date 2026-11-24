"""Servicios falsos: una escena de Maya hecha de diccionarios, para probar sin Maya."""

import contextlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from lightmanager import geometria as geo  # noqa: E402
from lightmanager.modelo import Luz  # noqa: E402
from lightmanager.servicios import Servicios  # noqa: E402
from lightmanager.zonas import Zona  # noqa: E402


class ServiciosFalsos(Servicios):
    def __init__(self):
        self._luces = {}
        self.orden = []
        self.objetos = {"taza": ((-0.5, 0.0, -0.5), (0.5, 1.0, 0.5))}
        self.sel = []
        self.camara = (0.0, 1.0, 6.0)
        self.datos = {}
        self.enlaces = {}
        self._zonas = {}
        self.grupos = []
        self.ventanas = []
        self.bloques = 0
        self.abiertos = 0
        self.avisos = []
        self.fisico = {}
        self.aovs = []
        self.tx = []

    # luces
    def luces(self):
        return [self._luces[n].copia() for n in self.orden]

    def crear(self, datos):
        datos = dict(datos)
        nombre = datos.pop("nombre")
        tipo = datos.pop("tipo")
        while nombre in self._luces:
            nombre += "1"
        campos = {k: v for k, v in datos.items() if k in Luz.CAMPOS}
        luz = Luz(nombre, tipo, **campos)
        if tipo == "cielo":
            luz.posicion = (0.0, 0.0, 0.0)
        self._luces[nombre] = luz
        self.orden.append(nombre)
        return nombre

    def escribir(self, nodo, campos):
        luz = self._luces[nodo]
        for c, v in campos.items():
            if c == "nombre":
                if v != nodo:
                    self._luces[v] = self._luces.pop(nodo)
                    self.orden[self.orden.index(nodo)] = v
                    luz.nodo = v
                    nodo = v
            else:
                setattr(luz, c, tuple(v) if isinstance(v, list) else v)
        return nodo

    def borrar(self, nodos):
        for n in nodos:
            self._luces.pop(n, None)
            if n in self.orden:
                self.orden.remove(n)

    def duplicar(self, nodo):
        nuevo = nodo + "_copia"
        while nuevo in self._luces:
            nuevo += "1"
        luz = self._luces[nodo].copia()
        luz.nodo = nuevo
        self._luces[nuevo] = luz
        self.orden.append(nuevo)
        return nuevo

    # escena
    def seleccionar(self, nodos):
        self.sel = list(nodos)

    def seleccion(self):
        return list(self.sel)

    def caja(self, nodos):
        return geo.caja_union([self.objetos.get(n) for n in nodos])

    def caja_escena(self):
        return geo.caja_union(list(self.objetos.values()))

    def camara_render(self):
        return ("camara", self.camara) if self.camara else (None, None)

    def ventanas_seleccionadas(self):
        return list(self.ventanas)

    def objetos_seleccionados(self):
        return [(n, self.objetos[n]) for n in self.sel if n in self.objetos]

    def crear_luz_de_malla(self, objeto, nombre):
        return self.crear({"nombre": nombre, "tipo": "malla", "pasos": 0.0})

    # enlaces
    def objetos_enlazables(self):
        return [(n, n) for n in sorted(self.objetos)]

    def estado_enlace(self, luz, objeto):
        return self.enlaces.get((luz, objeto), 2)

    def poner_enlace(self, luz, objeto, estado):
        self.enlaces[(luz, objeto)] = estado

    # zonas
    def zonas(self):
        return list(self._zonas.values())

    def crear_zona(self, nombre, caja):
        nodo = "LM_zona_" + nombre
        self._zonas[nodo] = Zona(nombre, caja, nodo)
        return nodo

    def borrar_zona(self, nodo):
        self._zonas.pop(nodo, None)

    def grupos_outliner(self):
        return list(self.grupos)

    # cielo
    def cielo_fisico(self, nodo, azimut, altura, norte, activo=True):
        self.fisico[nodo] = (azimut, altura, norte)
        self._luces[nodo].cielo_fisico = True

    def quitar_cielo_fisico(self, nodo):
        self.fisico.pop(nodo, None)
        self._luces[nodo].cielo_fisico = False

    def crear_aovs_grupos(self, grupos):
        self.aovs = ["RGBA_" + g for g in grupos]
        return self.aovs

    def convertir_tx(self, ruta):
        self.tx.append(ruta)
        return os.path.splitext(ruta)[0] + ".tx"

    def info_comprobaciones(self, luces):
        return {"sin_disco": True}

    # datos y deshacer
    def leer_dato(self, clave):
        return self.datos.get(clave, "")

    def escribir_dato(self, clave, valor):
        self.datos[clave] = valor

    @contextlib.contextmanager
    def bloque(self, nombre="LightManager"):
        self.bloques += 1
        yield

    def abrir_bloque(self, nombre="LightManager"):
        self.abiertos += 1

    def cerrar_bloque(self):
        self.abiertos -= 1

    def aviso(self, texto):
        self.avisos.append(texto)
