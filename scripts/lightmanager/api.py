"""API sin interfaz para otras herramientas (RenderDesk, Radial, scripts propios).

Todo funciona sin abrir el panel. Ejemplo desde RenderDesk::

    from lightmanager import api
    for luz in api.listar():
        print(luz["nombre"], luz["pasos"], luz["grupo"])
    api.potencia("LM_Clave", 1, relativo=True)   # un paso más
    api.solo("LM_Clave")
    avisos = api.comprobar()                     # para su pestaña Comprobar
    api.llevar_mezcla({"clave": -0.5, "relleno": 1.0})

Las luces se identifican por el nombre de su transform. Las funciones devuelven
datos sencillos (dicts, listas, textos) para no atar a nadie a las clases internas.
"""

from lightmanager.modelo import activa

_gestor = None


def gestor():
    """El ``Gestor`` compartido con el panel (se crea al primer uso)."""
    try:
        from lightmanager import interfaz_maya
        g = interfaz_maya.gestor()
    except ImportError:  # fuera de Maya: el que se haya puesto con ``usar``
        g = _gestor
    if g is None:
        raise RuntimeError("LightManager no está cargado")
    return g


def usar(g):
    """Para pruebas o uso fuera de Maya: fija el gestor que usa la API."""
    global _gestor
    _gestor = g


def _datos(luz, luces):
    from lightmanager.i18n import t
    return {
        "nodo": luz.nodo,
        "nombre": luz.nombre,
        "tipo": luz.tipo,
        "tipo_texto": t(luz.texto_tipo),
        "encendida": luz.encendida,
        "solo": luz.solo,
        "activa": activa(luz, luces),
        "pasos": luz.pasos,
        "kelvin": luz.kelvin,
        "color": luz.color,
        "grupo": luz.grupo,
        "papel": luz.papel,
        "zona": luz.zona.lstrip("="),
        "gemela": luz.gemela,
        "muestras": luz.muestras,
    }


def listar():
    """Todas las luces, como dicts."""
    g = gestor()
    g.refrescar()
    return [_datos(l, g.luces) for l in g.luces]


def encender(nodos, valor=True):
    g = gestor()
    g.refrescar()
    g.encender(_lista(nodos), valor)


def apagar(nodos):
    encender(nodos, False)


def alternar(nodos):
    g = gestor()
    g.refrescar()
    g.encender(_lista(nodos), None)


def solo(nodos, valor=True):
    g = gestor()
    g.refrescar()
    g.solo(_lista(nodos), valor)


def quitar_solos():
    g = gestor()
    g.refrescar()
    g.quitar_solos()


def potencia(nodos, pasos, relativo=False):
    """Pone ``pasos`` de exposición (o los suma con ``relativo``). Las gemelas cambian también."""
    g = gestor()
    g.refrescar()
    g.cambiar(_lista(nodos), "pasos", float(pasos), relativo=relativo)


def grupos():
    """Nombres de los grupos de luz (los AOV de grupos que usa el mezclador)."""
    g = gestor()
    g.refrescar()
    return g.grupos()


def luces_de_grupo(grupo):
    g = gestor()
    g.refrescar()
    return [l.nodo for l in g.luces if l.grupo == grupo]


def crear_aovs():
    """Crea los AOV de grupos de luz. Devuelve sus nombres."""
    g = gestor()
    g.refrescar()
    return g.crear_aovs()


def llevar_mezcla(mezcla):
    """Aplica a las luces una mezcla hecha sobre el render: {grupo: pasos que se suman}."""
    g = gestor()
    g.refrescar()
    g.llevar_mezcla(mezcla)


def comprobar():
    """Avisos de iluminación como dicts: clave, nivel (ok/aviso/mal), texto, detalle, nodos y arreglo."""
    from lightmanager.i18n import t
    g = gestor()
    g.refrescar()
    resultado = []
    for a in g.comprobar():
        d = a.como_dict()
        d["texto"] = t(a.texto, **a.valores)
        d["detalle"] = t(a.detalle, **a.valores)
        resultado.append(d)
    return resultado


def arreglar(clave):
    """Arregla el aviso ``clave`` (la de ``comprobar``). True si había algo que arreglar."""
    g = gestor()
    g.refrescar()
    for a in g.comprobar():
        if a.clave == clave and a.arreglo:
            g.arreglar(a)
            return True
    return False


def resumen():
    """Cuántas luces hay, cuántas cuentan, si hay cielo, sol o portales y qué grupos: para sugerir presets."""
    g = gestor()
    g.refrescar()
    luces = g.luces
    return {
        "luces": len([l for l in luces if l.emite]),
        "activas": len([l for l in luces if l.emite and activa(l, luces)]),
        "cielo": any(l.es_cielo for l in luces),
        "sol": any(l.tipo == "sol" and activa(l, luces) for l in luces),
        "portales": any(l.tipo == "portal" for l in luces),
        "practicas": len([l for l in luces if l.es_practica]),
        "grupos": g.grupos(),
        "modo": g.modo(),
    }


def abrir_panel():
    from lightmanager import interfaz_maya
    interfaz_maya.mostrar()


def _lista(nodos):
    return [nodos] if isinstance(nodos, str) else list(nodos)
