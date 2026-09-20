"""Integración contra Postgres real (Docker) con las localidades sintéticas de
`tests/fixtures/insumos/`. La tool ya no usa la ubicación del lote: identifica
la localidad por nombre e informa banda de la aplicación y distancias mínimas.

"Flyer 10 Ec" es un producto real del catálogo, banda II."""

from fitosanitarios.dominio.motivos import MotivoNoResuelto
from fitosanitarios.tools.evaluar_riesgo import EvaluarRiesgoArgs, evaluar_riesgo_logica

TOLERANCIA_PCT = 10.0


def _args(**kwargs) -> EvaluarRiesgoArgs:
    base = dict(
        localidad="San Carlos Centro", tipo_aplicacion="terrestre",
        productos=["Flyer 10 Ec"], cultivo="Soja", adversidad="Chinche De La Alfalfa",
        dosis_valor=170, dosis_unidad="cm³/ha",
    )
    return EvaluarRiesgoArgs(**{**base, **kwargs})


def test_riesgo_informa_banda_y_distancias_minimas_de_la_localidad(conexion, modelo_embeddings):
    resultado = evaluar_riesgo_logica(_args(), conexion, modelo_embeddings, TOLERANCIA_PCT)
    assert resultado.estado == "ok"
    assert resultado.datos["jurisdiccion_id"] == "san-carlos-centro"
    condiciones = resultado.datos["condiciones"]
    assert condiciones["banda"] == "II"
    distancias = {d["tipo_zona"]: d["distancia_min_m"] for d in condiciones["distancias_minimas"]}
    assert distancias["escuela"] == 100
    assert distancias["curso_agua"] == 50
    assert distancias["zona_urbana"] == 300  # regla provincial: aplica a toda localidad de Santa Fe
    assert len(resultado.citas) > 0


def test_riesgo_aplicacion_aerea_usa_la_regla_aerea(conexion, modelo_embeddings):
    resultado = evaluar_riesgo_logica(
        _args(tipo_aplicacion="aerea"), conexion, modelo_embeddings, TOLERANCIA_PCT
    )
    distancias = {
        d["tipo_zona"]: d["distancia_min_m"]
        for d in resultado.datos["condiciones"]["distancias_minimas"]
    }
    assert distancias["escuela"] == 200
    assert any("Aviso previo" in a for a in resultado.advertencias)


def test_riesgo_sin_localidad_pide_la_lista_de_cargadas(conexion, modelo_embeddings):
    resultado = evaluar_riesgo_logica(
        _args(localidad=None), conexion, modelo_embeddings, TOLERANCIA_PCT
    )
    assert resultado.estado == "faltan_datos"
    (faltante,) = resultado.faltantes
    assert faltante.campo == "localidad"
    assert "San Carlos Centro" in faltante.opciones


def test_riesgo_provincia_no_cargada(conexion, modelo_embeddings):
    resultado = evaluar_riesgo_logica(
        _args(localidad="Buenos Aires", provincia="Buenos Aires"), conexion, modelo_embeddings,
        TOLERANCIA_PCT,
    )
    assert resultado.estado == "no_resuelto"
    assert resultado.motivo == MotivoNoResuelto.JURISDICCION_NO_CUBIERTA


def test_riesgo_localidad_no_cargada_pide_la_provincia_y_no_la_supone(
    conexion, modelo_embeddings
):
    resultado = evaluar_riesgo_logica(
        _args(localidad="Rosario"), conexion, modelo_embeddings, TOLERANCIA_PCT
    )
    assert resultado.estado == "faltan_datos"
    assert resultado.faltantes[0].campo == "provincia"


def test_riesgo_localidad_sin_normativa_local_se_basa_en_la_provincial_y_lo_aclara(
    conexion, modelo_embeddings
):
    resultado = evaluar_riesgo_logica(
        _args(localidad="Rosario", provincia="santa-fe"), conexion, modelo_embeddings,
        TOLERANCIA_PCT,
    )
    assert resultado.estado == "ok"
    condiciones = resultado.datos["condiciones"]
    assert condiciones["sin_normativa_municipal"] is True
    assert any("No se cuenta con la normativa municipal de Rosario" in a
               for a in resultado.advertencias)
    distancias = {d["tipo_zona"]: d["distancia_min_m"] for d in condiciones["distancias_minimas"]}
    assert distancias == {"zona_urbana": 300}  # solo la regla provincial: sin ordenanza propia
