"""Plantilla de `listar_limitaciones`, en particular la convención de
`DISTANCIA_SIN_LIMITE_M` (ver DECISIONES.md, "Localidades y normas sin
fuente oficial")."""

from fitosanitarios.dominio.modelos import ResultadoTool
from fitosanitarios.servicios.reglas import DISTANCIA_SIN_LIMITE_M
from fitosanitarios.tools.listar_limitaciones.mensajes import plantilla_limitaciones


def _regla(distancia, tipo_aplicacion="terrestre", bandas=None):
    return {
        "tipo_zona": "zona_urbana", "tipo_aplicacion": tipo_aplicacion,
        "bandas": bandas or ["Ia", "Ib"], "distancia_min_m": distancia,
        "norma": "ordenanza-1174-2019", "articulo": None, "jurisdiccion_id": "sastre",
        "observaciones": None, "condiciones": None, "extraida_de_pdf": False,
    }


def test_distancia_sin_limite_se_muestra_como_toda_la_jurisdiccion():
    resultado = ResultadoTool(
        estado="ok",
        datos={
            "localidad": "Sastre", "filtros": {},
            "prohibiciones": [_regla(DISTANCIA_SIN_LIMITE_M)], "condicionales": [],
        },
    )
    texto = plantilla_limitaciones(None, [resultado])
    assert "no se puede aplicar en toda la jurisdicción" in texto
    assert str(int(DISTANCIA_SIN_LIMITE_M)) not in texto


def test_distancia_normal_se_muestra_en_metros():
    resultado = ResultadoTool(
        estado="ok",
        datos={
            "localidad": "Sastre", "filtros": {},
            "prohibiciones": [_regla(1000)], "condicionales": [],
        },
    )
    texto = plantilla_limitaciones(None, [resultado])
    assert "a menos de 1000 m no se puede aplicar" in texto
