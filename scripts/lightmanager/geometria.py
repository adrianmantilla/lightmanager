"""Cuentas de colocación de luces. No depende de Maya.

Convenciones (las de Maya): Y hacia arriba, las luces alumbran hacia su -Z local
y el orden de rotación es XYZ. La *dirección* (azimut) de una luz en modo Estudio
se mide alrededor del objetivo y respecto a la cámara: 0° es desde el lado de la
cámara, 90° desde la derecha de la imagen y 180° desde detrás (contraluz). La
*altura* es el ángulo sobre el horizonte.
"""

import math


def suma(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def resta(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def escala(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def punto(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def largo(a):
    return math.sqrt(punto(a, a))


def unitario(a):
    n = largo(a)
    if n < 1e-12:
        return (0.0, 0.0, -1.0)
    return (a[0] / n, a[1] / n, a[2] / n)


def distancia(a, b):
    return largo(resta(a, b))


def direccion(azimut, altura):
    """Vector unitario hacia ``azimut`` (grados, desde +Z hacia +X) y ``altura`` (grados)."""
    a, e = math.radians(azimut), math.radians(altura)
    return (math.sin(a) * math.cos(e), math.sin(e), math.cos(a) * math.cos(e))


def angulos(vector):
    """(azimut, altura) en grados de un vector (inversa de ``direccion``)."""
    x, y, z = unitario(vector)
    altura = math.degrees(math.asin(max(-1.0, min(1.0, y))))
    azimut = math.degrees(math.atan2(x, z))
    return azimut, altura


def normalizar_angulo(grados):
    """Ángulo en (-180, 180]."""
    g = (grados + 180.0) % 360.0 - 180.0
    return 180.0 if g == -180.0 else g


def rotacion_para(direccion_luz):
    """Rotación XYZ (grados) para que el -Z local de una luz apunte hacia ``direccion_luz``.

    Con orden XYZ, girar ``x`` alrededor de X levanta el -Z hacia +Y y después
    ``y`` lo gira alrededor del eje vertical.
    """
    dx, dy, dz = unitario(direccion_luz)
    rx = math.degrees(math.asin(max(-1.0, min(1.0, dy))))
    horizontal = math.hypot(dx, dz)
    ry = math.degrees(math.atan2(-dx, -dz)) if horizontal > 1e-9 else 0.0
    return (rx, ry, 0.0)


def mirar(desde, hacia):
    """Rotación para que una luz en ``desde`` alumbre hacia ``hacia``."""
    return rotacion_para(resta(hacia, desde))


def azimut_de_camara(camara, objetivo):
    """Azimut (grados) de la cámara vista desde el objetivo, en el plano horizontal."""
    v = resta(camara, objetivo)
    if math.hypot(v[0], v[2]) < 1e-9:
        return 0.0
    return math.degrees(math.atan2(v[0], v[2]))


def posicion_orbita(objetivo, distancia_, azimut, altura, azimut_camara=0.0):
    """Posición de una luz a ``distancia_`` del objetivo, en (azimut, altura) relativos a la cámara."""
    return suma(objetivo, escala(direccion(azimut + azimut_camara, altura), distancia_))


def orbita_de(posicion, objetivo, azimut_camara=0.0):
    """(azimut relativo a la cámara, altura, distancia) de una luz que ya está en ``posicion``."""
    v = resta(posicion, objetivo)
    az, alt = angulos(v)
    return normalizar_angulo(az - azimut_camara), alt, largo(v)


# --- apuntar con un clic ---------------------------------------------------------------

def reflejar(vista, normal):
    """Refleja ``vista`` (del punto hacia la cámara) en la superficie de ``normal``."""
    n = unitario(normal)
    v = unitario(vista)
    return unitario(resta(escala(n, 2.0 * punto(n, v)), v))


def apuntar_luz(punto_, normal, distancia_):
    """Modo Luz: la luz de frente al punto, a lo largo de la normal."""
    pos = suma(punto_, escala(unitario(normal), distancia_))
    return pos, mirar(pos, punto_)


def apuntar_reflejo(punto_, normal, camara, distancia_):
    """Modo Reflejo: el brillo especular se ve en ``punto_`` desde ``camara``."""
    r = reflejar(resta(camara, punto_), normal)
    if punto(r, unitario(normal)) <= 0:  # rozando: se queda en la normal
        r = unitario(normal)
    pos = suma(punto_, escala(r, distancia_))
    return pos, mirar(pos, punto_)


def apuntar_sombra(punto_suelo, objetivo, distancia_):
    """Modo Sombra: la sombra de ``objetivo`` cae en ``punto_suelo``.

    La luz se pone en la recta que va del punto del suelo al objetivo, más allá
    de él, a ``distancia_`` del objetivo. Si quedara por debajo, se sube lo justo.
    """
    d = unitario(resta(objetivo, punto_suelo))
    if d[1] < 0.05:
        d = unitario((d[0], 0.05, d[2]))
    pos = suma(objetivo, escala(d, distancia_))
    return pos, mirar(pos, objetivo)


# --- modo Escena ----------------------------------------------------------------------

def pegar_a_superficie(punto_, normal, separacion):
    """Posición y rotación de una luz pegada a una superficie, alumbrando hacia fuera de ella.

    Un techo (normal hacia abajo) da una luz que mira al suelo; una pared, una luz
    que mira a la habitación.
    """
    n = unitario(normal)
    pos = suma(punto_, escala(n, separacion))
    return pos, rotacion_para(n)


def en_linea(inicio, fin, cantidad):
    """``cantidad`` posiciones repartidas por igual después de ``inicio``; la última es ``fin``."""
    cantidad = max(1, int(cantidad))
    return [suma(inicio, escala(resta(fin, inicio), i / float(cantidad))) for i in range(1, cantidad + 1)]


def caja_union(cajas):
    """Caja que envuelve varias ((min), (max)). None si no hay ninguna."""
    cajas = [c for c in cajas if c]
    if not cajas:
        return None
    mn = tuple(min(c[0][i] for c in cajas) for i in range(3))
    mx = tuple(max(c[1][i] for c in cajas) for i in range(3))
    return mn, mx


def centro(caja):
    mn, mx = caja
    return tuple((mn[i] + mx[i]) * 0.5 for i in range(3))


def tamano(caja):
    """La medida mayor de la caja (al menos 0,01)."""
    mn, mx = caja
    return max(0.01, max(mx[i] - mn[i] for i in range(3)))


def dentro(punto_, caja):
    mn, mx = caja
    return all(mn[i] <= punto_[i] <= mx[i] for i in range(3))


def direccion_de_rotacion(rotacion):
    """Hacia dónde alumbra (su -Z) una luz con rotación XYZ en grados."""
    rx, ry, rz = (math.radians(v) for v in rotacion)
    # Se aplica X, luego Y, luego Z al vector (0, 0, -1).
    x, y, z = 0.0, 0.0, -1.0
    y, z = y * math.cos(rx) - z * math.sin(rx), y * math.sin(rx) + z * math.cos(rx)
    x, z = x * math.cos(ry) + z * math.sin(ry), -x * math.sin(ry) + z * math.cos(ry)
    x, y = x * math.cos(rz) - y * math.sin(rz), x * math.sin(rz) + y * math.cos(rz)
    return unitario((x, y, z))
