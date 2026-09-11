from fitosanitarios.dominio.modelos import (
    Cita,
    Dictamen,
    Observacion,
    Receta,
    RecetaItem,
    RespuestaAgente,
    ResultadoTool,
    TipoAplicacion,
)
from fitosanitarios.dominio.motivos import MotivoNoResuelto

# --- Cita ---


def test_cita_minima_con_solo_los_campos_requeridos():
    cita = Cita(fuente="normativa")
    assert cita.norma is None
    assert cita.articulo is None
    data = cita.model_dump()
    assert data["fuente"] == "normativa"
    assert data["norma"] is None


def test_cita_completa_round_trip():
    cita = Cita(
        fuente="senasa",
        jurisdiccion_id=None,
        registro_senasa="12345",
        documento="detalle API",
    )
    restaurada = Cita.model_validate(cita.model_dump())
    assert restaurada == cita


# --- CampoFaltante: opciones=None vs [] son semánticamente distintos ---


def test_campo_faltante_opciones_none_no_es_lista_vacia():
    from fitosanitarios.dominio.modelos import CampoFaltante

    sin_opciones = CampoFaltante(
        campo="ubicacion_lote",
        motivo="no informada",
        pregunta_sugerida="Mandá la ubicación del lote",
        tipo_entrada="ubicacion",
    )
    con_opciones_vacias = CampoFaltante(
        campo="tipo_aplicacion",
        motivo="no informado",
        pregunta_sugerida="Elegí una opción",
        tipo_entrada="botones",
        opciones=[],
    )
    assert sin_opciones.opciones is None
    assert con_opciones_vacias.opciones == []
    assert sin_opciones.opciones != con_opciones_vacias.opciones


# --- ResultadoTool: estados esperables, datos=None con no_resuelto ---


def test_resultado_tool_no_resuelto_sin_datos_serializa_igual():
    resultado = ResultadoTool(
        estado="no_resuelto",
        datos=None,
        motivo=MotivoNoResuelto.JURISDICCION_NO_CUBIERTA,
    )
    data = resultado.model_dump()
    assert data["estado"] == "no_resuelto"
    assert data["datos"] is None
    assert data["motivo"] == "jurisdiccion_no_cubierta"
    restaurado = ResultadoTool.model_validate(data)
    assert restaurado == resultado


def test_resultado_tool_ok_con_datos_arbitrarios():
    resultado = ResultadoTool(estado="ok", datos={"registro": "12345", "banda": "IV"})
    restaurado = ResultadoTool.model_validate(resultado.model_dump())
    assert restaurado.datos == {"registro": "12345", "banda": "IV"}


def test_resultado_tool_defaults_de_listas_no_se_comparten_entre_instancias():
    a = ResultadoTool(estado="ok")
    b = ResultadoTool(estado="ok")
    a.advertencias.append("algo")
    assert b.advertencias == []


# --- RespuestaAgente ---


def test_respuesta_agente_repregunta_sin_tools_lleva_faltantes():
    from fitosanitarios.dominio.modelos import CampoFaltante

    respuesta = RespuestaAgente(
        tipo="repregunta",
        faltantes=[
            CampoFaltante(
                campo="tipo_aplicacion",
                motivo="no informado",
                pregunta_sugerida="Elegí una opción",
                tipo_entrada="botones",
                opciones=["Terrestre", "Aérea"],
            )
        ],
    )
    assert respuesta.tipo == "repregunta"
    assert len(respuesta.faltantes) == 1
    assert respuesta.faltantes[0].opciones == ["Terrestre", "Aérea"]


def test_respuesta_agente_fuera_de_dominio_sin_faltantes():
    respuesta = RespuestaAgente(tipo="fuera_de_dominio", intro="Solo puedo ayudarte con...")
    assert respuesta.faltantes == []
    restaurada = RespuestaAgente.model_validate(respuesta.model_dump())
    assert restaurada == respuesta


# --- Receta / RecetaItem / Dictamen ---


def test_receta_default_es_borrador_sin_items():
    receta = Receta()
    assert receta.estado.value == "borrador"
    assert receta.items == []
    assert receta.confianza_por_campo == {}


def test_receta_con_items_y_confianza_round_trip():
    receta = Receta(
        numero="0042",
        cultivo="soja",
        lote="4",
        items=[
            RecetaItem(producto_nombre="Glifosato Full 48 SL", dosis_declarada="2 L/ha"),
        ],
        superficie_ha=35,
        tipo_aplicacion=TipoAplicacion.TERRESTRE,
        confianza_por_campo={"tipo_aplicacion": 0.4},
    )
    restaurada = Receta.model_validate(receta.model_dump())
    assert restaurada == receta
    assert restaurada.items[0].producto_id is None


def test_dictamen_observada_con_citas():
    dictamen = Dictamen(
        resultado="OBSERVADA",
        observaciones=[
            Observacion(
                descripcion="Distancia a escuela insuficiente: 80 m, mínimo 100 m.",
                citas=[Cita(fuente="normativa", norma="Ordenanza 914/2018", articulo="8")],
            )
        ],
        chequeos_no_realizados=[],
    )
    assert dictamen.resultado == "OBSERVADA"
    assert len(dictamen.observaciones) == 1
    assert dictamen.observaciones[0].citas[0].articulo == "8"


def test_dictamen_no_evaluable_lista_chequeos_no_realizados():
    dictamen = Dictamen(
        resultado="NO_EVALUABLE",
        chequeos_no_realizados=["dosis: sin usos registrados para el producto"],
    )
    assert dictamen.observaciones == []
    assert "sin usos registrados" in dictamen.chequeos_no_realizados[0]
