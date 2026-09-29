"""Tests unitarios de la lógica de resolución de dosis ambigua por
adversidad (ver skill, "Dosis"): hallazgo real de la Fase 7, ver
DECISIONES.md."""

from fitosanitarios.servicios.validacion_producto import (
    _chequeo_sin_un_unico_rango,
    _dosis_sin_ambiguedad_de_adversidad,
)


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


# --- los usos del cultivo consultado ---


def test_los_usos_del_cultivo_son_solo_los_del_cultivo_y_la_adversidad_consultados(monkeypatch):
    """Bug real: se mostraba la dosis del primer uso registrado, de otro cultivo."""
    from fitosanitarios.datos.retrievers.catalogo import CandidatoProducto
    from fitosanitarios.servicios import validacion_producto as modulo

    usos = [
        _uso("Duraznero", "Pulgon Verde", 10, 10, "cm3/hl"),
        _uso("Soja", "Chinche De La Alfalfa", 160, 180),
        _uso("Soja", "Oruga", 25, 35),
        _uso("Manzanas", "Aranuela", 20, 30, "cm3/hl"),
    ]
    candidato = CandidatoProducto(
        id=1, numero_inscripcion="41881", marca="Flyer 10 Ec", banda_toxicologica="II",
        estado_producto="Activo", score=0.9, usos_registrados=usos,
    )
    monkeypatch.setattr(modulo, "buscar_productos_por_nombre", lambda *a, **k: [candidato])

    res = modulo.resolver_y_validar_producto(
        None, None, "Flyer 10 Ec", "soja", None, None, None, 10.0
    )
    assert [u["adversidad"] for u in res.usos_del_cultivo] == ["Chinche De La Alfalfa", "Oruga"]

    con_adversidad = modulo.resolver_y_validar_producto(
        None, None, "Flyer 10 Ec", "Soja", "oruga", None, None, 10.0
    )
    assert [u["adversidad"] for u in con_adversidad.usos_del_cultivo] == ["Oruga"]

    otro = modulo.resolver_y_validar_producto(
        None, None, "Flyer 10 Ec", "trigo", None, None, None, 10.0
    )
    assert otro.usos_del_cultivo == [] and otro.chequeo_producto.cultivo_autorizado is False


# --- dosis sin un único rango (plan del video, 27/09/2026: 500 cm3/ha de Flyer en soja,
# sin plaga, daba APTA porque la dosis no se comparaba ni se avisaba) ---

_FLYER_SOJA = [
    _uso("soja", "oruga de las leguminosas", 25, 35),
    _uso("soja", "trips del poroto", 150, 150),
    _uso("soja", "chinche de la alfalfa", 160, 180),
]


def test_fuera_de_todos_los_rangos_es_observacion_sea_cual_sea_la_plaga():
    chd = _chequeo_sin_un_unico_rango(_FLYER_SOJA, "soja", 500, "cm³/ha", 10)
    assert chd.comparable and not chd.cumple
    assert (chd.valor_min_registrado, chd.valor_max_registrado) == (25, 180)


def test_dentro_de_algun_rango_depende_de_la_plaga_y_no_se_verifica():
    chd = _chequeo_sin_un_unico_rango(_FLYER_SOJA, "soja", 170, "cm³/ha", 10)
    assert not chd.comparable
    assert "depende de la plaga" in chd.motivo_no_comparable


def test_entre_dos_rangos_tambien_depende_de_la_plaga():
    chd = _chequeo_sin_un_unico_rango(_FLYER_SOJA, "soja", 100, "cm³/ha", 10)
    assert not chd.comparable


def test_sin_ningun_rango_comparable_no_se_verifica_y_lo_dice():
    usos = [{"cultivo": "soja", "adversidad": None, "dosis": {"parseable": False}}]
    chd = _chequeo_sin_un_unico_rango(usos, "soja", 170, "cm³/ha", 10)
    assert not chd.comparable
    assert "no trae un rango" in chd.motivo_no_comparable
