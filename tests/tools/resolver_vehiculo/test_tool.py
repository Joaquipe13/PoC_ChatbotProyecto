from fitosanitarios.tools.resolver_vehiculo import ResolverVehiculoArgs, resolver_vehiculo_logica


def test_resuelve_por_sinonimo(conexion, modelo_embeddings):
    args = ResolverVehiculoArgs(descripcion="la mosquito")
    resultado = resolver_vehiculo_logica(args, conexion, modelo_embeddings)
    assert resultado.estado == "ok"
    assert resultado.datos["vehiculo"] == "pulverizador autopropulsado"
    assert resultado.datos["tipo_aplicacion"] == "terrestre"


def test_resuelve_avion_puntual_por_rag(conexion, modelo_embeddings):
    args = ResolverVehiculoArgs(descripcion="la avioneta grande turbohelice")
    resultado = resolver_vehiculo_logica(args, conexion, modelo_embeddings)
    assert resultado.estado == "ok"
    assert resultado.datos["vehiculo"] == "Air Tractor AT-502B"
    assert resultado.datos["tipo_aplicacion"] == "aerea"


def test_no_matchea_nada_ofrece_lista(conexion, modelo_embeddings):
    args = ResolverVehiculoArgs(descripcion="xqzwplk asdf no es un vehiculo de verdad")
    resultado = resolver_vehiculo_logica(args, conexion, modelo_embeddings)
    assert resultado.estado == "faltan_datos"
    assert resultado.faltantes[0].campo == "vehiculo"
    assert resultado.faltantes[0].tipo_entrada == "lista"
    assert len(resultado.faltantes[0].opciones) == 7
