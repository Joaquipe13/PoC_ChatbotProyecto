"""Cuándo una receta de foto quedó confirmada (ver `servicios/confirmacion.py`)."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from fitosanitarios.servicios.confirmacion import es_confirmacion, hay_receta_sin_confirmar


def usuario(texto):
    return HumanMessage(content=texto)


def llama(nombre, **args):
    return AIMessage(content="", tool_calls=[{"name": nombre, "args": args, "id": f"c-{nombre}"}])


def respuesta(tipo):
    return llama("RespuestaAgente", tipo=tipo)


FOTO = [usuario("Te mando la foto de mi receta."), llama("leer_receta"),
        ToolMessage(content="Receta leída", tool_call_id="c-leer_receta"),
        respuesta("confirmacion_receta")]


@pytest.mark.parametrize("texto", [
    "Confirmar", "confirmo", "dale", "sí", "si", "ok", "esta bien", "todo bien", "perfecto",
    "el lote esta en el trebol. confirmo", "listo, evaluala",
])
def test_estas_respuestas_confirman(texto):
    assert es_confirmacion(texto) is True


@pytest.mark.parametrize("texto", [
    "el trebol", "El Trébol", "corregir", "asi como esta", "no", "35 ha", "mas info",
    "el cultivo es maiz", "",
])
def test_estas_no_confirman(texto):
    assert es_confirmacion(texto) is False


def test_sin_receta_de_foto_no_hay_nada_pendiente():
    assert hay_receta_sin_confirmar([usuario("quiero evaluar Flyer en soja")]) is False


def test_receta_mostrada_y_sin_aceptar_esta_pendiente():
    """El caso real: el usuario contestó solo la localidad."""
    assert hay_receta_sin_confirmar([*FOTO, usuario("el trebol")]) is True


def test_receta_aceptada_ya_no_esta_pendiente():
    con_dato = usuario("el lote esta en el trebol. confirmo")
    assert hay_receta_sin_confirmar([*FOTO, con_dato]) is False
    assert hay_receta_sin_confirmar([*FOTO, usuario("Confirmar")]) is False


def test_si_la_acepto_en_un_turno_anterior_una_nueva_evaluacion_no_esta_bloqueada():
    historial = [*FOTO, usuario("Confirmar"), respuesta("dictamen"), usuario("mas info"),
                 respuesta("detalle_bandas"), usuario("y si cambio la localidad?")]
    assert hay_receta_sin_confirmar(historial) is False


def test_leer_la_receta_y_evaluar_en_el_mismo_turno_esta_pendiente():
    """La confirmación todavía ni se mostró: no se puede haber aceptado."""
    en_el_mismo_turno = [usuario("Te mando la foto de mi receta."), llama("leer_receta"),
                         ToolMessage(content="Receta leída", tool_call_id="c-leer_receta"),
                         llama("evaluar_viabilidad_legal")]
    assert hay_receta_sin_confirmar(en_el_mismo_turno) is True


def test_una_correccion_no_es_una_confirmacion_y_la_nueva_confirmacion_se_puede_aceptar():
    historial = [*FOTO, usuario("corregir"), usuario("el cultivo es maiz")]
    assert hay_receta_sin_confirmar(historial) is True
    historial += [respuesta("confirmacion_receta"), usuario("dale")]
    assert hay_receta_sin_confirmar(historial) is False
