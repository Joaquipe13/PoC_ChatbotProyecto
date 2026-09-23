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
from fitosanitarios.tools.listar_limitaciones.utils import BANDAS

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
_APLICACION_CORTA = {"terrestre": "Terrestre", "aerea": "Aérea"}
_ZONA_CON_ARTICULO = {"zona_urbana": "la zona urbana"}
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
    if r.get("extraida_de_pdf"):
        lineas.append(_AVISO_PDF)
    return lineas


def _linea_condicional(r: dict) -> list[str]:
    """Solo que existe la excepción y dónde está: las condiciones se leen en la norma
    (pedido del usuario, 23/09/2026: no transcribir la reglamentación)."""
    detalle = " · ".join(
        [_zona_legible(r["tipo_zona"]), _NOMBRE_APLICACION[r["tipo_aplicacion"]],
         _bandas_legibles(r["bandas"])]
    )
    desde = f"desde {num(r['distancia_min_m'])} m " if r["distancia_min_m"] else ""
    return [f"- {detalle}: se puede {desde}con condiciones ({_referencia(r)})"]


def _cubre(regla: dict, aplicacion: str, banda: str) -> bool:
    return regla["tipo_aplicacion"] in (aplicacion, "todas") and (
        regla["bandas"] == ["todas"] or banda in regla["bandas"]
    )


def _estado_banda(restricciones: list[dict], aplicacion: str, banda: str) -> str:
    """"si", "no" o "condicional": a esa distancia, con esa aplicación y banda. Es
    condicional si cada prohibición que la alcanza tiene una excepción que la cubre."""
    alcanzan = [x for x in restricciones if _cubre(x["prohibicion"], aplicacion, banda)]
    if not alcanzan:
        return "si"
    if all(any(_cubre(e, aplicacion, banda) for e in x["excepciones"]) for x in alcanzan):
        return "condicional"
    return "no"


def _lista_bandas(bandas: list[str]) -> str:
    return ", ".join(bandas[:-1]) + f" y {bandas[-1]}" if len(bandas) > 1 else bandas[0]


def _linea_aplicacion(restricciones: list[dict], aplicacion: str, bandas: list[str]) -> str:
    por_estado: dict[str, list[str]] = {"si": [], "condicional": [], "no": []}
    for banda in bandas:
        por_estado[_estado_banda(restricciones, aplicacion, banda)].append(banda)
    partes = []
    if not por_estado["si"] and not por_estado["condicional"]:
        partes.append("❌ ninguna banda")
    else:
        if por_estado["si"]:
            partes.append(f"✅ {_lista_bandas(por_estado['si'])}")
        if por_estado["condicional"]:
            normas = dict.fromkeys(
                _referencia(e)
                for x in restricciones for e in x["excepciones"]
                for b in por_estado["condicional"] if _cubre(e, aplicacion, b)
            )
            partes.append(
                f"⚠️ {_lista_bandas(por_estado['condicional'])} solo con excepción "
                f"({'; '.join(normas)})"
            )
        if por_estado["no"]:
            partes.append(f"❌ {_lista_bandas(por_estado['no'])}")
    return f"- *{_APLICACION_CORTA[aplicacion]}:* {' · '.join(partes)}"


def _plantilla_a_una_distancia(datos: dict, aclaracion: str, fuentes: str) -> str:
    """Qué tipo de aplicación y qué bandas se pueden a esa distancia, sin transcribir
    la norma: las normas quedan en *Fuentes* (pedido del usuario, 23/09/2026)."""
    restricciones = datos.get("restricciones", [])
    filtros = datos.get("filtros") or {}
    aplicaciones = [filtros["tipo_aplicacion"]] if filtros.get("tipo_aplicacion") else [
        "terrestre", "aerea"
    ]
    bandas = [b for b in BANDAS if not filtros.get("bandas") or b in filtros["bandas"]]
    zonas = list(dict.fromkeys(x["prohibicion"]["tipo_zona"] for x in restricciones))
    if filtros.get("tipo_zona") and filtros["tipo_zona"] not in zonas:
        zonas.insert(0, filtros["tipo_zona"])

    distancia = num(datos["distancia_m"])
    if not restricciones:
        titulo = f"*A {distancia} m en {datos['localidad']}*"
        return unir_secciones(titulo, aclaracion, _SIN_PROHIBICION, fuentes)

    secciones = []
    for zona in zonas:
        de_la_zona = [x for x in restricciones if x["prohibicion"]["tipo_zona"] == zona]
        nombre = _ZONA_CON_ARTICULO.get(zona) or NOMBRE_ZONA.get(zona, zona.replace("_", " "))
        lineas = [f"*A {distancia} m de {nombre} en {datos['localidad']}*"]
        lineas += [_linea_aplicacion(de_la_zona, a, bandas) for a in aplicaciones]
        secciones.append("\n".join(lineas))
    return unir_secciones(*secciones, aclaracion, fuentes)


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
