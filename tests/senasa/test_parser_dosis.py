import pytest

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


# Abreviaturas y variantes reales del catálogo SENASA (snapshot 2026-09-22).
@pytest.mark.parametrize(
    ("texto", "valor_min", "valor_max", "unidad"),
    [
        ("1 litro/ha", 1.0, 1.0, "L/ha"),
        ("0,75 a 1 lt/ha", 0.75, 1.0, "L/ha"),
        ("3-4 lts/ha", 3.0, 4.0, "L/ha"),
        ("Suelo medio y pesados: 2-4 Ltrs/ha", 2.0, 4.0, "L/ha"),
        ("143gr/ha", 143.0, 143.0, "g/ha"),
        ("70-140 grs/ha", 70.0, 140.0, "g/ha"),
        ("600-900 cm'/ha", 600.0, 900.0, "cm³/ha"),
        ("150-200 cc3/ha", 150.0, 200.0, "cm³/ha"),
        ("20-30 (g/ha)", 20.0, 30.0, "g/ha"),
        ("2 a 3 Litros por Hectárea", 2.0, 3.0, "L/ha"),
        ("60-100 cm3/hl", 60.0, 100.0, "cm³/100L"),
        ("50-100 cm3/100 lts agua", 50.0, 100.0, "cm³/100L"),
        ("O,5 L/ha", 0.5, 0.5, "L/ha"),
    ],
)
def test_dosis_con_abreviaturas_del_catalogo(texto, valor_min, valor_max, unidad):
    resultado = parsear_dosis(texto)
    assert resultado.parseable is True
    assert (resultado.valor_min, resultado.valor_max, resultado.unidad) == (valor_min, valor_max, unidad)


def test_dosis_en_mezcla_de_tanque_toma_la_de_antes_del_mas():
    resultado = parsear_dosis("150-200 cm3/ha + 240-320 cm3/ha de 2,4D (éster butílico 100% p/v)")
    assert resultado.parseable is True
    assert (resultado.valor_min, resultado.valor_max, resultado.unidad) == (150.0, 200.0, "cm³/ha")


def test_dosis_en_mezcla_con_unidad_solo_en_el_companero_no_parseable():
    assert parsear_dosis("80-120 ml + 665 ml/ha de sal dimetilamina de 2,4-D").parseable is False


@pytest.mark.parametrize(
    "texto",
    [
        # Una dosis por tipo de suelo: no hay una sola dosis.
        "Suelo liviano: 2 lt/ha; suelo mediano: 2,5 lt/ha; suelo pesado: 3 lts/ha",
        "Livianos NOA (*) 800-900 cm3/ha  Medios 900-1350 cm3/ha  Pesados 1350-1600 cm3/ha",
        # "250-300 Litros" es el volumen de agua, no la dosis.
        "600 cm3 / ha (volumen: 250-300 Litros de agua/ha) o 180 cm3 /100 Litros de agua",
        # El rango sería "4 hojas – 2,5 kg": dos dosis por estadio.
        "1,4 kg/ha hasta 4 hojas – 2,5 kg/ha desde 20% apertura de frutos",
        # El "3" de "cm3" no arranca un rango.
        "1000 cm3/ ha  50 cm3/ hl",
        # Rango con el primer número roto: no se lee solo el segundo.
        "0,.3 – 0,4 l/ha",
        "1 L/ha. Caudal mínimo: 500 lt/ha",
    ],
)
def test_dosis_ambigua_no_parseable(texto):
    assert parsear_dosis(texto).parseable is False
