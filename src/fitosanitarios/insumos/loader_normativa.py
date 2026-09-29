"""Carga la normativa (PDFs, y `.md` sin fuente oficial) a `territorio.norma`
y `territorio.articulo`, chunkeada por artículo con embedding (ver skill,
"RAG de normativa").

Si un PDF no tiene capa de texto, intenta OCR con Tesseract (pytesseract). Si
Tesseract no está instalado en la máquina no falla: marca los artículos para
revisión manual (`requiere_revision=True`) y sigue con el resto -- ver
DIFICULTADES.md, Tesseract no está instalado en la máquina de desarrollo de
esta sesión, no se pudo probar el camino de OCR real todavía.

**Normas sin PDF (22/09/2026, ver DECISIONES.md, "Localidades y normas sin
fuente oficial: Sastre y San Jorge").** Un fallo judicial o una norma citada
solo por fuente secundaria (sin texto oficial disponible) se carga desde un
`.md` en vez de un PDF: mismo nombre `<tipo>-<numero>-<anio>`, con `tipo`
también pudiendo ser `fallo`. Se toma el texto tal cual (sin OCR) pero **no
se chunkea en artículos**: no tiene encabezados "Artículo N" reales y no hay
que inventarlos, así que no aparece en `consultar_articulo`.

**Fragmentos para el RAG (23/09/2026, ver DECISIONES.md, "RAG de
limitaciones").** Además de los artículos, cada norma se parte en fragmentos
(`territorio.fragmento_norma`) con el `RecursiveCharacterTextSplitter` de la
cursada (800 caracteres, 120 de solapamiento): un artículo largo queda en
varios fragmentos, y una norma sin PDF, sin artículos, también se fragmenta
(`articulo_id` NULL). Son los que busca `responder_consulta_normativa`.

Idempotente por localidad/ámbito: antes de cargar, borra las normas
existentes de ese alcance y las vuelve a insertar (mismo patrón que
`zona_protegida` en loader_geo.py) -- más simple que un `ON CONFLICT`
compuesto, dado que `archivo` solo es único dentro de su carpeta, no global.
"""

import argparse
import json
import logging
import re
from pathlib import Path

import pdfplumber
import psycopg

from fitosanitarios.config import get_settings
from fitosanitarios.datos.vectores import vector_literal
from fitosanitarios.insumos.estructura import (
    carpeta_nacional,
    carpetas_localidad,
    carpetas_provincia,
)
from fitosanitarios.servicios.fragmentos import partir_en_fragmentos

logger = logging.getLogger(__name__)

_PATRON_ARTICULO = re.compile(
    r"(?im)^\s*art(?:\.|[ií]culo)?\s*(?:n[°º]?\.?)?\s*(\d+)\s*[°º]?\s*[:.\-]*\s*"
)
_PATRON_NOMBRE_NORMA = re.compile(
    r"^(ordenanza|decreto|resolucion|ley|fallo)-([a-z0-9]+(?:-[a-z0-9]+)*)-(\d{4})\.(pdf|md)$"
)

def chunkear_articulos(texto: str) -> list[tuple[str, str]]:
    """Divide el texto de una norma en artículos: [(numero, cuerpo), ...].
    Si no encuentra ningún encabezado reconocible, devuelve `[]` -- no se
    inventa un artículo "1" con todo el texto adentro (ver caso borde de
    PDFs con formato de artículo no estándar)."""
    matches = list(_PATRON_ARTICULO.finditer(texto))
    articulos = []
    for i, m in enumerate(matches):
        numero = m.group(1)
        inicio = m.end()
        fin = matches[i + 1].start() if i + 1 < len(matches) else len(texto)
        cuerpo = texto[inicio:fin].strip()
        if cuerpo:
            articulos.append((numero, cuerpo))
    return articulos


def extraer_texto_o_ocr(ruta_pdf: Path) -> tuple[str, bool]:
    """Devuelve (texto, requiere_revision). `requiere_revision=True` si no
    había capa de texto (con o sin OCR exitoso después)."""
    with pdfplumber.open(ruta_pdf) as pdf:
        texto = "\n".join(pagina.extract_text() or "" for pagina in pdf.pages).strip()
    if texto:
        return texto, False

    try:
        import pytesseract

        with pdfplumber.open(ruta_pdf) as pdf:
            textos_ocr = [
                pytesseract.image_to_string(pagina.to_image(resolution=300).original, lang="spa")
                for pagina in pdf.pages
            ]
        return "\n".join(textos_ocr).strip(), True
    except Exception:
        logger.warning(
            "No se pudo hacer OCR de %s (¿Tesseract instalado?)", ruta_pdf, exc_info=True
        )
        return "", True


def _parsear_nombre_norma(ruta: Path) -> tuple[str, str, int]:
    m = _PATRON_NOMBRE_NORMA.match(ruta.name)
    if not m:
        raise ValueError(f"{ruta.name} no respeta <tipo>-<numero>-<anio>.pdf|.md")
    tipo, numero, anio, _extension = m.groups()
    return tipo, numero, int(anio)


def _texto_de_norma(ruta: Path) -> tuple[str, bool]:
    """(texto, requiere_revision). Un `.md` es una norma sin fuente oficial
    (fallo judicial o cita de fuente secundaria: ver DECISIONES.md,
    "Localidades y normas sin fuente oficial"), se toma tal cual, sin OCR."""
    if ruta.suffix == ".md":
        return ruta.read_text(encoding="utf-8").strip(), False
    return extraer_texto_o_ocr(ruta)


def cargar_normas_de_carpeta(
    cur,
    carpeta: Path,
    ambito: str,
    localidad_id: int | None,
    provincia_id: int | None,
    modelo_embeddings,
) -> dict[str, int]:
    if ambito == "municipal":
        cur.execute("DELETE FROM territorio.norma WHERE localidad_id = %s", (localidad_id,))
    elif ambito == "provincial":
        cur.execute(
            "DELETE FROM territorio.norma WHERE ambito = 'provincial' AND provincia_id = %s",
            (provincia_id,),
        )
    else:
        cur.execute("DELETE FROM territorio.norma WHERE ambito = 'nacional'")

    resumen = {"normas": 0, "articulos": 0, "fragmentos": 0, "pdfs_requieren_revision": 0}
    docs = sorted(carpeta.glob("*.pdf")) + sorted(carpeta.glob("*.md"))
    for doc in docs:
        tipo, numero, anio = _parsear_nombre_norma(doc)
        archivo = doc.stem
        sin_fuente_oficial = doc.suffix == ".md"
        texto, requiere_revision = _texto_de_norma(doc)
        if requiere_revision:
            resumen["pdfs_requieren_revision"] += 1

        cur.execute(
            """
            INSERT INTO territorio.norma
                (ambito, localidad_id, provincia_id, tipo, numero, anio, archivo, metadatos)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                ambito, localidad_id, provincia_id, tipo, numero, anio, archivo,
                json.dumps({
                    "paginas_sin_texto": bool(requiere_revision),
                    "sin_fuente_oficial": bool(sin_fuente_oficial),
                }),
            ),
        )
        norma_id = cur.fetchone()[0]
        resumen["normas"] += 1

        if sin_fuente_oficial:
            # sin encabezados de artículo reales: no se chunkea en artículos, pero sí
            # en fragmentos para el RAG (ver módulo)
            resumen["fragmentos"] += _insertar_fragmentos(
                cur, norma_id, [(None, texto)], modelo_embeddings
            )
            continue

        articulos = chunkear_articulos(texto)
        insertados: list[tuple[int, str]] = []
        if not articulos:
            logger.warning(
                "No se encontraron artículos en %s (¿formato de encabezado no estándar?)", doc
            )
        for numero_articulo, cuerpo in articulos:
            embedding = modelo_embeddings.encode(cuerpo[:2000]).tolist()
            vector_literal = "[" + ",".join(repr(float(x)) for x in embedding) + "]"
            cur.execute(
                """
                INSERT INTO territorio.articulo
                    (norma_id, numero, texto, requiere_revision, embedding)
                VALUES (%s, %s, %s, %s, %s::vector)
                RETURNING id
                """,
                (norma_id, numero_articulo, cuerpo, requiere_revision, vector_literal),
            )
            insertados.append((cur.fetchone()[0], cuerpo))
            resumen["articulos"] += 1
        resumen["fragmentos"] += _insertar_fragmentos(
            cur, norma_id, insertados, modelo_embeddings
        )

    return resumen


def _insertar_fragmentos(
    cur, norma_id: int, textos: list[tuple[int | None, str]], modelo_embeddings
) -> int:
    """`textos`: (articulo_id, texto) de cada artículo, o (None, texto completo) para una
    norma sin artículos. Los embeddings se calculan en lote."""
    fragmentos = [
        (articulo_id, orden, fragmento)
        for articulo_id, texto in textos
        for orden, fragmento in enumerate(partir_en_fragmentos(texto))
    ]
    if not fragmentos:
        return 0
    embeddings = modelo_embeddings.encode([f[2] for f in fragmentos], batch_size=32)
    for (articulo_id, orden, fragmento), embedding in zip(fragmentos, embeddings, strict=True):
        cur.execute(
            """
            INSERT INTO territorio.fragmento_norma (norma_id, articulo_id, orden, texto, embedding)
            VALUES (%s, %s, %s, %s, %s::vector)
            """,
            (norma_id, articulo_id, orden, fragmento, vector_literal(embedding.tolist())),
        )
    return len(fragmentos)


def cargar_normativa(conn: psycopg.Connection, data_dir: Path, modelo_embeddings) -> dict:
    resumen_total: dict[str, int] = {
        "normas": 0, "articulos": 0, "fragmentos": 0, "pdfs_requieren_revision": 0
    }

    with conn.cursor() as cur:
        for provincia_dir in carpetas_provincia(data_dir):
            cur.execute(
                """
                INSERT INTO territorio.provincia (nombre) VALUES (%s)
                ON CONFLICT (nombre) DO UPDATE SET nombre = EXCLUDED.nombre
                RETURNING id
                """,
                (provincia_dir.name,),
            )
            provincia_id = cur.fetchone()[0]
            # Normativa provincial: los PDFs de la propia carpeta de la provincia.
            r = cargar_normas_de_carpeta(
                cur, provincia_dir, "provincial", None, provincia_id, modelo_embeddings
            )
            for k in resumen_total:
                resumen_total[k] += r[k]

            # Normativa municipal: las carpetas de localidad dentro de la provincia.
            for carpeta in carpetas_localidad(provincia_dir):
                cur.execute(
                    "SELECT id FROM territorio.localidad WHERE jurisdiccion_id = %s",
                    (carpeta.name,),
                )
                row = cur.fetchone()
                if row is None:
                    logger.warning(
                        "%s no tiene localidad cargada todavía (correr loader_geo primero)",
                        carpeta.name,
                    )
                    continue
                r = cargar_normas_de_carpeta(
                    cur, carpeta, "municipal", row[0], None, modelo_embeddings
                )
                for k in resumen_total:
                    resumen_total[k] += r[k]

        nacional_dir = carpeta_nacional(data_dir)
        if nacional_dir.exists():
            r = cargar_normas_de_carpeta(
                cur, nacional_dir, "nacional", None, None, modelo_embeddings
            )
            for k in resumen_total:
                resumen_total[k] += r[k]

        conn.commit()
    return resumen_total


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--database-url", type=str, default=None)
    args = parser.parse_args()

    from sentence_transformers import SentenceTransformer

    settings = get_settings()
    db_url = args.database_url or settings.database_url
    modelo = SentenceTransformer(settings.embeddings_model)

    with psycopg.connect(db_url) as conn:
        resumen = cargar_normativa(conn, args.data, modelo)
    logger.info("Carga de normativa terminada: %s", resumen)


if __name__ == "__main__":
    main()
