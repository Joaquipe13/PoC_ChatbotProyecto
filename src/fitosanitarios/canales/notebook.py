"""Canal notebook: conversar con el bot desde Jupyter (`notebooks/chat.ipynb`), con el
mismo orquestador que el canal WhatsApp. Reemplaza al canal web (Fase 11), que se sacó
el 28/09/2026 a pedido del usuario (ver DECISIONES.md).

    conversacion = Conversacion()
    conversacion.enviar("¿qué banda tiene el Tordon D 30?")
    conversacion.enviar(foto="data/recetas_ejemplo/02_apta_aerea_banda_ii.jpg")
    conversacion.nueva()

Cada `Conversacion` es un thread propio del checkpointer (`notebook-<id>`); `nueva()`
arranca otro, como "Nueva conversación" en la web. El modelo y el checkpointer se pueden
inyectar para testear sin Gemini ni Postgres.
"""

import base64
import logging
import re
import uuid
from contextlib import ExitStack
from pathlib import Path

import psycopg

from fitosanitarios.config import Settings, get_settings
from fitosanitarios.orquestador.agente import (
    checkpointer_postgres,
    crear_agente,
    crear_modelo_chat_gemini,
    modelos_de_respaldo,
)
from fitosanitarios.orquestador.estado import ContadorRepreguntas
from fitosanitarios.orquestador.turno import ejecutar_turno

logger = logging.getLogger(__name__)

# Una foto sin texto nunca llega al agente como string vacío: un mensaje sin contenido no
# dispara ninguna tool (bug real del canal web, ver DIFICULTADES.md).
TEXTO_DE_UNA_FOTO_SOLA = "Te mando la foto de mi receta."


def texto_final(texto: str, con_foto: bool) -> str:
    if con_foto and not texto.strip():
        return TEXTO_DE_UNA_FOTO_SOLA
    return texto


def foto_en_base64(foto: str | Path | bytes) -> str:
    datos = foto if isinstance(foto, bytes) else Path(foto).read_bytes()
    return base64.b64encode(datos).decode()


def a_markdown(mensaje: str) -> str:
    """El formato de WhatsApp (`*negrita*`, `_cursiva_`, botones `[Sí] [No]`) en Markdown,
    para mostrarlo en la notebook. Cada salto de línea se respeta."""
    texto = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"**\1**", mensaje)
    texto = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"*\1*", texto)
    texto = re.sub(r"\[([^\]\n]+)\]", r"`[\1]`", texto)
    return texto.replace("\n", "  \n")


class Conversacion:
    """Una conversación con el bot. Sin argumentos usa Gemini (con todas las keys, para
    rotar ante un error de cuota), el checkpointer de Postgres y el log por turno, igual
    que el canal WhatsApp."""

    def __init__(
        self,
        settings: Settings | None = None,
        modelo=None,
        respaldo=None,
        checkpointer=None,
        registrar_turnos: bool = True,
    ):
        self.settings = settings or get_settings()
        if self.settings.use_fixtures and modelo is None:
            logger.warning(
                "USE_FIXTURES=true: leer_receta y las respuestas con RAG usan un LLM fake. "
                "Para conversar de verdad, USE_FIXTURES=false."
            )
        self._pila = ExitStack()
        if modelo is None:
            modelo = crear_modelo_chat_gemini(self.settings)
            respaldo = modelos_de_respaldo(self.settings) if respaldo is None else respaldo
        if checkpointer is None:
            checkpointer = self._pila.enter_context(
                checkpointer_postgres(self.settings.database_url)
            )
        self._modelo = modelo
        self._respaldo = respaldo
        self._checkpointer = checkpointer
        self._agente = crear_agente(modelo, checkpointer=checkpointer, respaldo=respaldo)
        self._registrar = registrar_turnos
        self._contador = ContadorRepreguntas()
        self.thread_id = ""
        self.nueva()

    def nueva(self) -> str:
        """Arranca una conversación nueva (otro thread): el bot no recuerda la anterior."""
        self.thread_id = f"notebook-{uuid.uuid4().hex[:8]}"
        return self.thread_id

    def enviar(self, texto: str = "", foto: str | Path | bytes | None = None) -> list[str]:
        """Manda un mensaje (texto, foto o los dos) y devuelve las respuestas del bot tal
        como las mandaría por WhatsApp."""
        imagen = foto_en_base64(foto) if foto is not None else None
        texto = texto_final(texto, imagen is not None)
        if not texto.strip():
            return []
        agente = self._agente if imagen is None else crear_agente(
            self._modelo, checkpointer=self._checkpointer, imagen_base64=imagen,
            respaldo=self._respaldo,
        )
        if not self._registrar:
            _, mensajes = ejecutar_turno(agente, self.thread_id, texto, self._contador)
            return mensajes
        with psycopg.connect(self.settings.database_url) as conn:
            _, mensajes = ejecutar_turno(
                agente, self.thread_id, texto, self._contador, conn_log=conn
            )
        return mensajes

    def cerrar(self) -> None:
        self._pila.close()
