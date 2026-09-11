import pytest

from fitosanitarios.tools.consultar_productos import (
    ConsultarProductosArgs,
    consultar_productos_logica,
)


def test_consulta_por_cultivo_real_devuelve_productos(conexion, modelo_embeddings):
    args = ConsultarProductosArgs(cultivo="Soja")
    resultado = consultar_productos_logica(args, conexion, modelo_embeddings)
    assert resultado.estado == "ok"
    assert resultado.datos["total"] > 0
    assert any(p["marca"] == "Flyer 10 Ec" for p in resultado.datos["productos"])


def test_consulta_por_cultivo_y_adversidad(conexion, modelo_embeddings):
    args = ConsultarProductosArgs(cultivo="Soja", adversidad="Chinche De La Alfalfa")
    resultado = consultar_productos_logica(args, conexion, modelo_embeddings)
    assert resultado.estado == "ok"
    assert resultado.datos["total"] > 0


def test_consulta_con_banda_maxima_filtra_bandas_mas_peligrosas(conexion, modelo_embeddings):
    args = ConsultarProductosArgs(cultivo="Soja", banda_maxima="III")
    resultado = consultar_productos_logica(args, conexion, modelo_embeddings)
    for p in resultado.datos["productos"]:
        assert p["banda_toxicologica"] in ("Ia", "Ib", "II", "III", None)


def test_sin_ningun_filtro_falla_la_validacion_de_args():
    with pytest.raises(ValueError):
        ConsultarProductosArgs()


def test_cultivo_no_reconocido_pide_repregunta(conexion, modelo_embeddings):
    args = ConsultarProductosArgs(cultivo="zzzznocultivoinventadoxyz")
    resultado = consultar_productos_logica(args, conexion, modelo_embeddings)
    assert resultado.estado == "faltan_datos"
    assert resultado.faltantes[0].campo == "cultivo"
