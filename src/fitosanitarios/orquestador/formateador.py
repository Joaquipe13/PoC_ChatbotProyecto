"""Formateador determinista: arma el texto final de WhatsApp a partir de
`RespuestaAgente.tipo` y los artifacts (`ResultadoTool`) de las tools que
corrieron en el turno -- nunca del texto libre del LLM (ver skill,
"Contratos": el formateador "renderiza los artifacts de las tools
ejecutadas en el turno actual, así el LLM no puede alterar números ni
citas", y "Formato de respuestas").

Cada tool define en `tools/<tool>/mensajes.py` la plantilla del tipo de respuesta
que produce; acá se las reúne en `_PLANTILLAS` y quedan las comunes (repregunta,
fuera de dominio, no resuelto, ayuda y error), más el corte de mensajes largos.
Los tipos que producen varias tools se reparten según la forma del resultado (ver
`_plantilla_dictamen` y `_plantilla_consulta_producto`). Lo que se repite entre
plantillas (citas, números, *Fuentes*) está en `servicios/formato.py`
(ver docs/especificacion-plantillas.md).
"""

import json
import re

from fitosanitarios.dominio.modelos import RespuestaAgente, ResultadoTool
from fitosanitarios.dominio.motivos import DESCRIPCION_MOTIVO, MotivoNoResuelto
from fitosanitarios.servicios.formato import primer_dato
from fitosanitarios.tools.agendar_aplicacion.mensajes import plantilla_agendar_aplicacion
from fitosanitarios.tools.consultar_agenda.mensajes import plantilla_agenda
from fitosanitarios.tools.consultar_articulo.mensajes import plantilla_consulta_articulo
from fitosanitarios.tools.consultar_marbete.mensajes import plantilla_consulta_marbete
from fitosanitarios.tools.consultar_productos.mensajes import plantilla_listado
from fitosanitarios.tools.evaluar_riesgo.mensajes import plantilla_detalle_bandas, plantilla_riesgo
from fitosanitarios.tools.evaluar_viabilidad_legal.mensajes import plantilla_dictamen
from fitosanitarios.tools.leer_receta.mensajes import plantilla_confirmacion_receta
from fitosanitarios.tools.listar_limitaciones.mensajes import plantilla_limitaciones
from fitosanitarios.tools.registrar_evento.mensajes import plantilla_evento_registrado
from fitosanitarios.tools.resolver_vehiculo.mensajes import plantilla_consulta_vehiculo
from fitosanitarios.tools.responder_consulta_normativa.mensajes import (
    plantilla_consulta_normativa,
)
from fitosanitarios.tools.validar_producto_registro.mensajes import plantilla_producto

LIMITE_CARACTERES_WHATSAPP = 4096


# --- tipos de respuesta que producen varias tools ---


def _plantilla_dictamen(respuesta: RespuestaAgente, resultados: list[ResultadoTool]) -> str:
    """Con veredicto es el dictamen de `evaluar_viabilidad_legal`; sin él, un
    `evaluar_riesgo` suelto (solo las condiciones de aplicación)."""
    datos = primer_dato(resultados) or {}
    if datos.get("dictamen") is None:
        return plantilla_riesgo(respuesta, resultados)
    return plantilla_dictamen(respuesta, resultados)


def _plantilla_consulta_producto(
    respuesta: RespuestaAgente, resultados: list[ResultadoTool]
) -> str:
    """Un listado (`consultar_productos`) o un producto puntual
    (`validar_producto_registro`), según la forma del resultado."""
    datos = primer_dato(resultados) or {}
    if "productos" in datos:
        return plantilla_listado(respuesta, resultados)
    return plantilla_producto(respuesta, resultados)


# --- comunes ---


# --- repregunta ---


def _plantilla_repregunta(respuesta: RespuestaAgente, resultados: list[ResultadoTool]) -> str:
    # Si una tool de este turno ya dijo qué falta (y con qué opciones), eso manda: el LLM
    # reescribía las opciones por su cuenta y llegó a inventar una norma que no existe.
    de_tools = next((r.faltantes for r in resultados if r.faltantes), [])
    faltantes = de_tools or respuesta.faltantes
    if not faltantes:
        return (
            "Necesito un dato más para continuar, pero no pude identificar cuál. "
            "¿Podés repetir el mensaje?"
        )
    # Estructura fija: la pregunta y, si corresponde, sus opciones. Sin encabezado
    # ni nombre de campo: la pregunta tiene que entenderse sola.
    varias = len(faltantes) > 1
    lineas: list[str] = []
    for i, f in enumerate(faltantes[:3], start=1):
        lineas.append(f"{i}. {f.pregunta_sugerida}" if varias else f.pregunta_sugerida)
        if f.tipo_entrada == "botones" and f.opciones:
            lineas.append("[" + "] [".join(f.opciones) + "]")
        elif f.tipo_entrada == "lista" and f.opciones:
            lineas.extend(f"   - {o}" for o in f.opciones[:10])
    return "\n".join(lineas)


# --- fuera_de_dominio ---


def _plantilla_fuera_de_dominio(respuesta: RespuestaAgente, resultados: list[ResultadoTool]) -> str:
    return (
        "Solo puedo ayudarte con recetas de fitosanitarios: leer y validar recetas, "
        "verificar productos registrados en SENASA, responder dudas sobre la normativa "
        "de aplicación de las localidades cargadas, y registrar/consultar tus "
        "aplicaciones en el campo. ¿Me mandás una receta o una consulta sobre eso?"
    )


# --- no_resuelto ---


def _plantilla_no_resuelto(respuesta: RespuestaAgente, resultados: list[ResultadoTool]) -> str:
    motivo: MotivoNoResuelto | None = next((r.motivo for r in resultados if r.motivo), None)
    porque = DESCRIPCION_MOTIVO.get(motivo, "no se pudo determinar el motivo exacto.")

    advertencias = [a for r in resultados for a in r.advertencias]
    lineas = ["⚠️ *No pude completar la consulta*", f"*Por qué:* {porque}"]
    if advertencias:
        lineas.append(f"*Detalle:* {advertencias[0]}")
    lineas.append(
        "*Qué podés hacer:* revisá el dato e intentá de nuevo, o consultá al área de "
        "ambiente del municipio / a tu ingeniero agrónomo."
    )
    return "\n".join(lineas)


# --- ayuda ---


def _plantilla_ayuda(respuesta: RespuestaAgente, resultados: list[ResultadoTool]) -> str:
    return (
        "Hola 👋 Soy el asistente de recetas fitosanitarias. Puedo:\n"
        "- Leer una foto de tu receta y decirte si es apta para aplicar.\n"
        "- Buscar si un producto está registrado en SENASA y qué dice su marbete "
        "(carencia, precauciones, mezclas).\n"
        "- Responder dudas sobre la normativa de aplicación de tu localidad, mostrarte el "
        "texto de un artículo o decirte qué limitaciones tiene.\n"
        "- Registrar cuando empezás y terminás de aplicar.\n"
        "- Contarte tu agenda del día.\n"
        "Mandame una foto de receta o contame qué necesitás."
    )


# --- error ---


def _plantilla_error(respuesta: RespuestaAgente, resultados: list[ResultadoTool]) -> str:
    return (
        "⚠️ Tuve un problema técnico y no pude procesar tu mensaje. Probá de nuevo en "
        "unos minutos; si sigue fallando, contactá a soporte."
    )


_PLANTILLAS = {
    "confirmacion_receta": plantilla_confirmacion_receta,
    "dictamen": _plantilla_dictamen,
    "consulta_producto": _plantilla_consulta_producto,
    "consulta_normativa": plantilla_consulta_normativa,
    "repregunta": _plantilla_repregunta,
    "fuera_de_dominio": _plantilla_fuera_de_dominio,
    "no_resuelto": _plantilla_no_resuelto,
    "ayuda": _plantilla_ayuda,
    "error": _plantilla_error,
    "consulta_vehiculo": plantilla_consulta_vehiculo,
    "evento_registrado": plantilla_evento_registrado,
    "agenda": plantilla_agenda,
    "detalle_bandas": plantilla_detalle_bandas,
    "agendar_aplicacion": plantilla_agendar_aplicacion,
    "consulta_articulo": plantilla_consulta_articulo,
    "limitaciones": plantilla_limitaciones,
    "consulta_marbete": plantilla_consulta_marbete,
}


def _partir_bloque_largo(bloque: str, limite: int) -> list[str]:
    """Un bloque más largo que el límite (un artículo de ley, por ejemplo): se
    parte por renglones, y si un renglón solo lo supera, por oraciones y en último
    caso por palabras. Nunca corta a mitad de una palabra."""
    unidades: list[str] = []
    for renglon in bloque.split("\n"):
        if len(renglon) <= limite:
            unidades.append(renglon)
            continue
        for oracion in re.split(r"(?<=[.;:])\s+", renglon):
            while len(oracion) > limite:
                corte = oracion.rfind(" ", 0, limite)
                corte = corte if corte > 0 else limite
                unidades.append(oracion[:corte])
                oracion = oracion[corte:].lstrip()
            unidades.append(oracion)
    partes: list[str] = []
    actual = ""
    for unidad in unidades:
        candidato = f"{actual}\n{unidad}" if actual else unidad
        if len(candidato) > limite and actual:
            partes.append(actual)
            actual = unidad
        else:
            actual = candidato
    if actual:
        partes.append(actual)
    return partes


def partir_por_seccion(texto: str, limite: int = LIMITE_CARACTERES_WHATSAPP) -> list[str]:
    """Parte un mensaje largo por sección (separadas por línea en blanco),
    nunca a mitad de una lista (ver skill, "Formato de respuestas"). Una sola
    sección que supera el límite se parte aparte (`_partir_bloque_largo`)."""
    if len(texto) <= limite:
        return [texto]
    secciones = [
        parte
        for seccion in texto.split("\n\n")
        for parte in (_partir_bloque_largo(seccion, limite) if len(seccion) > limite else [seccion])
    ]
    mensajes: list[str] = []
    actual = ""
    for seccion in secciones:
        candidato = f"{actual}\n\n{seccion}" if actual else seccion
        if len(candidato) > limite and actual:
            mensajes.append(actual)
            actual = seccion
        else:
            actual = candidato
    if actual:
        mensajes.append(actual)
    return mensajes


def _forma_de(datos: dict | None) -> str | None:
    for propio, tiene_esa_forma in _FORMAS_PROPIAS.items():
        if datos and tiene_esa_forma(datos):
            return propio
    return None


def _respuestas_de_consultas(resultados: list[ResultadoTool]) -> list[tuple[str, ResultadoTool]]:
    """Cada consulta distinta que el turno contestó, con su plantilla. Llamadas idénticas (el
    LLM repitió una tool con los mismos argumentos) cuentan una sola vez."""
    vistas: set[tuple[str, str]] = set()
    respuestas: list[tuple[str, ResultadoTool]] = []
    for r in resultados:
        forma = _forma_de(r.datos)
        if forma is None:
            continue
        clave = (forma, json.dumps(r.datos, sort_keys=True, default=str))
        if clave not in vistas:
            vistas.add(clave)
            respuestas.append((forma, r))
    return respuestas


def _texto_de_varias_consultas(
    respuesta: RespuestaAgente, resultados: list[ResultadoTool]
) -> str | None:
    """Un mensaje con varias preguntas ("¿y en El Trébol a 1000 m? y pasame el art. 33")
    se contesta entero: una sección por cada consulta, y al final lo que una tool todavía
    necesita saber. Antes se mostraba solo el primer resultado y el resto se perdía
    (hallazgo H3 de la evaluación conversacional). `None` si no es ese caso."""
    respuestas = _respuestas_de_consultas(resultados)
    pendientes = [
        r for r in resultados if r.estado == "faltan_datos" and r.faltantes and not r.datos
    ]
    if len(respuestas) < 2 and not (respuestas and pendientes):
        return None
    secciones = [_PLANTILLAS[forma](respuesta, [r]) for forma, r in respuestas]
    if pendientes:
        secciones.append(_plantilla_repregunta(respuesta, pendientes))
    return "\n\n".join(s for s in secciones if s.strip())


def formatear_respuesta(respuesta: RespuestaAgente, resultados: list[ResultadoTool]) -> list[str]:
    """Punto de entrada del formateador: `RespuestaAgente.tipo` + los
    `ResultadoTool` de las tools ejecutadas en el turno -> lista de mensajes
    de WhatsApp (más de uno solo si supera el límite de caracteres)."""
    varias = _texto_de_varias_consultas(respuesta, resultados)
    if varias is not None:
        return partir_por_seccion(varias)
    tipo = _tipo_efectivo(respuesta.tipo, resultados)
    texto = _PLANTILLAS[tipo](respuesta, resultados)
    return partir_por_seccion(texto)


# Resultados con una forma propia, que solo una plantilla sabe mostrar.
_FORMAS_PROPIAS = {
    # Por tipo de valor, no solo por nombre: una receta leída también tiene un campo
    # `restricciones` y otro `condiciones`, pero son texto.
    "limitaciones": lambda datos: (
        isinstance(datos.get("prohibiciones"), list) or isinstance(datos.get("restricciones"), list)
    ),
    "consulta_articulo": lambda datos: isinstance(datos.get("partes"), list),
    "consulta_marbete": lambda datos: "respuesta" in datos and "numero_inscripcion" in datos,
    "consulta_normativa": lambda datos: "veredicto" in datos and "regla" in datos,
    # el listado de `consultar_productos` trae `total` (los datos de `evaluar_riesgo` también
    # traen `productos`, pero no `total`); uno vacío no tiene qué mostrar: no cuenta
    "consulta_producto": lambda datos: (
        (bool(datos.get("productos")) and "total" in datos)
        or ("numero_inscripcion" in datos and "cultivo_autorizado" in datos)
    ),
}


def _tipo_segun_los_datos(tipo: str, datos: dict) -> str:
    """El LLM elige el `tipo`, pero la forma del resultado es inequívoca: si es la de
    las limitaciones o la de un artículo, esa plantilla es la única que sirve; y si
    dijo `limitaciones` o `consulta_articulo` para el resultado de otra tool (Gemini lo
    hizo con `evaluar_riesgo`: salía "*Limitaciones en *" vacío), se muestra como
    dictamen."""
    for propio, tiene_esa_forma in _FORMAS_PROPIAS.items():
        if tiene_esa_forma(datos):
            return propio
    if tipo in _FORMAS_PROPIAS and (
        isinstance(datos.get("dictamen"), dict) or isinstance(datos.get("condiciones"), dict)
    ):
        return "dictamen"
    return tipo


_TIPOS_DE_CONSULTA = (
    "consulta_producto", "consulta_normativa", "consulta_articulo", "limitaciones",
    "dictamen", "detalle_bandas",
)


def _tipo_efectivo(tipo: str, resultados: list[ResultadoTool]) -> str:
    """El tipo que se usa para elegir la plantilla. Si hay datos, manda su forma
    (`_tipo_segun_los_datos`). Si la tool no llegó a evaluar nada (faltó un dato, p. ej.
    la provincia) no hay dictamen ni bandas que mostrar: se responde lo que la tool
    devolvió en vez de una plantilla vacía (bug real: `tipo="dictamen"` tras un
    `faltan_datos` salía como una sola frase)."""
    # Una tool que pidió un dato sin haber evaluado nada manda sobre lo que devolvió otra
    # en el mismo turno: el operario tiene que contestar eso (bug real de Gemini: llamó a
    # `validar_producto_registro`, que preguntó cuál de 5 productos, y a `consultar_productos`,
    # cuyo listado vacío se mostró en su lugar como "No encontré productos").
    if tipo in _TIPOS_DE_CONSULTA and any(
        r.estado == "faltan_datos" and r.faltantes and not r.datos for r in resultados
    ):
        return "repregunta"
    datos = primer_dato(resultados)
    if datos:
        return _tipo_segun_los_datos(tipo, datos)
    if tipo not in ("dictamen", "detalle_bandas", "consulta_articulo", "limitaciones"):
        return tipo
    for r in resultados:
        if r.estado == "faltan_datos":
            return "repregunta"
        if r.estado == "no_resuelto":
            return "no_resuelto"
    return tipo
