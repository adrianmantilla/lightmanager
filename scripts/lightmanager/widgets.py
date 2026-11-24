"""Controles propios del panel: deslizadores de pasos y Kelvin, y la vista de órbita del modo Estudio."""

import math

from lightmanager import unidades
from lightmanager.qt import QtCore, QtGui, QtWidgets, posicion_local

Qt = QtCore.Qt
Signal = QtCore.Signal

AMBAR = "#f2913d"


class Deslizador(QtWidgets.QWidget):
    """Deslizador con su casilla numérica.

    Mientras se arrastra solo cambia la casilla (``vivo``); al soltar, o al escribir
    un número, emite ``fijado`` una vez, para que cada cambio sea un solo Ctrl+Z.
    """

    vivo = Signal(float)
    fijado = Signal(float)

    def __init__(self, minimo, maximo, paso=0.1, decimales=1, sufijo="", padre=None):
        QtWidgets.QWidget.__init__(self, padre)
        self._escala = 10 ** decimales
        self._bloqueo = False
        capa = QtWidgets.QHBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(6)
        self.barra = QtWidgets.QSlider(Qt.Horizontal)
        self.barra.setRange(int(round(minimo * self._escala)), int(round(maximo * self._escala)))
        self.barra.setSingleStep(max(1, int(round(paso * self._escala))))
        self.barra.setPageStep(max(1, int(round(paso * self._escala * 10))))
        self.casilla = QtWidgets.QDoubleSpinBox()
        self.casilla.setRange(minimo, maximo)
        self.casilla.setDecimals(decimales)
        self.casilla.setSingleStep(paso)
        self.casilla.setKeyboardTracking(False)
        self.casilla.setFixedWidth(72)
        if sufijo:
            self.casilla.setSuffix(sufijo)
        capa.addWidget(self.barra, 1)
        capa.addWidget(self.casilla)
        self.barra.valueChanged.connect(self._de_barra)
        self.barra.sliderReleased.connect(lambda: self.fijado.emit(self.valor()))
        self.casilla.valueChanged.connect(self._de_casilla)

    def valor(self):
        return self.casilla.value()

    def poner(self, valor):
        """Cambia el valor sin emitir nada (al leer la luz)."""
        self._bloqueo = True
        try:
            self.casilla.setValue(valor)
            self.barra.setValue(int(round(valor * self._escala)))
        finally:
            self._bloqueo = False

    def _de_barra(self, entero):
        if self._bloqueo:
            return
        valor = entero / float(self._escala)
        self._bloqueo = True
        self.casilla.setValue(valor)
        self._bloqueo = False
        self.vivo.emit(valor)
        if not self.barra.isSliderDown():  # rueda del ratón o teclado
            self.fijado.emit(valor)

    def _de_casilla(self, valor):
        if self._bloqueo:
            return
        self._bloqueo = True
        self.barra.setValue(int(round(valor * self._escala)))
        self._bloqueo = False
        self.fijado.emit(valor)


class BarraKelvin(QtWidgets.QWidget):
    """Barra con el degradado de temperatura de color: se pincha o arrastra para elegir los Kelvin."""

    vivo = Signal(int)
    fijado = Signal(int)
    MINIMO, MAXIMO = 1500, 12000

    def __init__(self, padre=None):
        QtWidgets.QWidget.__init__(self, padre)
        self.setMinimumHeight(18)
        self.setMinimumWidth(120)
        self.setCursor(Qt.PointingHandCursor)
        self._valor = 6500
        self._arrastrando = False
        self.setToolTip("Kelvin")

    def valor(self):
        return self._valor

    def poner(self, kelvin):
        self._valor = int(max(self.MINIMO, min(self.MAXIMO, kelvin)))
        self.update()

    # Escala logarítmica: los cálidos ocupan más sitio, que es donde más se elige.
    def _x_de(self, kelvin):
        a, b = math.log(self.MINIMO), math.log(self.MAXIMO)
        return 6 + (math.log(kelvin) - a) / (b - a) * (self.width() - 12)

    def _kelvin_de(self, x):
        a, b = math.log(self.MINIMO), math.log(self.MAXIMO)
        f = max(0.0, min(1.0, (x - 6) / float(max(1, self.width() - 12))))
        return int(round(math.exp(a + f * (b - a)) / 50.0) * 50)

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        r = QtCore.QRectF(6, 4, self.width() - 12, self.height() - 8)
        g = QtGui.QLinearGradient(r.left(), 0, r.right(), 0)
        for i in range(11):
            k = math.exp(math.log(self.MINIMO) + i / 10.0 * (math.log(self.MAXIMO) - math.log(self.MINIMO)))
            g.setColorAt(i / 10.0, QtGui.QColor(unidades.kelvin_a_hex(k)))
        p.setPen(QtGui.QPen(QtGui.QColor("#262626"), 1))
        p.setBrush(QtGui.QBrush(g))
        p.drawRoundedRect(r, 4, 4)
        x = self._x_de(self._valor)
        p.setPen(QtGui.QPen(QtGui.QColor("#ffffff"), 2))
        p.setBrush(QtGui.QColor(unidades.kelvin_a_hex(self._valor)))
        p.drawEllipse(QtCore.QPointF(x, self.height() / 2.0), 6, 6)
        p.end()

    def mousePressEvent(self, evento):
        self._arrastrando = True
        self._mover(evento)

    def mouseMoveEvent(self, evento):
        if self._arrastrando:
            self._mover(evento)

    def mouseReleaseEvent(self, evento):
        if self._arrastrando:
            self._arrastrando = False
            self._mover(evento)
            self.fijado.emit(self._valor)

    def _mover(self, evento):
        self._valor = self._kelvin_de(posicion_local(evento).x())
        self.update()
        self.vivo.emit(self._valor)


class Orbita(QtWidgets.QWidget):
    """Vista desde arriba del modo Estudio: el objeto en el centro, la cámara abajo y las luces alrededor.

    Cada luz es un punto de su color. Arrastrar un punto la gira alrededor del objeto
    (y la acerca o aleja); la rueda sobre la luz elegida cambia su altura. Las
    luces se dan con ``poner_luces([(nodo, nombre, azimut, altura, distancia, color, activa)])``,
    con la distancia en múltiplos del tamaño del objeto.
    """

    elegida = Signal(str)
    movida = Signal(str, float, float)   # nodo, azimut, distancia (múltiplos del tamaño)
    altura = Signal(str, float)          # nodo, grados que se suman

    def __init__(self, padre=None):
        QtWidgets.QWidget.__init__(self, padre)
        self.setMinimumSize(200, 170)
        self.setMouseTracking(True)
        self.luces = []
        self.seleccion = set()
        self._arrastre = None
        self._radio_max = 4.0

    def poner_luces(self, luces, seleccion=()):
        self.luces = list(luces)
        self.seleccion = set(seleccion)
        lejos = [l[4] for l in self.luces if l[4] is not None]
        self._radio_max = max([3.0] + [d * 1.15 for d in lejos])
        self.update()

    # --- geometría de la vista -----------------------------------------------------------
    def _centro(self):
        return QtCore.QPointF(self.width() / 2.0, self.height() / 2.0 - 6)

    def _escala(self):
        return (min(self.width(), self.height() - 30) / 2.0 - 14) / self._radio_max

    def _punto(self, azimut, distancia):
        # Azimut 0 = lado de la cámara (abajo), 90 = derecha.
        a = math.radians(azimut)
        c, k = self._centro(), self._escala()
        return QtCore.QPointF(c.x() + math.sin(a) * distancia * k, c.y() + math.cos(a) * distancia * k)

    def _desde_punto(self, punto):
        c, k = self._centro(), self._escala()
        dx, dy = punto.x() - c.x(), punto.y() - c.y()
        az = math.degrees(math.atan2(dx, dy))
        return az, max(0.6, math.hypot(dx, dy) / max(k, 1e-6))

    def _luz_en(self, punto):
        for l in reversed(self.luces):
            if l[4] is None:
                continue
            q = self._punto(l[2], l[4])
            if math.hypot(q.x() - punto.x(), q.y() - punto.y()) < 11:
                return l
        return None

    # --- dibujo -----------------------------------------------------------------------------
    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QtGui.QColor("#2f2f2f"))
        c, k = self._centro(), self._escala()
        p.setPen(QtGui.QPen(QtGui.QColor("#3d3d3d"), 1, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        for r in (1, 2, 3, 4, 6, 8):
            if r <= self._radio_max:
                p.drawEllipse(c, r * k, r * k)
        # Objeto
        p.setPen(QtGui.QPen(QtGui.QColor("#8a8a8a"), 1))
        p.setBrush(QtGui.QColor("#5a5a5a"))
        p.drawEllipse(c, 0.5 * k, 0.5 * k)
        # Cámara (abajo)
        cam = QtCore.QPointF(c.x(), min(self.height() - 10.0, c.y() + self._radio_max * k + 4))
        p.setBrush(QtGui.QColor("#9c9c9c"))
        p.setPen(Qt.NoPen)
        p.drawPolygon(QtGui.QPolygonF([cam + QtCore.QPointF(-8, 6), cam + QtCore.QPointF(8, 6),
                                       cam + QtCore.QPointF(0, -6)]))
        fuente = p.font()
        fuente.setPointSizeF(max(7.0, fuente.pointSizeF() - 1))
        p.setFont(fuente)
        for nodo, nombre, az, alt, dist, color, activa in self.luces:
            if dist is None:
                continue
            q = self._punto(az, dist)
            col = QtGui.QColor(color)
            if not activa:
                col.setAlpha(70)
            # Rayo hacia el objeto
            p.setPen(QtGui.QPen(QtGui.QColor(col.red(), col.green(), col.blue(), 60), 2))
            p.drawLine(q, c)
            elegida = nodo in self.seleccion
            p.setPen(QtGui.QPen(QtGui.QColor("#ffffff" if elegida else "#202020"), 2 if elegida else 1))
            p.setBrush(col)
            radio = 7 + max(-2.0, min(3.0, (alt or 0) / 30.0))
            p.drawEllipse(q, radio, radio)
            p.setPen(QtGui.QColor("#e2e2e2" if activa else "#777777"))
            p.drawText(QtCore.QRectF(q.x() - 60, q.y() + 8, 120, 16), Qt.AlignHCenter | Qt.AlignTop, nombre)
        p.end()

    # --- ratón ------------------------------------------------------------------------------
    def mousePressEvent(self, evento):
        l = self._luz_en(QtCore.QPointF(posicion_local(evento)))
        if l is not None:
            self._arrastre = l[0]
            self.elegida.emit(l[0])

    def mouseMoveEvent(self, evento):
        punto = QtCore.QPointF(posicion_local(evento))
        if self._arrastre is None:
            self.setCursor(Qt.OpenHandCursor if self._luz_en(punto) else Qt.ArrowCursor)
            return
        az, dist = self._desde_punto(punto)
        self.luces = [(n, nom, az if n == self._arrastre else a, al, dist if n == self._arrastre else d, col, ac)
                      for n, nom, a, al, d, col, ac in self.luces]
        self.update()

    def mouseReleaseEvent(self, evento):
        if self._arrastre is None:
            return
        az, dist = self._desde_punto(QtCore.QPointF(posicion_local(evento)))
        nodo, self._arrastre = self._arrastre, None
        self.movida.emit(nodo, round(az, 1), round(dist, 2))

    def wheelEvent(self, evento):
        if not self.seleccion:
            return
        delta = evento.angleDelta().y()
        for nodo in self.seleccion:
            self.altura.emit(nodo, 5.0 if delta > 0 else -5.0)
        evento.accept()


def color_de_luz(luz):
    """Color para pintar una luz en la lista y en la órbita."""
    if luz.usa_kelvin or luz.tiene_temperatura:
        return unidades.kelvin_a_hex(luz.kelvin)
    r, g, b = (max(0.0, min(1.0, c)) for c in luz.color)
    return QtGui.QColor.fromRgbF(r, g, b).name()


def icono_color(color, lado=12, apagada=False):
    mapa = QtGui.QPixmap(lado, lado)
    mapa.fill(Qt.transparent)
    p = QtGui.QPainter(mapa)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    c = QtGui.QColor(color)
    if apagada:
        c.setAlpha(60)
    p.setBrush(c)
    p.setPen(QtGui.QPen(QtGui.QColor("#202020"), 1))
    p.drawEllipse(1, 1, lado - 2, lado - 2)
    p.end()
    return QtGui.QIcon(mapa)


def boton_herramienta(texto, ayuda="", comprobable=False):
    b = QtWidgets.QToolButton()
    b.setText(texto)
    b.setToolTip(ayuda)
    b.setCheckable(comprobable)
    b.setToolButtonStyle(Qt.ToolButtonTextOnly)
    return b
