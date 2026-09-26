"""Resumen del pronóstico de la franja agendada: función pura."""

from datetime import datetime

from fitosanitarios.servicios.meteorologia import HoraPronostico
from fitosanitarios.servicios.viento import punto_cardinal, resumen_pronostico

EL_TREBOL_ART_4 = {
    "norma": "ordenanza-841-2010", "articulo": "4", "jurisdiccion_id": "el-trebol",
    "viento_max_kmh": 8.0,
    "descripcion": "prohíbe pulverizar con vientos de más de 8 km/h que puedan producir "
                   "derivas hacia la planta urbana",
}


def _hora(h, viento, direccion, rafagas=None, lluvia=0.0, prob=0, temp=20.0, humedad=60):
    return HoraPronostico(
        hora=datetime(2026, 9, 30, h), viento_kmh=viento, direccion_grados=direccion,
        rafagas_kmh=rafagas, lluvia_mm=lluvia, lluvia_probabilidad=prob, temperatura=temp,
        humedad=humedad,
    )


def test_puntos_cardinales():
    assert punto_cardinal(0) == "norte"
    assert punto_cardinal(110) == "este"
    assert punto_cardinal(135) == "sureste"
    assert punto_cardinal(350) == "norte"


def test_viento_del_norte_empuja_hacia_el_sur():
    """Convención meteorológica: la dirección es de dónde viene."""
    r = resumen_pronostico([_hora(8, 12, 0), _hora(9, 14, 10)], [])
    assert r["viene_de"] == "norte"
    assert r["empuja_hacia"] == "sur"


def test_la_direccion_media_de_350_y_10_grados_es_norte():
    r = resumen_pronostico([_hora(8, 10, 350), _hora(9, 10, 10)], [])
    assert r["viene_de"] == "norte"


def test_rangos_lluvia_y_franja():
    r = resumen_pronostico(
        [_hora(7, 10, 90, rafagas=20, lluvia=0.2, prob=30, temp=15, humedad=70),
         _hora(9, 18, 90, rafagas=31, lluvia=0.5, prob=60, temp=21, humedad=50)],
        [],
    )
    assert (r["desde"], r["hasta"]) == ("07:00", "09:00")
    assert (r["viento_min_kmh"], r["viento_max_kmh"], r["rafagas_max_kmh"]) == (10, 18, 31)
    assert (r["lluvia_mm"], r["lluvia_probabilidad_max"]) == (0.7, 60)
    assert (r["temperatura_min"], r["temperatura_max"], r["humedad_min"]) == (15, 21, 50)


def test_la_norma_de_viento_se_menciona_solo_si_el_viento_supera_su_umbral():
    assert resumen_pronostico([_hora(8, 12, 0)], [EL_TREBOL_ART_4])["normas"] == [
        EL_TREBOL_ART_4
    ]
    assert resumen_pronostico([_hora(8, 6, 0)], [EL_TREBOL_ART_4])["normas"] == []


def test_calma_sin_direccion():
    r = resumen_pronostico([_hora(8, 0, 0)], [])
    assert r["viene_de"] is None


def test_sin_horas_no_hay_resumen():
    assert resumen_pronostico([], []) is None
