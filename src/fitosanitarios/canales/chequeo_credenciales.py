"""Chequeo de credenciales al arrancar un canal (web o WhatsApp).

Sin esto, una credencial mal cargada recién se notaba con el primer mensaje, y
a veces ni eso: un token de WhatsApp vencido hacía que el bot procesara el
mensaje y la respuesta no llegara nunca, con el error solo en el log.

Qué se verifica:
- Postgres: que conecte y que el catálogo SENASA esté cargado.
- Gemini: cada `GEMINI_API_KEY_*` contra el modelo configurado (sin gastar
  cuota: solo se consulta el modelo, no se genera nada). La key 1 es la única
  que usa el agente (ver DECISIONES.md, rotación pendiente), así que si falla
  es un error; si falla otra, es un aviso.
- WhatsApp: que estén las 4 variables, y el token y el `phone_number_id`
  contra la Graph API. El `WHATSAPP_APP_SECRET` no se puede validar contra Meta
  sin el id de la app; si está mal, cada mensaje se rechaza con un aviso de
  "firma inválida" en la consola (ver `webhook.py`).

Con algún error, el servidor no arranca: se imprime el informe y se sale con
código 1, en vez de quedar prendido sin poder contestar.
"""

import sys
from dataclasses import dataclass, field

import httpx
import psycopg

from fitosanitarios.config import Settings

_URL_GEMINI = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}"
_URL_GRAPH = "https://graph.facebook.com/{version}/{phone_number_id}"
_TIMEOUT_S = 10.0


@dataclass
class Informe:
    ok: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)

    def texto(self, canal: str) -> str:
        lineas = [f"Chequeo de credenciales ({canal}):"]
        lineas += [f"  OK     {m}" for m in self.ok]
        lineas += [f"  AVISO  {m}" for m in self.avisos]
        lineas += [f"  ERROR  {m}" for m in self.errores]
        if self.errores:
            lineas.append(
                "El servidor no arranca: corregí los errores en .env y volvé a levantarlo."
            )
        return "\n".join(lineas)


def chequear_postgres(settings: Settings, informe: Informe) -> None:
    try:
        with psycopg.connect(settings.database_url, connect_timeout=5) as conn:
            productos = conn.execute("SELECT count(*) FROM catalogo.producto").fetchone()[0]
    except psycopg.Error as e:
        informe.errores.append(
            f"Postgres: no se pudo conectar ({_primera_linea(e)}). "
            "¿Está levantado? `docker compose up -d db`"
        )
        return
    if productos == 0:
        informe.avisos.append("Postgres: conecta, pero el catálogo SENASA está vacío.")
    else:
        informe.ok.append(f"Postgres: conecta, catálogo con {productos} productos.")


def chequear_gemini(settings: Settings, informe: Informe, cliente: httpx.Client) -> None:
    claves = [
        (i, clave)
        for i, clave in enumerate(
            (
                settings.gemini_api_key_1,
                settings.gemini_api_key_2,
                settings.gemini_api_key_3,
                settings.gemini_api_key_4,
                settings.gemini_api_key_5,
            ),
            start=1,
        )
        if clave
    ]
    if not settings.gemini_api_key_1:
        informe.errores.append("Gemini: falta GEMINI_API_KEY_1 (es la que usa el agente).")
    for i, clave in claves:
        problema = _problema_gemini(settings.gemini_model, clave, cliente)
        nombre = f"GEMINI_API_KEY_{i}"
        if problema is None:
            informe.ok.append(f"Gemini: {nombre} válida para {settings.gemini_model}.")
        elif i == 1:
            informe.errores.append(f"Gemini: {nombre} {problema}")
        else:
            informe.avisos.append(f"Gemini: {nombre} {problema} (el agente usa solo la key 1).")


def _problema_gemini(modelo: str, clave: str, cliente: httpx.Client) -> str | None:
    # La key va en un header y no en la URL: httpx loguea la URL de cada request.
    try:
        resp = cliente.get(
            _URL_GEMINI.format(modelo=modelo),
            headers={"x-goog-api-key": clave},
            timeout=_TIMEOUT_S,
        )
    except httpx.HTTPError as e:
        return f"no se pudo verificar: sin conexión con Google ({type(e).__name__})."
    if resp.status_code == 200:
        return None
    if resp.status_code == 404:
        return f"es válida, pero el modelo GEMINI_MODEL={modelo} no existe."
    if resp.status_code == 429:
        return "es válida, pero no tiene cuota disponible ahora (429)."
    if resp.status_code in (400, 401, 403):
        return f"es inválida o está deshabilitada ({_mensaje_error(resp)})."
    return f"respuesta inesperada de Google: {resp.status_code} ({_mensaje_error(resp)})."


def chequear_whatsapp(settings: Settings, informe: Informe, cliente: httpx.Client) -> None:
    faltantes = [
        nombre
        for nombre, valor in (
            ("WHATSAPP_ACCESS_TOKEN", settings.whatsapp_access_token),
            ("WHATSAPP_PHONE_NUMBER_ID", settings.whatsapp_phone_number_id),
            ("WHATSAPP_APP_SECRET", settings.whatsapp_app_secret),
            ("WHATSAPP_VERIFY_TOKEN", settings.whatsapp_verify_token),
        )
        if not valor
    ]
    if faltantes:
        informe.errores.append(f"WhatsApp: faltan en .env: {', '.join(faltantes)}.")
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        return

    try:
        resp = cliente.get(
            _URL_GRAPH.format(
                version=settings.whatsapp_graph_version,
                phone_number_id=settings.whatsapp_phone_number_id,
            ),
            params={"fields": "display_phone_number,verified_name"},
            headers={"Authorization": f"Bearer {settings.whatsapp_access_token}"},
            timeout=_TIMEOUT_S,
        )
    except httpx.HTTPError as e:
        informe.errores.append(
            f"WhatsApp: no se pudo verificar el token, sin conexión con Meta ({type(e).__name__})."
        )
        return

    if resp.status_code == 200:
        datos = resp.json()
        informe.ok.append(
            "WhatsApp: token válido, número "
            f"{datos.get('display_phone_number', '?')} ({datos.get('verified_name', '?')})."
        )
        return
    codigo = _codigo_error_graph(resp)
    if codigo == 190:
        informe.errores.append(
            "WhatsApp: WHATSAPP_ACCESS_TOKEN inválido o vencido (el token temporal de Meta "
            "vence a las 24 h). Generá uno nuevo en developers.facebook.com > tu app > "
            "WhatsApp > Configuración de la API."
        )
    elif codigo == 100:
        informe.errores.append(
            "WhatsApp: WHATSAPP_PHONE_NUMBER_ID no existe o el token no tiene acceso a ese "
            f"número ({_mensaje_error(resp)})."
        )
    else:
        informe.errores.append(
            f"WhatsApp: la Graph API devolvió {resp.status_code} ({_mensaje_error(resp)})."
        )


def _codigo_error_graph(resp: httpx.Response) -> int | None:
    try:
        return resp.json().get("error", {}).get("code")
    except ValueError:
        return None


def _mensaje_error(resp: httpx.Response) -> str:
    try:
        return resp.json().get("error", {}).get("message") or resp.text[:200]
    except ValueError:
        return resp.text[:200]


def _primera_linea(error: Exception) -> str:
    return str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__


def chequear_al_arrancar(settings: Settings, whatsapp: bool) -> None:
    """Imprime el informe y corta el arranque si hay errores. Se imprime por
    stderr y no por `logging` porque uvicorn no muestra los logs INFO de la
    aplicación, y los OK tienen que verse."""
    informe = Informe()
    chequear_postgres(settings, informe)
    with httpx.Client() as cliente:
        chequear_gemini(settings, informe, cliente)
        if whatsapp:
            chequear_whatsapp(settings, informe, cliente)
    print(informe.texto("WhatsApp" if whatsapp else "web"), file=sys.stderr, flush=True)
    if informe.errores:
        raise SystemExit(1)
