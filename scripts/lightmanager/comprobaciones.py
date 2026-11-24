"""Comprobaciones de iluminación con semáforo y arreglo. No depende de Maya.

``revisar(luces, info)`` devuelve una lista de ``Aviso``. ``info`` lo rellena
``Servicios.info_comprobaciones()`` con lo que no está en las luces (qué mallas
encierran una bombilla, qué HDRI no tienen .tx…). RenderDesk muestra estos mismos
avisos en su pestaña Comprobar a través de ``lightmanager.api``.
"""

import os
import re

from lightmanager.modelo import activa

OK, AVISO, MAL = "ok", "aviso", "mal"
_NOMBRE_DE_FABRICA = re.compile(r"^(ai)?(Area|Sky[Dd]ome|Photometric|Mesh|Light)?[A-Za-z]*Light(Portal)?\d*$")


class Aviso(object):
    def __init__(self, clave, nivel, nodos=(), arreglo=None, **valores):
        self.clave = clave
        self.nivel = nivel
        self.nodos = list(nodos)
        self.arreglo = arreglo
        self.valores = valores

    @property
    def texto(self):
        return "chk_{}_{}".format(self.clave, "ok" if self.nivel == OK else "mal")

    @property
    def detalle(self):
        return "chk_{}_{}_det".format(self.clave, "ok" if self.nivel == OK else "mal")

    def como_dict(self):
        return {"clave": self.clave, "nivel": self.nivel, "nodos": self.nodos, "arreglo": self.arreglo,
                "valores": self.valores}

    def __repr__(self):
        return "Aviso({}, {})".format(self.clave, self.nivel)


def _nombres(luces):
    return ", ".join("«{}»".format(l.nombre) for l in luces[:4]) + ("…" if len(luces) > 4 else "")


def revisar(luces, info=None):
    info = info or {}
    avisos = []
    emisoras = [l for l in luces if l.emite]
    activas = [l for l in emisoras if activa(l, luces)]

    # 1. Sin luces: Arnold renderiza en negro (no usa la luz por defecto de Maya).
    if not emisoras:
        avisos.append(Aviso("sin_luces", MAL, arreglo="anadir_esquema"))
        return avisos

    # 2. Solo olvidado.
    solos = [l for l in luces if l.solo and l.encendida]
    if solos:
        avisos.append(Aviso("solo", MAL, [l.nodo for l in solos], "quitar_solo", luces=_nombres(solos)))
    else:
        avisos.append(Aviso("solo", OK))

    # 3. Todo apagado.
    if not activas:
        avisos.append(Aviso("apagadas", MAL, arreglo="encender_todas"))

    # 4. Sombras negras: ni cielo ni relleno.
    hay_cielo = any(l.es_cielo for l in activas)
    hay_relleno = any(l.papel in ("Relleno", "Ambiente") for l in activas)
    if activas and not hay_cielo and not hay_relleno and len(activas) < 2:
        avisos.append(Aviso("sombras_negras", AVISO, arreglo="anadir_cielo"))
    elif activas:
        avisos.append(Aviso("sombras_negras", OK))

    # 5. Diferencia de potencia enorme entre luces directas.
    directas = [l for l in activas if not l.es_cielo and l.tipo != "sol"]
    if len(directas) > 1:
        fuerte = max(directas, key=lambda l: l.pasos)
        debil = min(directas, key=lambda l: l.pasos)
        if fuerte.pasos - debil.pasos > 8:
            avisos.append(Aviso("diferencia", AVISO, [debil.nodo], None, fuerte=fuerte.nombre, debil=debil.nombre,
                                pasos="{:.1f}".format(fuerte.pasos - debil.pasos).replace(".", ",")))

    # 6. Escala no uniforme en luces de área (estira el brillo; con Normalize no cambia la potencia).
    estiradas = [l for l in emisoras if l.tipo in ("area", "area_maya")
                 and max(l.escala) > 1e-6 and max(l.escala[:2]) / max(1e-6, min(l.escala[:2])) > 1.01]
    if estiradas:
        avisos.append(Aviso("escala", AVISO, [l.nodo for l in estiradas], None, luces=_nombres(estiradas)))
    else:
        avisos.append(Aviso("escala", OK))

    # 7. Luces de Maya sin caída cuadrática.
    sin_caida = [l for l in emisoras if l.tipo in ("punto", "foco", "area_maya", "volumen") and l.decay != 2]
    if sin_caida:
        avisos.append(Aviso("decay", MAL, [l.nodo for l in sin_caida], "decay_cuadratico", luces=_nombres(sin_caida)))

    # 8. HDRI sin .tx.
    sin_tx = [l for l in emisoras if l.es_cielo and l.hdri and not l.hdri.lower().endswith(".tx")
              and not os.path.exists(os.path.splitext(l.hdri)[0] + ".tx")]
    if sin_tx:
        avisos.append(Aviso("tx", AVISO, [l.nodo for l in sin_tx], "convertir_tx",
                            archivo=os.path.basename(sin_tx[0].hdri)))
    rotos = [l for l in emisoras if l.es_cielo and l.hdri and not os.path.exists(l.hdri)
             and not info.get("sin_disco")]
    if rotos:
        avisos.append(Aviso("hdri_roto", MAL, [l.nodo for l in rotos], None, archivo=os.path.basename(rotos[0].hdri)))

    # 9. Portales sin cielo, o cielo sin modo portal.
    portales = [l for l in luces if l.tipo == "portal"]
    cielos = [l for l in emisoras if l.es_cielo]
    if portales and not cielos:
        avisos.append(Aviso("portal_sin_cielo", MAL, [l.nodo for l in portales], "anadir_cielo"))
    elif portales and any(c.portal_modo == 0 for c in cielos):
        avisos.append(Aviso("portal_modo", AVISO, [c.nodo for c in cielos if c.portal_modo == 0], "portal_modo"))

    # 10. Bombillas atrapadas dentro de una pantalla que hace sombra.
    encerradas = info.get("encerradas", [])
    if encerradas:
        avisos.append(Aviso("encerrada", AVISO, [n for n, _ in encerradas], "sombra_pantalla",
                            luz=encerradas[0][0].split("|")[-1], malla=encerradas[0][1].split("|")[-1]))

    # 11. Muestras muy altas en una luz (lento).
    lentas = [l for l in emisoras if l.muestras > 4]
    if lentas:
        avisos.append(Aviso("muestras", AVISO, [l.nodo for l in lentas], "bajar_muestras", luces=_nombres(lentas)))

    # 12. Nombres de fábrica.
    sin_nombre = [l for l in emisoras if _NOMBRE_DE_FABRICA.match(l.nodo.split("|")[-1] or "")]
    if sin_nombre:
        avisos.append(Aviso("nombres", AVISO, [l.nodo for l in sin_nombre], "renombrar", luces=_nombres(sin_nombre)))
    else:
        avisos.append(Aviso("nombres", OK))

    # 13. Luces visibles en cámara sin querer (áreas que salen en la imagen como un rectángulo blanco).
    visibles = [l for l in activas if l.tipo == "area" and l.visible_camara]
    if visibles:
        avisos.append(Aviso("visible", AVISO, [l.nodo for l in visibles], "ocultar_camara", luces=_nombres(visibles)))
    return avisos


def pendientes(avisos):
    return [a for a in avisos if a.nivel != OK]
