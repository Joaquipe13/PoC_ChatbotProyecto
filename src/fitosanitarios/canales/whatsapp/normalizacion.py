"""Normalización del número argentino (ver skill, "Canal WhatsApp: gotchas"):
el `from` de un mensaje entrante llega como `549XXXXXXXXXX`, pero enviar a ese
mismo formato en modo desarrollo (número de prueba) falla con el error 131030
de la Graph API -- hay que enviar a `54XXXXXXXXXX`, sin el "9".

Se normaliza en un único punto: `numero_canonico` (para el `thread_id`, así
`549...` y `54...` del mismo abonado caen en el mismo hilo de conversación) y
`numero_para_envio` (para el destinatario del mensaje saliente, según
`WHATSAPP_AR_QUITAR_9`). Números que no matchean el patrón argentino de
celular (54 9 + 10 dígitos) se devuelven sin tocar -- no es un error, solo no
aplica la normalización (ver plan, "casos borde").
"""

_PREFIJO_AR_MOVIL = "549"
_PREFIJO_AR = "54"
_LARGO_CON_9 = 13
_LARGO_SIN_9 = 12


def numero_canonico(numero: str) -> str:
    """Forma canónica de un número para usar como `thread_id`: siempre sin
    el "9" argentino, para que ambas variantes del mismo abonado matcheen."""
    numero = numero.strip()
    if numero.startswith(_PREFIJO_AR_MOVIL) and len(numero) == _LARGO_CON_9:
        return _PREFIJO_AR + numero[len(_PREFIJO_AR_MOVIL) :]
    return numero


def numero_para_envio(thread_id: str, quitar_9: bool) -> str:
    """`thread_id` ya viene en forma canónica (ver `numero_canonico`). Si
    `quitar_9` es `False`, se reinserta el "9" para el envío (número real,
    fuera del modo desarrollo del número de prueba)."""
    if quitar_9:
        return thread_id
    if thread_id.startswith(_PREFIJO_AR) and len(thread_id) == _LARGO_SIN_9:
        return _PREFIJO_AR_MOVIL + thread_id[len(_PREFIJO_AR) :]
    return thread_id
