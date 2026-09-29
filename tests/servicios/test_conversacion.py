"""Lo dicho en la conversación, para verificar que un dato que pasó el LLM salió de ahí."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from fitosanitarios.servicios.conversacion import lo_dicho_en_la_conversacion, se_menciona


def test_cuenta_lo_del_operario_y_de_las_tools_pero_no_lo_que_escribio_el_llm():
    dicho = lo_dicho_en_la_conversacion([
        HumanMessage("¿Puedo aplicar Metsulfurón en El Trébol?"),
        AIMessage("", tool_calls=[{"name": "x", "args": {"cultivo": "trigo"}, "id": "1"}]),
        AIMessage("Supongo que es para trigo"),
        ToolMessage("Receta leída. Cultivo: Soja", tool_call_id="1"),
        HumanMessage([{"type": "text", "text": "y la foto"}, {"type": "image_url"}]),
    ])
    assert se_menciona("metsulfuron", dicho)
    assert se_menciona("soja", dicho)  # de la receta que leyó una tool
    assert se_menciona("foto", dicho)
    assert not se_menciona("trigo", dicho)


def test_se_menciona_tolera_el_plural():
    dicho = lo_dicho_en_la_conversacion([HumanMessage("qué hay para los trigos")])
    assert se_menciona("trigo", dicho) and se_menciona("Trigos", dicho)
    assert not se_menciona("", dicho)
