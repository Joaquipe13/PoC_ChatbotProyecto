"""Tests de matching de vehículo contra el catálogo real (Fase 9, RF6),
sembrado en la migración 001 (pulverizador autopropulsado/mosquito,
pulverizador de arrastre, mochila, avión fumigador, dron)."""

from fitosanitarios.servicios.resolucion_vehiculo import resolver_vehiculo


def test_match_por_nombre_exacto(conexion):
    resolucion = resolver_vehiculo(conexion, "pulverizador autopropulsado")
    assert resolucion.vehiculo is not None
    assert resolucion.vehiculo.nombre == "pulverizador autopropulsado"
    assert resolucion.vehiculo.tipo_aplicacion == "terrestre"


def test_match_por_sinonimo_como_substring(conexion):
    resolucion = resolver_vehiculo(conexion, "voy a aplicar con la mosquito")
    assert resolucion.vehiculo is not None
    assert resolucion.vehiculo.nombre == "pulverizador autopropulsado"


def test_match_dron_es_aereo(conexion):
    resolucion = resolver_vehiculo(conexion, "uso el dron")
    assert resolucion.vehiculo is not None
    assert resolucion.vehiculo.nombre == "dron"
    assert resolucion.vehiculo.tipo_aplicacion == "aerea"


def test_descripcion_sin_match_ofrece_el_catalogo_completo(conexion):
    resolucion = resolver_vehiculo(conexion, "un vehiculo que no existe en absoluto zzz")
    assert resolucion.vehiculo is None
    assert resolucion.motivo_no_resuelto is None
    assert resolucion.opciones_ambiguas is not None
    assert "dron" in resolucion.opciones_ambiguas
    assert len(resolucion.opciones_ambiguas) == 5
