"""Panel acoplable de LightManager.

Arriba, la cabecera con el modo (Estudio | Escena) y cómo agrupar la lista. Debajo,
la vista: en Estudio, la órbita (desde arriba, con la cámara abajo); en Escena, el
visor de Maya desde arriba que pone ``Visor``. Luego las pestañas Luces, Esquemas,
Cielo, Enlaces, Escenarios y Comprobar.

El panel no llama a Maya: todo pasa por ``Gestor`` y por ``Visor`` (los clics en el
visor de Maya). Así se puede probar fuera de Maya con servicios falsos.
"""

import datetime
import os

import lightmanager
from lightmanager import estilo, geometria as geo, hdri as biblioteca, ies, unidades
from lightmanager import esquemas as esq
from lightmanager import sol as solar
from lightmanager.gestor import ErrorLightManager
from lightmanager.i18n import t
from lightmanager.modelo import PAPELES, TIPOS, ZONA_GENERAL, activa, agrupar
from lightmanager.qt import QtCore, QtGui, QtWidgets
from lightmanager.widgets import (AMBAR, BarraKelvin, Deslizador, Orbita, boton_herramienta, color_de_luz,
                                  icono_color)
from lightmanager.zonas import nombre_visible

Qt = QtCore.Qt
NOMBRE_OBJETO = "LightManagerPanel"
TIPOS_NUEVA = ("area", "foco", "punto", "fotometrica", "sol", "cielo")
AGRUPAR = ("papel", "zona", "tipo", "grupo")
FAMILIAS = ("estudio", "interior", "exterior", "mios")
ENLACE_TEXTO = {2: "●", 1: "◐", 0: "○"}
NIVEL_COLOR = {"ok": "#5cb85c", "aviso": "#e0a43a", "mal": "#d9534f"}
MAX_OBJETOS_ENLACE = 40


class Visor(object):
    """Lo que el panel necesita del visor de Maya. Esta versión no hace nada (fuera de Maya).

    ``interfaz_maya`` pone una que usa ``lightmanager.visor`` y ``lightmanager.vista``.
    """

    disponible = False

    def crear_vista(self, padre):
        """Widget con el visor de Maya desde arriba (modo Escena), o None."""
        return None

    def encuadrar(self):
        pass

    def pedir_clic(self, texto, funcion, repetir=False):
        """Espera un clic en el visor y llama ``funcion(punto, normal, camara)``."""
        return False

    def pedir_rectangulo(self, texto, funcion):
        """Espera un rectángulo arrastrado en la vista de arriba y llama ``funcion(caja)``."""
        return False

    def cancelar(self):
        pass


def _seccion(texto):
    return estilo.etiqueta(texto, "seccion")


def _fila(*widgets, estirar=True):
    w = QtWidgets.QWidget()
    capa = QtWidgets.QHBoxLayout(w)
    capa.setContentsMargins(0, 0, 0, 0)
    capa.setSpacing(6)
    for x in widgets:
        if x is None:
            capa.addStretch(1)
        else:
            capa.addWidget(x)
    if estirar and None not in widgets:
        capa.addStretch(1)
    return w


def _desplazable(contenido):
    zona = QtWidgets.QScrollArea()
    zona.setWidgetResizable(True)
    zona.setFrameShape(QtWidgets.QFrame.NoFrame)
    zona.setWidget(contenido)
    return zona


def _texto_papel(papel):
    return t("papel_" + (papel or ""))


class PanelLightManager(QtWidgets.QWidget):
    def __init__(self, gestor, visor=None, padre=None, padre_dialogos=None):
        QtWidgets.QWidget.__init__(self, padre)
        self.g = gestor
        self.visor = visor or Visor()
        self.padre_dialogos = padre_dialogos or self
        self.seleccion = []          # nodos elegidos en la lista
        self._bloqueo = False
        self._pendiente = False
        self._ultima_lectura = datetime.datetime.now()
        self._cola_miniaturas = []
        self._objetos_enlace = None  # None = todos los enlazables
        estilo.aplicar(self, NOMBRE_OBJETO)
        # Seis pestañas en un panel estrecho: un poco menos de relleno que en las ventanas.
        self.setStyleSheet(self.styleSheet() + "\n#%s QTabBar::tab { padding: 7px 9px; }" % NOMBRE_OBJETO)
        self.setMinimumWidth(320)
        self._construir()
        self.g.oyentes.append(self._al_cambiar_gestor)
        self.reloj_miniaturas = QtCore.QTimer(self)
        self.reloj_miniaturas.setInterval(30)
        self.reloj_miniaturas.timeout.connect(self._siguiente_miniatura)
        self.refrescar()

    # =========================================================================================
    # construcción
    # =========================================================================================
    def _construir(self):
        capa = QtWidgets.QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(0)
        capa.addWidget(self._cabecera())

        self.divisor = QtWidgets.QSplitter(Qt.Vertical)
        self.divisor.setChildrenCollapsible(True)
        self.pila_vista = QtWidgets.QStackedWidget()
        self.orbita = Orbita()
        self.orbita.elegida.connect(lambda n: self.elegir([n]))
        self.orbita.movida.connect(self._orbita_movida)
        self.orbita.altura.connect(self._orbita_altura)
        self.pila_vista.addWidget(self.orbita)
        self.hueco_vista = QtWidgets.QWidget()
        capa_hueco = QtWidgets.QVBoxLayout(self.hueco_vista)
        capa_hueco.setContentsMargins(0, 0, 0, 0)
        self.vista_maya = None
        self.sin_vista = estilo.etiqueta(t("vista_sin_maya"), "tenue", ajuste=True)
        self.sin_vista.setAlignment(Qt.AlignCenter)
        capa_hueco.addWidget(self.sin_vista)
        self.pila_vista.addWidget(self.hueco_vista)
        self.divisor.addWidget(self.pila_vista)

        self.pestanas = QtWidgets.QTabWidget()
        self.pestanas.setDocumentMode(True)
        self.pestanas.addTab(self._pestana_luces(), t("pes_luces"))
        self.pestanas.addTab(self._pestana_esquemas(), t("pes_esquemas"))
        self.pestanas.addTab(self._pestana_cielo(), t("pes_cielo"))
        self.pestanas.addTab(self._pestana_enlaces(), t("pes_enlaces"))
        self.pestanas.addTab(self._pestana_escenarios(), t("pes_escenarios"))
        self.pestanas.addTab(self._pestana_comprobar(), t("pes_comprobar"))
        self.pestanas.currentChanged.connect(lambda _: self._refrescar_pestana())
        self.divisor.addWidget(self.pestanas)
        self.divisor.setStretchFactor(0, 0)
        self.divisor.setStretchFactor(1, 1)
        self.divisor.setSizes([210, 600])
        capa.addWidget(self.divisor, 1)

        self.estado = estilo.etiqueta("", "tenue", ajuste=True)
        self.estado.setContentsMargins(10, 4, 10, 6)
        capa.addWidget(self.estado)

    def _cabecera(self):
        caja = QtWidgets.QWidget()
        capa = QtWidgets.QVBoxLayout(caja)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(0)
        marco, _ = estilo.cabecera("LightManager", AMBAR, lightmanager.__version__)
        capa.addWidget(marco)
        barra = QtWidgets.QWidget()
        fila = QtWidgets.QHBoxLayout(barra)
        fila.setContentsMargins(10, 6, 10, 6)
        fila.setSpacing(0)
        self.boton_estudio = QtWidgets.QToolButton()
        self.boton_escena = QtWidgets.QToolButton()
        for b, texto, lado, modo in ((self.boton_estudio, t("modo_estudio"), "izq", "estudio"),
                                     (self.boton_escena, t("modo_escena"), "der", "escena")):
            b.setText(texto)
            b.setCheckable(True)
            b.setAutoExclusive(True)
            estilo.rol(b, "segmento", lado=lado)
            b.clicked.connect(lambda _=False, m=modo: self.poner_modo(m))
            fila.addWidget(b)
        self.boton_estudio.setToolTip(t("modo_estudio_ayuda"))
        self.boton_escena.setToolTip(t("modo_escena_ayuda"))
        fila.addStretch(1)
        fila.addWidget(estilo.etiqueta(t("agrupar_por"), "tenue"))
        fila.addSpacing(6)
        self.combo_agrupar = QtWidgets.QComboBox()
        for clave in AGRUPAR:
            self.combo_agrupar.addItem(t("agrupar_" + clave), clave)
        self.combo_agrupar.currentIndexChanged.connect(self._agrupar_cambiado)
        fila.addWidget(self.combo_agrupar)
        capa.addWidget(barra)
        return caja

    # --- Luces ---------------------------------------------------------------------------------
    def _pestana_luces(self):
        w = QtWidgets.QWidget()
        capa = QtWidgets.QVBoxLayout(w)
        capa.setContentsMargins(8, 8, 8, 8)
        capa.setSpacing(6)

        self.boton_nueva = QtWidgets.QToolButton()
        self.boton_nueva.setText(t("nueva_luz"))
        self.boton_nueva.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        menu = QtWidgets.QMenu(self.boton_nueva)
        for tipo in TIPOS_NUEVA:
            menu.addAction(t(TIPOS[tipo][0]), lambda tp=tipo: self.nueva_luz(tp))
        self.boton_nueva.setMenu(menu)
        self.boton_duplicar = boton_herramienta(t("duplicar"), t("duplicar_ayuda"))
        self.boton_duplicar.clicked.connect(self.duplicar)
        self.boton_borrar = boton_herramienta(t("borrar"), t("borrar_ayuda"))
        self.boton_borrar.clicked.connect(self.borrar)
        capa.addWidget(_fila(self.boton_nueva, self.boton_duplicar, self.boton_borrar))

        # Apuntar en el visor
        self.botones_apuntar = {}
        fila_apuntar = [estilo.etiqueta(t("apuntar"), "tenue")]
        for i, modo in enumerate(("luz", "reflejo", "sombra")):
            b = QtWidgets.QToolButton()
            b.setText(t("apuntar_" + modo))
            b.setToolTip(t("apuntar_{}_ayuda".format(modo)))
            b.setCheckable(True)
            estilo.rol(b, "segmento", lado="izq" if i == 0 else ("der" if i == 2 else ""))
            b.clicked.connect(lambda marcado, m=modo: self.apuntar(m, marcado))
            self.botones_apuntar[modo] = b
            fila_apuntar.append(b)
        capa.addWidget(_fila(*fila_apuntar))

        # Herramientas del modo Escena
        self.fila_escena = QtWidgets.QWidget()
        capa_esc = QtWidgets.QHBoxLayout(self.fila_escena)
        capa_esc.setContentsMargins(0, 0, 0, 0)
        capa_esc.setSpacing(4)
        self.boton_superficie = QtWidgets.QToolButton()
        self.boton_superficie.setText(t("colocar"))
        self.boton_superficie.setToolTip(t("colocar_ayuda"))
        self.boton_superficie.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        menu_sup = QtWidgets.QMenu(self.boton_superficie)
        for perfil in ies.ORDEN:
            menu_sup.addAction(t("ies_" + perfil), lambda p=perfil: self.colocar("fotometrica", p))
        menu_sup.addSeparator()
        menu_sup.addAction(t("tipo_punto"), lambda: self.colocar("punto", None))
        menu_sup.addAction(t("tipo_area"), lambda: self.colocar("area", None))
        self.boton_superficie.setMenu(menu_sup)
        self.boton_portales = boton_herramienta(t("portales"), t("portales_ayuda"))
        self.boton_portales.clicked.connect(lambda: self._hacer(self.g.crear_portales, aviso="hecho_portales"))
        self.boton_lamparas = boton_herramienta(t("lamparas"), t("lamparas_ayuda"))
        self.boton_lamparas.clicked.connect(lambda: self._hacer(self.g.crear_lamparas, aviso="hecho_lamparas"))
        self.boton_malla = boton_herramienta(t("malla"), t("malla_ayuda"))
        self.boton_malla.clicked.connect(lambda: self._hacer(self.g.crear_luces_de_malla, aviso="hecho_malla"))
        self.boton_repetir = boton_herramienta(t("repetir"), t("repetir_ayuda"))
        self.boton_repetir.clicked.connect(self.repetir)
        self.boton_zonas = QtWidgets.QToolButton()
        self.boton_zonas.setText(t("zonas"))
        self.boton_zonas.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.menu_zonas = QtWidgets.QMenu(self.boton_zonas)
        self.menu_zonas.aboutToShow.connect(self._llenar_menu_zonas)
        self.boton_zonas.setMenu(self.menu_zonas)
        for b in (self.boton_superficie, self.boton_portales, self.boton_lamparas, self.boton_malla,
                  self.boton_repetir, self.boton_zonas):
            capa_esc.addWidget(b)
        capa_esc.addStretch(1)
        capa.addWidget(self.fila_escena)

        divisor = QtWidgets.QSplitter(Qt.Vertical)
        self.lista = QtWidgets.QTreeWidget()
        self.lista.setColumnCount(3)
        self.lista.setHeaderLabels([t("col_luz"), t("col_solo"), t("col_pasos")])
        self.lista.setRootIsDecorated(True)
        self.lista.setUniformRowHeights(True)
        self.lista.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        cab = self.lista.header()
        cab.setStretchLastSection(False)
        cab.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        cab.setSectionResizeMode(1, QtWidgets.QHeaderView.Fixed)
        cab.setSectionResizeMode(2, QtWidgets.QHeaderView.Fixed)
        self.lista.setColumnWidth(1, 38)
        self.lista.setColumnWidth(2, 58)
        self.lista.itemSelectionChanged.connect(self._seleccion_lista)
        self.lista.itemChanged.connect(self._casilla_lista)
        self.lista.itemClicked.connect(self._clic_lista)
        self.lista.setContextMenuPolicy(Qt.CustomContextMenu)
        self.lista.customContextMenuRequested.connect(self._menu_lista)
        divisor.addWidget(self.lista)
        divisor.addWidget(_desplazable(self._ficha()))
        divisor.setSizes([200, 320])
        capa.addWidget(divisor, 1)
        return w

    def _ficha(self):
        marco, capa = estilo.tarjeta()
        self.ficha = marco
        self.ficha_vacia = estilo.etiqueta(t("ficha_vacia"), "tenue", ajuste=True)
        capa.addWidget(self.ficha_vacia)
        self.ficha_cuerpo = QtWidgets.QWidget()
        f = estilo.formulario(self.ficha_cuerpo)
        f.setContentsMargins(0, 0, 0, 0)
        self.campo_nombre = QtWidgets.QLineEdit()
        self.campo_nombre.editingFinished.connect(self._renombrar)
        self.chip_tipo = estilo.etiqueta("", "tenue")
        f.addRow(t("f_nombre"), _fila(self.campo_nombre, self.chip_tipo, estirar=False))

        self.combo_papel = QtWidgets.QComboBox()
        for p in ("",) + PAPELES:
            self.combo_papel.addItem(_texto_papel(p), p)
        self.combo_papel.activated.connect(lambda _: self._cambiar("papel", self.combo_papel.currentData()))
        self.combo_zona = QtWidgets.QComboBox()
        self.combo_zona.activated.connect(self._zona_elegida)
        self.etiqueta_zona = QtWidgets.QLabel(t("f_zona"))
        f.addRow(t("f_papel"), self.combo_papel)
        f.addRow(self.etiqueta_zona, self.combo_zona)
        self.combo_grupo = QtWidgets.QComboBox()
        self.combo_grupo.setEditable(True)
        self.combo_grupo.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self.combo_grupo.lineEdit().editingFinished.connect(self._grupo_escrito)
        self.combo_grupo.activated.connect(lambda _: self._grupo_escrito())
        self.combo_grupo.setToolTip(t("f_grupo_ayuda"))
        f.addRow(t("f_grupo"), self.combo_grupo)

        self.potencia = Deslizador(unidades.PASOS_MIN, unidades.PASOS_MAX, 0.1, 1)
        self.potencia.fijado.connect(lambda v: self._cambiar("pasos", v))
        self.potencia.setToolTip(t("f_pasos_ayuda"))
        menos = boton_herramienta("½×", t("mitad"))
        menos.clicked.connect(lambda: self._cambiar("pasos", -1.0, relativo=True))
        mas = boton_herramienta("2×", t("doble"))
        mas.clicked.connect(lambda: self._cambiar("pasos", 1.0, relativo=True))
        f.addRow(t("f_pasos"), _fila(self.potencia, menos, mas, estirar=False))

        self.kelvin = BarraKelvin()
        self.kelvin.fijado.connect(lambda v: self._cambiar("kelvin", int(v)))
        self.kelvin.vivo.connect(lambda v: self.texto_kelvin.setText("{} K".format(v)))
        self.texto_kelvin = estilo.etiqueta("", "tenue")
        self.texto_kelvin.setFixedWidth(52)
        self.boton_temperaturas = QtWidgets.QToolButton()
        self.boton_temperaturas.setText("▾")
        self.boton_temperaturas.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        menu_k = QtWidgets.QMenu(self.boton_temperaturas)
        for clave, k in unidades.TEMPERATURAS:
            menu_k.addAction(icono_color(unidades.kelvin_a_hex(k)), "{} · {} K".format(t(clave), k),
                             lambda kk=k: self._cambiar("kelvin", kk))
        self.boton_temperaturas.setMenu(menu_k)
        self.fila_kelvin = _fila(self.kelvin, self.texto_kelvin, self.boton_temperaturas, estirar=False)
        self.etiqueta_kelvin = QtWidgets.QLabel(t("f_kelvin"))
        f.addRow(self.etiqueta_kelvin, self.fila_kelvin)

        self.giro_cielo = Deslizador(0, 360, 1, 0, "°")
        self.giro_cielo.fijado.connect(lambda v: self._cambiar("rotacion_cielo", v))
        self.etiqueta_giro = QtWidgets.QLabel(t("f_giro"))
        f.addRow(self.etiqueta_giro, self.giro_cielo)

        self.tamano = Deslizador(0.01, 20, 0.01, 2)
        self.tamano.fijado.connect(lambda v: self._cambiar("tamano", v))
        self.etiqueta_tamano = QtWidgets.QLabel(t("f_tamano"))
        f.addRow(self.etiqueta_tamano, self.tamano)

        self.combo_ies = QtWidgets.QComboBox()
        self.combo_ies.activated.connect(lambda _: self._cambiar("ies", self.combo_ies.currentData()))
        self.etiqueta_ies = QtWidgets.QLabel(t("f_ies"))
        f.addRow(self.etiqueta_ies, self.combo_ies)

        self.muestras = QtWidgets.QSpinBox()
        self.muestras.setRange(1, 10)
        self.muestras.setKeyboardTracking(False)
        self.muestras.valueChanged.connect(lambda v: None if self._bloqueo else self._cambiar("muestras", v))
        self.visible_camara = QtWidgets.QCheckBox(t("f_visible_camara"))
        self.visible_camara.toggled.connect(lambda v: None if self._bloqueo else self._cambiar("visible_camara", v))
        f.addRow(t("f_muestras"), _fila(self.muestras, self.visible_camara))

        # Órbita (Estudio)
        self.caja_orbita = QtWidgets.QWidget()
        fo = estilo.formulario(self.caja_orbita)
        fo.setContentsMargins(0, 0, 0, 0)
        self.azimut = Deslizador(-180, 180, 1, 0, "°")
        self.azimut.fijado.connect(lambda v: self._mover_orbita(azimut=v))
        self.altura = Deslizador(-89, 89, 1, 0, "°")
        self.altura.fijado.connect(lambda v: self._mover_orbita(altura=v))
        self.distancia = Deslizador(0.05, 100, 0.05, 2)
        self.distancia.fijado.connect(lambda v: self._mover_orbita(distancia=v))
        fo.addRow(t("f_azimut"), self.azimut)
        fo.addRow(t("f_altura"), self.altura)
        fo.addRow(t("f_distancia"), self.distancia)
        f.addRow(self.caja_orbita)

        self.texto_gemelas = estilo.etiqueta("", "tenue")
        self.boton_separar = boton_herramienta(t("separar"), t("separar_ayuda"))
        self.boton_separar.clicked.connect(lambda: self._hacer(self.g.separar_gemelas, self.seleccion))
        self.fila_gemelas = _fila(self.texto_gemelas, self.boton_separar)
        f.addRow(self.fila_gemelas)
        self.linea_arnold = estilo.etiqueta("", "tenue", ajuste=True)
        self.linea_arnold.setTextInteractionFlags(Qt.TextSelectableByMouse)
        f.addRow(self.linea_arnold)
        capa.addWidget(self.ficha_cuerpo)
        capa.addStretch(1)
        return marco

    # --- Esquemas --------------------------------------------------------------------------------
    def _pestana_esquemas(self):
        w = QtWidgets.QWidget()
        capa = QtWidgets.QVBoxLayout(w)
        capa.setContentsMargins(8, 8, 8, 8)
        self.familia = QtWidgets.QComboBox()
        for fam in FAMILIAS:
            self.familia.addItem(t("familia_" + fam), fam)
        self.familia.currentIndexChanged.connect(lambda _: self._llenar_esquemas())
        self.reemplazar = QtWidgets.QCheckBox(t("reemplazar"))
        self.reemplazar.setChecked(True)
        self.reemplazar.setToolTip(t("reemplazar_ayuda"))
        capa.addWidget(_fila(self.familia, self.reemplazar))
        self.contenedor_esquemas = QtWidgets.QWidget()
        self.capa_esquemas = QtWidgets.QVBoxLayout(self.contenedor_esquemas)
        self.capa_esquemas.setContentsMargins(0, 0, 0, 0)
        self.capa_esquemas.setSpacing(6)
        capa.addWidget(_desplazable(self.contenedor_esquemas), 1)
        guardar = QtWidgets.QPushButton(t("guardar_esquema"))
        guardar.clicked.connect(self.guardar_esquema)
        abrir = QtWidgets.QPushButton(t("abrir_carpeta"))
        abrir.clicked.connect(lambda: self._abrir_carpeta(self.g.ajustes.esquemas))
        capa.addWidget(_fila(guardar, abrir))
        return w

    # --- Cielo -----------------------------------------------------------------------------------
    def _pestana_cielo(self):
        contenido = QtWidgets.QWidget()
        capa = QtWidgets.QVBoxLayout(contenido)
        capa.setContentsMargins(8, 8, 8, 8)
        capa.addWidget(_seccion(t("sec_hdri")))
        self.lista_hdri = QtWidgets.QListWidget()
        self.lista_hdri.setViewMode(QtWidgets.QListView.IconMode)
        self.lista_hdri.setIconSize(QtCore.QSize(112, 56))
        self.lista_hdri.setGridSize(QtCore.QSize(124, 82))
        self.lista_hdri.setResizeMode(QtWidgets.QListView.Adjust)
        self.lista_hdri.setMovement(QtWidgets.QListView.Static)
        self.lista_hdri.setMinimumHeight(150)
        self.lista_hdri.itemActivated.connect(self._hdri_elegido)
        self.lista_hdri.itemClicked.connect(self._hdri_elegido)
        capa.addWidget(self.lista_hdri)
        carpeta = QtWidgets.QPushButton(t("carpeta_hdri"))
        carpeta.clicked.connect(self._elegir_carpeta_hdri)
        self.boton_pack = QtWidgets.QPushButton(t("descargar_pack"))
        self.boton_pack.setToolTip(t("descargar_pack_ayuda"))
        self.boton_pack.clicked.connect(self.descargar_pack)
        capa.addWidget(_fila(carpeta, self.boton_pack))

        f = estilo.formulario()
        self.cielo_giro = Deslizador(0, 360, 1, 0, "°")
        self.cielo_giro.fijado.connect(lambda v: self._cambiar_cielo("rotacion_cielo", v))
        self.cielo_pasos = Deslizador(-6, 8, 0.1, 1)
        self.cielo_pasos.fijado.connect(lambda v: self._cambiar_cielo("pasos", v))
        self.cielo_visible = QtWidgets.QCheckBox(t("f_visible_camara"))
        self.cielo_visible.toggled.connect(
            lambda v: None if self._bloqueo else self._cambiar_cielo("visible_camara", v))
        f.addRow(t("f_giro"), self.cielo_giro)
        f.addRow(t("f_pasos"), self.cielo_pasos)
        f.addRow("", self.cielo_visible)
        capa.addLayout(f)
        sol_hdri = QtWidgets.QPushButton(t("sol_desde_hdri"))
        sol_hdri.setToolTip(t("sol_desde_hdri_ayuda"))
        sol_hdri.clicked.connect(self.sol_desde_hdri)
        fisico = QtWidgets.QPushButton(t("cielo_fisico"))
        fisico.setToolTip(t("cielo_fisico_ayuda"))
        fisico.clicked.connect(lambda: self._hacer(self.g.poner_cielo_fisico, aviso="hecho_cielo_fisico"))
        capa.addWidget(_fila(sol_hdri, fisico))

        # Sol físico
        self.caja_sol = QtWidgets.QWidget()
        cs = QtWidgets.QVBoxLayout(self.caja_sol)
        cs.setContentsMargins(0, 0, 0, 0)
        cs.addWidget(_seccion(t("sec_sol")))
        fs = estilo.formulario()
        self.ciudad = QtWidgets.QComboBox()
        for clave, nombre, *_ in solar.CIUDADES:
            self.ciudad.addItem(nombre, clave)
        self.ciudad.activated.connect(lambda _: self._poner_sol(ciudad=self.ciudad.currentData()))
        self.fecha = QtWidgets.QDateEdit()
        self.fecha.setCalendarPopup(True)
        self.fecha.setDisplayFormat("dd/MM/yyyy")
        self.fecha.editingFinished.connect(
            lambda: self._poner_sol(fecha=self.fecha.date().toString("yyyy-MM-dd")))
        self.hora = Deslizador(0, 24, 0.25, 2, " h")
        self.hora.fijado.connect(lambda v: self._poner_sol(hora=v))
        self.hora.vivo.connect(self._hora_viva)
        self.texto_salida = estilo.etiqueta("", "tenue")
        self.sol_pasos = Deslizador(-2, 10, 0.1, 1)
        self.sol_pasos.fijado.connect(lambda v: self._poner_sol(pasos=v))
        self.norte = Deslizador(-180, 180, 1, 0, "°")
        self.norte.setToolTip(t("norte_ayuda"))
        self.norte.fijado.connect(self._norte)
        self.practicas_auto = QtWidgets.QCheckBox(t("practicas_auto"))
        self.practicas_auto.toggled.connect(self._practicas_auto)
        fs.addRow(t("f_ciudad"), self.ciudad)
        fs.addRow(t("f_fecha"), self.fecha)
        fs.addRow(t("f_hora"), self.hora)
        fs.addRow("", self.texto_salida)
        fs.addRow(t("f_pasos"), self.sol_pasos)
        fs.addRow(t("f_norte"), self.norte)
        fs.addRow("", self.practicas_auto)
        cs.addLayout(fs)
        self.boton_sol = QtWidgets.QPushButton(t("activar_sol"))
        estilo.primario(self.boton_sol)
        self.boton_sol.clicked.connect(lambda: self._poner_sol())
        cs.addWidget(_fila(self.boton_sol))
        capa.addWidget(self.caja_sol)
        capa.addStretch(1)
        return _desplazable(contenido)

    # --- Enlaces ---------------------------------------------------------------------------------
    def _pestana_enlaces(self):
        w = QtWidgets.QWidget()
        capa = QtWidgets.QVBoxLayout(w)
        capa.setContentsMargins(8, 8, 8, 8)
        capa.addWidget(estilo.etiqueta(t("enlaces_ayuda"), "tenue", ajuste=True))
        usar_sel = QtWidgets.QPushButton(t("enlaces_seleccion"))
        usar_sel.clicked.connect(self._enlaces_de_seleccion)
        todos = QtWidgets.QPushButton(t("enlaces_todos"))
        todos.clicked.connect(self._enlaces_todos)
        capa.addWidget(_fila(usar_sel, todos))
        self.tabla = QtWidgets.QTableWidget()
        self.tabla.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.tabla.cellClicked.connect(self._clic_enlace)
        self.tabla.horizontalHeader().setDefaultSectionSize(34)
        capa.addWidget(self.tabla, 1)
        capa.addWidget(_seccion(t("sec_grupos")))
        self.texto_grupos = estilo.etiqueta("", "tenue", ajuste=True)
        capa.addWidget(self.texto_grupos)
        aovs = QtWidgets.QPushButton(t("crear_aovs"))
        aovs.setToolTip(t("crear_aovs_ayuda"))
        aovs.clicked.connect(self.crear_aovs)
        capa.addWidget(_fila(aovs))
        return w

    # --- Escenarios ------------------------------------------------------------------------------
    def _pestana_escenarios(self):
        w = QtWidgets.QWidget()
        capa = QtWidgets.QVBoxLayout(w)
        capa.setContentsMargins(8, 8, 8, 8)
        capa.addWidget(estilo.etiqueta(t("escenarios_ayuda"), "tenue", ajuste=True))
        self.lista_escenarios = QtWidgets.QListWidget()
        self.lista_escenarios.itemDoubleClicked.connect(lambda _: self.recuperar_escenario())
        capa.addWidget(self.lista_escenarios, 1)
        guardar = QtWidgets.QPushButton(t("guardar_escenario"))
        estilo.primario(guardar)
        guardar.clicked.connect(self.guardar_escenario)
        recuperar = QtWidgets.QPushButton(t("recuperar"))
        recuperar.clicked.connect(self.recuperar_escenario)
        self.boton_comparar = QtWidgets.QPushButton(t("comparar"))
        self.boton_comparar.setToolTip(t("comparar_ayuda"))
        self.boton_comparar.pressed.connect(self._comparar_inicio)
        self.boton_comparar.released.connect(self._comparar_fin)
        borrar = QtWidgets.QPushButton(t("borrar"))
        estilo.rol(borrar, "peligro")
        borrar.clicked.connect(self.borrar_escenario)
        capa.addWidget(_fila(guardar, recuperar, self.boton_comparar, None, borrar))
        return w

    # --- Comprobar -------------------------------------------------------------------------------
    def _pestana_comprobar(self):
        w = QtWidgets.QWidget()
        capa = QtWidgets.QVBoxLayout(w)
        capa.setContentsMargins(8, 8, 8, 8)
        self.resumen_avisos = estilo.etiqueta("", None, ajuste=True)
        otra = QtWidgets.QPushButton(t("comprobar_otra_vez"))
        otra.clicked.connect(self._llenar_avisos)
        capa.addWidget(_fila(self.resumen_avisos, None, otra))
        self.contenedor_avisos = QtWidgets.QWidget()
        self.capa_avisos = QtWidgets.QVBoxLayout(self.contenedor_avisos)
        self.capa_avisos.setContentsMargins(0, 0, 0, 0)
        self.capa_avisos.setSpacing(6)
        capa.addWidget(_desplazable(self.contenedor_avisos), 1)
        capa.addWidget(estilo.etiqueta(t("comprobar_renderdesk"), "tenue", ajuste=True))
        return w

    # =========================================================================================
    # refresco
    # =========================================================================================
    def _al_cambiar_gestor(self):
        # Nunca se rehace la lista dentro de una señal suya (borraría el elemento que la emite):
        # se deja para cuando Qt termine lo que está haciendo, y varios avisos seguidos son uno.
        if not self._bloqueo and not self._pendiente:
            self._pendiente = True
            QtCore.QTimer.singleShot(0, self._refresco_pendiente)

    def _refresco_pendiente(self):
        self._pendiente = False
        self.refrescar(leer=False)

    def refrescar(self, leer=True):
        """Vuelve a leer las luces y lo pinta todo. ``leer=False`` si el gestor ya está al día."""
        if leer:
            self.g.refrescar()
        nodos = {l.nodo for l in self.g.luces}
        self.seleccion = [n for n in self.seleccion if n in nodos]
        self._poner_modo_en_cabecera()
        self._llenar_lista()
        self._llenar_ficha()
        self._llenar_orbita()
        self._refrescar_pestana()

    def _refrescar_pestana(self):
        i = self.pestanas.currentIndex()
        if i == 1:
            self._llenar_esquemas()
        elif i == 2:
            self._llenar_cielo()
        elif i == 3:
            self._llenar_enlaces()
        elif i == 4:
            self._llenar_escenarios()
        elif i == 5:
            self._llenar_avisos()

    def modo(self):
        return self.g.modo()

    def _poner_modo_en_cabecera(self):
        modo = self.modo()
        self._bloqueo = True
        try:
            self.boton_estudio.setChecked(modo == "estudio")
            self.boton_escena.setChecked(modo == "escena")
            clave = self.g.ajustes["agrupar_" + modo]
            i = self.combo_agrupar.findData(clave)
            self.combo_agrupar.setCurrentIndex(max(0, i))
        finally:
            self._bloqueo = False
        escena = modo == "escena"
        self.fila_escena.setVisible(escena)
        self.caja_sol.setVisible(escena)
        self.etiqueta_zona.setVisible(escena)
        self.combo_zona.setVisible(escena)
        if escena:
            self._asegurar_vista_maya()
            self.pila_vista.setCurrentWidget(self.hueco_vista)
        else:
            self.pila_vista.setCurrentWidget(self.orbita)
        familia = "estudio" if not escena else "interior"
        if self.familia.currentData() in ("estudio",) and escena or (not escena and self.familia.currentData()
                                                                    in ("interior", "exterior")):
            self.familia.setCurrentIndex(self.familia.findData(familia))

    def _asegurar_vista_maya(self):
        if self.vista_maya is not None:
            return
        vista = self.visor.crear_vista(self.hueco_vista)
        if vista is not None:
            self.vista_maya = vista
            self.sin_vista.hide()
            self.hueco_vista.layout().addWidget(vista)

    def poner_modo(self, modo):
        if self._bloqueo:
            return
        self.g.poner_modo(modo)
        self.refrescar(leer=False)

    def _agrupar_cambiado(self, _):
        if self._bloqueo:
            return
        self.g.ajustes["agrupar_" + self.modo()] = self.combo_agrupar.currentData()
        self._llenar_lista()

    # --- lista -----------------------------------------------------------------------------------
    def enterEvent(self, evento):
        # Lo que se cambie en el Attribute Editor no avisa: al volver al panel se vuelve a leer.
        ahora = datetime.datetime.now()
        if not self._bloqueo and (ahora - self._ultima_lectura).total_seconds() > 1.5:
            self.refrescar()
        QtWidgets.QWidget.enterEvent(self, evento)

    def _llenar_lista(self):
        self._ultima_lectura = datetime.datetime.now()
        desplazamiento = self.lista.verticalScrollBar().value()
        self._bloqueo = True
        try:
            self.lista.clear()
            por = self.combo_agrupar.currentData() or "papel"
            luces = self.g.luces
            for grupo, miembros in agrupar(luces, por):
                if por == "papel":
                    titulo = _texto_papel(grupo)
                elif por == "zona":
                    titulo = nombre_visible(grupo) if grupo else ZONA_GENERAL
                elif por == "tipo":
                    titulo = t(grupo)
                else:
                    titulo = grupo or t("sin_grupo")
                cabeza = QtWidgets.QTreeWidgetItem(["{}  ({})".format(titulo, len(miembros)), "", ""])
                cabeza.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                encendidas = sum(1 for l in miembros if l.encendida)
                cabeza.setCheckState(0, Qt.Checked if encendidas == len(miembros) else
                                     (Qt.Unchecked if not encendidas else Qt.PartiallyChecked))
                fuente = cabeza.font(0)
                fuente.setBold(True)
                cabeza.setFont(0, fuente)
                cabeza.setData(0, Qt.UserRole, [l.nodo for l in miembros])
                self.lista.addTopLevelItem(cabeza)
                for l in miembros:
                    hijo = QtWidgets.QTreeWidgetItem([l.nombre, "S" if l.solo else "·",
                                                      "{:.1f}".format(l.pasos).replace(".", ",")])
                    hijo.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
                    hijo.setCheckState(0, Qt.Checked if l.encendida else Qt.Unchecked)
                    hijo.setData(0, Qt.UserRole, l.nodo)
                    hijo.setIcon(0, icono_color(color_de_luz(l), 12, not activa(l, luces)))
                    hijo.setToolTip(0, "{} · {}".format(t(l.texto_tipo), l.nodo))
                    hijo.setToolTip(1, t("solo_ayuda"))
                    hijo.setTextAlignment(1, Qt.AlignCenter)
                    hijo.setTextAlignment(2, Qt.AlignRight | Qt.AlignVCenter)
                    if l.solo:
                        hijo.setForeground(1, QtGui.QBrush(QtGui.QColor(AMBAR)))
                    if not activa(l, luces):
                        for c in range(3):
                            hijo.setForeground(c, QtGui.QBrush(QtGui.QColor("#7a7a7a")))
                    cabeza.addChild(hijo)
                    if l.nodo in self.seleccion:
                        hijo.setSelected(True)
                cabeza.setExpanded(True)
            self.lista.verticalScrollBar().setValue(desplazamiento)
        finally:
            self._bloqueo = False

    def _items_luz(self):
        for i in range(self.lista.topLevelItemCount()):
            cabeza = self.lista.topLevelItem(i)
            for j in range(cabeza.childCount()):
                yield cabeza.child(j)

    def _seleccion_lista(self):
        if self._bloqueo:
            return
        self.seleccion = [it.data(0, Qt.UserRole) for it in self.lista.selectedItems()
                          if isinstance(it.data(0, Qt.UserRole), str)]
        try:
            self.g.s.seleccionar(self.seleccion)
        except Exception:
            pass
        self._llenar_ficha()
        self._llenar_orbita()

    def elegir(self, nodos, en_maya=True):
        """Elige luces en la lista (y en Maya)."""
        self.seleccion = [n for n in nodos if self.g.existe(n)]
        self._bloqueo = True
        try:
            for it in self._items_luz():
                it.setSelected(it.data(0, Qt.UserRole) in self.seleccion)
        finally:
            self._bloqueo = False
        if en_maya:
            try:
                self.g.s.seleccionar(self.seleccion)
            except Exception:
                pass
        self._llenar_ficha()
        self._llenar_orbita()

    def sincronizar_desde_maya(self):
        """Cuando cambia la selección en Maya: elige en la lista las luces seleccionadas."""
        try:
            sel = {n.split("|")[-1] for n in self.g.s.seleccion()}
        except Exception:
            return
        nodos = [l.nodo for l in self.g.luces if l.nodo.split("|")[-1] in sel]
        if set(nodos) != set(self.seleccion):
            self.elegir(nodos, en_maya=False)

    def _casilla_lista(self, item, columna):
        if self._bloqueo or columna != 0:
            return
        dato = item.data(0, Qt.UserRole)
        if isinstance(dato, list):
            self._hacer(self.g.encender, dato, item.checkState(0) == Qt.Checked)
        else:
            self._hacer(self.g.encender, [dato], item.checkState(0) == Qt.Checked)

    def _clic_lista(self, item, columna):
        dato = item.data(0, Qt.UserRole)
        if columna == 1 and isinstance(dato, str):
            self._hacer(self.g.solo, [dato])

    def _menu_lista(self, punto):
        item = self.lista.itemAt(punto)
        if item is None or not isinstance(item.data(0, Qt.UserRole), str):
            return
        nodos = self.seleccion or [item.data(0, Qt.UserRole)]
        menu = QtWidgets.QMenu(self)
        menu.addAction(t("solo"), lambda: self._hacer(self.g.solo, nodos))
        menu.addAction(t("quitar_solos"), lambda: self._hacer(self.g.quitar_solos))
        menu.addAction(t("encender_grupo"), lambda: self._hacer(self.g.encender_grupo, nodos))
        menu.addSeparator()
        menu.addAction(t("duplicar"), self.duplicar)
        menu.addAction(t("borrar"), self.borrar)
        ejecutar_menu = getattr(menu, "exec", None) or menu.exec_
        ejecutar_menu(self.lista.viewport().mapToGlobal(punto))

    # --- ficha -----------------------------------------------------------------------------------
    def _llenar_ficha(self):
        luces = [self.g.luz(n) for n in self.seleccion if self.g.existe(n)]
        self.ficha_vacia.setVisible(not luces)
        self.ficha_cuerpo.setVisible(bool(luces))
        if not luces:
            return
        l = luces[0]
        varias = len(luces) > 1
        self._bloqueo = True
        try:
            self.campo_nombre.setText(t("varias_luces", n=len(luces)) if varias else l.nombre)
            self.campo_nombre.setEnabled(not varias)
            self.chip_tipo.setText(t(l.texto_tipo))
            self.combo_papel.setCurrentIndex(max(0, self.combo_papel.findData(l.papel)))
            self.combo_zona.clear()
            self.combo_zona.addItem(t("zona_auto", zona=nombre_visible(l.zona.lstrip("=")) if l.zona else
                                      ZONA_GENERAL), "")
            for z in self.g.zonas():
                self.combo_zona.addItem(z.nombre, z.nombre)
            if l.zona.startswith("="):
                self.combo_zona.setCurrentIndex(max(0, self.combo_zona.findData(l.zona[1:])))
            self.combo_grupo.clear()
            self.combo_grupo.addItem("", "")
            for grupo in self.g.grupos():
                self.combo_grupo.addItem(grupo, grupo)
            self.combo_grupo.setEditText(l.grupo)
            self.potencia.poner(l.pasos if l.pasos != float("-inf") else unidades.PASOS_MIN)
            con_kelvin = l.tiene_temperatura
            self.etiqueta_kelvin.setVisible(con_kelvin)
            self.fila_kelvin.setVisible(con_kelvin)
            self.kelvin.poner(l.kelvin)
            self.texto_kelvin.setText("{} K".format(int(l.kelvin)))
            es_cielo = l.es_cielo
            self.etiqueta_giro.setVisible(es_cielo)
            self.giro_cielo.setVisible(es_cielo)
            self.giro_cielo.poner(l.rotacion_cielo % 360.0)
            tipo_tam = l.tipo_tamano
            self.etiqueta_tamano.setVisible(bool(tipo_tam))
            self.tamano.setVisible(bool(tipo_tam))
            if tipo_tam:
                self.etiqueta_tamano.setText(t("f_tamano_" + tipo_tam))
                self.tamano.poner(l.tamano)
            es_ies = l.tipo == "fotometrica"
            self.etiqueta_ies.setVisible(es_ies)
            self.combo_ies.setVisible(es_ies)
            if es_ies:
                self._llenar_ies(l.ies)
            self.muestras.setValue(int(l.muestras))
            self.visible_camara.setChecked(bool(l.visible_camara))
            self.visible_camara.setVisible(l.tipo in ("area", "cielo", "malla", "fotometrica", "punto", "foco"))
            orbita = None if varias or self.modo() != "estudio" else self.g.orbita(l.nodo)
            self.caja_orbita.setVisible(orbita is not None)
            if orbita is not None:
                self.azimut.poner(orbita[0])
                self.altura.poner(orbita[1])
                self.distancia.poner(orbita[2])
            gemelas = [x for x in self.g.luces if l.gemela and x.gemela == l.gemela]
            self.fila_gemelas.setVisible(len(gemelas) > 1)
            self.texto_gemelas.setText(t("gemelas", n=len(gemelas)))
            ver = bool(self.g.ajustes["ver_arnold"])
            self.linea_arnold.setVisible(ver)
            if ver:
                self.linea_arnold.setText(self._texto_arnold(l))
        finally:
            self._bloqueo = False

    def _texto_arnold(self, l):
        partes = [t("arnold_potencia", veces=_numero(unidades.multiplicador(l.pasos)))]
        if l.tiene_temperatura:
            partes.append("{} K".format(int(l.kelvin)))
        if l.tipo in TIPOS:
            partes.append(TIPOS[l.tipo][1])
        if l.grupo:
            partes.append("AOV RGBA_" + l.grupo)
        return "Arnold · " + " · ".join(partes)

    def _llenar_ies(self, actual):
        self.combo_ies.clear()
        carpetas = [self.g.ajustes.ies_incluidos, self.g.ajustes["carpeta_ies"]]
        for nombre, ruta in ies.listar(carpetas):
            clave = ies.clave_de(ruta)
            self.combo_ies.addItem(t("ies_" + clave) if clave else nombre, ruta)
        i = self.combo_ies.findData(actual)
        if i < 0 and actual:
            self.combo_ies.addItem(os.path.basename(actual), actual)
            i = self.combo_ies.count() - 1
        self.combo_ies.setCurrentIndex(max(0, i))

    def _cambiar(self, campo, valor, relativo=False):
        if self._bloqueo or not self.seleccion:
            return
        self._hacer(self.g.cambiar, self.seleccion, campo, valor, relativo=relativo)

    def _renombrar(self):
        if self._bloqueo or len(self.seleccion) != 1:
            return
        nuevo = self.campo_nombre.text().strip()
        if not nuevo or nuevo == self.g.luz(self.seleccion[0]).nombre:
            return
        nodo = self._hacer(self.g.renombrar, self.seleccion[0], nuevo)
        if nodo:
            self.seleccion = [nodo]
            self.refrescar(leer=False)

    def _zona_elegida(self, _):
        if self._bloqueo or not self.seleccion:
            return
        zona = self.combo_zona.currentData()
        self._hacer(self.g.fijar_zona, self.seleccion, zona or None)

    def _grupo_escrito(self):
        if self._bloqueo or not self.seleccion:
            return
        texto = self.combo_grupo.currentText().strip()
        if all(self.g.luz(n).grupo == texto for n in self.seleccion if self.g.existe(n)):
            return
        self._hacer(self.g.poner_grupo, self.seleccion, texto)

    def _mover_orbita(self, **valores):
        if self._bloqueo or len(self.seleccion) != 1:
            return
        self._hacer(self.g.mover_orbita, self.seleccion[0], **valores)

    # --- órbita ----------------------------------------------------------------------------------
    def _llenar_orbita(self):
        if self.modo() != "estudio":
            return
        datos = []
        caja = self.g.objetivo_y_tamano()
        tam = max(1e-3, geo.tamano(caja))
        for l in self.g.luces:
            o = None
            try:
                o = self.g.orbita(l.nodo)
            except Exception:
                pass
            if o is None:
                continue
            az, alt, dist = o
            datos.append((l.nodo, l.nombre, az, alt, dist / tam, color_de_luz(l), activa(l, self.g.luces)))
        self.orbita.poner_luces(datos, self.seleccion)

    def _orbita_movida(self, nodo, azimut, distancia_relativa):
        caja = self.g.objetivo_y_tamano()
        tam = max(1e-3, geo.tamano(caja))
        self._hacer(self.g.mover_orbita, nodo, azimut=azimut, distancia=distancia_relativa * tam)

    def _orbita_altura(self, nodo, delta):
        o = self.g.orbita(nodo)
        if o is not None:
            self._hacer(self.g.mover_orbita, nodo, altura=o[1] + delta)

    # --- acciones de luces ----------------------------------------------------------------------
    def nueva_luz(self, tipo):
        if tipo == "cielo":
            nodo = self._hacer(self.g.asegurar_cielo, "hdri", self.g.hdri_del_pack("studio_small_09"))
        else:
            nodo = self._hacer(self.g.crear_en_orbita, tipo)
        if nodo:
            self._tras_crear([nodo])

    def duplicar(self):
        if len(self.seleccion) != 1:
            self._decir(t("elige_una"))
            return
        nodo = self._hacer(self.g.duplicar, self.seleccion[0])
        if nodo:
            self._tras_crear([nodo])

    def _tras_crear(self, nodos):
        """Elige las luces recién creadas (en la lista y en Maya)."""
        self.g.refrescar()
        self.seleccion = [n for n in nodos if self.g.existe(n)]
        self.refrescar(leer=False)
        try:
            self.g.s.seleccionar(self.seleccion)
        except Exception:
            pass

    def borrar(self):
        if not self.seleccion:
            return
        nodos = list(self.seleccion)
        self.seleccion = []
        self._hacer(self.g.borrar, nodos)

    def apuntar(self, modo, marcado=True):
        for m, b in self.botones_apuntar.items():
            if m != modo:
                b.setChecked(False)
        if not marcado:
            self.visor.cancelar()
            return
        if len(self.seleccion) != 1:
            self.botones_apuntar[modo].setChecked(False)
            self._decir(t("elige_una"))
            return
        nodo = self.seleccion[0]

        def al_clic(punto, normal, camara):
            self._hacer(self.g.apuntar, nodo, modo, punto, normal, camara)

        if not self.visor.pedir_clic(t("clic_apuntar_" + modo), al_clic, repetir=True):
            self.botones_apuntar[modo].setChecked(False)
            self._decir(t("sin_visor"))
        else:
            self._decir(t("clic_apuntar_" + modo))

    def apuntar_terminado(self):
        """El visor avisa cuando se sale de la herramienta de clic (Esc, otra herramienta…)."""
        for b in self.botones_apuntar.values():
            b.setChecked(False)

    def colocar(self, tipo, perfil):
        def al_clic(punto, normal, camara):
            nodo = self._hacer(self.g.colocar_en_superficie, punto, normal, tipo, None, perfil or "downlight")
            if nodo:
                self._tras_crear([nodo])
        if not self.visor.pedir_clic(t("clic_colocar"), al_clic, repetir=True):
            self._decir(t("sin_visor"))
        else:
            self._decir(t("clic_colocar"))

    def repetir(self):
        if len(self.seleccion) != 1:
            self._decir(t("elige_una"))
            return
        nodo = self.seleccion[0]
        cantidad, ok = QtWidgets.QInputDialog.getInt(self.padre_dialogos, "LightManager", t("repetir_cuantas"),
                                                     int(self.g.ajustes["repetir_cantidad"]), 1, 50)
        if not ok:
            return
        self.g.ajustes["repetir_cantidad"] = cantidad

        def al_clic(punto, normal, camara):
            l = self.g.luz(nodo)
            fin = (punto[0], l.posicion[1], punto[2])
            self._hacer(self.g.repetir, nodo, fin, cantidad, aviso="hecho_repetir")

        if not self.visor.pedir_clic(t("clic_repetir"), al_clic):
            self._decir(t("sin_visor"))
        else:
            self._decir(t("clic_repetir"))

    # --- zonas -------------------------------------------------------------------------------------
    def _llenar_menu_zonas(self):
        m = self.menu_zonas
        m.clear()
        m.addAction(t("zona_seleccion"), self.zona_desde_seleccion)
        m.addAction(t("zona_rectangulo"), self.zona_rectangulo)
        m.addAction(t("zona_outliner"), lambda: self._hacer(self.g.zonas_desde_outliner, aviso="hecho_zonas"))
        m.addAction(t("zona_reasignar"), lambda: self._hacer(self.g.reasignar_zonas, aviso="hecho_reasignar"))
        zonas = self.g.zonas()
        if zonas:
            m.addSeparator()
            borrar = m.addMenu(t("zona_borrar"))
            for z in zonas:
                borrar.addAction(z.nombre, lambda n=z.nodo: self._hacer(self.g.borrar_zona, n))

    def _pedir_nombre(self, pregunta, defecto=""):
        texto, ok = QtWidgets.QInputDialog.getText(self.padre_dialogos, "LightManager", pregunta,
                                                   QtWidgets.QLineEdit.Normal, defecto)
        texto = (texto or "").strip()
        return texto if ok and texto else None

    def zona_desde_seleccion(self):
        nombre = self._pedir_nombre(t("zona_nombre"))
        if nombre:
            self._hacer(self.g.zona_desde_seleccion, nombre, aviso="hecho_zona")

    def zona_rectangulo(self):
        def al_soltar(caja):
            nombre = self._pedir_nombre(t("zona_nombre"))
            if nombre:
                self._hacer(self.g.crear_zona, nombre, caja, aviso="hecho_zona")
        if not self.visor.pedir_rectangulo(t("clic_rectangulo"), al_soltar):
            self._decir(t("sin_visor"))
        else:
            self._decir(t("clic_rectangulo"))

    # --- esquemas ----------------------------------------------------------------------------------
    def _llenar_esquemas(self):
        while self.capa_esquemas.count():
            item = self.capa_esquemas.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        familia = self.familia.currentData()
        lista = esq.por_familia(self.g.esquemas(), familia)
        if not lista:
            self.capa_esquemas.addWidget(estilo.etiqueta(t("sin_esquemas_" + familia), "tenue", ajuste=True))
        for e in lista:
            marco, capa = estilo.tarjeta(8, 4)
            titulo = estilo.etiqueta(e.nombre)
            titulo.setStyleSheet("font-weight: 600;")
            if e.es_estudio:
                cuenta = estilo.etiqueta(t("n_luces", n=len(e.luces)), "tenue")
            else:
                cuenta = estilo.etiqueta(t("esquema_escena"), "tenue")
            aplicar = QtWidgets.QPushButton(t("aplicar"))
            estilo.primario(aplicar)
            aplicar.clicked.connect(lambda _=False, x=e: self.aplicar_esquema(x))
            capa.addWidget(_fila(titulo, cuenta, None, aplicar))
            if e.descripcion:
                capa.addWidget(estilo.etiqueta(e.descripcion, "tenue", ajuste=True))
            self.capa_esquemas.addWidget(marco)
        self.capa_esquemas.addStretch(1)

    def aplicar_esquema(self, esquema):
        hechas = self._hacer(self.g.aplicar_esquema, esquema, self.reemplazar.isChecked())
        if hechas is not None:
            self._decir(t("hecho_esquema", nombre=esquema.nombre))
            if esquema.es_estudio and hechas:
                self._tras_crear(hechas[:1])

    def guardar_esquema(self):
        if not self.g.luces:
            self._decir(t("sin_luces"))
            return
        nombre = self._pedir_nombre(t("esquema_nombre"))
        if nombre:
            ruta = self._hacer(self.g.guardar_como_esquema, nombre)
            if ruta:
                self.familia.setCurrentIndex(self.familia.findData("mios"))
                self._decir(t("hecho_guardar_esquema", nombre=nombre))

    # --- cielo -----------------------------------------------------------------------------------
    def _carpetas_hdri(self):
        return [self.g.ajustes.hdri]

    def _llenar_cielo(self):
        c = self.g.cielo()
        actual = c.hdri if c else ""
        self.lista_hdri.clear()
        self._cola_miniaturas = []
        miniaturas = self.g.ajustes.miniaturas
        for nombre, ruta in biblioteca.listar(self._carpetas_hdri()):
            item = QtWidgets.QListWidgetItem(nombre.replace("_", " "))
            item.setData(Qt.UserRole, ruta)
            item.setToolTip(ruta)
            m = biblioteca.ruta_miniatura(miniaturas, ruta)
            if biblioteca.miniatura_al_dia(miniaturas, ruta):
                item.setIcon(QtGui.QIcon(m))
            else:
                self._cola_miniaturas.append((item, ruta, m))
            self.lista_hdri.addItem(item)
            if actual and os.path.normcase(actual) == os.path.normcase(ruta):
                item.setSelected(True)
        if self._cola_miniaturas:
            self.reloj_miniaturas.start()
        self.boton_pack.setVisible(not all(biblioteca.buscar(self._carpetas_hdri(), n)
                                           for n, _ in biblioteca.PACK_INICIAL))
        self._bloqueo = True
        try:
            self.cielo_giro.setEnabled(c is not None)
            self.cielo_pasos.setEnabled(c is not None)
            self.cielo_visible.setEnabled(c is not None)
            if c is not None:
                self.cielo_giro.poner(c.rotacion_cielo % 360.0)
                self.cielo_pasos.poner(c.pasos)
                self.cielo_visible.setChecked(bool(c.visible_camara))
            e = self.g.estado_sol()
            i = self.ciudad.findData(e.get("ciudad"))
            self.ciudad.setCurrentIndex(max(0, i))
            fecha = self.g._fecha(e)
            self.fecha.setDate(QtCore.QDate(fecha.year, fecha.month, fecha.day))
            self.hora.poner(float(e.get("hora", 13.0)))
            self.sol_pasos.poner(float(e.get("pasos", 3.0)))
            self.norte.poner(float(self.g.ajustes["norte"]))
            self.practicas_auto.setChecked(bool(self.g.ajustes["practicas_auto"]))
            self.boton_sol.setVisible(not e.get("activo"))
            self._texto_sol(e)
        finally:
            self._bloqueo = False

    def _texto_sol(self, estado, hora=None):
        try:
            fecha = self.g._fecha(estado)
            salida, puesta = solar.salida_y_puesta(estado["ciudad"], fecha)
            hora = float(estado.get("hora", 13.0)) if hora is None else hora
            az, alt = solar.posicion_en(estado["ciudad"], fecha, hora)
        except Exception:
            self.texto_salida.setText("")
            return
        self.texto_salida.setText(t("sol_salida", salida=solar.texto_hora(salida) if salida is not None else "—",
                                    puesta=solar.texto_hora(puesta) if puesta is not None else "—",
                                    altura=int(round(alt))))

    def _hora_viva(self, hora):
        self._texto_sol(self.g.estado_sol(), hora)

    def _siguiente_miniatura(self):
        if not self._cola_miniaturas:
            self.reloj_miniaturas.stop()
            return
        item, ruta, destino = self._cola_miniaturas.pop(0)
        try:
            if self.g.s.miniatura(ruta, destino):
                item.setIcon(QtGui.QIcon(destino))
        except Exception:
            pass

    def _hdri_elegido(self, item):
        ruta = item.data(Qt.UserRole)
        c = self.g.cielo()
        if c is not None and c.hdri == ruta and not c.cielo_fisico:
            return
        self._hacer(self.g.poner_hdri, ruta, aviso="hecho_hdri")

    def _cambiar_cielo(self, campo, valor):
        c = self.g.cielo()
        if self._bloqueo or c is None:
            return
        self._hacer(self.g.cambiar, [c.nodo], campo, valor)

    def _elegir_carpeta_hdri(self):
        carpeta = QtWidgets.QFileDialog.getExistingDirectory(self.padre_dialogos, t("carpeta_hdri"),
                                                             self.g.ajustes.hdri)
        if carpeta:
            self.g.ajustes["carpeta_hdri"] = carpeta
            self._llenar_cielo()

    def descargar_pack(self):
        carpeta = self.g.ajustes.hdri
        progreso = QtWidgets.QProgressDialog(t("descargando"), t("cancelar"), 0, len(biblioteca.PACK_INICIAL),
                                             self.padre_dialogos)
        progreso.setWindowTitle("LightManager")
        progreso.setMinimumDuration(0)

        def avance(i, total, nombre):
            progreso.setValue(i)
            progreso.setLabelText(t("descargando_uno", nombre=nombre, i=i + 1, total=total))
            QtWidgets.QApplication.processEvents()
            return not progreso.wasCanceled()

        hechos, fallidos = biblioteca.descargar_pack(carpeta, avance)
        progreso.setValue(len(biblioteca.PACK_INICIAL))
        progreso.close()
        if fallidos:
            QtWidgets.QMessageBox.warning(self.padre_dialogos, "LightManager",
                                          t("descarga_fallos", n=len(fallidos), web="https://polyhaven.com/hdris",
                                            carpeta=carpeta, error=fallidos[0][1]))
        else:
            self._decir(t("descarga_hecha", n=len(hechos)))
        self._llenar_cielo()

    def sol_desde_hdri(self):
        c = self.g.cielo()
        if c is None or not c.hdri:
            self._decir(t("err_sin_cielo"))
            return
        destino = biblioteca.ruta_miniatura(self.g.ajustes.miniaturas, c.hdri)
        if not biblioteca.miniatura_al_dia(self.g.ajustes.miniaturas, c.hdri):
            self.g.s.miniatura(c.hdri, destino, 256)
        datos = luminancias(destino)
        sol = biblioteca.buscar_sol(*datos) if datos else None
        if sol is None:
            self._decir(t("sol_hdri_no"))
            return
        az, alt, fuerza = sol
        if fuerza < 2.0:
            self._decir(t("sol_hdri_debil"))
            return
        nodo = self._hacer(self.g.sol_desde_hdri, az, alt, 5600 if alt > 20 else 4000)
        if nodo:
            self._decir(t("hecho_sol_hdri", altura=int(round(alt))))

    def _poner_sol(self, **cambios):
        if self._bloqueo:
            return
        self._hacer(self.g.poner_sol, **cambios)

    def _norte(self, valor):
        if self._bloqueo:
            return
        self.g.ajustes["norte"] = float(valor)
        self._hacer(self.g.aplicar_sol)
        self.g.refrescar()
        self.refrescar(leer=False)

    def _practicas_auto(self, valor):
        if not self._bloqueo:
            self.g.ajustes["practicas_auto"] = bool(valor)

    # --- enlaces ---------------------------------------------------------------------------------
    def _enlaces_de_seleccion(self):
        try:
            objetos = self.g.s.objetos_seleccionados()
        except Exception:
            objetos = []
        if not objetos:
            self._decir(t("err_sin_objetos"))
            return
        self._objetos_enlace = [n for n, _ in objetos]
        self._llenar_enlaces()

    def _enlaces_todos(self):
        self._objetos_enlace = None
        self._llenar_enlaces()

    def _llenar_enlaces(self):
        luces = [l for l in self.g.luces if l.emite]
        if self.seleccion:
            luces = [l for l in luces if l.nodo in self.seleccion] or luces
        enlazables = self.g.objetos_enlazables()
        if self._objetos_enlace is not None:
            enlazables = [o for o in enlazables if o[0] in self._objetos_enlace]
        enlazables = enlazables[:MAX_OBJETOS_ENLACE]
        self.tabla.clear()
        self.tabla.setRowCount(len(luces))
        self.tabla.setColumnCount(len(enlazables))
        self.tabla.setVerticalHeaderLabels([l.nombre for l in luces])
        self.tabla.setHorizontalHeaderLabels([n for _, n in enlazables])
        for i, l in enumerate(luces):
            for j, (obj, _) in enumerate(enlazables):
                estado = self.g.estado_enlace(l.nodo, obj)
                celda = QtWidgets.QTableWidgetItem(ENLACE_TEXTO[estado])
                celda.setTextAlignment(Qt.AlignCenter)
                celda.setData(Qt.UserRole, (l.nodo, obj))
                celda.setToolTip(t("enlace_{}".format(estado)))
                self.tabla.setItem(i, j, celda)
        grupos = self.g.grupos()
        self.texto_grupos.setText(t("grupos_hay", grupos=", ".join(grupos)) if grupos else t("grupos_no"))

    def _clic_enlace(self, fila, columna):
        celda = self.tabla.item(fila, columna)
        if celda is None:
            return
        luz, obj = celda.data(Qt.UserRole)
        nuevo = self._hacer(self.g.siguiente_estado_enlace, luz, obj)
        if nuevo is not None:
            celda.setText(ENLACE_TEXTO[nuevo])
            celda.setToolTip(t("enlace_{}".format(nuevo)))

    def crear_aovs(self):
        nombres = self._hacer(self.g.crear_aovs)
        if nombres is not None:
            self._decir(t("hecho_aovs", aovs=", ".join(nombres)) if nombres else t("grupos_no"))

    # --- escenarios ------------------------------------------------------------------------------
    def _llenar_escenarios(self):
        self.lista_escenarios.clear()
        for e in self.g.escenarios():
            texto = e.get("nombre", "")
            if e.get("fecha"):
                texto += "   ·   " + e["fecha"]
            item = QtWidgets.QListWidgetItem(texto)
            item.setData(Qt.UserRole, e.get("nombre"))
            item.setToolTip(t("escenario_luces", n=len(e.get("luces", {}))))
            self.lista_escenarios.addItem(item)

    def _escenario_elegido(self):
        item = self.lista_escenarios.currentItem()
        return item.data(Qt.UserRole) if item is not None else None

    def guardar_escenario(self):
        nombre = self._pedir_nombre(t("escenario_nombre"), t("escenario_defecto", n=len(self.g.escenarios()) + 1))
        if nombre:
            self._hacer(self.g.guardar_escenario, nombre, aviso="hecho_escenario")
            self._llenar_escenarios()

    def recuperar_escenario(self):
        nombre = self._escenario_elegido()
        if nombre:
            self._hacer(self.g.recuperar_escenario, nombre, aviso="hecho_recuperar")

    def borrar_escenario(self):
        nombre = self._escenario_elegido()
        if nombre:
            self._hacer(self.g.borrar_escenario, nombre)
            self._llenar_escenarios()

    def _comparar_inicio(self):
        nombre = self._escenario_elegido()
        if nombre:
            self._bloqueo = True
            try:
                self._hacer(self.g.comparar_inicio, nombre)
            finally:
                self._bloqueo = False
            self._decir(t("comparando", nombre=nombre))

    def _comparar_fin(self):
        self._bloqueo = True
        try:
            self._hacer(self.g.comparar_fin)
        finally:
            self._bloqueo = False
        self._decir("")
        self.refrescar(leer=False)

    # --- comprobar -------------------------------------------------------------------------------
    def _llenar_avisos(self):
        while self.capa_avisos.count():
            item = self.capa_avisos.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        avisos = self.g.comprobar()
        pendientes = [a for a in avisos if a.nivel != "ok"]
        self.resumen_avisos.setText(t("avisos_resumen", n=len(pendientes)) if pendientes else t("avisos_ninguno"))
        for a in sorted(avisos, key=lambda x: {"mal": 0, "aviso": 1, "ok": 2}[x.nivel]):
            marco, capa = estilo.tarjeta(8, 2)
            titulo = estilo.etiqueta(t(a.texto, **a.valores), ajuste=True)
            if a.nivel != "ok":
                titulo.setStyleSheet("font-weight: 600;")
            capa.addWidget(_fila(estilo.punto(NIVEL_COLOR[a.nivel], 10), titulo, None))
            if a.nivel != "ok":
                capa.addWidget(estilo.etiqueta(t(a.detalle, **a.valores), "tenue", ajuste=True))
                botones = []
                if a.arreglo:
                    b = QtWidgets.QPushButton(t("arr_" + a.arreglo))
                    estilo.primario(b)
                    b.clicked.connect(lambda _=False, x=a: self.arreglar(x))
                    botones.append(b)
                if a.nodos:
                    s = QtWidgets.QPushButton(t("seleccionar"))
                    s.clicked.connect(lambda _=False, x=a: self.elegir(x.nodos))
                    botones.append(s)
                if botones:
                    capa.addWidget(_fila(*botones))
            self.capa_avisos.addWidget(marco)
        self.capa_avisos.addStretch(1)

    def arreglar(self, aviso):
        self._hacer(self.g.arreglar, aviso)
        self._llenar_avisos()

    # =========================================================================================
    # utilidades
    # =========================================================================================
    def _decir(self, texto):
        self.estado.setText(texto)

    def _hacer(self, funcion, *args, aviso=None, **kwargs):
        """Llama al gestor y convierte sus errores en un texto para el usuario."""
        try:
            resultado = funcion(*args, **kwargs)
        except ErrorLightManager as error:
            self._decir(t(error.clave, **error.valores))
            return None
        except Exception as error:  # que un fallo de Maya no rompa el panel
            self._decir(t("error_general", error=error))
            print("LightManager | {}".format(error))
            return None
        if aviso:
            self._decir(t(aviso, n=len(resultado) if isinstance(resultado, (list, tuple)) else 1))
        return resultado if resultado is not None else True

    def _abrir_carpeta(self, carpeta):
        os.makedirs(carpeta, exist_ok=True)
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(carpeta))

    def cerrar(self):
        if self._al_cambiar_gestor in self.g.oyentes:
            self.g.oyentes.remove(self._al_cambiar_gestor)
        self.reloj_miniaturas.stop()
        self.visor.cancelar()


def _numero(valor):
    if valor >= 100:
        return "{:,.0f}".format(valor).replace(",", ".")
    if valor >= 10:
        return "{:.1f}".format(valor).replace(".", ",")
    return "{:.2f}".format(valor).replace(".", ",")


def luminancias(ruta, ancho=64):
    """(ancho, alto, [brillo 0-1 por píxel]) de una imagen PNG/JPG reducida, o None."""
    imagen = QtGui.QImage(ruta)
    if imagen.isNull():
        return None
    alto = max(2, int(round(ancho * imagen.height() / float(max(1, imagen.width())))))
    imagen = imagen.scaled(ancho, alto, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    valores = []
    for j in range(alto):
        for i in range(ancho):
            c = imagen.pixelColor(i, j)
            valores.append(0.2126 * c.redF() + 0.7152 * c.greenF() + 0.0722 * c.blueF())
    return ancho, alto, valores

