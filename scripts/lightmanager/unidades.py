"""Unidades de luz que se entienden: pasos de exposición y grados Kelvin. No depende de Maya.

Arnold calcula la potencia de una luz como ``intensity * 2 ** exposure``. LightManager
la muestra como un solo número, los *pasos*: un paso más es el doble de luz. Al
escribir se respeta la ``intensity`` que ya tenga la luz y solo se cambia la
exposición, así una luz hecha a mano no cambia de aspecto al tocarla aquí.
"""

import math

PASOS_MIN = -4.0
PASOS_MAX = 24.0

# Atajos de temperatura (clave de texto, Kelvin).
TEMPERATURAS = (
    ("k_vela", 1900),
    ("k_tungsteno", 3200),
    ("k_halogeno", 3000),
    ("k_flash", 5600),
    ("k_nublado", 6500),
    ("k_cielo", 10000),
)


def pasos(intensidad, exposicion):
    """Potencia de Arnold en pasos. Una intensidad nula o negativa cuenta como apagada (-inf)."""
    if intensidad <= 0:
        return float("-inf")
    return math.log2(intensidad) + exposicion


def exposicion_para(pasos_deseados, intensidad):
    """Exposición que hay que poner, respetando ``intensidad``, para llegar a ``pasos_deseados``."""
    if intensidad <= 0:
        return pasos_deseados
    return pasos_deseados - math.log2(intensidad)


def recortar_pasos(valor):
    return max(PASOS_MIN, min(PASOS_MAX, valor))


def multiplicador(pasos_):
    """Cuánta luz es respecto a 0 pasos (2 ** pasos)."""
    return 2.0 ** pasos_


def kelvin_a_rgb(kelvin):
    """Color aproximado (0-1) de un cuerpo negro a ``kelvin`` grados (Tanner Helland).

    Sirve para pintar la muestra de color en el panel y para teñir luces que no
    tienen temperatura de color propia (el cielo). Las luces de Arnold usan su
    propio atributo de temperatura, que es más exacto.
    """
    t = max(1000.0, min(40000.0, float(kelvin))) / 100.0
    if t <= 66:
        r = 255.0
        g = 99.4708025861 * math.log(t) - 161.1195681661
    else:
        r = 329.698727446 * math.pow(t - 60, -0.1332047592)
        g = 288.1221695283 * math.pow(t - 60, -0.0755148492)
    if t >= 66:
        b = 255.0
    elif t <= 19:
        b = 0.0
    else:
        b = 138.5177312231 * math.log(t - 10) - 305.0447927307

    def c(v):
        return max(0.0, min(255.0, v)) / 255.0
    return (c(r), c(g), c(b))


def kelvin_a_hex(kelvin):
    r, g, b = kelvin_a_rgb(kelvin)
    return "#{:02x}{:02x}{:02x}".format(int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))


def color_normalizado(kelvin):
    """Color de ``kelvin`` con luminancia 1, para teñir una luz sin cambiar su potencia."""
    r, g, b = kelvin_a_rgb(kelvin)
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    if lum <= 0:
        return (1.0, 1.0, 1.0)
    return (r / lum, g / lum, b / lum)


def rgb_a_kelvin(rgb):
    """Temperatura aproximada de un color (para leer luces de Maya sin temperatura). Búsqueda simple."""
    r, g, b = rgb
    if max(r, g, b) <= 0:
        return 6500
    objetivo = (b / r) if r > 0 else 10.0
    mejor, error = 6500, 1e9
    for k in range(1500, 15001, 100):
        cr, cg, cb = kelvin_a_rgb(k)
        q = (cb / cr) if cr > 0 else 10.0
        e = abs(q - objetivo)
        if e < error:
            mejor, error = k, e
    return mejor


def texto_pasos(valor, decimales=1):
    """``8,0`` (coma decimal, como en la interfaz)."""
    if valor == float("-inf"):
        return "—"
    return ("{:." + str(decimales) + "f}").format(valor).replace(".", ",")
