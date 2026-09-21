"""Borrador de `reglas.csv` desde los PDF: sin base, sobre las fixtures
sintéticas (`tests/fixtures/insumos`). Es una ayuda para revisar, no una fuente
de datos: nunca pisa un `reglas.csv` existente."""

import csv
import shutil
from pathlib import Path

from fitosanitarios.insumos.borrador_reglas import (
    borrador_de_carpeta,
    escribir_borrador,
    filas_de_texto,
)

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
    assert [(f["tipo_zona"], f["tipo_aplicacion"], f["bandas"], f["distancia_min_m"], f["articulo"])
            for f in filas] == [
        ("zona_urbana", "aerea", "Ia;Ib;II", "3000", "1"),
        ("escuela", "terrestre", "todas", "100", "2"),
    ]
    assert all(f["norma"] == "ley-1-2000" and f["oracion"] for f in filas)
    assert len(pendientes) == 1 and "Excepcionalmente" in pendientes[0]


def test_borrador_de_una_carpeta_con_reglas_csv_no_lo_pisa_y_lo_compara(tmp_path):
    carpeta = tmp_path / "santa-fe"
    shutil.copytree(FIXTURES / "santa-fe", carpeta, ignore=shutil.ignore_patterns("san-carlos*",
                                                                                  "colonia*"))
    original = (carpeta / "reglas.csv").read_text(encoding="utf-8")

    resumen = borrador_de_carpeta(carpeta)
    # La regla del CSV lleva "salvo que una norma municipal fije una distancia mayor":
    # el extractor la descarta (condicional), así que sale como pendiente y como
    # "solo en el CSV", que es lo que hay que mirar al revisar.
    assert resumen.tiene_csv and resumen.filas == [] and resumen.solo_en_borrador == []
    assert [f["norma"] for f in resumen.solo_en_csv] == ["ley-13740-2017"]
    assert len(resumen.pendientes) == 1 and "300 metros" in resumen.pendientes[0]
    escribir_borrador(resumen)

    assert (carpeta / "reglas.csv").read_text(encoding="utf-8") == original
    with (carpeta / "reglas.borrador.csv").open(encoding="utf-8") as f:
        assert list(csv.DictReader(f)) == []  # solo el encabezado
    assert "300 metros" in (carpeta / "reglas.borrador-pendientes.txt").read_text(encoding="utf-8")


def test_carpeta_sin_pdfs_no_tiene_borrador(tmp_path):
    assert borrador_de_carpeta(tmp_path) is None
