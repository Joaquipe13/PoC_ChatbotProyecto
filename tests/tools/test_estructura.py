"""La convención de `tools/`: cada tool es una carpeta con su script base, sus
prompts y sus mensajes en archivos aparte (ver DECISIONES.md).

    tools/<tool>/
        __init__.py   exporta la tool, sus argumentos y su lógica
        tool.py       el script base: argumentos, lógica y la tool de LangChain
        prompts.py    lo que lee un LLM: la descripción de la tool y, si los hay, sus prompts
        mensajes.py   lo que lee el operario: preguntas, avisos y la plantilla de la respuesta
        utils.py      los auxiliares que solo usa esta tool (si los tiene)

Lo que usan varias tools no va en `tools/`: está en `servicios/`.
"""

import importlib
import inspect
from pathlib import Path

import pytest

import fitosanitarios.tools as paquete_tools
from fitosanitarios.orquestador.agente import TOOLS

RAIZ = Path(paquete_tools.__file__).parent
CARPETAS = sorted(p.name for p in RAIZ.iterdir() if p.is_dir() and not p.name.startswith("__"))


def test_todas_las_tools_del_agente_tienen_su_carpeta():
    assert sorted(t.name for t in TOOLS) == CARPETAS


def test_no_hay_scripts_sueltos_en_tools():
    sueltos = [p.name for p in RAIZ.glob("*.py") if p.name != "__init__.py"]
    assert sueltos == [], f"lo común va en servicios/, cada tool en su carpeta: {sueltos}"


@pytest.mark.parametrize("nombre", CARPETAS)
def test_cada_tool_tiene_su_script_base_sus_prompts_y_sus_mensajes(nombre):
    carpeta = RAIZ / nombre
    for archivo in ("__init__.py", "tool.py", "prompts.py", "mensajes.py"):
        assert (carpeta / archivo).exists(), f"falta tools/{nombre}/{archivo}"


@pytest.mark.parametrize("nombre", CARPETAS)
def test_la_descripcion_que_ve_el_llm_sale_de_prompts(nombre):
    """El "cuándo usar" de cada tool vive en `prompts.py`, no en un docstring."""
    prompts = importlib.import_module(f"fitosanitarios.tools.{nombre}.prompts")
    herramienta = next(t for t in TOOLS if t.name == nombre)
    assert herramienta.description == inspect.cleandoc(prompts.DESCRIPCION)


@pytest.mark.parametrize("nombre", CARPETAS)
def test_el_paquete_exporta_la_tool_su_argumento_y_su_logica(nombre):
    paquete = importlib.import_module(f"fitosanitarios.tools.{nombre}")
    publicos = set(dir(paquete))
    assert nombre in publicos
    assert any(n.endswith("Args") for n in publicos)
    assert any(n.endswith("_logica") for n in publicos)


@pytest.mark.parametrize("nombre", CARPETAS)
def test_una_tool_no_depende_de_otra(nombre):
    """Lo que dos tools comparten se sube a `servicios/`; ninguna importa de otra."""
    otras = [c for c in CARPETAS if c != nombre]
    for archivo in (RAIZ / nombre).glob("*.py"):
        texto = archivo.read_text(encoding="utf-8")
        for otra in otras:
            assert f"fitosanitarios.tools.{otra}" not in texto, (
                f"{archivo.relative_to(RAIZ)} importa de la tool {otra}"
            )
