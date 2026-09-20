"""Canal web (Fase 11): GUI de chat servida por FastAPI, alternativa al
canal WhatsApp (Fase 8) para probar el agente sin depender del número de
prueba de Meta -- ver DECISIONES.md. Reutiliza el mismo orquestador; solo
cambia el transporte.

A diferencia del webhook de WhatsApp (que debe responder 200 de inmediato y
procesar en background, ver skill "Canal WhatsApp: gotchas"), acá el
navegador espera la respuesta en la misma request: `procesar_mensaje`
devuelve directamente los mensajes en vez de enviarlos por su cuenta.

`crear_app` recibe `procesar_mensaje` inyectado, igual que
`canales/whatsapp/webhook.py::crear_app`, para poder testear el protocolo
HTTP sin un LLM ni una conexión real."""

import logging
from collections.abc import Callable

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from fitosanitarios.canales.web.pagina import PAGINA_CHAT
from fitosanitarios.config import Settings

logger = logging.getLogger(__name__)

# (session_id, texto, imagen_base64) -> mensajes de respuesta ya formateados.
ProcesadorMensajeWeb = Callable[[str, str, str | None], list[str]]


class MensajeEntrante(BaseModel):
    session_id: str
    texto: str = ""
    imagen_base64: str | None = None


def texto_final(mensaje: MensajeEntrante) -> str:
    """Una foto sin texto nunca llega al agente como string vacío: un
    `HumanMessage` sin contenido no dispara ninguna tool y el agente cae en la
    respuesta genérica de ayuda (bug real, encontrado probando el canal web
    con una foto de receta sin escribir nada; ver DIFICULTADES.md). La
    ubicación del lote ya no se manda: la normativa se elige por localidad."""
    if mensaje.imagen_base64 and not mensaje.texto.strip():
        return "Te mando la foto de mi receta."
    return mensaje.texto


def crear_app(settings: Settings, procesar_mensaje: ProcesadorMensajeWeb) -> FastAPI:
    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return PAGINA_CHAT

    @app.post("/api/mensaje")
    def recibir(mensaje: MensajeEntrante) -> dict:
        texto = texto_final(mensaje)
        if not texto.strip() and not mensaje.imagen_base64:
            return {"mensajes": []}
        mensajes = procesar_mensaje(mensaje.session_id, texto, mensaje.imagen_base64)
        return {"mensajes": mensajes}

    return app
