import json
from pathlib import Path

import pytest

from fitosanitarios.senasa.cliente import DetalleProducto, ProductoListado, parsear_pagina_listado

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "senasa"


def _cargar_fixture(nombre: str) -> dict:
    with (FIXTURES / nombre).open(encoding="utf-8") as f:
        return json.load(f)


# --- Listado ---


def test_parsear_pagina_listado_real():
    data = _cargar_fixture("listado_pagina_ejemplo.json")
    pagina = parsear_pagina_listado(data)
    assert pagina.total_elementos > 7000
    assert len(pagina.productos) == 5
    primero = pagina.productos[0]
    assert primero.numero_inscripcion == "42770"
    assert primero.marca == "CORE OPTIMUS"
    assert "<b>" in primero.sustancias_activas  # se limpia en normalizador, no acá


def test_producto_listado_tolera_sustancias_activas_null():
    # Caso real encontrado en el crawl completo (12/09/2026): algunos productos
    # (coadyuvantes) no tienen sustanciasActivas y SENASA manda `null`, no "".
    crudo = {
        "id": 1,
        "numeroInscripcion": "99999",
        "marca": "PRODUCTO SIN ACTIVOS",
        "nombreFirma": "FIRMA X",
        "claseToxicologica": "S/D",
        "sustanciasActivas": None,
    }
    producto = ProductoListado.model_validate(crudo)
    assert producto.sustancias_activas == ""


def test_producto_listado_tolera_marca_y_firma_null():
    crudo = {
        "id": 2,
        "numeroInscripcion": "88888",
        "marca": None,
        "nombreFirma": None,
        "claseToxicologica": None,
        "sustanciasActivas": None,
    }
    producto = ProductoListado.model_validate(crudo)
    assert producto.marca == ""
    assert producto.nombre_firma == ""


# --- Detalle ---


@pytest.mark.parametrize(
    "nombre_fixture",
    [
        "detalle_239970.json",
        "detalle_195117.json",
        "detalle_190758.json",
        "detalle_180647.json",
    ],
)
def test_detalle_producto_parsea_respuesta_real_sin_error(nombre_fixture: str):
    data = _cargar_fixture(nombre_fixture)
    detalle = DetalleProducto.model_validate(data)
    assert detalle.id > 0
    assert detalle.numero_inscripcion


def test_detalle_claseToxicologica_es_objeto_estructurado():
    # Reg. 42770 "CORE OPTIMUS": banda IV, color VERDE (dato real).
    data = _cargar_fixture("detalle_239970.json")
    detalle = DetalleProducto.model_validate(data)
    assert detalle.clase_toxicologica is not None
    assert detalle.clase_toxicologica.clase_tox == "IV"
    assert detalle.clase_toxicologica.color == "VERDE"


def test_detalle_principios_activos_con_concentracion_y_unidad():
    data = _cargar_fixture("detalle_239970.json")
    detalle = DetalleProducto.model_validate(data)
    assert len(detalle.principios_activos) == 3
    primero = detalle.principios_activos[0]
    assert primero.nomenclador.descripcion
    assert primero.concentracion == 48.0
    assert primero.unidad_medida.sigla == "%"


def test_detalle_aplicaciones_por_producto_con_cultivo_y_dosis_real():
    # Reg. 40465 "FOCUS MAX": aplicación real para Apio, dosis "17 ml/ 100 Litros".
    data = _cargar_fixture("detalle_195117.json")
    detalle = DetalleProducto.model_validate(data)
    assert len(detalle.aplicaciones_por_producto) == 1
    aplicacion = detalle.aplicaciones_por_producto[0]
    assert aplicacion.cultivo.nombre_comun == "Apio"
    assert aplicacion.dosis == "17 ml/ 100 Litros"


def test_detalle_documentos_distingue_marbete_de_hds():
    # Hallazgo real (no documentado originalmente en la skill): productoDocumentos
    # trae distintos tipos identificados por `nombre` ('HDS' vs 'Marbete').
    data = _cargar_fixture("detalle_180647.json")
    detalle = DetalleProducto.model_validate(data)
    nombres = {doc.nombre for doc in detalle.producto_documentos}
    assert "HDS" in nombres
    assert "Marbete" in nombres
    marbetes = [doc for doc in detalle.producto_documentos if doc.es_marbete]
    assert len(marbetes) == 1


def test_detalle_producto_sin_documentos_ni_aplicaciones():
    # Caso muy frecuente en productos recién registrados (ver DECISIONES.md).
    data = _cargar_fixture("detalle_239970.json")
    detalle = DetalleProducto.model_validate(data)
    assert detalle.producto_documentos == []
    assert detalle.aplicaciones_por_producto == []
