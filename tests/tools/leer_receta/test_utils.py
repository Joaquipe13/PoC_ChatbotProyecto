import json

from fitosanitarios.llm.fake import ClienteLLMFake
from fitosanitarios.tools.leer_receta.utils import (
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
        productos=[
            ProductoExtraidoLLM(
                producto_nombre="Glifosato 48%", dosis_declarada="2 L/ha", confianza=0.9
            )
        ],
        superficie_ha=35.0,
        confianza_superficie_ha=0.9,
        tipo_aplicacion="terrestre",
        localidad="El Trébol",
        caudal="100 L/ha",
        ubic_poblado="a 500 m del pueblo",
        condiciones="sin viento",
        restricciones="no aplicar a menos de 100 m de cursos de agua",
        observaciones="aplicar por la mañana",
        fecha_emision="2026-09-01",
        validez_dias=30,
    )


# --- convertir_a_receta_y_faltantes ---


def test_conversion_con_todos_los_campos_altos_no_tiene_faltantes():
    receta, faltantes = convertir_a_receta_y_faltantes(_extraccion_completa())
    assert faltantes == []
    assert receta.cultivo == "Soja"
    assert receta.adversidad == "Malezas de hoja ancha"
    assert len(receta.items) == 1
    assert receta.items[0].producto_nombre == "Glifosato 48%"


def test_conversion_incluye_los_campos_descriptivos_nuevos():
    receta, _ = convertir_a_receta_y_faltantes(_extraccion_completa())
    assert receta.tipo_aplicacion == "terrestre"
    assert receta.caudal == "100 L/ha"
    assert receta.ubic_poblado == "a 500 m del pueblo"
    assert receta.condiciones == "sin viento"
    assert receta.restricciones == "no aplicar a menos de 100 m de cursos de agua"
    assert receta.observaciones == "aplicar por la mañana"
    assert receta.fecha_emision.isoformat() == "2026-09-01"
    assert receta.validez_dias == 30


def test_conversion_campos_descriptivos_ausentes_no_generan_faltantes():
    """Son descriptivos (ver DECISIONES.md): si el LLM no los leyó, la receta
    se arma igual con el resto -- nunca bloquean con una repregunta."""
    extraccion = _extraccion_completa()
    extraccion.adversidad = None
    extraccion.caudal = None
    extraccion.ubic_poblado = None
    extraccion.condiciones = None
    extraccion.restricciones = None
    extraccion.observaciones = None
    extraccion.fecha_emision = None
    extraccion.validez_dias = None

    receta, faltantes = convertir_a_receta_y_faltantes(extraccion)

    assert faltantes == []
    assert receta.adversidad is None
    assert receta.caudal is None
    assert receta.fecha_emision is None


def test_conversion_adversidad_ausente_no_es_faltante():
    """Regresión: la plaga/adversidad general es opcional (el usuario lo
    marcó explícitamente); no debe generar CampoFaltante ni bloquear la
    receta aunque el LLM no la haya leído (ver DIFICULTADES.md)."""
    extraccion = _extraccion_completa()
    extraccion.adversidad = None

    _, faltantes = convertir_a_receta_y_faltantes(extraccion)

    assert not any(f.campo == "adversidad" for f in faltantes)


def test_conversion_fecha_emision_no_parseable_se_descarta_sin_romper():
    extraccion = _extraccion_completa()
    extraccion.fecha_emision = "hace un mes"

    receta, faltantes = convertir_a_receta_y_faltantes(extraccion)

    assert receta.fecha_emision is None
    assert faltantes == []


def test_conversion_pasa_principio_activo_y_clase_toxicologica_por_item():
    extraccion = _extraccion_completa()
    extraccion.productos = [
        ProductoExtraidoLLM(
            producto_nombre="Glifosato 48%",
            dosis_declarada="2 L/ha",
            confianza=0.9,
            adversidad="Yuyo colorado",
            principio_activo="Glifosato",
            clase_toxicologica="IV",
        )
    ]

    receta, _ = convertir_a_receta_y_faltantes(extraccion)

    item = receta.items[0]
    assert item.adversidad == "Yuyo colorado"
    assert item.principio_activo == "Glifosato"
    assert item.clase_toxicologica == "IV"


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


def test_conversion_localidad_tipo_de_aplicacion_y_dosis_ausentes_son_faltantes():
    """Sin estos datos no se puede evaluar: se preguntan antes de confirmar (pedido del
    usuario, 23/09/2026)."""
    extraccion = _extraccion_completa()
    extraccion.localidad = None
    extraccion.tipo_aplicacion = None
    extraccion.productos[0].dosis_declarada = None

    _, faltantes = convertir_a_receta_y_faltantes(extraccion)

    assert [(f.campo, f.pregunta_sugerida) for f in faltantes] == [
        ("localidad", "¿En qué localidad se aplica?"),
        ("tipo_aplicacion", "¿Es aplicación terrestre o aérea?"),
        ("dosis", "¿Qué dosis de Glifosato 48% indica la receta?"),
    ]


def test_conversion_normaliza_el_tipo_de_aplicacion():
    extraccion = _extraccion_completa()
    extraccion.tipo_aplicacion = "Aérea"
    receta, _ = convertir_a_receta_y_faltantes(extraccion)
    assert receta.tipo_aplicacion == "aerea"
