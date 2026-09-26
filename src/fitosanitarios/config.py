"""Configuración única del proyecto, leída desde variables de entorno / .env.

No se lee ninguna configuración fuera de este módulo (ver convención en la skill
agente-fitosanitarios). Variables documentadas en .env.example.
"""

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Base de datos
    database_url: str

    # LLM
    llm_provider: Literal["gemini", "groq"] = "gemini"
    gemini_api_key_1: str | None = None
    gemini_api_key_2: str | None = None
    gemini_api_key_3: str | None = None
    gemini_api_key_4: str | None = None
    gemini_api_key_5: str | None = None
    gemini_model: str = "gemini-3.5-flash-lite"
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    embeddings_model: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"

    # WhatsApp Cloud API (Fase 8)
    whatsapp_access_token: str | None = None
    whatsapp_phone_number_id: str | None = None
    whatsapp_app_secret: str | None = None
    whatsapp_verify_token: str | None = None
    # v26.0 verificada en vivo el 12/09/2026 contra el número de prueba (ver DECISIONES.md).
    whatsapp_graph_version: str = "v26.0"
    whatsapp_ar_quitar_9: bool = True

    # SENASA (Fase 2)
    senasa_base_url: str = "https://aps2.senasa.gov.ar/adt_api/api"
    senasa_req_por_seg: float = 1.0

    # Umbrales del núcleo experto
    dosis_tolerancia_pct: float = 10.0
    # 0.35, no 0.75: calibrado en la Fase 6 contra scores reales de
    # sentence-transformers/paraphrase-multilingual-mpnet-base-v2 (un
    # artículo genuinamente relevante scoreó 0.50-0.58 en el corpus de
    # prueba; 0.75 dejaba todo por debajo del umbral). Ver DECISIONES.md.
    rag_umbral_similitud: float = 0.35
    radio_busqueda_zonas_m: float = 2000.0

    # Presentación: las tools con RAG muestran la respuesta con y sin reformular la
    # pregunta (ver `servicios/demo_reformulacion.py`).
    modo_demo_reformulacion: bool = False

    # Tests y desarrollo
    use_fixtures: bool = True

    @model_validator(mode="after")
    def _validar_credenciales_llm(self) -> "Settings":
        if self.use_fixtures:
            return self
        if self.llm_provider == "gemini" and not self.gemini_api_keys:
            raise ValueError(
                "LLM_PROVIDER=gemini requiere al menos GEMINI_API_KEY_1 cuando USE_FIXTURES=false"
            )
        if self.llm_provider == "groq" and not self.groq_api_key:
            raise ValueError(
                "LLM_PROVIDER=groq requiere GROQ_API_KEY cuando USE_FIXTURES=false"
            )
        return self

    @property
    def gemini_api_keys(self) -> list[str]:
        """Keys de Gemini configuradas, en orden de rotación ante 429."""
        return [
            key
            for key in (
                self.gemini_api_key_1,
                self.gemini_api_key_2,
                self.gemini_api_key_3,
                self.gemini_api_key_4,
                self.gemini_api_key_5,
            )
            if key
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
