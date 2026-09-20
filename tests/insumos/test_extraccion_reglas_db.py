"""Extracción de reglas desde los artículos guardados en la base (sin reglas.csv).
Todo dentro de una transacción que se revierte: no toca los datos cargados."""

import pytest

from fitosanitarios.datos.retrievers.territorio import reglas_candidatas
from fitosanitarios.insumos.loader_reglas import extraer_reglas_de_pdfs

ART_33 = (
    "Prohíbese la aplicación aérea de productos fitosanitarios de clase toxicológica A y B "
    "dentro del radio de 3.000 metros de las plantas urbanas."
)
ART_SIN_DISTANCIA = "Los portones tendrán un ancho mínimo de cuatro metros."


@pytest.fixture
def provincia_de_prueba(conexion):
    with conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO territorio.provincia (nombre) VALUES ('provincia-de-prueba') RETURNING id"
        )
        provincia_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO territorio.norma (ambito, provincia_id, tipo, numero, anio, archivo)
            VALUES ('provincial', %s, 'ley', '1', 2000, 'ley-1-2000') RETURNING id
            """,
            (provincia_id,),
        )
        norma_id = cur.fetchone()[0]
        for numero, texto in (("33", ART_33), ("7", ART_SIN_DISTANCIA)):
            cur.execute(
                "INSERT INTO territorio.articulo (norma_id, numero, texto) VALUES (%s, %s, %s)",
                (norma_id, numero, texto),
            )
    yield provincia_id
    conexion.rollback()


FILTRO = "n.ambito = 'provincial' AND n.provincia_id = %s"


def test_las_reglas_se_leen_del_articulo_y_quedan_marcadas_como_extraidas(
    conexion, provincia_de_prueba
):
    with conexion.cursor() as cur:
        n = extraer_reglas_de_pdfs(cur, FILTRO, (provincia_de_prueba,))

    assert n == 1  # el artículo sin prohibición de distancia no da nada
    (regla,) = reglas_candidatas(conexion, None, provincia_de_prueba)
    assert regla.fuente == "pdf_extraido"
    assert regla.articulo == "33" and regla.norma == "ley-1-2000"
    assert regla.tipo_zona == "zona_urbana" and regla.tipo_aplicacion == "aerea"
    assert regla.bandas == ["Ia", "Ib", "II"] and regla.distancia_min_m == 3000


def test_volver_a_extraer_da_lo_mismo_y_no_duplica_reglas(conexion, provincia_de_prueba):
    with conexion.cursor() as cur:
        extraer_reglas_de_pdfs(cur, FILTRO, (provincia_de_prueba,))
        extraer_reglas_de_pdfs(cur, FILTRO, (provincia_de_prueba,))
    assert len(reglas_candidatas(conexion, None, provincia_de_prueba)) == 1
