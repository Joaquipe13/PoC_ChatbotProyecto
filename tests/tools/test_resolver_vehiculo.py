from fitosanitarios.tools.resolver_vehiculo import ResolverVehiculoArgs, resolver_vehiculo_logica


def test_resuelve_por_sinonimo(conexion):
    args = ResolverVehiculoArgs(descripcion="la mosquito")
    resultado = resolver_vehiculo_logica(args, conexion)
    assert resultado.estado == "ok"
    assert resultado.datos["vehiculo"] == "pulverizador autopropulsado"
    assert resultado.datos["tipo_aplicacion"] == "terrestre"


def test_no_matchea_nada_ofrece_lista(conexion):
    args = ResolverVehiculoArgs(descripcion="zzz no existe zzz")
    resultado = resolver_vehiculo_logica(args, conexion)
    assert resultado.estado == "faltan_datos"
    assert resultado.faltantes[0].campo == "vehiculo"
    assert resultado.faltantes[0].tipo_entrada == "lista"
    assert len(resultado.faltantes[0].opciones) == 5
