from fitosanitarios.servicios.reglas import (
    ReglaCandidata,
    evaluar_distancia_zona,
    excepciones_aplicables,
)

# Reglas reales de tests/fixtures/insumos/reglas.csv (copia de data/insumos).
SASTRE = "sastre"


def _regla_escuela_sastre() -> ReglaCandidata:
    """Ordenanza 1174/2019 de Sastre: terrestre, todas las bandas, 200 m de la escuela."""
    return ReglaCandidata(
        tipo_zona="escuela", tipo_aplicacion="terrestre", bandas=["todas"],
        distancia_min_m=200, norma="ordenanza-1174-2019", articulo=None,
        jurisdiccion_id=SASTRE,
    )


def test_lote_a_150m_de_la_escuela_con_regla_de_200m_no_cumple_con_cita():
    chequeo = evaluar_distancia_zona(
        zona_tipo="escuela", zona_nombre="Escuela rural N 693", distancia_real_m=150.0,
        reglas=[_regla_escuela_sastre()], tipo_aplicacion="terrestre", banda="IV",
    )
    assert chequeo is not None
    assert chequeo.cumple is False
    assert len(chequeo.citas) == 1
    assert chequeo.citas[0].norma == "ordenanza-1174-2019"
    assert chequeo.citas[0].articulo is None


def test_lote_a_250m_de_la_escuela_con_regla_de_200m_cumple():
    chequeo = evaluar_distancia_zona(
        zona_tipo="escuela", zona_nombre="Escuela rural N 693", distancia_real_m=250.0,
        reglas=[_regla_escuela_sastre()], tipo_aplicacion="terrestre", banda="IV",
    )
    assert chequeo.cumple is True


def test_distancia_exactamente_en_el_limite_cumple():
    chequeo = evaluar_distancia_zona(
        zona_tipo="escuela", zona_nombre="X", distancia_real_m=200.0,
        reglas=[_regla_escuela_sastre()], tipo_aplicacion="terrestre", banda="IV",
    )
    assert chequeo.cumple is True  # >= , no estrictamente mayor


def test_sin_regla_aplicable_devuelve_none():
    chequeo = evaluar_distancia_zona(
        zona_tipo="curso_agua", zona_nombre="Arroyo", distancia_real_m=10.0,
        reglas=[_regla_escuela_sastre()], tipo_aplicacion="terrestre", banda="IV",
    )
    assert chequeo is None


def test_regla_no_aplica_a_aplicacion_aerea_si_es_solo_terrestre():
    chequeo = evaluar_distancia_zona(
        zona_tipo="escuela", zona_nombre="X", distancia_real_m=80.0,
        reglas=[_regla_escuela_sastre()], tipo_aplicacion="aerea", banda="IV",
    )
    assert chequeo is None


def test_regla_con_tipo_aplicacion_todas_aplica_a_terrestre_y_aerea():
    # Ninguna norma cargada usa "todas" como tipo de aplicación: regla de prueba.
    regla_todas = ReglaCandidata(
        tipo_zona="curso_agua", tipo_aplicacion="todas", bandas=["todas"],
        distancia_min_m=50, norma="norma-de-prueba", articulo="1", jurisdiccion_id=None,
    )
    terrestre = evaluar_distancia_zona("curso_agua", "Arroyo", 30, [regla_todas], "terrestre", "IV")
    aerea = evaluar_distancia_zona("curso_agua", "Arroyo", 30, [regla_todas], "aerea", "IV")
    assert terrestre is not None and terrestre.cumple is False
    assert aerea is not None and aerea.cumple is False


def test_regla_con_bandas_especificas_no_aplica_a_otra_banda():
    # Ley 11.273, art. 34: terrestre, clases A y B (Ia, Ib, II), 500 m de la zona urbana.
    art_34 = ReglaCandidata(
        tipo_zona="zona_urbana", tipo_aplicacion="terrestre", bandas=["Ia", "Ib", "II"],
        distancia_min_m=500, norma="ley-11273-1995", articulo="34", jurisdiccion_id=None,
    )
    assert evaluar_distancia_zona("zona_urbana", "X", 80, [art_34], "terrestre", "IV") is None
    assert evaluar_distancia_zona("zona_urbana", "X", 80, [art_34], "terrestre", "II") is not None


def test_varias_reglas_aplicables_gana_la_mas_restrictiva_citando_todas():
    # El Trébol, aérea banda II: la ordenanza dice 500 m para todas las bandas (art. 6) y la
    # ley, 3000 m para la clase B (art. 33).
    ordenanza_art_6 = ReglaCandidata(
        tipo_zona="zona_urbana", tipo_aplicacion="aerea", bandas=["todas"],
        distancia_min_m=500, norma="ordenanza-841-2010", articulo="6",
        jurisdiccion_id="el-trebol",
    )
    ley_art_33 = ReglaCandidata(
        tipo_zona="zona_urbana", tipo_aplicacion="aerea", bandas=["II"],
        distancia_min_m=3000, norma="ley-11273-1995", articulo="33", jurisdiccion_id=None,
    )
    chequeo = evaluar_distancia_zona(
        "zona_urbana", "Limite Agronomico", 1000, [ordenanza_art_6, ley_art_33], "aerea", "II",
    )
    assert chequeo.distancia_min_aplicable_m == 3000  # gana la provincial, más restrictiva
    assert chequeo.cumple is False  # 1000 < 3000
    assert len(chequeo.citas) == 2  # cita ambas, no solo la que ganó
    assert {c.norma for c in chequeo.citas} == {"ordenanza-841-2010", "ley-11273-1995"}


def test_observaciones_de_las_reglas_se_propagan_como_advertencias():
    aviso = "Buffer adicional desde la escuela rural N 693 Bernardino Rivadavia (Estacion km 465)"
    regla_con_aviso = ReglaCandidata(
        tipo_zona="escuela", tipo_aplicacion="aerea", bandas=["todas"],
        distancia_min_m=200, norma="ordenanza-1174-2019", articulo=None,
        jurisdiccion_id=SASTRE, observaciones=aviso,
    )
    chequeo = evaluar_distancia_zona("escuela", "X", 250, [regla_con_aviso], "aerea", "IV")
    assert chequeo.advertencias == [aviso]


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
