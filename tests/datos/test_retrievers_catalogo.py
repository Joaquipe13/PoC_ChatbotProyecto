"""Tests de integración de datos/retrievers/catalogo.py contra Postgres real
(Docker), sobre el catálogo real de SENASA cargado en la Fase 2 (7.370
productos, 187 con detalle)."""

import pytest

from fitosanitarios.datos.retrievers.catalogo import (
    aptitudes_registradas,
    buscar_productos_por_nombre,
    listar_productos_por_filtro,
    resolver_entidad_por_nombre,
    resolver_firmas,
)


def test_buscar_por_nombre_exacto_encuentra_el_producto(conexion, modelo_embeddings):
    # Producto real del catálogo cargado (ver DECISIONES.md).
    candidatos = buscar_productos_por_nombre(conexion, "Abril 50 Curasemilla", modelo_embeddings)
    assert len(candidatos) >= 1
    assert candidatos[0].marca == "Abril 50 Curasemilla"
    assert candidatos[0].numero_inscripcion == "38052"


def test_buscar_por_nombre_con_typo_igual_encuentra_candidatos(conexion, modelo_embeddings):
    # Trigram tolera un error de tipeo menor (falta una letra).
    candidatos = buscar_productos_por_nombre(conexion, "Abril 50 Curasemila", modelo_embeddings)
    assert any(c.marca == "Abril 50 Curasemilla" for c in candidatos)


def test_buscar_producto_con_usos_registrados_trae_los_usos(conexion, modelo_embeddings):
    candidatos = buscar_productos_por_nombre(conexion, "Abril 50 Curasemilla", modelo_embeddings)
    candidato = candidatos[0]
    assert len(candidato.usos_registrados) == 4
    assert all("cultivo" in u for u in candidato.usos_registrados)


def test_buscar_nombre_inexistente_no_devuelve_nada_por_encima_del_umbral(
    conexion, modelo_embeddings
):
    candidatos = buscar_productos_por_nombre(
        conexion, "Xyzzyproductoquenoexisteenelregistro123", modelo_embeddings
    )
    assert candidatos == []


def test_resolver_cultivo_por_nombre_real(conexion, modelo_embeddings):
    # "Soja" es un cultivo real cargado desde aplicacionesPorProducto.
    cultivo_id = resolver_entidad_por_nombre(
        conexion, "cultivo", "nombre", "soja", modelo_embeddings
    )
    assert cultivo_id is not None


def test_resolver_cultivo_inexistente_devuelve_none(conexion, modelo_embeddings):
    cultivo_id = resolver_entidad_por_nombre(
        conexion, "cultivo", "nombre", "planta inventada que no existe zzz", modelo_embeddings
    )
    assert cultivo_id is None


def test_listar_productos_por_cultivo(conexion, modelo_embeddings):
    cultivo_id = resolver_entidad_por_nombre(
        conexion, "cultivo", "nombre", "soja", modelo_embeddings
    )
    assert cultivo_id is not None
    listado = listar_productos_por_filtro(conexion, cultivo_id=cultivo_id, limite=10)
    assert len(listado.productos) == 10 and listado.total > 10
    assert all("marca" in p for p in listado.productos)
    # una fila por producto, no una por uso registrado
    registros = [p["numero_inscripcion"] for p in listado.productos]
    assert len(registros) == len(set(registros))


def test_listar_productos_sin_ningun_filtro_lanza_error(conexion):
    with pytest.raises(ValueError):
        listar_productos_por_filtro(conexion)


def test_listar_productos_por_banda(conexion, modelo_embeddings):
    cultivo_id = resolver_entidad_por_nombre(
        conexion, "cultivo", "nombre", "soja", modelo_embeddings
    )
    listado = listar_productos_por_filtro(
        conexion, cultivo_id=cultivo_id, bandas_permitidas=["III", "IV"], limite=10
    )
    for p in listado.productos:
        assert p["banda_toxicologica"] in ("III", "IV", None)


def test_listar_productos_por_aptitud_filtra_el_jsonb_del_registro(conexion):
    """La aptitud se aceptaba pero no se filtraba: "fungicidas para trigo" listaba 2,4-D."""
    listado = listar_productos_por_filtro(conexion, aptitudes=["Fungicida"], limite=50)
    assert listado.total > 0
    with conexion.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM catalogo.producto p WHERE p.id = ANY(%s) AND NOT "
            "p.crudo_api->'productos_aptitudes' @> '[{\"nomenclador\": "
            "{\"descripcion\": \"Fungicida\"}}]'",
            ([p["id"] for p in listado.productos],),
        )
        assert cur.fetchone()[0] == 0


def test_listar_productos_por_firma_y_marca(conexion):
    firmas = resolver_firmas(conexion, "Syngenta")
    assert firmas
    listado = listar_productos_por_filtro(conexion, firma_ids=firmas, marca="amistar")
    assert listado.productos
    assert all("amistar" in p["marca"].lower() for p in listado.productos)
    assert all("syngenta" in p["firma"].lower() for p in listado.productos)


def test_aptitudes_registradas_incluye_las_comunes(conexion):
    aptitudes = aptitudes_registradas(conexion)
    assert {"Fungicida", "Herbicida", "Insecticida"} <= set(aptitudes)
