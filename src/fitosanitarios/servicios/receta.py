"""La receta en curso: qué datos son obligatorios y cuál es la última que se leyó.

Lo usan `leer_receta` (qué falta de lo leído en la foto), `completar_receta` (los datos
que da el operario después, sobre la última receta) y `evaluar_viabilidad_legal` (no se
evalúa una receta incompleta).

Antes, un dato que no estaba en la foto se mostraba en la confirmación como
"no figura ⚠️" con los botones [Confirmar] [Corregir]: el operario confirmaba y el LLM
evaluaba con "NO FIGURA" como cultivo o localidad (pasó el 23/09/2026 en WhatsApp: el
dictamen dijo que el producto no estaba autorizado "para el cultivo declarado"). Ahora un
dato obligatorio que falta se pregunta antes de mostrar la confirmación.
"""

import unicodedata

from langchain_core.messages import ToolMessage

from fitosanitarios.dominio.modelos import CampoFaltante, ResultadoTool

# Los datos sin los que no se puede evaluar una receta, en el orden en que se preguntan.
PREGUNTA_POR_CAMPO = {
    "cultivo": "¿Qué cultivo es?",
    "localidad": "¿En qué localidad se aplica?",
    "tipo_aplicacion": "¿Es aplicación terrestre o aérea?",
    "productos": "¿Qué producto y dosis indica la receta?",
    "lote": "¿Cuál es el número o nombre del lote?",
    "superficie_ha": "¿Cuántas hectáreas tiene el lote?",
}
NOMBRE_CAMPO = {
    "cultivo": "Cultivo",
    "localidad": "Localidad",
    "tipo_aplicacion": "Tipo de aplicación",
    "productos": "Producto",
    "dosis": "Dosis",
    "lote": "Lote",
    "superficie_ha": "Superficie",
}
MOTIVO_FALTA = "no figura en la receta o no se pudo leer con confianza"
_TOOLS_DE_RECETA = ("leer_receta", "completar_receta")
# Lo que el LLM llegó a pasar como si fuera un valor: el texto con que se le avisa que el
# dato no está.
_SIN_DATO = {"", "no figura", "nofigura", "sin dato", "sin datos", "n/a", "-", "none", "null"}


def _normalizar(texto: str) -> str:
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return " ".join(sin_tildes.lower().split())


def es_sin_dato(valor) -> bool:
    """`None`, vacío o un "NO FIGURA" que el LLM copió como si fuera el valor."""
    return valor is None or (isinstance(valor, str) and _normalizar(valor) in _SIN_DATO)


def normalizar_tipo_aplicacion(texto: str | None) -> str | None:
    if es_sin_dato(texto):
        return None
    t = _normalizar(texto)
    if "aer" in t or "avion" in t:
        return "aerea"
    if "terr" in t or "mochila" in t or "mosquito" in t:
        return "terrestre"
    return None


def pregunta_dosis(producto: str) -> str:
    return f"¿Qué dosis de {producto} indica la receta?"


def faltantes_de_receta(datos: dict) -> list[CampoFaltante]:
    """Los datos obligatorios que le faltan a una receta (el `model_dump` de `Receta`)."""
    items = datos.get("items") or []
    preguntas: list[tuple[str, str]] = []
    for campo, pregunta in PREGUNTA_POR_CAMPO.items():
        if campo == "productos":
            if not items:
                preguntas.append((campo, pregunta))
            preguntas += [
                ("dosis", pregunta_dosis(i.get("producto_nombre") or "el producto"))
                for i in items if es_sin_dato(i.get("dosis_declarada"))
            ]
        elif es_sin_dato(datos.get(campo)):
            preguntas.append((campo, pregunta))
    return [
        CampoFaltante(campo=c, motivo=MOTIVO_FALTA, pregunta_sugerida=p, tipo_entrada="texto")
        for c, p in preguntas
    ]


def datos_para_llm(datos: dict) -> str:
    """Lo leído, en texto: es lo ÚNICO que el agente sabe de la receta (el
    formateador arma el mensaje al usuario desde el artifact, no desde acá).
    Sin esto el LLM completaba cultivo, producto, dosis y localidad por su
    cuenta y evaluaba datos inventados (bug real, ver DIFICULTADES.md)."""
    productos = "; ".join(
        f"{i['producto_nombre']} (dosis: {i.get('dosis_declarada') or 'NO FIGURA'})"
        for i in datos.get("items", [])
    )
    campos = {
        "cultivo": datos.get("cultivo"), "lote": datos.get("lote"),
        "superficie_ha": datos.get("superficie_ha"),
        "tipo_aplicacion": datos.get("tipo_aplicacion"),
        "localidad": datos.get("localidad"), "adversidad": datos.get("adversidad"),
        "productos": productos or None,
    }
    return "; ".join(f"{k}={v if v not in (None, '') else 'NO FIGURA'}" for k, v in campos.items())


def faltantes_para_evaluar(
    mensajes: list, cultivo: str | None, tipo_aplicacion: str | None
) -> list[CampoFaltante]:
    """Lo que falta para evaluar: lo que le falta a la última receta leída (si hay una), o
    un cultivo o tipo de aplicación que el LLM pasó vacío o como "NO FIGURA". La
    localidad no: sin ella, la tool ya pregunta con la lista de localidades."""
    receta = ultima_receta(mensajes)
    if receta is not None:
        faltantes = faltantes_de_receta(receta)
        if faltantes:
            return faltantes
    return [
        CampoFaltante(
            campo=campo, motivo=MOTIVO_FALTA, pregunta_sugerida=PREGUNTA_POR_CAMPO[campo],
            tipo_entrada="texto",
        )
        for campo, sin_dato in (
            ("cultivo", es_sin_dato(cultivo)),
            ("tipo_aplicacion", normalizar_tipo_aplicacion(tipo_aplicacion) is None),
        )
        if sin_dato
    ]


def _como_resultado(artifact) -> ResultadoTool | None:
    """El artifact de una tool: un `ResultadoTool` en el turno en que corrió, un dict
    cuando vuelve del checkpoint de Postgres."""
    if isinstance(artifact, ResultadoTool):
        return artifact
    if isinstance(artifact, dict):
        try:
            return ResultadoTool.model_validate(artifact)
        except ValueError:
            return None
    return None


def ultima_receta(mensajes: list) -> dict | None:
    """Los datos de la última receta que mostró `leer_receta` o `completar_receta` en la
    conversación. `None` si no hay, o si la última lectura no dio una receta (una foto
    ilegible no deja viva la receta anterior)."""
    for m in reversed(mensajes):
        if isinstance(m, ToolMessage) and m.name in _TOOLS_DE_RECETA:
            resultado = _como_resultado(m.artifact)
            if resultado is None or not resultado.datos or "items" not in resultado.datos:
                return None
            return resultado.datos
    return None
