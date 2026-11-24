"""Esquemas de iluminación: puntos de partida en .json. No depende de Maya.

Hay dos clases:

- **Estudio** (``modo: estudio``): luces colocadas alrededor de un objetivo, con
  azimut y altura respecto a la cámara y distancia en múltiplos del tamaño del
  objeto. Se ajustan a cualquier escala: una taza de 10 cm y un coche de 4 m
  quedan igual de iluminados.
- **Escena** (``modo: escena``, familias interior y exterior): no ponen luces
  alrededor de nada; dicen a qué hora va el sol, qué cielo hay, si se crean
  portales en las ventanas seleccionadas y si se encienden las prácticas.

Los esquemas propios («Mis esquemas») son archivos .json con el mismo formato en
la carpeta que se elija en Ajustes.
"""

import json
import math
import os

from lightmanager import geometria as geo

CARPETA_INCLUIDOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "esquemas")
FAMILIAS = ("estudio", "interior", "exterior", "mios")
# Tamaño de referencia de los esquemas: los pasos están pensados para un objeto de 1 unidad.
TAMANO_REFERENCIA = 1.0


class Esquema(object):
    def __init__(self, datos, origen=""):
        self.datos = datos
        self.id = datos.get("id") or os.path.splitext(os.path.basename(origen))[0]
        self.nombre = datos.get("nombre", self.id)
        self.descripcion = datos.get("descripcion", "")
        self.familia = datos.get("familia", "mios")
        self.modo = datos.get("modo", "estudio")
        self.hdri = datos.get("hdri")
        self.luces = list(datos.get("luces", []))
        self.origen = origen

    @property
    def es_estudio(self):
        return self.modo == "estudio"

    def __repr__(self):
        return "Esquema({})".format(self.id)


def _leer(ruta):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def cargar(carpetas_propias=()):
    """Todos los esquemas: los incluidos y los de las carpetas propias (familia «mios»).

    Un .json propio puede tener un esquema suelto o ``{"esquemas": [...]}``. Los
    archivos rotos se saltan sin parar la carga.
    """
    resultado = []
    for nombre in sorted(os.listdir(CARPETA_INCLUIDOS)):
        if nombre.endswith(".json"):
            datos = _leer(os.path.join(CARPETA_INCLUIDOS, nombre))
            for e in datos.get("esquemas", []):
                e.setdefault("familia", datos.get("familia", "estudio"))
                resultado.append(Esquema(e, nombre))
    vistos = {e.id for e in resultado}
    for carpeta in carpetas_propias:
        if not carpeta or not os.path.isdir(carpeta):
            continue
        for nombre in sorted(os.listdir(carpeta)):
            if not nombre.lower().endswith(".json"):
                continue
            ruta = os.path.join(carpeta, nombre)
            try:
                datos = _leer(ruta)
            except (OSError, ValueError):
                continue
            lista = datos.get("esquemas") if isinstance(datos, dict) and "esquemas" in datos else [datos]
            for e in lista:
                if not isinstance(e, dict):
                    continue
                e = dict(e)
                e["familia"] = "mios"
                esquema = Esquema(e, ruta)
                if esquema.id in vistos:
                    esquema.id = "mio_" + esquema.id
                vistos.add(esquema.id)
                resultado.append(esquema)
    return resultado


def por_familia(esquemas, familia):
    return [e for e in esquemas if e.familia == familia]


def buscar(esquemas, ident):
    for e in esquemas:
        if e.id == ident:
            return e
    raise KeyError(ident)


def colocar(esquema, caja, camara):
    """Luces listas para crear a partir de un esquema de estudio.

    ``caja`` es la caja del objetivo ((min), (max)); ``camara`` la posición de la
    cámara de render (o None: se mira desde +Z). Devuelve una lista de dicts con
    ``nombre, tipo, papel, grupo, pasos, kelvin, posicion, rotacion, escala, tamano, objetivo``.
    """
    objetivo = geo.centro(caja)
    tam = geo.tamano(caja)
    az_cam = geo.azimut_de_camara(camara, objetivo) if camara else 0.0
    resultado = []
    for d in esquema.luces:
        tipo = d.get("tipo", "area")
        luz = {
            "nombre": d.get("nombre", "Luz"),
            "tipo": tipo,
            "papel": d.get("papel", ""),
            "grupo": d.get("grupo", ""),
            "kelvin": int(d.get("kelvin", 6500)),
            "objetivo": objetivo,
            "pasos": float(d.get("pasos", 6.0)),
            "escala": (1.0, 1.0, 1.0),
            "tamano": 1.0,
        }
        az = float(d.get("azimut", 0.0))
        alt = float(d.get("altura", 30.0))
        if tipo == "cielo":
            luz["posicion"] = objetivo
            luz["rotacion"] = (0.0, 0.0, 0.0)
        elif tipo == "sol":
            direccion = geo.direccion(az + az_cam, alt)
            luz["posicion"] = geo.suma(objetivo, geo.escala(direccion, tam * 3.0))
            luz["rotacion"] = geo.rotacion_para(geo.escala(direccion, -1.0))
            luz["tamano"] = float(d.get("tamano", 0.5))  # grados de diámetro del sol
        else:
            dist = float(d.get("distancia", 2.5)) * tam
            pos = geo.posicion_orbita(objetivo, dist, az, alt, az_cam)
            luz["posicion"] = pos
            luz["rotacion"] = geo.mirar(pos, objetivo)
            lado = float(d.get("tamano", 0.5)) * tam
            if tipo == "area":
                luz["escala"] = (lado * 0.5, lado * 0.5, lado * 0.5)  # el área de Arnold mide 2x2
                luz["tamano"] = lado
            else:
                luz["tamano"] = lado * 0.25  # radio
            # Luz que cae con el cuadrado de la distancia: compensar la escala de la escena.
            luz["pasos"] += 2.0 * math.log2(tam / TAMANO_REFERENCIA)
        resultado.append(luz)
    return resultado


def desde_luces(luces, caja, camara, nombre, descripcion=""):
    """Esquema de estudio a partir de luces de la escena (para «Guardar como esquema»)."""
    objetivo = geo.centro(caja)
    tam = geo.tamano(caja)
    az_cam = geo.azimut_de_camara(camara, objetivo) if camara else 0.0
    datos = {"id": _ident(nombre), "nombre": nombre, "descripcion": descripcion, "modo": "estudio",
             "familia": "mios", "luces": []}
    for luz in luces:
        if luz.tipo == "portal":
            continue
        d = {"nombre": luz.nombre, "tipo": luz.tipo if luz.tipo in ("area", "sol", "cielo", "foco", "punto",
                                                                    "fotometrica") else "area",
             "papel": luz.papel, "grupo": luz.grupo, "kelvin": int(luz.kelvin), "pasos": round(luz.pasos, 2)}
        if luz.tipo == "sol":
            fwd = geo.direccion_de_rotacion(luz.rotacion)
            az, alt = geo.angulos(geo.escala(fwd, -1.0))
            d.update(azimut=round(geo.normalizar_angulo(az - az_cam), 1), altura=round(alt, 1), tamano=luz.tamano)
        elif luz.tipo == "cielo":
            d.update(azimut=0, altura=90)
            if luz.hdri:
                datos.setdefault("hdri", os.path.splitext(os.path.basename(luz.hdri))[0])
        else:
            az, alt, dist = geo.orbita_de(luz.posicion, objetivo, az_cam)
            lado = (luz.escala[0] * 2.0) if luz.tipo == "area" else luz.tamano * 4.0
            d.update(azimut=round(az, 1), altura=round(alt, 1), distancia=round(dist / tam, 3),
                     tamano=round(lado / tam, 3))
            d["pasos"] = round(luz.pasos - 2.0 * math.log2(tam / TAMANO_REFERENCIA), 2)
        datos["luces"].append(d)
    return datos


def _ident(nombre):
    import re
    import unicodedata
    s = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_") or "esquema"


def guardar(datos, carpeta):
    """Escribe ``datos`` en ``carpeta/<id>.json`` (sin pisar uno que exista) y devuelve la ruta."""
    os.makedirs(carpeta, exist_ok=True)
    base = datos.get("id") or _ident(datos.get("nombre", "esquema"))
    ruta = os.path.join(carpeta, base + ".json")
    n = 2
    while os.path.exists(ruta):
        ruta = os.path.join(carpeta, "{}_{}.json".format(base, n))
        n += 1
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
    return ruta


def hora_de(clave, salida, puesta):
    """Hora para un esquema de escena: «mediodia», «puesta-0.5», «salida+1» o un número."""
    if clave is None:
        return None
    if isinstance(clave, (int, float)):
        return float(clave)
    if salida is None or puesta is None:
        return 12.0
    if clave == "mediodia":
        return round(((salida + puesta) / 2.0) * 4) / 4.0
    for base, valor in (("puesta", puesta), ("salida", salida)):
        if clave.startswith(base):
            resto = clave[len(base):]
            desplazamiento = float(resto) if resto else 0.0
            return round((valor + desplazamiento) * 4) / 4.0
    return 12.0
