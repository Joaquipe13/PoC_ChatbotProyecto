from fitosanitarios.servicios.matching import (
    Candidato,
    hay_empate_ambiguo,
    rankear_candidatos,
)


def test_candidato_claro_gana_por_texto():
    candidatos = [
        Candidato(id=1, nombre="Glifosato Full 48 SL"),
        Candidato(id=2, nombre="Cipermetrina 25 EC"),
        Candidato(id=3, nombre="Atrazina 50 SC"),
    ]
    resultados = rankear_candidatos("glifosato full 48", candidatos)
    assert resultados[0].candidato.id == 1
    assert not hay_empate_ambiguo(resultados)


def test_empate_entre_dos_nombres_muy_parecidos_dispara_repregunta():
    candidatos = [
        Candidato(id=1, nombre="Glifosato Full 48 SL"),
        Candidato(id=2, nombre="Glifosato Full 74 SL"),
    ]
    resultados = rankear_candidatos("glifosato full", candidatos)
    assert hay_empate_ambiguo(resultados)


def test_top_k_limita_resultados():
    candidatos = [Candidato(id=i, nombre=f"Producto {i}") for i in range(10)]
    resultados = rankear_candidatos("Producto 5", candidatos, top_k=3)
    assert len(resultados) == 3


def test_un_solo_candidato_nunca_es_empate():
    candidatos = [Candidato(id=1, nombre="Único Producto")]
    resultados = rankear_candidatos("unico producto", candidatos)
    assert not hay_empate_ambiguo(resultados)


def test_embedding_desempata_cuando_texto_es_identico():
    # Dos candidatos con nombre EXACTAMENTE igual (homónimos de distintas
    # firmas): el texto no puede desempatar, pero el embedding sí puede
    # inclinar el score si uno es semánticamente más cercano a la consulta
    # (ej. la consulta menciona el cultivo/uso en el texto libre original).
    consulta_embedding = [1.0, 0.0]
    candidatos = [
        Candidato(id=1, nombre="Multi Uso", embedding=[1.0, 0.0]),
        Candidato(id=2, nombre="Multi Uso", embedding=[0.0, 1.0]),
    ]
    resultados = rankear_candidatos(
        "multi uso", candidatos, consulta_embedding=consulta_embedding
    )
    assert resultados[0].candidato.id == 1
    assert resultados[0].score > resultados[1].score


def test_sin_embedding_score_es_solo_texto():
    candidatos = [Candidato(id=1, nombre="Producto X")]
    resultados = rankear_candidatos("producto x", candidatos)
    assert resultados[0].score_embedding is None
    assert resultados[0].score == resultados[0].score_texto
