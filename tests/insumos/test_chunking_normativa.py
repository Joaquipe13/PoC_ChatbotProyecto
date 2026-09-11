from pathlib import Path

from fitosanitarios.insumos.loader_normativa import chunkear_articulos, extraer_texto_o_ocr

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "insumos"


def test_chunkea_pdf_real_con_3_articulos():
    ruta = FIXTURES / "localidades" / "san-carlos-centro" / "ordenanza-914-2018.pdf"
    texto, requiere_revision = extraer_texto_o_ocr(ruta)
    assert requiere_revision is False

    articulos = chunkear_articulos(texto)

    assert len(articulos) == 3
    numeros = [numero for numero, _ in articulos]
    assert numeros == ["8", "9", "10"]
    assert "100 metros" in articulos[0][1]


def test_chunkea_con_formato_articulo_punto():
    texto = "Art. 1.- Primer articulo.\nArt. 2.- Segundo articulo."
    articulos = chunkear_articulos(texto)
    assert [n for n, _ in articulos] == ["1", "2"]
    assert articulos[0][1] == "Primer articulo."
    assert articulos[1][1] == "Segundo articulo."


def test_chunkea_con_formato_sin_punto_y_simbolo_grado():
    # Caso borde citado en el plan: "Art 8º" sin punto.
    texto = "Art 8º Contenido del articulo ocho."
    articulos = chunkear_articulos(texto)
    assert len(articulos) == 1
    assert articulos[0][0] == "8"
    assert articulos[0][1] == "Contenido del articulo ocho."


def test_chunkea_con_articulo_mayusculas_y_tilde():
    texto = "ARTÍCULO 5°: Contenido en mayusculas."
    articulos = chunkear_articulos(texto)
    assert len(articulos) == 1
    assert articulos[0][0] == "5"


def test_sin_encabezados_reconocibles_devuelve_lista_vacia():
    # Caso borde: PDF con formato de artículo no estándar (numeración romana,
    # por ejemplo) -- no se inventa un artículo "1" con todo el texto adentro.
    texto = "CAPITULO PRIMERO\nDisposiciones generales sin numeracion de articulo reconocible."
    articulos = chunkear_articulos(texto)
    assert articulos == []


def test_ultimo_articulo_toma_el_resto_del_texto():
    texto = "Art. 1.- Uno.\nArt. 2.- Dos y mas texto\nque sigue en otra linea."
    articulos = chunkear_articulos(texto)
    assert articulos[-1][1] == "Dos y mas texto\nque sigue en otra linea."
