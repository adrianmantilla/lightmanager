"""Pruebas del panel con Qt sin pantalla (QT_QPA_PLATFORM=offscreen) y servicios falsos."""

import os
import shutil
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6 import QtCore, QtWidgets  # noqa: F401
except ImportError:  # pragma: no cover
    QtWidgets = None

from falsos import ServiciosFalsos

from lightmanager.ajustes import Ajustes
from lightmanager.gestor import Gestor


class VisorFalso(object):
    disponible = True

    def __init__(self):
        self.clic = None
        self.rectangulo = None

    def crear_vista(self, padre):
        return QtWidgets.QLabel("vista", padre)

    def encuadrar(self):
        pass

    def pedir_clic(self, texto, funcion, repetir=False):
        self.clic = funcion
        return True

    def pedir_rectangulo(self, texto, funcion):
        self.rectangulo = funcion
        return True

    def cancelar(self):
        self.clic = None


@unittest.skipIf(QtWidgets is None, "sin PySide6")
class Panel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        from lightmanager.panel import PanelLightManager
        self.carpeta = tempfile.mkdtemp()
        self.s = ServiciosFalsos()
        self.g = Gestor(self.s, Ajustes(self.carpeta))
        self.visor = VisorFalso()
        self.p = PanelLightManager(self.g, self.visor)
        self.p.resize(460, 900)
        self.p.show()

    def tearDown(self):
        self.p.cerrar()
        self.p.close()
        self.p.deleteLater()
        shutil.rmtree(self.carpeta, ignore_errors=True)

    def esquema(self, ident="tres_puntos"):
        return [e for e in self.g.esquemas() if e.id == ident][0]

    def pasar(self):
        QtWidgets.QApplication.processEvents()

    def luces_en_lista(self):
        return [it.data(0, QtCore.Qt.UserRole) for it in self.p._items_luz()]

    def test_esquema_lista_y_ficha(self):
        self.p.aplicar_esquema(self.esquema())
        self.assertEqual(len(self.luces_en_lista()), 3)
        self.assertEqual(self.p.seleccion, ["LM_Clave"])
        self.assertTrue(self.p.ficha_cuerpo.isVisibleTo(self.p))
        self.assertEqual(self.p.campo_nombre.text(), "Clave")
        # Potencia desde la ficha: un solo cambio.
        self.p.potencia.casilla.setValue(5.0)
        self.assertAlmostEqual(self.s._luces["LM_Clave"].pasos, 5.0)
        self.p._cambiar("pasos", 1.0, relativo=True)
        self.assertAlmostEqual(self.s._luces["LM_Clave"].pasos, 6.0)
        # Órbita visible en Estudio
        self.assertTrue(self.p.caja_orbita.isVisibleTo(self.p))
        self.assertEqual(len(self.p.orbita.luces), 3)

    def test_solo_y_encender(self):
        self.p.aplicar_esquema(self.esquema())
        item = [it for it in self.p._items_luz() if it.data(0, QtCore.Qt.UserRole) == "LM_Relleno"][0]
        self.p._clic_lista(item, 1)
        self.pasar()
        self.assertTrue(self.s._luces["LM_Relleno"].solo)
        item = [it for it in self.p._items_luz() if it.data(0, QtCore.Qt.UserRole) == "LM_Contra"][0]
        item.setCheckState(0, QtCore.Qt.Unchecked)
        self.assertFalse(self.s._luces["LM_Contra"].encendida)

    def test_modo_escena_y_apuntar(self):
        self.p.aplicar_esquema(self.esquema())
        self.p.poner_modo("escena")
        self.assertTrue(self.p.fila_escena.isVisibleTo(self.p))
        self.assertIsNotNone(self.p.vista_maya)
        self.p.elegir(["LM_Clave"])
        self.p.apuntar("luz", True)
        self.assertIsNotNone(self.visor.clic)
        self.visor.clic((0.0, 1.0, 0.5), (0.0, 0.0, 1.0), (0.0, 1.0, 6.0))
        l = self.g.luz("LM_Clave")
        self.assertGreater(l.posicion[2], 0.5)
        # Colocar en superficie
        self.p.colocar("fotometrica", "downlight")
        self.visor.clic((1.0, 2.5, 1.0), (0.0, -1.0, 0.0), None)
        self.assertTrue(any(x.tipo == "fotometrica" for x in self.g.luces))
        # Zona con rectángulo
        self.p._pedir_nombre = lambda *a, **k: "Cocina"
        self.p.zona_rectangulo()
        self.visor.rectangulo(((-2, 0, -2), (2, 3, 2)))
        self.assertEqual([z.nombre for z in self.g.zonas()], ["Cocina"])

    def test_pestanas(self):
        self.p.aplicar_esquema(self.esquema())
        for i in range(self.p.pestanas.count()):
            self.p.pestanas.setCurrentIndex(i)
        self.p.pestanas.setCurrentIndex(5)
        self.assertGreater(self.p.capa_avisos.count(), 1)
        # Escenarios
        self.p._pedir_nombre = lambda *a, **k: "Día"
        self.p.guardar_escenario()
        self.assertEqual(self.p.lista_escenarios.count(), 1)
        self.p.lista_escenarios.setCurrentRow(0)
        self.g.cambiar(["LM_Clave"], "pasos", 1.0)
        self.p._comparar_inicio()
        self.p._comparar_fin()
        self.assertAlmostEqual(self.s._luces["LM_Clave"].pasos, 1.0)
        self.p.recuperar_escenario()
        self.assertNotAlmostEqual(self.s._luces["LM_Clave"].pasos, 1.0)

    def test_errores_se_muestran(self):
        self.p.poner_modo("escena")
        self.p._hacer(self.g.crear_portales)
        self.assertIn("ventanas", self.p.estado.text())

    def test_sol(self):
        self.p.poner_modo("escena")
        self.p.pestanas.setCurrentIndex(2)
        self.p._poner_sol(hora=18.0)
        self.assertTrue(self.g.estado_sol()["activo"])
        self.assertIsNotNone(self.g.sol())


if __name__ == "__main__":
    unittest.main()
