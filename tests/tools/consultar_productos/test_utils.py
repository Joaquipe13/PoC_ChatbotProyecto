"""La banda máxima es la más peligrosa que se acepta: entran ella y las menos peligrosas."""

from fitosanitarios.tools.consultar_productos.utils import (
    bandas_hasta,
    intersectar_bandas,
    resolver_aptitudes,
)

APTITUDES = [
    "Acaricida", "Fitoregulador", "Fungicida", "Herbicida", "Insecticida",
    "Terapico trat. semillas",
]


def test_banda_verde_trae_solo_banda_verde():
    assert bandas_hasta("IV") == ["IV"]


def test_banda_maxima_iii_excluye_las_mas_peligrosas():
    assert bandas_hasta("III") == ["III", "IV"]


def test_banda_maxima_ia_trae_todas():
    assert bandas_hasta("Ia") == ["Ia", "Ib", "II", "III", "IV"]


def test_sin_banda_maxima_no_filtra():
    assert bandas_hasta(None) is None


def test_intersectar_bandas_combina_los_filtros_dados():
    assert intersectar_bandas(["II", "III", "IV"], None, ["III", "IV", "Ia"]) == ["III", "IV"]
    assert intersectar_bandas(None, None) is None
    assert intersectar_bandas(["II"], ["IV"]) == []


def test_aptitud_en_plural_y_varias_a_la_vez():
    assert resolver_aptitudes("fungicidas", APTITUDES) == (["Fungicida"], [])
    assert resolver_aptitudes("Herbicidas o insecticidas", APTITUDES) == (
        ["Herbicida", "Insecticida"], []
    )
    assert resolver_aptitudes("fitorreguladores", APTITUDES) == (["Fitoregulador"], [])


def test_aptitud_con_sinonimo_y_una_que_no_existe():
    assert resolver_aptitudes("curasemillas, abonos", APTITUDES) == (
        ["Terapico trat. semillas"], ["abonos"]
    )
