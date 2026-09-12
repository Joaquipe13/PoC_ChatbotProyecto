"""Resuelve una descripción informal de vehículo/equipo de aplicación
contra `catalogo.vehiculo` (Fase 9, RF6 `resolver_vehiculo`).

A diferencia de `validacion_producto.py` (7370 productos, necesita
trigram+embedding), acá el catálogo es un puñado de categorías fijas: se
resuelve por sinónimo/nombre como substring de la descripción (case
insensitive) y, si eso no matchea nada, similitud de trigram como fallback
de typos -- sin cargar el modelo de embeddings (ver DECISIONES.md). Si
tampoco hay match por trigram, nunca se elige al azar: se ofrece el
catálogo completo como opciones (igual que un producto ambiguo)."""

from dataclasses import dataclass

from fitosanitarios.dominio.motivos import MotivoNoResuelto

UMBRAL_SIMILITUD_TRIGRAM = 0.3


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


def resolver_vehiculo(conn, descripcion: str) -> ResolucionVehiculo:
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

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, nombre, tipo_aplicacion, similarity(nombre, %(d)s) AS score
            FROM catalogo.vehiculo
            WHERE nombre %% %(d)s
            ORDER BY score DESC
            LIMIT 1
            """,
            {"d": descripcion_norm},
        )
        fila = cur.fetchone()
    if fila and fila[3] >= UMBRAL_SIMILITUD_TRIGRAM:
        return ResolucionVehiculo(
            vehiculo=VehiculoResuelto(id=fila[0], nombre=fila[1], tipo_aplicacion=fila[2])
        )

    nombres = _todos_los_nombres(conn)
    if not nombres:
        return ResolucionVehiculo(motivo_no_resuelto=MotivoNoResuelto.VEHICULO_NO_ENCONTRADO)
    return ResolucionVehiculo(opciones_ambiguas=nombres)
