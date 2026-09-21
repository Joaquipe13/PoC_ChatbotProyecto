"""Lo que ve el LLM de `consultar_articulo` y de `listar_limitaciones` tras llamarlas."""

import pytest

from fitosanitarios.dominio.modelos import CampoFaltante, ResultadoTool
from fitosanitarios.tools.consultar_articulo import mensajes as mensajes_articulo
from fitosanitarios.tools.listar_limitaciones import mensajes as mensajes_limitaciones


def _pide_la_norma() -> ResultadoTool:
    return ResultadoTool(estado="faltan_datos", faltantes=[CampoFaltante(
        campo="norma", motivo="varias", pregunta_sugerida="¿De cuál?", tipo_entrada="lista",
    )])


@pytest.mark.parametrize("mensajes", [mensajes_articulo, mensajes_limitaciones])
def test_si_la_tool_pidio_un_dato_el_llm_recibe_que_falta_y_que_no_reintente(mensajes):
    resumen = mensajes.resumen_para_llm(_pide_la_norma())
    assert "estado=faltan_datos" in resumen and "Falta: norma" in resumen
    assert "no vuelvas a llamar" in resumen


@pytest.mark.parametrize("mensajes", [mensajes_articulo, mensajes_limitaciones])
def test_si_no_falta_nada_solo_informa_el_estado(mensajes):
    assert mensajes.resumen_para_llm(ResultadoTool(estado="ok")).endswith("estado=ok")
