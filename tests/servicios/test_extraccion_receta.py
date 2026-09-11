import json

from fitosanitarios.llm.fake import ClienteLLMFake
from fitosanitarios.servicios.extraccion_receta import (
    ProductoExtraidoLLM,
    RecetaExtraidaLLM,
    convertir_a_receta_y_faltantes,
    extraer_receta_de_imagen,
)


def _extraccion_completa() -> RecetaExtraidaLLM:
    return RecetaExtraidaLLM(
        legible=True,
        numero="0042",
        cultivo="Soja",
        confianza_cultivo=0.95,
        lote="4",
        confianza_lote=0.9,
        adversidad="Malezas de hoja ancha",
        confianza_adversidad=0.9,
        productos=[
            ProductoExtraidoLLM(
                producto_nombre="Glifosato 48%", dosis_declarada="2 L/ha", confianza=0.9
            )
        ],
        superficie_ha=35.0,
        confianza_superficie_ha=0.9,
        tipo_aplicacion="terrestre",
        confianza_tipo_aplicacion=0.9,
    )


# --- convertir_a_receta_y_faltantes ---


def test_conversion_con_todos_los_campos_altos_no_tiene_faltantes():
    receta, faltantes = convertir_a_receta_y_faltantes(_extraccion_completa())
    assert faltantes == []
    assert receta.cultivo == "Soja"
    assert receta.adversidad == "Malezas de hoja ancha"
    assert len(receta.items) == 1
    assert receta.items[0].producto_nombre == "Glifosato 48%"


def test_conversion_campo_con_baja_confianza_va_a_faltantes():
    extraccion = _extraccion_completa()
    extraccion.tipo_aplicacion = None
    extraccion.confianza_tipo_aplicacion = 0.0

    receta, faltantes = convertir_a_receta_y_faltantes(extraccion)

    assert receta.tipo_aplicacion is None
    campos_faltantes = {f.campo for f in faltantes}
    assert "tipo_aplicacion" in campos_faltantes
    faltante = next(f for f in faltantes if f.campo == "tipo_aplicacion")
    assert faltante.tipo_entrada == "botones"
    assert faltante.opciones == ["Terrestre", "Aérea"]


def test_conversion_valor_presente_pero_confianza_baja_tambien_es_faltante():
    extraccion = _extraccion_completa()
    extraccion.cultivo = "algo dudoso"
    extraccion.confianza_cultivo = 0.2  # por debajo del umbral

    receta, faltantes = convertir_a_receta_y_faltantes(extraccion)

    assert receta.cultivo is None
    assert any(f.campo == "cultivo" for f in faltantes)


def test_conversion_sin_productos_por_encima_del_umbral():
    extraccion = _extraccion_completa()
    extraccion.productos = [
        ProductoExtraidoLLM(producto_nombre="algo", dosis_declarada=None, confianza=0.1)
    ]

    receta, faltantes = convertir_a_receta_y_faltantes(extraccion)

    assert receta.items == []
    assert any(f.campo == "productos" for f in faltantes)


def test_conversion_umbral_configurable():
    extraccion = _extraccion_completa()
    extraccion.confianza_lote = 0.5  # por debajo del default (0.6) pero no de uno custom

    receta, faltantes = convertir_a_receta_y_faltantes(extraccion, umbral=0.4)

    assert receta.lote == "4"
    assert not any(f.campo == "lote" for f in faltantes)


# --- extraer_receta_de_imagen ---


def test_extraer_receta_de_imagen_parsea_json_de_la_respuesta():
    respuesta = json.dumps(
        {
            "legible": True,
            "cultivo": "Maiz",
            "confianza_cultivo": 0.9,
            "productos": [],
        }
    )
    fake = ClienteLLMFake(respuestas=[respuesta])

    extraccion = extraer_receta_de_imagen(b"imagen-fake", fake)

    assert extraccion.legible is True
    assert extraccion.cultivo == "Maiz"


def test_extraer_receta_de_imagen_no_legible_explicito():
    fake = ClienteLLMFake(respuestas=[json.dumps({"legible": False})])
    extraccion = extraer_receta_de_imagen(b"imagen-fake", fake)
    assert extraccion.legible is False


def test_extraer_receta_de_imagen_json_invalido_se_trata_como_no_legible():
    fake = ClienteLLMFake(respuestas=["esto no es JSON"])
    extraccion = extraer_receta_de_imagen(b"imagen-fake", fake)
    assert extraccion.legible is False


def test_extraer_receta_de_imagen_tolera_markdown():
    contenido = '{"legible": true, "cultivo": "Trigo", "confianza_cultivo": 0.8}'
    fake = ClienteLLMFake(respuestas=[f"```json\n{contenido}\n```"])
    extraccion = extraer_receta_de_imagen(b"imagen-fake", fake)
    assert extraccion.legible is True
    assert extraccion.cultivo == "Trigo"


def test_extraer_receta_de_imagen_usa_cache_por_hash():
    respuesta = json.dumps({"legible": True, "cultivo": "Soja", "confianza_cultivo": 0.9})
    fake = ClienteLLMFake(respuestas=[respuesta, "NO DEBERIA LLAMARSE DE NUEVO"])
    cache: dict[str, str] = {}

    imagen = b"misma-imagen"
    primera = extraer_receta_de_imagen(imagen, fake, cache=cache)
    segunda = extraer_receta_de_imagen(imagen, fake, cache=cache)

    assert primera.cultivo == segunda.cultivo == "Soja"
    assert len(fake.llamadas) == 1  # la segunda vino de la cache, no del LLM


def test_extraer_receta_de_imagen_distintas_imagenes_no_comparten_cache():
    fake = ClienteLLMFake(
        respuestas=[
            json.dumps({"legible": True, "cultivo": "Soja", "confianza_cultivo": 0.9}),
            json.dumps({"legible": True, "cultivo": "Maiz", "confianza_cultivo": 0.9}),
        ]
    )
    cache: dict[str, str] = {}

    a = extraer_receta_de_imagen(b"imagen-a", fake, cache=cache)
    b = extraer_receta_de_imagen(b"imagen-b", fake, cache=cache)

    assert a.cultivo == "Soja"
    assert b.cultivo == "Maiz"
    assert len(fake.llamadas) == 2
