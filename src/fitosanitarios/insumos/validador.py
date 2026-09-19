"""Validador del contrato de insumos manuales (ver docs/contrato-insumos.md).

Dos niveles: errores que bloquean la carga de esa localidad/norma (no se
insertan datos parciales o inconsistentes) y advertencias que no bloquean.
No valida contenido semántico de las reglas contra la base ya cargada --
eso lo hace `loader_reglas.py` al resolver las FK, con sus propios errores
de "norma citada no encontrada en la base".
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd
import pdfplumber
from shapely.geometry import shape
from shapely.validation import explain_validity

from fitosanitarios.config import get_settings
from fitosanitarios.insumos.estructura import (
    carpeta_nacional,
    carpetas_localidad,
    carpetas_provincia,
)

NOMBRE_CARPETA_VALIDO = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
NOMBRE_PDF_VALIDO = re.compile(r"^(ordenanza|decreto|resolucion|ley)-[a-z0-9]+-\d{4}\.pdf$")
TIPOS_ZONA_PROTEGIDA = {"escuela", "curso_agua", "zona_urbana", "otro"}
TIPOS_FEATURE_CONOCIDOS = TIPOS_ZONA_PROTEGIDA | {"limite"}

# Bounding box aproximado de Argentina (continental + insular), EPSG:4326.
ARGENTINA_MIN_LON, ARGENTINA_MIN_LAT = -73.6, -55.1
ARGENTINA_MAX_LON, ARGENTINA_MAX_LAT = -53.6, -21.7


@dataclass
class ErrorValidacion:
    codigo: str
    ruta: str
    mensaje: str


@dataclass
class AdvertenciaValidacion:
    codigo: str
    ruta: str
    mensaje: str


@dataclass
class ResultadoValidacion:
    errores: list[ErrorValidacion] = field(default_factory=list)
    advertencias: list[AdvertenciaValidacion] = field(default_factory=list)

    @property
    def es_valido(self) -> bool:
        return not self.errores

    def extend(self, otro: "ResultadoValidacion") -> None:
        self.errores.extend(otro.errores)
        self.advertencias.extend(otro.advertencias)


def _en_argentina(geom) -> bool:
    min_lon, min_lat, max_lon, max_lat = geom.bounds
    return (
        max_lon >= ARGENTINA_MIN_LON
        and min_lon <= ARGENTINA_MAX_LON
        and max_lat >= ARGENTINA_MIN_LAT
        and min_lat <= ARGENTINA_MAX_LAT
    )


def validar_geojson(ruta: Path, radio_busqueda_m: float | None = None) -> ResultadoValidacion:
    import json

    resultado = ResultadoValidacion()
    with ruta.open(encoding="utf-8") as f:
        data = json.load(f)

    features = data.get("features", [])
    limites = [f for f in features if f.get("properties", {}).get("tipo") == "limite"]
    if len(limites) != 1:
        resultado.errores.append(
            ErrorValidacion(
                "F2", str(ruta),
                f"se esperaba exactamente 1 feature con tipo=limite, hay {len(limites)}",
            )
        )

    geom_limite = None
    geoms_zonas = []
    for feature in features:
        tipo = feature.get("properties", {}).get("tipo")
        if tipo not in TIPOS_FEATURE_CONOCIDOS:
            resultado.errores.append(
                ErrorValidacion("F3", str(ruta), f"tipo de feature desconocido: {tipo!r}")
            )
            continue

        geom = shape(feature["geometry"])
        if not geom.is_valid:
            resultado.errores.append(
                ErrorValidacion(
                    "F4", str(ruta),
                    f"geometría inválida (tipo={tipo}): {explain_validity(geom)}",
                )
            )
            continue
        if not _en_argentina(geom):
            resultado.errores.append(
                ErrorValidacion(
                    "F4", str(ruta), f"geometría (tipo={tipo}) fuera del bbox de Argentina"
                )
            )
            continue

        if tipo == "limite" and len(limites) == 1:
            geom_limite = geom
        elif tipo != "limite":
            nombre = feature.get("properties", {}).get("nombre", "(sin nombre)")
            geoms_zonas.append((nombre, geom))

    if geom_limite is not None and geoms_zonas:
        radio = radio_busqueda_m
        if radio is None:
            radio = get_settings().radio_busqueda_zonas_m
        serie = gpd.GeoSeries([geom_limite, *[g for _, g in geoms_zonas]], crs="EPSG:4326")
        crs_metrico = serie.estimate_utm_crs()
        serie_metrica = serie.to_crs(crs_metrico)
        limite_metrico = serie_metrica.iloc[0]
        for (nombre, _), geom_metrico in zip(geoms_zonas, serie_metrica.iloc[1:], strict=True):
            distancia = geom_metrico.distance(limite_metrico)
            if distancia > radio:
                resultado.advertencias.append(
                    AdvertenciaValidacion(
                        "A2", str(ruta),
                        f"la zona '{nombre}' está a {distancia:.0f} m del límite de su "
                        f"localidad, más que RADIO_BUSQUEDA_ZONAS_M ({radio:.0f} m)",
                    )
                )

    return resultado


def validar_reglas_csv(ruta_csv: Path, pdfs_disponibles: set[str]) -> ResultadoValidacion:
    import csv

    resultado = ResultadoValidacion()
    with ruta_csv.open(encoding="utf-8") as f:
        lector = csv.DictReader(f)
        for i, fila in enumerate(lector, start=2):  # fila 1 = encabezado
            norma = (fila.get("norma") or "").strip()
            if norma and norma not in pdfs_disponibles:
                resultado.errores.append(
                    ErrorValidacion(
                        "F5", str(ruta_csv),
                        f"fila {i}: cita la norma '{norma}', que no está en la misma carpeta",
                    )
                )
    return resultado


def validar_nombre_carpeta(nombre: str, ruta: Path) -> ResultadoValidacion:
    resultado = ResultadoValidacion()
    if not NOMBRE_CARPETA_VALIDO.match(nombre):
        resultado.errores.append(
            ErrorValidacion(
                "F6", str(ruta),
                f"nombre de carpeta '{nombre}' no respeta la convención "
                "(minúsculas, sin tildes, separado por guiones)",
            )
        )
    return resultado


def validar_nombre_pdf(ruta_pdf: Path) -> ResultadoValidacion:
    resultado = ResultadoValidacion()
    if not NOMBRE_PDF_VALIDO.match(ruta_pdf.name):
        resultado.errores.append(
            ErrorValidacion(
                "F6", str(ruta_pdf),
                f"nombre de PDF '{ruta_pdf.name}' no respeta la convención "
                "<tipo>-<numero>-<anio>.pdf",
            )
        )
    return resultado


def pdf_tiene_texto(ruta_pdf: Path) -> bool:
    with pdfplumber.open(ruta_pdf) as pdf:
        return any((pagina.extract_text() or "").strip() for pagina in pdf.pages)


def validar_carpeta_localidad(ruta: Path) -> ResultadoValidacion:
    """Valida una carpeta de `data/insumos/<provincia>/<jurisdiccion_id>/`."""
    resultado = ResultadoValidacion()
    resultado.extend(validar_nombre_carpeta(ruta.name, ruta))

    geojson = ruta / "localidad.geojson"
    reglas_csv = ruta / "reglas.csv"
    pdfs = sorted(ruta.glob("*.pdf"))

    if not geojson.exists():
        resultado.errores.append(ErrorValidacion("F1", str(ruta), "falta localidad.geojson"))
    if not pdfs:
        resultado.errores.append(ErrorValidacion("F1", str(ruta), "falta al menos un PDF de norma"))
    if not reglas_csv.exists():
        resultado.errores.append(ErrorValidacion("F1", str(ruta), "falta reglas.csv"))

    if geojson.exists():
        resultado.extend(validar_geojson(geojson))
    for pdf in pdfs:
        resultado.extend(validar_nombre_pdf(pdf))
        if not pdf_tiene_texto(pdf):
            resultado.advertencias.append(
                AdvertenciaValidacion(
                    "A3", str(pdf), "el PDF no tiene texto extraíble, requiere OCR"
                )
            )
    if reglas_csv.exists():
        nombres_pdf = {p.stem for p in pdfs}
        resultado.extend(validar_reglas_csv(reglas_csv, nombres_pdf))

    return resultado


def validar_carpeta_normativa_general(ruta: Path) -> ResultadoValidacion:
    """Valida la carpeta de una provincia (`data/insumos/<provincia>/`, sus
    propios PDFs; las subcarpetas de localidad se validan aparte) o
    `normativa-general/nacional/`. Mismo contrato que una localidad, salvo
    que `reglas.csv` es opcional."""
    resultado = ResultadoValidacion()
    pdfs = sorted(ruta.glob("*.pdf"))
    if not pdfs:
        resultado.errores.append(ErrorValidacion("F1", str(ruta), "falta al menos un PDF de norma"))

    for pdf in pdfs:
        resultado.extend(validar_nombre_pdf(pdf))
        if not pdf_tiene_texto(pdf):
            resultado.advertencias.append(
                AdvertenciaValidacion(
                    "A3", str(pdf), "el PDF no tiene texto extraíble, requiere OCR"
                )
            )

    reglas_csv = ruta / "reglas.csv"
    if reglas_csv.exists():
        nombres_pdf = {p.stem for p in pdfs}
        resultado.extend(validar_reglas_csv(reglas_csv, nombres_pdf))

    return resultado


def es_clave_de_localidad(clave: str) -> bool:
    """Claves de `validar_insumos`: `<provincia>/<localidad>`, `<provincia>`
    (normativa provincial) y `normativa-general/nacional`."""
    return "/" in clave and not clave.startswith("normativa-general/")


def validar_insumos(data_dir: Path) -> dict[str, ResultadoValidacion]:
    """Valida todo `data/insumos/`. Devuelve un resultado por carpeta (clave =
    ruta relativa), para poder reportar y decidir qué localidades/normas
    entran y cuáles no, en vez de todo-o-nada."""
    resultados: dict[str, ResultadoValidacion] = {}

    for provincia_dir in carpetas_provincia(data_dir):
        provincia = provincia_dir.name
        resultado_provincial = validar_carpeta_normativa_general(provincia_dir)
        resultado_provincial.extend(validar_nombre_carpeta(provincia, provincia_dir))
        resultados[provincia] = resultado_provincial

        for carpeta in carpetas_localidad(provincia_dir):
            resultado = validar_carpeta_localidad(carpeta)
            geojson = carpeta / "localidad.geojson"
            if geojson.exists() and resultado.es_valido:
                provincia_del_limite = _provincia_del_limite(geojson)
                if provincia_del_limite and provincia_del_limite != provincia:
                    resultado.errores.append(
                        ErrorValidacion(
                            "F7", str(geojson),
                            f"la provincia '{provincia_del_limite}' del límite no coincide con "
                            f"la carpeta de la provincia donde está la localidad ('{provincia}')",
                        )
                    )
            resultados[f"{provincia}/{carpeta.name}"] = resultado

    nacional_dir = carpeta_nacional(data_dir)
    if nacional_dir.exists():
        resultados["normativa-general/nacional"] = validar_carpeta_normativa_general(nacional_dir)

    return resultados


def _provincia_del_limite(ruta_geojson: Path) -> str | None:
    import json

    with ruta_geojson.open(encoding="utf-8") as f:
        data = json.load(f)
    for feature in data.get("features", []):
        if feature.get("properties", {}).get("tipo") == "limite":
            return feature["properties"].get("provincia")
    return None
