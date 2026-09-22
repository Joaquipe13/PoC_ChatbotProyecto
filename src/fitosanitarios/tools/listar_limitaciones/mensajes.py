"""Los mensajes de esta tool: lo que avisa y cómo se le muestran las limitaciones al
operario (la plantilla del tipo de respuesta `limitaciones`)."""

from fitosanitarios.dominio.modelos import Cita, RespuestaAgente, ResultadoTool
from fitosanitarios.servicios.formato import (
    NOMBRE_ZONA,
    cita_norma,
    num,
    primer_dato,
    seccion_fuentes,
    todas_las_citas,
    unir_secciones,
)
from fitosanitarios.servicios.reglas import DISTANCIA_SIN_LIMITE_M

# --- avisos de la tool ---


def aviso_sin_normativa_municipal(localidad: str) -> str:
    return (
        f"No se cuenta con la normativa municipal de {localidad}: las limitaciones "
        "son las de la normativa provincial"
    )


def aviso_tipo_aplicacion_no_entendido(texto: str) -> str:
    return f"No entendí el tipo de aplicación '{texto}': muestro todas"


def aviso_banda_no_entendida(texto: str) -> str:
    return f"No entendí la banda '{texto}': muestro todas"


def resumen_para_llm(resultado: ResultadoTool) -> str:
    """Lo que ve el LLM de la tool. Si la tool pidió un dato, se lo dice para que se lo
    pregunte al operario en vez de volver a llamarla con argumentos inventados."""
    texto = f"listar_limitaciones: estado={resultado.estado}"
    if resultado.faltantes:
        campos = ", ".join(f.campo for f in resultado.faltantes)
        texto += (
            f". Falta: {campos}. Preguntáselo al operario y no vuelvas a llamar la tool "
            "hasta que responda"
        )
    return texto


# --- plantilla del resultado (tipo de respuesta `limitaciones`) ---

_ORDEN_APLICACION = ("aerea", "terrestre", "todas")
_TITULO_APLICACION = {
    "aerea": "*Aplicación aérea*", "terrestre": "*Aplicación terrestre*",
    "todas": "*Cualquier tipo de aplicación*",
}
_NOMBRE_APLICACION = {"aerea": "aérea", "terrestre": "terrestre", "todas": "cualquier aplicación"}
_AVISO_PDF = "  ⚠️ Distancia leída del texto de la norma: verificala con la norma."
_SIN_EXCEPCIONES = "  No hay excepciones cargadas para esa distancia."
_SIN_PROHIBICION = "A esa distancia no hay ninguna prohibición para lo consultado."


def _zona_legible(tipo_zona: str) -> str:
    nombre = NOMBRE_ZONA.get(tipo_zona, tipo_zona.replace("_", " "))
    return nombre[0].upper() + nombre[1:]


def _bandas_legibles(bandas: list[str]) -> str:
    if bandas == ["todas"]:
        return "todas las bandas"
    return ("banda " if len(bandas) == 1 else "bandas ") + ", ".join(bandas)


def _referencia(regla: dict) -> str:
    return cita_norma(
        Cita(fuente="normativa", norma=regla.get("norma"), articulo=regla.get("articulo"))
    )


def _linea_prohibicion(r: dict, con_aplicacion: bool = False) -> list[str]:
    detalle = [_zona_legible(r["tipo_zona"])]
    if con_aplicacion:
        detalle.append(_NOMBRE_APLICACION[r["tipo_aplicacion"]])
    detalle.append(_bandas_legibles(r["bandas"]))
    if r["distancia_min_m"] >= DISTANCIA_SIN_LIMITE_M:
        alcance = "no se puede aplicar en toda la jurisdicción"
    else:
        alcance = f"a menos de {num(r['distancia_min_m'])} m no se puede aplicar"
    lineas = [f"- {' · '.join(detalle)}: {alcance} ({_referencia(r)})"]
    if r.get("observaciones"):
        lineas.append(f"  ⚠️ {r['observaciones']}")
    if r.get("extraida_de_pdf"):
        lineas.append(_AVISO_PDF)
    return lineas


def _linea_condicional(r: dict) -> list[str]:
    detalle = " · ".join(
        [_zona_legible(r["tipo_zona"]), _NOMBRE_APLICACION[r["tipo_aplicacion"]],
         _bandas_legibles(r["bandas"])]
    )
    desde = f"desde {num(r['distancia_min_m'])} m, " if r["distancia_min_m"] else ""
    cond = r.get("condiciones") or "según la norma"
    lineas = [f"- {detalle}: se puede aplicar {desde}si: {cond} ({_referencia(r)})"]
    if r.get("observaciones"):
        lineas.append(f"  ⚠️ {r['observaciones']}")
    return lineas


def _plantilla_a_una_distancia(datos: dict, aclaracion: str, fuentes: str) -> str:
    titulo = f"*A {num(datos['distancia_m'])} m en {datos['localidad']}*"
    restricciones = datos.get("restricciones", [])
    if not restricciones:
        return unir_secciones(titulo, aclaracion, _SIN_PROHIBICION, fuentes)
    lineas: list[str] = []
    for x in restricciones:
        lineas.extend(_linea_prohibicion(x["prohibicion"], con_aplicacion=True))
        if x["excepciones"]:
            lineas.append("  *Excepciones posibles:*")
            for e in x["excepciones"]:
                lineas.extend(f"  {renglon}" for renglon in _linea_condicional(e))
        else:
            lineas.append(_SIN_EXCEPCIONES)
    return unir_secciones(titulo, aclaracion, "\n".join(lineas), fuentes)


def plantilla_limitaciones(respuesta: RespuestaAgente, resultados: list[ResultadoTool]) -> str:
    datos = primer_dato(resultados) or {}
    aclaracion = "\n".join(f"⚠️ {a}" for r in resultados for a in r.advertencias)
    fuentes = seccion_fuentes(todas_las_citas(resultados))

    if datos.get("distancia_m") is not None:
        return _plantilla_a_una_distancia(datos, aclaracion, fuentes)

    secciones = [f"*Limitaciones en {datos.get('localidad', '')}*", aclaracion]
    prohibiciones = datos.get("prohibiciones", [])
    for aplicacion in _ORDEN_APLICACION:
        reglas = [r for r in prohibiciones if r["tipo_aplicacion"] == aplicacion]
        if reglas:
            lineas = [_TITULO_APLICACION[aplicacion]]
            for r in reglas:
                lineas.extend(_linea_prohibicion(r))
            secciones.append("\n".join(lineas))
    condicionales = datos.get("condicionales", [])
    if condicionales:
        lineas = ["*Excepciones*"]
        for r in condicionales:
            lineas.extend(_linea_condicional(r))
        secciones.append("\n".join(lineas))
    secciones.append(fuentes)
    return unir_secciones(*secciones)
