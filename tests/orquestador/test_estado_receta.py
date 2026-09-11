"""Test de integración de la persistencia de receta en curso contra
Postgres real (Docker)."""

from fitosanitarios.orquestador.estado import (
    cancelar_receta_en_curso,
    guardar_receta_en_curso,
    obtener_receta_en_curso,
    registrar_turno,
)


def test_guardar_y_obtener_receta_en_curso(conexion):
    thread_id = "test-thread-549341XXXXXXX"
    guardar_receta_en_curso(conexion, thread_id, {"cultivo": "soja", "lote": "4"})

    receta = obtener_receta_en_curso(conexion, thread_id)

    assert receta is not None
    assert receta["cultivo"] == "soja"
    assert receta["lote"] == "4"
    assert receta["estado"] == "borrador"


def test_guardar_dos_veces_actualiza_la_misma_receta(conexion):
    thread_id = "test-thread-actualiza"
    id_1 = guardar_receta_en_curso(conexion, thread_id, {"cultivo": "soja"})
    id_2 = guardar_receta_en_curso(conexion, thread_id, {"lote": "7"})

    assert id_1 == id_2
    receta = obtener_receta_en_curso(conexion, thread_id)
    assert receta["cultivo"] == "soja"  # no se pisó con None
    assert receta["lote"] == "7"


def test_thread_sin_receta_devuelve_none(conexion):
    assert obtener_receta_en_curso(conexion, "thread-sin-recetas-jamas-usado") is None


def test_cancelar_receta_en_curso(conexion):
    thread_id = "test-thread-cancelar"
    guardar_receta_en_curso(conexion, thread_id, {"cultivo": "maiz"})
    cancelar_receta_en_curso(conexion, thread_id)

    assert obtener_receta_en_curso(conexion, thread_id) is None


def test_guardar_receta_confirmada(conexion):
    thread_id = "test-thread-confirmada"
    guardar_receta_en_curso(conexion, thread_id, {"cultivo": "trigo"}, estado="confirmada")

    receta = obtener_receta_en_curso(conexion, thread_id)
    assert receta["estado"] == "confirmada"


def test_registrar_turno_guarda_una_fila(conexion):
    thread_id = "test-thread-log"
    registrar_turno(
        conexion, thread_id, "quiero evaluar mi receta",
        [{"name": "validar_producto_registro", "args": {"producto_nombre": "X"}}],
        "consulta_producto",
    )

    with conexion.cursor() as cur:
        cur.execute(
            "SELECT entrada, tool_calls, salida FROM operacion.turno "
            "WHERE thread_id = %s ORDER BY creado_en DESC LIMIT 1",
            (thread_id,),
        )
        entrada, tool_calls, salida = cur.fetchone()

    assert entrada["texto"] == "quiero evaluar mi receta"
    assert tool_calls[0]["nombre"] == "validar_producto_registro"
    assert salida["tipo"] == "consulta_producto"


def test_registrar_turno_nunca_loguea_imagenes(conexion):
    thread_id = "test-thread-log-imagen"
    registrar_turno(
        conexion, thread_id, "foto de receta",
        [{"name": "leer_receta", "args": {"imagen_base64": "AAAA" * 1000}}],
        "confirmacion_receta",
    )

    with conexion.cursor() as cur:
        cur.execute(
            "SELECT tool_calls FROM operacion.turno WHERE thread_id = %s "
            "ORDER BY creado_en DESC LIMIT 1",
            (thread_id,),
        )
        (tool_calls,) = cur.fetchone()

    assert tool_calls[0]["args"]["imagen_base64"] == "<omitido>"
