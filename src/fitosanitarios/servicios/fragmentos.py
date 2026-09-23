"""Cómo se parte un texto para el RAG: el `RecursiveCharacterTextSplitter` de la cursada
(`Ejemplos/NLP_3_langchain_conversaciones_rag_v2.ipynb`), con 800 caracteres por
fragmento y 120 de solapamiento, para que una idea cortada en el borde quede entera en
alguno de los dos. Lo usan la normativa (`insumos/loader_normativa.py`) y los marbetes
de SENASA (`senasa/loader_marbetes.py`)."""

from langchain_text_splitters import RecursiveCharacterTextSplitter

TAMANO_FRAGMENTO = 800
SOLAPAMIENTO_FRAGMENTO = 120
# Un fragmento más corto no dice nada por sí solo ("de esta norma.", la cola de un
# artículo) y aparecía entre los más parecidos a cualquier pregunta.
LARGO_MINIMO_FRAGMENTO = 60

_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=TAMANO_FRAGMENTO, chunk_overlap=SOLAPAMIENTO_FRAGMENTO
)


def partir_en_fragmentos(texto: str) -> list[str]:
    return [
        f for f in _SPLITTER.split_text(texto) if len(f.strip()) >= LARGO_MINIMO_FRAGMENTO
    ]
