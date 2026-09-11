"""Benchmark de latencia de EMBEDDINGS_MODEL sobre nombres de producto sintéticos.

Fase 1, tarea 11 de plandefases.md: confirmar (o corregir) la elección de
EMBEDDINGS_MODEL con datos representativos del dominio antes de darla por
cerrada. Uso:

    uv run python scripts/benchmark_embeddings.py

No requiere red más allá de la primera corrida (descarga el modelo una vez,
después queda cacheado por sentence-transformers/huggingface-hub).
"""

import random
import time

from sentence_transformers import SentenceTransformer

from fitosanitarios.config import get_settings

MARCAS = [
    "Glifosato", "Full", "Atanor", "Roundup", "Cipermetrina", "Clorpirifos",
    "Paraquat", "2,4-D", "Metsulfuron", "Imazetapir", "Fipronil", "Lambda",
    "Cialotrina", "Azoxistrobina", "Mancozeb", "Carbendazim", "Tebuconazole",
    "Metsulfurón", "Diquat", "Flumioxazin", "Sulfentrazone", "Dicamba",
    "Picloram", "Triclopir", "Acetoclor", "Metolaclor", "Atrazina",
]
SUFIJOS = [
    "48 SL", "Full II", "Max", "Plus", "SC", "EC", "WG", "480", "24", "BIO",
    "Premium", "Total", "Gold", "Xtra", "72", "44", "25", "Combi",
]
CULTIVOS = ["soja", "maiz", "trigo", "girasol", "sorgo", "algodon", "cebada"]
ADVERSIDADES = [
    "yuyo colorado", "sorgo de alepo", "gramineas anuales", "roya asiatica",
    "oruga militar tardia", "chinche de la soja", "malezas de hoja ancha",
]


def generar_nombres_sinteticos(cantidad: int, semilla: int = 42) -> list[str]:
    rnd = random.Random(semilla)
    nombres = []
    for _ in range(cantidad):
        tipo = rnd.random()
        if tipo < 0.5:
            nombre = f"{rnd.choice(MARCAS)} {rnd.choice(SUFIJOS)}"
        elif tipo < 0.8:
            nombre = f"{rnd.choice(MARCAS)} para {rnd.choice(CULTIVOS)}"
        else:
            nombre = f"{rnd.choice(MARCAS)} {rnd.choice(SUFIJOS)} - {rnd.choice(ADVERSIDADES)}"
        nombres.append(nombre)
    return nombres


def main() -> None:
    settings = get_settings()
    modelo_nombre = settings.embeddings_model
    print(f"Modelo: {modelo_nombre}")

    nombres = generar_nombres_sinteticos(200)

    inicio_carga = time.perf_counter()
    modelo = SentenceTransformer(modelo_nombre)
    segundos_carga = time.perf_counter() - inicio_carga
    print(f"Carga del modelo: {segundos_carga:.1f} s")

    # Warmup (excluido de la medición: primera corrida incluye compilación/cachés internos)
    modelo.encode(nombres[:5])

    inicio = time.perf_counter()
    embeddings = modelo.encode(nombres, batch_size=32, show_progress_bar=False)
    segundos = time.perf_counter() - inicio

    print(f"200 nombres embebidos en {segundos:.2f} s ({segundos / 200 * 1000:.1f} ms/nombre)")
    print(f"Dimensión del embedding: {embeddings.shape[1]}")


if __name__ == "__main__":
    main()
