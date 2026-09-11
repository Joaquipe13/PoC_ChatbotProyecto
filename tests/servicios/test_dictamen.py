from fitosanitarios.dominio.modelos import Cita
from fitosanitarios.servicios.dictamen import ChequeoProducto, armar_dictamen
from fitosanitarios.servicios.dosis import comparar_dosis
from fitosanitarios.servicios.reglas import ReglaCandidata, evaluar_distancia_zona


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
        chequeos_distancia=[],
        chequeos_dosis=[],
        chequeos_no_realizados=[],
    )
    assert dictamen.resultado == "APTA"
    assert dictamen.observaciones == []


def test_distancia_insuficiente_da_observada_con_todas_las_observaciones():
    # Reproduce el ejemplo de dictamen de la skill: distancia insuficiente Y
    # dosis fuera de rango, ambas listadas (no solo la primera).
    regla = ReglaCandidata(
        tipo_zona="escuela", tipo_aplicacion="terrestre", bandas=["todas"],
        distancia_min_m=100, norma="ordenanza-914-2018", articulo="8",
        jurisdiccion_id="san-carlos-centro",
    )
    chequeo_distancia = evaluar_distancia_zona(
        "escuela", "Escuela N 12", 80.0, [regla], "terrestre", "IV"
    )
    chequeo_dosis = comparar_dosis(5.0, "L/ha", 2.0, 3.0, "L/ha", tolerancia_pct=10.0)

    dictamen = armar_dictamen(
        chequeos_producto=[_producto_ok()],
        chequeos_distancia=[chequeo_distancia],
        chequeos_dosis=[chequeo_dosis],
        chequeos_no_realizados=[],
    )

    assert dictamen.resultado == "OBSERVADA"
    assert len(dictamen.observaciones) == 2
    descripciones = " ".join(o.descripcion for o in dictamen.observaciones)
    assert "80 m" in descripciones and "100 m" in descripciones
    assert "67" in descripciones or "66" in descripciones  # desvío de dosis


def test_producto_no_registrado_da_observada():
    producto = ChequeoProducto(producto_nombre="Producto Trucho", registrado=False)
    dictamen = armar_dictamen([producto], [], [], [])
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
    dictamen = armar_dictamen([producto], [], [], [])
    assert dictamen.resultado == "NO_EVALUABLE"
    assert dictamen.observaciones == []  # nada "no cumple", solo no se pudo evaluar
    assert len(dictamen.chequeos_no_realizados) == 1


def test_no_evaluable_nunca_se_convierte_en_apta_por_omision():
    producto_no_verificado = ChequeoProducto(
        producto_nombre="X", registrado=True, activo=True, cultivo_autorizado=None
    )
    dictamen = armar_dictamen(
        chequeos_producto=[producto_no_verificado, _producto_ok()],
        chequeos_distancia=[],
        chequeos_dosis=[],
        chequeos_no_realizados=[],
    )
    assert dictamen.resultado == "NO_EVALUABLE"


def test_citas_se_acumulan_de_producto_y_distancia():
    regla = ReglaCandidata(
        tipo_zona="curso_agua", tipo_aplicacion="todas", bandas=["todas"],
        distancia_min_m=50, norma="ordenanza-914-2018", articulo="10",
        jurisdiccion_id="san-carlos-centro",
    )
    chequeo_distancia = evaluar_distancia_zona(
        "curso_agua", "Arroyo", 100.0, [regla], "terrestre", "IV"
    )
    dictamen = armar_dictamen([_producto_ok()], [chequeo_distancia], [], [])
    assert dictamen.resultado == "APTA"  # cumple, pero igual se citan las fuentes
    fuentes = {c.fuente for c in dictamen.citas}
    assert fuentes == {"senasa", "normativa"}


def test_dosis_no_comparable_va_a_no_realizados_no_a_observaciones():
    chequeo_dosis = comparar_dosis(2.5, "L/ha", None, None, None, tolerancia_pct=10.0)
    dictamen = armar_dictamen([_producto_ok()], [], [chequeo_dosis], [])
    assert dictamen.resultado == "NO_EVALUABLE"
    assert dictamen.observaciones == []


def test_dosis_requiere_volumen_caldo_va_a_no_realizados():
    chequeo_dosis = comparar_dosis(17.0, "ml/100L", 15.0, 20.0, "ml/100L", tolerancia_pct=10.0)
    dictamen = armar_dictamen([_producto_ok()], [], [chequeo_dosis], [])
    assert dictamen.resultado == "NO_EVALUABLE"
    assert any("volumen de caldo" in c for c in dictamen.chequeos_no_realizados)
