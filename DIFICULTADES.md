# Dificultades

Registro de qué falló y cómo se resolvió. Una entrada por dificultad relevante, en orden cronológico (más reciente arriba).

## Fase 0 — Setup

### Puerto 5432 ocupado por otro proyecto

Al levantar `docker compose up -d db` por primera vez, el puerto 5432 ya estaba tomado por un contenedor de otro proyecto en esta misma máquina (`asistente_viajes_db`, también `pgvector/pgvector`). Se resolvió mapeando este proyecto al puerto 5433 en `docker-compose.yml` y actualizando `DATABASE_URL` en `.env.example` en consecuencia. Si se levanta este proyecto en otra máquina sin ese conflicto, el puerto 5433 sigue funcionando igual (no depende de que 5432 esté libre).

### `uv` no estaba instalado en la máquina de desarrollo

CI usa `uv sync --dev`, pero la máquina de desarrollo local no lo tenía instalado. Para verificar los criterios de aceptación de la Fase 0 se usó un `venv` + `pip install -e . pytest ruff` como alternativa puntual. Recomendado instalar `uv` (`https://docs.astral.sh/uv/getting-started/installation/`) para el flujo de desarrollo día a día, ya que es lo que corre en CI.

### `ruff` marcó `pytest.raises(Exception)` como demasiado genérico (regla B017)

Los tests que esperaban que `Settings(...)` fallara por falta de una variable requerida usaban `pytest.raises(Exception)`. Se corrigió usando `pydantic.ValidationError`, que es la excepción real que levanta `pydantic-settings` (los `ValueError` de los validadores personalizados en `config.py` también se envuelven en `ValidationError` automáticamente).
