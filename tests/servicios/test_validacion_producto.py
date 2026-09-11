"""Tests unitarios de la lógica de resolución de dosis ambigua por
adversidad (ver skill, "Dosis"): hallazgo real de la Fase 7, ver
DECISIONES.md."""

from fitosanitarios.servicios.validacion_producto import _dosis_sin_ambiguedad_de_adversidad


def _uso(cultivo, adversidad, valor_min, valor_max, unidad="cm³/ha"):
    return {
        "cultivo": cultivo, "adversidad": adversidad,
        "dosis": {"parseable": True, "valor_min": valor_min, "valor_max": valor_max,
                  "unidad": unidad},
    }


def test_adversidad_especificada_usa_el_primer_uso_filtrado():
    usos = [_uso("soja", "chinche de la alfalfa", 160, 180)]
    dosis = _dosis_sin_ambiguedad_de_adversidad(usos, adversidad="chinche de la alfalfa")
    assert dosis == {"parseable": True, "valor_min": 160, "valor_max": 180, "unidad": "cm³/ha"}


def test_sin_adversidad_y_un_solo_rango_no_es_ambiguo():
    usos = [
        _uso("soja", "chinche de la alfalfa", 160, 180),
        _uso("soja", "chinche verde", 160, 180),  # mismo rango, otra adversidad
    ]
    dosis = _dosis_sin_ambiguedad_de_adversidad(usos, adversidad=None)
    assert dosis is not None
    assert dosis["valor_min"] == 160


def test_sin_adversidad_y_rangos_distintos_es_ambiguo_devuelve_none():
    # Caso real encontrado probando evaluar_viabilidad_legal (Fase 7):
    # "Flyer 10 Ec" en soja tiene 160-180 para una adversidad y 25-35 para
    # otra. Sin especificar cuál, no hay un rango único para comparar.
    usos = [
        _uso("soja", "chinche de la alfalfa", 160, 180),
        _uso("soja", "oruga de las leguminosas", 25, 35),
    ]
    assert _dosis_sin_ambiguedad_de_adversidad(usos, adversidad=None) is None


def test_sin_usos_devuelve_none():
    assert _dosis_sin_ambiguedad_de_adversidad([], adversidad=None) is None
