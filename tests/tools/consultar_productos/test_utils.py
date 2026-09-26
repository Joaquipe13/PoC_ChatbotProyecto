"""La banda máxima es la más peligrosa que se acepta: entran ella y las menos peligrosas."""

from fitosanitarios.tools.consultar_productos.utils import bandas_hasta


def test_banda_verde_trae_solo_banda_verde():
    assert bandas_hasta("IV") == ["IV"]


def test_banda_maxima_iii_excluye_las_mas_peligrosas():
    assert bandas_hasta("III") == ["III", "IV"]


def test_banda_maxima_ia_trae_todas():
    assert bandas_hasta("Ia") == ["Ia", "Ib", "II", "III", "IV"]


def test_sin_banda_maxima_no_filtra():
    assert bandas_hasta(None) is None
