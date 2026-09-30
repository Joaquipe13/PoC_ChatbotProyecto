# Agente de recetas fitosanitarias (TP2 IA, UTN FRRo)

Prueba de concepto de un **chatbot para operarios que aplican fitosanitarios en Santa Fe**. Lee la foto de una receta agronómica, la contrasta con el registro de productos de SENASA y con la normativa de la localidad (Ley provincial 11.273 y su decreto, ordenanzas y fallos judiciales), y dictamina si la aplicación es viable y legal. También responde consultas sueltas (qué banda tiene un producto, qué dice su marbete, a qué distancia del pueblo se puede aplicar, qué dice un artículo), agenda aplicaciones con el pronóstico del tiempo y registra cuándo empiezan y terminan.

El canal de producción es WhatsApp. Para probarlo sin WhatsApp hay notebooks que usan el mismo orquestador, y se pueden abrir directamente en Google Colab:

| Notebook | Qué hace | Colab |
|---|---|---|
| [`notebooks/chat.ipynb`](notebooks/chat.ipynb) | Chat libre con el bot: texto, foto de receta y botones de opciones | [![Abrir en Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Joaquipe13/PoC_ChatbotProyecto/blob/master/notebooks/chat.ipynb) |
| [`notebooks/demo_sin_whatsapp.ipynb`](notebooks/demo_sin_whatsapp.ipynb) | Recorrido corto: un caso por tipo de consulta | [![Abrir en Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Joaquipe13/PoC_ChatbotProyecto/blob/master/notebooks/demo_sin_whatsapp.ipynb) |
| [`notebooks/demo_e2e.ipynb`](notebooks/demo_e2e.ipynb) | Guion completo de la demo (APTA, OBSERVADA, repregunta, fuera de dominio…) | [![Abrir en Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Joaquipe13/PoC_ChatbotProyecto/blob/master/notebooks/demo_e2e.ipynb) |

## Cómo funciona

**El LLM orquesta, el núcleo decide.** Gemini entiende el mensaje, elige la herramienta (tool) y sus argumentos, repregunta lo que falta y detecta lo que está fuera de tema. Todo lo que es un dato (registro, banda toxicológica, dosis, distancias, normas, fechas) lo resuelve código determinista contra la base, y la respuesta la arma un formateador con plantillas a partir de los resultados de las tools. El LLM nunca escribe un número, una norma o un registro que no venga de una tool. Si un chequeo obligatorio no se pudo hacer, no hay dictamen APTA: **la falta de evidencia no cuenta como aprobación**.

```
mensaje (WhatsApp / notebook)
   └─► orquestador LangGraph (Gemini) ──► tools ──► servicios deterministas ──► PostgreSQL
                                                                                (JSONB + pgvector + pg_trgm)
   ◄── formateador con plantillas ◄──────── resultados de las tools
```

| Pieza | Elección |
|---|---|
| Agente | LangChain / LangGraph (`create_agent`), 14 tools tipadas con pydantic |
| LLM | Gemini Flash-Lite (multimodal: lee la foto de la receta), hasta 5 API keys para rotar |
| Base | PostgreSQL 16 con JSONB, pgvector y pg_trgm |
| Embeddings | `paraphrase-multilingual-mpnet-base-v2` (768 dimensiones, corre en CPU) |
| Canales | WhatsApp Cloud API (webhook FastAPI) y notebook de chat |
| Clima | Open-Meteo (sin API key) |

**Tools del agente** (`src/fitosanitarios/tools/`, una carpeta por tool):

- Receta: `leer_receta` (extrae los datos de la foto), `completar_receta` (pide los datos obligatorios que faltan).
- Productos: `validar_producto_registro`, `consultar_productos`, `consultar_marbete` (RAG sobre la etiqueta del producto), `evaluar_riesgo`.
- Dictamen: `evaluar_viabilidad_legal` (APTA / OBSERVADA / NO_EVALUABLE, con la distancia mínima que rige y la norma que la fija).
- Normativa: `listar_limitaciones`, `consultar_articulo` (texto literal) y `responder_consulta_normativa` (RAG con verificación de citas).
- Operación: `agendar_aplicacion` (con pronóstico de viento), `consultar_agenda`, `registrar_evento`, `resolver_vehiculo`.

**Datos cargados en la base:** registro de SENASA completo (7.370 productos, usos y dosis, bandas, principios activos), marbetes de 3.217 productos partidos en unos 76.000 fragmentos con embedding, las 362 localidades de Santa Fe, la Ley 11.273 y su decreto, y la normativa municipal de El Trébol, Sastre y San Jorge.

## Ejecutar en Google Colab

1. Conseguí una API key de Gemini en [Google AI Studio](https://aistudio.google.com/apikey) (la cuota gratuita alcanza).
2. Abrí una notebook con su botón **Abrir en Colab** (tabla de arriba).
3. En Colab, abrí el panel **Secrets** (el ícono de la llave, a la izquierda) y agregá un secret llamado `GEMINI_API_KEY` con tu key. Activá **Acceso del notebook**. Si tenés más keys, agregalas como `GEMINI_API_KEY_2` … `GEMINI_API_KEY_5` y el bot rota cuando una se queda sin cuota.
4. **Entorno de ejecución → Ejecutar todas.** La primera celda prepara la máquina: clona el repo, instala Postgres 16 con pgvector y las dependencias, baja la base ya cargada (un dump de unos 340 MB publicado en el [Release `datos-v1`](https://github.com/Joaquipe13/PoC_ChatbotProyecto/releases/tag/datos-v1)) y la restaura.

No hace falta GPU: el entorno gratuito con CPU alcanza.

### Limitaciones al ejecutar las notebooks en Colab

- **La preparación tarda varios minutos cada vez que se abre un entorno nuevo.** Medido en un contenedor Debian con Python 3.12: instalar Postgres, 1,5 minutos; restaurar la base con sus índices vectoriales, 1,5 minutos; instalar las dependencias, 12 minutos, porque tuvo que bajar PyTorch. Colab ya trae PyTorch instalado, así que ahí ese último paso debería ser bastante más corto. A eso se suma la primera respuesta del bot, que baja el modelo de embeddings (~1 GB) de Hugging Face. Volver a correr la celda en el mismo entorno tarda segundos.
- **Nada persiste.** La máquina de Colab es descartable: al desconectarse (por inactividad, a los ~90 minutos, o al límite de sesión) se pierden las conversaciones, la agenda y los eventos registrados. La próxima vez arranca de cero con la base del dump.
- **La base es una foto del 30/09/2026.** El registro de SENASA y los marbetes no se actualizan solos. Rehacer la carga desde cero (crawl de SENASA y carga de marbetes) lleva horas y no está pensado para Colab.
- **Sin WhatsApp.** Colab sirve para las notebooks, no para dejar corriendo el webhook, que necesita un servidor con una URL HTTPS fija. El canal de WhatsApp se levanta en local (ver [`docs/setup-whatsapp.md`](docs/setup-whatsapp.md)).
- **Cuota de Gemini.** Cada mensaje hace una o más llamadas a Gemini. Con la cuota gratuita, después de muchas consultas seguidas aparece el error 429. La rotación entre varias keys funciona en las tools, pero el agente orquestador usa una sola key.
- **Gemini a veces está saturado.** Si responde `503 UNAVAILABLE` ("high demand"), el bot contesta "Tuve un problema técnico…". Es un problema de Google y pasa solo: reintentá en un rato.
- **Las respuestas varían entre corridas.** Gemini no es determinista (ignora la temperatura), así que un mismo caso de la demo puede elegir otra tool o redactar distinto de una corrida a otra.
- **Fotos de recetas en el chat.** El botón *Foto* del chat usa un widget de carga de archivos. Si en Colab no responde, subí la imagen al panel **Archivos** y mandala con `enviar(foto="/content/tu_foto.jpg")`. Las recetas de ejemplo del repo están en `data/recetas_ejemplo/`.
- **Avisos de pip.** Colab trae paquetes preinstalados, y `pip` puede avisar de conflictos de versiones con alguno que el proyecto no usa. Si la celda termina con "Colab listo.", se pueden ignorar.
- **El repo tiene que ser público** para que Colab lo clone y baje el dump sin credenciales.

## Ejecutar en local

Requisitos: Python 3.12+, [uv](https://docs.astral.sh/uv/) y Docker.

```bash
cp .env.example .env          # completar al menos una GEMINI_API_KEY_*
uv sync --dev                 # dependencias (incluye pytest y ruff)
docker compose up -d db       # Postgres 16 + pgvector + pg_trgm en el puerto 5433
```

La base arranca vacía. Para cargarla con los mismos datos que usa Colab, bajá `fitosanitarios.dump` del [Release `datos-v1`](https://github.com/Joaquipe13/PoC_ChatbotProyecto/releases/tag/datos-v1) y restauralo:

```bash
docker cp fitosanitarios.dump fitosanitarios-db:/tmp/
docker exec fitosanitarios-db pg_restore -U postgres -d fitosanitarios --no-owner --clean --if-exists /tmp/fitosanitarios.dump
```

Después, abrí una notebook (`uv run python -m notebook notebooks/chat.ipynb`) y corré todas las celdas. En local, la celda de Colab no hace nada.

Los comandos van con `python -m` (`python -m pytest`, `python -m notebook`, `python -m uvicorn`) y no con el ejecutable directo: con un venv creado sobre el Python de la Microsoft Store, los ejecutables que arma uv fallan con "uv trampoline failed to canonicalize script path".

Para el canal real de WhatsApp (credenciales de Meta y un túnel HTTPS), ver [`docs/setup-whatsapp.md`](docs/setup-whatsapp.md).

## Tests

```bash
uv run python -m pytest -q
uv run ruff check .
```

Los tests nunca salen a la red: con `USE_FIXTURES=true` (el default) el LLM y SENASA son dobles deterministas y no hace falta ninguna API key. Los que usan la base corren contra una base aislada, `fitosanitarios_test`, que se carga sola con una copia congelada de los insumos reales (`tests/fixtures/`). Si no existe, esos tests se saltean e indican el comando para crearla. El CI (`.github/workflows/ci.yml`) corre lint y tests en cada push.

## Estructura del repositorio

```
src/fitosanitarios/
  orquestador/   agente LangGraph, prompt del sistema, formateador de respuestas
  tools/         una carpeta por tool (tool, prompts, mensajes)
  servicios/     lógica determinista: dosis, reglas de distancia, fechas, RAG, clima
  datos/         migraciones SQL y consultas (retrievers)
  senasa/        crawler, normalizador y carga del registro y los marbetes
  insumos/       validación y carga de localidades, normativa y reglas
  canales/       WhatsApp (webhook FastAPI) y notebook
data/insumos/    reglas.csv, localidades.csv, reglas_viento.csv y normativa
data/recetas_ejemplo/  recetas sintéticas para probar la lectura de fotos
scripts/         crawl de SENASA, embeddings de vehículos, recetas de ejemplo, preparación de Colab
notebooks/       chat y demos
tests/           suite de pytest y fixtures
docs/            modelo de datos, contrato de insumos, WhatsApp, decisiones y dificultades
```

## Límites conocidos del sistema

- Normativa municipal cargada solo para El Trébol, Sastre y San Jorge. El resto de las localidades de Santa Fe se responden con la ley provincial, y el bot lo aclara. El servicio opera solo en Santa Fe.
- Para Sastre y San Jorge no hay texto oficial: se cargaron fallos judiciales y una ordenanza desde fuentes secundarias (prensa), que el sistema trata igual que una norma general.
- La consulta libre de normativa (RAG) falla con preguntas muy generales ("¿hay que avisar antes de aplicar?"). Para distancias y restricciones, `listar_limitaciones` y `consultar_articulo` son las vías confiables.
- Sin OCR: 461 marbetes escaneados y las normas sin capa de texto no se pueden consultar.
- El parser de dosis entiende el 83 % de las dosis del registro. Las ambiguas (por tipo de suelo, por semilla) quedan sin comparar en vez de adivinarse.
- Lo que la normativa no contempla (aplicar dentro del casco urbano, drones, mochila) no se responde bien. Drones y mochila salen con un aviso.

## Documentación

- [`docs/DECISIONES_PRINCIPALES.md`](docs/DECISIONES_PRINCIPALES.md): resumen de las decisiones de diseño y por qué.
- [`docs/DECISIONES.md`](docs/DECISIONES.md) y [`docs/DIFICULTADES.md`](docs/DIFICULTADES.md): registro completo de decisiones y de los problemas encontrados (los comentarios del código los citan).
- [`docs/modelo-datos.md`](docs/modelo-datos.md): diagrama entidad-relación y consultas de las tools RAG.
- [`docs/contrato-insumos.md`](docs/contrato-insumos.md): formato de los insumos de normativa y reglas.
- [`docs/setup-whatsapp.md`](docs/setup-whatsapp.md): configuración del canal de WhatsApp.
