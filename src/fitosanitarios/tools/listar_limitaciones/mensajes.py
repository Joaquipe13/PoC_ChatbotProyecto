"""Los mensajes de esta tool: lo que avisa y cómo se le muestran las limitaciones al
operario (la plantilla del tipo de respuesta `limitaciones`)."""

from fitosanitarios.dominio.modelos import Cita, RespuestaAgente, ResultadoTool
from fitosanitarios.servicios.condiciones_aplicacion import COLOR_BANDA
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


_AVISO_EQUIPO = {
    "drone": (
        "Las normas cargadas no mencionan los drones: muestro las reglas de aplicación "
        "aérea, que es como se los suele encuadrar. Confirmalo con la autoridad de "
        "aplicación antes de aplicar"
    ),
    "mochila": (
        "Las normas cargadas no tienen reglas propias para la mochila (aplicación "
        "manual): muestro las de aplicación terrestre"
    ),
}


def aviso_equipo_sin_norma(equipo: str) -> str:
    return _AVISO_EQUIPO[equipo]


def aviso_producto_no_encontrado(nombre: str) -> str:
    return f"No encontré '{nombre}' en el registro de SENASA: muestro todas las bandas"


def aviso_banda_distinta_del_registro(marca: str, banda: str) -> str:
    return (
        f"{marca} es banda {banda} ({COLOR_BANDA[banda]}) en el registro de SENASA: "
        "uso esa banda"
    )


def aviso_producto_sin_banda(marca: str) -> str:
    return f"{marca} no tiene banda registrada en SENASA: muestro todas las bandas"


def pregunta_producto_ambiguo(nombre: str) -> str:
    return f"Hay varios productos parecidos a '{nombre}', de distinta banda. ¿Cuál es?"


def motivo_producto_ambiguo(nombre: str) -> str:
    return f"'{nombre}' coincide con varios productos de distinta banda"


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


def _tramo(tramo: dict, todas: bool) -> str:
    bandas = "todas las bandas" if todas else _bandas_legibles(tramo["bandas"])
    regla = tramo["regla"]
    if regla is None:
        return f"{bandas}: sin distancia fija"
    if regla["distancia_min_m"] >= DISTANCIA_SIN_LIMITE_M:
        alcance = "en toda la jurisdicción"
    else:
        alcance = f"{num(regla['distancia_min_m'])} m"
    excepciones = ", salvo excepciones" if tramo["con_excepciones"] else ""
    return f"{bandas}: {alcance}{excepciones} ({_referencia(regla)})"


def _seccion_que_rige(que_rige: list[dict], filtro_bandas: list[str] | None) -> str:
    """Arriba de la lista: la distancia que manda para cada zona y aplicación. Cuando la
    ley dice 500 m y la ordenanza 3000 m, el operario tenía que deducir que manda la de
    3000 m (hallazgo del 26/09/2026)."""
    if not que_rige:
        return ""
    lineas = ["*Distancia mínima que rige*"]
    for d in que_rige:
        tramos = d["tramos"]
        todas = not filtro_bandas and len(tramos) == 1
        detalle = "; ".join(_tramo(t, todas) for t in tramos)
        lineas.append(
            f"- {_zona_legible(d['tipo_zona'])} · {_NOMBRE_APLICACION[d['tipo_aplicacion']]}: "
            f"{detalle}"
        )
    return "\n".join(lineas)


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


def _linea_producto(producto: dict | None) -> str:
    """Con qué banda se filtró, cuando salió del producto: "Para *Roundup Max*: banda IV
    (verde)"."""
    if not producto:
        return ""
    banda = producto["banda"]
    color = COLOR_BANDA.get(banda)
    banda_txt = f"banda {banda} ({color})" if color else f"banda {banda}"
    if producto.get("variantes"):
        return f"Para *{producto['marca']}*: {banda_txt}, la de todas sus variantes registradas"
    return f"Para *{producto['marca']}*: {banda_txt}"


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
    producto = _linea_producto(datos.get("producto"))
    if not restricciones:
        titulo = f"*A {distancia} m en {datos['localidad']}*"
        return unir_secciones(titulo, producto, aclaracion, _SIN_PROHIBICION, fuentes)

    secciones = [producto]
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

    secciones = [
        f"*Limitaciones en {datos.get('localidad', '')}*",
        _linea_producto(datos.get("producto")), aclaracion,
        _seccion_que_rige(
            datos.get("que_rige") or [], (datos.get("filtros") or {}).get("bandas")
        ),
    ]
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
