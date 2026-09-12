from fitosanitarios.servicios.dosis import comparar_dosis


def test_dosis_dentro_del_rango_cumple():
    resultado = comparar_dosis(2.5, "L/ha", 2.0, 3.0, "L/ha", tolerancia_pct=10.0)
    assert resultado.comparable is True
    assert resultado.cumple is True
    assert resultado.porcentaje_desvio == 0.0


def test_dosis_5_l_ha_fuera_de_rango_2_3_l_ha_da_observacion_con_desvio():
    # Caso citado literalmente en plandefases.md, Fase 5.
    resultado = comparar_dosis(5.0, "L/ha", 2.0, 3.0, "L/ha", tolerancia_pct=10.0)
    assert resultado.comparable is True
    assert resultado.cumple is False
    assert resultado.porcentaje_desvio is not None
    assert resultado.porcentaje_desvio > 0  # por encima
    assert round(resultado.porcentaje_desvio) == 67  # (5-3)/3 * 100


def test_dosis_por_debajo_del_rango_da_desvio_negativo():
    resultado = comparar_dosis(1.0, "L/ha", 2.0, 3.0, "L/ha", tolerancia_pct=10.0)
    assert resultado.cumple is False
    assert resultado.porcentaje_desvio < 0


def test_dosis_dentro_de_la_tolerancia_igual_cumple():
    # 3,2 L/ha está fuera de 2-3 pero dentro del 10% de tolerancia sobre el máximo (3,3)
    resultado = comparar_dosis(3.2, "L/ha", 2.0, 3.0, "L/ha", tolerancia_pct=10.0)
    assert resultado.cumple is True


def test_dosis_justo_en_el_limite_de_tolerancia_cumple():
    resultado = comparar_dosis(3.3, "L/ha", 2.0, 3.0, "L/ha", tolerancia_pct=10.0)
    assert resultado.cumple is True


def test_dosis_apenas_pasado_el_limite_de_tolerancia_no_cumple():
    resultado = comparar_dosis(3.31, "L/ha", 2.0, 3.0, "L/ha", tolerancia_pct=10.0)
    assert resultado.cumple is False


def test_sin_maximo_registrado_usa_el_minimo_como_valor_unico():
    # Sin max_registrado, el rango colapsa a un único valor (el mínimo) +-
    # tolerancia. 2,5 L/ha está fuera de 2,0 +-10% (1,8 a 2,2).
    resultado = comparar_dosis(2.5, "L/ha", 2.0, None, "L/ha", tolerancia_pct=10.0)
    assert resultado.comparable is True
    assert resultado.cumple is False
    assert resultado.porcentaje_desvio > 0

    dentro_de_tolerancia = comparar_dosis(2.1, "L/ha", 2.0, None, "L/ha", tolerancia_pct=10.0)
    assert dentro_de_tolerancia.cumple is True


def test_conversion_cm3_a_litro_es_comparable():
    # 2500 cm3/ha == 2,5 L/ha
    resultado = comparar_dosis(2500, "cm³/ha", 2.0, 3.0, "L/ha", tolerancia_pct=10.0)
    assert resultado.comparable is True
    assert resultado.cumple is True


def test_conversion_cm3_sin_superindice_unicode_es_comparable():
    # Hallazgo real (Fase 10): el operario escribe "cm3/ha" (ASCII, sin el
    # "³") desde el teclado del celular, y el LLM lo pasa tal cual como
    # argumento de tool -- antes de este alias daba "unidad no reconocida"
    # (reproducido en evals/ y en la demo). Ver DECISIONES.md.
    resultado = comparar_dosis(170, "cm3/ha", 160.0, 180.0, "cm³/ha", tolerancia_pct=10.0)
    assert resultado.comparable is True
    assert resultado.cumple is True


def test_conversion_gramos_a_kg_es_comparable():
    resultado = comparar_dosis(2500, "g/ha", 2.0, 3.0, "kg/ha", tolerancia_pct=10.0)
    assert resultado.comparable is True
    assert resultado.cumple is True


def test_familias_distintas_no_son_comparables():
    # L/ha (volumen) contra kg/ha (masa): no tiene sentido compararlos.
    resultado = comparar_dosis(2.5, "L/ha", 2.0, 3.0, "kg/ha", tolerancia_pct=10.0)
    assert resultado.comparable is False
    assert resultado.motivo_no_comparable is not None


def test_sin_rango_registrado_no_es_comparable():
    resultado = comparar_dosis(2.5, "L/ha", None, None, None, tolerancia_pct=10.0)
    assert resultado.comparable is False


def test_dosis_por_100_litros_requiere_volumen_de_caldo():
    # "Cada 100 L de agua" (ver skill, sección Dosis): no se puede convertir
    # a por-hectárea sin el volumen de caldo aplicado por hectárea.
    resultado = comparar_dosis(17.0, "ml/100L", 15.0, 20.0, "ml/100L", tolerancia_pct=10.0)
    assert resultado.comparable is False
    assert resultado.requiere_volumen_caldo is True


def test_coma_decimal_ya_resuelta_por_el_llamador():
    # El parseo de "1,9" -> 1.9 ya lo hace parser_dosis.py; acá solo se
    # recibe el float ya convertido.
    resultado = comparar_dosis(1.9, "L/ha", 1.5, 2.2, "L/ha", tolerancia_pct=10.0)
    assert resultado.comparable is True
    assert resultado.cumple is True
