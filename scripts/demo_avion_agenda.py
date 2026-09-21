"""Test end-to-end (sesión post-Fase 11, "RAG de equipos" -- ver
DECISIONES.md): carga una receta real por imagen, agenda la aplicación con
un avión resuelto por RAG (sin decir el nombre exacto del catálogo) y
consulta la agenda para confirmar que aparece.

Usa Gemini real, embeddings reales y Postgres real -- nada de fixtures ni
LLM fake. Requiere:

    docker compose up -d db
    (con USE_FIXTURES en el estado que sea: este script no pasa por
    leer_receta/responder_consulta_normativa vía el LLM fake, llama
    leer_receta_logica directo con un ClienteGemini real)

Uso: uv run python scripts/demo_avion_agenda.py

Nota (ver DIFICULTADES.md): la conversación real por WhatsApp/canal web
todavía no tiene un camino para que una receta leída por foto quede
guardada en `operacion.receta` con `fecha_prevista` (`guardar_receta_en_curso`
no está conectada al flujo del orquestador). Este script llama
`guardar_receta_en_curso` directamente para simular ese paso -- el resto
(resolver_vehiculo vía RAG, registrar_evento, consultar_agenda) sí corre
tal cual lo haría el agente real, contra la lógica real de las tools.
"""

import uuid
from datetime import date
from pathlib import Path

import psycopg

from fitosanitarios.config import get_settings
from fitosanitarios.llm.client import ClienteGemini
from fitosanitarios.orquestador.estado import guardar_receta_en_curso
from fitosanitarios.servicios.recursos import con_conexion, con_conexion_y_modelo
from fitosanitarios.tools.consultar_agenda import ConsultarAgendaArgs, consultar_agenda_tool_logica
from fitosanitarios.tools.leer_receta import leer_receta_logica
from fitosanitarios.tools.registrar_evento import RegistrarEventoArgs, registrar_evento_logica

RECETA_IMAGEN = Path("data/recetas_ejemplo/01_apta_terrestre.jpg")
DESCRIPCION_AVION = "la avioneta grande turbohelice"  # no es un sinónimo cargado a propósito


def separador(titulo: str) -> None:
    print(f"\n{'=' * 10} {titulo} {'=' * 10}")


def main() -> None:
    settings = get_settings()
    keys = [k for k in [settings.gemini_api_key_1, settings.gemini_api_key_2] if k]
    cliente_llm = ClienteGemini(keys, settings.gemini_model)
    thread_id = f"demo-avion-{uuid.uuid4().hex[:8]}"
    print(f"thread_id de prueba: {thread_id}")

    separador("1. Cargar receta (leer_receta, imagen real, Gemini real)")
    if not RECETA_IMAGEN.exists():
        raise SystemExit(
            f"No está {RECETA_IMAGEN}. Corré primero: "
            "uv run python scripts/generar_recetas_ejemplo_el_trebol.py"
        )
    imagen = RECETA_IMAGEN.read_bytes()
    resultado_lectura = leer_receta_logica(imagen, cliente_llm)
    print("estado:", resultado_lectura.estado)
    if resultado_lectura.estado != "ok":
        raise SystemExit("leer_receta no devolvió 'ok', no se puede continuar la demo")
    datos = resultado_lectura.datos
    print(f"cultivo={datos['cultivo']!r} lote={datos['lote']!r} "
          f"producto={datos['items'][0]['producto_nombre']!r}")

    separador("2. Guardar la receta en curso con fecha_prevista = hoy")
    with psycopg.connect(settings.database_url) as conn:
        receta_id = guardar_receta_en_curso(
            conn,
            thread_id,
            {
                "numero": datos["numero"],
                "cultivo": datos["cultivo"],
                "lote": datos["lote"],
                "adversidad": datos["adversidad"],
                "superficie_ha": datos["superficie_ha"],
                "tipo_aplicacion": datos["tipo_aplicacion"],
                "fecha_prevista": date.today(),
            },
            estado="confirmada",
        )
    print(f"receta_id={receta_id}, fecha_prevista={date.today().isoformat()}")

    separador("3. Agendar la aplicación con un avión (resolver_vehiculo vía RAG)")
    print(f"descripción tal cual la escribiría el operario: {DESCRIPCION_AVION!r}")
    args_evento = RegistrarEventoArgs(
        accion="iniciar", vehiculo=DESCRIPCION_AVION, lote=datos["lote"], receta_id=receta_id
    )
    resultado_evento = con_conexion_y_modelo(
        lambda conn, modelo: registrar_evento_logica(args_evento, conn, modelo, thread_id)
    )
    print("estado:", resultado_evento.estado)
    print("datos:", resultado_evento.datos)
    if resultado_evento.estado != "ok":
        raise SystemExit("registrar_evento no devolvió 'ok'")
    print(f"-> el RAG de equipos resolvió {DESCRIPCION_AVION!r} como "
          f"{resultado_evento.datos['vehiculo']!r} sin que se haya dicho el nombre exacto")

    separador("4. Consultar la agenda de hoy")
    resultado_agenda = con_conexion(
        lambda conn: consultar_agenda_tool_logica(ConsultarAgendaArgs(fecha=None), conn, thread_id)
    )
    print("tareas de hoy:")
    for tarea in resultado_agenda.datos["tareas"]:
        print(f"  - receta {tarea['numero']} ({tarea['cultivo']}, lote {tarea['lote']}): "
              f"{tarea['estado_tarea']}")
    tareas_en_curso = [t for t in resultado_agenda.datos["tareas"] if t["receta_id"] == receta_id]
    assert tareas_en_curso, "la receta cargada no aparece en la agenda de hoy"
    assert tareas_en_curso[0]["estado_tarea"] == "en_curso"
    print("\nOK: la receta cargada aparece en la agenda de hoy con estado 'en_curso'.")

    separador("5. Finalizar la aplicación y volver a consultar la agenda")
    resultado_fin = con_conexion_y_modelo(
        lambda conn, modelo: registrar_evento_logica(
            RegistrarEventoArgs(accion="finalizar"), conn, modelo, thread_id
        )
    )
    print("estado finalizar:", resultado_fin.estado)
    resultado_agenda_2 = con_conexion(
        lambda conn: consultar_agenda_tool_logica(ConsultarAgendaArgs(fecha=None), conn, thread_id)
    )
    tarea_final = next(
        t for t in resultado_agenda_2.datos["tareas"] if t["receta_id"] == receta_id
    )
    print("estado de la tarea después de finalizar:", tarea_final["estado_tarea"])
    assert tarea_final["estado_tarea"] == "finalizada"
    print("\nOK: la agenda refleja 'finalizada' después de registrar el fin de la aplicación.")


if __name__ == "__main__":
    main()
