from fitosanitarios.servicios.localidad import Jurisdiccion, resolver_localidad

CARGADAS = [
    Jurisdiccion(id=1, jurisdiccion_id="el-trebol", nombre="El Trébol", provincia_id=1),
    Jurisdiccion(
        id=2, jurisdiccion_id="san-carlos-centro", nombre="San Carlos Centro", provincia_id=1
    ),
    Jurisdiccion(id=3, jurisdiccion_id="san-carlos-sud", nombre="San Carlos Sud", provincia_id=1),
]


def test_coincide_por_nombre_sin_tildes_ni_mayusculas():
    assert resolver_localidad("el trebol", CARGADAS).localidad.jurisdiccion_id == "el-trebol"


def test_coincide_por_jurisdiccion_id():
    assert resolver_localidad("san-carlos-sud", CARGADAS).localidad.id == 3


def test_nombre_dentro_de_un_texto_mas_largo():
    resolucion = resolver_localidad("Aplicación en El Trébol, Santa Fe", CARGADAS)
    assert resolucion.localidad.jurisdiccion_id == "el-trebol"


def test_texto_ambiguo_devuelve_opciones_y_no_elige():
    resolucion = resolver_localidad("San Carlos", CARGADAS)
    assert resolucion.localidad is None
    assert {j.id for j in resolucion.ambiguas} == {2, 3}


def test_localidad_no_cargada_no_resuelve_ni_ofrece_opciones():
    resolucion = resolver_localidad("Buenos Aires", CARGADAS)
    assert resolucion.localidad is None
    assert resolucion.ambiguas == []


def test_texto_vacio():
    assert resolver_localidad("  ", CARGADAS).localidad is None
