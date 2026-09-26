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


# --- Insumos reales (copia congelada en tests/fixtures): deben validar sin errores ---


def test_las_localidades_reales_son_validas():
    for localidad in ("el-trebol", "sastre", "san-jorge"):
        resultado = validar_carpeta_localidad(FIXTURES / "santa-fe" / localidad)
        assert resultado.es_valido, resultado.errores


def test_validar_insumos_sobre_fixtures_completas_sin_errores():
    resultados = validar_insumos(FIXTURES)
    assert len(resultados) == 4  # 3 localidades + provincial santa-fe
    for clave, resultado in resultados.items():
        assert resultado.es_valido, f"{clave}: {resultado.errores}"
    # Sastre y San Jorge no tienen localidad.geojson: es válido, pero avisa (A5).
    assert [a.codigo for a in resultados["santa-fe/sastre"].advertencias] == ["A5"]


# --- F1: falta algún archivo requerido ---


def test_sin_filas_en_reglas_csv_la_localidad_es_valida_y_avisa_que_se_leera_del_pdf(tmp_path):
    carpeta = tmp_path / "santa-fe" / "localidad-incompleta"
    carpeta.mkdir(parents=True)
    propiedades = {"tipo": "limite", "nombre": "X", "provincia": "santa-fe"}
    _escribir_geojson(carpeta / "localidad.geojson", [
        {"type": "Feature", "properties": propiedades, "geometry": LIMITE_VALIDO},
    ])
    _pdf_con_texto(carpeta / "ordenanza-1-2020.pdf")
    _pdf_con_texto(carpeta.parent / "ley-100-2010.pdf")
    # sin reglas.csv: las distancias se extraen del texto del PDF al cargar

    resultado = validar_insumos(tmp_path)["santa-fe/localidad-incompleta"]
    assert resultado.es_valido
    assert any(a.codigo == "A4" for a in resultado.advertencias)


def test_la_normativa_nacional_no_avisa_que_se_leera_del_pdf(tmp_path):
    nacional = tmp_path / "normativa-general" / "nacional"
    nacional.mkdir(parents=True)
    _pdf_con_texto(nacional / "ley-1-2000.pdf")
    resultado = validar_insumos(tmp_path)["normativa-general/nacional"]
    assert resultado.es_valido and resultado.advertencias == []


# --- A5 / .md: localidad sin `localidad.geojson`, norma sin PDF (22/09/2026,
# ver DECISIONES.md, "Localidades y normas sin fuente oficial") ---


def test_localidad_sin_geojson_es_valida_y_avisa_a5(tmp_path):
    carpeta = tmp_path / "santa-fe" / "sastre"
    carpeta.mkdir(parents=True)
    (carpeta / "fallo-sastre-2020.md").write_text("Texto de referencia.", encoding="utf-8")

    resultado = validar_carpeta_localidad(carpeta)
    assert resultado.es_valido
    assert any(a.codigo == "A5" for a in resultado.advertencias)


def test_localidad_sin_geojson_ni_norma_sigue_fallando_f1(tmp_path):
    carpeta = tmp_path / "santa-fe" / "sin-nada"
    carpeta.mkdir(parents=True)

    resultado = validar_carpeta_localidad(carpeta)
    assert any(e.codigo == "F1" for e in resultado.errores)


def test_f6_nombre_de_fallo_con_localidad_de_varias_palabras_es_valido(tmp_path):
    from fitosanitarios.insumos.validador import validar_nombre_norma

    resultado = validar_nombre_norma(tmp_path / "fallo-san-jorge-2009.md")
    assert resultado.es_valido


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


PROVINCIAL = ("provincial", "santa-fe")


def _csv(tmp_path: Path, *filas: str) -> Path:
    ruta = tmp_path / "reglas.csv"
    encabezado = (
        "provincia,jurisdiccion,tipo_zona,tipo_aplicacion,banda_toxicologica,distancia_min_m,"
        "permitido,condiciones,norma,articulo,observaciones"
    )
    ruta.write_text(encabezado + "\n" + "\n".join(filas) + "\n", encoding="utf-8")
    return ruta


def test_f5_regla_cita_norma_inexistente(tmp_path):
    ruta = _csv(
        tmp_path, ",santa-fe,escuela,terrestre,todas,100,N,,ordenanza-que-no-existe-2020,8,"
    )
    resultados = validar_reglas_csv(ruta, {PROVINCIAL: {"ley-1-2000"}})
    assert any(e.codigo == "F5" for e in resultados[PROVINCIAL].errores)


def test_f5_una_norma_de_otra_carpeta_no_vale(tmp_path):
    # La misma norma existe, pero en otra jurisdiccion: no es la que corresponde.
    ruta = _csv(tmp_path, ",santa-fe,escuela,terrestre,todas,100,N,,ordenanza-1-2020,8,")
    pdfs = {PROVINCIAL: {"ley-1-2000"}, ("municipal", "santa-fe", "pueblo-a"): {"ordenanza-1-2020"}}
    resultados = validar_reglas_csv(ruta, pdfs)
    assert any(e.codigo == "F5" for e in resultados[PROVINCIAL].errores)


def test_f8_fila_con_formato_invalido_no_se_atribuye_a_una_carpeta(tmp_path):
    ruta = _csv(tmp_path, ",santa-fe,escuela,terrestre,todas,100,QUIZAS,,ley-1-2000,8,")
    resultados = validar_reglas_csv(ruta, {PROVINCIAL: {"ley-1-2000"}})
    assert any(e.codigo == "F8" and "permitido" in e.mensaje for e in resultados[None].errores)


def test_f8_encabezado_incompleto(tmp_path):
    ruta = tmp_path / "reglas.csv"
    ruta.write_text("tipo_zona,tipo_aplicacion,bandas,distancia_min_m,norma,articulo,observaciones\n",
                    encoding="utf-8")
    resultados = validar_reglas_csv(ruta, {PROVINCIAL: {"ley-1-2000"}})
    errores = resultados[None].errores
    assert any(e.codigo == "F8" and "faltan las columnas" in e.mensaje for e in errores)


def test_f9_jurisdiccion_sin_carpeta(tmp_path):
    ruta = _csv(tmp_path, "santa-fe,pueblo-fantasma,escuela,terrestre,todas,100,N,,ley-1-2000,8,")
    resultados = validar_reglas_csv(ruta, {PROVINCIAL: {"ley-1-2000"}})
    assert any(e.codigo == "F9" for e in resultados[None].errores)


def test_una_regla_nacional_se_valida_contra_la_carpeta_nacional(tmp_path):
    ruta = _csv(tmp_path, ",ARGENTINA,zona_urbana,todas,todas,10,N,,ley-1-2000,1,")
    assert validar_reglas_csv(ruta, {("nacional",): {"ley-1-2000"}}) == {}


# --- F6: nombre de archivo/carpeta no respeta la convención ---


def test_f6_nombre_de_carpeta_invalido(tmp_path):
    resultado = validar_nombre_carpeta("El Trébol", tmp_path)
    assert any(e.codigo == "F6" for e in resultado.errores)


def test_f6_nombre_de_carpeta_valido(tmp_path):
    resultado = validar_nombre_carpeta("el-trebol", tmp_path)
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
    (base / "reglas.csv").write_text(
        "provincia,jurisdiccion,tipo_zona,tipo_aplicacion,banda_toxicologica,distancia_min_m,"
        "permitido,condiciones,norma,articulo,observaciones\n"
        f"{provincia},pueblo-a,escuela,terrestre,todas,100,N,,ordenanza-1-2020,1,\n",
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
