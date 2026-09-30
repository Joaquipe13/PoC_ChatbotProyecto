# Decisiones principales (resumen para el grupo)

Resumen de [`DECISIONES.md`](DECISIONES.md) para entender el proyecto sin leer el registro
completo. Cada punto dice **qué** se decidió y **por qué**; el detalle, las alternativas
descartadas y las fechas están en `DECISIONES.md`, y lo que falló y cómo se arregló, en
[`DIFICULTADES.md`](DIFICULTADES.md). Estado al 29/09/2026.

## 1. Qué es

Un chatbot por WhatsApp (y un notebook de chat para probar) para operarios que aplican
fitosanitarios en Santa Fe. Lee la foto de la receta agronómica, la contrasta con el registro
de SENASA y la normativa (ley provincial, ordenanzas, fallos), y responde consultas: si se
puede aplicar, a qué distancia del pueblo, qué banda tiene un producto, qué dice su etiqueta,
qué dice una norma. También agenda aplicaciones, con el pronóstico del tiempo, y registra
cuándo empiezan y terminan.

## 2. El principio que ordena todo: el LLM orquesta, el núcleo decide

- **El LLM (Gemini)** entiende el mensaje, elige la herramienta (tool) y sus argumentos,
  repregunta lo que falta y detecta lo que está fuera de tema.
- **El núcleo** (código determinista + base de datos) decide todo lo que es un dato: registro,
  banda, dosis, distancias, normas, fechas. El LLM **nunca** escribe un número, una norma o un
  registro que no venga de una tool.
- **La respuesta la arma un formateador con plantillas** a partir de los resultados de las
  tools, no del texto libre del modelo.
- **Ausencia de evidencia no es aprobación:** si un chequeo obligatorio no se pudo hacer, no
  hay dictamen APTA. Si no hay una fuente, el bot dice que no cuenta con esa información.

**Por qué:** un dictamen legal tiene que ser reproducible y auditable, y un LLM (más con cuota
gratuita) puede fallar o inventar. Además permite tests confiables sin red.

## 3. Stack

| Pieza | Elección | Por qué |
|---|---|---|
| Agente | LangChain / LangGraph (`create_agent`) con 14 tools | Requisito de la cátedra; tools tipadas con pydantic |
| LLM | Gemini 3.5 Flash-Lite (`google-genai`) | Multimodal (lee la foto), cuota gratuita; hasta 5 keys para rotar en las tools |
| Base | PostgreSQL 16 + JSONB + pgvector + pg_trgm (Docker) | Un solo motor para lo relacional, lo semiestructurado y los embeddings (requisito: sin tablas planas) |
| Embeddings | `paraphrase-multilingual-mpnet-base-v2` (768 dim, CPU) | Buen español; elegido con un benchmark |
| Canales | WhatsApp Cloud API (webhook FastAPI) + `notebooks/chat.ipynb` | El notebook permite probar sin depender de Meta ni de un túnel; reemplazó al canal web el 28/09 |
| Clima | Open-Meteo (sin API key) | Pronóstico hora por hora gratuito |
| Dependencias | `uv` | Rápido y con `pyproject.toml` estándar |

## 4. Datos

- **Registro de SENASA:** crawl de la API pública (7.370 productos, bandas, principios activos,
  usos y dosis) guardado como snapshot JSON Lines; los PDF de los marbetes se separan a disco
  durante el crawl (un snapshot con PDFs embebidos pesaba 88 MB por cada 190 productos).
- **Parser de dosis:** entiende el 83 % de los textos de dosis del registro ("1,5-2 L/ha",
  "cm3", "lts"…). Lo que no se puede leer sin adivinar (dosis por tipo de suelo, por semilla)
  queda sin comparar, nunca inventado.
- **Normativa:** PDF de la Ley 11.273 y su decreto, la Ordenanza 841/2010 de El Trébol; para
  Sastre y San Jorge (fallos judiciales y una ordenanza sin texto oficial) un resumen `.md` con
  su fuente. Se parte en artículos y en fragmentos con embedding.
- **Reglas de distancia:** un único `data/insumos/reglas.csv` revisado a mano, con
  prohibiciones (`N`) y reglas condicionales (`S`, excepciones con sus condiciones). Si una
  jurisdicción no tiene filas, las distancias se leen del PDF con un parser determinista (sin
  LLM: con LLM salían reglas dudosas y variaban entre corridas).
- **Localidades:** las 362 de Santa Fe se reconocen por nombre; las que no tienen ordenanza
  cargada se responden con la ley provincial, **aclarándolo**. El servicio opera solo en Santa
  Fe.
- **Marbetes:** 3.630 productos con marbete cargado, 3.217 con texto (76.000 fragmentos); 461
  son escaneos sin texto (no hay OCR).

## 5. Decisiones de diseño que conviene conocer

- **Una tool = una carpeta** (`tools/<tool>/`: la tool, su prompt y sus mensajes). La tool
  valida y llama servicios; la lógica de negocio vive en `servicios/`.
- **El dictamen no depende de que el LLM encadene tools:** `evaluar_viabilidad_legal` hace los
  chequeos de producto y de riesgo por dentro.
- **Se informa la distancia mínima, no se valida la ubicación del lote** (cambio del 19/09).
  El único polígono disponible de El Trébol era la mancha urbana, así que ningún lote real
  "caía" en la localidad. Ahora, con la localidad, el tipo de aplicación y la banda de la mezcla
  (la más peligrosa), el bot dice la distancia mínima que rige y la norma que la fija. El código
  de geometría quedó sin uso y se borró el 29/09.
- **La distancia que rige es la más restrictiva** entre la ley, la ordenanza y los fallos; una
  excepción provincial no levanta una prohibición municipal.
- **Consultas de normativa en tres tools:** `listar_limitaciones` (lista completa desde las
  reglas, sin búsqueda por similitud), `consultar_articulo` (texto literal por número) y
  `responder_consulta_normativa` (RAG para dudas de contenido). Las dos primeras son las
  confiables; la tercera es secundaria.
- **RAG de marbetes:** busca solo dentro del marbete del producto, con búsqueda híbrida
  (similitud + BM25 fusionados) y **reformulación de la pregunta** (el LLM agrega los términos
  técnicos antes de buscar). Cada página citada se verifica contra lo recuperado.
- **Menos tokens por turno:** 10 de las 14 tools terminan el turno ellas mismas (una llamada a
  Gemini en vez de dos): −58 % de tokens por turno. Tope de 4 llamadas a tools por turno.
- **Receta de foto:** la imagen no viaja como argumento de la tool (serían ~100.000 tokens); la
  tool la recibe "ligada" desde el canal. Siempre se confirma antes de evaluar, y los datos
  obligatorios que faltan se preguntan.
- **Fechas y horas las resuelve código** ("el martes", "mañana a las 8"), no el LLM.
- **Pronóstico al agendar:** información, no control. Dice de dónde viene el viento y hacia
  dónde empuja la deriva, y menciona la norma de viento de la localidad (El Trébol, art. 4) si
  el pronóstico supera su umbral. No cambia el dictamen ni impide agendar.
- **Cuando el RAG no encuentra respuesta**, el bot dice "No cuento con esa información" en
  lugar de un error técnico.

## 6. Cómo se prueba

- **~940 tests** que nunca salen a la red (LLM y SENASA falsos), contra una **base de test
  aislada** (`fitosanitarios_test`, se carga sola). Antes los tests escribían en la base de
  desarrollo y llegaron a borrarle datos reales.
- **Los tests usan una copia congelada de los insumos reales** (`tests/fixtures/insumos/`);
  las localidades y normas inventadas de las primeras fases se borraron el 26/09.
- **Evaluación con Gemini real** (`evals/`, fuera de `pytest`): exactitud de ruteo y una
  **evaluación conversacional** donde un agente simula un operario y otro analiza las
  conversaciones. Encontró errores que los tests no veían.
- **Chequeo de credenciales al arrancar un canal:** si una key o el token de WhatsApp están
  mal, el servidor no arranca en vez de fallar con el primer mensaje.

## 7. Límites conocidos

- Normativa municipal cargada solo de El Trébol, Sastre y San Jorge; Sastre y San Jorge desde
  fuentes secundarias (prensa, fallos), que el sistema trata igual que una ley.
- La consulta libre de normativa (RAG) falla con preguntas muy generales ("¿hay que avisar
  antes de aplicar?"): el decreto tiene muchos artículos genéricos que ganan la búsqueda.
- Gemini varía entre corridas (ignora la temperatura): conviene ensayar antes de una demo.
- El agente orquestador usa una sola API key (la rotación solo está en las tools).
- Sin OCR: los marbetes escaneados y las normas sin capa de texto no se leen.
- Lo que la normativa no contempla no se responde bien (aplicar dentro del casco urbano,
  drones, mochila: estos dos se informan con un aviso).

## 8. Dónde está cada cosa

- `src/fitosanitarios/`: `orquestador/` (agente, prompt, formateador), `tools/` (una carpeta
  por tool), `servicios/` (lógica determinista), `datos/` (migraciones SQL y consultas),
  `senasa/` (crawl y carga), `insumos/` (carga de normativa y reglas), `canales/`.
- `data/insumos/`: normativa, `reglas.csv`, `localidades.csv`, `reglas_viento.csv`.
- `docs/`: modelo de datos, guion de la demo, guion de la presentación, contrato de insumos.
- Cómo levantarlo: `README.md`.
