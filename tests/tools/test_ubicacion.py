"""Cómo se elige la normativa según dónde se aplica, sin base (los accesos a
la base se reemplazan por dobles): localidad con ordenanzas, localidad sin
ordenanzas y localidad no cargada, que se resuelven con la normativa provincial
y lo aclaran."""

import pytest

from fitosanitarios.dominio.motivos import MotivoNoResuelto
from fitosanitarios.servicios.localidad import Jurisdiccion
from fitosanitarios.tools import _localidad as modulo
from fitosanitarios.tools._localidad import resolver_ubicacion_o_cortar

LOCALIDADES = [
    Jurisdiccion(id=1, jurisdiccion_id="el-trebol", nombre="El Trébol", provincia_id=10),
    Jurisdiccion(id=2, jurisdiccion_id="pueblo-sin-ordenanzas", nombre="Pueblo Sin Ordenanzas",
                 provincia_id=10),
]
PROVINCIAS = [
    Jurisdiccion(id=10, jurisdiccion_id="santa-fe", nombre="Santa Fe", provincia_id=10),
]
CON_ORDENANZAS = {1}


@pytest.fixture(autouse=True)
def base_falsa(monkeypatch):
    monkeypatch.setattr(modulo, "listar_localidades", lambda conn: LOCALIDADES)
    monkeypatch.setattr(modulo, "listar_provincias", lambda conn: PROVINCIAS)
    monkeypatch.setattr(
        modulo, "localidad_tiene_normativa_municipal", lambda conn, id_: id_ in CON_ORDENANZAS
    )


def test_localidad_con_ordenanzas_usa_su_normativa_municipal():
    ubicacion, corte = resolver_ubicacion_o_cortar(None, "El Trébol")
    assert corte is None
    assert ubicacion.localidad_id == 1 and ubicacion.con_normativa_municipal is True


def test_localidad_cargada_sin_ordenanzas_cae_a_la_provincial_y_lo_marca():
    ubicacion, corte = resolver_ubicacion_o_cortar(None, "Pueblo Sin Ordenanzas")
    assert corte is None
    assert ubicacion.localidad_id == 2 and ubicacion.provincia_id == 10
    assert ubicacion.con_normativa_municipal is False


def test_localidad_no_cargada_con_provincia_usa_la_provincial_y_lo_marca():
    ubicacion, corte = resolver_ubicacion_o_cortar(None, "Rosario", "Santa Fe")
    assert corte is None
    assert ubicacion.nombre == "Rosario"
    assert ubicacion.localidad_id is None and ubicacion.provincia_id == 10
    assert ubicacion.con_normativa_municipal is False


def test_la_provincia_puede_venir_en_el_mismo_texto():
    ubicacion, corte = resolver_ubicacion_o_cortar(None, "Rosario, Santa Fe")
    assert corte is None and ubicacion.provincia_id == 10


def test_localidad_no_cargada_sin_provincia_la_pregunta_nunca_la_supone():
    ubicacion, corte = resolver_ubicacion_o_cortar(None, "Rosario")
    assert ubicacion is None
    assert corte.estado == "faltan_datos"
    (faltante,) = corte.faltantes
    assert faltante.campo == "provincia"
    assert faltante.opciones == ["Santa Fe"]
    assert "Rosario" in faltante.pregunta_sugerida


def test_provincia_no_cargada_es_no_resuelto():
    ubicacion, corte = resolver_ubicacion_o_cortar(None, "Cordoba capital", "Córdoba")
    assert ubicacion is None
    assert corte.estado == "no_resuelto"
    assert corte.motivo == MotivoNoResuelto.JURISDICCION_NO_CUBIERTA


def test_sin_localidad_pide_la_lista_de_cargadas():
    ubicacion, corte = resolver_ubicacion_o_cortar(None, None)
    assert corte.faltantes[0].campo == "localidad"
    assert "El Trébol" in corte.faltantes[0].opciones
