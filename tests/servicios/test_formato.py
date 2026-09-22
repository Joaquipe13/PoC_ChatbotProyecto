from fitosanitarios.servicios.formato import norma_legible


def test_norma_legible_ordenanza():
    assert norma_legible("ordenanza-841-2010") == "Ordenanza 841/2010"


def test_norma_legible_resolucion_capitaliza_con_tilde():
    assert norma_legible("resolucion-5-2020") == "Resolución 5/2020"


def test_norma_legible_fallo_de_localidad_de_una_palabra():
    assert norma_legible("fallo-sastre-2020") == "Fallo Sastre/2020"


def test_norma_legible_fallo_de_localidad_de_varias_palabras():
    assert norma_legible("fallo-san-jorge-2009") == "Fallo San Jorge/2009"


def test_norma_legible_texto_sin_convencion_se_devuelve_igual():
    assert norma_legible("un-nombre-cualquiera") == "un-nombre-cualquiera"
