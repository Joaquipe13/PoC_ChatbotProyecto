"""Resumen del pronóstico de la franja de una aplicación agendada: de dónde viene el viento
y hacia dónde empuja la deriva, su velocidad, ráfagas, lluvia, temperatura y humedad. Y
las normas de la localidad que se refieren al viento, si el pronosticado supera su umbral,
para mencionarlas como referencia. Función pura, sin base ni red.

Es información, no un control: no dice si se puede aplicar ni cambia el dictamen (ver
DECISIONES.md, "Pronóstico del tiempo al agendar"). La dirección sigue la convención
meteorológica: "viento del norte" es el que viene del norte, y empuja hacia el sur.
"""

import math

from fitosanitarios.servicios.meteorologia import HoraPronostico

_PUNTOS = ["norte", "noreste", "este", "sureste", "sur", "suroeste", "oeste", "noroeste"]


def punto_cardinal(grados: float) -> str:
    return _PUNTOS[round((grados % 360) / 45) % 8]


def _direccion_media(horas: list[HoraPronostico]) -> float | None:
    """Promedio de las direcciones, pesado por la velocidad: el promedio de 350° y 10° es
    0° (norte), no 180°."""
    x = y = 0.0
    for h in horas:
        if h.direccion_grados is None or not h.viento_kmh:
            continue
        x += h.viento_kmh * math.sin(math.radians(h.direccion_grados))
        y += h.viento_kmh * math.cos(math.radians(h.direccion_grados))
    if x == 0 and y == 0:
        return None
    return math.degrees(math.atan2(x, y)) % 360


def _valores(horas: list[HoraPronostico], campo: str) -> list[float]:
    return [v for h in horas if (v := getattr(h, campo)) is not None]


def resumen_pronostico(
    horas: list[HoraPronostico], reglas_viento: list[dict]
) -> dict | None:
    """`None` si no hay horas de pronóstico para la franja."""
    if not horas:
        return None
    viento = _valores(horas, "viento_kmh")
    rafagas = _valores(horas, "rafagas_kmh")
    lluvia = _valores(horas, "lluvia_mm")
    probabilidad = _valores(horas, "lluvia_probabilidad")
    temperatura = _valores(horas, "temperatura")
    humedad = _valores(horas, "humedad")
    direccion = _direccion_media(horas)
    viento_max = max(viento) if viento else None
    return {
        "desde": horas[0].hora.strftime("%H:%M"),
        "hasta": horas[-1].hora.strftime("%H:%M"),
        "viene_de": punto_cardinal(direccion) if direccion is not None else None,
        "empuja_hacia": punto_cardinal(direccion + 180) if direccion is not None else None,
        "viento_min_kmh": min(viento) if viento else None,
        "viento_max_kmh": viento_max,
        "rafagas_max_kmh": max(rafagas) if rafagas else None,
        "lluvia_mm": round(sum(lluvia), 1) if lluvia else None,
        "lluvia_probabilidad_max": max(probabilidad) if probabilidad else None,
        "temperatura_min": min(temperatura) if temperatura else None,
        "temperatura_max": max(temperatura) if temperatura else None,
        "humedad_min": min(humedad) if humedad else None,
        # Solo las normas cuyo umbral supera el viento pronosticado: se mencionan como
        # referencia, sin decidir nada.
        "normas": [
            r for r in reglas_viento
            if viento_max is not None and viento_max > r["viento_max_kmh"]
        ],
    }
