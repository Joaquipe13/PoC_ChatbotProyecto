"""Búsqueda híbrida: similitud vectorial + palabras (BM25), fusionadas por ranking.

La vectorial encuentra el tema aunque la pregunta use otras palabras, pero pierde un dato
puntual enterrado en un fragmento que habla de otras cosas: "¿cuánto hay que esperar
para reingresar al lote?" no encontraba en el marbete de Banvel la línea "No reingresar
al área tratada hasta que el producto se haya secado" (el fragmento es sobre residuos,
carencia y resistencia; su vector sale con 0,38). La de palabras la encuentra por
"reingresar", pero contar coincidencias no alcanza: "tiempo" y "lote" están en todas las
páginas. BM25 pesa cada palabra por lo rara que es entre los fragmentos (una que está en
una sola página vale mucho más que una que está en todas).

Las dos listas se fusionan con Reciprocal Rank Fusion (cada fragmento suma 1/(k + su
puesto) en cada lista donde aparece): sube lo que está arriba en cualquiera de las dos.

Las palabras llegan ya llevadas a su raíz (Postgres, full-text en español: "reingresar"
y "reingreso" dan "reingres"), con una aparición por vez que figura en el texto.
Ver DECISIONES.md, "Búsqueda híbrida en los marbetes".
"""

import math
from dataclasses import dataclass

K1_BM25 = 1.2
B_BM25 = 0.75
K_RRF = 60
# Un fragmento que entra solo por palabras tiene que tener un mínimo de parecido de
# significado y un BM25 claro: si no, una raíz compartida por casualidad ("¿quién ganó el
# mundial?" -> "gan", como "ganado") lo metía. Calibrado con preguntas reales sobre los
# marbetes cargados el 23/09/2026: el fragmento del reingreso de Banvel tiene 0,38 de
# similitud y 3,1 de BM25; el del mundial, 0,03 y 5,1.
UMBRAL_BM25 = 2.0
PISO_VECTOR = 0.30


def bm25(consulta: list[str], documentos: list[list[str]]) -> list[float]:
    """El score BM25 de cada documento para la consulta (listas de palabras en su raíz)."""
    if not documentos:
        return []
    n = len(documentos)
    largo_medio = sum(len(d) for d in documentos) / n or 1
    frecuencia_docs = {t: sum(t in d for d in documentos) for t in set(consulta)}
    scores = []
    for doc in documentos:
        score = 0.0
        for termino in set(consulta):
            veces = doc.count(termino)
            if not veces:
                continue
            df = frecuencia_docs[termino]
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            score += idf * veces * (K1_BM25 + 1) / (
                veces + K1_BM25 * (1 - B_BM25 + B_BM25 * len(doc) / largo_medio)
            )
        scores.append(score)
    return scores


@dataclass
class Puntaje:
    indice: int  # posición en la lista de fragmentos recibida
    vector: float
    palabras: float
    fusion: float


def fusionar(scores_vector: list[float], scores_palabras: list[float]) -> list[Puntaje]:
    """Reciprocal Rank Fusion de los dos rankings, de mayor a menor. Un fragmento sin
    ninguna palabra de la consulta no suma por el ranking de palabras."""
    por_vector = sorted(range(len(scores_vector)), key=lambda i: -scores_vector[i])
    por_palabras = sorted(range(len(scores_palabras)), key=lambda i: -scores_palabras[i])
    puesto_vector = {i: p for p, i in enumerate(por_vector, start=1)}
    puesto_palabras = {i: p for p, i in enumerate(por_palabras, start=1)}
    puntajes = [
        Puntaje(
            indice=i, vector=scores_vector[i], palabras=scores_palabras[i],
            fusion=1 / (K_RRF + puesto_vector[i])
            + (1 / (K_RRF + puesto_palabras[i]) if scores_palabras[i] > 0 else 0.0),
        )
        for i in range(len(scores_vector))
    ]
    return sorted(puntajes, key=lambda p: -p.fusion)


def seleccionar(
    scores_vector: list[float],
    palabras_por_fragmento: list[list[str]],
    palabras_consulta: list[str],
    umbral_vector: float,
    top_k: int,
) -> list[Puntaje]:
    """Los fragmentos relevantes, en el orden de la fusión: los que pasan el umbral de
    similitud, más los que entran por palabras (BM25 alto y un mínimo de similitud)."""
    palabras = bm25(palabras_consulta, palabras_por_fragmento)
    relevantes = [
        p for p in fusionar(scores_vector, palabras)
        if p.vector >= umbral_vector or (p.palabras >= UMBRAL_BM25 and p.vector >= PISO_VECTOR)
    ]
    return relevantes[:top_k]
