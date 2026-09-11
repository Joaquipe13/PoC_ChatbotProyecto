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


def test_producto_sin_usos_registrados(conexion, modelo_embeddings):
    args = ValidarProductoRegistroArgs(producto_nombre="Glynomyl Dd", cultivo="Soja")
    resultado = validar_producto_registro_logica(args, conexion, modelo_embeddings, TOLERANCIA_PCT)
    assert resultado.estado == "no_resuelto"

    from fitosanitarios.dominio.motivos import MotivoNoResuelto

    assert resultado.motivo == MotivoNoResuelto.SIN_USOS_REGISTRADOS


def test_producto_no_encontrado(conexion, modelo_embeddings):
    args = ValidarProductoRegistroArgs(
        producto_nombre="Xyzzyproductoquenoexisteenelregistro123", cultivo="Soja"
    )
    resultado = validar_producto_registro_logica(args, conexion, modelo_embeddings, TOLERANCIA_PCT)
    assert resultado.estado == "no_resuelto"

    from fitosanitarios.dominio.motivos import MotivoNoResuelto

    assert resultado.motivo == MotivoNoResuelto.PRODUCTO_NO_ENCONTRADO
