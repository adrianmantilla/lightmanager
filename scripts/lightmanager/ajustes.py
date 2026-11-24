"""Ajustes de LightManager en ``<carpeta de Maya>/lightmanager/ajustes.json``. No depende de Maya.

MantiTools los lee y escribe desde su ventana central con las mismas claves.
"""

import json
import os

DEFECTOS = {
    "carpeta_hdri": "",          # vacío = <prefs>/hdri
    "carpeta_esquemas": "",      # vacío = <prefs>/esquemas («Mis esquemas»)
    "carpeta_ies": "",           # perfiles propios además de los incluidos
    "ciudad": "madrid",
    "norte": 0.0,                # grados que hay que girar la escena para que su norte sea -Z
    "modo": "auto",              # auto | estudio | escena
    "agrupar_estudio": "papel",
    "agrupar_escena": "zona",
    "ver_arnold": True,          # línea con los valores reales de Arnold en la ficha
    "practicas_auto": True,      # encender las prácticas al ponerse el sol
    "repetir_cantidad": 3,
    "separacion_superficie": 0.02,  # en múltiplos del tamaño de la escena
}


class Ajustes(object):
    def __init__(self, carpeta):
        self.carpeta = carpeta
        self.ruta = os.path.join(carpeta, "ajustes.json")
        self._datos = dict(DEFECTOS)
        self.cargar()

    def cargar(self):
        try:
            with open(self.ruta, encoding="utf-8") as f:
                datos = json.load(f)
            if isinstance(datos, dict):
                self._datos.update({k: v for k, v in datos.items() if k in DEFECTOS})
        except (OSError, ValueError):
            pass

    def guardar(self):
        os.makedirs(self.carpeta, exist_ok=True)
        temporal = self.ruta + ".tmp"
        with open(temporal, "w", encoding="utf-8") as f:
            json.dump(self._datos, f, ensure_ascii=False, indent=1)
        os.replace(temporal, self.ruta)

    def __getitem__(self, clave):
        return self._datos.get(clave, DEFECTOS.get(clave))

    def __setitem__(self, clave, valor):
        if clave not in DEFECTOS:
            raise KeyError(clave)
        self._datos[clave] = valor
        self.guardar()

    # --- carpetas con su valor por defecto ------------------------------------------------
    def _carpeta_de(self, clave, sub):
        valor = self[clave]
        return valor if valor else os.path.join(self.carpeta, sub)

    @property
    def hdri(self):
        return self._carpeta_de("carpeta_hdri", "hdri")

    @property
    def esquemas(self):
        return self._carpeta_de("carpeta_esquemas", "esquemas")

    @property
    def ies_incluidos(self):
        return os.path.join(self.carpeta, "ies")

    @property
    def miniaturas(self):
        return os.path.join(self.carpeta, "miniaturas")
