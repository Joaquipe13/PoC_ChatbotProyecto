"""Regenera tests/fixtures/insumos/ como copia congelada de data/insumos/.

Desde el 26/09/2026 los tests usan los insumos reales (El Trébol, Sastre, San Jorge,
la Ley 11.273 y su decreto), no localidades inventadas (ver DECISIONES.md). Correrlo
después de cambiar los insumos reales, y revisar el diff: los tests que citan hechos
de esas normas pueden tener que actualizarse.

Los borradores de reglas (`reglas.borrador*`) no se copian.

Uso: uv run python scripts/generar_fixtures_insumos.py
"""

import shutil
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ORIGEN = RAIZ / "data" / "insumos"
DESTINO = RAIZ / "tests" / "fixtures" / "insumos"


def main() -> None:
    if not ORIGEN.is_dir():
        raise SystemExit(f"No existe {ORIGEN}: no hay insumos reales para copiar.")
    if DESTINO.exists():
        shutil.rmtree(DESTINO)
    shutil.copytree(ORIGEN, DESTINO, ignore=shutil.ignore_patterns("reglas.borrador*"))
    archivos = sum(1 for f in DESTINO.rglob("*") if f.is_file())
    print(f"{archivos} archivos copiados a {DESTINO.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
