"""Carga el `reglas.csv` único de `data/insumos/` a `territorio.regla_distancia`
(y, donde una jurisdicción no tiene filas, lee las distancias del texto de sus
PDF, de forma determinista: ver `servicios/extraccion_reglas.py`). La normativa
nacional nunca se lee del PDF: está para consultas, no para el dictamen.

Resuelve la norma y el artículo citados contra lo que ya insertó
`loader_normativa.py` -- tiene que correr después de ese loader, no antes
(ver docs/contrato-insumos.md). Si una regla cita una norma o un artículo
que no está cargado, falla con un error explícito en vez de insertar una FK
inconsistente. Todo el archivo se valida antes de tocar la base.

`indexar_reglas` (23/09/2026, ver DECISIONES.md, "RAG de limitaciones") escribe cada
regla como una oración y le calcula el embedding, para recuperar por similitud qué
reglas corresponden a una pregunta. Va aparte de `cargar_reglas` porque necesita el
modelo de embeddings; `main` corre las dos.
"""

import argparse
import logging
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import psycopg

from fitosanitarios.config import get_settings
from fitosanitarios.datos.vectores import vector_literal
from fitosanitarios.insumos.estructura import carpeta_nacional, carpetas_provincia, localidades
from fitosanitarios.insumos.reglas_csv import FilaRegla, leer_reglas_csv
from fitosanitarios.servicios.condiciones_aplicacion import COLOR_BANDA
from fitosanitarios.servicios.extraccion_reglas import extraer_reglas_de_articulo
from fitosanitarios.servicios.formato import norma_legible
from fitosanitarios.servicios.reglas import DISTANCIA_SIN_LIMITE_M

logger = logging.getLogger(__name__)


@dataclass
class _Alcance:
    """Una jurisdicción cargada: qué normas de la base son suyas."""

    clave: tuple[str, ...]  # como `FilaRegla.alcance`
    filtro_normas: str  # SQL sobre `territorio.norma n`
    params: tuple
    con_extraccion: bool  # sin filas en el CSV, leer las distancias del PDF


def _resolver_articulo(cur, fila: FilaRegla, norma_id: int) -> int | None:
    if not fila.articulo:
        return None
    cur.execute(
        "SELECT id FROM territorio.articulo WHERE norma_id = %s AND numero = %s",
        (norma_id, fila.articulo),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(
            f"reglas.csv línea {fila.linea}: cita el artículo {fila.articulo} de {fila.norma}, "
            "que no se encontró chunkeado (¿el PDF usa un formato de encabezado no estándar?)"
        )
    return row[0]


def cargar_reglas_de_alcance(cur, alcance: _Alcance, filas: list[FilaRegla]) -> int:
    """Reemplaza las reglas del alcance por las del CSV."""
    cur.execute(
        "DELETE FROM territorio.regla_distancia WHERE norma_id IN "
        f"(SELECT n.id FROM territorio.norma n WHERE {alcance.filtro_normas})",
        alcance.params,
    )
    cur.execute(
        f"SELECT n.archivo, n.id FROM territorio.norma n WHERE {alcance.filtro_normas}",
        alcance.params,
    )
    norma_id_por_archivo = dict(cur.fetchall())
    for fila in filas:
        norma_id = norma_id_por_archivo.get(fila.norma)
        if norma_id is None:
            raise ValueError(
                f"reglas.csv línea {fila.linea}: la regla cita la norma '{fila.norma}', que no "
                f"está cargada para {'/'.join(alcance.clave)} (¿corriste loader_normativa.py "
                "antes?)"
            )
        articulo_id = _resolver_articulo(cur, fila, norma_id)
        cur.execute(
            """
            INSERT INTO territorio.regla_distancia
                (norma_id, articulo_id, tipo_zona, tipo_aplicacion, bandas,
                 distancia_min_m, permitido, condiciones, observaciones)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                norma_id, articulo_id, fila.tipo_zona, fila.tipo_aplicacion, fila.bandas,
                fila.distancia_min_m, fila.permitido, fila.condiciones, fila.observaciones,
            ),
        )
    return len(filas)


def _alcances_cargados(cur, data_dir: Path) -> list[_Alcance]:
    """Las jurisdicciones con carpeta en `data/insumos/` que ya están en la base."""
    alcances: list[_Alcance] = []
    for provincia in carpetas_provincia(data_dir):
        cur.execute("SELECT id FROM territorio.provincia WHERE nombre = %s", (provincia.name,))
        fila = cur.fetchone()
        if fila is None:
            logger.warning("%s sin provincia cargada, se omiten sus reglas", provincia.name)
        else:
            alcances.append(_Alcance(
                ("provincial", provincia.name),
                "n.ambito = 'provincial' AND n.provincia_id = %s", (fila[0],), True,
            ))
    for provincia, localidad in localidades(data_dir):
        cur.execute(
            "SELECT id FROM territorio.localidad WHERE jurisdiccion_id = %s", (localidad.name,)
        )
        fila = cur.fetchone()
        if fila is None:
            logger.warning("%s sin localidad cargada, se omiten sus reglas", localidad.name)
        else:
            alcances.append(_Alcance(
                ("municipal", provincia.name, localidad.name),
                "n.ambito = 'municipal' AND n.localidad_id = %s", (fila[0],), True,
            ))
    if carpeta_nacional(data_dir).exists():
        alcances.append(_Alcance(("nacional",), "n.ambito = 'nacional'", (), False))
    return alcances


def cargar_reglas(conn: psycopg.Connection, data_dir: Path) -> int:
    """`data_dir/reglas.csv` es la fuente preferida. Donde una jurisdicción no
    tiene filas, las distancias se leen del texto de sus PDF
    (`servicios/extraccion_reglas.py`), salvo las nacionales."""
    ruta_csv = data_dir / "reglas.csv"
    filas: list[FilaRegla] = []
    if ruta_csv.exists():
        filas, errores = leer_reglas_csv(ruta_csv)
        if errores:
            raise ValueError("reglas.csv con errores:\n" + "\n".join(errores))
    por_alcance: dict[tuple, list[FilaRegla]] = defaultdict(list)
    for fila in filas:
        por_alcance[fila.alcance].append(fila)

    total = 0
    with conn.cursor() as cur:
        alcances = _alcances_cargados(cur, data_dir)
        # Antes de tocar la base: una fila de una jurisdicción sin carpeta es un error del CSV.
        sin_carpeta = set(por_alcance) - {a.clave for a in alcances}
        if sin_carpeta:
            detalle = ", ".join("/".join(c) for c in sorted(sin_carpeta))
            raise ValueError(
                f"reglas.csv tiene filas de jurisdicciones sin carpeta cargada: {detalle}"
            )
        for alcance in alcances:
            del_csv = por_alcance.get(alcance.clave)
            if del_csv:
                total += cargar_reglas_de_alcance(cur, alcance, del_csv)
            elif alcance.con_extraccion:
                total += extraer_reglas_de_pdfs(cur, alcance.filtro_normas, alcance.params)
            else:
                cur.execute(
                    "DELETE FROM territorio.regla_distancia WHERE norma_id IN "
                    f"(SELECT n.id FROM territorio.norma n WHERE {alcance.filtro_normas})",
                    alcance.params,
                )
        conn.commit()
    return total


def extraer_reglas_de_pdfs(cur, filtro_normas: str, params: tuple) -> int:
    """Reemplaza las reglas del alcance (`filtro_normas`, sobre `territorio.norma n`)
    por las que se leen de sus artículos. Cada regla se guarda con
    `fuente='pdf_extraido'` y el artículo del que salió."""
    cur.execute(
        "DELETE FROM territorio.regla_distancia WHERE norma_id IN "
        f"(SELECT n.id FROM territorio.norma n WHERE {filtro_normas})",
        params,
    )
    cur.execute(
        "SELECT a.id, a.numero, a.texto, n.id, n.archivo FROM territorio.articulo a "
        f"JOIN territorio.norma n ON n.id = a.norma_id WHERE {filtro_normas} "
        "ORDER BY n.id, a.id",
        params,
    )
    articulos = cur.fetchall()
    total = 0
    for articulo_id, numero, texto, norma_id, archivo in articulos:
        for regla in extraer_reglas_de_articulo(archivo, numero, texto):
            cur.execute(
                """
                INSERT INTO territorio.regla_distancia
                    (norma_id, articulo_id, tipo_zona, tipo_aplicacion, bandas,
                     distancia_min_m, observaciones, fuente)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'pdf_extraido')
                """,
                (
                    norma_id, articulo_id, regla.tipo_zona, regla.tipo_aplicacion,
                    regla.bandas, regla.distancia_min_m, None,
                ),
            )
            logger.info("%s art. %s: %s", archivo, numero, regla.oracion)
            total += 1
    logger.info("%d reglas leídas de %d artículos (%s)", total, len(articulos), params)
    return total


# Palabras con que un operario nombra cada cosa: van en el texto de la regla para que la
# búsqueda por similitud la encuentre aunque la pregunta no use el término de la norma.
_ZONA = {
    "zona_urbana": "la zona urbana (planta urbana, pueblo, ciudad, casas)",
    "escuela": "escuelas (establecimientos educativos, escuela rural)",
    "curso_agua": "cursos de agua (arroyos, ríos, lagunas, canales)",
    "otro": "otras zonas protegidas",
}
_APLICACION = {
    "aerea": "aplicación aérea (avión, avioneta, fumigación aérea)",
    "terrestre": "aplicación terrestre (equipo terrestre, mosquito, pulverizadora)",
    "todas": "cualquier tipo de aplicación, aérea o terrestre",
}


def _bandas_con_color(bandas: list[str]) -> str:
    if bandas == ["todas"]:
        return "todas las bandas toxicológicas"
    return "bandas " + ", ".join(f"{b} ({COLOR_BANDA.get(b, '?')})" for b in bandas)


def texto_de_regla(
    lugar: str, tipo_zona: str, tipo_aplicacion: str, bandas: list[str], distancia_m: float,
    permitido: bool, condiciones: str | None, norma: str, articulo: str | None,
) -> str:
    """La regla como una oración, con los sinónimos de la zona, la aplicación y las
    bandas. Es lo que se embebe; nunca se le muestra al operario."""
    zona = _ZONA.get(tipo_zona, tipo_zona.replace("_", " "))
    distancia = f"{distancia_m:g}"
    if permitido:
        desde = f"desde {distancia} m de {zona}" if distancia_m else f"cerca de {zona}"
        regla = f"se permite aplicar {desde} con condiciones: {condiciones or 'según la norma'}"
    elif distancia_m >= DISTANCIA_SIN_LIMITE_M:
        regla = "prohibido aplicar en toda la jurisdicción"
    else:
        regla = f"prohibido aplicar a menos de {distancia} m de {zona}"
    fuente = norma_legible(norma) + (f", art. {articulo}" if articulo else "")
    return (
        f"{lugar} · {_APLICACION.get(tipo_aplicacion, tipo_aplicacion)} · "
        f"{_bandas_con_color(bandas)}: {regla} ({fuente})"
    )


def indexar_reglas(conn: psycopg.Connection, modelo_embeddings) -> int:
    """Texto + embedding de todas las reglas cargadas (se recalculan siempre: son pocas)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT r.id, COALESCE(l.nombre, p.nombre, 'Argentina'), r.tipo_zona,
                   r.tipo_aplicacion, r.bandas, r.distancia_min_m, r.permitido,
                   r.condiciones, n.archivo, a.numero
            FROM territorio.regla_distancia r
            JOIN territorio.norma n ON n.id = r.norma_id
            LEFT JOIN territorio.articulo a ON a.id = r.articulo_id
            LEFT JOIN territorio.localidad l ON l.id = n.localidad_id
            LEFT JOIN territorio.provincia p ON p.id = n.provincia_id
            ORDER BY r.id
            """
        )
        filas = cur.fetchall()
        if not filas:
            return 0
        textos = [
            texto_de_regla(lugar, zona, aplicacion, list(bandas), float(distancia),
                           permitido, condiciones, norma, articulo)
            for (_, lugar, zona, aplicacion, bandas, distancia, permitido, condiciones,
                 norma, articulo) in filas
        ]
        embeddings = modelo_embeddings.encode(textos, batch_size=32)
        for (regla_id, *_), texto, embedding in zip(filas, textos, embeddings, strict=True):
            cur.execute(
                "UPDATE territorio.regla_distancia SET texto = %s, embedding = %s::vector"
                " WHERE id = %s",
                (texto, vector_literal(embedding.tolist()), regla_id),
            )
    conn.commit()
    return len(filas)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--database-url", type=str, default=None)
    args = parser.parse_args()

    settings = get_settings()
    db_url = args.database_url or settings.database_url
    from sentence_transformers import SentenceTransformer

    with psycopg.connect(db_url) as conn:
        total = cargar_reglas(conn, args.data)
        indexadas = indexar_reglas(conn, SentenceTransformer(settings.embeddings_model))
    logger.info("Reglas cargadas: %d (indexadas para la búsqueda: %d)", total, indexadas)


if __name__ == "__main__":
    main()
