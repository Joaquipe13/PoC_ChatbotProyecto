from fitosanitarios.servicios.reglas import (
    ReglaCandidata,
    excepciones_aplicables,
    reglas_aplicables,
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


def test_la_regla_de_la_escuela_aplica_a_terrestre():
    aplicables = reglas_aplicables([_regla_escuela_sastre()], "escuela", "terrestre", "IV")
    assert [r.norma for r in aplicables] == ["ordenanza-1174-2019"]


def test_sin_regla_para_ese_tipo_de_zona_no_hay_aplicables():
    assert reglas_aplicables([_regla_escuela_sastre()], "curso_agua", "terrestre", "IV") == []


def test_regla_no_aplica_a_aplicacion_aerea_si_es_solo_terrestre():
    assert reglas_aplicables([_regla_escuela_sastre()], "escuela", "aerea", "IV") == []


def test_regla_con_tipo_aplicacion_todas_aplica_a_terrestre_y_aerea():
    # Ninguna norma cargada usa "todas" como tipo de aplicación: regla de prueba.
    regla_todas = ReglaCandidata(
        tipo_zona="curso_agua", tipo_aplicacion="todas", bandas=["todas"],
        distancia_min_m=50, norma="norma-de-prueba", articulo="1", jurisdiccion_id=None,
    )
    assert reglas_aplicables([regla_todas], "curso_agua", "terrestre", "IV") == [regla_todas]
    assert reglas_aplicables([regla_todas], "curso_agua", "aerea", "IV") == [regla_todas]


def test_regla_con_bandas_especificas_no_aplica_a_otra_banda():
    # Ley 11.273, art. 34: terrestre, clases A y B (Ia, Ib, II), 500 m de la zona urbana.
    art_34 = ReglaCandidata(
        tipo_zona="zona_urbana", tipo_aplicacion="terrestre", bandas=["Ia", "Ib", "II"],
        distancia_min_m=500, norma="ley-11273-1995", articulo="34", jurisdiccion_id=None,
    )
    assert reglas_aplicables([art_34], "zona_urbana", "terrestre", "IV") == []
    assert reglas_aplicables([art_34], "zona_urbana", "terrestre", "II") == [art_34]


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


def test_la_regla_condicional_no_entra_entre_las_aplicables():
    # La S (500 m) no se cuenta como límite: queda solo la prohibición N (3.000 m).
    aplicables = reglas_aplicables(_clase_b_aerea_ley_11273(), "zona_urbana", "aerea", "II")
    assert [r.articulo for r in aplicables] == ["33"]


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
