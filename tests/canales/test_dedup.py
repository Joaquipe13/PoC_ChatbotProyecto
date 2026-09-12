"""Test de integración contra Postgres real (Docker) de la deduplicación de
mensajes de WhatsApp por `message.id`.

`message_id` único por corrida (`uuid4`), no un string fijo: la fila que
inserta `ya_procesado` queda en `operacion.mensaje_whatsapp` para siempre
(no hay rollback de transacción entre tests, es una tabla real). Con un
string fijo, la segunda corrida de la suite completa contra la misma base
encuentra el `message_id` ya procesado por la corrida anterior y el test
falla -- se detectó así, corriendo `pytest -q` dos veces seguidas (ver
DIFICULTADES.md, Fase 8)."""

import uuid

from fitosanitarios.canales.whatsapp.dedup import ya_procesado


def _message_id() -> str:
    return f"wamid.test-{uuid.uuid4()}"


def test_primer_mensaje_no_esta_procesado(conexion):
    assert ya_procesado(conexion, _message_id()) is False


def test_mismo_message_id_dos_veces_se_detecta(conexion):
    message_id = _message_id()
    assert ya_procesado(conexion, message_id) is False
    assert ya_procesado(conexion, message_id) is True
