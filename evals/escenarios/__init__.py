"""Catálogo de escenarios de la simulación (`evals/escenarios/*.yaml`).

Cada escenario es lo ÚNICO que el simulador sabe: quién es, qué quiere, de qué datos
dispone y cómo se comporta. No lleva el código, el prompt del sistema, las reglas ni las
respuestas esperadas. Las `expectativas_duras` y las `tools_esperadas` son para
`evals/invariantes.py` y `evals/metricas.py`: el simulador no las recibe.

Campos: `id`, `persona`, `objetivo`, `datos`, `comportamiento`, `expectativas_duras`
(opcional), `tools_esperadas` (opcional), `conjunto` (`desarrollo` | `holdout`).
Los `holdout` solo sirven para medir: no se usan para decidir arreglos.
"""

from pathlib import Path

import yaml

DIRECTORIO = Path(__file__).parent
CAMPOS_PARA_EL_SIMULADOR = ("persona", "objetivo", "datos", "comportamiento")


def cargar(escenario_id: str, requerido: bool = True) -> dict:
    ruta = DIRECTORIO / f"{escenario_id}.yaml"
    if not ruta.exists():
        if requerido:
            raise FileNotFoundError(f"No existe el escenario {escenario_id}")
        return {}
    return yaml.safe_load(ruta.read_text(encoding="utf-8"))


def ids(conjunto: str | None = None) -> list[str]:
    todos = sorted(p.stem for p in DIRECTORIO.glob("*.yaml"))
    if conjunto is None:
        return todos
    return [i for i in todos if cargar(i).get("conjunto") == conjunto]


def para_el_simulador(escenario: dict) -> dict:
    """Solo lo que el simulador puede saber."""
    return {k: escenario[k] for k in CAMPOS_PARA_EL_SIMULADOR if k in escenario}
