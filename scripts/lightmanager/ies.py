"""Perfiles de lámpara (archivos IES) genéricos, hechos por LightManager. No depende de Maya.

Un perfil IES dice cuánta luz sale de una lámpara en cada dirección: es lo que
da el típico abanico de un downlight en la pared. Los ocho perfiles se generan
con fórmulas sencillas (no copian datos de ningún fabricante), así que se pueden
repartir sin problemas de licencia. Se escriben en formato LM-63-2002, simétricos
alrededor del eje vertical; el ángulo 0 mira hacia abajo.
"""

import math
import os

PICO_CANDELAS = 800.0
ANGULOS = [float(a) for a in range(0, 181, 5)]


def _gauss(x, ancho):
    return math.exp(-(x / ancho) ** 2)


def _corte(g, desde, hasta):
    """1 antes de ``desde``, 0 después de ``hasta``, suave entre medias."""
    if g <= desde:
        return 1.0
    if g >= hasta:
        return 0.0
    t = (g - desde) / (hasta - desde)
    return 0.5 + 0.5 * math.cos(math.pi * t)


# clave -> (clave de texto, función de reparto entre 0 y 1)
PERFILES = {
    "bombilla": ("ies_bombilla", lambda g: 1.0 if g < 150 else 0.3 + 0.7 * _corte(g, 150, 180)),
    "downlight": ("ies_downlight", lambda g: math.cos(math.radians(min(g, 90))) ** 1.5 * _corte(g, 40, 62)),
    "foco_estrecho": ("ies_foco_estrecho", lambda g: _gauss(g, 11.0)),
    "foco_ancho": ("ies_foco_ancho", lambda g: _gauss(g, 28.0)),
    "aplique": ("ies_aplique", lambda g: max(_gauss(g, 32.0), _gauss(180.0 - g, 32.0))),
    "pantalla": ("ies_pantalla", lambda g: 0.18 + 0.82 * max(_gauss(g, 48.0), 0.7 * _gauss(180.0 - g, 42.0))),
    "farola": ("ies_farola", lambda g: (0.4 + 0.6 * _gauss(g - 62.0, 16.0)) * _corte(g, 80, 96)),
    "tira": ("ies_tira", lambda g: _gauss(180.0 - g, 55.0)),
}
ORDEN = ("bombilla", "downlight", "foco_estrecho", "foco_ancho", "aplique", "pantalla", "farola", "tira")


def candelas(clave):
    funcion = PERFILES[clave][1]
    return [max(0.0, funcion(g)) * PICO_CANDELAS for g in ANGULOS]


def texto_ies(clave):
    valores = candelas(clave)
    lineas = [
        "IESNA:LM-63-2002",
        "[TEST] LightManager",
        "[MANUFAC] LightManager (perfil generico)",
        "[LUMCAT] {}".format(clave),
        "[LUMINAIRE] {}".format(clave),
        "TILT=NONE",
        # lámparas, lúmenes por lámpara, multiplicador, n.º ángulos verticales, horizontales,
        # tipo fotométrico (C), unidades (metros), ancho, largo, alto
        "1 -1 1 {} 1 1 2 0 0 0".format(len(ANGULOS)),
        "1 1 50",
        " ".join("{:g}".format(a) for a in ANGULOS),
        "0",
        " ".join("{:.2f}".format(v) for v in valores),
    ]
    return "\r\n".join(lineas) + "\r\n"


def ruta(carpeta, clave):
    return os.path.join(carpeta, "lightmanager_{}.ies".format(clave))


def asegurar(carpeta):
    """Escribe los perfiles que falten en ``carpeta``. Devuelve {clave: ruta}."""
    os.makedirs(carpeta, exist_ok=True)
    rutas = {}
    for clave in ORDEN:
        r = ruta(carpeta, clave)
        if not os.path.exists(r):
            with open(r, "w", encoding="ascii", newline="") as f:
                f.write(texto_ies(clave))
        rutas[clave] = r
    return rutas


def listar(carpetas):
    """[(nombre visible o clave de texto, ruta)] de los perfiles propios y los incluidos."""
    resultado = []
    for carpeta in carpetas:
        if not carpeta or not os.path.isdir(carpeta):
            continue
        for nombre in sorted(os.listdir(carpeta)):
            if nombre.lower().endswith(".ies"):
                resultado.append((nombre, os.path.join(carpeta, nombre)))
    return resultado


def clave_de(ruta_):
    """La clave del perfil incluido de ``ruta_`` (o None si es de otro sitio)."""
    base = os.path.splitext(os.path.basename(ruta_ or ""))[0]
    if base.startswith("lightmanager_") and base[13:] in PERFILES:
        return base[13:]
    return None
