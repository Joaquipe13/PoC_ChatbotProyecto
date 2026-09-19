"""Estructura de carpetas de `data/insumos/` (ver docs/contrato-insumos.md).

```
data/insumos/
├── <provincia>/                 normativa provincial: PDFs y reglas.csv acá
│   └── <localidad>/             normativa municipal + localidad.geojson
└── normativa-general/nacional/
```

Un solo lugar que sabe recorrerla: el validador y los tres loaders la
usan, así no se repite (ni se desincroniza) la convención de carpetas.
"""

from pathlib import Path

CARPETA_GENERAL = "normativa-general"


def _subcarpetas(ruta: Path) -> list[Path]:
    if not ruta.exists():
        return []
    return sorted(
        p for p in ruta.iterdir()
        if p.is_dir() and not p.name.startswith((".", "_"))
    )


def carpetas_provincia(data_dir: Path) -> list[Path]:
    """Cada carpeta de primer nivel salvo la de normativa general."""
    return [p for p in _subcarpetas(data_dir) if p.name != CARPETA_GENERAL]


def carpetas_localidad(provincia_dir: Path) -> list[Path]:
    return _subcarpetas(provincia_dir)


def localidades(data_dir: Path) -> list[tuple[Path, Path]]:
    """(carpeta de la provincia, carpeta de la localidad) de todas las cargadas."""
    return [
        (provincia, localidad)
        for provincia in carpetas_provincia(data_dir)
        for localidad in carpetas_localidad(provincia)
    ]


def carpeta_nacional(data_dir: Path) -> Path:
    return data_dir / CARPETA_GENERAL / "nacional"
