"""El modelo de embeddings se carga una sola vez por proceso, también si lo piden
varios mensajes a la vez (sin cargar el modelo real: se reemplaza por un contador)."""

import sys
import threading
import time
import types

from fitosanitarios.servicios import recursos


def test_el_modelo_se_carga_una_sola_vez_aunque_lo_pidan_varios_hilos(monkeypatch):
    cargas = []

    class ModeloFalso:
        def __init__(self, nombre):
            time.sleep(0.05)  # que los hilos se pisen mientras carga
            cargas.append(nombre)

    monkeypatch.setitem(
        sys.modules, "sentence_transformers",
        types.SimpleNamespace(SentenceTransformer=ModeloFalso),
    )
    monkeypatch.setattr(recursos, "_modelo", None)

    obtenidos = []
    hilos = [
        threading.Thread(target=lambda: obtenidos.append(recursos.modelo_embeddings()))
        for _ in range(5)
    ]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert len(cargas) == 1
    assert all(m is obtenidos[0] for m in obtenidos)
    assert recursos.modelo_embeddings() is obtenidos[0]
