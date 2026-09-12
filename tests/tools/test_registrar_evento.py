"""`thread_id` único por test (`uuid4`): filas reales sin rollback, ver
DIFICULTADES.md (Fase 8) para el mismo hallazgo con otra tabla."""

import uuid

from fitosanitarios.dominio.motivos import MotivoNoResuelto
from fitosanitarios.tools.registrar_evento import RegistrarEventoArgs, registrar_evento_logica


def _thread() -> str:
    return f"t-tool-evento-{uuid.uuid4()}"


def test_iniciar_completo(conexion):
    args = RegistrarEventoArgs(accion="iniciar", vehiculo="dron", lote="4")
    resultado = registrar_evento_logica(args, conexion, _thread())
    assert resultado.estado == "ok"
    assert resultado.datos["vehiculo"] == "dron"
    assert resultado.datos["lote"] == "4"


def test_iniciar_sin_lote_repregunta(conexion):
    args = RegistrarEventoArgs(accion="iniciar", vehiculo="dron", lote=None)
    resultado = registrar_evento_logica(args, conexion, _thread())
    assert resultado.estado == "faltan_datos"
    assert any(f.campo == "lote" for f in resultado.faltantes)


def test_finalizar_sin_evento_en_curso(conexion):
    resultado = registrar_evento_logica(
        RegistrarEventoArgs(accion="finalizar"), conexion, _thread()
    )
    assert resultado.estado == "no_resuelto"
    assert resultado.motivo == MotivoNoResuelto.SIN_EVENTO_EN_CURSO


def test_iniciar_y_finalizar_en_el_mismo_thread(conexion):
    thread_id = _thread()
    registrar_evento_logica(
        RegistrarEventoArgs(accion="iniciar", vehiculo="mochila", lote="1"), conexion, thread_id
    )
    resultado = registrar_evento_logica(
        RegistrarEventoArgs(accion="finalizar"), conexion, thread_id
    )
    assert resultado.estado == "ok"
    assert resultado.datos["fecha_fin"] is not None


def test_iniciar_dos_veces_da_observado(conexion):
    thread_id = _thread()
    args = RegistrarEventoArgs(accion="iniciar", vehiculo="mochila", lote="1")
    registrar_evento_logica(args, conexion, thread_id)
    resultado = registrar_evento_logica(args, conexion, thread_id)
    assert resultado.estado == "observado"
    assert resultado.advertencias
