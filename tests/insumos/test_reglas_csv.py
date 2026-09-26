"""Lectura del `reglas.csv` único: formato, normalización y alcance de cada fila."""

from pathlib import Path

import pytest

from fitosanitarios.insumos.reglas_csv import COLUMNAS, ErrorFila, leer_reglas_csv, normalizar_fila

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "insumos"


def _fila(**cambios) -> dict:
    base = {
        "provincia": "", "jurisdiccion": "santa-fe", "tipo_zona": "zona_urbana",
        "tipo_aplicacion": "aerea", "banda_toxicologica": "Ia;Ib", "distancia_min_m": "3000",
        "permitido": "N", "condiciones": "", "norma": "ley-11273-1995", "articulo": "33",
        "observaciones": "",
    }
    return {**base, **cambios}


def test_las_fixtures_se_leen_sin_errores_y_con_su_alcance():
    filas, errores = leer_reglas_csv(FIXTURES / "reglas.csv")
    assert errores == []
    assert {f.alcance for f in filas} == {
        ("municipal", "santa-fe", "el-trebol"),
        ("municipal", "santa-fe", "sastre"),
        ("municipal", "santa-fe", "san-jorge"),
        ("provincial", "santa-fe"),
    }
    # La excepción del decreto para banda II por avión (Ley 055297/2017, art. 51).
    (condicional,) = [
        f for f in filas if f.permitido and f.norma == "ley-055297-2017" and f.bandas == ["II"]
    ]
    assert condicional.condiciones.startswith("Excepcion para clase B entre 500 y 3000 m")
    assert condicional.distancia_min_m == 500


def test_provincial_lleva_la_provincia_en_jurisdiccion_y_provincia_vacia():
    fila = normalizar_fila(_fila(), 2)
    assert fila.provincia is None and fila.alcance == ("provincial", "santa-fe")


def test_municipal_lleva_provincia_y_localidad():
    fila = normalizar_fila(_fila(provincia="santa-fe", jurisdiccion="el-trebol"), 2)
    assert fila.alcance == ("municipal", "santa-fe", "el-trebol")


@pytest.mark.parametrize("nombre", ["ARGENTINA", "NACIONAL", "argentina"])
def test_nacional_ignora_la_provincia(nombre):
    fila = normalizar_fila(_fila(jurisdiccion=nombre, provincia="santa-fe"), 2)
    assert fila.alcance == ("nacional",) and fila.provincia is None


def test_acepta_mayusculas_y_guion_bajo_en_provincia_y_jurisdiccion():
    fila = normalizar_fila(
        _fila(provincia="SANTA_FE", jurisdiccion="EL_TREBOL", tipo_aplicacion="AEREA",
              banda_toxicologica="ia;IB;Ii", tipo_zona="ZONA_URBANA"), 2,
    )
    assert fila.alcance == ("municipal", "santa-fe", "el-trebol")
    assert fila.tipo_aplicacion == "aerea" and fila.tipo_zona == "zona_urbana"
    assert fila.bandas == ["Ia", "Ib", "II"]


@pytest.mark.parametrize(("valor", "esperado"), [
    ("N", False), ("no", False), ("S", True), ("SI", True), ("sí", True),
])
def test_permitido_n_es_prohibicion_y_s_es_condicional(valor, esperado):
    assert normalizar_fila(_fila(permitido=valor), 2).permitido is esperado


@pytest.mark.parametrize("cambio", [
    {"permitido": "quizas"}, {"permitido": ""},
    {"tipo_aplicacion": "satelital"}, {"banda_toxicologica": "V"}, {"banda_toxicologica": ""},
    {"distancia_min_m": "mucho"}, {"distancia_min_m": "-5"}, {"jurisdiccion": ""},
    {"norma": ""}, {"tipo_zona": ""},
])
def test_valores_invalidos_se_rechazan(cambio):
    with pytest.raises(ErrorFila):
        normalizar_fila(_fila(**cambio), 2)


def test_todas_las_bandas():
    assert normalizar_fila(_fila(banda_toxicologica="TODAS"), 2).bandas == ["todas"]


def test_articulo_y_textos_vacios_quedan_en_none():
    fila = normalizar_fila(_fila(articulo="", condiciones="  ", observaciones=""), 2)
    assert fila.articulo is None and fila.condiciones is None and fila.observaciones is None


def test_encabezado_incompleto_se_informa_una_vez(tmp_path):
    ruta = tmp_path / "reglas.csv"
    ruta.write_text("tipo_zona,tipo_aplicacion\nescuela,terrestre\n", encoding="utf-8")
    filas, errores = leer_reglas_csv(ruta)
    assert filas == [] and len(errores) == 1 and "faltan las columnas" in errores[0]


def test_los_errores_dicen_la_linea_y_no_frenan_las_demas_filas(tmp_path):
    ruta = tmp_path / "reglas.csv"
    ok = ",santa-fe,zona_urbana,aerea,II,3000,N,,ley-1-2000,1,"
    mal = ",santa-fe,zona_urbana,aerea,II,3000,X,,ley-1-2000,1,"
    ruta.write_text(",".join(COLUMNAS) + "\n" + ok + "\n\n" + mal + "\n", encoding="utf-8")
    filas, errores = leer_reglas_csv(ruta)
    assert len(filas) == 1
    assert len(errores) == 1 and errores[0].startswith("línea 4:")


def test_ignora_columnas_de_mas_como_oracion_del_borrador(tmp_path):
    ruta = tmp_path / "reglas.csv"
    ruta.write_text(
        ",".join(COLUMNAS) + ",oracion\n"
        ",santa-fe,zona_urbana,aerea,II,3000,N,,ley-1-2000,1,,Una frase\n",
        encoding="utf-8",
    )
    filas, errores = leer_reglas_csv(ruta)
    assert errores == [] and len(filas) == 1
