"""Resuelve una descripción informal de vehículo/equipo de aplicación
contra `catalogo.vehiculo` (Fase 9, RF6 `resolver_vehiculo`).

Desde la sesión post-Fase 11 ("RAG de equipos", ver DECISIONES.md) el
catálogo dejó de ser solo un puñado de categorías genéricas: puede tener
equipos puntuales (matrícula + características propias, ej. dos modelos de
avión distintos). Se resuelve en dos pasos: primero sinónimo/nombre como
substring exacto de la descripción (caso común, más preciso que cualquier
score); si no matchea nada, RAG real -- mismo patrón que
`datos/retrievers/catalogo.py::buscar_productos_por_nombre` (score
combinado 0.5 trigram + 0.5 similitud coseno de embedding). Si tampoco supera
el umbral, nunca se elige al azar: se ofrece el catálogo completo como
opciones (igual que un producto ambiguo)."""

from dataclasses import dataclass

from fitosanitarios.datos.vectores import vector_literal
from fitosanitarios.dominio.modelos import CampoFaltante
from fitosanitarios.dominio.motivos import MotivoNoResuelto

UMBRAL_SIMILITUD_RAG = 0.5


@dataclass
class VehiculoResuelto:
    id: int
    nombre: str
    tipo_aplicacion: str


@dataclass
class ResolucionVehiculo:
    vehiculo: VehiculoResuelto | None = None
    opciones_ambiguas: list[str] | None = None  # catálogo completo, se ofrece como lista
    motivo_no_resuelto: MotivoNoResuelto | None = None


def _todos_los_nombres(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT nombre FROM catalogo.vehiculo ORDER BY nombre")
        return [fila[0] for fila in cur.fetchall()]


def resolver_vehiculo(conn, modelo_embeddings, descripcion: str) -> ResolucionVehiculo:
    descripcion_norm = descripcion.strip().lower()

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT v.id, v.nombre, v.tipo_aplicacion
            FROM catalogo.vehiculo v
            WHERE %(d)s ILIKE '%%' || lower(v.nombre) || '%%'
               OR EXISTS (
                   SELECT 1 FROM jsonb_array_elements_text(v.sinonimos) s
                   WHERE %(d)s ILIKE '%%' || lower(s) || '%%'
               )
            ORDER BY length(v.nombre) DESC
            LIMIT 1
            """,
            {"d": descripcion_norm},
        )
        fila = cur.fetchone()
    if fila:
        return ResolucionVehiculo(
            vehiculo=VehiculoResuelto(id=fila[0], nombre=fila[1], tipo_aplicacion=fila[2])
        )

    embedding = vector_literal(modelo_embeddings.encode(descripcion).tolist())
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, nombre, tipo_aplicacion,
                   (0.5 * similarity(nombre, %(d)s)
                    + 0.5 * (1 - (embedding <=> %(emb)s::vector))) AS score
            FROM catalogo.vehiculo
            WHERE embedding IS NOT NULL
            ORDER BY score DESC
            LIMIT 1
            """,
            {"d": descripcion_norm, "emb": embedding},
        )
        fila = cur.fetchone()
    if fila and fila[3] >= UMBRAL_SIMILITUD_RAG:
        return ResolucionVehiculo(
            vehiculo=VehiculoResuelto(id=fila[0], nombre=fila[1], tipo_aplicacion=fila[2])
        )

    nombres = _todos_los_nombres(conn)
    if not nombres:
        return ResolucionVehiculo(motivo_no_resuelto=MotivoNoResuelto.VEHICULO_NO_ENCONTRADO)
    return ResolucionVehiculo(opciones_ambiguas=nombres)


def faltante_vehiculo_no_identificado(descripcion: str, opciones: list[str]) -> CampoFaltante:
    """Lo que se le pregunta al operario cuando la descripción del vehículo no
    coincide con nada: común a `resolver_vehiculo` y `registrar_evento`."""
    return CampoFaltante(
        campo="vehiculo",
        motivo="la descripción no coincide con ningún vehículo del catálogo",
        pregunta_sugerida=f"No identifiqué '{descripcion}'. ¿Cuál de estos es?",
        tipo_entrada="lista",
        opciones=opciones,
    )
