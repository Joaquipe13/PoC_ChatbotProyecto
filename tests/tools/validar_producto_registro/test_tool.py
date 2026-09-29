from fitosanitarios.tools.validar_producto_registro import (
    ValidarProductoRegistroArgs,
    validar_producto_registro_logica,
)

TOLERANCIA_PCT = 10.0


def test_producto_real_con_cultivo_autorizado(conexion, modelo_embeddings):
    args = ValidarProductoRegistroArgs(producto_nombre="Flyer 10 Ec", cultivo="Soja")
    resultado = validar_producto_registro_logica(args, conexion, modelo_embeddings, TOLERANCIA_PCT)
    assert resultado.estado == "ok"
    assert resultado.datos["cultivo_autorizado"] is True
    assert resultado.datos["banda_toxicologica"] == "II"
    assert resultado.citas[0].registro_senasa == "41881"


def test_producto_real_con_cultivo_no_autorizado(conexion, modelo_embeddings):
    args = ValidarProductoRegistroArgs(
        producto_nombre="Flyer 10 Ec", cultivo="Un cultivo que no está registrado zzz"
    )
    resultado = validar_producto_registro_logica(args, conexion, modelo_embeddings, TOLERANCIA_PCT)
    assert resultado.estado == "observado"
    assert resultado.datos["cultivo_autorizado"] is False
    assert len(resultado.advertencias) == 1


def test_producto_sin_usos_registrados_dice_lo_que_sabe_y_que_no_verifica(
    conexion, modelo_embeddings
):
    """Caso real (28/09/2026): "¿es correcta la dosis para Manto?" terminaba en "No pude
    completar la consulta" con el motivo en jerga, sin decir que el producto está
    registrado ni su banda."""
    args = ValidarProductoRegistroArgs(
        producto_nombre="Manto", cultivo="MAIZ", dosis_valor=60, dosis_unidad="cc/ha"
    )
    resultado = validar_producto_registro_logica(args, conexion, modelo_embeddings, TOLERANCIA_PCT)
    assert resultado.estado == "ok"
    assert resultado.datos["numero_inscripcion"] == "38008"
    assert resultado.datos["sin_usos_registrados"] is True
    assert resultado.datos["marbete"] is None  # sin cliente LLM no se busca en el marbete
    assert "60 cc/ha" in resultado.chequeos_no_realizados[0]


def test_producto_no_encontrado(conexion, modelo_embeddings):
    args = ValidarProductoRegistroArgs(
        producto_nombre="Xyzzyproductoquenoexisteenelregistro123", cultivo="Soja"
    )
    resultado = validar_producto_registro_logica(args, conexion, modelo_embeddings, TOLERANCIA_PCT)
    assert resultado.estado == "no_resuelto"

    from fitosanitarios.dominio.motivos import MotivoNoResuelto

    assert resultado.motivo == MotivoNoResuelto.PRODUCTO_NO_ENCONTRADO


def test_sin_cultivo_informa_registro_y_banda(conexion, modelo_embeddings):
    """"¿Qué banda tiene el Flyer?": sin cultivo no se chequea autorización, pero la banda
    se informa (antes el cultivo era obligatorio y Gemini mandaba la pregunta al marbete)."""
    args = ValidarProductoRegistroArgs(producto_nombre="Flyer 10 Ec")
    resultado = validar_producto_registro_logica(args, conexion, modelo_embeddings, TOLERANCIA_PCT)
    assert resultado.estado == "ok"
    assert resultado.datos["banda_toxicologica"] == "II"
    assert resultado.datos["cultivo_autorizado"] is None
    assert resultado.advertencias == []


def test_sin_cultivo_informa_la_banda_aunque_no_tenga_usos(conexion, modelo_embeddings):
    args = ValidarProductoRegistroArgs(producto_nombre="Glynomyl Dd")
    resultado = validar_producto_registro_logica(args, conexion, modelo_embeddings, TOLERANCIA_PCT)
    assert resultado.estado == "ok"
    assert "banda_toxicologica" in resultado.datos
