from fitosanitarios.senasa.normalizador import (
    limpiar_html,
    normalizar_banda,
    normalizar_color_banda,
    normalizar_nombre,
)


def test_limpiar_html_saca_tags_de_sustancias_activas():
    # Caso real relevado (producto SENASA reg. 42770, "CORE OPTIMUS")
    crudo = "ALCOHOL GRASO ETOXILADO <b>48%</b>, ALCOHOL LAURICO ETOXILADO <b>48%</b>"
    assert limpiar_html(crudo) == "ALCOHOL GRASO ETOXILADO 48%, ALCOHOL LAURICO ETOXILADO 48%"


def test_limpiar_html_colapsa_espacios():
    assert limpiar_html("A   <b>x</b>   B") == "A x B"


def test_normalizar_nombre_title_case():
    assert normalizar_nombre("ALGODON") == "Algodon"
    assert normalizar_nombre("YUYO COLORADO") == "Yuyo Colorado"


def test_normalizar_banda_valores_conocidos():
    assert normalizar_banda("IV") == "IV"
    assert normalizar_banda("Ia") == "Ia"
    assert normalizar_banda("ib") == "Ib"
    assert normalizar_banda("iii") == "III"


def test_normalizar_banda_desconocida_devuelve_none():
    assert normalizar_banda("S/D") is None
    assert normalizar_banda(None) is None
    assert normalizar_banda("") is None


def test_normalizar_color_banda_variante_con_typo_amareillo():
    assert normalizar_color_banda("AMAREILLO") == "amarillo"
    assert normalizar_color_banda("AMARILLO") == "amarillo"


def test_normalizar_color_banda_valores_conocidos():
    assert normalizar_color_banda("VERDE") == "verde"
    assert normalizar_color_banda("rojo") == "rojo"
    assert normalizar_color_banda("Azul") == "azul"


def test_normalizar_color_banda_desconocido_devuelve_none():
    assert normalizar_color_banda("FUCSIA") is None
    assert normalizar_color_banda(None) is None
