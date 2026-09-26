"""Cliente LLM real con rotación de keys de Gemini y alternativa Groq.

(verificar) antes de la Fase 2 -- primera fase que llama al LLM real -- el tipo
exacto de excepción que `google-genai` y `groq` levantan ante cuota agotada
(HTTP 429 / RESOURCE_EXHAUSTED). Por ahora se detecta heurísticamente por texto
del error, ya que no se pudo confirmar la clase exacta contra la documentación
vigente al momento de escribir este cliente.
"""

from typing import Protocol

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from fitosanitarios.config import Settings
from fitosanitarios.llm.fake import ClienteLLMFake


class ServicioLLMNoDisponible(Exception):
    """Se agotaron todas las keys/reintentos configurados para el proveedor de LLM."""


class ImagenRechazada(Exception):
    """El proveedor no pudo procesar la imagen (archivo dañado o que no es una imagen).
    Gemini responde `400 INVALID_ARGUMENT: Unable to process input image`."""


class ClienteLLM(Protocol):
    def generar(self, prompt: str, *, system: str | None = None) -> str: ...


class ClienteLLMMultimodal(Protocol):
    """Subconjunto de proveedores que aceptan imagen + texto (hoy solo Gemini;
    ver skill, "LLM: proveedor intercambiable... Gemini Flash multimodal como
    principal"). `ClienteGroq` no lo implementa."""

    def generar_con_imagen(
        self, imagen: bytes, prompt: str, *, system: str | None = None
    ) -> str: ...


def _es_error_cuota(exc: BaseException) -> bool:
    texto = str(exc).upper()
    return "429" in texto or "RESOURCE_EXHAUSTED" in texto or "RATE LIMIT" in texto


def _es_imagen_rechazada(exc: BaseException) -> bool:
    return "UNABLE TO PROCESS INPUT IMAGE" in str(exc).upper()


def _texto_de_respuesta(respuesta) -> str:
    """`respuesta.text` (el accessor de conveniencia de `google-genai`) da
    `""` para `gemini-3.5-flash-lite` en llamadas multimodales: el modelo
    devuelve el JSON pedido correctamente en
    `candidates[0].content.parts[*].text`, pero esas partes vienen con un
    `thought_signature` (token de continuidad de "thinking" de la API nueva,
    no un indicador de que el texto sea razonamiento interno) que rompe la
    heurística de esa propiedad. Encontrado el 12/09/2026 probando el canal
    web con una foto de receta real: `leer_receta` daba `IMAGEN_ILEGIBLE` en
    el 100 % de los casos pese a que el modelo leía la receta perfecto (ver
    DIFICULTADES.md). Reproducido con `resp.candidates[0].content.parts`
    conteniendo el JSON completo mientras `resp.text == ""`.

    Fallback: concatenar el texto de las partes de la primera respuesta que
    no estén marcadas explícitamente como pensamiento (`part.thought`, un
    campo distinto de `thought_signature`)."""
    if respuesta.text:
        return respuesta.text
    if not respuesta.candidates:
        return ""
    candidato = respuesta.candidates[0]
    if not candidato.content or not candidato.content.parts:
        return ""
    return "".join(
        parte.text
        for parte in candidato.content.parts
        if parte.text and not getattr(parte, "thought", False)
    )


class ClienteGemini:
    """Rota entre las API keys configuradas ante error de cuota."""

    def __init__(self, api_keys: list[str], model: str) -> None:
        if not api_keys:
            raise ValueError("ClienteGemini requiere al menos una API key")
        self._api_keys = api_keys
        self._model = model

    def generar(self, prompt: str, *, system: str | None = None) -> str:
        return self._con_rotacion(prompt, system, imagen=None)

    def generar_con_imagen(
        self,
        imagen: bytes,
        prompt: str,
        *,
        system: str | None = None,
        mime_type: str = "image/jpeg",
    ) -> str:
        return self._con_rotacion(prompt, system, imagen=imagen, mime_type=mime_type)

    def _con_rotacion(
        self,
        prompt: str,
        system: str | None,
        imagen: bytes | None,
        mime_type: str = "image/jpeg",
    ) -> str:
        ultimo_error: Exception | None = None
        for api_key in self._api_keys:
            try:
                return self._generar_con_key(api_key, prompt, system, imagen, mime_type)
            except Exception as exc:
                if imagen is not None and _es_imagen_rechazada(exc):
                    # La imagen es la misma con cualquier key: no tiene sentido rotar.
                    raise ImagenRechazada(str(exc)) from exc
                if not _es_error_cuota(exc):
                    raise
                ultimo_error = exc
                continue
        raise ServicioLLMNoDisponible(
            f"Las {len(self._api_keys)} keys de Gemini configuradas fallaron por cuota"
        ) from ultimo_error

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception(_es_error_cuota),
        reraise=True,
    )
    def _generar_con_key(
        self,
        api_key: str,
        prompt: str,
        system: str | None,
        imagen: bytes | None,
        mime_type: str = "image/jpeg",
    ) -> str:
        from google import genai  # import diferido: no es dependencia de los tests con fake
        from google.genai import types

        cliente = genai.Client(api_key=api_key)
        config = {"system_instruction": system} if system else None
        if imagen is not None:
            contents = [
                types.Part.from_bytes(data=imagen, mime_type=mime_type),
                prompt,
            ]
        else:
            contents = prompt
        respuesta = cliente.models.generate_content(
            model=self._model, contents=contents, config=config
        )
        return _texto_de_respuesta(respuesta)


class ClienteGroq:
    """Alternativa a Gemini, configurable por LLM_PROVIDER=groq."""

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise ValueError("ClienteGroq requiere una API key")
        self._api_key = api_key
        self._model = model

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception(_es_error_cuota),
        reraise=True,
    )
    def generar(self, prompt: str, *, system: str | None = None) -> str:
        from groq import Groq  # import diferido: no es dependencia de los tests con fake

        cliente = Groq(api_key=self._api_key)
        mensajes = []
        if system:
            mensajes.append({"role": "system", "content": system})
        mensajes.append({"role": "user", "content": prompt})
        try:
            respuesta = cliente.chat.completions.create(model=self._model, messages=mensajes)
        except Exception as exc:
            if _es_error_cuota(exc):
                raise ServicioLLMNoDisponible("Groq agotó la cuota configurada") from exc
            raise
        return respuesta.choices[0].message.content


def crear_cliente_llm(settings: Settings) -> ClienteLLM:
    """Fábrica única: fake si USE_FIXTURES=true, si no el proveedor real configurado."""
    if settings.use_fixtures:
        return ClienteLLMFake()
    if settings.llm_provider == "gemini":
        return ClienteGemini(settings.gemini_api_keys, settings.gemini_model)
    return ClienteGroq(settings.groq_api_key or "", settings.groq_model)
