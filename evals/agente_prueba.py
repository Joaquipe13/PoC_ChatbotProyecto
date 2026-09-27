"""Agente de prueba con Gemini: un usuario simulado que conversa con el bot siguiendo los
casos del plan de pruebas (`docs/plan_pruebas.md`, `evals/escenarios/*.yaml`).

Por cada caso, Gemini hace de operario: recibe solo la persona, el objetivo, los datos y
el comportamiento del escenario (no el código, ni el prompt del bot, ni lo esperado), lee
lo que contestó el bot y decide qué escribir, si mandar la foto de la receta o si
terminar. Cada turno entra por el mismo camino que WhatsApp (`evals/chat.py::correr_turno`:
agente real, checkpointer de Postgres, log por turno). Al terminar declara si logró el
objetivo. Después se corren los invariantes y las expectativas del escenario
(`evals/invariantes.py`) y se escribe un informe.

    uv run python -m evals.base_eval crear                # una vez: clon de la base
    uv run python -m evals.agente_prueba                  # todos los casos del plan
    uv run python -m evals.agente_prueba --casos dictamen_dosis_observada,banda_de_producto
    uv run python -m evals.agente_prueba --reps 2 --max-turnos 8

Sale a la red (Gemini para el bot y para el simulador): no corre con `pytest`. El
simulador usa las API keys en el orden inverso al del bot, para repartir la cuota. Un
turno que falla por cuota o red se reintenta una vez; si vuelve a fallar, la conversación
se cierra como `infra` (no cuenta como error del bot).
"""

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from evals import chat, registro
from evals import escenarios as cat

RAIZ_REPO = registro.RAIZ.parent
CONJUNTO_PLAN = "plan"
ESPERA_INFRA_S = 20.0

PROMPT_SIMULADOR = """\
Sos una persona que le escribe por WhatsApp a un asistente de recetas de fitosanitarios.
Actuás SOLO como el usuario que se describe abajo: con su forma de escribir, lo que sabe y
lo que quiere. No sabés cómo está hecho el asistente ni qué va a contestar. No inventes
datos que tu persona no tiene; si te preguntan algo que no sabés, decilo. No expliques lo
que hacés ni hables del asistente como un sistema: solo escribís tus mensajes.

En cada turno respondé ÚNICAMENTE un JSON (sin texto alrededor, sin markdown):
{"accion": "escribir" | "foto" | "terminar", "mensaje": "...", "resultado": "..."}

- "escribir": mandás "mensaje" (un mensaje corto de WhatsApp).
- "foto": mandás la foto de tu receta (solo si tus datos tienen una "imagen"); "mensaje"
  es el texto que la acompaña, o vacío.
- "terminar": cuando ya lograste tu objetivo, o cuando te trabaste y no vas a lograrlo.
  "resultado" empieza con "objetivo logrado" o con "abandoné:" y el motivo, en una frase.

Si el asistente te ofrece botones u opciones, podés contestar con el texto de una de ellas.
No termines antes de intentar todo lo que dice tu objetivo."""


@dataclass
class Decision:
    accion: str
    mensaje: str = ""
    resultado: str = ""


def interpretar(respuesta: str) -> Decision | None:
    """El JSON del simulador, o `None` si no se entiende."""
    texto = respuesta.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    try:
        datos = json.loads(texto.strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(datos, dict) or datos.get("accion") not in ("escribir", "foto", "terminar"):
        return None
    return Decision(
        accion=datos["accion"], mensaje=str(datos.get("mensaje") or "").strip(),
        resultado=str(datos.get("resultado") or "").strip(),
    )


def lo_que_vio_el_usuario(reg: dict) -> str:
    """Los mensajes del bot como los vería en WhatsApp: texto, botones o lista."""
    partes = []
    for m in reg["mensajes"]:
        texto = m["texto"]
        if m["envio"] == "botones":
            texto += "\n[BOTONES: " + " | ".join(m["opciones"]) + "]"
        elif m["envio"] == "lista":
            texto += "\n[LISTA: " + " | ".join(m["opciones"]) + "]"
        partes.append(texto)
    return "\n\n".join(partes)


def pedido_al_simulador(escenario: dict, historial: list[tuple[str, str]]) -> str:
    ficha = yaml.safe_dump(
        cat.para_el_simulador(escenario), allow_unicode=True, sort_keys=False, width=100
    )
    conversacion = "\n\n".join(
        f"{'VOS' if quien == 'usuario' else 'ASISTENTE'}:\n{texto}" for quien, texto in historial
    ) or "(todavía no escribiste nada)"
    return (
        f"Quién sos y qué querés:\n{ficha}\n"
        f"Conversación hasta ahora:\n{conversacion}\n\n"
        "¿Qué hacés ahora? Respondé solo el JSON."
    )


def decidir(cliente, escenario: dict, historial: list[tuple[str, str]]) -> Decision:
    """Le pide al simulador el próximo paso; si dos veces no devuelve un JSON válido, se
    termina la conversación (no es un error del bot)."""
    pedido = pedido_al_simulador(escenario, historial)
    for _ in range(2):
        decision = interpretar(cliente.generar(pedido, system=PROMPT_SIMULADOR))
        if decision is not None:
            return decision
    return Decision("terminar", resultado="abandoné: el simulador no devolvió una acción válida")


def ruta_imagen(escenario: dict) -> Path | None:
    imagen = (escenario.get("datos") or {}).get("imagen")
    return RAIZ_REPO / imagen if imagen else None


def reiniciar_thread(thread: str) -> None:
    """La base de evaluación guarda la conversación, la agenda y los eventos entre
    corridas: un caso repetido arrancaría con el historial viejo y, al agendar, avisaba un
    choque con cada aplicación agendada en las corridas anteriores."""
    import psycopg

    from fitosanitarios.config import get_settings
    from fitosanitarios.orquestador.agente import checkpointer_postgres

    url = get_settings().database_url
    with checkpointer_postgres(url) as checkpointer:
        checkpointer.delete_thread(thread)
    with psycopg.connect(url) as conn:
        conn.execute("DELETE FROM operacion.evento_aplicacion WHERE thread_id = %s", (thread,))
        conn.execute("DELETE FROM operacion.receta WHERE thread_id = %s", (thread,))


def conversar(
    escenario: dict, run: str, n: int, cliente, pausa: float, max_turnos: int,
    turno=chat.correr_turno,
) -> dict:
    """Una conversación completa. Devuelve el registro de cierre."""
    conversacion = f"{escenario['id']}__{n}"
    thread = f"sim-{conversacion}"
    ruta = registro.ruta_log(run, thread)
    historial: list[tuple[str, str]] = []
    cierre = {"tipo_registro": "cierre", "resultado": "abandoné: límite de turnos",
              "logrado": False}
    turnos = 0
    while turnos < max_turnos:
        decision = decidir(cliente, escenario, historial)
        if decision.accion == "terminar":
            resultado = decision.resultado or "abandoné: sin motivo"
            cierre = {"tipo_registro": "cierre", "resultado": resultado,
                      "logrado": resultado.lower().startswith("objetivo logrado")}
            break
        imagen = ruta_imagen(escenario) if decision.accion == "foto" else None
        texto = decision.mensaje or (chat.TEXTO_FOTO_POR_DEFECTO if imagen else "hola")
        reg, codigo = turno(thread, run, texto, imagen, pausa, max_turnos)
        if codigo == chat.CODIGO_INFRA:
            time.sleep(ESPERA_INFRA_S)
            reg, codigo = turno(thread, run, texto, imagen, pausa, max_turnos)
        if reg is None:
            break
        if codigo == chat.CODIGO_INFRA:
            cierre = {"tipo_registro": "cierre", "resultado": "infra: cuota o red",
                      "logrado": False}
            break
        turnos += 1
        nota_foto = "\n[mandaste la foto de la receta]" if imagen else ""
        historial.append(("usuario", texto + nota_foto))
        historial.append(("asistente", lo_que_vio_el_usuario(reg)))
    cierre["simulador"] = "gemini"
    registro.agregar(ruta, cierre)
    estado = "infra" if cierre["resultado"].startswith("infra") else "hecha"
    registro.marcar_progreso(run, conversacion, estado)
    return cierre


def informe(run: str) -> Path:
    """Un resumen por caso: qué declaró el simulador, cuántos turnos, qué tools se usaron y
    qué invariantes o expectativas fallaron. Lo lee una persona."""
    directorio = registro.dir_run(run)
    invariantes = registro.leer_json(directorio / "invariantes.json", {"conversaciones": {}})
    lineas = [f"# Plan de pruebas — corrida {run}", ""]
    filas = []
    for ruta in sorted(directorio.glob("*.jsonl")):
        registros = registro.leer_registros(ruta)
        turnos = [r for r in registros if r["tipo_registro"] == "turno"]
        cierre = next((r for r in registros if r["tipo_registro"] == "cierre"), {})
        violaciones = invariantes["conversaciones"].get(ruta.stem, [])
        tools = sorted({t["nombre"] for r in turnos for t in r["tool_calls"]})
        ok = cierre.get("logrado") and not violaciones
        filas.append((ruta.stem, ok, cierre, turnos, tools, violaciones))
    aprobadas = sum(1 for _, ok, *_ in filas if ok)
    lineas += [f"**{aprobadas} de {len(filas)} casos sin fallas** (objetivo logrado según el "
               "simulador y ninguna expectativa ni invariante incumplidos).", ""]
    lineas += ["| Caso | Resultado | Turnos | Tools | Fallas |", "|---|---|---|---|---|"]
    for nombre, ok, cierre, turnos, tools, violaciones in filas:
        estado = "✅" if ok else ("⚙️ infra" if str(cierre.get("resultado", "")).startswith("infra")
                                   else "❌")
        lineas.append(f"| {nombre} | {estado} | {len(turnos)} | {', '.join(tools)} | "
                      f"{len(violaciones)} |")
    lineas.append("")
    for nombre, _ok, cierre, turnos, _tools, violaciones in filas:
        lineas += [f"## {nombre}", "", f"- Simulador: {cierre.get('resultado', 'sin cierre')}"]
        for v in violaciones:
            lineas.append(f"- **{v['invariante']}** ({v['severidad']}, turno {v['turno']}): "
                          f"{v['detalle']}")
        lineas += ["", "<details><summary>Conversación</summary>", ""]
        for t in turnos:
            entrada = t["entrada"]
            foto = " 📷" if entrada["tipo"] == "imagen" else ""
            lineas.append(f"**Usuario{foto}:** {entrada['contenido']}")
            lineas.append("")
            lineas.append("**Bot:** " + lo_que_vio_el_usuario(t).replace("\n", "  \n"))
            lineas.append("")
        lineas += ["</details>", ""]
    ruta = directorio / "informe_plan.md"
    ruta.write_text("\n".join(lineas), encoding="utf-8")
    return ruta


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--casos", default=CONJUNTO_PLAN,
                        help=f"ids separados por coma, o un conjunto ('{CONJUNTO_PLAN}', "
                             "'desarrollo')")
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument("--pausa", type=float, default=2.0)
    parser.add_argument("--max-turnos", type=int, default=10)
    args = parser.parse_args()

    chat.preparar_entorno(permitir_base_real=False)
    from evals import corrida
    from fitosanitarios.config import get_settings
    from fitosanitarios.llm.client import ClienteGemini

    ids = cat.ids(args.casos) if "," not in args.casos and cat.ids(args.casos) else (
        args.casos.split(",")
    )
    settings = get_settings()
    cliente = ClienteGemini(list(reversed(settings.gemini_api_keys)), settings.gemini_model)
    run = corrida.iniciar(ids, args.reps)
    meta_ruta = registro.dir_run(run) / "meta.json"
    meta = registro.leer_json(meta_ruta, {})
    meta["simulador"] = "Gemini (evals/agente_prueba.py)"
    registro.escribir_json(meta_ruta, meta)
    print(f"Corrida {run}: {len(ids)} casos x {args.reps}")

    for conversacion in corrida.pendientes(run):
        escenario_id, n = conversacion.rsplit("__", 1)
        escenario = cat.cargar(escenario_id)
        reiniciar_thread(f"sim-{conversacion}")
        inicio = datetime.now()
        cierre = conversar(escenario, run, int(n), cliente, args.pausa, args.max_turnos)
        segundos = (datetime.now() - inicio).seconds
        print(f"  {conversacion}: {cierre['resultado']} ({segundos} s)")
        registro.anotar_bitacora(run, f"{conversacion}: {cierre['resultado']}")

    corrida.analizar(run)
    print(f"Informe: {informe(run)}")


if __name__ == "__main__":
    main()
