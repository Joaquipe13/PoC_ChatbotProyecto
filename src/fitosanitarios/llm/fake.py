"""Cliente LLM fake, determinista y sin red. Usado en tests y con USE_FIXTURES=true."""

from collections.abc import Callable


class ClienteLLMFake:
    """Devuelve respuestas fijas o calculadas por una función, sin llamar a ningún proveedor.

    Uso en tests:
        fake = ClienteLLMFake(respuestas=["hola", "chau"])
        fake.generar("...")  # -> "hola"
        fake.generar("...")  # -> "chau"

    o con una función del prompt a la respuesta:
        fake = ClienteLLMFake(responder=lambda prompt, system: "siempre esto")
    """

    def __init__(
        self,
        respuestas: list[str] | None = None,
        responder: Callable[[str, str | None], str] | None = None,
    ) -> None:
        self._respuestas = list(respuestas) if respuestas is not None else None
        self._responder = responder
        self.llamadas: list[dict] = []

    def generar(self, prompt: str, *, system: str | None = None) -> str:
        self.llamadas.append({"prompt": prompt, "system": system})
        if self._responder is not None:
            return self._responder(prompt, system)
        if self._respuestas:
            return self._respuestas.pop(0)
        return ""
