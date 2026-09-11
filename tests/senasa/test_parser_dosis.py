from fitosanitarios.senasa.parser_dosis import parsear_dosis


def test_dosis_simple_por_hectarea():
    resultado = parsear_dosis("2 L/ha")
    assert resultado.parseable is True
    assert resultado.valor_min == 2.0
    assert resultado.valor_max == 2.0
    assert resultado.unidad == "L/ha"
    assert resultado.base == "superficie"


def test_dosis_rango_con_en_dash_y_coma_decimal():
    resultado = parsear_dosis("1,9 L/ha – 2,2 L/ha")
    assert resultado.parseable is True
    assert resultado.valor_min == 1.9
    assert resultado.valor_max == 2.2
    assert resultado.unidad == "L/ha"
    assert resultado.base == "superficie"


def test_dosis_rango_con_guion_simple():
    resultado = parsear_dosis("150-200 cm3/ha")
    assert resultado.parseable is True
    assert resultado.valor_min == 150.0
    assert resultado.valor_max == 200.0
    assert resultado.unidad == "cm³/ha"


def test_dosis_cada_100_litros_dato_real_focus_max():
    # Dato real relevado del producto SENASA reg. 40465 ("FOCUS MAX")
    resultado = parsear_dosis("17 ml/ 100 Litros")
    assert resultado.parseable is True
    assert resultado.valor_min == 17.0
    assert resultado.valor_max == 17.0
    assert resultado.unidad == "ml/100L"
    assert resultado.base == "volumen_caldo"


def test_dosis_kg_por_hectarea():
    resultado = parsear_dosis("1,5 kg/ha")
    assert resultado.parseable is True
    assert resultado.unidad == "kg/ha"
    assert resultado.valor_min == 1.5


def test_dosis_con_texto_alrededor_igual_matchea():
    resultado = parsear_dosis("Aplicar 2 L/ha en pre-siembra, incorporado")
    assert resultado.parseable is True
    assert resultado.valor_min == 2.0


def test_dosis_no_parseable_texto_libre():
    resultado = parsear_dosis("A definir por el profesional actuante")
    assert resultado.parseable is False
    assert resultado.valor_min is None
    assert resultado.texto_original == "A definir por el profesional actuante"


def test_dosis_no_parseable_unidades_mezcladas():
    resultado = parsear_dosis("2 L/ha + 500 g/ha")
    assert resultado.parseable is False


def test_dosis_vacia_no_parseable():
    resultado = parsear_dosis("")
    assert resultado.parseable is False


def test_dosis_none_no_parseable():
    resultado = parsear_dosis(None)
    assert resultado.parseable is False
