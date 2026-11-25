"""Pruebas sin Maya del núcleo de LightManager."""

import datetime
import io
import math
import os
import shutil
import tempfile
import unittest

from falsos import ServiciosFalsos

from lightmanager import api, comprobaciones, escenarios, esquemas, geometria as geo, hdri, ies, nombres
from lightmanager import sol, unidades, zonas
from lightmanager.ajustes import Ajustes
from lightmanager.gestor import ErrorLightManager, Gestor
from lightmanager.modelo import Luz, activa, agrupar


def cerca(a, b, tol=1e-6):
    if isinstance(a, (tuple, list)):
        return all(abs(x - y) < tol for x, y in zip(a, b))
    return abs(a - b) < tol


class Unidades(unittest.TestCase):
    def test_pasos_y_exposicion(self):
        self.assertTrue(cerca(unidades.pasos(1.0, 8.0), 8.0))
        self.assertTrue(cerca(unidades.pasos(4.0, 1.0), 3.0))
        # Respeta la intensidad que ya tenía la luz.
        self.assertTrue(cerca(unidades.exposicion_para(8.0, 4.0), 6.0))
        self.assertEqual(unidades.pasos(0.0, 3.0), float("-inf"))

    def test_kelvin(self):
        calido = unidades.kelvin_a_rgb(2000)
        frio = unidades.kelvin_a_rgb(10000)
        self.assertGreater(calido[0], calido[2])
        self.assertGreater(frio[2], frio[0])
        self.assertEqual(unidades.kelvin_a_hex(6600)[:3], "#ff")
        self.assertTrue(abs(unidades.rgb_a_kelvin(unidades.kelvin_a_rgb(3200)) - 3200) <= 200)

    def test_texto(self):
        self.assertEqual(unidades.texto_pasos(7.25), "7,2")
        self.assertEqual(unidades.texto_pasos(float("-inf")), "—")


class Geometria(unittest.TestCase):
    def test_rotacion_apunta(self):
        for d in [(0, 0, -1), (1, 0, 0), (0, -1, 0), (0.3, 0.5, -0.8), (-0.2, -0.9, 0.3)]:
            r = geo.rotacion_para(d)
            self.assertTrue(cerca(geo.direccion_de_rotacion(r), geo.unitario(d), 1e-6))

    def test_orbita_ida_y_vuelta(self):
        pos = geo.posicion_orbita((0, 1, 0), 3.0, 45.0, 30.0, 20.0)
        az, alt, dist = geo.orbita_de(pos, (0, 1, 0), 20.0)
        self.assertTrue(cerca((az, alt, dist), (45.0, 30.0, 3.0)))

    def test_reflejo(self):
        # Mirando de frente a una superficie que mira a la cámara, el reflejo vuelve hacia la cámara.
        pos, _ = geo.apuntar_reflejo((0, 0, 0), (0, 0, 1), (0, 0, 5), 2.0)
        self.assertTrue(cerca(pos, (0, 0, 2)))
        # Superficie inclinada 45°: la luz sale hacia arriba.
        n = geo.unitario((0, 1, 1))
        pos, rot = geo.apuntar_reflejo((0, 0, 0), n, (0, 0, 5), 1.0)
        self.assertTrue(cerca(pos, (0, 1, 0), 1e-6))
        self.assertTrue(cerca(geo.direccion_de_rotacion(rot), (0, -1, 0), 1e-6))

    def test_sombra(self):
        pos, _ = geo.apuntar_sombra((2, 0, 0), (0, 1, 0), 2.0)
        # La luz está al otro lado del objeto, en la recta suelo-objeto.
        self.assertLess(pos[0], 0)
        self.assertGreater(pos[1], 1)

    def test_superficie_techo(self):
        pos, rot = geo.pegar_a_superficie((0, 3, 0), (0, -1, 0), 0.1)
        self.assertTrue(cerca(pos, (0, 2.9, 0)))
        self.assertTrue(cerca(geo.direccion_de_rotacion(rot), (0, -1, 0)))

    def test_en_linea(self):
        p = geo.en_linea((0, 0, 0), (3, 0, 0), 3)
        self.assertEqual(len(p), 3)
        self.assertTrue(cerca(p[0], (1, 0, 0)) and cerca(p[-1], (3, 0, 0)))


class Sol(unittest.TestCase):
    def test_madrid_noviembre(self):
        f = datetime.date(2026, 11, 24)
        az, alt = sol.posicion_en("madrid", f, 13.75)
        self.assertTrue(25 < alt < 32, alt)       # unos 29° como mucho en noviembre
        self.assertTrue(170 < az < 200, az)       # al sur
        salida, puesta = sol.salida_y_puesta("madrid", f)
        self.assertTrue(8.0 < salida < 8.4 and 17.7 < puesta < 18.0, (salida, puesta))

    def test_verano_y_norte(self):
        self.assertTrue(sol.horario_de_verano(datetime.date(2026, 7, 1), "eu"))
        self.assertFalse(sol.horario_de_verano(datetime.date(2026, 12, 1), "eu"))
        _, alt = sol.posicion_en("madrid", datetime.date(2026, 6, 21), 14.25)
        self.assertGreater(alt, 70)
        _, alt = sol.posicion_en("oslo", datetime.date(2026, 11, 24), 12.5)
        self.assertLess(alt, 11)

    def test_vector_y_temperatura(self):
        # Sol al sur a 0° de altura: en la escena, +Z (abajo en la vista Top).
        self.assertTrue(cerca(sol.vector_escena(180, 0), (0, 0, 1), 1e-9))
        self.assertTrue(cerca(sol.vector_escena(90, 0), (1, 0, 0), 1e-9))
        self.assertLess(sol.temperatura(3), sol.temperatura(30))
        self.assertEqual(sol.temperatura(60), 5600)
        self.assertEqual(sol.texto_hora(17.5), "17:30")


class Esquemas(unittest.TestCase):
    def test_carga_y_familias(self):
        todos = esquemas.cargar()
        self.assertEqual(len(esquemas.por_familia(todos, "estudio")), 7)
        self.assertTrue(esquemas.por_familia(todos, "interior"))
        self.assertTrue(esquemas.por_familia(todos, "exterior"))

    def test_escala(self):
        e = esquemas.buscar(esquemas.cargar(), "tres_puntos")
        uno = esquemas.colocar(e, ((-0.5, 0, -0.5), (0.5, 1, 0.5)), (0, 1, 5))
        diez = esquemas.colocar(e, ((-5, 0, -5), (5, 10, 5)), (0, 10, 50))
        # Diez veces más grande: luz a diez veces la distancia y 2*log2(10) pasos más.
        self.assertTrue(cerca(diez[0]["pasos"] - uno[0]["pasos"], 2 * math.log2(10)))
        self.assertTrue(cerca(geo.distancia(diez[0]["posicion"], diez[0]["objetivo"]),
                              10 * geo.distancia(uno[0]["posicion"], uno[0]["objetivo"])))

    def test_relativo_a_camara(self):
        e = esquemas.buscar(esquemas.cargar(), "tres_puntos")
        caja = ((-0.5, 0, -0.5), (0.5, 1, 0.5))
        delante = esquemas.colocar(e, caja, (0, 0.5, 5))[0]["posicion"]
        lado = esquemas.colocar(e, caja, (5, 0.5, 0))[0]["posicion"]
        # La clave a 45° a la derecha de la cámara gira con la cámara.
        self.assertGreater(delante[0], 0)
        self.assertLess(lado[2], 0)

    def test_horas(self):
        self.assertEqual(esquemas.hora_de("mediodia", 8.0, 18.0), 13.0)
        self.assertEqual(esquemas.hora_de("puesta-0.5", 8.0, 18.0), 17.5)
        self.assertEqual(esquemas.hora_de("salida+1", 8.2, 18.0), 9.25)


class Varios(unittest.TestCase):
    def test_nombres(self):
        self.assertEqual(nombres.limpio("Lámpara de pie"), "Lampara_de_pie")
        self.assertEqual(nombres.de_zona("Salón"), "LM_zona_Salon")
        self.assertEqual(nombres.siguiente("LM_Clave", ["LM_Clave"]), "LM_Clave2")
        self.assertEqual(nombres.siguiente("LM_Farola2", ["LM_Farola2", "LM_Farola3"]), "LM_Farola4")
        self.assertEqual(nombres.sin_numero("Downlight salón 3"), "Downlight salón")

    def test_activa_y_agrupar(self):
        a, b = Luz("a", "area", papel="Clave"), Luz("b", "area", papel="Relleno")
        self.assertTrue(activa(a, [a, b]))
        b.solo = True
        self.assertFalse(activa(a, [a, b]))
        self.assertEqual([g for g, _ in agrupar([b, a])], ["Clave", "Relleno"])

    def test_zonas(self):
        salon = zonas.Zona("Salón", ((0, 0, 0), (5, 3, 5)))
        sofa = zonas.Zona("Rincón", ((0, 0, 0), (1, 3, 1)))
        self.assertEqual(zonas.zona_de((0.5, 1, 0.5), [salon, sofa]), "Rincón")
        self.assertEqual(zonas.zona_de((4, 1, 4), [salon, sofa]), "Salón")
        self.assertEqual(zonas.zona_de((9, 1, 9), [salon]), "Escena")
        fija = Luz("f", "punto", posicion=(4, 1, 4), zona="=Cocina")
        libre = Luz("l", "punto", posicion=(4, 1, 4))
        cambios = zonas.reasignar([fija, libre], [salon])
        self.assertEqual(len(cambios), 1)
        self.assertEqual(libre.zona, "Salón")
        self.assertEqual(zonas.nombre_visible(fija.zona), "Cocina")

    def test_escenarios_codificar(self):
        datos = [{"nombre": "Día", "luces": {"a": {"pasos": 3}}}]
        self.assertEqual(escenarios.decodificar(escenarios.codificar(datos)), datos)
        self.assertEqual(escenarios.decodificar("basura"), [])

    def test_ies(self):
        d = tempfile.mkdtemp()
        try:
            rutas = ies.asegurar(d)
            self.assertEqual(len(rutas), 8)
            texto = open(rutas["downlight"]).read()
            self.assertTrue(texto.startswith("IESNA:LM-63-2002"))
            self.assertIn("TILT=NONE", texto)
            valores = ies.candelas("downlight")
            self.assertEqual(len(valores), len(ies.ANGULOS))
            self.assertGreater(valores[0], valores[-1])  # alumbra hacia abajo
            farola = ies.candelas("farola")
            self.assertGreater(farola[12], farola[0])     # abanico ancho: más luz a 60° que en vertical
            self.assertEqual(ies.clave_de(rutas["farola"]), "farola")
        finally:
            shutil.rmtree(d)

    def test_hdri_listar_y_descargar(self):
        d = tempfile.mkdtemp()
        try:
            for n in ("cielo.hdr", "cielo.tx", "otro.exr", "nota.txt"):
                open(os.path.join(d, n), "w").close()
            lista = hdri.listar([d])
            self.assertEqual([n for n, _ in lista], ["cielo", "otro"])
            self.assertTrue(lista[0][1].endswith(".hdr"))

            pedidas = []

            def abrir(url, timeout=0):
                pedidas.append(url)
                if "venice" in url:
                    raise IOError("sin red")
                return io.BytesIO(b"#?RADIANCE")

            hechos, fallidos = hdri.descargar_pack(os.path.join(d, "pack"), abrir=abrir)
            self.assertEqual(len(hechos), 7)
            self.assertEqual(fallidos[0][0], "venice_sunset")
            self.assertTrue(hdri.buscar([os.path.join(d, "pack")], "lebombo").endswith("lebombo_2k.hdr"))
        finally:
            shutil.rmtree(d)


class GestorPruebas(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.s = ServiciosFalsos()
        self.a = Ajustes(os.path.join(self.dir, "prefs"))
        self.g = Gestor(self.s, self.a)
        self.cambios = 0
        self.g.oyentes.append(self._oyente)

    def _oyente(self):
        self.cambios += 1

    def tearDown(self):
        shutil.rmtree(self.dir)

    def esquema(self, ident="tres_puntos"):
        return esquemas.buscar(self.g.esquemas(), ident)

    def test_aplicar_esquema_y_reemplazar(self):
        creadas = self.g.aplicar_esquema(self.esquema())
        self.assertEqual([c for c in creadas], ["LM_Clave", "LM_Relleno", "LM_Contra"])
        self.assertTrue(all(l.esquema == "tres_puntos" for l in self.g.luces))
        self.g.crear("area", "Mía")
        self.g.aplicar_esquema(self.esquema("rembrandt"))
        nodos = [l.nodo for l in self.g.luces]
        self.assertIn("LM_Mia", nodos)           # la que hice a mano no se borra
        self.assertNotIn("LM_Contra", nodos)     # las del esquema anterior sí
        self.assertGreater(self.cambios, 0)

    def test_solo_y_visibilidad(self):
        self.g.aplicar_esquema(self.esquema())
        self.g.solo(["LM_Clave"])
        vis = {l.nodo: l.visible for l in self.s.luces()}
        self.assertEqual(vis, {"LM_Clave": True, "LM_Relleno": False, "LM_Contra": False})
        self.g.quitar_solos()
        self.assertTrue(all(l.visible for l in self.s.luces()))
        self.g.encender(["LM_Relleno"], False)
        self.assertFalse(self.s._luces["LM_Relleno"].visible)

    def test_cambio_relativo_y_gemelas(self):
        self.g.aplicar_esquema(self.esquema())
        antes = {l.nodo: l.pasos for l in self.g.luces}
        self.g.cambiar(["LM_Clave", "LM_Relleno"], "pasos", 1.0, relativo=True)
        self.assertTrue(cerca(self.s._luces["LM_Clave"].pasos, antes["LM_Clave"] + 1))
        self.assertTrue(cerca(self.s._luces["LM_Relleno"].pasos, antes["LM_Relleno"] + 1))
        self.assertTrue(cerca(self.s._luces["LM_Contra"].pasos, antes["LM_Contra"]))

    def test_repetir_crea_gemelas(self):
        nodo = self.g.crear("fotometrica", "Downlight", posicion=(0, 3, 0))
        nuevas = self.g.repetir(nodo, (3, 3, 0), 3)
        self.assertEqual(len(nuevas), 3)
        gemelas = {l.gemela for l in self.g.luces}
        self.assertEqual(len(gemelas), 1)
        self.g.cambiar([nuevas[0]], "kelvin", 2400)
        self.assertTrue(all(l.kelvin == 2400 for l in self.s.luces()))
        self.assertEqual(sorted(l.nodo for l in self.g.luces),
                         ["LM_Downlight_1", "LM_Downlight_2", "LM_Downlight_3", "LM_Downlight_4"])
        self.g.separar_gemelas([nuevas[0]])
        self.g.cambiar([nuevas[0]], "kelvin", 5000)
        self.assertEqual(sorted(l.kelvin for l in self.s.luces()), [2400, 2400, 2400, 5000])

    def test_apuntar(self):
        self.g.aplicar_esquema(self.esquema())
        clave = self.g.luz("LM_Clave")
        d = geo.distancia(clave.posicion, clave.objetivo)
        pos, rot = self.g.apuntar("LM_Clave", "reflejo", (0, 0.5, 0.5), (0, 0, 1), (0, 0.5, 6))
        self.assertTrue(cerca(geo.distancia(pos, (0, 0.5, 0.5)), d, 1e-6))
        self.assertTrue(cerca(geo.direccion_de_rotacion(rot), (0, 0, -1), 1e-6))
        with self.assertRaises(ErrorLightManager):
            self.g.apuntar("LM_Clave", "reflejo", (0, 0, 0), (0, 0, 1), None)

    def test_orbita(self):
        self.g.aplicar_esquema(self.esquema())
        az, alt, dist = self.g.orbita("LM_Clave")
        self.assertTrue(cerca((az, alt), (45.0, 35.0), 1e-6))
        self.g.mover_orbita("LM_Clave", azimut=-30.0)
        az2, alt2, dist2 = self.g.orbita("LM_Clave")
        self.assertTrue(cerca((az2, alt2, dist2), (-30.0, 35.0, dist), 1e-6))

    def test_portales_y_lamparas(self):
        with self.assertRaises(ErrorLightManager):
            self.g.crear_portales()
        self.s.ventanas = [((0, 1.5, -2), (0, 0, -1), 1.2, 1.0, "ventana1")]
        self.g.crear_cielo = None
        self.g.poner_hdri("cielo.hdr")
        self.g.crear_portales()
        portal = [l for l in self.g.luces if l.tipo == "portal"][0]
        self.assertTrue(cerca(portal.escala, (0.6, 0.5, 1.0)))
        self.assertEqual(self.g.cielo().portal_modo, 1)
        self.s.sel = ["taza"]
        lamp = self.g.crear_lamparas()[0]
        self.assertEqual(self.s.enlaces[(lamp, "taza")], 1)   # la pantalla no le hace sombra
        self.assertTrue(self.g.luz(lamp).ies.endswith("lightmanager_pantalla.ies"))

    def test_superficie_y_zonas(self):
        self.g.crear_zona("Salón", ((0, 0, 0), (5, 3, 5)))
        nodo = self.g.colocar_en_superficie((2, 3, 2), (0, -1, 0))
        luz = self.g.luz(nodo)
        self.assertEqual(luz.zona, "Salón")
        self.assertEqual(luz.nombre, "Downlight_salon")
        self.g.escribir_varios(nodo, {"posicion": (9, 1, 9)})
        self.g.reasignar_zonas()
        self.assertEqual(self.g.luz(nodo).zona, "Escena")
        self.g.fijar_zona([nodo], "Salón")
        self.assertEqual(self.g.luz(nodo).zona, "=Salón")
        self.s.grupos = [("Cocina", ((5, 0, 0), (8, 3, 5))), ("Vacío", None)]
        self.assertEqual(len(self.g.zonas_desde_outliner()), 1)

    def test_sol_fisico_y_practicas(self):
        self.a["ciudad"] = "madrid"
        lampara = self.g.crear("punto", "Lámpara")
        self.g.poner_cielo_fisico()
        self.g.poner_sol(hora=13.0, fecha="2026-11-24")
        s = self.g.sol()
        self.assertEqual(s.esquema, "sol_fisico")
        self.assertTrue(s.encendida)
        self.assertGreater(s.kelvin, 4500)
        self.assertFalse(self.g.luz(lampara).encendida)    # de día, prácticas apagadas
        self.g.poner_sol(hora=21.0)
        self.assertFalse(self.g.sol().encendida)
        self.assertTrue(self.g.luz(lampara).encendida)     # de noche se encienden solas
        self.assertIn(self.g.cielo().nodo, self.s.fisico)

    def test_esquema_de_escena(self):
        self.g.crear("punto", "Lámpara")
        self.g.aplicar_esquema(self.esquema("exterior_atardecer"))
        estado = self.g.estado_sol()
        salida, puesta = sol.salida_y_puesta(estado["ciudad"], datetime.date.fromisoformat(estado["fecha"]))
        self.assertTrue(cerca(estado["hora"], round((puesta - 0.5) * 4) / 4.0))
        self.assertEqual(self.g.modo(), "escena")
        self.g.aplicar_esquema(self.esquema("interior_noche"))
        self.assertTrue(self.g.luz("LM_Lampara").encendida)

    def test_escenarios(self):
        self.g.aplicar_esquema(self.esquema())
        self.g.guardar_escenario("Base")
        self.g.cambiar(["LM_Clave"], "pasos", 2.0)
        self.g.encender(["LM_Contra"], False)
        self.g.comparar_inicio("Base")
        self.assertTrue(self.s._luces["LM_Contra"].encendida)
        self.g.comparar_fin()
        self.assertFalse(self.s._luces["LM_Contra"].encendida)
        cambios = self.g.recuperar_escenario("Base")
        self.assertEqual(len(cambios), 2)
        self.assertTrue(self.s._luces["LM_Contra"].encendida)
        self.g.renombrar("LM_Clave", "LM_Principal")
        self.assertIn("LM_Principal", self.g.escenarios()[0]["luces"])
        self.g.borrar_escenario("Base")
        self.assertEqual(self.g.escenarios(), [])

    def test_comprobar_y_arreglar(self):
        avisos = self.g.comprobar()
        self.assertEqual(avisos[0].clave, "sin_luces")
        self.g.arreglar(avisos[0])
        self.assertEqual(len(self.g.luces), 3)
        self.g.solo(["LM_Clave"])
        self.s.crear({"nombre": "pointLight1", "tipo": "punto", "decay": 0})
        self.g.refrescar()
        claves = {a.clave: a for a in comprobaciones.pendientes(self.g.comprobar())}
        self.assertIn("solo", claves)
        self.assertIn("decay", claves)
        self.assertIn("nombres", claves)
        for c in ("solo", "decay", "nombres"):
            self.g.arreglar(claves[c])
        claves = {a.clave for a in comprobaciones.pendientes(self.g.comprobar())}
        self.assertFalse({"solo", "decay", "nombres"} & claves)

    def test_arreglar_muestras_baja_a_1(self):
        self.s.crear({"nombre": "LM_Lenta", "tipo": "punto", "decay": 2, "muestras": 8})
        self.g.refrescar()
        claves = {a.clave: a for a in comprobaciones.pendientes(self.g.comprobar())}
        self.assertIn("muestras", claves)
        self.g.arreglar(claves["muestras"])
        self.assertEqual(self.g.luz("LM_Lenta").muestras, 1)
        claves = {a.clave for a in comprobaciones.pendientes(self.g.comprobar())}
        self.assertNotIn("muestras", claves)

    def test_guardar_esquema_propio(self):
        self.g.aplicar_esquema(self.esquema())
        ruta = self.g.guardar_como_esquema("Mi luz de taza")
        self.assertTrue(os.path.exists(ruta))
        mio = [e for e in self.g.esquemas() if e.familia == "mios"][0]
        self.assertEqual(mio.nombre, "Mi luz de taza")
        original = esquemas.colocar(self.esquema(), self.g.objetivo_y_tamano(), self.s.camara)
        copia = esquemas.colocar(mio, self.g.objetivo_y_tamano(), self.s.camara)
        for a, b in zip(original, copia):
            self.assertTrue(cerca(a["posicion"], b["posicion"], 1e-2))
            self.assertTrue(cerca(a["pasos"], b["pasos"], 1e-2))

    def test_grupos_y_mezcla(self):
        self.g.aplicar_esquema(self.esquema())
        self.assertEqual(self.g.grupos(), ["clave", "contra", "relleno"])
        self.g.poner_grupo(["LM_Contra"], "Borde Pelo")
        self.assertIn("borde_pelo", self.g.grupos())
        antes = self.g.luz("LM_Clave").pasos
        self.g.llevar_mezcla({"clave": -0.5})
        self.assertTrue(cerca(self.s._luces["LM_Clave"].pasos, antes - 0.5))
        self.assertEqual(self.g.crear_aovs(), ["RGBA_borde_pelo", "RGBA_clave", "RGBA_relleno"])

    def test_modo_propuesto(self):
        self.assertEqual(self.g.modo(), "estudio")
        self.g.crear_zona("Cocina", ((0, 0, 0), (1, 1, 1)))
        self.assertEqual(self.g.modo(), "escena")
        self.g.poner_modo("estudio")
        self.assertEqual(self.g.modo(), "estudio")

    def test_api(self):
        api.usar(self.g)
        self.g.aplicar_esquema(self.esquema())
        luces = api.listar()
        self.assertEqual(luces[0]["nombre"], "Clave")
        api.potencia("LM_Clave", 1, relativo=True)
        self.assertTrue(cerca(api.listar()[0]["pasos"], luces[0]["pasos"] + 1))
        api.solo("LM_Relleno")
        self.assertEqual([l["activa"] for l in api.listar()], [False, True, False])
        avisos = api.comprobar()
        solo = [a for a in avisos if a["clave"] == "solo"][0]
        self.assertEqual(solo["nivel"], "mal")
        self.assertIn("Relleno", solo["texto"])
        self.assertTrue(api.arreglar("solo"))
        r = api.resumen()
        self.assertEqual((r["luces"], r["activas"], r["modo"]), (3, 3, "estudio"))
        api.usar(None)


if __name__ == "__main__":
    unittest.main()
