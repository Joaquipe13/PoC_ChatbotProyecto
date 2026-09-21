# Matriz de parámetros de las tools

Formaliza la matriz de la skill `agente-fitosanitarios` con el nombre del modelo pydantic `Args` de cada tool. Las tools no existen todavía (se implementan en las Fases 4, 5 y 6); estos son los nombres y campos que van a tener, fijados acá para que el orquestador (Fase 7) y las tools se desarrollen contra el mismo contrato. Van a vivir en `src/fitosanitarios/tools/<nombre_tool>.py` junto a la tool que los usa.

Fuentes para completar un parámetro, en este orden: **mensaje actual → receta en curso → turnos previos**. Nunca por suposición (ver skill, "Matriz de parámetros").

## `leer_receta`

```python
class LeerRecetaArgs(BaseModel):
    imagen: bytes  # o referencia a la imagen ya descargada del media de WhatsApp
```

| Requeridos | Opcionales | Si falta |
|---|---|---|
| imagen de la receta | — | pedir la foto, nítida y completa |

## `validar_producto_registro`

```python
class ValidarProductoRegistroArgs(BaseModel):
    producto_nombre: str
    cultivo: str
    adversidad: str | None = None
    dosis_valor: float | None = None
    dosis_unidad: str | None = None
```

| Requeridos | Opcionales | Si falta |
|---|---|---|
| producto, cultivo | adversidad, dosis + unidad | cultivo: texto. Producto ambiguo: lista de candidatos |

## `evaluar_riesgo`

```python
class EvaluarRiesgoArgs(BaseModel):
    localidad: str | None = None  # nombre de la localidad/municipio; ya no lat/lon (ver DECISIONES.md)
    tipo_aplicacion: str  # "terrestre" | "aerea"
    productos: list[str]  # nombres tal como los escribió el operario
    cultivo: str
    dosis_valor: float
    dosis_unidad: str
    adversidad: str | None = None  # pasa a requerida si el uso registrado varía por adversidad
```

**Implementado distinto de lo planeado en la Fase 1** (ver DECISIONES.md, Fase 5): acá se había previsto `productos: list[ProductoConBanda]`, con `banda_toxicologica` provista por quien llama. En la implementación real (Fase 5), `evaluar_riesgo` resuelve cada producto contra `catalogo.producto` (mismo mecanismo que `validar_producto_registro`) y toma la banda del registro, no de un dato que el operario tendría que saber de memoria -- el operario no suele conocer la banda toxicológica de un producto.

| Requeridos | Opcionales | Si falta |
|---|---|---|
| localidad o municipio, tipo de aplicación, productos, cultivo, dosis + unidad | adversidad (condicional) | localidad: lista de las cargadas. Tipo: botones Terrestre/Aérea |

Devuelve la banda de la aplicación completa (la más peligrosa de la mezcla) y la distancia mínima por tipo de zona (zona urbana, escuela, curso de agua) que fija la normativa de la localidad. No compara contra la ubicación del lote.

## `evaluar_viabilidad_legal`

```python
class EvaluarViabilidadLegalArgs(BaseModel):
    receta_id: int  # receta ya confirmada, con los requeridos de validar_producto_registro + evaluar_riesgo
    superficie_ha: float | None = None
    fecha_prevista: date | None = None
```

| Requeridos | Opcionales | Si falta |
|---|---|---|
| receta confirmada con los requeridos de las dos anteriores | superficie, fecha prevista | repreguntar agrupado |

## `responder_consulta_normativa`

```python
class ResponderConsultaNormativaArgs(BaseModel):
    pregunta: str
    jurisdiccion_id: str | None = None  # explícita o de la receta en curso
    tipo_aplicacion: TipoAplicacion | None = None
    tipo_zona: str | None = None
```

| Requeridos | Opcionales | Si falta |
|---|---|---|
| pregunta, jurisdicción (explícita o de la receta en curso) | tipo de aplicación, tipo de zona | jurisdicción: lista de las localidades cargadas |

## `consultar_productos`

```python
class ConsultarProductosArgs(BaseModel):
    cultivo: str | None = None
    adversidad: str | None = None
    principio_activo: str | None = None
    aptitud: str | None = None
    banda_maxima: str | None = None

    @model_validator(mode="after")
    def _al_menos_un_filtro(self) -> "ConsultarProductosArgs":
        if not (self.cultivo or self.adversidad or self.principio_activo):
            raise ValueError("consultar_productos requiere cultivo, adversidad o principio_activo")
        return self
```

| Requeridos | Opcionales | Si falta |
|---|---|---|
| al menos uno: cultivo, adversidad o principio activo | aptitud, banda máxima | pedir cultivo o plaga |

## `consultar_articulo`

```python
class ConsultarArticuloArgs(BaseModel):
    numero_articulo: str        # "33", "art. 33", "5 bis"
    norma: str | None = None    # "ley 11273", "ordenanza 841/2010" (como lo nombró el usuario)
    localidad: str | None = None
    provincia: str | None = None  # solo si la localidad no está cargada
```

| Requeridos | Opcionales | Si falta |
|---|---|---|
| número de artículo | norma, localidad | número: pregunta cuál. Norma (el número está en varias): lista de las normas que lo tienen. Localidad: se busca solo en la normativa provincial y nacional y se avisa |

## `listar_limitaciones`

```python
class ListarLimitacionesArgs(BaseModel):
    localidad: str | None = None
    provincia: str | None = None  # solo si la localidad no está cargada
    tipo_aplicacion: str | None = None  # "terrestre" | "aerea" (se entiende "con avión", "mosquito")
    banda: str | None = None            # Ia/Ib/II/III/IV o roja/amarilla/azul/verde
    tipo_zona: str | None = None        # "escuela", "zona urbana", "curso de agua"
    distancia_m: float | None = None    # qué está prohibido a esa distancia y qué excepciones hay
```

| Requeridos | Opcionales | Si falta |
|---|---|---|
| localidad | tipo de aplicación, banda, tipo de zona, distancia | localidad: pregunta cuál (lista de las cargadas). Un filtro que no se entiende se ignora y se avisa |

## Notas de implementación (Fases 4-6)

- Todos los `Args` heredan de `pydantic.BaseModel`; el orquestador (Fase 7) valida contra este schema antes de invocar la tool, nunca completa un campo por suposición.
- `TipoAplicacion` es el enum de `src/fitosanitarios/dominio/modelos.py` (`terrestre` | `aerea`), reutilizado acá para no duplicar el tipo.
- El validador de `ConsultarProductosArgs` (al menos un filtro) es ilustrativo del patrón a seguir; se implementa junto con la tool en la Fase 5.

## `agendar_aplicacion`

```python
class AgendarAplicacionArgs(BaseModel):
    fecha: str | None = None   # texto del operario: "martes", "mañana", "25/09" (lo resuelve el código)
    hora: str | None = None    # "8", "8:30", "3 de la tarde"
    numero: str | None = None; cultivo: str | None = None; lote: str | None = None
    superficie_ha: float | None = None; tipo_aplicacion: str | None = None
```

| Requeridos | Opcionales | Si falta |
|---|---|---|
| fecha, hora | datos de la receta (para mostrarla en la agenda) | fecha: pregunta el día. Hora: muestra la agenda de ese día y pregunta el horario |

`thread_id` sale del `config` del turno, no del LLM. Ver DECISIONES.md ("Seguimiento del dictamen").
