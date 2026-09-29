import pytest

from fitosanitarios.tools.consultar_productos import (
    ConsultarProductosArgs,
    consultar_productos_logica,
)


def _unico_listado(resultado):
    assert len(resultado.datos["listados"]) == 1
    return resultado.datos["listados"][0]


def test_consulta_por_cultivo_real_devuelve_productos(conexion, modelo_embeddings):
    args = ConsultarProductosArgs(cultivo="Soja")
    resultado = consultar_productos_logica(args, conexion, modelo_embeddings)
    assert resultado.estado == "ok"
    listado = _unico_listado(resultado)
    assert listado["total"] > len(listado["productos"]) > 0


def test_consulta_por_cultivo_y_adversidad(conexion, modelo_embeddings):
    args = ConsultarProductosArgs(cultivo="Soja", adversidad="Chinche De La Alfalfa")
    resultado = consultar_productos_logica(args, conexion, modelo_embeddings)
    assert resultado.estado == "ok"
    assert _unico_listado(resultado)["total"] > 0


def test_consulta_con_banda_maxima_filtra_bandas_mas_peligrosas(conexion, modelo_embeddings):
    args = ConsultarProductosArgs(cultivo="Soja", banda_maxima="azul")
    resultado = consultar_productos_logica(args, conexion, modelo_embeddings)
    for p in _unico_listado(resultado)["productos"]:
        assert p["banda_toxicologica"] in ("III", "IV")


def test_sin_ningun_filtro_falla_la_validacion_de_args():
    with pytest.raises(ValueError):
        ConsultarProductosArgs()
    with pytest.raises(ValueError):
        ConsultarProductosArgs(localidad="El Trébol")  # sin distancia no filtra nada


def test_un_filtro_que_no_esta_en_el_registro_se_omite_y_se_avisa(conexion, modelo_embeddings):
    args = ConsultarProductosArgs(cultivo="Trigo", firma="Empresa Inexistente Xyz")
    resultado = consultar_productos_logica(args, conexion, modelo_embeddings)
    assert _unico_listado(resultado)["total"] > 0
    assert any("Empresa Inexistente Xyz" in a for a in resultado.advertencias)


def test_con_cultivo_avisa_que_solo_estan_los_productos_con_usos(conexion, modelo_embeddings):
    args = ConsultarProductosArgs(cultivo="Trigo", aptitud="fungicidas")
    resultado = consultar_productos_logica(args, conexion, modelo_embeddings)
    assert any("cultivos y plagas cargados" in a for a in resultado.advertencias)
    assert resultado.datos["filtros"]["aptitudes"] == ["Fungicida"]


def test_distancia_con_tipo_de_aplicacion_filtra_por_las_bandas_permitidas(
    conexion, modelo_embeddings
):
    """Caso real (28/09/2026): "¿qué fungicidas para trigo puedo aplicar con avión a 1500 m
    de El Trébol?" listaba productos de banda II, que a esa distancia no se pueden."""
    args = ConsultarProductosArgs(
        aptitud="fungicida", cultivo="trigo", tipo_aplicacion="avión", distancia_m=1500,
        localidad="El Trébol",
    )
    resultado = consultar_productos_logica(args, conexion, modelo_embeddings)
    listado = _unico_listado(resultado)
    assert listado["aplicaciones"] == ["aerea"]
    assert listado["permitidas"] == ["III", "IV"]
    assert {p["banda_toxicologica"] for p in listado["productos"]} <= {"III", "IV"}
    assert any(c.norma and "841" in c.norma for c in resultado.citas)


def test_distancia_sin_tipo_de_aplicacion_responde_para_cada_tipo(conexion, modelo_embeddings):
    args = ConsultarProductosArgs(
        aptitud="fungicida", cultivo="trigo", distancia_m=1500, localidad="El Trébol"
    )
    resultado = consultar_productos_logica(args, conexion, modelo_embeddings)
    por_tipo = {tuple(lst["aplicaciones"]): lst for lst in resultado.datos["listados"]}
    assert set(por_tipo) == {("aerea",), ("terrestre",)}
    assert por_tipo[("aerea",)]["permitidas"] == ["III", "IV"]
    assert por_tipo[("terrestre",)]["permitidas"] == ["Ia", "Ib", "II", "III", "IV"]


def test_distancia_sin_localidad_la_pregunta(conexion, modelo_embeddings):
    args = ConsultarProductosArgs(aptitud="fungicida", distancia_m=1500)
    resultado = consultar_productos_logica(args, conexion, modelo_embeddings)
    assert resultado.estado == "faltan_datos"


def test_un_cultivo_que_nadie_dijo_se_omite(conexion, modelo_embeddings):
    """Caso real (28/09/2026): "¿puedo aplicar metsulfuron en el trébol?" y Gemini pasaba
    `cultivo="trigo"`."""
    dicho = "puedo aplicar metsulfuron en el trebol?"
    args = ConsultarProductosArgs(principio_activo="metsulfuron", cultivo="trigo")
    resultado = consultar_productos_logica(args, conexion, modelo_embeddings, dicho)
    assert resultado.datos["filtros"]["cultivo"] is None
    assert resultado.datos["filtros"]["principio_activo"] == "metsulfuron"


def test_una_localidad_no_se_toma_como_cultivo(conexion, modelo_embeddings):
    dicho = "puedo aplicar metsulfuron en el trebol?"
    args = ConsultarProductosArgs(principio_activo="metsulfuron", cultivo="Trébol")
    resultado = consultar_productos_logica(args, conexion, modelo_embeddings, dicho)
    assert resultado.datos["filtros"]["cultivo"] is None


def test_un_cultivo_dicho_se_usa(conexion, modelo_embeddings):
    dicho = "que fungicidas hay para trigo"
    args = ConsultarProductosArgs(aptitud="fungicida", cultivo="trigo")
    resultado = consultar_productos_logica(args, conexion, modelo_embeddings, dicho)
    assert resultado.datos["filtros"]["cultivo"] == "trigo"
