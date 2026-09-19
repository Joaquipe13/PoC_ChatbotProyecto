"""Tests de integración de evaluar_viabilidad_legal contra Postgres real
(Docker), con el catálogo real de SENASA (Fase 2) y las localidades
sintéticas de San Carlos Centro (Fase 3). Cubre los 3 resultados posibles
del dictamen: APTA, OBSERVADA y NO_EVALUABLE (ver plandefases.md, Fase 5).

El dictamen ya no compara contra la ubicación del lote: la localidad se
indica por nombre y la distancia mínima a zonas protegidas se informa como
condición de aplicación, sin cambiar el resultado (ver DECISIONES.md).

Producto real usado: "Flyer 10 Ec" (banda II), con uso registrado real para
soja + Chinche De La Alfalfa: 160-180 cm3/ha (ver DECISIONES.md).
"""

from fitosanitarios.dominio.motivos import MotivoNoResuelto
from fitosanitarios.tools.evaluar_viabilidad_legal import (
    EvaluarViabilidadLegalArgs as Args,
)
from fitosanitarios.tools.evaluar_viabilidad_legal import (
    ProductoDeclarado,
    evaluar_viabilidad_legal_logica,
)

TOLERANCIA_PCT = 10.0
LOCALIDAD = "San Carlos Centro"


def test_dictamen_apta_producto_registrado_dosis_ok(conexion, modelo_embeddings):
    args = Args(
        localidad=LOCALIDAD, tipo_aplicacion="terrestre",
        productos=[ProductoDeclarado(nombre="Flyer 10 Ec", dosis_valor=170, dosis_unidad="cm³/ha")],
        cultivo="Soja", adversidad="Chinche De La Alfalfa",
    )
    resultado = evaluar_viabilidad_legal_logica(args, conexion, modelo_embeddings, TOLERANCIA_PCT)
    assert resultado.estado == "ok"
    assert resultado.datos["dictamen"]["resultado"] == "APTA"
    assert resultado.datos["dictamen"]["observaciones"] == []
    assert len(resultado.citas) > 0  # cita el registro SENASA y la norma de distancia


def test_dictamen_informa_banda_y_distancias_minimas(conexion, modelo_embeddings):
    args = Args(
        localidad=LOCALIDAD, tipo_aplicacion="terrestre",
        productos=[ProductoDeclarado(nombre="Flyer 10 Ec", dosis_valor=170, dosis_unidad="cm³/ha")],
        cultivo="Soja", adversidad="Chinche De La Alfalfa",
    )
    resultado = evaluar_viabilidad_legal_logica(args, conexion, modelo_embeddings, TOLERANCIA_PCT)
    condiciones = resultado.datos["dictamen"]["condiciones"]
    assert condiciones["banda"] == "II"
    distancias = {d["tipo_zona"]: d["distancia_min_m"] for d in condiciones["distancias_minimas"]}
    assert distancias["escuela"] == 100
    assert any(c["norma"] == "ordenanza-914-2018" for c in resultado.datos["dictamen"]["citas"])


def test_dictamen_observada_por_dosis_fuera_de_rango(conexion, modelo_embeddings):
    args = Args(
        localidad=LOCALIDAD, tipo_aplicacion="terrestre",
        # 500 cm3/ha está muy por encima del rango registrado (160-180).
        productos=[ProductoDeclarado(nombre="Flyer 10 Ec", dosis_valor=500, dosis_unidad="cm³/ha")],
        cultivo="Soja", adversidad="Chinche De La Alfalfa",
    )
    resultado = evaluar_viabilidad_legal_logica(args, conexion, modelo_embeddings, TOLERANCIA_PCT)
    dictamen = resultado.datos["dictamen"]
    assert dictamen["resultado"] == "OBSERVADA"
    descripciones = " ".join(o["descripcion"] for o in dictamen["observaciones"])
    assert "Dosis" in descripciones
    assert "por encima" in descripciones


def test_dictamen_no_evaluable_producto_sin_usos_registrados(conexion, modelo_embeddings):
    # "Glynomyl Dd" (reg. 39006) es un producto real del catálogo sin
    # ningún uso_registrado cargado (ver DECISIONES.md).
    args = Args(
        localidad=LOCALIDAD, tipo_aplicacion="terrestre",
        productos=[ProductoDeclarado(nombre="Glynomyl Dd", dosis_valor=2, dosis_unidad="L/ha")],
        cultivo="Soja",
    )
    resultado = evaluar_viabilidad_legal_logica(args, conexion, modelo_embeddings, TOLERANCIA_PCT)
    dictamen = resultado.datos["dictamen"]
    assert dictamen["resultado"] == "NO_EVALUABLE"
    assert dictamen["observaciones"] == []
    assert len(dictamen["chequeos_no_realizados"]) > 0


def test_sin_localidad_pide_la_lista_de_cargadas(conexion, modelo_embeddings):
    args = Args(
        tipo_aplicacion="terrestre",
        productos=[ProductoDeclarado(nombre="Flyer 10 Ec", dosis_valor=170, dosis_unidad="cm³/ha")],
        cultivo="Soja",
    )
    resultado = evaluar_viabilidad_legal_logica(args, conexion, modelo_embeddings, TOLERANCIA_PCT)
    assert resultado.estado == "faltan_datos"
    assert resultado.faltantes[0].campo == "localidad"
    assert LOCALIDAD in resultado.faltantes[0].opciones


def test_localidad_no_cargada(conexion, modelo_embeddings):
    args = Args(
        localidad="Buenos Aires", tipo_aplicacion="terrestre",
        productos=[ProductoDeclarado(nombre="Flyer 10 Ec", dosis_valor=170, dosis_unidad="cm³/ha")],
        cultivo="Soja",
    )
    resultado = evaluar_viabilidad_legal_logica(args, conexion, modelo_embeddings, TOLERANCIA_PCT)
    assert resultado.estado == "no_resuelto"
    assert resultado.motivo == MotivoNoResuelto.JURISDICCION_NO_CUBIERTA


def test_producto_no_encontrado(conexion, modelo_embeddings):
    args = Args(
        localidad=LOCALIDAD, tipo_aplicacion="terrestre",
        productos=[
            ProductoDeclarado(
                nombre="Xyzzyproductoquenoexisteenelregistro123",
                dosis_valor=2, dosis_unidad="L/ha",
            )
        ],
        cultivo="Soja",
    )
    resultado = evaluar_viabilidad_legal_logica(args, conexion, modelo_embeddings, TOLERANCIA_PCT)
    assert resultado.estado == "no_resuelto"
    assert resultado.motivo == MotivoNoResuelto.PRODUCTO_NO_ENCONTRADO
