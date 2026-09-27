"""`consultar_articulo` sin base: los accesos a datos se reemplazan por dobles."""

import pytest

from fitosanitarios.dominio.motivos import MotivoNoResuelto
from fitosanitarios.servicios.localidad import Jurisdiccion, Ubicacion
from fitosanitarios.tools.consultar_articulo import (
    ConsultarArticuloArgs,
    consultar_articulo_logica,
)
from fitosanitarios.tools.consultar_articulo import tool as modulo

PROVINCIA = Jurisdiccion(id=10, jurisdiccion_id="santa-fe", nombre="Santa Fe", provincia_id=10)
EL_TREBOL = Ubicacion(
    nombre="El Trébol", provincia_id=10, localidad_id=1, jurisdiccion_id="el-trebol",
    con_normativa_municipal=True,
)


def _fila(archivo, numero, texto, jurisdiccion="santa-fe", ambito="provincial", revision=False):
    return {
        "id": 1, "numero": numero, "texto": texto, "pagina": 3, "requiere_revision": revision,
        "archivo": archivo, "ambito": ambito, "jurisdiccion_id": jurisdiccion,
    }


ART_33 = _fila(
    "ley-11273-1995", "33",
    "\xad Prohíbese la aplicación aérea de productos\nde clase toxicológica A y B dentro del "
    "radio de 3.000 metros.",
)
ART_6_OTRA_NORMA = _fila("ordenanza-841-2010", "33", "Otro texto.", "el-trebol", "municipal")
NORMAS = [
    {"archivo": "ley-11273-1995", "ambito": "provincial", "jurisdiccion_id": "santa-fe"},
    {"archivo": "ley-055297-2017", "ambito": "provincial", "jurisdiccion_id": "santa-fe"},
    {"archivo": "ordenanza-841-2010", "ambito": "municipal", "jurisdiccion_id": "el-trebol"},
]


@pytest.fixture
def base(monkeypatch):
    """Estado de la 'base' que cada test puede cambiar."""
    estado = {"filas": [ART_33], "consultas": []}

    def articulos(conn, numero, localidad_id, provincia_id):
        estado["consultas"].append((numero, localidad_id, provincia_id))
        return [f for f in estado["filas"] if f["numero"] == numero]

    monkeypatch.setattr(modulo, "articulos_por_numero", articulos)
    monkeypatch.setattr(modulo, "normas_de_alcance", lambda conn, loc, prov: NORMAS)
    monkeypatch.setattr(modulo, "listar_provincias", lambda conn: [PROVINCIA])
    monkeypatch.setattr(
        modulo, "resolver_ubicacion_o_cortar", lambda conn, texto, provincia=None: (EL_TREBOL, None)
    )
    return estado


def _consultar(**kwargs):
    return consultar_articulo_logica(ConsultarArticuloArgs(**kwargs), None)


def test_devuelve_el_texto_del_articulo_limpio_con_su_cita(base):
    r = _consultar(numero_articulo="art. 33")
    assert r.estado == "ok"
    assert r.datos["norma_legible"] == "Ley 11273/1995" and r.datos["numero"] == "33"
    assert r.datos["partes"] == [{
        "texto": "Prohíbese la aplicación aérea de productos de clase toxicológica A y B "
                 "dentro del radio de 3.000 metros.",
        "pagina": 3,
    }]
    (cita,) = r.citas
    assert (cita.norma, cita.articulo, cita.jurisdiccion_id) == ("ley-11273-1995", "33", "santa-fe")


def test_sin_localidad_busca_en_la_provincia_y_avisa_que_no_incluyo_ordenanzas(base):
    r = _consultar(numero_articulo="33")
    assert base["consultas"] == [("33", None, 10)]  # sin localidad, con la provincia
    assert any("decime la localidad" in a for a in r.advertencias)


def test_con_localidad_busca_tambien_su_normativa_municipal(base):
    r = _consultar(numero_articulo="33", localidad="El Trébol")
    assert base["consultas"] == [("33", 1, 10)]
    assert not any("decime la localidad" in a for a in r.advertencias)


def test_localidad_sin_ordenanzas_lo_aclara(base, monkeypatch):
    sin = Ubicacion(nombre="Rosario", provincia_id=10, con_normativa_municipal=False)
    monkeypatch.setattr(modulo, "resolver_ubicacion_o_cortar", lambda c, t, p=None: (sin, None))
    r = _consultar(numero_articulo="33", localidad="Rosario")
    aviso = "No se cuenta con la normativa municipal de Rosario"
    assert any(a.startswith(aviso) for a in r.advertencias)


def test_el_numero_esta_en_varias_normas_pregunta_cual(base):
    base["filas"] = [ART_33, ART_6_OTRA_NORMA]
    r = _consultar(numero_articulo="33", localidad="El Trébol")
    assert r.estado == "faltan_datos"
    (falta,) = r.faltantes
    assert falta.campo == "norma" and falta.tipo_entrada == "lista"
    assert falta.opciones == ["Ley 11273/1995 (santa-fe)", "Ordenanza 841/2010 (el-trebol)"]


def test_la_respuesta_a_esa_pregunta_resuelve_la_norma(base):
    base["filas"] = [ART_33, ART_6_OTRA_NORMA]
    r = _consultar(
        numero_articulo="33", norma="Ordenanza 841/2010 (el-trebol)", localidad="El Trébol"
    )
    assert r.estado == "ok" and r.datos["norma"] == "ordenanza-841-2010"


def test_la_norma_puede_venir_escrita_a_mano(base):
    base["filas"] = [ART_33, ART_6_OTRA_NORMA]
    r = _consultar(numero_articulo="33", norma="la ley 11.273")
    assert r.estado == "ok" and r.datos["norma"] == "ley-11273-1995"


def test_con_la_norma_nombrada_no_pide_la_localidad(base):
    """Plan de pruebas (27/09/2026): "el artículo 33 de la ley 11273" avisaba "Si es de una
    ordenanza, decime la localidad", aunque ya había dicho que era una ley provincial."""
    base["filas"] = [ART_33, ART_6_OTRA_NORMA]
    r = _consultar(numero_articulo="33", norma="ley 11273")
    assert not any("decime la localidad" in a for a in r.advertencias)


def test_norma_que_no_esta_cargada_lista_las_que_si(base):
    r = _consultar(numero_articulo="33", norma="ley 999")
    assert r.estado == "no_resuelto" and r.motivo == MotivoNoResuelto.ARTICULO_NO_ENCONTRADO
    assert "Ley 11273/1995 (santa-fe)" in r.advertencias[0]
    assert "Ordenanza 841/2010 (el-trebol)" in r.advertencias[0]


def test_articulo_que_no_existe(base):
    r = _consultar(numero_articulo="999")
    assert r.estado == "no_resuelto" and r.motivo == MotivoNoResuelto.ARTICULO_NO_ENCONTRADO
    assert "999" in r.advertencias[0]


def test_sin_numero_pregunta_cual(base):
    for texto in ("", "el de las escuelas"):
        r = _consultar(numero_articulo=texto)
        assert r.estado == "faltan_datos" and r.faltantes[0].campo == "numero_articulo"


def test_numero_repetido_dentro_de_una_norma_devuelve_todas_las_partes(base):
    base["filas"] = [
        _fila("ley-11273-1995", "13", "Primero."), _fila("ley-11273-1995", "13", "Segundo."),
    ]
    r = _consultar(numero_articulo="13")
    assert r.estado == "ok"
    assert [p["texto"] for p in r.datos["partes"]] == ["Primero.", "Segundo."]
    assert len(r.citas) == 1


def test_avisa_si_el_texto_vino_de_ocr(base):
    base["filas"] = [_fila("ley-11273-1995", "33", "Texto.", revision=True)]
    r = _consultar(numero_articulo="33")
    assert any("escaneado" in a for a in r.advertencias)


def test_si_hay_varias_provincias_y_no_se_dio_localidad_la_pide(base, monkeypatch):
    otra = Jurisdiccion(id=11, jurisdiccion_id="cordoba", nombre="Córdoba", provincia_id=11)
    monkeypatch.setattr(modulo, "listar_provincias", lambda conn: [PROVINCIA, otra])
    from fitosanitarios.dominio.modelos import ResultadoTool

    pedir = ResultadoTool(estado="faltan_datos")
    monkeypatch.setattr(modulo, "resolver_ubicacion_o_cortar", lambda c, t, p=None: (None, pedir))
    assert _consultar(numero_articulo="33") is pedir
