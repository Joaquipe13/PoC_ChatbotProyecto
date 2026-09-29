"""Los mensajes de esta tool: lo que avisa y cómo se le muestra el listado al operario
(una de las dos formas del tipo de respuesta `consulta_producto`; la otra es la de
`validar_producto_registro`)."""

from fitosanitarios.dominio.modelos import RespuestaAgente, ResultadoTool
from fitosanitarios.servicios.formato import (
    num,
    primer_dato,
    seccion_fuentes,
    unir_secciones,
)

SIN_PRODUCTOS = "No encontré productos registrados con esos filtros."
_AVISO_REGISTRO = (
    "Es lo que figura en el registro; qué aplicar lo define la receta del ingeniero agrónomo."
)
AVISO_SOLO_CON_USOS = (
    "Solo aparecen los productos que tienen cultivos y plagas cargados en SENASA; puede "
    "haber otros registrados sin esos datos"
)
MAXIMO_LISTADO = 10

_NOMBRE_APLICACION = {"aerea": "aérea", "terrestre": "terrestre"}
_AVISO_EQUIPO = {
    "drone": (
        "Las normas cargadas no mencionan los drones: tomo las reglas de aplicación aérea, "
        "que es como se los suele encuadrar. Confirmalo con la autoridad de aplicación"
    ),
    "mochila": (
        "Las normas cargadas no tienen reglas propias para la mochila (aplicación manual): "
        "tomo las de aplicación terrestre"
    ),
}


# --- avisos de la tool ---


def motivo_sin_filtros() -> str:
    return (
        "consultar_productos requiere al menos un filtro: cultivo, adversidad, principio "
        "activo, aptitud, banda, firma, marca, o localidad con distancia"
    )


def aviso_filtro_no_encontrado(que: str, valor: str) -> str:
    return f"No encontré {que} '{valor.strip()}' en el registro: busqué sin ese filtro"


def aviso_banda_no_entendida(texto: str) -> str:
    return f"No entendí la banda '{texto}': busqué sin ese filtro"


def aviso_tipo_aplicacion_no_entendido(texto: str) -> str:
    return f"No entendí el tipo de aplicación '{texto}': respondo para aérea y terrestre"


def aviso_equipo_sin_norma(equipo: str) -> str:
    return _AVISO_EQUIPO[equipo]


def aviso_sin_normativa_municipal(localidad: str) -> str:
    return (
        f"No se cuenta con la normativa municipal de {localidad}: las bandas permitidas "
        "salen de la normativa provincial"
    )


def resumen_para_llm(resultado: ResultadoTool) -> str:
    texto = f"consultar_productos: estado={resultado.estado}"
    if resultado.datos:
        totales = ", ".join(str(lst["total"]) for lst in resultado.datos["listados"])
        texto += f", productos encontrados: {totales}"
    if resultado.faltantes:
        campos = ", ".join(f.campo for f in resultado.faltantes)
        texto += (
            f". Falta: {campos}. Preguntáselo al operario y no vuelvas a llamar la tool "
            "hasta que responda"
        )
    return texto


# --- plantilla del resultado (tipo de respuesta `consulta_producto`, listado) ---


def _lista(elementos: list[str], conjuncion: str = "y") -> str:
    if len(elementos) <= 1:
        return "".join(elementos)
    return ", ".join(elementos[:-1]) + f" {conjuncion} {elementos[-1]}"


def _plural(aptitud: str) -> str:
    palabra = aptitud.lower()
    if palabra.endswith(("a", "e", "o")):
        return palabra + "s"
    return palabra + "es" if palabra.endswith(("r", "l", "n")) else palabra


def _titulo(filtros: dict) -> str:
    """Lo que se buscó, con las palabras del registro y del operario: "Fungicidas para
    trigo", "Productos con glifosato de Syngenta, banda III o IV"."""
    aptitudes = filtros.get("aptitudes") or []
    cabeza = _lista([_plural(a) for a in aptitudes], "o") if aptitudes else "productos"
    partes = [cabeza[0].upper() + cabeza[1:]]
    if filtros.get("cultivo"):
        partes.append(f"para {filtros['cultivo'].lower()}")
    if filtros.get("adversidad"):
        partes.append(f"contra {filtros['adversidad'].lower()}")
    if filtros.get("principio_activo"):
        partes.append(f"con {filtros['principio_activo'].lower()}")
    if filtros.get("marca"):
        partes.append(f"con \"{filtros['marca']}\" en el nombre")
    if filtros.get("firma"):
        partes.append(f"de {filtros['firma']}")
    titulo = " ".join(partes)
    if filtros.get("bandas"):
        titulo += f", banda {_lista(filtros['bandas'], 'o')}"
    return titulo


def _dosis(p: dict) -> str:
    dosis = p.get("dosis") or []
    if len(dosis) == 1:
        return f" · {dosis[0]}"
    if dosis:
        return f" · {len(dosis)} dosis distintas según la plaga"
    return ""


def _linea_producto(i: int, p: dict) -> str:
    banda = p.get("banda_toxicologica") or "S/D"
    return (
        f"{i}. *{p.get('marca', '(sin marca)')}* · Reg. SENASA "
        f"{p.get('numero_inscripcion', '-')} · Banda {banda}{_dosis(p)}"
    )


def _linea_bandas(listado: dict) -> str:
    """"*Aérea:* ✅ III y IV · ❌ Ia, Ib y II", como en `listar_limitaciones`. Con las dos
    aplicaciones en una misma lista, se aclara que vale para las dos."""
    aplicaciones = listado["aplicaciones"]
    if len(aplicaciones) > 1:
        nombre = "Aérea y terrestre (lo mismo para las dos)"
    else:
        nombre = _NOMBRE_APLICACION[aplicaciones[0]].capitalize()
    partes = []
    if listado["permitidas"]:
        todas = not listado["con_excepcion"] and not listado["prohibidas"]
        partes.append("✅ todas las bandas" if todas else f"✅ {_lista(listado['permitidas'])}")
    if listado["con_excepcion"]:
        partes.append(f"⚠️ {_lista(listado['con_excepcion'])} solo con excepción")
    if listado["prohibidas"]:
        prohibidas = listado["prohibidas"]
        partes.append(
            "❌ ninguna banda" if not listado["permitidas"] and not listado["con_excepcion"]
            else f"❌ {_lista(prohibidas)}"
        )
    return f"*{nombre}:* {' · '.join(partes)}"


def _seccion_listado(listado: dict, con_bandas: bool) -> str:
    productos = listado["productos"][:MAXIMO_LISTADO]
    lineas = [_linea_bandas(listado)] if con_bandas else []
    if listado["bandas"] == []:
        lineas.append("No hay productos que se puedan aplicar a esa distancia.")
    elif not productos:
        lineas.append(SIN_PRODUCTOS)
    else:
        if listado["total"] > len(productos):
            lineas.append(f"({len(productos)} de {listado['total']})")
        lineas.extend(_linea_producto(i, p) for i, p in enumerate(productos, start=1))
    return "\n".join(lineas)


def plantilla_listado(respuesta: RespuestaAgente, resultados: list[ResultadoTool]) -> str:
    """Una sección por tipo de aplicación cuando la consulta traía una distancia (o una
    sola, si las dos permiten las mismas bandas). Las normas de la distancia van en
    *Fuentes*; el registro de SENASA ya está en cada línea, así que la cita genérica del
    vademécum no se repite."""
    resultado = next(
        (r for r in resultados if r.datos and isinstance(r.datos.get("listados"), list)), None
    )
    datos = (resultado.datos if resultado else primer_dato(resultados)) or {}
    listados = datos.get("listados") or []
    titulo = f"*{_titulo(datos.get('filtros') or {})}*"
    if datos.get("distancia_m") is not None:
        titulo += (
            f" a {num(datos['distancia_m'])} m de la zona urbana de {datos['localidad']}"
        )
    con_bandas = datos.get("distancia_m") is not None
    secciones = [_seccion_listado(lst, con_bandas) for lst in listados] or [SIN_PRODUCTOS]
    avisos = "\n".join(f"⚠️ {a}" for a in (resultado.advertencias if resultado else []))
    hay_productos = any(lst["productos"] for lst in listados)
    normas = [c for c in (resultado.citas if resultado else []) if c.fuente == "normativa"]
    return unir_secciones(
        titulo, *secciones, avisos, _AVISO_REGISTRO if hay_productos else "",
        seccion_fuentes(normas) if normas else "",
    )
