import json
from pathlib import Path

from fpdf import FPDF

from fitosanitarios.insumos.validador import (
    pdf_tiene_texto,
    validar_carpeta_localidad,
    validar_geojson,
    validar_insumos,
    validar_nombre_carpeta,
    validar_reglas_csv,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "insumos"

LIMITE_VALIDO = {
    "type": "Polygon",
    "coordinates": [[
        [-60.660, -32.930], [-60.640, -32.930],
        [-60.640, -32.910], [-60.660, -32.910],
        [-60.660, -32.930],
    ]],
}


def _escribir_geojson(ruta: Path, features: list[dict]) -> None:
    ruta.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False),
        encoding="utf-8",
    )


def _pdf_con_texto(ruta: Path, texto: str = "Articulo 1.-\nContenido de prueba.") -> None:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 7, texto)
    pdf.output(str(ruta))


def _pdf_sin_texto(ruta: Path) -> None:
    pdf = FPDF()
    pdf.add_page()  # página en blanco, sin ningún texto
    pdf.output(str(ruta))


# --- Fixtures sintéticas reales: deben validar limpio ---


def test_fixtures_sinteticas_son_validas():
    for carpeta in [
        FIXTURES / "localidades" / "san-carlos-centro",
        FIXTURES / "localidades" / "colonia-vecina",
    ]:
        resultado = validar_carpeta_localidad(carpeta)
        assert resultado.es_valido, resultado.errores


def test_validar_insumos_sobre_fixtures_completas_sin_errores():
    resultados = validar_insumos(FIXTURES)
    assert len(resultados) == 4  # 2 localidades + provincial santa-fe + nacional
    for clave, resultado in resultados.items():
        assert resultado.es_valido, f"{clave}: {resultado.errores}"


# --- F1: falta algún archivo requerido ---


def test_f1_falta_reglas_csv(tmp_path):
    carpeta = tmp_path / "localidad-incompleta"
    carpeta.mkdir()
    propiedades = {"tipo": "limite", "nombre": "X", "provincia": "santa-fe"}
    _escribir_geojson(carpeta / "localidad.geojson", [
        {"type": "Feature", "properties": propiedades, "geometry": LIMITE_VALIDO},
    ])
    _pdf_con_texto(carpeta / "ordenanza-1-2020.pdf")
    # sin reglas.csv

    resultado = validar_carpeta_localidad(carpeta)
    assert not resultado.es_valido
    assert any(e.codigo == "F1" for e in resultado.errores)


# --- F2: no hay exactamente un límite ---


def test_f2_geojson_sin_limite(tmp_path):
    ruta = tmp_path / "caso.geojson"
    _escribir_geojson(ruta, [
        {"type": "Feature", "properties": {"tipo": "escuela", "nombre": "X"},
         "geometry": {"type": "Point", "coordinates": [-60.65, -32.92]}},
    ])
    resultado = validar_geojson(ruta)
    assert any(e.codigo == "F2" for e in resultado.errores)


def test_f2_geojson_con_dos_limites(tmp_path):
    ruta = tmp_path / "caso.geojson"
    _escribir_geojson(ruta, [
        {"type": "Feature", "properties": {"tipo": "limite", "nombre": "A", "provincia": "x"},
         "geometry": LIMITE_VALIDO},
        {"type": "Feature", "properties": {"tipo": "limite", "nombre": "B", "provincia": "x"},
         "geometry": LIMITE_VALIDO},
    ])
    resultado = validar_geojson(ruta)
    assert any(e.codigo == "F2" for e in resultado.errores)


# --- F3: tipo de feature desconocido ---


def test_f3_tipo_desconocido(tmp_path):
    ruta = tmp_path / "caso.geojson"
    _escribir_geojson(ruta, [
        {"type": "Feature", "properties": {"tipo": "limite", "nombre": "A", "provincia": "x"},
         "geometry": LIMITE_VALIDO},
        {"type": "Feature", "properties": {"tipo": "cancha_de_futbol", "nombre": "Y"},
         "geometry": {"type": "Point", "coordinates": [-60.65, -32.92]}},
    ])
    resultado = validar_geojson(ruta)
    assert any(e.codigo == "F3" for e in resultado.errores)


# --- F4: geometría inválida o fuera de Argentina ---


def test_f4_geometria_autointersectante(tmp_path):
    poligono_bowtie = {
        "type": "Polygon",
        "coordinates": [[
            [-60.66, -32.93], [-60.64, -32.91],
            [-60.64, -32.93], [-60.66, -32.91],
            [-60.66, -32.93],
        ]],
    }
    ruta = tmp_path / "caso.geojson"
    _escribir_geojson(ruta, [
        {"type": "Feature", "properties": {"tipo": "limite", "nombre": "A", "provincia": "x"},
         "geometry": poligono_bowtie},
    ])
    resultado = validar_geojson(ruta)
    assert any(e.codigo == "F4" for e in resultado.errores)


def test_f4_fuera_de_argentina(tmp_path):
    limite_en_europa = {
        "type": "Polygon",
        "coordinates": [[
            [10.0, 45.0], [10.1, 45.0], [10.1, 45.1], [10.0, 45.1], [10.0, 45.0],
        ]],
    }
    ruta = tmp_path / "caso.geojson"
    _escribir_geojson(ruta, [
        {"type": "Feature", "properties": {"tipo": "limite", "nombre": "A", "provincia": "x"},
         "geometry": limite_en_europa},
    ])
    resultado = validar_geojson(ruta)
    assert any(e.codigo == "F4" for e in resultado.errores)


# --- F5: regla cita una norma que no está en la carpeta ---


def test_f5_regla_cita_norma_inexistente(tmp_path):
    csv_path = tmp_path / "reglas.csv"
    csv_path.write_text(
        "tipo_zona,tipo_aplicacion,bandas,distancia_min_m,norma,articulo,observaciones\n"
        "escuela,terrestre,todas,100,ordenanza-que-no-existe-2020,8,\n",
        encoding="utf-8",
    )
    resultado = validar_reglas_csv(csv_path, pdfs_disponibles={"ordenanza-1-2020"})
    assert any(e.codigo == "F5" for e in resultado.errores)


# --- F6: nombre de archivo/carpeta no respeta la convención ---


def test_f6_nombre_de_carpeta_invalido(tmp_path):
    resultado = validar_nombre_carpeta("San Carlos Centro", tmp_path)
    assert any(e.codigo == "F6" for e in resultado.errores)


def test_f6_nombre_de_carpeta_valido(tmp_path):
    resultado = validar_nombre_carpeta("san-carlos-centro", tmp_path)
    assert resultado.es_valido


# --- A2: zona protegida lejos del límite de su localidad ---


def test_a2_zona_protegida_lejos_del_limite(tmp_path):
    zona_muy_lejos = {"type": "Point", "coordinates": [-58.0, -32.92]}  # a decenas de km
    ruta = tmp_path / "caso.geojson"
    _escribir_geojson(ruta, [
        {"type": "Feature", "properties": {"tipo": "limite", "nombre": "A", "provincia": "x"},
         "geometry": LIMITE_VALIDO},
        {"type": "Feature", "properties": {"tipo": "escuela", "nombre": "Lejana"},
         "geometry": zona_muy_lejos},
    ])
    resultado = validar_geojson(ruta, radio_busqueda_m=2000)
    assert resultado.es_valido  # no es un error, es una advertencia
    assert any(a.codigo == "A2" for a in resultado.advertencias)


def test_sin_a2_cuando_la_zona_esta_cerca(tmp_path):
    zona_cerca = {"type": "Point", "coordinates": [-60.6505, -32.9295]}
    ruta = tmp_path / "caso.geojson"
    _escribir_geojson(ruta, [
        {"type": "Feature", "properties": {"tipo": "limite", "nombre": "A", "provincia": "x"},
         "geometry": LIMITE_VALIDO},
        {"type": "Feature", "properties": {"tipo": "escuela", "nombre": "Cercana"},
         "geometry": zona_cerca},
    ])
    resultado = validar_geojson(ruta, radio_busqueda_m=2000)
    assert not any(a.codigo == "A2" for a in resultado.advertencias)


# --- A3: PDF sin texto extraíble (requiere OCR) ---


def test_a3_pdf_sin_texto(tmp_path):
    ruta = tmp_path / "documento.pdf"
    _pdf_sin_texto(ruta)
    assert pdf_tiene_texto(ruta) is False


def test_pdf_con_texto_no_dispara_a3(tmp_path):
    ruta = tmp_path / "documento.pdf"
    _pdf_con_texto(ruta)
    assert pdf_tiene_texto(ruta) is True
