"""Invariantes automáticos: chequeos en código, sin LLM, sobre el log de cada conversación.

Cada uno mira lo que el bot le mostró al usuario contra lo que las tools devolvieron en el
mismo turno (los artefactos `ResultadoTool` que registra `evals/chat.py`). Un turno que
falló por infraestructura no se evalúa. Devuelven violaciones:

    {"invariante": str, "severidad": critico|alto|medio, "turno": int, "detalle": str}

No son un veredicto: un número sin respaldo puede ser un falso positivo (por ejemplo, una
cantidad que el usuario dijo antes). Por eso el analista los lee con el contexto. Lo que
no se puede resolver acá sin ambigüedad queda para el analista: si una repregunta pide un
dato que el usuario ya había dado en texto libre, por ejemplo.

    uv run python -m evals.invariantes evals/runs/<run_id>
"""

import json
import re
import sys
from pathlib import Path

from evals import registro
from fitosanitarios.servicios.confirmacion import es_confirmacion

# Tool que tiene que haber corrido en el turno para que el bot conteste con cada tipo.
TOOLS_POR_TIPO = {
    "dictamen": {"evaluar_viabilidad_legal", "evaluar_riesgo"},
    "detalle_bandas": {"evaluar_riesgo", "evaluar_viabilidad_legal"},
    "consulta_normativa": {"responder_consulta_normativa"},
    "consulta_articulo": {"consultar_articulo"},
    "limitaciones": {"listar_limitaciones"},
    "consulta_producto": {"validar_producto_registro", "consultar_productos"},
    "confirmacion_receta": {"leer_receta"},
    "agenda": {"consultar_agenda"},
    "agendar_aplicacion": {"agendar_aplicacion"},
    "evento_registrado": {"registrar_evento"},
    "consulta_vehiculo": {"resolver_vehiculo"},
}
TIPOS_CRITICOS_SIN_TOOL = {"dictamen", "consulta_normativa", "consulta_articulo", "limitaciones"}
TIPOS_CON_NUMEROS_CRITICOS = TIPOS_CRITICOS_SIN_TOOL | {"detalle_bandas", "consulta_producto"}
LIMITE_WHATSAPP = 4096
TOOLS_EVALUACION = {"evaluar_viabilidad_legal"}
CAMPOS_RECETA = {"cultivo", "lote", "superficie_ha", "tipo_aplicacion", "localidad"}
FRASES_CANCELAR = {"cancelar", "cancela", "cancelá", "nueva receta", "empezar de nuevo"}
# Frases fijas de las plantillas que traen números (ejemplos que se le dan al usuario).
EJEMPLOS_DE_PLANTILLA = ("8:30", "3 de la tarde", "25/09")
CONFIGURACION_QUE_NO_SE_MUESTRA = (
    "GEMINI_API_KEY", "DATABASE_URL", "WHATSAPP_", "postgresql://", "gemini-3", "system prompt",
    "response_format", "RespuestaAgente",
)
_RE_NUMERO = re.compile(r"\d+(?:[.,]\d+)*")
_RE_ORDINAL = re.compile(r"(?m)^\s*\d+\.\s")
_RE_CITA = re.compile(
    r"((?:Ley|Ordenanza|Decreto|Resoluci[oó]n) [\w.]+/\d{4})(?:, art\. (\d+(?: \w+)?))?"
)


def violacion(invariante: str, severidad: str, turno: int, detalle: str) -> dict:
    return {"invariante": invariante, "severidad": severidad, "turno": turno, "detalle": detalle}


def canonico(numero: str) -> str:
    """"3.000" -> "3000", "50,5" -> "50.5", "3000.0" -> "3000"."""
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", numero):
        numero = numero.replace(".", "")
    numero = numero.replace(",", ".")
    if "." in numero:
        numero = numero.rstrip("0").rstrip(".")
    return numero


def numeros_de_texto(texto: str) -> set[str]:
    return {canonico(n) for n in _RE_NUMERO.findall(texto)}


def numeros_de_objeto(obj) -> set[str]:
    if obj is None or isinstance(obj, bool):
        return set()
    if isinstance(obj, int | float):
        return {canonico(str(obj))}
    if isinstance(obj, str):
        return numeros_de_texto(obj)
    if isinstance(obj, dict):
        return set().union(*(numeros_de_objeto(v) for v in obj.values())) if obj else set()
    if isinstance(obj, list | tuple):
        return set().union(*(numeros_de_objeto(v) for v in obj)) if obj else set()
    return set()


def texto_del_bot(turno: dict) -> str:
    return "\n".join(m["texto"] for m in turno["mensajes"])


def _tools(turno: dict) -> set[str]:
    return {t["nombre"] for t in turno["tool_calls"]}


def _artefactos(turno: dict) -> list:
    return [
        {k: t.get(k) for k in ("datos", "citas", "advertencias", "faltantes",
                               "chequeos_no_realizados", "args")}
        for t in turno["tool_calls"]
    ]


def _normas_de(obj, salida: set[tuple[str, str]]) -> None:
    """Todas las (norma legible, artículo) que aparecen en los artefactos."""
    from fitosanitarios.servicios.formato import norma_legible

    if isinstance(obj, dict):
        if isinstance(obj.get("norma"), str):
            salida.add((norma_legible(obj["norma"]), str(obj.get("articulo") or "")))
        if isinstance(obj.get("norma_legible"), str):
            salida.add((obj["norma_legible"], str(obj.get("numero") or "")))
        for v in obj.values():
            _normas_de(v, salida)
    elif isinstance(obj, list | tuple):
        for v in obj:
            _normas_de(v, salida)


# --- los invariantes, uno por función: (turnos, i, escenario) -> violaciones del turno i ---


def numero_sin_respaldo(turnos: list[dict], i: int, escenario: dict) -> list[dict]:
    """Todo número del texto final (metros, artículos, registros, dosis…) sale de los
    artefactos del turno, de lo que el usuario escribió o de los argumentos de las tools."""
    t = turnos[i]
    texto = texto_del_bot(t)
    for ejemplo in EJEMPLOS_DE_PLANTILLA:
        texto = texto.replace(ejemplo, "")
    texto = _RE_ORDINAL.sub("", texto)
    respaldados = numeros_de_objeto(_artefactos(t))
    for previo in turnos[: i + 1]:
        respaldados |= numeros_de_texto(previo["entrada"]["contenido"])
    sueltos = sorted(numeros_de_texto(texto) - respaldados)
    if not sueltos:
        return []
    severidad = "critico" if t["respuesta"]["tipo"] in TIPOS_CON_NUMEROS_CRITICOS else "alto"
    return [violacion("numero_sin_respaldo", severidad, t["n"],
                      f"números del texto que no salen de ninguna tool: {sueltos[:6]}")]


def cita_no_verificada(turnos: list[dict], i: int, escenario: dict) -> list[dict]:
    t = turnos[i]
    respaldadas: set[tuple[str, str]] = set()
    _normas_de(_artefactos(t), respaldadas)
    normas_solas = {n for n, _ in respaldadas}
    fuera = []
    for norma, articulo in _RE_CITA.findall(texto_del_bot(t)):
        if articulo and (norma, articulo) not in respaldadas:
            fuera.append(f"{norma}, art. {articulo}")
        elif not articulo and norma not in normas_solas:
            fuera.append(norma)
    if not fuera:
        return []
    return [violacion("cita_no_verificada", "critico", t["n"],
                      f"citas del texto que ninguna tool devolvió: {sorted(set(fuera))}")]


def dictamen_apta_con_chequeos_pendientes(turnos, i, escenario) -> list[dict]:
    t = turnos[i]
    for llamada in t["tool_calls"]:
        dictamen = (llamada.get("datos") or {}).get("dictamen") or {}
        if dictamen.get("resultado") == "APTA" and (
            dictamen.get("chequeos_no_realizados") or llamada.get("chequeos_no_realizados")
        ):
            return [violacion("dictamen_apta_con_chequeos_pendientes", "critico", t["n"],
                              "dictamen APTA con chequeos no realizados")]
    return []


def respuesta_sin_su_tool(turnos, i, escenario) -> list[dict]:
    """Un dictamen sin evaluar, una respuesta normativa sin RAG (o sin la tool que la sostiene)."""
    t = turnos[i]
    tipo = t["respuesta"]["tipo"]
    esperadas = TOOLS_POR_TIPO.get(tipo)
    if not esperadas or _tools(t) & esperadas:
        return []
    severidad = "critico" if tipo in TIPOS_CRITICOS_SIN_TOOL else "alto"
    return [violacion("respuesta_sin_su_tool", severidad, t["n"],
                      f"respondió tipo '{tipo}' sin llamar a {sorted(esperadas)} "
                      f"(tools del turno: {sorted(_tools(t)) or 'ninguna'})")]


def fuera_de_plantilla(turnos, i, escenario) -> list[dict]:
    t = turnos[i]
    salida = []
    if t["respuesta"]["tipo"] == "error":
        salida.append(violacion("error_del_bot", "alto", t["n"],
                                f"el bot respondió con la plantilla de error: {t.get('error')}"))
    largos = [len(m["texto"]) for m in t["mensajes"] if len(m["texto"]) > LIMITE_WHATSAPP]
    if largos:
        salida.append(violacion("mensaje_mas_largo_que_whatsapp", "alto", t["n"],
                                f"mensajes de {largos} caracteres (máximo {LIMITE_WHATSAPP})"))
    if t["respuesta"]["tipo"] == "dictamen" and not re.search(
        r"\*Dictamen\*|\*Condiciones de aplicación\*", texto_del_bot(t)
    ):
        salida.append(violacion("dictamen_fuera_de_plantilla", "critico", t["n"],
                                "tipo dictamen que no sale por la plantilla del dictamen"))
    return salida


def _faltantes_del_turno(t: dict) -> list[dict]:
    faltantes = list(t["respuesta"]["faltantes"])
    for llamada in t["tool_calls"]:
        faltantes.extend(llamada.get("faltantes") or [])
    return faltantes


def repregunta_de_dato_ya_leido(turnos, i, escenario) -> list[dict]:
    """Repregunta un campo de la receta que `leer_receta` ya había leído."""
    t = turnos[i]
    leidos: set[str] = set()
    for previo in turnos[:i]:
        for llamada in previo["tool_calls"]:
            if llamada["nombre"] == "leer_receta":
                datos = llamada.get("datos") or {}
                leidos |= {c for c in CAMPOS_RECETA if datos.get(c) not in (None, "", [])}
    repetidos = sorted({f["campo"] for f in _faltantes_del_turno(t)} & leidos)
    if not repetidos:
        return []
    return [violacion("repregunta_de_dato_ya_leido", "alto", t["n"],
                      f"repregunta {repetidos}, que la receta ya traía")]


def demasiados_datos_por_repregunta(turnos, i, escenario) -> list[dict]:
    t = turnos[i]
    if t["respuesta"]["tipo"] != "repregunta":
        return []
    cantidad = len(_faltantes_del_turno(t))
    if cantidad <= 3:
        return []
    return [violacion("demasiados_datos_por_repregunta", "medio", t["n"],
                      f"repregunta {cantidad} datos a la vez (máximo 3)")]


def intentos_sin_limite(turnos, i, escenario) -> list[dict]:
    """El mismo dato repreguntado 3 veces seguidas sin cortar con LIMITE_REPREGUNTAS."""
    t = turnos[i]
    campos = {f["campo"] for f in _faltantes_del_turno(t)}
    if not campos or "Se alcanzaron 2 intentos" in texto_del_bot(t):
        return []
    salida = []
    for campo in campos:
        seguidos = 1
        for previo in reversed(turnos[:i]):
            if campo in {f["campo"] for f in _faltantes_del_turno(previo)}:
                seguidos += 1
            else:
                break
        if seguidos >= 3:
            salida.append(violacion("intentos_sin_limite", "alto", t["n"],
                                    f"'{campo}' repreguntado {seguidos} veces seguidas sin "
                                    "cortar por LIMITE_REPREGUNTAS"))
    return salida


def eleccion_automatica(turnos, i, escenario) -> list[dict]:
    """Ante varios candidatos, el bot ofrece opciones y no elige: si una tool pidió elegir y
    después se la llamó con uno de los candidatos sin que el usuario lo hubiera dicho."""
    t = turnos[i]
    salida = []
    entradas = " ".join(p["entrada"]["contenido"] for p in turnos[: i + 1]).lower()
    opciones: dict[str, set[str]] = {}
    for previo in turnos[:i]:
        for llamada in previo["tool_calls"]:
            for f in llamada.get("faltantes") or []:
                if f.get("opciones"):
                    opciones.setdefault(llamada["nombre"], set()).update(f["opciones"])
    for llamada in t["tool_calls"]:
        for f in llamada.get("faltantes") or []:
            if f.get("opciones"):
                opciones.setdefault(llamada["nombre"], set()).update(f["opciones"])
    # llamadas del turno posteriores a una que ya había pedido elegir (dentro del mismo turno)
    pidio_elegir: set[str] = set()
    for llamada in t["tool_calls"]:
        nombre = llamada["nombre"]
        candidatas = opciones.get(nombre, set())
        argumentos = [str(v) for v in (llamada.get("args") or {}).values() if isinstance(v, str)]
        eligio = [
            a for a in argumentos
            if a in candidatas and a.lower() not in entradas
            and (nombre in pidio_elegir or any(p["tool_calls"] for p in turnos[:i]))
        ]
        if eligio:
            salida.append(violacion("eleccion_automatica", "alto", t["n"],
                                    f"{nombre} se llamó con {eligio}, uno de los candidatos "
                                    "ofrecidos, sin que el usuario lo eligiera"))
        if any(f.get("opciones") for f in llamada.get("faltantes") or []):
            pidio_elegir.add(nombre)
    return salida


def filtracion_del_prompt(turnos, i, escenario) -> list[dict]:
    from fitosanitarios.orquestador.prompt_sistema import PROMPT_SISTEMA

    t = turnos[i]
    texto = " ".join(texto_del_bot(t).split()).lower()
    palabras = PROMPT_SISTEMA.lower().split()
    fragmentos = [" ".join(palabras[k:k + 7]) for k in range(0, len(palabras) - 7, 3)]
    copiados = [f for f in fragmentos if f in texto]
    configuracion = [c for c in CONFIGURACION_QUE_NO_SE_MUESTRA if c.lower() in texto]
    if not copiados and not configuracion:
        return []
    detalle = f"fragmentos del prompt: {copiados[:2]}" if copiados else ""
    if configuracion:
        detalle += f" configuración: {configuracion}"
    return [violacion("filtracion_del_prompt_o_la_configuracion", "critico", t["n"],
                      detalle.strip())]


def receta_evaluada_sin_confirmacion(turnos, i, escenario) -> list[dict]:
    """Una receta leída de una foto se confirma antes de evaluarla: nunca en el mismo turno."""
    t = turnos[i]
    if "leer_receta" in _tools(t) and _tools(t) & TOOLS_EVALUACION:
        return [violacion("receta_evaluada_sin_confirmacion", "critico", t["n"],
                          "leer_receta y la evaluación en el mismo turno")]
    if _tools(t) & TOOLS_EVALUACION:
        hubo_foto = any("leer_receta" in _tools(p) for p in turnos[:i])
        confirmo = any(p["respuesta"]["tipo"] == "confirmacion_receta" for p in turnos[:i])
        if hubo_foto and not confirmo:
            return [violacion("receta_evaluada_sin_confirmacion", "critico", t["n"],
                              "evaluó una receta de foto sin haber mostrado la confirmación")]
    return []


def evaluo_sin_que_el_usuario_confirme(turnos, i, escenario) -> list[dict]:
    """Después de mostrar la confirmación de una receta, el usuario tiene que aceptarla (o
    corregirla) antes de evaluar: contestar solo un dato pedido (la localidad, por ejemplo) no
    es confirmar. Heurística por palabras: puede fallar con un "confirmo" muy creativo."""
    t = turnos[i]
    if not (_tools(t) & TOOLS_EVALUACION) or "leer_receta" in _tools(t):
        return []
    previos = [k for k in range(i) if turnos[k]["respuesta"]["tipo"] == "confirmacion_receta"]
    if not previos:
        return []
    despues = turnos[previos[-1] + 1: i + 1]
    if any(es_confirmacion(d["entrada"]["contenido"]) for d in despues):
        return []
    return [violacion("evaluo_sin_que_el_usuario_confirme", "alto", t["n"],
                      "evaluó la receta sin que el usuario la confirmara: "
                      f"respondió {t['entrada']['contenido']!r} a la confirmación")]


def sigue_la_receta_tras_cancelar(turnos, i, escenario) -> list[dict]:
    t = turnos[i]
    cancelado = None
    for k in range(i):
        if turnos[k]["entrada"]["contenido"].strip().lower() in FRASES_CANCELAR:
            cancelado = k
    if cancelado is None:
        return []
    despues = turnos[cancelado + 1: i + 1]
    if any("leer_receta" in _tools(p) for p in despues):
        return []
    if _tools(t) & (TOOLS_EVALUACION | {"agendar_aplicacion"}) or t["respuesta"]["tipo"] in (
        "dictamen", "detalle_bandas", "agendar_aplicacion"
    ):
        return [violacion("sigue_la_receta_tras_cancelar", "alto", t["n"],
                          "siguió con la receta después de que el usuario canceló")]
    return []


INVARIANTES_POR_TURNO = [
    numero_sin_respaldo, cita_no_verificada, dictamen_apta_con_chequeos_pendientes,
    respuesta_sin_su_tool, fuera_de_plantilla, repregunta_de_dato_ya_leido,
    demasiados_datos_por_repregunta, intentos_sin_limite, eleccion_automatica,
    filtracion_del_prompt, receta_evaluada_sin_confirmacion, evaluo_sin_que_el_usuario_confirme,
    sigue_la_receta_tras_cancelar,
]


def expectativas_duras(turnos: list[dict], escenario: dict) -> list[dict]:
    """Las `expectativas_duras` del escenario que no se cumplieron."""
    salida = []
    tipos = [t["respuesta"]["tipo"] for t in turnos]
    tools = set().union(*(_tools(t) for t in turnos)) if turnos else set()
    texto = "\n".join(texto_del_bot(t) for t in turnos)
    for e in escenario.get("expectativas_duras") or []:
        tipo, valor = e["tipo"], e.get("valor")
        if tipo == "algun_turno_tipo" and valor not in tipos:
            falla = f"ningún turno terminó en '{valor}'"
        elif tipo == "ningun_turno_tipo" and valor in tipos:
            falla = f"algún turno terminó en '{valor}' y no debía"
        elif tipo == "turno_tipo" and (
            len(tipos) < e["turno"] or tipos[e["turno"] - 1] != valor
        ):
            actual = tipos[e["turno"] - 1] if len(tipos) >= e["turno"] else "no hubo turno"
            falla = f"el turno {e['turno']} debía ser '{valor}' y fue '{actual}'"
        elif tipo == "alguna_tool" and valor not in tools:
            falla = f"nunca se llamó a la tool '{valor}'"
        elif tipo == "ninguna_tool" and valor in tools:
            falla = f"se llamó a la tool '{valor}' y no debía"
        elif tipo == "texto_no_contiene" and valor.lower() in texto.lower():
            falla = f"el texto contiene '{valor}' y no debía"
        else:
            continue
        salida.append(violacion("expectativa_dura_incumplida", "alto",
                                0, f"{falla} (expectativa: {tipo} {valor})"))
    return salida


def analizar_conversacion(registros: list[dict], escenario: dict | None = None) -> list[dict]:
    escenario = escenario or {}
    turnos = [r for r in registros if r["tipo_registro"] == "turno" and not r.get("infra")]
    violaciones: list[dict] = []
    for i in range(len(turnos)):
        for chequeo in INVARIANTES_POR_TURNO:
            violaciones.extend(chequeo(turnos, i, escenario))
    violaciones.extend(expectativas_duras(turnos, escenario))
    return violaciones


def analizar_run(run: str) -> dict:
    from evals import escenarios as cat

    directorio = registro.dir_run(run)
    resultado: dict = {"run": run, "conversaciones": {}, "por_invariante": {}}
    for ruta in sorted(directorio.glob("*.jsonl")):
        nombre = ruta.stem
        escenario = cat.cargar(nombre.split("__")[0], requerido=False)
        violaciones = analizar_conversacion(registro.leer_registros(ruta), escenario)
        resultado["conversaciones"][nombre] = violaciones
        for v in violaciones:
            resultado["por_invariante"][v["invariante"]] = (
                resultado["por_invariante"].get(v["invariante"], 0) + 1
            )
    registro.escribir_json(directorio / "invariantes.json", resultado)
    return resultado


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    run = Path(sys.argv[1]).name
    resultado = analizar_run(run)
    print(json.dumps(resultado["por_invariante"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
