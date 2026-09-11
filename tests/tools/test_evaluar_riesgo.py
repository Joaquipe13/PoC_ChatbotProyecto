from fitosanitarios.tools.evaluar_riesgo import EvaluarRiesgoArgs, evaluar_riesgo_logica

RADIO_BUSQUEDA_M = 2000
TOLERANCIA_PCT = 10.0

LON_LEJOS, LAT_LEJOS = -60.642, -32.912
LON_ESCUELA_80M, LAT_ESCUELA_80M = -60.6505, -32.92877865019107


def test_riesgo_ok_lejos_de_zonas_protegidas(conexion, modelo_embeddings):
    args = EvaluarRiesgoArgs(
        lat=LAT_LEJOS, lon=LON_LEJOS, tipo_aplicacion="terrestre",
        productos=["Flyer 10 Ec"], cultivo="Soja", adversidad="Chinche De La Alfalfa",
        dosis_valor=170, dosis_unidad="cm³/ha",
    )
    resultado = evaluar_riesgo_logica(
        args, conexion, modelo_embeddings, RADIO_BUSQUEDA_M, TOLERANCIA_PCT
    )
    assert resultado.estado == "ok"
    assert resultado.datos["jurisdiccion_id"] == "san-carlos-centro"


def test_riesgo_observado_por_distancia_a_escuela(conexion, modelo_embeddings):
    args = EvaluarRiesgoArgs(
        lat=LAT_ESCUELA_80M, lon=LON_ESCUELA_80M, tipo_aplicacion="terrestre",
        productos=["Flyer 10 Ec"], cultivo="Soja", adversidad="Chinche De La Alfalfa",
        dosis_valor=170, dosis_unidad="cm³/ha",
    )
    resultado = evaluar_riesgo_logica(
        args, conexion, modelo_embeddings, RADIO_BUSQUEDA_M, TOLERANCIA_PCT
    )
    assert resultado.estado == "observado"
    # Con radio 2000 m también entra la escuela de colonia-vecina (a más de
    # 100 m, cumple) -- las reglas de la jurisdicción del lote (San Carlos)
    # se aplican a toda zona protegida en el radio, sea de la localidad que
    # sea (ver skill, "Geo"). Hay que buscar puntualmente la escuela cercana.
    zona_escuela = next(
        z for z in resultado.datos["zonas_evaluadas"] if z["tipo"] == "escuela" and not z["cumple"]
    )
    assert zona_escuela["distancia_m"] < 100


def test_riesgo_jurisdiccion_no_cubierta(conexion, modelo_embeddings):
    args = EvaluarRiesgoArgs(
        lat=-50.0, lon=-70.0, tipo_aplicacion="terrestre",
        productos=["Flyer 10 Ec"], cultivo="Soja", dosis_valor=170, dosis_unidad="cm³/ha",
    )
    resultado = evaluar_riesgo_logica(
        args, conexion, modelo_embeddings, RADIO_BUSQUEDA_M, TOLERANCIA_PCT
    )
    assert resultado.estado == "no_resuelto"

    from fitosanitarios.dominio.motivos import MotivoNoResuelto

    assert resultado.motivo == MotivoNoResuelto.JURISDICCION_NO_CUBIERTA
