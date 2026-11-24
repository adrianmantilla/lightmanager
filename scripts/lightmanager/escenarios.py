"""Escenarios e instantáneas: el estado de la iluminación guardado con nombre. No depende de Maya.

Un escenario guarda, de cada luz, si está encendida, su potencia, su color y su
posición, y además el cielo (HDRI y giro) y el sol (hora, fecha y ciudad). Se
guardan dentro de la escena con ``Servicios.escribir_dato``.
"""

import base64
import json

CLAVE = "lightmanager_escenarios"
CAMPOS = ("encendida", "pasos", "kelvin", "usa_kelvin", "posicion", "rotacion", "escala", "tamano", "hdri",
          "rotacion_cielo")


def foto(luces, sol=None, nombre="", descripcion=""):
    """Escenario a partir de las luces actuales. ``sol`` es un dict (hora, fecha, ciudad…) o None."""
    estado = {}
    for luz in luces:
        datos = {}
        for c in CAMPOS:
            v = getattr(luz, c)
            datos[c] = list(v) if isinstance(v, tuple) else v
        estado[luz.nodo] = datos
    return {"nombre": nombre, "descripcion": descripcion, "luces": estado, "sol": sol}


def diferencias(escenario, luces):
    """Cambios para volver a ``escenario``: [(nodo, {campo: valor})]. Las luces nuevas no se tocan."""
    cambios = []
    por_nodo = {l.nodo: l for l in luces}
    for nodo, datos in escenario.get("luces", {}).items():
        luz = por_nodo.get(nodo)
        if luz is None:
            continue
        distintos = {}
        for c, v in datos.items():
            if c not in CAMPOS:
                continue
            actual = getattr(luz, c)
            if isinstance(actual, tuple):
                v = tuple(v)
                if all(abs(a - b) < 1e-6 for a, b in zip(actual, v)):
                    continue
            elif isinstance(actual, float) and isinstance(v, (int, float)):
                if abs(actual - v) < 1e-6:
                    continue
            elif actual == v:
                continue
            distintos[c] = v
        if distintos:
            cambios.append((nodo, distintos))
    return cambios


def faltan(escenario, luces):
    """Luces del escenario que ya no están en la escena."""
    nodos = {l.nodo for l in luces}
    return [n for n in escenario.get("luces", {}) if n not in nodos]


def codificar(escenarios):
    texto = json.dumps(escenarios, ensure_ascii=False)
    return base64.b64encode(texto.encode("utf-8")).decode("ascii")


def decodificar(texto):
    if not texto:
        return []
    try:
        return json.loads(base64.b64decode(texto.encode("ascii")).decode("utf-8"))
    except (ValueError, TypeError):
        return []


def renombrar_nodo(escenarios, viejo, nuevo):
    """Mantiene los escenarios al día si una luz cambia de nombre."""
    for e in escenarios:
        luces = e.get("luces", {})
        if viejo in luces:
            luces[nuevo] = luces.pop(viejo)
