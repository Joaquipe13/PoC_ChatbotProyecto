"""Tests de matching de vehículo contra el catálogo real (Fase 9, RF6),
sembrado en la migración 001: pulverizador autopropulsado/mosquito,
pulverizador de arrastre, mochila, avión fumigador, dron, más los 2 aviones
puntuales agregados en la sesión post-Fase 11 (Air Tractor AT-502B, PZL M18
Dromader -- ver DECISIONES.md, "RAG de equipos")."""

from fitosanitarios.servicios.resolucion_vehiculo import resolver_vehiculo


def test_match_por_nombre_exacto(conexion, modelo_embeddings):
    resolucion = resolver_vehiculo(conexion, modelo_embeddings, "pulverizador autopropulsado")
    assert resolucion.vehiculo is not None
    assert resolucion.vehiculo.nombre == "pulverizador autopropulsado"
    assert resolucion.vehiculo.tipo_aplicacion == "terrestre"


def test_match_por_sinonimo_como_substring(conexion, modelo_embeddings):
    resolucion = resolver_vehiculo(conexion, modelo_embeddings, "voy a aplicar con la mosquito")
    assert resolucion.vehiculo is not None
    assert resolucion.vehiculo.nombre == "pulverizador autopropulsado"


def test_match_dron_es_aereo(conexion, modelo_embeddings):
    resolucion = resolver_vehiculo(conexion, modelo_embeddings, "uso el dron")
    assert resolucion.vehiculo is not None
    assert resolucion.vehiculo.nombre == "dron"
    assert resolucion.vehiculo.tipo_aplicacion == "aerea"


def test_match_por_sinonimo_exacto_distingue_los_dos_aviones(conexion, modelo_embeddings):
    resolucion = resolver_vehiculo(conexion, modelo_embeddings, "vuelo con la dromader")
    assert resolucion.vehiculo is not None
    assert resolucion.vehiculo.nombre == "PZL M18 Dromader"


def test_match_por_rag_sin_sinonimo_exacto(conexion, modelo_embeddings):
    """"avioneta grande" no es un sinónimo cargado -- tiene que resolverse
    por el score combinado de trigram + embedding, no por substring."""
    resolucion = resolver_vehiculo(conexion, modelo_embeddings, "la avioneta grande turbohelice")
    assert resolucion.vehiculo is not None
    assert resolucion.vehiculo.nombre == "Air Tractor AT-502B"


def test_descripcion_sin_match_ofrece_el_catalogo_completo(conexion, modelo_embeddings):
    resolucion = resolver_vehiculo(
        conexion, modelo_embeddings, "xqzwplk asdf no es un vehiculo de verdad"
    )
    assert resolucion.vehiculo is None
    assert resolucion.motivo_no_resuelto is None
    assert resolucion.opciones_ambiguas is not None
    assert "dron" in resolucion.opciones_ambiguas
    assert len(resolucion.opciones_ambiguas) == 7
