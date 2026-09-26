"""El índice del RAG de normativa (migración 006): fragmentos de cada norma y reglas
escritas como oración, y el retriever que los busca juntos por similitud."""

from fitosanitarios.datos.retrievers.territorio import (
    contexto_normativo_por_similitud,
    obtener_localidad_por_jurisdiccion_id,
)
from fitosanitarios.insumos.loader_reglas import texto_de_regla
from fitosanitarios.servicios.fragmentos import (
    LARGO_MINIMO_FRAGMENTO,
    TAMANO_FRAGMENTO,
    partir_en_fragmentos,
)
from fitosanitarios.servicios.reglas import DISTANCIA_SIN_LIMITE_M


def test_un_texto_largo_se_parte_en_fragmentos_que_no_superan_el_tamano():
    texto = " ".join(f"Oración número {i} de un artículo bastante largo." for i in range(80))
    fragmentos = partir_en_fragmentos(texto)
    assert len(fragmentos) > 1
    assert all(len(f) <= TAMANO_FRAGMENTO for f in fragmentos)


def test_los_fragmentos_demasiado_cortos_se_descartan():
    assert partir_en_fragmentos("de esta norma.") == []
    assert len("de esta norma.") < LARGO_MINIMO_FRAGMENTO


def test_texto_de_una_prohibicion_con_sinonimos_y_fuente():
    texto = texto_de_regla(
        "Sastre", "zona_urbana", "aerea", ["II"], 3000, False, None, "ley-11273-1995", "33"
    )
    assert texto == (
        "Sastre · aplicación aérea (avión, avioneta, fumigación aérea) · bandas II (amarilla): "
        "prohibido aplicar a menos de 3000 m de la zona urbana (planta urbana, pueblo, "
        "ciudad, casas) (Ley 11273/1995, art. 33)"
    )


def test_texto_de_una_prohibicion_sin_limite_y_de_una_excepcion():
    sin_limite = texto_de_regla(
        "Sastre", "zona_urbana", "terrestre", ["Ia", "Ib"], DISTANCIA_SIN_LIMITE_M, False,
        None, "ordenanza-1174-2019", None,
    )
    assert "prohibido aplicar en toda la jurisdicción (Ordenanza 1174/2019)" in sin_limite
    excepcion = texto_de_regla(
        "santa-fe", "zona_urbana", "aerea", ["II"], 500, True, "con ordenanza que la autorice",
        "ley-055297-2017", "51",
    )
    assert "se permite aplicar desde 500 m de la zona urbana" in excepcion
    assert "con condiciones: con ordenanza que la autorice" in excepcion


def test_el_retriever_trae_fragmentos_y_reglas_de_la_jurisdiccion(conexion, modelo_embeddings):
    localidad = obtener_localidad_por_jurisdiccion_id(conexion, "el-trebol")
    embedding = modelo_embeddings.encode("¿a qué distancia del pueblo puedo aplicar con avión?")
    filas = contexto_normativo_por_similitud(
        conexion, embedding.tolist(), localidad.id, localidad.provincia_id, top_k=20
    )

    assert {f["tipo"] for f in filas} == {"fragmento", "regla"}
    archivos = {f["archivo"] for f in filas}
    assert "ordenanza-841-2010" in archivos
    assert "ordenanza-1174-2019" not in archivos  # es de Sastre
    scores = [f["score"] for f in filas]
    assert scores == sorted(scores, reverse=True)


def test_la_carga_indexa_fragmentos_y_reglas(conexion):
    with conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM territorio.fragmento_norma")
        assert cur.fetchone()[0] > 0
        cur.execute(
            "SELECT count(*) FROM territorio.regla_distancia"
            " WHERE texto IS NULL OR embedding IS NULL"
        )
        assert cur.fetchone()[0] == 0
