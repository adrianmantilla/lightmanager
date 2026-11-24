"""Nombres de nodos válidos en Maya a partir de nombres con tildes y espacios. No depende de Maya."""

import re
import unicodedata

PREFIJO = "LM_"
GRUPO_LUCES = "LM_luces"
GRUPO_ZONAS = "LM_zonas"


def limpio(texto):
    """«Lámpara de pie» -> «Lampara_de_pie». Nunca vacío ni empezando por número."""
    s = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^A-Za-z0-9_]+", "_", s).strip("_")
    if not s:
        s = "Luz"
    if s[0].isdigit():
        s = "_" + s
    return s


def de_luz(nombre):
    return PREFIJO + limpio(nombre)


def de_zona(nombre):
    return PREFIJO + "zona_" + limpio(nombre)


def siguiente(base, existentes):
    """``base`` si está libre; si no, ``base2``, ``base3``…"""
    existentes = set(existentes)
    if base not in existentes:
        return base
    m = re.match(r"^(.*?)(\d+)$", base)
    raiz, n = (m.group(1), int(m.group(2)) + 1) if m else (base, 2)
    while "{}{}".format(raiz, n) in existentes:
        n += 1
    return "{}{}".format(raiz, n)


def sin_numero(nombre):
    """«Downlight salón 3» -> «Downlight salón»."""
    return re.sub(r"[\s_]*\d+$", "", nombre) or nombre
