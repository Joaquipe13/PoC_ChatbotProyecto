"""Tests de integración de evaluar_viabilidad_legal contra Postgres real
(Docker), con el catálogo real de SENASA (Fase 2) y las localidades
sintéticas de San Carlos Centro (Fase 3). Cubre los 3 resultados posibles
del dictamen: APTA, OBSERVADA y NO_EVALUABLE (ver plandefases.md, Fase 5).

Producto real usado: "Flyer 10 Ec" (banda II), con uso registrado real para
soja + Chinche De La Alfalfa: 160-180 cm3/ha (ver DECISIONES.md).
"""

from fitosanitarios.tools.evaluar_viabilidad_legal import (
    EvaluarViabilidadLegalArgs as Args,
)
from fitosanitarios.tools.evaluar_viabilidad_legal import (
    ProductoDeclarado,
    evaluar_viabilidad_legal_logica,
)

RADIO_BUSQUEDA_M = 2000
TOLERANCIA_PCT = 10.0

# Punto lejos de toda zona protegida de San Carlos Centro (>2 km de la
# escuela, >650 m del arroyo y de la zona urbana).
LON_LEJOS, LAT_LEJOS = -60.642, -32.912

# Punto a ~80 m de la Escuela N 12 (regla: 100 m terrestre).
LON_ESCUELA_80M, LAT_ESCUELA_80M = -60.6505, -32.92877865019107


def test_dictamen_apta_producto_registrado_dosis_ok_lejos_de_zonas(conexion, modelo_embeddings):
    args = Args(
        lat=LAT_LEJOS, lon=LON_LEJOS, tipo_aplicacion="terrestre",
        productos=[ProductoDeclarado(nombre="Flyer 10 Ec", dosis_valor=170, dosis_unidad="cm³/ha")],
        cultivo="Soja", adversidad="Chinche De La Alfalfa",
    )
    resultado = evaluar_viabilidad_legal_logica(
        args, conexion, modelo_embeddings, RADIO_BUSQUEDA_M, TOLERANCIA_PCT
    )
    assert resultado.estado == "ok"
    assert resultado.datos["dictamen"]["resultado"] == "APTA"
    assert resultado.datos["dictamen"]["observaciones"] == []
    assert len(resultado.citas) > 0  # cita el registro SENASA aunque cumpla


def test_dictamen_observada_por_distancia_insuficiente(conexion, modelo_embeddings):
    args = Args(
        lat=LAT_ESCUELA_80M, lon=LON_ESCUELA_80M, tipo_aplicacion="terrestre",
        productos=[ProductoDeclarado(nombre="Flyer 10 Ec", dosis_valor=170, dosis_unidad="cm³/ha")],
        cultivo="Soja", adversidad="Chinche De La Alfalfa",
    )
    resultado = evaluar_viabilidad_legal_logica(
        args, conexion, modelo_embeddings, RADIO_BUSQUEDA_M, TOLERANCIA_PCT
    )
    assert resultado.estado == "observado"
    dictamen = resultado.datos["dictamen"]
    assert dictamen["resultado"] == "OBSERVADA"
    descripciones = " ".join(o["descripcion"] for o in dictamen["observaciones"])
    assert "escuela" in descripciones.lower()
    assert any(c["norma"] == "ordenanza-914-2018" for c in dictamen["citas"])


def test_dictamen_observada_por_dosis_fuera_de_rango(conexion, modelo_embeddings):
    args = Args(
        lat=LAT_LEJOS, lon=LON_LEJOS, tipo_aplicacion="terrestre",
        # 500 cm3/ha está muy por encima del rango registrado (160-180).
        productos=[ProductoDeclarado(nombre="Flyer 10 Ec", dosis_valor=500, dosis_unidad="cm³/ha")],
        cultivo="Soja", adversidad="Chinche De La Alfalfa",
    )
    resultado = evaluar_viabilidad_legal_logica(
        args, conexion, modelo_embeddings, RADIO_BUSQUEDA_M, TOLERANCIA_PCT
    )
    dictamen = resultado.datos["dictamen"]
    assert dictamen["resultado"] == "OBSERVADA"
    descripciones = " ".join(o["descripcion"] for o in dictamen["observaciones"])
    assert "Dosis" in descripciones
    assert "por encima" in descripciones


def test_dictamen_no_evaluable_producto_sin_usos_registrados(conexion, modelo_embeddings):
    # "Glynomyl Dd" (reg. 39006) es un producto real del catálogo sin
    # ningún uso_registrado cargado (ver DECISIONES.md).
    args = Args(
        lat=LAT_LEJOS, lon=LON_LEJOS, tipo_aplicacion="terrestre",
        productos=[ProductoDeclarado(nombre="Glynomyl Dd", dosis_valor=2, dosis_unidad="L/ha")],
        cultivo="Soja",
    )
    resultado = evaluar_viabilidad_legal_logica(
        args, conexion, modelo_embeddings, RADIO_BUSQUEDA_M, TOLERANCIA_PCT
    )
    dictamen = resultado.datos["dictamen"]
    assert dictamen["resultado"] == "NO_EVALUABLE"
    assert dictamen["observaciones"] == []
    assert len(dictamen["chequeos_no_realizados"]) > 0


def test_jurisdiccion_no_cubierta_para_un_punto_lejano(conexion, modelo_embeddings):
    args = Args(
        lat=-50.0, lon=-70.0, tipo_aplicacion="terrestre",
        productos=[ProductoDeclarado(nombre="Flyer 10 Ec", dosis_valor=170, dosis_unidad="cm³/ha")],
        cultivo="Soja",
    )
    resultado = evaluar_viabilidad_legal_logica(
        args, conexion, modelo_embeddings, RADIO_BUSQUEDA_M, TOLERANCIA_PCT
    )
    assert resultado.estado == "no_resuelto"
    from fitosanitarios.dominio.motivos import MotivoNoResuelto

    assert resultado.motivo == MotivoNoResuelto.JURISDICCION_NO_CUBIERTA


def test_producto_no_encontrado(conexion, modelo_embeddings):
    args = Args(
        lat=LAT_LEJOS, lon=LON_LEJOS, tipo_aplicacion="terrestre",
        productos=[
            ProductoDeclarado(
                nombre="Xyzzyproductoquenoexisteenelregistro123",
                dosis_valor=2, dosis_unidad="L/ha",
            )
        ],
        cultivo="Soja",
    )
    resultado = evaluar_viabilidad_legal_logica(
        args, conexion, modelo_embeddings, RADIO_BUSQUEDA_M, TOLERANCIA_PCT
    )
    from fitosanitarios.dominio.motivos import MotivoNoResuelto

    assert resultado.estado == "no_resuelto"
    assert resultado.motivo == MotivoNoResuelto.PRODUCTO_NO_ENCONTRADO
