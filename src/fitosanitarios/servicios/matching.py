"""Matching de nombre comercial: combina similitud de texto y semántica en un
score único, con top-k y detección de empate para repreguntar en vez de
elegir (ver skill, "Matching de productos").

En la Fase 5 el mismo criterio de score se replica en SQL contra Postgres
(`pg_trgm` + `pgvector`, ver docs/modelo-datos.md, retriever de
`validar_producto_registro`). Esta versión en Python no depende de una base:
sirve para tests sin Docker y para deduplicar nombres durante la carga del
catálogo (Fase 2, `loader.py`).

`rapidfuzz.fuzz.token_sort_ratio` no es idéntico a `pg_trgm.similarity()`
(trigramas de caracteres) -- son heurísticas de texto distintas, ambas
razonables para nombres cortos de producto. Se documenta como aproximación
aceptada para esta fase, no como el score final que va a correr en SQL.
"""

import math
from dataclasses import dataclass

from rapidfuzz import fuzz

UMBRAL_EMPATE = 0.05  # diferencia de score por debajo de la cual se considera ambiguo


@dataclass
class Candidato:
    id: int
    nombre: str
    embedding: list[float] | None = None


@dataclass
class ResultadoMatching:
    candidato: Candidato
    score: float
    score_texto: float
    score_embedding: float | None


def _similitud_coseno(a: list[float], b: list[float]) -> float:
    producto_punto = sum(x * y for x, y in zip(a, b, strict=True))
    norma_a = math.sqrt(sum(x * x for x in a))
    norma_b = math.sqrt(sum(y * y for y in b))
    if norma_a == 0 or norma_b == 0:
        return 0.0
    return producto_punto / (norma_a * norma_b)


def rankear_candidatos(
    consulta: str,
    candidatos: list[Candidato],
    consulta_embedding: list[float] | None = None,
    peso_texto: float = 0.5,
    peso_embedding: float = 0.5,
    top_k: int = 5,
) -> list[ResultadoMatching]:
    """Ordena `candidatos` por score combinado (texto + embedding si hay) de
    mayor a menor, devuelve como mucho `top_k`."""
    resultados = []
    for candidato in candidatos:
        score_texto = fuzz.token_sort_ratio(consulta.lower(), candidato.nombre.lower()) / 100.0
        score_embedding = None
        if consulta_embedding is not None and candidato.embedding is not None:
            score_embedding = _similitud_coseno(consulta_embedding, candidato.embedding)
            score = peso_texto * score_texto + peso_embedding * score_embedding
        else:
            score = score_texto
        resultados.append(
            ResultadoMatching(
                candidato=candidato,
                score=score,
                score_texto=score_texto,
                score_embedding=score_embedding,
            )
        )
    resultados.sort(key=lambda r: r.score, reverse=True)
    return resultados[:top_k]


def hay_empate_ambiguo(
    resultados: list[ResultadoMatching], umbral: float = UMBRAL_EMPATE
) -> bool:
    """True si el 1° y el 2° candidato están tan cerca que no se puede elegir
    uno solo con confianza: el orquestador tiene que repreguntar con
    opciones, nunca elegir (ver skill, "Matching de productos")."""
    if len(resultados) < 2:
        return False
    return (resultados[0].score - resultados[1].score) < umbral
