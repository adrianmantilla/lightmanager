"""Biblioteca de HDRI: carpetas, miniaturas y el pack inicial de Poly Haven. No depende de Maya.

El pack inicial son ocho HDRI de Poly Haven (polyhaven.com), con licencia CC0:
se pueden usar para cualquier cosa sin pedir permiso ni citar. Se descargan al
pulsar el botón, a 2K, en la carpeta de HDRI que se haya elegido.
"""

import os

EXTENSIONES = (".hdr", ".exr", ".tx", ".tif", ".tiff", ".jpg", ".jpeg", ".png")
URL_POLYHAVEN = "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/2k/{}_2k.hdr"
WEB_POLYHAVEN = "https://polyhaven.com/a/{}"

# (nombre de archivo en Poly Haven, clave de texto, para qué sirve)
PACK_INICIAL = (
    ("studio_small_09", "hdri_estudio"),
    ("brown_photostudio_02", "hdri_estudio_calido"),
    ("kloofendal_48d_partly_cloudy_puresky", "hdri_mediodia"),
    ("venice_sunset", "hdri_atardecer"),
    ("rural_asphalt_road", "hdri_carretera"),
    ("lebombo", "hdri_interior"),
    ("potsdamer_platz", "hdri_ciudad"),
    ("dikhololo_night", "hdri_noche"),
)


def listar(carpetas):
    """[(nombre sin extensión, ruta)] de las imágenes de las carpetas. Si hay .tx y .hdr, gana el original."""
    vistos = {}
    for carpeta in carpetas:
        if not carpeta or not os.path.isdir(carpeta):
            continue
        for nombre in sorted(os.listdir(carpeta)):
            base, ext = os.path.splitext(nombre)
            if ext.lower() not in EXTENSIONES or base.startswith("."):
                continue
            base = base[:-3] if base.endswith("_2k") else base
            ruta = os.path.join(carpeta, nombre)
            if base in vistos and ext.lower() == ".tx":
                continue
            vistos[base] = ruta
    return sorted(vistos.items(), key=lambda x: x[0].lower())


def buscar(carpetas, nombre):
    """Ruta del HDRI ``nombre`` (sin extensión) en las carpetas, o None."""
    for base, ruta in listar(carpetas):
        if base == nombre or base == nombre + "_2k":
            return ruta
    return None


def ruta_miniatura(carpeta_miniaturas, ruta):
    base = os.path.splitext(os.path.basename(ruta))[0]
    return os.path.join(carpeta_miniaturas, base + ".png")


def miniatura_al_dia(carpeta_miniaturas, ruta):
    m = ruta_miniatura(carpeta_miniaturas, ruta)
    try:
        return os.path.exists(m) and os.path.getmtime(m) >= os.path.getmtime(ruta)
    except OSError:
        return False


def descargar_pack(carpeta, avance=None, abrir=None):
    """Descarga el pack inicial en ``carpeta``. Devuelve (descargados, fallidos).

    ``avance(i, total, nombre)`` se llama antes de cada archivo; si devuelve False
    se para. ``abrir`` permite cambiar ``urllib.request.urlopen`` en las pruebas.
    """
    if abrir is None:
        import urllib.request
        abrir = urllib.request.urlopen
    os.makedirs(carpeta, exist_ok=True)
    hechos, fallidos = [], []
    for i, (nombre, _) in enumerate(PACK_INICIAL):
        if avance is not None and avance(i, len(PACK_INICIAL), nombre) is False:
            break
        destino = os.path.join(carpeta, nombre + "_2k.hdr")
        if os.path.exists(destino):
            hechos.append(destino)
            continue
        temporal = destino + ".descargando"
        try:
            respuesta = abrir(URL_POLYHAVEN.format(nombre), timeout=60)
            with open(temporal, "wb") as f:
                while True:
                    bloque = respuesta.read(1 << 16)
                    if not bloque:
                        break
                    f.write(bloque)
            os.replace(temporal, destino)
            hechos.append(destino)
        except Exception as error:  # red cortada, proxy de la red local…
            fallidos.append((nombre, str(error)))
            try:
                os.remove(temporal)
            except OSError:
                pass
    return hechos, fallidos


# --- el sol de un HDRI ----------------------------------------------------------------------
# Un HDRI es una imagen lat-long: la fila de arriba es el cenit y la de abajo el nadir; de
# izquierda a derecha da una vuelta completa. Con el domo sin girar, el centro de la imagen
# mira hacia AZIMUT_CENTRO (grados, desde +Z hacia +X) y la imagen avanza en SENTIDO.
# (Convención de Arnold en Maya; se comprueba con herramientas/prueba_maya.py.)
AZIMUT_CENTRO = 180.0
SENTIDO = -1.0


def direccion_de_pixel(u, v):
    """(azimut, altura) del punto (u, v) de la imagen, con u y v entre 0 y 1."""
    azimut = AZIMUT_CENTRO + SENTIDO * (u - 0.5) * 360.0
    altura = 90.0 - v * 180.0
    return (azimut + 180.0) % 360.0 - 180.0, altura


def buscar_sol(ancho, alto, luminancias):
    """(azimut, altura, fuerza) del sol de un HDRI a partir de su brillo en una rejilla pequeña.

    ``luminancias`` va por filas, de arriba abajo. Busca el punto más brillante del
    hemisferio de arriba y hace la media de los píxeles casi igual de brillantes que
    lo rodean (en una miniatura de 8 bits el sol sale como una mancha blanca). ``fuerza``
    es lo que destaca sobre la media del cielo: por debajo de 2 casi no hay sol.
    Devuelve None si la imagen está vacía.
    """
    if not ancho or not alto or len(luminancias) < ancho * alto:
        return None
    filas = max(1, alto // 2)
    mejor, mi, mj = -1.0, 0, 0
    total = 0.0
    for j in range(filas):
        for i in range(ancho):
            v = luminancias[j * ancho + i]
            total += v
            if v > mejor:
                mejor, mi, mj = v, i, j
    media = total / float(ancho * filas) or 1e-6
    umbral = mejor * 0.92
    su, sv, n = 0.0, 0.0, 0
    radio = max(2, ancho // 16)
    for j in range(max(0, mj - radio), min(filas, mj + radio + 1)):
        for di in range(-radio, radio + 1):
            i = (mi + di) % ancho
            if luminancias[j * ancho + i] >= umbral:
                su += mi + di
                sv += j
                n += 1
    u = ((su / n) + 0.5) / ancho
    v = ((sv / n) + 0.5) / alto
    az, alt = direccion_de_pixel(u % 1.0, v)
    return az, max(1.0, alt), mejor / media
