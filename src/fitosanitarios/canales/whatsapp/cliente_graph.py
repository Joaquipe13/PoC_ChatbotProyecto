"""Cliente de WhatsApp Cloud API (Graph API): envío de texto, botones y
listas, y descarga de media (ver skill, "Canal WhatsApp: gotchas" y
plandefases.md Fase 8, tareas 6 y 8).

Las funciones `_payload_*` arman el cuerpo del request y validan los límites
de la API (máx. 3 botones, título ≤ 20 caracteres; máx. 10 filas en listas)
sin hacer ninguna llamada de red, para poder testearlas sin mockear HTTP.
"""

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from fitosanitarios.config import Settings

MAX_BOTONES = 3
MAX_LARGO_TITULO_BOTON = 20
MAX_FILAS_LISTA = 10
MAX_TAMANO_IMAGEN_BYTES = 5 * 1024 * 1024


class ErrorEnvioWhatsApp(Exception):
    """La Graph API devolvió un error al enviar un mensaje."""


class ErrorMediaWhatsApp(Exception):
    """No se pudo descargar un media de WhatsApp (venció la URL, supera el
    tamaño permitido, etc.)."""


def _url_mensajes(settings: Settings) -> str:
    return (
        f"https://graph.facebook.com/{settings.whatsapp_graph_version}"
        f"/{settings.whatsapp_phone_number_id}/messages"
    )


def _url_media(settings: Settings, media_id: str) -> str:
    return f"https://graph.facebook.com/{settings.whatsapp_graph_version}/{media_id}"


def _headers(settings: Settings) -> dict:
    return {"Authorization": f"Bearer {settings.whatsapp_access_token}"}


def _payload_texto(to: str, texto: str) -> dict:
    return {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": texto}}


def _payload_botones(to: str, texto: str, botones: list[dict]) -> dict:
    """`botones`: lista de `{"id": ..., "titulo": ...}`, máx. 3, título ≤ 20
    caracteres (límite de la Graph API)."""
    if not botones or len(botones) > MAX_BOTONES:
        raise ValueError(
            f"se necesitan entre 1 y {MAX_BOTONES} botones, se recibieron {len(botones)}"
        )
    for boton in botones:
        if len(boton["titulo"]) > MAX_LARGO_TITULO_BOTON:
            raise ValueError(
                f"título de botón demasiado largo (máx. {MAX_LARGO_TITULO_BOTON}): "
                f"{boton['titulo']!r}"
            )
    return {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": texto},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": b["id"], "title": b["titulo"]}}
                    for b in botones
                ]
            },
        },
    }


def _payload_lista(to: str, texto: str, titulo_boton: str, filas: list[dict]) -> dict:
    """`filas`: lista de `{"id": ..., "titulo": ..., "descripcion": ...}`,
    máx. 10 (límite de la Graph API)."""
    if not filas or len(filas) > MAX_FILAS_LISTA:
        raise ValueError(
            f"se necesitan entre 1 y {MAX_FILAS_LISTA} filas, se recibieron {len(filas)}"
        )
    return {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": texto},
            "action": {
                "button": titulo_boton,
                "sections": [
                    {
                        "rows": [
                            {
                                "id": f["id"],
                                "title": f["titulo"],
                                "description": f.get("descripcion", ""),
                            }
                            for f in filas
                        ]
                    }
                ],
            },
        },
    }


@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(2),
    retry=retry_if_exception_type(httpx.TransportError),
    reraise=True,
)
def _post(settings: Settings, payload: dict) -> httpx.Response:
    """Reintento simple ante error transitorio de red (ver plan, tarea 8).
    Un 4xx/5xx de la Graph API en sí no se reintenta acá -- lo maneja el
    llamador chequeando el status code."""
    return httpx.post(
        _url_mensajes(settings), headers=_headers(settings), json=payload, timeout=10.0
    )


def _enviar(settings: Settings, payload: dict) -> None:
    resp = _post(settings, payload)
    if resp.status_code >= 400:
        raise ErrorEnvioWhatsApp(f"Graph API devolvió {resp.status_code}: {resp.text}")


def enviar_texto(settings: Settings, to: str, texto: str) -> None:
    _enviar(settings, _payload_texto(to, texto))


def enviar_mensajes(settings: Settings, to: str, mensajes: list[str]) -> None:
    """Envía cada elemento de la lista ya partida por el formateador (ver
    `orquestador/formateador.py::formatear_respuesta`) como un mensaje de
    texto separado, en orden."""
    for mensaje in mensajes:
        enviar_texto(settings, to, mensaje)


def enviar_botones(settings: Settings, to: str, texto: str, botones: list[dict]) -> None:
    _enviar(settings, _payload_botones(to, texto, botones))


def enviar_lista(
    settings: Settings, to: str, texto: str, titulo_boton: str, filas: list[dict]
) -> None:
    _enviar(settings, _payload_lista(to, texto, titulo_boton, filas))


def obtener_url_media(settings: Settings, media_id: str) -> str:
    """La URL devuelta vence a los 5 minutos (ver skill) -- usar enseguida."""
    resp = httpx.get(_url_media(settings, media_id), headers=_headers(settings), timeout=10.0)
    if resp.status_code >= 400:
        raise ErrorMediaWhatsApp(
            f"no se pudo resolver la URL del media {media_id}: {resp.status_code}"
        )
    return resp.json()["url"]


def descargar_media(settings: Settings, media_id: str) -> bytes:
    """Descarga JPEG/PNG hasta 5 MB (ver skill). El tipo de contenido no se
    valida acá contra JPEG/PNG -- lo valida `extraccion_receta.py` al
    intentar leer la imagen; acá solo se corta por tamaño para no cargar en
    memoria un archivo desproporcionado."""
    url = obtener_url_media(settings, media_id)
    resp = httpx.get(url, headers=_headers(settings), timeout=15.0)
    if resp.status_code >= 400:
        raise ErrorMediaWhatsApp(f"no se pudo descargar el media {media_id}: {resp.status_code}")
    contenido = resp.content
    if len(contenido) > MAX_TAMANO_IMAGEN_BYTES:
        raise ErrorMediaWhatsApp(f"imagen de {len(contenido)} bytes supera el máximo de 5 MB")
    return contenido
