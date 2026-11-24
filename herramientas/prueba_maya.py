"""Prueba de LightManager dentro de Maya, sin interfaz (herramienta de desarrollo).

Desde la terminal, con el mayapy de cada versión:

    /Applications/Autodesk/maya2027/Maya.app/Contents/bin/mayapy herramientas/prueba_maya.py
    "C:\\Program Files\\Autodesk\\Maya2027\\bin\\mayapy.exe" herramientas\\prueba_maya.py

Necesita Arnold (MtoA). No toca tus preferencias: los ajustes van a una carpeta
temporal. Comprueba que el plugin carga y, sobre una escena de prueba, esquemas,
pasos y Kelvin leídos de vuelta, solo, órbita, apuntar, sol por hora, cielo físico,
zonas, portales, lámparas, luces de malla, repetir, enlaces, AOV, escenarios,
comprobaciones y la API. El panel y los clics en el visor necesitan la interfaz:
pruébalos abriendo Maya normalmente.
Termina con «RESULTADO: OK» o con la lista de fallos.
"""

import datetime
import math
import os
import shutil
import sys
import tempfile
import traceback

try:  # que las líneas salgan aunque la salida vaya a un archivo (el script termina con os._exit)
    sys.stdout.reconfigure(line_buffering=True)
except AttributeError:
    pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "scripts"))

fallos = []


def comprobar(condicion, texto):
    print(("  ok    " if condicion else "  FALLO ") + texto)
    if not condicion:
        fallos.append(texto)


def cerca(a, b, tol=1e-3):
    if isinstance(a, (tuple, list)):
        return all(abs(x - y) < tol for x, y in zip(a, b))
    return abs(a - b) < tol


def direccion_mundo(cmds, nodo):
    """Hacia dónde alumbra una luz (su -Z local en el mundo)."""
    m = cmds.xform(nodo, query=True, matrix=True, worldSpace=True)
    z = (m[8], m[9], m[10])
    largo = math.sqrt(sum(c * c for c in z)) or 1.0
    return tuple(-c / largo for c in z)


def main():
    import maya.standalone
    maya.standalone.initialize(name="python")
    from maya import cmds

    print("Maya", cmds.about(version=True), "-", cmds.about(operatingSystem=True))
    try:
        cmds.loadPlugin("mtoa", quiet=True)
    except Exception as error:
        print("  (sin Arnold: {})".format(error))
    comprobar(cmds.pluginInfo("mtoa", query=True, loaded=True), "Arnold (mtoa) está cargado")
    cmds.loadPlugin(os.path.join(RAIZ, "plug-ins", "lightmanager_plugin.py"))
    comprobar(cmds.pluginInfo("lightmanager_plugin", query=True, loaded=True), "el plugin se carga")
    from lightmanager import interfaz_maya
    interfaz_maya.iniciar()
    for nombre in interfaz_maya.COMANDOS:
        comprobar(cmds.runTimeCommand(nombre, exists=True), "existe la orden " + nombre)

    from lightmanager import api, geometria as geo, sol as solar
    from lightmanager.ajustes import Ajustes
    from lightmanager.esquemas import buscar
    from lightmanager.gestor import Gestor
    from lightmanager.maya_servicios import ServiciosMaya

    temporal = tempfile.mkdtemp()
    try:
        cmds.file(new=True, force=True)
        cmds.polyPlane(name="suelo", width=10, height=10)
        taza = cmds.polyCube(name="taza", width=1, height=1, depth=1)[0]
        cmds.move(0, 0.5, 0, taza)
        cam, cam_forma = cmds.camera(name="camRender")
        cmds.move(0, 1.5, 6, cam)
        cmds.setAttr("perspShape.renderable", False)
        cmds.setAttr(cam_forma + ".renderable", True)

        s = ServiciosMaya()
        g = Gestor(s, Ajustes(os.path.join(temporal, "prefs")))
        interfaz_maya._estado.update({"servicios": s, "gestor": g, "ajustes": g.ajustes})
        g.refrescar()

        # --- esquema de estudio ---
        cmds.select(taza)
        creadas = g.aplicar_esquema(buscar(g.esquemas(), "tres_puntos"))
        comprobar(len(creadas) == 3, "tres puntos crea 3 luces")
        tipos = sorted(cmds.nodeType(cmds.listRelatives(n, shapes=True)[0]) for n in creadas)
        comprobar(tipos == ["aiAreaLight"] * 3, "son luces de área de Arnold ({})".format(tipos))
        clave = [n for n in creadas if "Clave" in n][0]
        l = g.luz(clave)
        comprobar(cerca(geo.angulos(direccion_mundo(cmds, clave)),
                        geo.angulos(geo.resta(l.objetivo, l.posicion)), 0.5),
                  "la clave mira al objeto")
        g.cambiar([clave], "pasos", 7.5)
        g.cambiar([clave], "kelvin", 3200)
        g.refrescar()
        comprobar(cerca(g.luz(clave).pasos, 7.5), "pasos leídos de vuelta")
        comprobar(abs(g.luz(clave).kelvin - 3200) < 1, "Kelvin leídos de vuelta")
        forma = cmds.listRelatives(clave, shapes=True)[0]
        comprobar(cerca(cmds.getAttr(forma + ".intensity") * 2 ** cmds.getAttr(forma + ".aiExposure"), 2 ** 7.5, 0.5),
                  "intensity·2^exposure = 2^pasos")
        g.solo([clave])
        visibles = [n for n in creadas if cmds.getAttr(n + ".visibility")]
        comprobar(visibles == [clave], "solo deja visible solo la clave")
        g.quitar_solos()
        comprobar(all(cmds.getAttr(n + ".visibility") for n in creadas), "quitar solos enciende todas")
        g.mover_orbita(clave, azimut=90, altura=20)
        az, alt, _ = g.orbita(clave)
        comprobar(cerca(az, 90, 0.5) and cerca(alt, 20, 0.5), "órbita: azimut y altura ({:.1f}, {:.1f})".format(az, alt))
        g.apuntar(clave, "luz", (0.5, 0.5, 0.0), (1.0, 0.0, 0.0), (0, 1.5, 6))
        comprobar(cerca(direccion_mundo(cmds, clave), (-1.0, 0.0, 0.0), 0.02), "apuntar: la luz alumbra el punto de frente")
        g.apuntar(clave, "reflejo", (0.0, 1.0, 0.0), (0.0, 1.0, 0.0), (0, 1.5, 6))
        d = direccion_mundo(cmds, clave)
        # Brillo en lo alto del objeto visto desde la cámara: la luz está al otro lado, casi rasante, y alumbra hacia la cámara.
        comprobar(d[1] < 0 and d[2] > 0.9, "apuntar reflejo: la luz viene del otro lado, hacia la cámara")

        # --- tipos de luz ---
        for tipo in ("foco", "punto", "fotometrica", "sol"):
            n = g.crear_en_orbita(tipo)
            comprobar(bool(n) and cmds.objExists(n), "crear luz " + tipo)
        foto = [x for x in g.luces if x.tipo == "fotometrica"][0]
        forma = cmds.listRelatives(foto.nodo, shapes=True)[0]
        comprobar(os.path.isfile(cmds.getAttr(forma + ".aiFilename") or ""), "la fotométrica tiene su IES")
        print("        (orientación de la fotométrica: mira {})".format(
            tuple(round(c, 2) for c in direccion_mundo(cmds, foto.nodo))))

        # --- escena: zonas, sol, cielo físico ---
        cocina = g.crear_zona("Cocina", ((-5, 0, -5), (0, 3, 5)))
        comprobar(bool(cocina) and [z.nombre for z in g.zonas()] == ["Cocina"], "crear zona")
        cmds.polyPlane(name="ventana", width=1, height=1.2, axis=(0, 0, 1))
        cmds.move(-2, 1.5, -4.9, "ventana")
        cmds.select("ventana")
        portales = g.crear_portales()
        comprobar(len(portales) == 1, "un portal por ventana")
        g.poner_cielo_fisico()
        comprobar(g.cielo() is not None and g.cielo().cielo_fisico, "cielo físico puesto")
        g.poner_sol(ciudad="madrid", fecha="2026-06-21", hora=12.0)
        sol = g.sol()
        az, alt = solar.posicion_en("madrid", datetime.date(2026, 6, 21), 12.0)
        esperado = geo.escala(solar.vector_escena(az, alt, 0.0), -1.0)
        comprobar(cerca(direccion_mundo(cmds, sol.nodo), esperado, 0.02), "el sol alumbra desde donde toca a esa hora")
        g.poner_sol(hora=23.0)
        comprobar(not cmds.getAttr(sol.nodo + ".visibility") or not g.sol().encendida, "de noche el sol se apaga")

        lampara = cmds.polyCylinder(name="lampara", radius=0.2, height=0.3)[0]
        cmds.move(1, 1, 1, lampara)
        cmds.select(lampara)
        comprobar(len(g.crear_lamparas()) == 1, "una bombilla por lámpara")
        tira = cmds.polyCube(name="tiraLED", width=1, height=0.02, depth=0.02)[0]
        cmds.select(tira)
        comprobar(len(g.crear_luces_de_malla()) == 1, "luz de malla")
        nueva = g.colocar_en_superficie((-2, 3, 0), (0, -1, 0))
        g.refrescar()
        comprobar(g.luz(nueva).zona == "Cocina", "la luz del techo cae en la zona Cocina")
        copias = g.repetir(nueva, (-4, 3, 0), 2)
        comprobar(len(copias) == 2, "repetir crea 2 gemelas")

        # --- enlaces, AOV, escenarios, comprobar, API ---
        g.poner_enlace([clave], ["|suelo"], 1)
        comprobar(g.estado_enlace(clave, "|suelo") == 1, "enlace: ilumina sin sombra")
        g.poner_enlace([clave], ["|suelo"], 0)
        comprobar(g.estado_enlace(clave, "|suelo") == 0, "enlace: no le afecta")
        g.poner_enlace([clave], ["|suelo"], 2)
        comprobar(g.estado_enlace(clave, "|suelo") == 2, "enlace: vuelve a iluminar")
        aovs = g.crear_aovs()
        comprobar("RGBA_clave" in aovs, "AOV de grupos ({})".format(", ".join(aovs)))
        g.guardar_escenario("Día")
        g.cambiar([clave], "pasos", 2.0)
        g.recuperar_escenario("Día")
        g.refrescar()
        comprobar(cerca(g.luz(clave).pasos, 7.5), "recuperar escenario")
        avisos = g.comprobar()
        comprobar(len(avisos) > 0, "comprobaciones ({} avisos)".format(len(avisos)))
        comprobar(len(api.listar()) == len(g.luces), "api.listar")
        comprobar(api.resumen()["luces"] == len([x for x in g.luces if x.emite]), "api.resumen (sin contar portales)")

        ruta = os.path.join(temporal, "escena.ma")
        cmds.file(rename=ruta)
        cmds.file(save=True, type="mayaAscii")
        cmds.file(ruta, open=True, force=True)
        g.refrescar()
        comprobar([e["nombre"] for e in g.escenarios()] == ["Día"], "los escenarios se guardan en la escena")
        comprobar(g.modo() == "escena", "el modo se recuerda en la escena")
    except Exception:
        traceback.print_exc()
        fallos.append("excepción")
    finally:
        shutil.rmtree(temporal, ignore_errors=True)

    print()
    print("RESULTADO: OK" if not fallos else "RESULTADO: {} fallos\n - {}".format(len(fallos), "\n - ".join(fallos)))
    try:
        maya.standalone.uninitialize()
    except Exception:
        pass
    os._exit(0 if not fallos else 1)


if __name__ == "__main__":
    main()
