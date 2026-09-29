"""El canal notebook (`canales/notebook.py`) con un modelo falso: sin Gemini ni Postgres."""

from langgraph.checkpoint.memory import InMemorySaver

from fitosanitarios.canales.notebook import (
    TEXTO_DE_UNA_FOTO_SOLA,
    Conversacion,
    a_markdown,
    texto_final,
)
from tests.orquestador.fake_chat_model import ChatModelFake, mensaje_respuesta_estructurada


def _conversacion(*respuestas):
    modelo = ChatModelFake(respuestas=list(respuestas))
    conversacion = Conversacion(
        modelo=modelo, respaldo=[], checkpointer=InMemorySaver(), registrar_turnos=False
    )
    return conversacion, modelo


def test_un_mensaje_de_texto_devuelve_la_respuesta_del_bot():
    conversacion, _ = _conversacion(mensaje_respuesta_estructurada({"tipo": "ayuda"}))
    mensajes = conversacion.enviar("hola")
    assert mensajes and mensajes[0].startswith("Hola")


def test_la_conversacion_recuerda_los_turnos_y_nueva_arranca_otra():
    conversacion, modelo = _conversacion(
        mensaje_respuesta_estructurada({"tipo": "ayuda"}),
        mensaje_respuesta_estructurada({"tipo": "ayuda"}),
        mensaje_respuesta_estructurada({"tipo": "ayuda"}),
    )
    primera = conversacion.thread_id
    conversacion.enviar("hola")
    conversacion.enviar("¿y qué más?")
    assert len(modelo.llamadas[1]) > len(modelo.llamadas[0])  # el historial viajó
    assert conversacion.nueva() != primera
    conversacion.enviar("hola de nuevo")
    assert len(modelo.llamadas[2]) < len(modelo.llamadas[1])


def test_un_mensaje_vacio_no_llama_al_bot():
    conversacion, modelo = _conversacion()
    assert conversacion.enviar("   ") == []
    assert modelo.llamadas == []


def test_una_foto_sin_texto_usa_el_texto_generico():
    assert texto_final("", con_foto=True) == TEXTO_DE_UNA_FOTO_SOLA
    assert texto_final("te paso la receta", con_foto=True) == "te paso la receta"
    assert texto_final("", con_foto=False) == ""


def test_el_formato_de_whatsapp_pasa_a_markdown():
    texto = a_markdown("*Dictamen* — lote 4\n✅ _APTA_\n¿Agendamos?\n[Agendar] [No, gracias]")
    assert texto == (
        "**Dictamen** — lote 4  \n✅ *APTA*  \n¿Agendamos?  \n`[Agendar]` `[No, gracias]`"
    )
