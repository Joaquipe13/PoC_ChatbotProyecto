"""Webhook de WhatsApp Cloud API: handshake (`GET`) y recepción de mensajes
(`POST`), ver skill "Canal WhatsApp: gotchas" y plandefases.md Fase 8.

`crear_app` recibe `procesar_mensaje` inyectado (en vez de construirlo acá
adentro) para poder testear el comportamiento del webhook en sí -- firma,
handshake, deduplicación, mensajes `statuses` ignorados -- sin necesitar un
LLM ni una conexión real por test; `app_produccion.py` es el que arma la
versión real (agente + Postgres + cliente Graph) para correr el servidor.
"""

import base64
import hashlib
import hmac
import json
import logging
from collections.abc import Callable

import psycopg
from fastapi import BackgroundTasks, FastAPI, Header, Request, Response
from starlette.concurrency import run_in_threadpool

from fitosanitarios.canales.whatsapp.dedup import ya_procesado
from fitosanitarios.config import Settings

logger = logging.getLogger(__name__)

TIPOS_INTERACTIVE_SOPORTADOS = {"button_reply", "list_reply"}
MENSAJE_TIPO_NO_SOPORTADO = (
    "Por ahora no puedo procesar ese tipo de mensaje. Mandame texto, "
    "una foto de la receta o tu ubicación."
)

ProcesadorMensaje = Callable[[dict, str], None]


def verificar_firma(cuerpo: bytes, firma_header: str | None, app_secret: str) -> bool:
    """Valida `X-Hub-Signature-256` en tiempo constante (ver skill). Una
    firma ausente (no solo inválida) también se rechaza -- ver plan, "casos
    borde"."""
    if not firma_header or not firma_header.startswith("sha256="):
        return False
    firma_recibida = firma_header.removeprefix("sha256=")
    firma_esperada = hmac.new(app_secret.encode(), cuerpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(firma_esperada, firma_recibida)


def mensajes_con_remitente(payload: dict) -> list[tuple[dict, str]]:
    """Recorre `entry[].changes[].value.messages[]` e ignora los `value`
    que solo traen `statuses` (confirmaciones de entrega, no mensajes; ver
    skill). Devuelve pares `(mensaje, numero_from)`."""
    resultado = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for mensaje in value.get("messages", []):
                resultado.append((mensaje, mensaje.get("from", "")))
    return resultado


def tipo_soportado(mensaje: dict) -> bool:
    tipo = mensaje.get("type")
    if tipo not in {"text", "image", "location", "interactive"}:
        return False
    if tipo == "interactive":
        return mensaje.get("interactive", {}).get("type") in TIPOS_INTERACTIVE_SOPORTADOS
    return True


def texto_e_imagen(
    mensaje: dict, descargar_imagen: Callable[[str], bytes]
) -> tuple[str, str | None]:
    """A partir de un mensaje ya soportado (`tipo_soportado`), arma el texto
    de entrada para el orquestador y, si es una foto, la baja y la devuelve
    en base64 (ver `orquestador/agente.py::construir_tools`)."""
    tipo = mensaje["type"]
    if tipo == "text":
        return mensaje["text"]["body"], None
    if tipo == "location":
        loc = mensaje["location"]
        return f"Mi ubicación: latitud {loc['latitude']}, longitud {loc['longitude']}", None
    if tipo == "interactive":
        inter = mensaje["interactive"]
        if inter["type"] == "button_reply":
            return inter["button_reply"]["title"], None
        return inter["list_reply"]["title"], None
    # image
    media_id = mensaje["image"]["id"]
    contenido = descargar_imagen(media_id)
    texto = mensaje["image"].get("caption") or "Te mando la foto de mi receta."
    return texto, base64.b64encode(contenido).decode()


def _ya_procesado_conectando(settings: Settings, message_id: str) -> bool:
    with psycopg.connect(settings.database_url) as conn:
        return ya_procesado(conn, message_id)


def crear_app(settings: Settings, procesar_mensaje: ProcesadorMensaje) -> FastAPI:
    """`procesar_mensaje(mensaje, numero_from)` hace todo el trabajo real
    (bajar imagen si corresponde, correr el turno, enviar la respuesta); acá
    solo se orquesta el protocolo del webhook."""
    app = FastAPI()

    @app.get("/webhook")
    def handshake(request: Request) -> Response:
        params = request.query_params
        if (
            params.get("hub.mode") == "subscribe"
            and params.get("hub.verify_token") == settings.whatsapp_verify_token
        ):
            return Response(content=params.get("hub.challenge", ""), media_type="text/plain")
        logger.warning(
            "Handshake del webhook rechazado: el token de verificación no coincide con "
            "WHATSAPP_VERIFY_TOKEN del .env (revisalo en Meta > WhatsApp > Configuración)."
        )
        return Response(status_code=403)

    @app.post("/webhook")
    async def recibir(
        request: Request,
        background_tasks: BackgroundTasks,
        x_hub_signature_256: str | None = Header(default=None),
    ) -> Response:
        cuerpo = await request.body()
        if not verificar_firma(cuerpo, x_hub_signature_256, settings.whatsapp_app_secret):
            # Sin este aviso, un WHATSAPP_APP_SECRET mal cargado dejaba al bot sin
            # contestar y sin ninguna pista en la consola.
            logger.warning(
                "Mensaje rechazado por firma inválida: revisá WHATSAPP_APP_SECRET en .env "
                "(Meta > tu app > Configuración > Básica > Clave secreta de la app)."
            )
            return Response(status_code=401)

        payload = json.loads(cuerpo)
        for mensaje, numero_from in mensajes_con_remitente(payload):
            message_id = mensaje.get("id", "")
            # run_in_threadpool: psycopg es bloqueante, no se puede await
            # directo dentro del handler async sin trabar el event loop.
            repetido = await run_in_threadpool(_ya_procesado_conectando, settings, message_id)
            if repetido:
                logger.info("Mensaje %s ya procesado, se ignora el reintento", message_id)
                continue
            # 200 inmediato, procesamiento en background (ver skill).
            background_tasks.add_task(procesar_mensaje, mensaje, numero_from)

        return Response(status_code=200)

    return app
