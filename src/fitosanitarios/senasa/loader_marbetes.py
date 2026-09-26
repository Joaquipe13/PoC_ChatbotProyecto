"""Carga los marbetes de SENASA (los PDF que dejó el crawl en
`data/senasa/crudo/documentos/`) al índice del RAG: `catalogo.documento` (tipo
'marbete') y `catalogo.fragmento_marbete` (ver DECISIONES.md, "RAG de marbetes").

Cada PDF se lee página por página con pdfplumber, cada página se parte con el splitter
de la cursada (`servicios/fragmentos.py`) y cada fragmento guarda su página, para citar
"marbete, pág. 3". El archivo se llama `<n.º de inscripción>_<índice>_Marbete.pdf`
(`senasa/crawler.py`): del número sale el producto.

Un marbete escaneado (sin capa de texto, ~10 % en una muestra) queda registrado como
documento con `extraccion.sin_texto = true` y sin fragmentos: no hay OCR (Tesseract no
está instalado, ver DIFICULTADES.md).

Se confirma producto por producto: si se corta, se retoma donde quedó (los productos que
ya tienen su marbete cargado se saltean, salvo con `--todos`). La carga completa lleva
unas 3 horas en la máquina de desarrollo (medido: ~0,9 s de lectura por marbete y
~8,5 fragmentos por segundo de embeddings).
"""

import argparse
import json
import logging
import time
from collections import defaultdict
from pathlib import Path

import pdfplumber
import psycopg

from fitosanitarios.config import get_settings
from fitosanitarios.datos.vectores import vector_literal
from fitosanitarios.servicios.fragmentos import partir_en_fragmentos

logger = logging.getLogger(__name__)

TIPO_DOCUMENTO = "marbete"
# Menos texto que esto en todo el PDF: es un escaneo (o una imagen con un sello).
MINIMO_CARACTERES_CON_TEXTO = 200


def marbetes_por_registro(carpeta: Path) -> dict[str, list[Path]]:
    """Los PDF de marbete de la carpeta, agrupados por n.º de inscripción."""
    grupos: dict[str, list[Path]] = defaultdict(list)
    for ruta in sorted(carpeta.glob("*_Marbete.pdf")):
        grupos[ruta.name.split("_", 1)[0]].append(ruta)
    return dict(grupos)


def leer_paginas(ruta: Path) -> list[str]:
    """El texto de cada página (vacío si la página no tiene capa de texto). Sin caracteres
    NUL: algunos PDF los traen en el texto y Postgres no los acepta en un campo de texto
    (cortaba la carga entera)."""
    with pdfplumber.open(ruta) as pdf:
        return [(pagina.extract_text() or "").replace("\x00", "") for pagina in pdf.pages]


def fragmentos_de_paginas(paginas: list[str]) -> list[tuple[int, int, str]]:
    """(página empezando en 1, orden dentro de la página, texto) de cada fragmento."""
    return [
        (numero, orden, fragmento)
        for numero, texto in enumerate(paginas, start=1)
        for orden, fragmento in enumerate(partir_en_fragmentos(texto))
    ]


def _cargar_producto(cur, producto_id: int, rutas: list[Path], modelo_embeddings) -> dict:
    cur.execute(
        "DELETE FROM catalogo.documento WHERE producto_id = %s AND tipo = %s",
        (producto_id, TIPO_DOCUMENTO),
    )
    resumen = {"documentos": 0, "fragmentos": 0, "sin_texto": 0, "ilegibles": 0}
    for ruta in rutas:
        try:
            paginas = leer_paginas(ruta)
        except Exception:  # un PDF roto no corta la carga de los demás
            logger.exception("No se pudo leer %s", ruta.name)
            resumen["ilegibles"] += 1
            continue
        sin_texto = sum(len(p) for p in paginas) < MINIMO_CARACTERES_CON_TEXTO
        cur.execute(
            """
            INSERT INTO catalogo.documento (producto_id, tipo, ruta_archivo, extraccion)
            VALUES (%s, %s, %s, %s::jsonb)
            RETURNING id
            """,
            (
                producto_id, TIPO_DOCUMENTO, ruta.name,
                json.dumps({"paginas": len(paginas), "sin_texto": sin_texto}),
            ),
        )
        documento_id = cur.fetchone()[0]
        resumen["documentos"] += 1
        if sin_texto:
            resumen["sin_texto"] += 1
            continue

        fragmentos = fragmentos_de_paginas(paginas)
        if not fragmentos:
            continue
        embeddings = modelo_embeddings.encode([f[2] for f in fragmentos], batch_size=64)
        cur.executemany(
            """
            INSERT INTO catalogo.fragmento_marbete
                (documento_id, producto_id, pagina, orden, texto, embedding)
            VALUES (%s, %s, %s, %s, %s, %s::vector)
            """,
            [
                (documento_id, producto_id, pagina, orden, texto,
                 vector_literal(embedding.tolist()))
                for (pagina, orden, texto), embedding in zip(fragmentos, embeddings, strict=True)
            ],
        )
        resumen["fragmentos"] += len(fragmentos)
    return resumen


def cargar_marbetes(
    conn: psycopg.Connection,
    carpeta: Path,
    modelo_embeddings,
    solo_faltantes: bool = True,
    limite: int | None = None,
) -> dict:
    grupos = marbetes_por_registro(carpeta)
    with conn.cursor() as cur:
        cur.execute("SELECT numero_inscripcion, id FROM catalogo.producto")
        producto_por_registro = dict(cur.fetchall())
        cur.execute(
            "SELECT DISTINCT producto_id FROM catalogo.documento WHERE tipo = %s",
            (TIPO_DOCUMENTO,),
        )
        ya_cargados = {fila[0] for fila in cur.fetchall()}

    total = {
        "productos": 0, "documentos": 0, "fragmentos": 0, "sin_texto": 0, "ilegibles": 0,
        "sin_producto": 0, "salteados": 0,
    }
    pendientes = []
    for registro, rutas in grupos.items():
        producto_id = producto_por_registro.get(registro)
        if producto_id is None:
            total["sin_producto"] += 1
        elif solo_faltantes and producto_id in ya_cargados:
            total["salteados"] += 1
        else:
            pendientes.append((producto_id, rutas))
    if limite is not None:
        pendientes = pendientes[:limite]

    inicio = time.monotonic()
    for i, (producto_id, rutas) in enumerate(pendientes, start=1):
        with conn.cursor() as cur:
            resumen = _cargar_producto(cur, producto_id, rutas, modelo_embeddings)
        conn.commit()  # producto por producto: si se corta, se retoma desde acá
        total["productos"] += 1
        for clave, valor in resumen.items():
            total[clave] += valor
        if i % 100 == 0 or i == len(pendientes):
            logger.info(
                "Marbetes: %d/%d productos, %d fragmentos (%.0f min)",
                i, len(pendientes), total["fragmentos"], (time.monotonic() - inicio) / 60,
            )
    return total


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--carpeta", type=Path, default=Path("data/senasa/crudo/documentos"))
    parser.add_argument("--database-url", type=str, default=None)
    parser.add_argument("--limite", type=int, default=None, help="cargar solo N productos")
    parser.add_argument(
        "--todos", action="store_true", help="recargar también los que ya tienen marbete"
    )
    args = parser.parse_args()

    from sentence_transformers import SentenceTransformer

    settings = get_settings()
    modelo = SentenceTransformer(settings.embeddings_model)
    with psycopg.connect(args.database_url or settings.database_url) as conn:
        resumen = cargar_marbetes(
            conn, args.carpeta, modelo, solo_faltantes=not args.todos, limite=args.limite
        )
    logger.info("Carga de marbetes terminada: %s", resumen)


if __name__ == "__main__":
    main()
