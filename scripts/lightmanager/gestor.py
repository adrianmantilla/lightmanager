"""El cerebro de LightManager: todo lo que se puede hacer con las luces, sin depender de Maya.

El panel, los atajos, Radial y RenderDesk (por ``api``) pasan por aquí. Cada
operación se hace dentro de un bloque de deshacer y vuelve a leer las luces.
"""

import datetime
import math
import os
import uuid

from lightmanager import comprobaciones as chk
from lightmanager import escenarios as esc
from lightmanager import esquemas as esq
from lightmanager import geometria as geo
from lightmanager import ies
from lightmanager import nombres
from lightmanager import sol as solar
from lightmanager import unidades
from lightmanager import zonas as zn
from lightmanager.modelo import ZONA_GENERAL, activa

CLAVE_SOL = "lightmanager_sol"
CLAVE_MODO = "lightmanager_modo"

# Valores de una luz nueva por tipo: (pasos, kelvin, tamaño, perfil IES).
NUEVAS = {
    "area": (6.5, 5600, 1.0, ""),
    "sol": (3.0, 5600, 0.5, ""),
    "foco": (8.0, 3200, 0.05, ""),
    "punto": (6.0, 2700, 0.05, ""),
    "fotometrica": (0.0, 3000, 0.02, "downlight"),
    "cielo": (0.0, 6500, 1.0, ""),
}


class ErrorLightManager(Exception):
    """Error con un texto ya pensado para el usuario (clave de i18n en ``clave``)."""

    def __init__(self, clave, **valores):
        Exception.__init__(self, clave)
        self.clave = clave
        self.valores = valores


class Gestor(object):
    def __init__(self, servicios, ajustes):
        self.s = servicios
        self.ajustes = ajustes
        self.luces = []
        self.oyentes = []  # funciones a llamar cuando cambian las luces

    # --- lectura -----------------------------------------------------------------------
    def refrescar(self):
        self.luces = self.s.luces()
        return self.luces

    def avisar(self):
        for f in list(self.oyentes):
            try:
                f()
            except Exception:  # pragma: no cover - un oyente roto no para al resto
                pass

    def luz(self, nodo):
        for l in self.luces:
            if l.nodo == nodo:
                return l
        raise KeyError(nodo)

    def existe(self, nodo):
        return any(l.nodo == nodo for l in self.luces)

    def con_gemelas(self, nodos):
        """Los nodos más sus gemelas, sin repetir y en orden."""
        resultado = []
        for n in nodos:
            if not self.existe(n):
                continue
            l = self.luz(n)
            grupo = [x.nodo for x in self.luces if l.gemela and x.gemela == l.gemela] or [n]
            for g in grupo:
                if g not in resultado:
                    resultado.append(g)
        return resultado

    def modo(self):
        """«estudio» o «escena»: el guardado en la escena, el de los ajustes o el que propone la escena."""
        guardado = self.s.leer_dato(CLAVE_MODO)
        if guardado in ("estudio", "escena"):
            return guardado
        if self.ajustes["modo"] in ("estudio", "escena"):
            return self.ajustes["modo"]
        return self.modo_propuesto()

    def modo_propuesto(self):
        """Escena si hay zonas, portales, sol físico o muchas luces prácticas; si no, Estudio."""
        if self.s.zonas():
            return "escena"
        if any(l.tipo == "portal" for l in self.luces):
            return "escena"
        if self.estado_sol().get("activo"):
            return "escena"
        if sum(1 for l in self.luces if l.es_practica) >= 4:
            return "escena"
        return "estudio"

    def poner_modo(self, modo):
        self.s.escribir_dato(CLAVE_MODO, modo)

    # --- edición -----------------------------------------------------------------------
    def _aplicar_visibilidad(self):
        """La visibilidad real de cada luz: encendida y, si hay solos, solo ella."""
        for l in self.luces:
            v = activa(l, self.luces)
            if v != l.visible:
                self.s.escribir(l.nodo, {"visible": v})
                l.visible = v

    def cambiar(self, nodos, campo, valor, relativo=False):
        """Cambia ``campo`` en unas luces y sus gemelas. Con ``relativo`` suma ``valor`` (pasos, kelvin…)."""
        nodos = self.con_gemelas(nodos)
        if not nodos:
            return
        with self.s.bloque("LightManager: " + campo):
            for n in nodos:
                l = self.luz(n)
                nuevo = valor
                if relativo:
                    nuevo = getattr(l, campo) + valor
                if campo == "pasos":
                    nuevo = unidades.recortar_pasos(nuevo)
                elif campo == "kelvin":
                    nuevo = int(max(1000, min(15000, round(nuevo))))
                self.s.escribir(n, {campo: nuevo})
                setattr(l, campo, nuevo)
            if campo in ("encendida", "solo"):
                self._aplicar_visibilidad()
        self.avisar()

    def escribir_varios(self, nodo, campos, con_gemelas=True):
        """Varios campos de una vez (sin sumar)."""
        nodos = self.con_gemelas([nodo]) if con_gemelas else [nodo]
        with self.s.bloque("LightManager"):
            for n in nodos:
                self.s.escribir(n, campos)
                l = self.luz(n)
                for c, v in campos.items():
                    if hasattr(l, c):
                        setattr(l, c, v)
        self.avisar()

    def encender(self, nodos, valor=None):
        """Enciende o apaga. Sin ``valor``, alterna según la primera."""
        nodos = [n for n in nodos if self.existe(n)]
        if not nodos:
            return
        if valor is None:
            valor = not self.luz(nodos[0]).encendida
        self.cambiar(nodos, "encendida", bool(valor))

    def solo(self, nodos, valor=None):
        nodos = [n for n in nodos if self.existe(n)]
        if not nodos:
            return
        if valor is None:
            valor = not self.luz(nodos[0]).solo
        self.cambiar(nodos, "solo", bool(valor))

    def quitar_solos(self):
        self.cambiar([l.nodo for l in self.luces if l.solo], "solo", False)

    def encender_grupo(self, nodos):
        """Enciende todo el grupo si alguna está apagada; si están todas encendidas, las apaga."""
        nodos = [n for n in nodos if self.existe(n)]
        if not nodos:
            return
        valor = not all(self.luz(n).encendida for n in nodos)
        self.cambiar(nodos, "encendida", valor)

    def renombrar(self, nodo, nombre):
        with self.s.bloque("LightManager: renombrar"):
            nuevo = self.s.escribir(nodo, {"nombre": nombre}) or nodo
        if nuevo != nodo:
            todos = esc.decodificar(self.s.leer_dato(esc.CLAVE))
            esc.renombrar_nodo(todos, nodo, nuevo)
            self.s.escribir_dato(esc.CLAVE, esc.codificar(todos))
        self.refrescar()
        self.avisar()
        return nuevo

    def borrar(self, nodos):
        nodos = [n for n in nodos if self.existe(n)]
        if not nodos:
            return
        with self.s.bloque("LightManager: borrar"):
            self.s.borrar(nodos)
        self.refrescar()
        self.avisar()

    def duplicar(self, nodo, girar=30.0):
        """Duplica una luz y la gira ``girar`` grados alrededor de su objetivo (si tiene)."""
        l = self.luz(nodo)
        with self.s.bloque("LightManager: duplicar"):
            nuevo = self.s.duplicar(nodo)
            if l.objetivo and l.tipo not in ("cielo",):
                cam = self.s.camara_render()[1]
                az_cam = geo.azimut_de_camara(cam, l.objetivo) if cam else 0.0
                az, alt, dist = geo.orbita_de(l.posicion, l.objetivo, az_cam)
                pos = geo.posicion_orbita(l.objetivo, dist, az + girar, alt, az_cam)
                self.s.escribir(nuevo, {"posicion": pos, "rotacion": geo.mirar(pos, l.objetivo), "gemela": ""})
        self.refrescar()
        self.avisar()
        return nuevo

    # --- crear --------------------------------------------------------------------------
    def _nombre_libre(self, nombre):
        return nombres.siguiente(nombres.de_luz(nombre), [l.nodo.split("|")[-1] for l in self.luces])

    def crear(self, tipo, nombre=None, **campos):
        pasos, kelvin, tam, perfil = NUEVAS.get(tipo, NUEVAS["area"])
        datos = {"tipo": tipo, "pasos": pasos, "kelvin": kelvin, "tamano": tam, "papel": "", "grupo": ""}
        if perfil:
            datos["ies"] = self.ruta_ies(perfil)
        datos.update(campos)
        datos["nombre"] = self._nombre_libre(nombre or datos.get("nombre") or tipo.capitalize())
        with self.s.bloque("LightManager: crear"):
            nodo = self.s.crear(datos)
        self.refrescar()
        self.avisar()
        return nodo

    def ruta_ies(self, perfil):
        rutas = ies.asegurar(self.ajustes.ies_incluidos)
        return rutas.get(perfil, perfil)

    def objetivo_y_tamano(self):
        """Caja de la selección (sin luces) o de la escena."""
        luces = {l.nodo.split("|")[-1] for l in self.luces}
        sel = [n for n in self.s.seleccion() if n.split("|")[-1] not in luces]
        caja = self.s.caja(sel) if sel else None
        if caja is None:
            caja = self.s.caja_escena()
        if caja is None:
            caja = ((-0.5, 0.0, -0.5), (0.5, 1.0, 0.5))
        return caja

    def crear_en_orbita(self, tipo, azimut=-120.0, altura=30.0):
        """Luz nueva de estudio alrededor del objetivo, mirándolo."""
        caja = self.objetivo_y_tamano()
        objetivo, tam = geo.centro(caja), geo.tamano(caja)
        cam = self.s.camara_render()[1]
        az_cam = geo.azimut_de_camara(cam, objetivo) if cam else 0.0
        campos = {"objetivo": objetivo}
        if tipo == "sol":
            d = geo.direccion(azimut + az_cam, 50.0)
            campos["posicion"] = geo.suma(objetivo, geo.escala(d, tam * 3))
            campos["rotacion"] = geo.rotacion_para(geo.escala(d, -1.0))
        else:
            pos = geo.posicion_orbita(objetivo, tam * 2.5, azimut, altura, az_cam)
            campos["posicion"] = pos
            campos["rotacion"] = geo.mirar(pos, objetivo)
            if tipo == "area":
                campos["escala"] = (tam * 0.3,) * 3
            campos["pasos"] = NUEVAS.get(tipo, NUEVAS["area"])[0] + 2 * math.log2(tam)
        nombre = {"area": "Area", "sol": "Sol", "foco": "Foco", "punto": "Punto"}.get(tipo, "Luz")
        return self.crear(tipo, nombre, **campos)

    # --- esquemas ----------------------------------------------------------------------
    def esquemas(self):
        return esq.cargar([self.ajustes.esquemas])

    def aplicar_esquema(self, esquema, reemplazar=True, caja=None):
        """Aplica un esquema. Los de estudio crean luces; los de escena ajustan sol, cielo y prácticas."""
        if not esquema.es_estudio:
            return self._aplicar_esquema_escena(esquema)
        caja = caja or self.objetivo_y_tamano()
        cam = self.s.camara_render()[1]
        creadas = []
        with self.s.bloque("LightManager: esquema " + esquema.nombre):
            if reemplazar:
                viejas = [l.nodo for l in self.luces if l.esquema]
                if viejas:
                    self.s.borrar(viejas)
                    self.refrescar()
            existentes = [l.nodo.split("|")[-1] for l in self.luces]
            for d in esq.colocar(esquema, caja, cam):
                nombre = nombres.siguiente(nombres.de_luz(d["nombre"]), existentes)
                existentes.append(nombre)
                datos = dict(d)
                datos["nombre"] = nombre
                datos["esquema"] = esquema.id
                datos["zona"] = ""
                if d["tipo"] == "cielo":
                    ruta = self.hdri_del_pack(esquema.hdri) if esquema.hdri else ""
                    datos["hdri"] = ruta or ""
                    datos["visible_camara"] = True
                creadas.append(self.s.crear(datos))
        self.refrescar()
        self._aplicar_visibilidad()
        self.avisar()
        return creadas

    def hdri_del_pack(self, nombre):
        from lightmanager import hdri
        return hdri.buscar([self.ajustes.hdri], nombre) or ""

    def _aplicar_esquema_escena(self, esquema):
        d = esquema.datos
        hechas = []
        with self.s.bloque("LightManager: esquema " + esquema.nombre):
            cielo_d = d.get("cielo") or {}
            cielo = self.asegurar_cielo(cielo_d.get("tipo", "fisico"), self.hdri_del_pack(cielo_d.get("hdri", "")))
            self.s.escribir(cielo, {"pasos": float(cielo_d.get("pasos", 0.0)), "encendida": True})
            sol_d = d.get("sol")
            estado = self.estado_sol()
            if sol_d:
                fecha = self._fecha(estado)
                salida, puesta = solar.salida_y_puesta(estado["ciudad"], fecha)
                estado["hora"] = esq.hora_de(sol_d.get("hora", "mediodia"), salida, puesta)
                estado["pasos"] = float(sol_d.get("pasos", 3.0))
                estado["activo"] = True
                self.guardar_estado_sol(estado)
                self.asegurar_sol()
            else:
                estado["activo"] = True
                estado["sin_sol"] = True
                self.guardar_estado_sol(estado)
                for l in self.luces:
                    if l.tipo == "sol":
                        self.s.escribir(l.nodo, {"encendida": False})
            if d.get("portales"):
                hechas += self.crear_portales(dentro_de_bloque=True)
                self.s.escribir(cielo, {"portal_modo": 1})
            self.refrescar()
            practicas = [l.nodo for l in self.luces if l.es_practica]
            if practicas:
                for n in practicas:
                    self.s.escribir(n, {"encendida": bool(d.get("practicas"))})
            self.refrescar()
            self.aplicar_sol(dentro_de_bloque=True)
            self.refrescar()
            self._aplicar_visibilidad()
        self.poner_modo("escena")
        self.avisar()
        return hechas

    def guardar_como_esquema(self, nombre, descripcion=""):
        caja = self.objetivo_y_tamano()
        cam = self.s.camara_render()[1]
        luces = [l for l in self.luces if activa(l, self.luces) or l.encendida]
        datos = esq.desde_luces(luces, caja, cam, nombre, descripcion)
        return esq.guardar(datos, self.ajustes.esquemas)

    # --- estudio: órbita y apuntar --------------------------------------------------------
    def orbita(self, nodo):
        """(azimut, altura, distancia) de una luz respecto a su objetivo y la cámara, o None."""
        l = self.luz(nodo)
        if not l.objetivo or l.tipo in ("cielo", "portal"):
            return None
        cam = self.s.camara_render()[1]
        az_cam = geo.azimut_de_camara(cam, l.objetivo) if cam else 0.0
        if l.tipo == "sol":
            az, alt = geo.angulos(geo.escala(geo.direccion_de_rotacion(l.rotacion), -1.0))
            return geo.normalizar_angulo(az - az_cam), alt, geo.distancia(l.posicion, l.objetivo)
        return geo.orbita_de(l.posicion, l.objetivo, az_cam)

    def mover_orbita(self, nodo, azimut=None, altura=None, distancia=None):
        """Gira una luz alrededor de su objetivo manteniendo lo que no se pase."""
        actual = self.orbita(nodo)
        if actual is None:
            return
        l = self.luz(nodo)
        az, alt, dist = actual
        az = az if azimut is None else azimut
        alt = alt if altura is None else max(-89.0, min(89.0, altura))
        dist = dist if distancia is None else max(1e-3, distancia)
        cam = self.s.camara_render()[1]
        az_cam = geo.azimut_de_camara(cam, l.objetivo) if cam else 0.0
        pos = geo.posicion_orbita(l.objetivo, dist, az, alt, az_cam)
        self.escribir_varios(nodo, {"posicion": pos, "rotacion": geo.mirar(pos, l.objetivo)}, con_gemelas=False)

    def apuntar(self, nodo, modo, punto, normal, camara, objetivo=None):
        """Coloca una luz con un clic. ``modo``: «luz», «reflejo» o «sombra».

        Mantiene la distancia de la luz a lo que ilumina. En modo sombra ``punto``
        es donde debe caer la sombra y ``objetivo`` el centro del objeto que la hace
        (por defecto, el objetivo guardado en la luz).
        """
        l = self.luz(nodo)
        if l.tipo == "cielo":
            return self._apuntar_cielo(l, punto, normal, camara, modo)
        referencia = l.objetivo or punto
        dist = geo.distancia(l.posicion, referencia)
        if dist < 1e-3:
            dist = geo.tamano(self.objetivo_y_tamano()) * 2.5
        if modo == "sombra":
            obj = objetivo or l.objetivo
            if not obj:
                raise ErrorLightManager("err_sin_objetivo")
            pos, rot = geo.apuntar_sombra(punto, obj, dist)
            nuevo_objetivo = obj
        elif modo == "reflejo":
            if camara is None:
                raise ErrorLightManager("err_sin_camara")
            pos, rot = geo.apuntar_reflejo(punto, normal, camara, dist)
            nuevo_objetivo = punto
        else:
            pos, rot = geo.apuntar_luz(punto, normal, dist)
            nuevo_objetivo = punto
        if l.tipo == "sol":
            # El sol no tiene posición que importe: solo dirección.
            self.escribir_varios(nodo, {"rotacion": rot, "objetivo": nuevo_objetivo}, con_gemelas=False)
        else:
            self.escribir_varios(nodo, {"posicion": pos, "rotacion": rot, "objetivo": nuevo_objetivo},
                                 con_gemelas=False)
        return pos, rot

    def _apuntar_cielo(self, cielo, punto, normal, camara, modo):
        """Gira el cielo para que su sol (el del HDRI, en el giro 0) caiga donde se ha hecho clic."""
        if modo == "reflejo" and camara is not None:
            d = geo.reflejar(geo.resta(camara, punto), normal)
        else:
            d = geo.unitario(normal)
        az, _ = geo.angulos(d)
        sol_hdri = self.s.leer_dato("lightmanager_sol_hdri_" + os.path.basename(cielo.hdri or ""))
        base = float(sol_hdri) if sol_hdri else 0.0
        giro = (az - base) % 360.0
        self.escribir_varios(cielo.nodo, {"rotacion_cielo": giro}, con_gemelas=False)
        return None, None

    # --- escena: superficie, ventanas, lámparas, repetir -------------------------------------
    def colocar_en_superficie(self, punto, normal, tipo="fotometrica", nombre=None, perfil="downlight"):
        caja = self.s.caja_escena() or ((0, 0, 0), (1, 1, 1))
        sep = geo.tamano(caja) * float(self.ajustes["separacion_superficie"]) * 0.25
        pos, rot = geo.pegar_a_superficie(punto, normal, sep)
        campos = {"posicion": pos, "rotacion": rot, "objetivo": None}
        if tipo == "fotometrica":
            campos["ies"] = self.ruta_ies(perfil)
        zonas = self.s.zonas()
        zona = zn.zona_de(pos, zonas)
        campos["zona"] = zona
        base = nombre or ("{} {}".format("Downlight" if perfil == "downlight" else "Luz", zona.lower())
                          if zona != ZONA_GENERAL else "Luz")
        return self.crear(tipo, base, **campos)

    def crear_portales(self, dentro_de_bloque=False):
        """Un portal por cada hueco seleccionado (caras de ventana o un objeto ventana)."""
        huecos = self.s.ventanas_seleccionadas()
        if not huecos:
            if dentro_de_bloque:
                return []
            raise ErrorLightManager("err_sin_ventanas")
        creadas = []
        zonas = self.s.zonas()

        def hacer():
            existentes = [l.nodo.split("|")[-1] for l in self.luces]
            for centro, normal, ancho, alto, origen in huecos:
                # El portal mira hacia dentro: su -Z apunta al interior (contra la normal exterior).
                rot = geo.rotacion_para(geo.escala(normal, -1.0))
                zona = zn.zona_de(geo.suma(centro, geo.escala(normal, -0.05 * max(ancho, alto))), zonas)
                nombre = nombres.siguiente(nombres.de_luz("Ventana " + (zona if zona != ZONA_GENERAL else "")
                                                          .strip()), existentes)
                existentes.append(nombre)
                creadas.append(self.s.crear({"nombre": nombre, "tipo": "portal", "posicion": centro,
                                             "rotacion": rot, "escala": (ancho * 0.5, alto * 0.5, 1.0),
                                             "papel": "Ventanas", "zona": zona}))
            for c in [l for l in self.luces if l.es_cielo]:
                self.s.escribir(c.nodo, {"portal_modo": 1})

        if dentro_de_bloque:
            hacer()
        else:
            with self.s.bloque("LightManager: portales"):
                hacer()
            self.refrescar()
            self.avisar()
        return creadas

    def crear_lamparas(self, perfil="pantalla"):
        """Una luz dentro de cada objeto seleccionado (la pantalla de una lámpara, una farola…).

        La luz se pone en el centro del objeto y el objeto deja de hacerle sombra,
        para que no se quede atrapada dentro.
        """
        objetos = self.s.objetos_seleccionados()
        if not objetos:
            raise ErrorLightManager("err_sin_objetos")
        creadas = []
        zonas = self.s.zonas()
        with self.s.bloque("LightManager: lámparas"):
            existentes = [l.nodo.split("|")[-1] for l in self.luces]
            for objeto, caja in objetos:
                c = geo.centro(caja)
                corto = objeto.split("|")[-1]
                nombre = nombres.siguiente(nombres.de_luz("Bombilla " + nombres.sin_numero(corto)), existentes)
                existentes.append(nombre)
                tam = geo.tamano(caja)
                nodo = self.s.crear({"nombre": nombre, "tipo": "fotometrica", "posicion": c,
                                     "rotacion": (-90.0, 0.0, 0.0), "ies": self.ruta_ies(perfil), "pasos": 0.0,
                                     "kelvin": 2700, "tamano": tam * 0.05, "papel": "Prácticas",
                                     "zona": zn.zona_de(c, zonas)})
                self.s.poner_enlace(nodo, objeto, 1)
                creadas.append(nodo)
        self.refrescar()
        self._aplicar_visibilidad()
        self.avisar()
        return creadas

    def crear_luces_de_malla(self):
        objetos = self.s.objetos_seleccionados()
        if not objetos:
            raise ErrorLightManager("err_sin_objetos")
        creadas = []
        with self.s.bloque("LightManager: luz de malla"):
            for objeto, _ in objetos:
                creadas.append(self.s.crear_luz_de_malla(objeto, self._nombre_libre(
                    "Luz " + nombres.sin_numero(objeto.split("|")[-1]))))
        self.refrescar()
        self.avisar()
        return creadas

    def repetir(self, nodo, fin, cantidad=None):
        """Copias gemelas de ``nodo`` en línea hasta ``fin``. Devuelve los nodos nuevos."""
        cantidad = int(cantidad or self.ajustes["repetir_cantidad"])
        l = self.luz(nodo)
        gemela = l.gemela or uuid.uuid4().hex[:8]
        zonas = self.s.zonas()
        nuevas = []
        with self.s.bloque("LightManager: repetir"):
            if not l.gemela:
                self.s.escribir(nodo, {"gemela": gemela})
            base = nombres.sin_numero(l.nombre)
            existentes = [x.nodo.split("|")[-1] for x in self.luces]
            if l.nodo.split("|")[-1] == nombres.de_luz(base) and not l.nombre[-1:].isdigit():
                nuevo_nombre = nombres.siguiente(nombres.de_luz(base + " 1"), existentes)
                nodo = self.s.escribir(nodo, {"nombre": nuevo_nombre}) or nodo
                existentes.append(nuevo_nombre)
            for pos in geo.en_linea(l.posicion, fin, cantidad):
                n = self.s.duplicar(nodo)
                nombre = nombres.siguiente(nombres.de_luz(base + " 2"), existentes)
                existentes.append(nombre)
                n = self.s.escribir(n, {"nombre": nombre}) or n
                campos = {"posicion": pos, "gemela": gemela}
                if not l.zona.startswith("="):
                    campos["zona"] = zn.zona_de(pos, zonas)
                self.s.escribir(n, campos)
                nuevas.append(n)
        self.refrescar()
        self.avisar()
        return nuevas

    def separar_gemelas(self, nodos):
        self.cambiar_sin_gemelas(nodos, "gemela", "")

    def cambiar_sin_gemelas(self, nodos, campo, valor):
        with self.s.bloque("LightManager"):
            for n in nodos:
                self.s.escribir(n, {campo: valor})
        self.refrescar()
        self.avisar()

    # --- zonas ---------------------------------------------------------------------------
    def zonas(self):
        return self.s.zonas()

    def reasignar_zonas(self):
        """Pone a cada luz la zona en la que está (salvo las fijadas). Devuelve los cambios."""
        cambios = zn.reasignar(self.luces, self.s.zonas())
        if cambios:
            with self.s.bloque("LightManager: zonas"):
                for luz, _, nueva in cambios:
                    self.s.escribir(luz.nodo, {"zona": nueva})
            self.refrescar()
            self.avisar()
        return cambios

    def zona_desde_seleccion(self, nombre):
        objetos = self.s.objetos_seleccionados()
        if not objetos:
            raise ErrorLightManager("err_sin_objetos")
        caja = geo.caja_union([c for _, c in objetos])
        # El suelo de una habitación es plano: la zona sube hasta el techo de la escena.
        escena = self.s.caja_escena() or caja
        mn, mx = caja
        alto = max(mx[1], escena[1][1]) if (mx[1] - mn[1]) < 0.05 * geo.tamano(caja) else mx[1]
        caja = zn.caja_con_margen(((mn[0], mn[1], mn[2]), (mx[0], alto, mx[2])))
        return self.crear_zona(nombre, caja)

    def crear_zona(self, nombre, caja):
        with self.s.bloque("LightManager: zona"):
            nodo = self.s.crear_zona(nombre, caja)
        self.reasignar_zonas()
        self.avisar()
        return nodo

    def zonas_desde_outliner(self):
        """Una zona por cada grupo de primer nivel con geometría que aún no tenga zona."""
        existentes = {z.nombre for z in self.s.zonas()}
        creadas = []
        with self.s.bloque("LightManager: zonas del Outliner"):
            for z in zn.desde_grupos(self.s.grupos_outliner()):
                if z.nombre in existentes:
                    continue
                creadas.append(self.s.crear_zona(z.nombre, z.caja))
        self.reasignar_zonas()
        self.avisar()
        return creadas

    def borrar_zona(self, nodo):
        with self.s.bloque("LightManager: borrar zona"):
            self.s.borrar_zona(nodo)
        self.reasignar_zonas()
        self.avisar()

    def fijar_zona(self, nodos, zona):
        """Fija la zona a mano (``None`` vuelve a la automática)."""
        with self.s.bloque("LightManager: zona"):
            for n in nodos:
                self.s.escribir(n, {"zona": ("=" + zona) if zona else ""})
        self.refrescar()
        self.reasignar_zonas()
        self.avisar()

    # --- cielo y sol ------------------------------------------------------------------------
    def cielo(self):
        for l in self.luces:
            if l.es_cielo:
                return l
        return None

    def sol(self):
        """La luz del sol físico; si no hay, la primera luz de sol."""
        soles = [l for l in self.luces if l.tipo == "sol"]
        for l in soles:
            if l.esquema == "sol_fisico":
                return l
        return soles[0] if soles else None

    def asegurar_cielo(self, tipo="hdri", ruta_hdri=""):
        """El domo de la escena (lo crea si no hay) con un HDRI o un cielo físico. Devuelve el nodo."""
        c = self.cielo()
        if c is None:
            datos = {"nombre": self._nombre_libre("Cielo"), "tipo": "cielo", "pasos": 0.0, "papel": "Ambiente",
                     "grupo": "ambiente", "visible_camara": True}
            nodo = self.s.crear(datos)
            self.refrescar()
        else:
            nodo = c.nodo
        if tipo == "fisico":
            e = self.estado_sol()
            az, alt = self._sol_ahora(e)
            self.s.cielo_fisico(nodo, az, alt, float(self.ajustes["norte"]))
        else:
            self.s.quitar_cielo_fisico(nodo)
            if ruta_hdri:
                self.s.escribir(nodo, {"hdri": ruta_hdri})
        self.refrescar()
        return nodo

    def poner_hdri(self, ruta):
        with self.s.bloque("LightManager: HDRI"):
            nodo = self.asegurar_cielo("hdri", ruta)
        self.refrescar()
        self.avisar()
        return nodo

    def poner_cielo_fisico(self):
        with self.s.bloque("LightManager: cielo físico"):
            nodo = self.asegurar_cielo("fisico")
        self.refrescar()
        self.avisar()
        return nodo

    def sol_desde_hdri(self, azimut_hdri, altura_hdri, kelvin=5600):
        """Luz direccional alineada con el sol de la imagen (azimut medido en el giro 0 del HDRI)."""
        c = self.cielo()
        if c is None:
            raise ErrorLightManager("err_sin_cielo")
        az = azimut_hdri + c.rotacion_cielo
        d = geo.direccion(az, altura_hdri)
        caja = self.s.caja_escena() or ((0, 0, 0), (1, 1, 1))
        centro = geo.centro(caja)
        self.s.escribir_dato("lightmanager_sol_hdri_" + os.path.basename(c.hdri or ""), str(azimut_hdri))
        return self.crear("sol", "Sol del HDRI", posicion=geo.suma(centro, geo.escala(d, geo.tamano(caja) * 2)),
                          rotacion=geo.rotacion_para(geo.escala(d, -1.0)), kelvin=int(kelvin), papel="Clave",
                          grupo="sol", objetivo=centro)

    def estado_sol(self):
        import json
        texto = self.s.leer_dato(CLAVE_SOL)
        estado = {"ciudad": self.ajustes["ciudad"], "fecha": datetime.date.today().isoformat(), "hora": 13.0,
                  "pasos": 3.0, "activo": False}
        if texto:
            try:
                estado.update(json.loads(texto))
            except ValueError:
                pass
        return estado

    def guardar_estado_sol(self, estado):
        import json
        self.s.escribir_dato(CLAVE_SOL, json.dumps(estado))

    @staticmethod
    def _fecha(estado):
        try:
            return datetime.date.fromisoformat(estado.get("fecha", ""))
        except ValueError:
            return datetime.date.today()

    def _sol_ahora(self, estado):
        return solar.posicion_en(estado["ciudad"], self._fecha(estado), float(estado["hora"]))

    def asegurar_sol(self):
        """La luz direccional del sol físico (la crea si no hay). Devuelve el nodo."""
        s = self.sol()
        if s is not None:
            if s.esquema != "sol_fisico":
                self.s.escribir(s.nodo, {"esquema": "sol_fisico"})
            return s.nodo
        nodo = self.s.crear({"nombre": self._nombre_libre("Sol"), "tipo": "sol", "pasos": 3.0, "kelvin": 5600,
                             "tamano": 0.53, "papel": "Clave", "grupo": "sol", "esquema": "sol_fisico",
                             "zona": ZONA_GENERAL})
        self.refrescar()
        return nodo

    def poner_sol(self, **cambios):
        """Cambia hora, fecha, ciudad o pasos del sol y lo recoloca."""
        estado = self.estado_sol()
        estado.update(cambios)
        estado["activo"] = True
        if "hora" in cambios:
            estado.pop("sin_sol", None)
        self.guardar_estado_sol(estado)
        with self.s.bloque("LightManager: sol"):
            if not estado.get("sin_sol"):
                self.asegurar_sol()
            self.aplicar_sol(dentro_de_bloque=True)
        self.refrescar()
        self.avisar()

    def aplicar_sol(self, dentro_de_bloque=False):
        """Coloca el sol (y el cielo físico) según el estado guardado. Enciende prácticas al anochecer."""
        estado = self.estado_sol()
        if not estado.get("activo"):
            return None
        az, alt = self._sol_ahora(estado)
        norte = float(self.ajustes["norte"])
        cambios = []
        s = self.sol()
        if s is not None and not estado.get("sin_sol"):
            v = solar.vector_escena(az, alt, norte)
            caja = self.s.caja_escena() or ((0, 0, 0), (1, 1, 1))
            centro = geo.centro(caja)
            campos = {"rotacion": geo.rotacion_para(geo.escala(v, -1.0)),
                      "posicion": geo.suma(centro, geo.escala(v, geo.tamano(caja))),
                      "kelvin": solar.temperatura(alt), "usa_kelvin": True,
                      "pasos": solar.potencia(alt, float(estado.get("pasos", 3.0))),
                      "encendida": alt > -0.5}
            cambios.append((s.nodo, campos))
        c = self.cielo()
        if c is not None and c.cielo_fisico:
            self.s.cielo_fisico(c.nodo, az, alt, norte)
        if self.ajustes["practicas_auto"] and not estado.get("sin_sol"):
            noche = alt < 3.0
            for l in self.luces:
                if l.es_practica and l.encendida != noche:
                    cambios.append((l.nodo, {"encendida": noche}))

        def hacer():
            for nodo, campos in cambios:
                self.s.escribir(nodo, campos)

        if dentro_de_bloque:
            hacer()
        else:
            with self.s.bloque("LightManager: sol"):
                hacer()
        self.refrescar()
        self._aplicar_visibilidad()
        return az, alt

    # --- escenarios e instantáneas --------------------------------------------------------
    def escenarios(self):
        return esc.decodificar(self.s.leer_dato(esc.CLAVE))

    def _guardar_escenarios(self, lista):
        self.s.escribir_dato(esc.CLAVE, esc.codificar(lista))

    def guardar_escenario(self, nombre, descripcion=""):
        lista = self.escenarios()
        sol = self.estado_sol() if self.estado_sol().get("activo") else None
        foto = esc.foto(self.luces, sol, nombre, descripcion)
        foto["fecha"] = datetime.datetime.now().strftime("%d/%m %H:%M")
        lista = [e for e in lista if e.get("nombre") != nombre] + [foto]
        self._guardar_escenarios(lista)
        self.avisar()
        return foto

    def borrar_escenario(self, nombre):
        self._guardar_escenarios([e for e in self.escenarios() if e.get("nombre") != nombre])
        self.avisar()

    def recuperar_escenario(self, nombre, deshacer=True):
        for e in self.escenarios():
            if e.get("nombre") == nombre:
                return self._aplicar_escenario(e, deshacer)
        raise KeyError(nombre)

    def _aplicar_escenario(self, escenario, deshacer=True):
        cambios = esc.diferencias(escenario, self.luces)

        def hacer():
            for nodo, campos in cambios:
                self.s.escribir(nodo, campos)
            if escenario.get("sol"):
                self.guardar_estado_sol(escenario["sol"])

        if deshacer:
            with self.s.bloque("LightManager: escenario"):
                hacer()
        else:
            hacer()
        self.refrescar()
        self._aplicar_visibilidad()
        self.avisar()
        return cambios

    def comparar_inicio(self, nombre):
        """Muestra un escenario sin perder el estado actual (para «mantener pulsado»)."""
        actual = esc.foto(self.luces, self.estado_sol())
        self._comparando = actual
        self.recuperar_escenario(nombre, deshacer=False)

    def comparar_fin(self):
        actual = getattr(self, "_comparando", None)
        if actual is not None:
            self._comparando = None
            self._aplicar_escenario(actual, deshacer=False)

    # --- grupos de luz (AOV) -------------------------------------------------------------
    def grupos(self):
        return sorted({l.grupo for l in self.luces if l.grupo})

    def poner_grupo(self, nodos, grupo):
        limpio = nombres.limpio(grupo).lower() if grupo else ""
        self.cambiar(nodos, "grupo", limpio)
        return limpio

    def crear_aovs(self):
        with self.s.bloque("LightManager: AOV"):
            return self.s.crear_aovs_grupos(self.grupos())

    def llevar_mezcla(self, mezcla):
        """Pasa a las luces una mezcla hecha sobre el render: {grupo: pasos que se suman}."""
        nodos_por_grupo = {}
        for l in self.luces:
            if l.grupo in mezcla:
                nodos_por_grupo.setdefault(l.grupo, []).append(l.nodo)
        with self.s.bloque("LightManager: mezcla"):
            for grupo, nodos in nodos_por_grupo.items():
                delta = float(mezcla[grupo])
                if abs(delta) > 1e-6:
                    for n in nodos:
                        l = self.luz(n)
                        nuevo = unidades.recortar_pasos(l.pasos + delta)
                        self.s.escribir(n, {"pasos": nuevo})
                        l.pasos = nuevo
        self.avisar()

    # --- enlaces --------------------------------------------------------------------------
    def objetos_enlazables(self):
        return self.s.objetos_enlazables()

    def estado_enlace(self, luz, objeto):
        return self.s.estado_enlace(luz, objeto)

    def poner_enlace(self, luces, objetos, estado):
        with self.s.bloque("LightManager: enlaces"):
            for l in self.con_gemelas(luces):
                for o in objetos:
                    self.s.poner_enlace(l, o, estado)
        self.avisar()

    def siguiente_estado_enlace(self, luz, objeto):
        """Al pulsar una casilla: 2 -> 1 -> 0 -> 2."""
        nuevo = (self.s.estado_enlace(luz, objeto) + 2) % 3
        self.poner_enlace([luz], [objeto], nuevo)
        return nuevo

    # --- comprobaciones ----------------------------------------------------------------------
    def comprobar(self):
        return chk.revisar(self.luces, self.s.info_comprobaciones(self.luces))

    def arreglar(self, aviso):
        a = aviso.arreglo
        with self.s.bloque("LightManager: arreglar"):
            if a == "quitar_solo":
                for l in self.luces:
                    if l.solo:
                        self.s.escribir(l.nodo, {"solo": False})
            elif a == "encender_todas":
                for l in self.luces:
                    if not l.encendida:
                        self.s.escribir(l.nodo, {"encendida": True})
            elif a == "anadir_cielo":
                nodo = self.asegurar_cielo("hdri", self.hdri_del_pack("studio_small_09"))
                self.s.escribir(nodo, {"pasos": -1.0 if not any(l.tipo == "portal" for l in self.luces) else 0.0})
            elif a == "decay_cuadratico":
                for n in aviso.nodos:
                    self.s.escribir(n, {"decay": 2})
            elif a == "convertir_tx":
                for n in aviso.nodos:
                    l = self.luz(n)
                    nueva = self.s.convertir_tx(l.hdri)
                    if nueva:
                        self.s.escribir(n, {"hdri": nueva})
            elif a == "portal_modo":
                for n in aviso.nodos:
                    self.s.escribir(n, {"portal_modo": 1})
            elif a == "sombra_pantalla":
                for nodo, malla in self.s.info_comprobaciones(self.luces).get("encerradas", []):
                    self.s.poner_enlace(nodo, malla, 1)
            elif a == "bajar_muestras":
                for n in aviso.nodos:
                    self.s.escribir(n, {"muestras": 1})
            elif a == "renombrar":
                self._renombrar_por_papel(aviso.nodos)
            elif a == "ocultar_camara":
                for n in aviso.nodos:
                    self.s.escribir(n, {"visible_camara": False})
            elif a == "anadir_esquema":
                pass
        if a == "anadir_esquema":
            self.aplicar_esquema(esq.buscar(self.esquemas(), "tres_puntos"))
        self.refrescar()
        self._aplicar_visibilidad()
        self.avisar()

    def _renombrar_por_papel(self, nodos):
        existentes = [l.nodo.split("|")[-1] for l in self.luces]
        for n in nodos:
            l = self.luz(n)
            from lightmanager.i18n import t
            base = l.papel or t(l.texto_tipo)
            nombre = nombres.siguiente(nombres.de_luz(base), existentes)
            existentes.append(nombre)
            self.s.escribir(n, {"nombre": nombre})
