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
        FIXTURES / "santa-fe" / "san-carlos-centro",
        FIXTURES / "santa-fe" / "colonia-vecina",
    ]:
        resultado = validar_carpeta_localidad(carpeta)
        assert resultado.es_valido, resultado.errores


def test_validar_insumos_sobre_fixtures_completas_sin_errores():
    resultados = validar_insumos(FIXTURES)
    assert len(resultados) == 4  # 2 localidades + provincial santa-fe + nacional
    for clave, resultado in resultados.items():
        assert resultado.es_valido, f"{clave}: {resultado.errores}"


# --- F1: falta algún archivo requerido ---


def test_sin_reglas_csv_la_localidad_es_valida_y_avisa_que_se_leera_del_pdf(tmp_path):
    carpeta = tmp_path / "localidad-incompleta"
    carpeta.mkdir()
    propiedades = {"tipo": "limite", "nombre": "X", "provincia": "santa-fe"}
    _escribir_geojson(carpeta / "localidad.geojson", [
        {"type": "Feature", "properties": propiedades, "geometry": LIMITE_VALIDO},
    ])
    _pdf_con_texto(carpeta / "ordenanza-1-2020.pdf")
    # sin reglas.csv: las distancias se extraen del texto del PDF al cargar

    resultado = validar_carpeta_localidad(carpeta)
    assert resultado.es_valido
    assert any(a.codigo == "A4" for a in resultado.advertencias)


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


# --- Estructura por provincia: <provincia>/<localidad> y normativa provincial en la provincia ---


def _armar_provincia(base: Path, provincia: str, provincia_del_limite: str) -> Path:
    carpeta_provincia = base / provincia
    localidad = carpeta_provincia / "pueblo-a"
    localidad.mkdir(parents=True)
    _pdf_con_texto(carpeta_provincia / "ley-100-2010.pdf")  # normativa provincial
    _escribir_geojson(localidad / "localidad.geojson", [
        {"type": "Feature",
         "properties": {"tipo": "limite", "nombre": "Pueblo A", "provincia": provincia_del_limite},
         "geometry": LIMITE_VALIDO},
    ])
    _pdf_con_texto(localidad / "ordenanza-1-2020.pdf")
    (localidad / "reglas.csv").write_text(
        "tipo_zona,tipo_aplicacion,bandas,distancia_min_m,norma,articulo,observaciones\n"
        "escuela,terrestre,todas,100,ordenanza-1-2020,1,\n",
        encoding="utf-8",
    )
    return localidad


def test_las_claves_reflejan_la_jerarquia_provincia_localidad(tmp_path):
    _armar_provincia(tmp_path, "santa-fe", "santa-fe")
    resultados = validar_insumos(tmp_path)
    assert set(resultados) == {"santa-fe", "santa-fe/pueblo-a"}
    assert all(r.es_valido for r in resultados.values()), resultados


def test_la_provincia_se_valida_con_sus_propios_pdfs_no_con_los_de_las_localidades(tmp_path):
    localidad = _armar_provincia(tmp_path, "santa-fe", "santa-fe")
    (tmp_path / "santa-fe" / "ley-100-2010.pdf").unlink()  # sin normativa provincial
    resultados = validar_insumos(tmp_path)
    assert any(e.codigo == "F1" for e in resultados["santa-fe"].errores)
    assert localidad.exists() and resultados["santa-fe/pueblo-a"].es_valido


def test_f7_provincia_del_limite_distinta_de_la_carpeta_que_la_contiene(tmp_path):
    _armar_provincia(tmp_path, "santa-fe", "cordoba")
    resultado = validar_insumos(tmp_path)["santa-fe/pueblo-a"]
    assert any(e.codigo == "F7" for e in resultado.errores)


def test_es_clave_de_localidad():
    from fitosanitarios.insumos.validador import es_clave_de_localidad

    assert es_clave_de_localidad("santa-fe/el-trebol")
    assert not es_clave_de_localidad("santa-fe")
    assert not es_clave_de_localidad("normativa-general/nacional")
