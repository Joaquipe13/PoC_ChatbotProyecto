"""Tests de integración de datos/retrievers/catalogo.py contra Postgres real
(Docker), sobre el catálogo real de SENASA cargado en la Fase 2 (7.370
productos, 187 con detalle)."""

import pytest

from fitosanitarios.datos.retrievers.catalogo import (
    buscar_productos_por_nombre,
    listar_productos_por_filtro,
    resolver_entidad_por_nombre,
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
    productos = listar_productos_por_filtro(conexion, cultivo_id=cultivo_id, limite=10)
    assert len(productos) > 0
    assert all("marca" in p for p in productos)


def test_listar_productos_sin_ningun_filtro_lanza_error(conexion):
    with pytest.raises(ValueError):
        listar_productos_por_filtro(conexion)


def test_listar_productos_por_banda(conexion, modelo_embeddings):
    cultivo_id = resolver_entidad_por_nombre(
        conexion, "cultivo", "nombre", "soja", modelo_embeddings
    )
    productos = listar_productos_por_filtro(
        conexion, cultivo_id=cultivo_id, bandas_permitidas=["III", "IV"], limite=10
    )
    for p in productos:
        assert p["banda_toxicologica"] in ("III", "IV", None)
