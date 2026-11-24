"""Todas las claves de texto que usa el código existen en es.json (y no sobra ninguna)."""

import glob
import json
import os
import re
import unittest

from lightmanager import ies, unidades, hdri
from lightmanager.modelo import PAPELES, TIPOS

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARPETA = os.path.join(RAIZ, "scripts", "lightmanager")


def _es():
    with open(os.path.join(CARPETA, "i18n", "es.json"), encoding="utf-8") as f:
        return json.load(f)


def claves_usadas():
    usadas = set()
    for ruta in glob.glob(os.path.join(CARPETA, "*.py")):
        with open(ruta, encoding="utf-8") as f:
            texto = f.read()
        usadas |= set(re.findall(r'\bt\(\s*"([a-zA-Z0-9_]+)"', texto))
        usadas |= set(re.findall(r'ErrorLightManager\("([a-z_]+)"', texto))
        usadas |= set(re.findall(r'aviso="([a-z_]+)"', texto))
        usadas |= set(re.findall(r'\("(cmd_[a-z_]+)", "', texto))
    # Claves que se forman al vuelo.
    usadas |= {v[0] for v in TIPOS.values()} | {"tipo_otra"}
    usadas |= {c for c, _ in unidades.TEMPERATURAS} | {c for _, c in hdri.PACK_INICIAL}
    usadas |= {"ies_" + c for c in ies.ORDEN} | {"papel_" + p for p in PAPELES + ("",)}
    for p in ("papel", "zona", "tipo", "grupo"):
        usadas.add("agrupar_" + p)
    for m in ("luz", "reflejo", "sombra"):
        usadas |= {"apuntar_" + m, "apuntar_{}_ayuda".format(m), "clic_apuntar_" + m}
    for f in ("estudio", "interior", "exterior", "mios"):
        usadas |= {"familia_" + f, "sin_esquemas_" + f}
    usadas |= {"f_tamano_escala", "f_tamano_angulo", "f_tamano_radio", "enlace_0", "enlace_1", "enlace_2"}
    return {u for u in usadas if not u.endswith("_")}


def claves_de_comprobaciones():
    from lightmanager import comprobaciones
    with open(comprobaciones.__file__, encoding="utf-8") as f:
        texto = f.read()
    claves = set()
    for clave, nivel in re.findall(r'Aviso\("([a-z_]+)", (OK|MAL|AVISO)', texto):
        sufijo = "ok" if nivel == "OK" else "mal"
        claves |= {"chk_{}_{}".format(clave, sufijo), "chk_{}_{}_det".format(clave, sufijo)}
    for arreglo in re.findall(r'"([a-z_]+)"\)\)?$', texto, re.M):
        pass
    claves |= {"arr_" + a for a in re.findall(r'arreglo="([a-z_]+)"', texto)}
    claves |= {"arr_" + a for a in re.findall(r'\], "([a-z_]+)"', texto)}
    return claves


class Textos(unittest.TestCase):
    def test_no_falta_ninguna(self):
        es = _es()
        faltan = sorted((claves_usadas() | claves_de_comprobaciones()) - set(es))
        self.assertEqual(faltan, [])

    def test_sin_referencias_a_un_aula(self):
        prohibidas = re.compile(r"profesor|alumn|\baula\b|estudiante", re.I)
        for clave, texto in _es().items():
            self.assertIsNone(prohibidas.search(texto), clave)

    def test_formato(self):
        for clave, texto in _es().items():
            texto.format(**{k: 1 for k in re.findall(r"\{(\w+)\}", texto)})


if __name__ == "__main__":
    unittest.main()
