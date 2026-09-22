"""Harness de conversación: un turno por vez, por el mismo camino que el webhook de WhatsApp.

Arma el agente igual que `canales/whatsapp/app_produccion.py` (Gemini real como
orquestador, checkpointer Postgres, `ejecutar_turno` con log por turno, contador de
repreguntas) y decide botones y listas con el mismo criterio que `cliente_graph`, pero en
vez de mandar a Meta imprime lo que el usuario vería. Sin firma ni Meta; los threads son
sintéticos.

    uv run python -m evals.chat --run R --thread sim-receta_apta__1 "hola, tengo una receta"
    uv run python -m evals.chat --run R --thread sim-receta_apta__1 --imagen foto.jpg
    uv run python -m evals.chat --run R --thread sim-receta_apta__1 --nuevo
    uv run python -m evals.chat --run R --thread sim-receta_apta__1 --cerrar "objetivo logrado"
    uv run python -m evals.chat --replay evals/runs/R/receta_apta__1.jsonl

Sale a la red a propósito (Gemini). Fuerza `USE_FIXTURES=false` y se niega a correr contra
una base cuyo nombre no termine en `_eval` (ver `evals/base_eval.py`), salvo
`--permitir-base-real`. Códigos de salida: 0 ok, 3 falla de infraestructura (cuota o red:
no es un error del bot), 4 límite de turnos de la conversación.

Lo que imprime es solo lo que vería el usuario; los tool calls, los estados y el resto van
al log (`evals/registro.py`) y a `--interno` (para quien evalúa, no para el simulador).
"""

import argparse
import base64
import difflib
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

os.environ["USE_FIXTURES"] = "false"  # las evaluaciones son con el LLM real

import psycopg  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: E402

from evals import base_eval, registro  # noqa: E402

CODIGO_INFRA = 3
CODIGO_LIMITE = 4
TEXTO_FOTO_POR_DEFECTO = "Te mando la foto de mi receta."  # como `webhook.texto_e_imagen`
_PALABRAS_INFRA = (
    "429", "resource_exhausted", "quota", "503", "unavailable", "timeout", "timed out",
    "connection", "deadline", "overloaded",
)


class _CapturaExcepciones(logging.Handler):
    """`ejecutar_turno` atrapa las excepciones y responde con la plantilla de error: se
    las captura del log para saber si fue el bot o la infraestructura."""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.excepciones: list[BaseException] = []

    def emit(self, record: logging.LogRecord) -> None:
        if record.exc_info and record.exc_info[1] is not None:
            self.excepciones.append(record.exc_info[1])


def es_infraestructura(exc: BaseException) -> bool:
    from fitosanitarios.llm.client import ServicioLLMNoDisponible, _es_error_cuota

    actual: BaseException | None = exc
    while actual is not None:
        if isinstance(actual, ServicioLLMNoDisponible) or _es_error_cuota(actual):
            return True
        texto = f"{type(actual).__name__} {actual}".lower()
        if any(p in texto for p in _PALABRAS_INFRA):
            return True
        actual = actual.__cause__ or actual.__context__
    return False


def preparar_entorno(permitir_base_real: bool) -> None:
    url = os.environ.get("EVAL_DATABASE_URL") or base_eval.url_eval()
    base = base_eval.nombre_base(url)
    if not base.endswith(base_eval.SUFIJO) and not permitir_base_real:
        print(
            f"Me niego a correr contra la base '{base}': las evaluaciones usan un clon "
            f"('*{base_eval.SUFIJO}'). Crealo con `uv run python -m evals.base_eval crear` "
            "y exportá EVAL_DATABASE_URL, o usá --permitir-base-real.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    os.environ["DATABASE_URL"] = url


def como_se_enviaria(mensaje: str) -> dict:
    """Texto, botones o lista, con el mismo criterio que `cliente_graph.enviar_mensajes`."""
    from fitosanitarios.canales.whatsapp import cliente_graph

    cuerpo, opciones = cliente_graph.partir_opciones(mensaje)
    payload = cliente_graph._payload_con_opciones("sim", cuerpo, opciones) if opciones else None
    if payload is None:
        return {"texto": mensaje, "envio": "texto", "opciones": []}
    tipo = payload["interactive"]["type"]
    return {
        "texto": cuerpo, "envio": "botones" if tipo == "button" else "lista",
        "opciones": opciones,
    }


def extraer_del_estado(mensajes: list) -> tuple[list[dict], dict, int]:
    """(tool calls con su resultado, tokens, reintentos) del último turno."""
    from fitosanitarios.dominio.modelos import ResultadoTool
    from fitosanitarios.orquestador.estado import _sanear_args_tool

    inicio = max((i for i, m in enumerate(mensajes) if isinstance(m, HumanMessage)), default=-1)
    llamadas: dict[str, dict] = {}
    tokens = {"entrada": 0, "salida": 0}
    for m in mensajes[inicio + 1:]:
        if isinstance(m, AIMessage):
            uso = m.usage_metadata or {}
            tokens["entrada"] += uso.get("input_tokens", 0)
            tokens["salida"] += uso.get("output_tokens", 0)
            for tc in m.tool_calls:
                if tc["name"] != "RespuestaAgente":
                    llamadas[tc["id"]] = {
                        "nombre": tc["name"], "args": _sanear_args_tool(tc.get("args", {}))
                    }
        elif isinstance(m, ToolMessage) and m.tool_call_id in llamadas:
            art = m.artifact
            if isinstance(art, ResultadoTool):
                llamadas[m.tool_call_id].update({
                    "estado": art.estado, "motivo": art.motivo,
                    "faltantes": [f.model_dump(mode="json") for f in art.faltantes],
                    "citas": [c.model_dump(mode="json") for c in art.citas],
                    "advertencias": art.advertencias,
                    "chequeos_no_realizados": art.chequeos_no_realizados,
                    "datos": art.datos,
                })
            else:
                llamadas[m.tool_call_id].update(
                    {"estado": "sin_resultado", "contenido": str(m.content)[:300]}
                )
    lista = list(llamadas.values())
    nombres = [t["nombre"] for t in lista]
    reintentos = len(nombres) - len(set(nombres))
    return lista, tokens, reintentos


class _AgenteGrabador:
    """Le pasa a `ejecutar_turno` el agente de siempre, pero se queda con lo que devuelve
    `invoke`: los artefactos de las tools (`ResultadoTool`) viven ahí y no sobreviven al
    checkpoint de Postgres, que es de donde salen si se los pide con `get_state`."""

    def __init__(self, agente) -> None:
        self._agente = agente
        self.ultimo: dict = {}

    def invoke(self, *args, **kwargs):
        self.ultimo = self._agente.invoke(*args, **kwargs)
        return self.ultimo


class ContadorPersistente:
    """El `ContadorRepreguntas` de producción vive en la memoria del servidor; acá cada
    turno es un proceso, así que su estado se guarda en un archivo por conversación."""

    def __init__(self, ruta: Path) -> None:
        from fitosanitarios.orquestador.estado import ContadorRepreguntas

        self.ruta = ruta
        self.contador = ContadorRepreguntas()
        for thread, campos in registro.leer_json(ruta, {}).items():
            for campo, n in campos.items():
                self.contador._conteos[thread][campo] = n

    def guardar(self) -> None:
        registro.escribir_json(
            self.ruta, {t: dict(c) for t, c in self.contador._conteos.items()}
        )


def correr_turno(
    thread: str, run: str, texto: str, imagen: Path | None, pausa: float, max_turnos: int,
    interno: bool = False,
) -> tuple[dict | None, int]:
    """Corre un turno y lo registra. Devuelve (registro del turno, código de salida)."""
    from fitosanitarios.config import get_settings
    from fitosanitarios.orquestador.agente import (
        checkpointer_postgres,
        crear_agente,
        crear_modelo_chat_gemini,
    )
    from fitosanitarios.orquestador.turno import ejecutar_turno

    ruta = registro.ruta_log(run, thread)
    previos = registro.leer_turnos(ruta)
    if sum(1 for t in previos if not t.get("infra")) >= max_turnos:
        return None, CODIGO_LIMITE
    n = len(previos) + 1

    settings = get_settings()
    time.sleep(pausa)
    contador = ContadorPersistente(registro.ruta_estado(run, thread))
    imagen_b64 = base64.b64encode(imagen.read_bytes()).decode() if imagen else None
    modelo = crear_modelo_chat_gemini(
        settings, temperature=registro.TEMPERATURA, indice_key=n - 1
    )
    captura = _CapturaExcepciones()
    logger_turno = logging.getLogger("fitosanitarios.orquestador.turno")
    logger_turno.addHandler(captura)
    try:
        with checkpointer_postgres(settings.database_url) as checkpointer:
            agente = _AgenteGrabador(
                crear_agente(modelo, checkpointer=checkpointer, imagen_base64=imagen_b64)
            )
            t0 = time.perf_counter()
            with psycopg.connect(settings.database_url) as conn:
                respuesta, mensajes = ejecutar_turno(
                    agente, thread, texto, contador.contador, conn_log=conn
                )
            latencia = time.perf_counter() - t0
            mensajes_estado = agente.ultimo.get("messages", [])
    finally:
        logger_turno.removeHandler(captura)
    contador.guardar()

    tool_calls, tokens, reintentos = extraer_del_estado(mensajes_estado)
    infra = False
    error = None
    if respuesta.tipo == "error":
        exc = captura.excepciones[-1] if captura.excepciones else None
        infra = exc is not None and es_infraestructura(exc)
        error = f"{type(exc).__name__}: {exc}"[:500] if exc else "sin structured_response"

    entrada = {"tipo": "texto", "contenido": texto}
    if imagen:
        entrada = {"tipo": "imagen", "contenido": texto, "ruta": str(imagen)}
    reg = {
        "tipo_registro": "turno", "n": n, "ts": datetime.now().isoformat(timespec="seconds"),
        "entrada": entrada,
        "intencion": {
            "tipo": respuesta.tipo,
            "primera_tool": tool_calls[0]["nombre"] if tool_calls else None,
        },
        "tool_calls": tool_calls,
        "respuesta": {
            "tipo": respuesta.tipo,
            "faltantes": [f.model_dump(mode="json") for f in respuesta.faltantes],
        },
        "mensajes": [como_se_enviaria(m) for m in mensajes],
        "latencia_s": round(latencia, 2), "tokens": tokens,
        "llamadas_tool": len(tool_calls), "reintentos_tool": reintentos,
        "infra": infra, "error": error,
    }
    registro.agregar(ruta, reg)
    return reg, (CODIGO_INFRA if infra else 0)


def imprimir_lo_que_ve_el_usuario(reg: dict, interno: bool) -> None:
    mensajes = reg["mensajes"]
    for i, m in enumerate(mensajes, start=1):
        if len(mensajes) > 1:
            print(f"[mensaje {i} de {len(mensajes)}]")
        print(m["texto"])
        if m["envio"] == "botones":
            print("[BOTONES: " + " | ".join(m["opciones"]) + "]")
        elif m["envio"] == "lista":
            print("[LISTA: " + " | ".join(m["opciones"]) + "]")
        print()
    if interno:
        print("--- interno (no es lo que ve el usuario) ---")
        print(json.dumps(
            {k: reg[k] for k in ("intencion", "tool_calls", "latencia_s", "tokens", "error")},
            ensure_ascii=False, indent=1, default=str,
        ))


def _texto_de(reg: dict) -> str:
    return " ".join(" ".join(m["texto"].split()) for m in reg["mensajes"])


def replay(ruta_log: Path, pausa: float, max_turnos: int) -> int:
    """Reenvía los mensajes del usuario grabados, sin simulador, en un thread nuevo, y marca
    dónde diverge la respuesta (tipo distinto o texto con parecido < 0,85)."""
    originales = registro.leer_turnos(ruta_log)
    if not originales:
        print(f"No hay turnos en {ruta_log}", file=sys.stderr)
        return 2
    sello = datetime.now().strftime("%Y%m%d-%H%M%S")
    run = f"replay-{sello}"
    thread = f"replay-{registro.nombre_conversacion(ruta_log.stem)}"
    divergencias = []
    for orig in originales:
        if orig.get("infra"):
            continue
        entrada = orig["entrada"]
        imagen = Path(entrada["ruta"]) if entrada["tipo"] == "imagen" else None
        nuevo, codigo = correr_turno(
            thread, run, entrada["contenido"], imagen, pausa, max_turnos
        )
        if nuevo is None or codigo == CODIGO_INFRA:
            divergencias.append({"turno": orig["n"], "motivo": "infraestructura o límite"})
            break
        parecido = difflib.SequenceMatcher(None, _texto_de(orig), _texto_de(nuevo)).ratio()
        if nuevo["respuesta"]["tipo"] != orig["respuesta"]["tipo"] or parecido < 0.85:
            divergencias.append({
                "turno": orig["n"], "entrada": entrada["contenido"],
                "tipo_original": orig["respuesta"]["tipo"],
                "tipo_nuevo": nuevo["respuesta"]["tipo"], "parecido": round(parecido, 2),
                "texto_original": _texto_de(orig)[:400], "texto_nuevo": _texto_de(nuevo)[:400],
            })
    resultado = {"origen": str(ruta_log), "run_replay": run, "divergencias": divergencias}
    registro.escribir_json(registro.dir_run(run) / "replay.json", resultado)
    print(f"Replay de {ruta_log.name}: {len(divergencias)} divergencias "
          f"en {len(originales)} turnos")
    for d in divergencias:
        print(f"  turno {d['turno']}: {d.get('tipo_original')} -> {d.get('tipo_nuevo')} "
              f"(parecido {d.get('parecido')})")
    print(f"Detalle en {registro.dir_run(run) / 'replay.json'}")
    return 0


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mensaje", nargs="?", help="lo que escribe el usuario (o por stdin)")
    parser.add_argument("--thread", help="sim-<escenario>__<n>")
    parser.add_argument("--run", default="manual", help="id de la corrida (default: manual)")
    parser.add_argument("--imagen", type=Path, help="foto que manda el usuario")
    parser.add_argument("--nuevo", action="store_true", help="reinicia la conversación")
    parser.add_argument("--cerrar", metavar="TEXTO", help="'objetivo logrado' o 'abandoné…'")
    parser.add_argument("--replay", type=Path, help="log .jsonl a reenviar")
    parser.add_argument("--pausa", type=float, default=2.0, help="throttle antes de cada turno")
    parser.add_argument("--max-turnos", type=int, default=registro.MAX_TURNOS)
    parser.add_argument("--interno", action="store_true", help="muestra tools y estados")
    parser.add_argument("--permitir-base-real", action="store_true")
    args = parser.parse_args()

    preparar_entorno(args.permitir_base_real)
    if args.replay:
        raise SystemExit(replay(args.replay, args.pausa, args.max_turnos))
    if not args.thread:
        parser.error("--thread es obligatorio")
    ruta = registro.ruta_log(args.run, args.thread)

    if args.nuevo:
        from fitosanitarios.config import get_settings
        from fitosanitarios.orquestador.agente import checkpointer_postgres

        with checkpointer_postgres(get_settings().database_url) as checkpointer:
            checkpointer.delete_thread(args.thread)
        for archivo in (ruta, registro.ruta_estado(args.run, args.thread)):
            archivo.unlink(missing_ok=True)
        print(f"Conversación {args.thread} reiniciada")
        if args.mensaje is None and not args.imagen:
            return

    if args.cerrar is not None:
        logrado = args.cerrar.strip().lower().startswith("objetivo logrado")
        registro.agregar(ruta, {"tipo_registro": "cierre", "resultado": args.cerrar,
                                "logrado": logrado})
        registro.marcar_progreso(
            args.run, registro.nombre_conversacion(args.thread),
            "hecha" if logrado or not args.cerrar.lower().startswith("infra") else "infra",
        )
        print("Cierre registrado")
        return

    texto = args.mensaje
    if texto is None and not sys.stdin.isatty() and not args.imagen:
        texto = sys.stdin.read().strip()
    if not texto:
        if args.imagen:
            texto = TEXTO_FOTO_POR_DEFECTO
        else:
            parser.error("falta el mensaje")
    reg, codigo = correr_turno(
        args.thread, args.run, texto, args.imagen, args.pausa, args.max_turnos
    )
    if reg is None:
        print(f"[LIMITE_DE_TURNOS] Ya se usaron los {args.max_turnos} turnos de esta "
              "conversación. Dejá el cierre con --cerrar.")
        raise SystemExit(codigo)
    if codigo == CODIGO_INFRA:
        print("[FALLA_DE_INFRAESTRUCTURA] El servicio no respondió (cuota o red). No es un "
              "error de la conversación: esperá unos segundos y reenviá el mismo mensaje una vez.")
        raise SystemExit(codigo)
    imprimir_lo_que_ve_el_usuario(reg, args.interno)


if __name__ == "__main__":
    main()
