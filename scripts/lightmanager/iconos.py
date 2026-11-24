"""Icono de LightManager (línea blanca fina sobre negro, como el resto de MantiTools)."""

import os

TRAZO = ('<path d="M5.2 6.4l5.6-2.2 2 5.2-5.6 2.2z"/>'
         '<path d="M12.8 6.2l5.7-1.4M13.6 8.3l6 .6M13.1 10.6l4.8 2.6"/>'
         '<path d="M8.9 11l1.1 3.2M10 14.2v6M10 14.2l-3.4 5.8M10 14.2l3.4 5.8"/>')
NOMBRE = "lightmanager_32.png"


def svg(color="#ffffff", grosor=0.85, fondo="#161616", radio=5):
    base = ""
    trazos = TRAZO
    if fondo:
        base = '<rect x="0" y="0" width="24" height="24" rx="{}" fill="{}" stroke="none"/>'.format(radio, fondo)
        trazos = '<g transform="translate(3.6 3.6) scale(0.7)">{}</g>'.format(TRAZO)
        grosor = grosor / 0.7
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">{}'
            '<g fill="none" stroke="{}" stroke-width="{}" stroke-linecap="round" stroke-linejoin="round">{}</g>'
            '</svg>').format(base, color, grosor, trazos)


def pixmap(lado=32, fondo="#161616"):
    from lightmanager.qt import QtCore, QtGui, QtSvg
    if QtSvg is None:
        return None
    render = QtSvg.QSvgRenderer(QtCore.QByteArray(svg(fondo=fondo).encode("utf-8")))
    mapa = QtGui.QPixmap(lado, lado)
    mapa.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(mapa)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    render.render(p)
    p.end()
    return mapa


def asegurar_icono(carpeta):
    ruta = os.path.join(carpeta, NOMBRE)
    if not os.path.isfile(ruta):
        os.makedirs(carpeta, exist_ok=True)
        m = pixmap(32)
        if m is not None:
            m.save(ruta)
    return ruta.replace("\\", "/")
