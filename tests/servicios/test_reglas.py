from fitosanitarios.servicios.reglas import (
    ReglaCandidata,
    evaluar_distancia_zona,
    excepciones_aplicables,
)


def _regla_san_carlos_escuela() -> ReglaCandidata:
    # Regla real de la fixture san-carlos-centro (reglas.csv)
    return ReglaCandidata(
        tipo_zona="escuela", tipo_aplicacion="terrestre", bandas=["todas"],
        distancia_min_m=100, norma="ordenanza-914-2018", articulo="8",
        jurisdiccion_id="san-carlos-centro",
    )


def test_lote_a_80m_de_escuela_con_regla_de_100m_no_cumple_con_cita():
    # Caso citado literalmente en plandefases.md, Fase 5.
    chequeo = evaluar_distancia_zona(
        zona_tipo="escuela", zona_nombre="Escuela N 12", distancia_real_m=80.0,
        reglas=[_regla_san_carlos_escuela()], tipo_aplicacion="terrestre", banda="IV",
    )
    assert chequeo is not None
    assert chequeo.cumple is False
    assert len(chequeo.citas) == 1
    assert chequeo.citas[0].norma == "ordenanza-914-2018"
    assert chequeo.citas[0].articulo == "8"


def test_lote_a_150m_de_escuela_con_regla_de_100m_cumple():
    chequeo = evaluar_distancia_zona(
        zona_tipo="escuela", zona_nombre="Escuela N 12", distancia_real_m=150.0,
        reglas=[_regla_san_carlos_escuela()], tipo_aplicacion="terrestre", banda="IV",
    )
    assert chequeo.cumple is True


def test_distancia_exactamente_en_el_limite_cumple():
    chequeo = evaluar_distancia_zona(
        zona_tipo="escuela", zona_nombre="X", distancia_real_m=100.0,
        reglas=[_regla_san_carlos_escuela()], tipo_aplicacion="terrestre", banda="IV",
    )
    assert chequeo.cumple is True  # >= , no estrictamente mayor


def test_sin_regla_aplicable_devuelve_none():
    chequeo = evaluar_distancia_zona(
        zona_tipo="curso_agua", zona_nombre="Arroyo", distancia_real_m=10.0,
        reglas=[_regla_san_carlos_escuela()], tipo_aplicacion="terrestre", banda="IV",
    )
    assert chequeo is None


def test_regla_no_aplica_a_aplicacion_aerea_si_es_solo_terrestre():
    chequeo = evaluar_distancia_zona(
        zona_tipo="escuela", zona_nombre="X", distancia_real_m=80.0,
        reglas=[_regla_san_carlos_escuela()], tipo_aplicacion="aerea", banda="IV",
    )
    assert chequeo is None


def test_regla_con_tipo_aplicacion_todas_aplica_a_terrestre_y_aerea():
    regla_todas = ReglaCandidata(
        tipo_zona="curso_agua", tipo_aplicacion="todas", bandas=["todas"],
        distancia_min_m=50, norma="ordenanza-914-2018", articulo="10",
        jurisdiccion_id="san-carlos-centro",
    )
    terrestre = evaluar_distancia_zona("curso_agua", "Arroyo", 30, [regla_todas], "terrestre", "IV")
    aerea = evaluar_distancia_zona("curso_agua", "Arroyo", 30, [regla_todas], "aerea", "IV")
    assert terrestre is not None and terrestre.cumple is False
    assert aerea is not None and aerea.cumple is False


def test_regla_con_bandas_especificas_no_aplica_a_otra_banda():
    regla_bandas_altas = ReglaCandidata(
        tipo_zona="escuela", tipo_aplicacion="terrestre", bandas=["Ia", "Ib", "II"],
        distancia_min_m=200, norma="ordenanza-914-2018", articulo="11",
        jurisdiccion_id="san-carlos-centro",
    )
    chequeo_banda_iv = evaluar_distancia_zona(
        "escuela", "X", 80, [regla_bandas_altas], "terrestre", "IV"
    )
    assert chequeo_banda_iv is None
    chequeo_banda_ii = evaluar_distancia_zona(
        "escuela", "X", 80, [regla_bandas_altas], "terrestre", "II"
    )
    assert chequeo_banda_ii is not None


def test_varias_reglas_aplicables_gana_la_mas_restrictiva_citando_todas():
    regla_municipal = ReglaCandidata(
        tipo_zona="zona_urbana", tipo_aplicacion="todas", bandas=["todas"],
        distancia_min_m=100, norma="ordenanza-914-2018", articulo="12",
        jurisdiccion_id="san-carlos-centro",
    )
    regla_provincial = ReglaCandidata(
        tipo_zona="zona_urbana", tipo_aplicacion="todas", bandas=["todas"],
        distancia_min_m=300, norma="ley-13740-2017", articulo="2",
        jurisdiccion_id=None,
    )
    chequeo = evaluar_distancia_zona(
        "zona_urbana", "Casco urbano", 150,
        [regla_municipal, regla_provincial], "terrestre", "IV",
    )
    assert chequeo.distancia_min_aplicable_m == 300  # gana la provincial, más restrictiva
    assert chequeo.cumple is False  # 150 < 300
    assert len(chequeo.citas) == 2  # cita ambas, no solo la que ganó
    normas_citadas = {c.norma for c in chequeo.citas}
    assert normas_citadas == {"ordenanza-914-2018", "ley-13740-2017"}


def test_observaciones_de_las_reglas_se_propagan_como_advertencias():
    regla_con_aviso = ReglaCandidata(
        tipo_zona="escuela", tipo_aplicacion="aerea", bandas=["todas"],
        distancia_min_m=200, norma="ordenanza-914-2018", articulo="9",
        jurisdiccion_id="san-carlos-centro",
        observaciones="Aviso previo a la direccion de la escuela",
    )
    chequeo = evaluar_distancia_zona("escuela", "X", 250, [regla_con_aviso], "aerea", "IV")
    assert chequeo.advertencias == ["Aviso previo a la direccion de la escuela"]


# --- Prohibiciones (N) y reglas condicionales (S) ---


def _clase_b_aerea_ley_11273() -> list[ReglaCandidata]:
    """Ley 11.273 art. 33 / decreto art. 51: clase B (II) aérea, prohibida hasta 3.000 m;
    entre 500 y 3.000 m hay una excepción condicional."""
    return [
        ReglaCandidata(
            tipo_zona="zona_urbana", tipo_aplicacion="aerea", bandas=["II"],
            distancia_min_m=3000, norma="ley-11273-1995", articulo="33",
            jurisdiccion_id=None,
        ),
        ReglaCandidata(
            tipo_zona="zona_urbana", tipo_aplicacion="aerea", bandas=["II"],
            distancia_min_m=500, norma="ley-055297-2017", articulo="51",
            jurisdiccion_id=None, permitido=True,
            condiciones="ordenanza municipal; terreno que impida equipos terrestres",
        ),
    ]


def test_la_regla_condicional_no_bloquea_ni_entra_en_el_dictamen():
    # A 1.000 m manda la prohibición N (3.000 m); la S (500 m) no la ablanda.
    chequeo = evaluar_distancia_zona(
        zona_tipo="zona_urbana", zona_nombre="Casco urbano", distancia_real_m=1000.0,
        reglas=_clase_b_aerea_ley_11273(), tipo_aplicacion="aerea", banda="II",
    )
    assert chequeo.cumple is False
    assert chequeo.distancia_min_aplicable_m == 3000
    assert [c.articulo for c in chequeo.citas] == ["33"]  # la S no se cita como límite


def test_solo_una_regla_condicional_no_alcanza_para_un_dictamen():
    solo_condicional = [r for r in _clase_b_aerea_ley_11273() if r.permitido]
    chequeo = evaluar_distancia_zona(
        zona_tipo="zona_urbana", zona_nombre="Casco urbano", distancia_real_m=10.0,
        reglas=solo_condicional, tipo_aplicacion="aerea", banda="II",
    )
    assert chequeo is None


def test_a_una_distancia_menor_que_la_restriccion_se_ofrecen_las_condiciones():
    opciones = excepciones_aplicables(
        _clase_b_aerea_ley_11273(), "zona_urbana", "aerea", "II", distancia_real_m=1000.0
    )
    assert [o.articulo for o in opciones] == ["51"]
    assert "ordenanza" in opciones[0].condiciones


def test_por_debajo_de_la_distancia_minima_de_la_condicional_no_hay_opciones():
    opciones = excepciones_aplicables(
        _clase_b_aerea_ley_11273(), "zona_urbana", "aerea", "II", distancia_real_m=300.0
    )
    assert opciones == []


def test_las_opciones_respetan_banda_y_tipo_de_aplicacion():
    reglas = _clase_b_aerea_ley_11273()
    assert excepciones_aplicables(reglas, "zona_urbana", "aerea", "Ia", 1000.0) == []
    assert excepciones_aplicables(reglas, "zona_urbana", "terrestre", "II", 1000.0) == []
    assert excepciones_aplicables(reglas, "escuela", "aerea", "II", 1000.0) == []
