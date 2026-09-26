"""Test de integración de los loaders de insumos contra Postgres real (Docker), con los
insumos reales congelados en `tests/fixtures/insumos/` (El Trébol, Sastre, San Jorge,
Ley 11.273 y su decreto).

Se salta automáticamente si no hay una base de test disponible (ver
`tests/db_test_infra.py`). Para correrlo:

    docker compose up -d db
    uv run pytest tests/insumos/test_loaders_integracion.py -q

La base de test ya tiene esos insumos cargados (`_base_de_test` en tests/conftest.py,
con el modelo de embeddings real), así que la mayoría de los tests solo inspecciona la
carga. Antes cada test borraba `territorio.*` y recargaba: con las fixtures inventadas
tardaba segundos; con las reales, un minuto por test. La regla de la normativa nacional
(nunca se leen distancias de su PDF) la cubre `test_loader_reglas_sin_base.py`, sin base.
"""

from pathlib import Path

from fitosanitarios.insumos.loader_geo import cargar_localidades
from fitosanitarios.insumos.loader_meteorologia import cargar_centros, cargar_reglas_viento
from fitosanitarios.insumos.loader_normativa import cargar_normativa
from fitosanitarios.insumos.loader_reglas import cargar_reglas, indexar_reglas

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "insumos"
FILAS_REGLAS_CSV = 18  # tests/fixtures/insumos/reglas.csv


def _una(conexion, sql, params=()):
    with conexion.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def test_la_carga_puebla_las_tres_localidades(conexion):
    filas = _una(conexion, "SELECT jurisdiccion_id FROM territorio.localidad")
    jurisdicciones = {r[0] for r in filas}
    assert jurisdicciones == {"el-trebol", "sastre", "san-jorge"}


def test_solo_el_trebol_tiene_limite(conexion):
    filas = dict(_una(
        conexion, "SELECT jurisdiccion_id, limite IS NOT NULL FROM territorio.localidad"
    ))
    assert filas == {"el-trebol": True, "sastre": False, "san-jorge": False}


def test_las_reglas_se_unen_con_su_norma_y_su_articulo(conexion):
    filas = _una(conexion, """
        SELECT rd.distancia_min_m, n.archivo, a.numero
        FROM territorio.regla_distancia rd
        JOIN territorio.norma n ON n.id = rd.norma_id
        LEFT JOIN territorio.articulo a ON a.id = rd.articulo_id
        JOIN territorio.localidad l ON l.id = n.localidad_id
        WHERE l.jurisdiccion_id = 'el-trebol' AND rd.tipo_aplicacion = 'aerea'
          AND rd.bandas = ARRAY['II']
    """)
    assert filas == [(3000, "ordenanza-841-2010", "7")]


def test_los_articulos_de_una_localidad_son_solo_de_sus_normas(conexion):
    normas = {r[0] for r in _una(conexion, """
        SELECT DISTINCT n.archivo FROM territorio.articulo a
        JOIN territorio.norma n ON n.id = a.norma_id
        JOIN territorio.localidad l ON l.id = n.localidad_id
        WHERE l.jurisdiccion_id = 'el-trebol'
    """)}
    assert normas == {"ordenanza-841-2010"}


def test_una_norma_sin_pdf_no_tiene_articulos_pero_si_reglas(conexion):
    """Las de Sastre son `.md` (fuente secundaria): no se inventan artículos."""
    ((articulos,),) = _una(conexion, """
        SELECT count(*) FROM territorio.articulo a JOIN territorio.norma n ON n.id = a.norma_id
        WHERE n.archivo = 'ordenanza-1174-2019'
    """)
    ((reglas,),) = _una(conexion, """
        SELECT count(*) FROM territorio.regla_distancia rd
        JOIN territorio.norma n ON n.id = rd.norma_id WHERE n.archivo = 'ordenanza-1174-2019'
    """)
    assert articulos == 0
    assert reglas > 0


def test_las_reglas_provinciales_no_tienen_localidad(conexion):
    filas = _una(conexion, """
        SELECT rd.tipo_zona, rd.tipo_aplicacion, rd.distancia_min_m, n.localidad_id
        FROM territorio.regla_distancia rd JOIN territorio.norma n ON n.id = rd.norma_id
        WHERE n.ambito = 'provincial' AND NOT rd.permitido
    """)
    assert filas and all(localidad_id is None for *_, localidad_id in filas)
    assert ("zona_urbana", "terrestre", 500) in {f[:3] for f in filas}  # Ley 11.273, art. 34


def test_la_regla_condicional_se_carga_aparte_con_sus_condiciones(conexion):
    filas = _una(conexion, """
        SELECT rd.bandas, rd.distancia_min_m, rd.condiciones, a.numero
        FROM territorio.regla_distancia rd
        JOIN territorio.norma n ON n.id = rd.norma_id
        LEFT JOIN territorio.articulo a ON a.id = rd.articulo_id
        WHERE n.archivo = 'ley-055297-2017' AND rd.permitido AND rd.bandas = ARRAY['II']
    """)
    assert len(filas) == 1
    bandas, distancia, condiciones, articulo = filas[0]
    assert (bandas, distancia, articulo) == (["II"], 500, "51")
    assert condiciones.startswith("Excepcion para clase B entre 500 y 3000 m")


def test_carga_es_idempotente(conexion, modelo_embeddings):
    def contar():
        ((localidades,),) = _una(conexion, "SELECT count(*) FROM territorio.localidad")
        ((reglas,),) = _una(conexion, "SELECT count(*) FROM territorio.regla_distancia")
        return localidades, reglas

    antes = contar()
    try:
        cargar_localidades(conexion, FIXTURES)
        cargar_normativa(conexion, FIXTURES, modelo_embeddings)
        cargar_reglas(conexion, FIXTURES)
        assert antes == contar() == (3, FILAS_REGLAS_CSV)
    finally:
        # Se deja la base como la deja `_base_de_test` para los demás archivos: recargar
        # las reglas les borra el texto y el embedding (el RAG de normativa los usa), y
        # recargar la normativa reemplaza las normas, de las que cuelgan las de viento.
        indexar_reglas(conexion, modelo_embeddings)
        cargar_centros(conexion, FIXTURES)
        cargar_reglas_viento(conexion, FIXTURES)


# --- Localidad sin `localidad.geojson` y norma sin PDF (22/09/2026, ver
# DECISIONES.md, "Localidades y normas sin fuente oficial: Sastre y San Jorge"): una
# carpeta mínima en tmp_path, para probar el caso sin tocar los insumos compartidos. Se
# borra al final.


def test_localidad_sin_geojson_se_carga_con_norma_sin_pdf(conexion, modelo_embeddings, tmp_path):
    localidad = tmp_path / "testprov" / "testville"
    localidad.mkdir(parents=True)
    (localidad / "fallo-testville-2020.md").write_text(
        "# Fallo de prueba\nTexto de referencia, sin encabezados de artículo.",
        encoding="utf-8",
    )
    (tmp_path / "reglas.csv").write_text(
        "provincia,jurisdiccion,tipo_zona,tipo_aplicacion,banda_toxicologica,distancia_min_m,"
        "permitido,condiciones,norma,articulo,observaciones\n"
        "testprov,testville,zona_urbana,terrestre,todas,500,N,,fallo-testville-2020,,\n",
        encoding="utf-8",
    )

    try:
        cargar_localidades(conexion, tmp_path)
        cargar_normativa(conexion, tmp_path, modelo_embeddings)
        assert cargar_reglas(conexion, tmp_path) == 1

        assert _una(conexion,
            "SELECT limite, bbox_min_lon FROM territorio.localidad WHERE jurisdiccion_id = %s",
            ("testville",),
        ) == [(None, None)]
        assert _una(conexion,
            "SELECT tipo FROM territorio.norma WHERE archivo = 'fallo-testville-2020'"
        ) == [("fallo",)]
        assert _una(conexion,
            "SELECT count(*) FROM territorio.articulo a "
            "JOIN territorio.norma n ON n.id = a.norma_id "
            "WHERE n.archivo = 'fallo-testville-2020'"
        ) == [(0,)]  # sin encabezados reales: no se inventan artículos
        assert _una(conexion,
            "SELECT rd.distancia_min_m FROM territorio.regla_distancia rd "
            "JOIN territorio.norma n ON n.id = rd.norma_id "
            "WHERE n.archivo = 'fallo-testville-2020'"
        ) == [(500,)]
    finally:
        with conexion.cursor() as cur:
            cur.execute(
                "DELETE FROM territorio.norma WHERE localidad_id IN "
                "(SELECT id FROM territorio.localidad WHERE jurisdiccion_id = 'testville')"
            )
            cur.execute("DELETE FROM territorio.localidad WHERE jurisdiccion_id = 'testville'")
            cur.execute("DELETE FROM territorio.provincia WHERE nombre = 'testprov'")
        conexion.commit()
