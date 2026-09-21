"""Borrador de filas de `reglas.csv` desde los PDF: sin base, sobre las fixtures
sintéticas (`tests/fixtures/insumos`). Es una ayuda para revisar, no una fuente
de datos: nunca toca el `reglas.csv`."""

import csv
import shutil
from pathlib import Path

from fpdf import FPDF

from fitosanitarios.insumos.borrador_reglas import (
    borrador_de_carpeta,
    escribir_borrador,
    filas_de_texto,
)
from fitosanitarios.insumos.reglas_csv import leer_reglas_csv

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "insumos"

TEXTO = (
    "Artículo 1° - Prohíbese la aplicación aérea de productos fitosanitarios de clase "
    "toxicológica A y B dentro del radio de 3.000 metros de las plantas urbanas. "
    "Excepcionalmente podrán aplicarse productos de clase C o D dentro de 500 metros, cuando "
    "exista ordenanza que lo autorice.\n"
    "Artículo 2° - Queda prohibida la aplicación terrestre a menos de 100 metros de las escuelas."
)


def test_filas_de_texto_toma_las_firmes_y_deja_las_excepciones_como_pendientes():
    filas, pendientes = filas_de_texto("ley-1-2000", TEXTO)
    assert [(f["tipo_zona"], f["tipo_aplicacion"], f["banda_toxicologica"], f["distancia_min_m"],
             f["articulo"]) for f in filas] == [
        ("zona_urbana", "aerea", "Ia;Ib;II", "3000", "1"),
        ("escuela", "terrestre", "todas", "100", "2"),
    ]
    assert all(f["norma"] == "ley-1-2000" and f["oracion"] for f in filas)
    assert all(f["permitido"] == "N" for f in filas)  # el extractor solo lee prohibiciones
    assert len(pendientes) == 1 and "Excepcionalmente" in pendientes[0]


PROVINCIAL = ("provincial", "santa-fe")


def _filas_del_csv(alcance):
    filas, errores = leer_reglas_csv(FIXTURES / "reglas.csv")
    assert errores == []
    return [f for f in filas if f.alcance == alcance]


def test_borrador_de_una_carpeta_con_filas_en_reglas_csv_no_pisa_nada_y_las_compara(tmp_path):
    carpeta = tmp_path / "santa-fe"
    shutil.copytree(FIXTURES / "santa-fe", carpeta, ignore=shutil.ignore_patterns("san-carlos*",
                                                                                  "colonia*"))
    csv_original = (FIXTURES / "reglas.csv").read_text(encoding="utf-8")

    resumen = borrador_de_carpeta(carpeta, PROVINCIAL, _filas_del_csv(PROVINCIAL))
    # La regla del CSV lleva "salvo que una norma municipal fije una distancia mayor":
    # el extractor la descarta (condicional), así que sale como pendiente y como
    # "solo en el CSV", que es lo que hay que mirar al revisar. La fila S (condicional)
    # no se compara: el extractor solo lee prohibiciones.
    assert resumen.tiene_csv and resumen.filas == [] and resumen.solo_en_borrador == []
    assert [f["norma"] for f in resumen.solo_en_csv] == ["ley-13740-2017"]
    assert len(resumen.pendientes) == 1 and "300 metros" in resumen.pendientes[0]
    escribir_borrador(resumen)

    assert (FIXTURES / "reglas.csv").read_text(encoding="utf-8") == csv_original
    with (carpeta / "reglas.borrador.csv").open(encoding="utf-8") as f:
        assert list(csv.DictReader(f)) == []  # solo el encabezado
    assert "300 metros" in (carpeta / "reglas.borrador-pendientes.txt").read_text(encoding="utf-8")


def test_las_filas_del_borrador_traen_provincia_y_jurisdiccion_para_copiarlas_al_csv(tmp_path):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 7, "Articulo 1 - Prohibese la aplicacion aerea de productos fitosanitarios "
                         "de clase toxicologica A y B dentro del radio de 3.000 metros de las "
                         "plantas urbanas.")
    pdf.output(str(tmp_path / "ley-2-2000.pdf"))

    for alcance, esperado in [
        (PROVINCIAL, ("", "santa-fe")),
        (("municipal", "santa-fe", "el-trebol"), ("santa-fe", "el-trebol")),
        (("nacional",), ("", "ARGENTINA")),
    ]:
        resumen = borrador_de_carpeta(tmp_path, alcance)
        assert resumen.filas, "el PDF de prueba tiene que dar una regla"
        assert {(f["provincia"], f["jurisdiccion"]) for f in resumen.filas} == {esperado}
        assert not resumen.tiene_csv


def test_carpeta_sin_pdfs_no_tiene_borrador(tmp_path):
    assert borrador_de_carpeta(tmp_path) is None
