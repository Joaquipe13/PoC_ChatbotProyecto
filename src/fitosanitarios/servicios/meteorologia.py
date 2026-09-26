"""Pronóstico del tiempo para una aplicación agendada, de Open-Meteo (ver DECISIONES.md,
"Pronóstico del tiempo al agendar"). Es información para el operario: no controla ni
restringe nada.

Se pide el pronóstico hora por hora del día de la aplicación en el centro de la
localidad y se toma la franja de la hora agendada (±2 h). Las horas vienen en hora de
Argentina (`timezone`), así que se comparan sin zona horaria. Si la API falla (red,
cuota, fecha fuera de rango) se devuelve `None`: el agendado sigue igual, sin pronóstico.
"""

import logging
import time as reloj
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta

import httpx

logger = logging.getLogger(__name__)

HORAS_ALREDEDOR = 2
ZONA_HORARIA = "America/Argentina/Buenos_Aires"
_VARIABLES = (
    "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m", "precipitation",
    "precipitation_probability", "temperature_2m", "relative_humidity_2m",
)
# El mismo pronóstico se reutiliza un rato: dos turnos seguidos no piden lo mismo dos veces.
_CACHE_SEGUNDOS = 30 * 60


@dataclass
class HoraPronostico:
    hora: datetime
    viento_kmh: float | None
    direccion_grados: float | None  # de dónde viene el viento (convención meteorológica)
    rafagas_kmh: float | None
    lluvia_mm: float | None
    lluvia_probabilidad: float | None
    temperatura: float | None
    humedad: float | None

    def como_dict(self) -> dict:
        return {**asdict(self), "hora": self.hora.isoformat(timespec="minutes")}


def horas_de_la_respuesta(respuesta: dict) -> list[HoraPronostico]:
    """La respuesta de Open-Meteo (`hourly`: una lista por variable) como una lista de
    horas."""
    horario = respuesta.get("hourly") or {}
    tiempos = horario.get("time") or []

    def valor(variable: str, i: int):
        serie = horario.get(variable) or []
        return serie[i] if i < len(serie) else None

    return [
        HoraPronostico(
            hora=datetime.fromisoformat(t),
            viento_kmh=valor("wind_speed_10m", i),
            direccion_grados=valor("wind_direction_10m", i),
            rafagas_kmh=valor("wind_gusts_10m", i),
            lluvia_mm=valor("precipitation", i),
            lluvia_probabilidad=valor("precipitation_probability", i),
            temperatura=valor("temperature_2m", i),
            humedad=valor("relative_humidity_2m", i),
        )
        for i, t in enumerate(tiempos)
    ]


def franja(horas: list[HoraPronostico], momento: datetime) -> list[HoraPronostico]:
    """Las horas a ±`HORAS_ALREDEDOR` de la hora agendada."""
    margen = timedelta(hours=HORAS_ALREDEDOR)
    return [h for h in horas if momento - margen <= h.hora <= momento + margen]


class ClienteOpenMeteo:
    def __init__(self, base_url: str, timeout_s: float = 10.0) -> None:
        self._base_url = base_url
        self._timeout_s = timeout_s
        self._cache: dict[tuple, tuple[float, list[HoraPronostico]]] = {}

    def horas_del_dia(self, lat: float, lon: float, dia: date) -> list[HoraPronostico] | None:
        clave = (round(lat, 4), round(lon, 4), dia)
        guardado = self._cache.get(clave)
        if guardado is not None and reloj.monotonic() - guardado[0] < _CACHE_SEGUNDOS:
            return guardado[1]
        try:
            respuesta = httpx.get(
                self._base_url,
                params={
                    "latitude": lat, "longitude": lon, "hourly": ",".join(_VARIABLES),
                    "timezone": ZONA_HORARIA, "wind_speed_unit": "kmh",
                    "start_date": dia.isoformat(), "end_date": dia.isoformat(),
                },
                timeout=self._timeout_s,
            )
            respuesta.raise_for_status()
            horas = horas_de_la_respuesta(respuesta.json())
        except (httpx.HTTPError, ValueError):
            logger.warning("No se pudo obtener el pronóstico de Open-Meteo", exc_info=True)
            return None
        self._cache[clave] = (reloj.monotonic(), horas)
        return horas
