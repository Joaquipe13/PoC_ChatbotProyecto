"""`listar_limitaciones` sin base: los accesos a datos se reemplazan por dobles."""

import pytest

from fitosanitarios.dominio.motivos import MotivoNoResuelto
from fitosanitarios.servicios.localidad import Ubicacion
from fitosanitarios.servicios.reglas import ReglaCandidata
from fitosanitarios.tools.listar_limitaciones import (
    ListarLimitacionesArgs,
    listar_limitaciones_logica,
)
from fitosanitarios.tools.listar_limitaciones import tool as modulo


def _r(zona, aplicacion, bandas, distancia, norma, articulo, permitido=False, condiciones=None,
       jurisdiccion="santa-fe", fuente="csv", observaciones=None):
    return ReglaCandidata(
        tipo_zona=zona, tipo_aplicacion=aplicacion, bandas=bandas, distancia_min_m=distancia,
        norma=norma, articulo=articulo, jurisdiccion_id=jurisdiccion, permitido=permitido,
        condiciones=condiciones, fuente=fuente, observaciones=observaciones,
    )


PROHIBICIONES = [
    _r("zona_urbana", "aerea", ["Ia", "Ib", "II"], 3000, "ley-11273-1995", "33"),
    _r("zona_urbana", "aerea", ["III", "IV"], 500, "ley-11273-1995", "33"),
    _r("zona_urbana", "terrestre", ["Ia", "Ib", "II"], 500, "ley-11273-1995", "34"),
    _r("zona_urbana", "aerea", ["todas"], 500, "ordenanza-841-2010", "6", jurisdiccion="el-trebol"),
]
CONDICIONALES = [
    _r("zona_urbana", "aerea", ["II"], 500, "ley-055297-2017", "51", True, "ordenanza + terreno"),
]
EL_TREBOL = Ubicacion(
    nombre="El Trébol", provincia_id=10, localidad_id=1, jurisdiccion_id="el-trebol",
    con_normativa_municipal=True,
)


@pytest.fixture
def base(monkeypatch):
    estado = {
        "ubicacion": EL_TREBOL, "prohibiciones": PROHIBICIONES, "condicionales": CONDICIONALES,
    }

    def reglas(conn, localidad_id, provincia_id, permitido=False):
        return estado["condicionales"] if permitido else estado["prohibiciones"]

    monkeypatch.setattr(modulo, "reglas_candidatas", reglas)
    monkeypatch.setattr(
        modulo, "resolver_ubicacion_o_cortar", lambda c, t, p=None: (estado["ubicacion"], None)
    )
    return estado


def _listar(**kwargs):
    return listar_limitaciones_logica(ListarLimitacionesArgs(localidad="El Trébol", **kwargs), None)


def test_lista_todas_las_prohibiciones_y_las_condicionales_con_sus_citas(base):
    r = _listar()
    assert r.estado == "ok" and r.datos["localidad"] == "El Trébol"
    assert len(r.datos["prohibiciones"]) == 4 and len(r.datos["condicionales"]) == 1
    assert r.datos["condicionales"][0]["condiciones"] == "ordenanza + terreno"
    assert {(c.norma, c.articulo) for c in r.citas} == {
        ("ley-11273-1995", "33"), ("ley-11273-1995", "34"), ("ordenanza-841-2010", "6"),
        ("ley-055297-2017", "51"),
    }


def test_filtra_por_aplicacion_banda_y_zona(base):
    r = _listar(tipo_aplicacion="terrestre")
    assert [x["articulo"] for x in r.datos["prohibiciones"]] == ["34"]
    assert r.datos["condicionales"] == []

    r = _listar(banda="azul")  # banda III
    assert [x["articulo"] for x in r.datos["prohibiciones"]] == ["33", "6"]
    assert r.datos["filtros"] == {"tipo_aplicacion": None, "bandas": ["III"], "tipo_zona": None}


def test_con_distancia_dice_que_esta_prohibido_y_que_excepciones_hay(base):
    r = _listar(distancia_m=1000, tipo_aplicacion="aerea", banda="II")
    (restriccion,) = r.datos["restricciones"]
    assert restriccion["prohibicion"]["distancia_min_m"] == 3000
    assert [e["articulo"] for e in restriccion["excepciones"]] == ["51"]
    assert {(c.norma, c.articulo) for c in r.citas} == {
        ("ley-11273-1995", "33"), ("ley-055297-2017", "51"),
    }


def test_con_distancia_que_no_alcanza_ninguna_prohibicion(base):
    r = _listar(distancia_m=5000)
    assert r.estado == "ok" and r.datos["restricciones"] == [] and r.citas == []


def test_localidad_sin_ordenanzas_lo_aclara(base):
    base["ubicacion"] = Ubicacion(nombre="Rosario", provincia_id=10, con_normativa_municipal=False)
    r = _listar()
    assert r.advertencias[0].startswith("No se cuenta con la normativa municipal de Rosario")


def test_filtros_que_no_se_entienden_se_ignoran_y_se_avisa(base):
    r = _listar(tipo_aplicacion="por el aire y por tierra", banda="la peligrosa")
    assert r.estado == "ok" and len(r.datos["prohibiciones"]) == 4
    assert any("tipo de aplicación" in a for a in r.advertencias)
    assert any("banda" in a for a in r.advertencias)


def test_sin_reglas_para_lo_que_se_pregunto_no_resuelve(base):
    r = _listar(tipo_zona="escuelas")
    assert r.estado == "no_resuelto" and r.motivo == MotivoNoResuelto.SIN_REGLA_APLICABLE


def test_marca_las_reglas_leidas_del_pdf(base):
    base["prohibiciones"] = [_r("zona_urbana", "aerea", ["todas"], 500, "ley-1-2000", "3",
                                fuente="pdf_extraido")]
    r = _listar()
    assert r.datos["prohibiciones"][0]["extraida_de_pdf"] is True


def test_sin_localidad_corta_con_la_pregunta_de_la_localidad(base, monkeypatch):
    from fitosanitarios.dominio.modelos import ResultadoTool

    pedir = ResultadoTool(estado="faltan_datos")
    monkeypatch.setattr(modulo, "resolver_ubicacion_o_cortar", lambda c, t, p=None: (None, pedir))
    assert listar_limitaciones_logica(ListarLimitacionesArgs(), None) is pedir


# --- con un producto: la banda sale del registro ---


def _producto(id_, marca, banda, registro="30000"):
    from fitosanitarios.datos.retrievers.catalogo import CandidatoProducto

    return CandidatoProducto(
        id=id_, numero_inscripcion=registro, marca=marca, banda_toxicologica=banda,
        estado_producto="Activo", score=0.9,
    )


def _con_catalogo(monkeypatch, productos):
    monkeypatch.setattr(modulo, "buscar_productos_por_nombre", lambda c, n, m: productos)


def test_con_un_producto_filtra_por_su_banda_y_lo_cita(base, monkeypatch):
    """"Tengo Tordon D 30, ¿a cuánto del pueblo lo puedo tirar?": antes se ignoraba el
    producto y se listaban todas las bandas."""
    _con_catalogo(monkeypatch, [_producto(1, "Tordon D 30", "III", "30735")])
    r = _listar(producto="Tordon D 30")
    assert r.estado == "ok"
    assert r.datos["filtros"]["bandas"] == ["III"]
    assert r.datos["producto"]["marca"] == "Tordon D 30"
    bandas = [b for p in r.datos["prohibiciones"] for b in p["bandas"]]
    assert "Ia" not in bandas and "II" not in bandas
    assert r.citas[0].registro_senasa == "30735"


def test_la_banda_que_dijo_el_operario_manda_sobre_el_producto(base, monkeypatch):
    def no_se_busca(*_):
        raise AssertionError("con la banda dicha no hace falta buscar el producto")

    monkeypatch.setattr(modulo, "buscar_productos_por_nombre", no_se_busca)
    r = _listar(producto="Tordon D 30", banda="verde")
    assert r.datos["filtros"]["bandas"] == ["IV"]
    assert r.datos["producto"] is None


def test_producto_con_variantes_de_distinta_banda_pregunta_cual(base, monkeypatch):
    _con_catalogo(monkeypatch, [
        _producto(1, "Roundup Fg", "III"), _producto(2, "Roundup Wg", "IV"),
    ])
    r = _listar(producto="Roundup")
    assert r.estado == "faltan_datos"
    assert r.faltantes[0].campo == "producto"
    assert set(r.faltantes[0].opciones) == {"Roundup Fg", "Roundup Wg"}


def test_producto_con_variantes_de_la_misma_banda_no_pregunta(base, monkeypatch):
    _con_catalogo(monkeypatch, [
        _producto(1, "Roundup Fg", "IV"), _producto(2, "Roundup Wg", "IV"),
    ])
    r = _listar(producto="Roundup")
    assert r.estado == "ok"
    assert r.datos["filtros"]["bandas"] == ["IV"]
    assert r.datos["producto"]["variantes"]


def test_producto_que_no_esta_en_el_registro_muestra_todas_y_lo_avisa(base, monkeypatch):
    _con_catalogo(monkeypatch, [])
    r = _listar(producto="Inventadol")
    assert r.estado == "ok"
    assert r.datos["filtros"]["bandas"] is None
    assert any("Inventadol" in a for a in r.advertencias)
