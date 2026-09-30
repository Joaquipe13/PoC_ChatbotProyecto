# Caso de negocio, decisiones técnicas y dificultades

Resumen breve para la defensa del trabajo. El detalle está en
[`DECISIONES_PRINCIPALES.md`](DECISIONES_PRINCIPALES.md), [`DECISIONES.md`](DECISIONES.md) y
[`DIFICULTADES.md`](DIFICULTADES.md).

## 1. Caso de negocio

**Contexto.** El chatbot es un módulo de nuestro proyecto final: un sistema para una empresa que
aplica fitosanitarios (lo que comúnmente se conoce como agroquímicos). Sus usuarios son los
operarios que salen al campo a hacer las aplicaciones.

**Cómo se trabaja hoy.** Todo arranca con la **receta agronómica**, que emite un ingeniero agrónomo
matriculado: indica el cultivo, el lote y su superficie, la plaga o enfermedad, los productos, las
dosis y si la aplicación es terrestre o aérea. Antes de aplicar hay que verificar dos cosas:

1. Que cada producto esté **registrado en SENASA**, autorizado para ese cultivo y con la dosis dentro
   del rango permitido.
2. Que se respeten las **distancias mínimas** a zonas urbanas, escuelas y cursos de agua. Estas
   distancias no son fijas: dependen del tipo de aplicación, de la banda toxicológica del producto y
   de la localidad.

**El problema.** Esa información está dispersa: miles de registros de SENASA, la Ley provincial
11.273 y su decreto, ordenanzas municipales y hasta fallos judiciales. Revisar todo eso parado en el
lote es lento y propenso a errores, y es justo el momento en que el operario necesita una respuesta
clara.

**La propuesta.** Usar una herramienta que el operario ya usa todos los días: **WhatsApp**. Manda una
foto de la receta o escribe una pregunta, y recibe una respuesta concreta con la fuente que la
respalda. Además puede consultar el marbete (la etiqueta) de un producto, preguntar por una norma,
agendar la aplicación con el pronóstico del tiempo y registrar cuándo empieza y termina.

**Alcance de la prueba de concepto.** Provincia de Santa Fe, con normativa municipal cargada para El
Trébol, Sastre y San Jorge. Para el resto de las localidades se aplica la ley provincial y el bot
aclara que no tiene cargada la normativa municipal.

## 2. Decisiones técnicas

- **El LLM orquesta, el núcleo decide.** Gemini entiende el mensaje, elige la herramienta y sus
  argumentos y repregunta lo que falta. Los números, normas, dosis, distancias, fechas y registros
  salen siempre de código determinista y de la base de datos, y la respuesta la arma un formateador
  con plantillas. Así cada dictamen es **reproducible y auditable**. El modelo solo aporta contenido al
  leer la foto de la receta (que el operario confirma) y en las consultas abiertas por RAG.
- **La falta de evidencia no es aprobación.** Si un chequeo obligatorio no se pudo hacer, el dictamen
  nunca es APTA. Si no hay fuente, el bot dice que no cuenta con esa información.
- **Agente con LangChain / LangGraph y 14 tools tipadas** (leer receta, validar producto, dictamen
  legal, normativa, marbetes, agenda…). El dictamen hace por dentro los chequeos de producto y riesgo,
  para no depender de que el LLM encadene bien las herramientas.
- **Gemini Flash-Lite**: multimodal (lee la foto) y con cuota gratuita; las tools rotan entre hasta 5
  API keys cuando una se queda sin cuota.
- **PostgreSQL como único motor**: tablas relacionales para lo estructurado, JSONB para lo
  semiestructurado, pgvector para los embeddings y pg_trgm para coincidencias de texto.
- **RAG sobre unos 76.000 fragmentos** de marbetes y normativa: embeddings multilingües
  (`paraphrase-multilingual-mpnet-base-v2`, elegido con un benchmark) combinados con búsqueda por
  términos (BM25), reformulación de la pregunta con vocabulario técnico y **verificación de cada cita**
  contra lo recuperado.
- **La distancia que rige es la más restrictiva** entre ley, ordenanza y fallos. Por ejemplo, para
  Sastre la ley pide 500 m y la ordenanza 3.000 m: rige 3.000.
- **Fechas y horas las interpreta el código** ("el lunes a las nueve"), no el modelo. El pronóstico de
  Open-Meteo es solo informativo: no habilita ni bloquea la aplicación.
- **Menos tokens por turno**: 10 de las 14 tools cierran el turno ellas mismas (−58 % de tokens), y la
  foto no viaja como argumento de la tool.
- **Calidad**: unos 940 tests que corren sin red, con LLM y SENASA simulados y una base de prueba
  aislada, más una evaluación conversacional con el modelo real (un agente simula al operario y
  después se revisan las conversaciones).

## 3. Dificultades encontradas

- **Riesgo de que el LLM invente datos legales.** Se resolvió separando la orquestación del núcleo
  determinista, verificando las citas por código y con la regla conservadora de no emitir APTA sin
  todos los chequeos.
- **Diferencias de vocabulario.** El operario dice "volver a entrar al lote" o "se me volcó" y el
  marbete dice "reingresar al área tratada" o "derrame". Con búsqueda híbrida y reformulación técnica,
  la recuperación en una evaluación con 40 marbetes pasó del 68 % al 81 % y finalmente al 95 %.
- **Validar la ubicación del lote no fue posible.** El único polígono disponible de El Trébol era la
  mancha urbana, así que ningún lote rural "caía" en la localidad. Se cambió el enfoque: el bot informa
  la distancia mínima que rige según localidad, tipo de aplicación y banda, y la norma que la fija.
- **Distancias leídas con LLM daban reglas dudosas** y distintas entre corridas. Se pasó a un
  `reglas.csv` revisado a mano y a un parser determinista.
- **Bugs que los tests no veían.** Un umbral de similitud mal configurado y un formato de cita
  (`"art. 7"` contra `"7"`) hacían que la consulta normativa nunca respondiera con Gemini real; las
  pruebas manuales también encontraron un filtro de bandas invertido y consultas que iban a la tool
  equivocada. Por eso se sumó la evaluación conversacional y las pruebas con el modelo real.
- **Tests que escribían en la base de desarrollo** llegaron a borrar datos reales; se creó una base de
  test aislada con una copia congelada de los insumos.
- **Límites de los datos y del modelo.** Cuota gratuita de Gemini (de ahí la rotación de keys),
  variación entre corridas, 461 marbetes escaneados sin texto (no hay OCR), un parser de dosis que
  entiende el 83 % del registro y preguntas normativas muy generales que el RAG no resuelve bien.

**Próximos pasos:** ampliar la cobertura municipal, aplicar OCR a los documentos escaneados, generar
avisos automáticos antes de cada aplicación e integrar el chatbot con el resto del proyecto final.
