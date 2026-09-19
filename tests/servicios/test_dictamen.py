from fitosanitarios.dominio.modelos import Cita
from fitosanitarios.servicios.condiciones_aplicacion import calcular_condiciones
from fitosanitarios.servicios.dictamen import ChequeoProducto, armar_dictamen
from fitosanitarios.servicios.dosis import comparar_dosis
from fitosanitarios.servicios.reglas import ReglaCandidata


def _producto_ok() -> ChequeoProducto:
    return ChequeoProducto(
        producto_nombre="Glifosato Full 48 SL",
        registrado=True,
        activo=True,
        cultivo_autorizado=True,
        banda_toxicologica="IV",
        citas=[Cita(fuente="senasa", registro_senasa="12345")],
    )


def test_todo_cumple_da_apta():
    dictamen = armar_dictamen(
        chequeos_producto=[_producto_ok()],
        chequeos_dosis=[],
        chequeos_no_realizados=[],
    )
    assert dictamen.resultado == "APTA"
    assert dictamen.observaciones == []


def test_producto_no_autorizado_y_dosis_fuera_de_rango_listan_todas_las_observaciones():
    producto = ChequeoProducto(
        producto_nombre="Glifosato Full 48 SL", registrado=True, activo=True,
        cultivo_autorizado=False, banda_toxicologica="IV",
    )
    chequeo_dosis = comparar_dosis(5.0, "L/ha", 2.0, 3.0, "L/ha", tolerancia_pct=10.0)

    dictamen = armar_dictamen(
        chequeos_producto=[producto], chequeos_dosis=[chequeo_dosis], chequeos_no_realizados=[],
    )

    assert dictamen.resultado == "OBSERVADA"
    assert len(dictamen.observaciones) == 2
    descripciones = " ".join(o.descripcion for o in dictamen.observaciones)
    assert "no está autorizado" in descripciones
    assert "67" in descripciones or "66" in descripciones  # desvío de dosis


def test_producto_no_registrado_da_observada():
    producto = ChequeoProducto(producto_nombre="Producto Trucho", registrado=False)
    dictamen = armar_dictamen([producto], [], [])
    assert dictamen.resultado == "OBSERVADA"
    assert "no está registrado" in dictamen.observaciones[0].descripcion


def test_producto_sin_usos_registrados_da_no_evaluable_no_apta():
    # "Si un producto no tiene usos registrados, cultivo y dosis figuran
    # como 'no verificado' y el dictamen queda NO EVALUABLE." (skill)
    producto = ChequeoProducto(
        producto_nombre="Producto Nuevo",
        registrado=True,
        activo=True,
        cultivo_autorizado=None,  # no se pudo verificar
    )
    dictamen = armar_dictamen([producto], [], [])
    assert dictamen.resultado == "NO_EVALUABLE"
    assert dictamen.observaciones == []  # nada "no cumple", solo no se pudo evaluar
    assert len(dictamen.chequeos_no_realizados) == 1


def test_no_evaluable_nunca_se_convierte_en_apta_por_omision():
    producto_no_verificado = ChequeoProducto(
        producto_nombre="X", registrado=True, activo=True, cultivo_autorizado=None
    )
    dictamen = armar_dictamen(
        chequeos_producto=[producto_no_verificado, _producto_ok()],
        chequeos_dosis=[],
        chequeos_no_realizados=[],
    )
    assert dictamen.resultado == "NO_EVALUABLE"


def test_condiciones_se_informan_sin_cambiar_el_resultado_y_citan_la_norma():
    regla = ReglaCandidata(
        tipo_zona="zona_urbana", tipo_aplicacion="todas", bandas=["todas"],
        distancia_min_m=500, norma="ordenanza-841-2010", articulo="6",
        jurisdiccion_id="el-trebol",
    )
    condiciones = calcular_condiciones("El Trébol", "terrestre", {"Glifosato": "IV"}, [regla])
    dictamen = armar_dictamen([_producto_ok()], [], [], condiciones)
    assert dictamen.resultado == "APTA"  # la distancia informa, no dictamina
    assert dictamen.condiciones.distancias_minimas[0].distancia_min_m == 500
    fuentes = {c.fuente for c in dictamen.citas}
    assert fuentes == {"senasa", "normativa"}


def test_producto_sin_banda_deja_la_aplicacion_no_evaluable():
    # Sin la banda de un producto, la de la aplicación podría ser más
    # restrictiva: ausencia de evidencia no es aprobación.
    condiciones = calcular_condiciones("El Trébol", "terrestre", {"Producto X": None}, [])
    dictamen = armar_dictamen([_producto_ok()], [], [], condiciones)
    assert dictamen.resultado == "NO_EVALUABLE"
    assert any("Producto X" in c for c in dictamen.chequeos_no_realizados)


def test_dosis_no_comparable_va_a_no_realizados_no_a_observaciones():
    chequeo_dosis = comparar_dosis(2.5, "L/ha", None, None, None, tolerancia_pct=10.0)
    dictamen = armar_dictamen([_producto_ok()], [chequeo_dosis], [])
    assert dictamen.resultado == "NO_EVALUABLE"
    assert dictamen.observaciones == []


def test_dosis_requiere_volumen_caldo_va_a_no_realizados():
    chequeo_dosis = comparar_dosis(17.0, "ml/100L", 15.0, 20.0, "ml/100L", tolerancia_pct=10.0)
    dictamen = armar_dictamen([_producto_ok()], [chequeo_dosis], [])
    assert dictamen.resultado == "NO_EVALUABLE"
    assert any("volumen de caldo" in c for c in dictamen.chequeos_no_realizados)
