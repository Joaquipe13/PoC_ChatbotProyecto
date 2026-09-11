"""Servicios de geometría determinista (ver skill, "Geo").

Sin PostGIS: opera en Python sobre geometrías GeoJSON que ya trajo el
retriever de `datos/retrievers/territorio.py` (prefiltradas por bounding box
en SQL). Punto y polígonos se reproyectan al CRS métrico que calcula
`geopandas.GeoSeries.estimate_utm_crs()` -- EPSG:32720 en la zona de Rosario,
como cita la skill -- para que las distancias sean metros reales, no grados.
"""

from dataclasses import dataclass

import geopandas as gpd
from shapely.geometry import Point, shape


@dataclass
class LocalidadCandidata:
    id: int
    jurisdiccion_id: str
    nombre: str
    provincia_id: int
    limite: dict  # GeoJSON


@dataclass
class ZonaCandidata:
    id: int
    tipo: str
    nombre: str
    jurisdiccion_id: str
    geometria: dict  # GeoJSON


@dataclass
class ZonaConDistancia:
    id: int
    tipo: str
    nombre: str
    jurisdiccion_id: str
    distancia_m: float


def resolver_jurisdiccion(
    lat: float, lon: float, localidades: list[LocalidadCandidata]
) -> LocalidadCandidata | None:
    """`localidades` ya viene prefiltrada por bbox (ver retriever). Devuelve
    la localidad cuyo límite contiene el punto, o `None` si no cae en
    ninguna (-> `JURISDICCION_NO_CUBIERTA`, lo decide quien llama)."""
    punto = Point(lon, lat)
    for localidad in localidades:
        poligono = shape(localidad.limite)
        if poligono.contains(punto) or poligono.touches(punto):
            return localidad
    return None


def calcular_distancias(
    lat: float, lon: float, zonas: list[ZonaCandidata]
) -> list[ZonaConDistancia]:
    """`zonas` ya viene prefiltrada por radio en SQL (incluye zonas de
    localidades vecinas, ver skill). Un punto dentro de la zona da 0 m."""
    if not zonas:
        return []
    punto = Point(lon, lat)
    geometrias = [shape(z.geometria) for z in zonas]
    serie = gpd.GeoSeries([punto, *geometrias], crs="EPSG:4326")
    crs_metrico = serie.estimate_utm_crs()
    serie_metrica = serie.to_crs(crs_metrico)
    punto_metrico = serie_metrica.iloc[0]

    resultados = []
    for zona, geom_metrico in zip(zonas, serie_metrica.iloc[1:], strict=True):
        distancia = punto_metrico.distance(geom_metrico)
        resultados.append(
            ZonaConDistancia(
                id=zona.id, tipo=zona.tipo, nombre=zona.nombre,
                jurisdiccion_id=zona.jurisdiccion_id, distancia_m=distancia,
            )
        )
    return resultados
