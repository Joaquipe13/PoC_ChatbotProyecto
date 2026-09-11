"""Corre el crawler de SENASA: listado completo + detalle de una muestra.

Uso:
    uv run python scripts/crawl_senasa.py --listado-completo
    uv run python scripts/crawl_senasa.py --detalle-muestra 150

El detalle de TODO el catálogo (~7370 productos) no se corre en este script
tal cual: a ~1 req/s son varias horas. Fase 2, tarea 1 del plan pide
justamente estimar el volumen con una corrida chica antes del crawl completo
-- eso es lo que hace `--detalle-muestra`. Para el crawl completo, correr
este mismo script con `--detalle-completo` como job de fondo (ver
DIFICULTADES.md).
"""

import argparse
import logging
from pathlib import Path

from fitosanitarios.config import get_settings
from fitosanitarios.senasa.cliente import ClienteSenasa
from fitosanitarios.senasa.crawler import (
    crawl_detalle,
    crawl_listado_completo,
    guardar_listado_jsonl,
    leer_listado_jsonl,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "senasa" / "crudo"
RUTA_LISTADO = DATA_DIR / "listado.jsonl"
RUTA_DETALLE = DATA_DIR / "detalle.jsonl"
RUTA_CHECKPOINT = DATA_DIR / "checkpoint_detalle.txt"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listado-completo", action="store_true")
    parser.add_argument("--detalle-muestra", type=int, default=0, help="cantidad de ids a bajar")
    parser.add_argument("--detalle-completo", action="store_true")
    parser.add_argument("--paso-muestra", type=int, default=1, help="tomar 1 de cada N ids")
    args = parser.parse_args()

    settings = get_settings()
    cliente = ClienteSenasa(base_url=settings.senasa_base_url)

    if args.listado_completo:
        productos = crawl_listado_completo(
            cliente, size=100, segundos_entre_requests=settings.senasa_req_por_seg
        )
        guardar_listado_jsonl(productos, RUTA_LISTADO)
        logger.info("Listado guardado: %d productos en %s", len(productos), RUTA_LISTADO)

    if args.detalle_muestra or args.detalle_completo:
        if not RUTA_LISTADO.exists():
            raise SystemExit(
                "Corré primero --listado-completo (falta data/senasa/crudo/listado.jsonl)"
            )
        productos = leer_listado_jsonl(RUTA_LISTADO)
        ids = [p.id for p in productos[:: args.paso_muestra]]
        if args.detalle_muestra:
            ids = ids[: args.detalle_muestra]
        logger.info("Bajando detalle de %d productos", len(ids))
        fallidos = crawl_detalle(
            cliente, ids, RUTA_DETALLE, RUTA_CHECKPOINT,
            segundos_entre_requests=settings.senasa_req_por_seg,
        )
        logger.info("Detalle terminado. Fallidos: %d %s", len(fallidos), fallidos)

    cliente.close()


if __name__ == "__main__":
    main()
