"""Posición y color del sol a partir del lugar, la fecha y la hora. No depende de Maya.

Usa las fórmulas de la NOAA (precisión de minutos de arco, de sobra para iluminar).
El azimut se mide desde el norte hacia el este (0° norte, 90° este, 180° sur).
En la escena el norte es -Z (arriba en la vista Top de Maya) salvo que se gire
con ``norte`` (grados que hay que girar la escena para que su norte apunte a -Z).
"""

import datetime
import math

# Ciudades: (clave, nombre, latitud, longitud, huso horario estándar, regla de horario de verano).
CIUDADES = (
    ("madrid", "Madrid", 40.4168, -3.7038, 1, "eu"),
    ("barcelona", "Barcelona", 41.3874, 2.1686, 1, "eu"),
    ("sevilla", "Sevilla", 37.3891, -5.9845, 1, "eu"),
    ("valencia", "Valencia", 39.4699, -0.3763, 1, "eu"),
    ("bilbao", "Bilbao", 43.2630, -2.9350, 1, "eu"),
    ("santiago", "Santiago de Compostela", 42.8782, -8.5448, 1, "eu"),
    ("canarias", "Las Palmas de Gran Canaria", 28.1235, -15.4363, 0, "eu"),
    ("lisboa", "Lisboa", 38.7223, -9.1393, 0, "eu"),
    ("londres", "Londres", 51.5072, -0.1276, 0, "eu"),
    ("paris", "París", 48.8566, 2.3522, 1, "eu"),
    ("roma", "Roma", 41.9028, 12.4964, 1, "eu"),
    ("berlin", "Berlín", 52.5200, 13.4050, 1, "eu"),
    ("oslo", "Oslo", 59.9139, 10.7522, 1, "eu"),
    ("reikiavik", "Reikiavik", 64.1466, -21.9426, 0, None),
    ("nueva_york", "Nueva York", 40.7128, -74.0060, -5, "us"),
    ("los_angeles", "Los Ángeles", 34.0522, -118.2437, -8, "us"),
    ("mexico", "Ciudad de México", 19.4326, -99.1332, -6, None),
    ("bogota", "Bogotá", 4.7110, -74.0721, -5, None),
    ("lima", "Lima", -12.0464, -77.0428, -5, None),
    ("buenos_aires", "Buenos Aires", -34.6037, -58.3816, -3, None),
    ("santiago_chile", "Santiago de Chile", -33.4489, -70.6693, -4, None),
    ("el_cairo", "El Cairo", 30.0444, 31.2357, 2, None),
    ("dubai", "Dubái", 25.2048, 55.2708, 4, None),
    ("tokio", "Tokio", 35.6762, 139.6503, 9, None),
    ("sidney", "Sídney", -33.8688, 151.2093, 10, None),
)


def ciudad(clave):
    for c in CIUDADES:
        if c[0] == clave:
            return c
    raise KeyError(clave)


def _domingo_ultimo(anio, mes):
    d = datetime.date(anio, mes + 1, 1) - datetime.timedelta(days=1) if mes < 12 else datetime.date(anio, 12, 31)
    while d.weekday() != 6:
        d -= datetime.timedelta(days=1)
    return d


def _domingo_n(anio, mes, n):
    d = datetime.date(anio, mes, 1)
    while d.weekday() != 6:
        d += datetime.timedelta(days=1)
    return d + datetime.timedelta(days=7 * (n - 1))


def horario_de_verano(fecha, regla):
    """True si en ``fecha`` rige el horario de verano según ``regla`` («eu», «us» o None)."""
    if regla == "eu":
        return _domingo_ultimo(fecha.year, 3) <= fecha < _domingo_ultimo(fecha.year, 10)
    if regla == "us":
        return _domingo_n(fecha.year, 3, 2) <= fecha < _domingo_n(fecha.year, 11, 1)
    return False


def huso(fecha, huso_estandar, regla):
    return huso_estandar + (1 if horario_de_verano(fecha, regla) else 0)


def posicion(latitud, longitud, fecha, hora, huso_horas):
    """(azimut, altura) del sol en grados. ``hora`` es la hora local decimal (13.5 = 13:30)."""
    if isinstance(fecha, datetime.datetime):
        fecha = fecha.date()
    # Día juliano a las 0 h UTC y fracción del día en UTC.
    utc = hora - huso_horas
    a = (14 - fecha.month) // 12
    y = fecha.year + 4800 - a
    m = fecha.month + 12 * a - 3
    jdn = fecha.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    jd = jdn - 0.5 + utc / 24.0
    t = (jd - 2451545.0) / 36525.0

    l0 = (280.46646 + t * (36000.76983 + 0.0003032 * t)) % 360.0
    mm = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    mr = math.radians(mm)
    c = (math.sin(mr) * (1.914602 - t * (0.004817 + 0.000014 * t)) + math.sin(2 * mr) * (0.019993 - 0.000101 * t)
         + math.sin(3 * mr) * 0.000289)
    verdadera = l0 + c
    omega = 125.04 - 1934.136 * t
    aparente = verdadera - 0.00569 - 0.00478 * math.sin(math.radians(omega))
    oblicuidad0 = 23 + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60.0) / 60.0
    oblicuidad = oblicuidad0 + 0.00256 * math.cos(math.radians(omega))
    declinacion = math.degrees(math.asin(math.sin(math.radians(oblicuidad)) * math.sin(math.radians(aparente))))
    yv = math.tan(math.radians(oblicuidad / 2.0)) ** 2
    l0r = math.radians(l0)
    ecuacion_tiempo = 4 * math.degrees(
        yv * math.sin(2 * l0r) - 2 * e * math.sin(mr) + 4 * e * yv * math.sin(mr) * math.cos(2 * l0r)
        - 0.5 * yv * yv * math.sin(4 * l0r) - 1.25 * e * e * math.sin(2 * mr))
    minutos_solares = (utc * 60.0 + ecuacion_tiempo + 4 * longitud) % 1440.0
    angulo_horario = minutos_solares / 4.0 - 180.0
    if angulo_horario < -180:
        angulo_horario += 360.0

    lat = math.radians(latitud)
    dec = math.radians(declinacion)
    ha = math.radians(angulo_horario)
    cos_cenit = math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(ha)
    cenit = math.acos(max(-1.0, min(1.0, cos_cenit)))
    altura = 90.0 - math.degrees(cenit)
    # Refracción atmosférica (pequeña, se nota al amanecer).
    if altura > -0.575:
        te = math.tan(math.radians(altura)) if abs(altura) < 89.9 else 1e9
        if altura > 5:
            r = 58.1 / te - 0.07 / te ** 3 + 0.000086 / te ** 5
        else:
            r = 1735 + altura * (-518.2 + altura * (103.4 + altura * (-12.79 + altura * 0.711)))
        altura += r / 3600.0
    seno_cenit = math.sin(cenit)
    if abs(seno_cenit) < 1e-9:
        azimut = 180.0
    else:
        cos_az = (math.sin(lat) * math.cos(cenit) - math.sin(dec)) / (math.cos(lat) * seno_cenit)
        az = math.degrees(math.acos(max(-1.0, min(1.0, cos_az))))
        azimut = (az + 180.0) % 360.0 if angulo_horario > 0 else (540.0 - az) % 360.0
    return azimut, altura


def posicion_en(clave_ciudad, fecha, hora):
    c = ciudad(clave_ciudad)
    return posicion(c[2], c[3], fecha, hora, huso(fecha, c[4], c[5]))


def salida_y_puesta(clave_ciudad, fecha, paso=1.0 / 60.0):
    """(hora de salida, hora de puesta) locales, o (None, None) si no sale o no se pone."""
    salida = puesta = None
    anterior = posicion_en(clave_ciudad, fecha, 0.0)[1]
    h = paso
    while h <= 24.0:
        alt = posicion_en(clave_ciudad, fecha, h)[1]
        if anterior <= -0.833 < alt and salida is None:
            salida = h
        if anterior > -0.833 >= alt:
            puesta = h
        anterior = alt
        h += paso
    return salida, puesta


def temperatura(altura):
    """Temperatura de color aproximada de la luz directa del sol según su altura."""
    if altura <= 0:
        return 2000
    if altura >= 40:
        return 5600
    # De 2000 K en el horizonte a 5600 K a 40°, más rápido al principio.
    f = (altura / 40.0) ** 0.6
    return int(round((2000 + 3600 * f) / 50.0) * 50)


def potencia(altura, pasos_mediodia):
    """Pasos del sol según su altura: al ras del horizonte pierde luz por la atmósfera."""
    if altura <= 0:
        return pasos_mediodia - 8
    s = math.sin(math.radians(altura))
    return pasos_mediodia + math.log2(max(s, 0.02) ** 0.7)


def vector_escena(azimut, altura, norte=0.0):
    """Vector unitario hacia el sol en la escena de Maya (norte = -Z girado ``norte`` grados)."""
    a = math.radians(azimut + norte)
    e = math.radians(altura)
    return (math.sin(a) * math.cos(e), math.sin(e), -math.cos(a) * math.cos(e))


def texto_hora(hora):
    m = int(round(hora * 60)) % 1440
    return "{:02d}:{:02d}".format(m // 60, m % 60)
