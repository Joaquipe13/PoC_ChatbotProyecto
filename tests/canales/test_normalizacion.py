from fitosanitarios.canales.whatsapp.normalizacion import numero_canonico, numero_para_envio


def test_numero_entrante_con_9_se_normaliza_sin_9():
    assert numero_canonico("5493411234567") == "543411234567"


def test_numero_ya_sin_9_queda_igual():
    assert numero_canonico("543411234567") == "543411234567"


def test_ambas_variantes_matchean_el_mismo_thread_id():
    assert numero_canonico("5493411234567") == numero_canonico("543411234567")


def test_numero_no_argentino_pasa_sin_tocar():
    assert numero_canonico("14155552671") == "14155552671"


def test_numero_para_envio_quita_9_en_modo_desarrollo():
    assert numero_para_envio("543411234567", quitar_9=True) == "543411234567"


def test_numero_para_envio_reinserta_9_fuera_de_modo_desarrollo():
    assert numero_para_envio("543411234567", quitar_9=False) == "5493411234567"


def test_numero_para_envio_no_argentino_pasa_sin_tocar():
    assert numero_para_envio("14155552671", quitar_9=False) == "14155552671"
