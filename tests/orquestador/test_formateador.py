"""Tests de snapshot de las 9 plantillas (ver docs/especificacion-plantillas.md).
"snapshot" acá es un string esperado fijo por plantilla, no una librería de
snapshot testing -- alcanza para las 9 plantillas y deja el `assert` legible."""

from fitosanitarios.dominio.modelos import CampoFaltante, Cita, RespuestaAgente, ResultadoTool
from fitosanitarios.dominio.motivos import MotivoNoResuelto
from fitosanitarios.orquestador.formateador import formatear_respuesta, partir_por_seccion


def _un_mensaje(respuesta, resultados) -> str:
    mensajes = formatear_respuesta(respuesta, resultados)
    assert len(mensajes) == 1
    return mensajes[0]


def test_confirmacion_receta():
    respuesta = RespuestaAgente(tipo="confirmacion_receta")
    resultado = ResultadoTool(
        estado="faltan_datos",
        datos={
            "numero": "0042", "cultivo": "soja", "lote": "4",
            "adversidad": "malezas de hoja ancha",
            "items": [{"producto_nombre": "Glifosato 48%", "dosis_declarada": "2 L/ha"}],
            "superficie_ha": 35, "tipo_aplicacion": None,
        },
    )
    texto = _un_mensaje(respuesta, [resultado])
    assert texto == (
        "*Leí la receta N.° 0042*. Confirmá los datos:\n"
        "- *Cultivo:* soja\n"
        "- *Lote:* 4\n"
        "- *Localidad:* no figura ⚠️\n"
        "- *Superficie:* 35 ha\n"
        "- *Adversidad:* malezas de hoja ancha\n"
        "- *Producto:* Glifosato 48% — 2 L/ha\n"
        "- *Tipo de aplicación:* no figura ⚠️\n"
        "[Confirmar] [Corregir]"
    )


def test_confirmacion_receta_cultivo_lote_y_superficie_faltantes_muestran_alerta():
    respuesta = RespuestaAgente(tipo="confirmacion_receta")
    resultado = ResultadoTool(estado="faltan_datos", datos={"items": []})
    texto = _un_mensaje(respuesta, [resultado])
    assert texto == (
        "*Leí la receta*. Confirmá los datos:\n"
        "- *Cultivo:* no figura ⚠️\n"
        "- *Lote:* no figura ⚠️\n"
        "- *Localidad:* no figura ⚠️\n"
        "- *Superficie:* no figura ⚠️\n"
        "- *Producto:* no figura ⚠️\n"
        "- *Tipo de aplicación:* no figura ⚠️\n"
        "[Confirmar] [Corregir]"
    )


def test_confirmacion_receta_con_campos_descriptivos_completos():
    """Los campos agregados el 12/09/2026 (ver DECISIONES.md) se muestran sin
    ⚠️: son descriptivos, no bloquean la confirmación si faltan."""
    respuesta = RespuestaAgente(tipo="confirmacion_receta")
    resultado = ResultadoTool(
        estado="ok",
        datos={
            "cultivo": "soja", "lote": "4", "superficie_ha": 35,
            "items": [{
                "producto_nombre": "Glifosato 48%", "dosis_declarada": "2 L/ha",
                "adversidad": "yuyo colorado", "principio_activo": "Glifosato",
                "clase_toxicologica": "IV",
            }],
            "tipo_aplicacion": "terrestre", "caudal": "100 L/ha",
            "ubic_poblado": "a 500 m del pueblo", "condiciones": "sin viento",
            "restricciones": "no aplicar cerca de cursos de agua",
            "observaciones": "aplicar por la mañana",
            "fecha_emision": "2026-09-01", "validez_dias": 30,
        },
    )
    texto = _un_mensaje(respuesta, [resultado])
    assert texto == (
        "*Leí la receta*. Confirmá los datos:\n"
        "- *Cultivo:* soja\n"
        "- *Lote:* 4\n"
        "- *Localidad:* no figura ⚠️\n"
        "- *Superficie:* 35 ha\n"
        "- *Producto:* Glifosato 48% — 2 L/ha (Glifosato · IV)\n"
        "  Plaga/maleza: yuyo colorado\n"
        "- *Tipo de aplicación:* terrestre\n"
        "- *Caudal:* 100 L/ha\n"
        "- *Ubicación respecto de zonas pobladas:* a 500 m del pueblo\n"
        "- *Condiciones de aplicación:* sin viento\n"
        "- *Restricciones:* no aplicar cerca de cursos de agua\n"
        "- *Observaciones:* aplicar por la mañana\n"
        "- *Fecha de emisión:* 2026-09-01\n"
        "- *Validez:* 30 días\n"
        "[Confirmar] [Corregir]"
    )


def test_dictamen_observada_con_citas():
    respuesta = RespuestaAgente(tipo="dictamen")
    resultado = ResultadoTool(
        estado="observado",
        datos={
            "jurisdiccion_id": "san-carlos-centro",
            "dictamen": {
                "resultado": "OBSERVADA",
                "observaciones": [
                    {"descripcion": "Distancia a escuela insuficiente: 80 m, mínimo 100 m."},
                ],
                "chequeos_no_realizados": [],
                "citas": [
                    {"fuente": "normativa", "norma": "ordenanza-914-2018", "articulo": "8",
                     "jurisdiccion_id": "san-carlos-centro"},
                ],
            },
        },
        citas=[Cita(fuente="normativa", norma="ordenanza-914-2018", articulo="8",
                    jurisdiccion_id="san-carlos-centro")],
    )
    texto = _un_mensaje(respuesta, [resultado])
    assert texto == (
        "*Dictamen* — san-carlos-centro\n"
        "*Resultado:* ❌ OBSERVADA\n\n"
        "*Observaciones*\n"
        "1. Distancia a escuela insuficiente: 80 m, mínimo 100 m.\n\n"
        "*Fuentes*\n"
        "- Ordenanza 914/2018, art. 8 (san-carlos-centro)"
    )


def test_dictamen_apta_sin_observaciones():
    respuesta = RespuestaAgente(tipo="dictamen")
    resultado = ResultadoTool(
        estado="ok",
        datos={
            "jurisdiccion_id": "san-carlos-centro",
            "dictamen": {"resultado": "APTA", "observaciones": [],
                         "chequeos_no_realizados": [], "citas": []},
        },
    )
    texto = _un_mensaje(respuesta, [resultado])
    assert "✅ APTA" in texto
    assert "Observaciones" not in texto


_NORMA_ART_7 = {"fuente": "normativa", "norma": "ordenanza-841-2010", "articulo": "7",
                "jurisdiccion_id": "el-trebol"}
_NORMA_ART_6 = {**_NORMA_ART_7, "articulo": "6"}
_SENASA = {"fuente": "senasa", "registro_senasa": "41881", "documento": "detalle API"}

_CONDICIONES_EL_TREBOL = {
    "localidad": "El Trébol", "tipo_aplicacion": "aerea", "banda": "II",
    "banda_color": "amarilla",
    "productos_por_banda": {"Producto A": "IV", "Producto B": "II"},
    "distancias_minimas": [{
        "tipo_zona": "zona_urbana", "distancia_min_m": 3000.0,
        "norma_limitante": _NORMA_ART_7, "citas": [_NORMA_ART_6, _NORMA_ART_7],
    }],
    "advertencias": [],
}


def _dictamen_el_trebol(resultado="APTA", **extra):
    return ResultadoTool(
        estado="ok",
        datos={
            "jurisdiccion_id": "el-trebol",
            "dictamen": {
                "resultado": resultado, "observaciones": [], "chequeos_no_realizados": [],
                "citas": [_SENASA, _NORMA_ART_6, _NORMA_ART_7],
                "condiciones": _CONDICIONES_EL_TREBOL, **extra,
            },
        },
    )


def test_dictamen_da_la_distancia_minima_con_la_norma_que_la_fija_y_ofrece_seguimiento():
    texto = _un_mensaje(RespuestaAgente(tipo="dictamen"), [_dictamen_el_trebol()])
    assert texto == (
        "*Dictamen* — El Trébol\n"
        "*Resultado:* ✅ APTA\n\n"
        "*Condiciones de aplicación* — El Trébol · aérea · banda II (amarilla)\n"
        "- *Distancia mínima a zona urbana:* 3000 m (Ordenanza 841/2010, art. 7)\n\n"
        "*Fuentes*\n"
        "- SENASA, Reg. 41881 (detalle API)\n"
        "- Ordenanza 841/2010, art. 6 (el-trebol)\n\n"
        "¿Querés más info (la banda de cada producto) o que agende la aplicación?"
    )


def test_dictamen_no_muestra_la_banda_de_cada_producto_hasta_que_se_pide():
    texto = _un_mensaje(RespuestaAgente(tipo="dictamen"), [_dictamen_el_trebol()])
    assert "Producto A" not in texto


def test_dictamen_observado_no_ofrece_agendar():
    texto = _un_mensaje(RespuestaAgente(tipo="dictamen"), [_dictamen_el_trebol("OBSERVADA")])
    assert texto.endswith("¿Querés más info (la banda de cada producto)?")
    assert "agende" not in texto


def test_evaluar_riesgo_suelto_muestra_condiciones_sin_veredicto():
    resultado = ResultadoTool(
        estado="ok",
        datos={"jurisdiccion_id": "el-trebol", "condiciones": _CONDICIONES_EL_TREBOL},
        citas=[Cita.model_validate(_NORMA_ART_7)],
    )
    texto = _un_mensaje(RespuestaAgente(tipo="dictamen"), [resultado])
    assert texto.startswith("*Condiciones de aplicación* — El Trébol")
    assert "Resultado" not in texto
    assert "Fuentes" not in texto  # la única norma ya está en la línea de la distancia
    assert texto.endswith("o que agende la aplicación?")


def test_detalle_bandas_lista_la_banda_de_cada_producto():
    resultado = ResultadoTool(
        estado="ok",
        datos={
            "jurisdiccion_id": "el-trebol",
            "productos": [{"nombre": "Producto B", "numero_inscripcion": "41881"}],
            "condiciones": {**_CONDICIONES_EL_TREBOL, "productos_por_banda": {
                "Producto A": "IV", "Producto B": "II", "Producto C": None,
            }},
        },
    )
    texto = _un_mensaje(RespuestaAgente(tipo="detalle_bandas"), [resultado])
    assert texto == (
        "*Banda de cada producto*\n"
        "- Producto A: IV (verde)\n"
        "- Producto B · Reg. SENASA 41881: II (amarilla)\n"
        "- Producto C: no figura en SENASA ⚠️\n"
        "La aplicación se rige por la más peligrosa: II (amarilla).\n\n"
        "*Condiciones de aplicación* — El Trébol · aérea · banda II (amarilla)\n"
        "- *Distancia mínima a zona urbana:* 3000 m (Ordenanza 841/2010, art. 7)\n\n"
        "¿Querés que agende la aplicación?"
    )


def test_detalle_bandas_sin_producto_resuelto_lo_dice_y_no_ofrece_agendar():
    """Bug real: un producto que no está en el catálogo se descartaba en
    silencio y la plantilla salía con el encabezado solo, sin banda, sin
    distancia y con la oferta de agendar."""
    resultado = ResultadoTool(
        estado="ok",
        datos={"jurisdiccion_id": None, "productos": [], "condiciones": {
            "localidad": "Maria Susana", "tipo_aplicacion": "terrestre", "banda": None,
            "productos_por_banda": {}, "distancias_minimas": [],
            "advertencias": ["No hay una distancia mínima cargada para Maria Susana"],
        }},
        chequeos_no_realizados=["Glifosato Full: no se pudo resolver contra el registro"],
    )
    texto = _un_mensaje(RespuestaAgente(tipo="detalle_bandas"), [resultado])
    assert "No pude identificar ningún producto" in texto
    assert "Glifosato Full: no se pudo resolver contra el registro" in texto
    assert "No hay una distancia mínima cargada" in texto
    assert "agende" not in texto


def test_dictamen_tras_faltan_datos_repregunta_en_vez_de_salir_vacio():
    """Bug real: el LLM eligió `dictamen` aunque la tool pidió la provincia;
    salía solo su intro ("La evaluación ha finalizado...")."""
    resultado = ResultadoTool(
        estado="faltan_datos",
        faltantes=[CampoFaltante(
            campo="provincia", motivo="la localidad no tiene normativa cargada",
            pregunta_sugerida="¿En qué provincia queda Pergamino?", tipo_entrada="texto",
        )],
    )
    respuesta = RespuestaAgente(tipo="dictamen", intro="La evaluación de la receta ha finalizado.")
    texto = _un_mensaje(respuesta, [resultado])
    assert "¿En qué provincia queda Pergamino?" in texto
    assert "ha finalizado" not in texto


def test_dictamen_y_detalle_bandas_ignoran_el_intro_del_llm():
    resultado = ResultadoTool(
        estado="ok",
        datos={"jurisdiccion_id": "el-trebol", "condiciones": _CONDICIONES_EL_TREBOL},
    )
    intro = "¿Querés ver el detalle de las bandas?"
    for tipo in ("dictamen", "detalle_bandas"):
        assert intro not in _un_mensaje(RespuestaAgente(tipo=tipo, intro=intro), [resultado])


def test_agendar_sin_fecha_pregunta_la_fecha():
    resultado = ResultadoTool(
        estado="faltan_datos",
        faltantes=[CampoFaltante(
            campo="fecha", motivo="no se indicó la fecha",
            pregunta_sugerida="¿Para qué fecha querés agendar la aplicación?",
            tipo_entrada="texto",
        )],
    )
    texto = _un_mensaje(RespuestaAgente(tipo="agendar_aplicacion"), [resultado])
    assert texto.startswith("¿Para qué fecha querés agendar la aplicación?")
    assert "martes" in texto


def test_agendar_con_fecha_muestra_la_agenda_del_dia_y_pregunta_el_horario():
    resultado = ResultadoTool(
        estado="faltan_datos",
        datos={
            "fecha": "2026-09-22", "fecha_legible": "martes 22/09/2026",
            "tareas": [{"cultivo": "soja", "lote": "4", "hora": "08:00",
                        "estado_tarea": "pendiente"}],
        },
        faltantes=[CampoFaltante(
            campo="hora", motivo="no se indicó el horario",
            pregunta_sugerida="¿En qué horario querés agendarla?", tipo_entrada="texto",
        )],
    )
    texto = _un_mensaje(RespuestaAgente(tipo="agendar_aplicacion"), [resultado])
    assert texto == (
        "*Agenda del martes 22/09/2026* (1)\n"
        "1. ⏳ 08:00 — soja — lote 4 (pendiente)\n\n"
        "¿En qué horario querés agendarla? Por ejemplo: 8:30 o 3 de la tarde."
    )


def test_agendar_dia_libre_lo_dice_y_pregunta_el_horario():
    resultado = ResultadoTool(
        estado="faltan_datos",
        datos={"fecha": "2026-09-22", "fecha_legible": "martes 22/09/2026", "tareas": []},
        faltantes=[CampoFaltante(
            campo="hora", motivo="no se indicó el horario",
            pregunta_sugerida="¿En qué horario querés agendarla?", tipo_entrada="texto",
        )],
    )
    texto = _un_mensaje(RespuestaAgente(tipo="agendar_aplicacion"), [resultado])
    assert texto.startswith("No tenés nada agendado para el martes 22/09/2026.")
    assert "¿En qué horario querés agendarla?" in texto


def test_agendar_confirmada_avisa_si_ya_hay_algo_a_esa_hora():
    resultado = ResultadoTool(
        estado="ok",
        datos={"fecha_legible": "martes 22/09/2026", "hora": "08:30",
               "cultivo": "soja", "lote": "4"},
        advertencias=["Ya tenías trigo (lote 2) agendada a las 08:30"],
    )
    texto = _un_mensaje(RespuestaAgente(tipo="agendar_aplicacion"), [resultado])
    assert texto == (
        "✅ *Aplicación agendada* — martes 22/09/2026, 08:30 hs\n"
        "- *Cultivo:* soja\n"
        "- *Lote:* 4\n"
        "⚠️ Ya tenías trigo (lote 2) agendada a las 08:30"
    )


def test_agendar_fecha_pasada_explica_y_repregunta():
    resultado = ResultadoTool(
        estado="faltan_datos",
        faltantes=[CampoFaltante(
            campo="fecha", motivo="lunes 14/09/2026 ya pasó",
            pregunta_sugerida="¿Para qué fecha querés agendar la aplicación?",
            tipo_entrada="texto",
        )],
    )
    texto = _un_mensaje(RespuestaAgente(tipo="agendar_aplicacion"), [resultado])
    assert texto.startswith("Lunes 14/09/2026 ya pasó. ¿Para qué fecha")


def test_agenda_muestra_la_hora_y_la_fecha_legible():
    resultado = ResultadoTool(
        estado="ok",
        datos={
            "fecha": "2026-09-22", "fecha_legible": "martes 22/09/2026", "total": 1,
            "tareas": [{"cultivo": "soja", "lote": "4", "hora": "08:00",
                        "estado_tarea": "pendiente"}],
        },
    )
    texto = _un_mensaje(RespuestaAgente(tipo="agenda"), [resultado])
    assert texto == "*Agenda del martes 22/09/2026* (1)\n1. ⏳ 08:00 — soja — lote 4 (pendiente)"


def test_consulta_producto_listado():
    respuesta = RespuestaAgente(tipo="consulta_producto")
    resultado = ResultadoTool(
        estado="ok",
        datos={
            "total": 1,
            "productos": [{
                "marca": "Flyer 10 Ec", "numero_inscripcion": "41881",
                "banda_toxicologica": "II",
                "dosis": {"texto_original": "160-180 cm3/ha"},
            }],
        },
        citas=[Cita(fuente="senasa", documento="vademécum")],
    )
    texto = _un_mensaje(respuesta, [resultado])
    assert "*Productos registrados* (1 de 1)" in texto
    assert "Flyer 10 Ec" in texto
    assert "Banda II" in texto
    assert "160-180 cm3/ha" in texto
    assert "*Fuentes*" not in texto


def test_consulta_producto_puntual():
    respuesta = RespuestaAgente(tipo="consulta_producto")
    resultado = ResultadoTool(
        estado="ok",
        datos={
            "producto": "Flyer 10 Ec", "numero_inscripcion": "41881",
            "banda_toxicologica": "II", "cultivo_autorizado": True,
            "usos_registrados": [
                {"cultivo": "soja", "dosis": {"texto_original": "160-180 cm3/ha"}}
            ],
        },
        citas=[Cita(fuente="senasa", registro_senasa="41881", documento="detalle API")],
    )
    texto = _un_mensaje(respuesta, [resultado])
    assert texto == (
        "*Flyer 10 Ec* · Reg. SENASA 41881 · Banda II · ✅ autorizado\n"
        "Dosis registrada: 160-180 cm3/ha"
    )
    assert "*Fuentes*" not in texto


def test_consulta_producto_puntual_sin_dosis_registrada():
    respuesta = RespuestaAgente(tipo="consulta_producto")
    resultado = ResultadoTool(
        estado="ok",
        datos={
            "producto": "Flyer 10 Ec", "numero_inscripcion": "41881",
            "banda_toxicologica": "II", "cultivo_autorizado": True,
        },
    )
    texto = _un_mensaje(respuesta, [resultado])
    assert texto == "*Flyer 10 Ec* · Reg. SENASA 41881 · Banda II · ✅ autorizado"


def test_consulta_producto_ignora_el_intro_del_llm():
    respuesta = RespuestaAgente(tipo="consulta_producto", intro="Acá tenés el resultado:")
    resultado = ResultadoTool(
        estado="ok",
        datos={
            "producto": "Flyer 10 Ec", "numero_inscripcion": "41881",
            "banda_toxicologica": "II",
        },
    )
    texto = _un_mensaje(respuesta, [resultado])
    assert "Acá tenés" not in texto


def test_consulta_normativa():
    respuesta = RespuestaAgente(tipo="consulta_normativa")
    resultado = ResultadoTool(
        estado="ok",
        datos={"veredicto": "No", "regla": "La distancia mínima es de 100 metros."},
        citas=[Cita(fuente="normativa", norma="ordenanza-914-2018", articulo="8",
                    jurisdiccion_id="san-carlos-centro")],
    )
    texto = _un_mensaje(respuesta, [resultado])
    assert texto == (
        "*No.* La distancia mínima es de 100 metros.\n\n"
        "*Fuentes*\n"
        "- Ordenanza 914/2018, art. 8 (san-carlos-centro)"
    )


def test_repregunta_agrupada_hasta_3():
    respuesta = RespuestaAgente(
        tipo="repregunta",
        faltantes=[
            CampoFaltante(campo="ubicacion_lote", motivo="no informada",
                          pregunta_sugerida="Mandá la ubicación del lote",
                          tipo_entrada="ubicacion"),
            CampoFaltante(campo="tipo_aplicacion", motivo="no informado",
                          pregunta_sugerida="Elegí una opción", tipo_entrada="botones",
                          opciones=["Terrestre", "Aérea"]),
        ],
    )
    texto = _un_mensaje(respuesta, [])
    assert texto == (
        "1. Mandá la ubicación del lote\n"
        "2. Elegí una opción\n"
        "[Terrestre] [Aérea]"
    )


def test_fuera_de_dominio_es_texto_fijo():
    respuesta = RespuestaAgente(tipo="fuera_de_dominio", intro="algo que no debería aparecer")
    texto = _un_mensaje(respuesta, [])
    assert texto.startswith("Solo puedo ayudarte con recetas de fitosanitarios")
    assert "algo que no debería aparecer" not in texto


def test_no_resuelto_con_motivo():
    respuesta = RespuestaAgente(tipo="no_resuelto")
    resultado = ResultadoTool(
        estado="no_resuelto", motivo=MotivoNoResuelto.JURISDICCION_NO_CUBIERTA
    )
    texto = _un_mensaje(respuesta, [resultado])
    assert "no está entre las cargadas" in texto


def test_ayuda_es_texto_fijo():
    respuesta = RespuestaAgente(tipo="ayuda")
    texto = _un_mensaje(respuesta, [])
    assert texto.startswith("Hola 👋")


def test_error_es_texto_fijo():
    respuesta = RespuestaAgente(tipo="error")
    texto = _un_mensaje(respuesta, [])
    assert "problema técnico" in texto


def test_intro_se_antepone_salvo_en_fuera_de_dominio_ayuda_y_error():
    respuesta = RespuestaAgente(tipo="consulta_normativa", intro="Che, mirá esto:")
    resultado = ResultadoTool(estado="ok", datos={"veredicto": "Si", "regla": "Se puede."})
    texto = _un_mensaje(respuesta, [resultado])
    assert texto.startswith("Che, mirá esto:")


def test_partir_por_seccion_no_corta_una_lista_a_mitad():
    seccion_a = "A" * 3000
    seccion_b = "B" * 3000
    texto = f"{seccion_a}\n\n{seccion_b}"
    partes = partir_por_seccion(texto, limite=4096)
    assert len(partes) == 2
    assert partes[0] == seccion_a
    assert partes[1] == seccion_b


def test_partir_por_seccion_texto_corto_no_se_parte():
    assert partir_por_seccion("hola", limite=4096) == ["hola"]


# --- Fase 9: consulta_vehiculo, evento_registrado, agenda ---


def test_consulta_vehiculo():
    respuesta = RespuestaAgente(tipo="consulta_vehiculo")
    resultado = ResultadoTool(
        estado="ok", datos={"vehiculo": "dron", "tipo_aplicacion": "aerea"}
    )
    texto = _un_mensaje(respuesta, [resultado])
    assert texto == "*Vehículo:* dron (aerea)"


def test_evento_registrado_iniciado():
    respuesta = RespuestaAgente(tipo="evento_registrado")
    resultado = ResultadoTool(
        estado="ok",
        datos={"vehiculo": "dron", "lote": "4", "fecha_inicio": "2026-09-12T10:00:00+00:00"},
    )
    texto = _un_mensaje(respuesta, [resultado])
    assert texto == (
        "✅ *Aplicación iniciada*\n"
        "- *Vehículo:* dron\n"
        "- *Lote:* 4\n"
        "- *Inicio:* 2026-09-12T10:00:00+00:00"
    )


def test_evento_registrado_finalizado():
    respuesta = RespuestaAgente(tipo="evento_registrado")
    resultado = ResultadoTool(
        estado="ok",
        datos={
            "lote": "4",
            "fecha_inicio": "2026-09-12T10:00:00+00:00",
            "fecha_fin": "2026-09-12T12:00:00+00:00",
        },
    )
    texto = _un_mensaje(respuesta, [resultado])
    assert texto == (
        "✅ *Aplicación finalizada*\n"
        "- *Lote:* 4\n"
        "- *Inicio:* 2026-09-12T10:00:00+00:00\n"
        "- *Fin:* 2026-09-12T12:00:00+00:00"
    )


def test_evento_registrado_ya_en_curso():
    respuesta = RespuestaAgente(tipo="evento_registrado")
    resultado = ResultadoTool(
        estado="observado",
        datos={"lote": "1", "fecha_inicio": "2026-09-12T09:00:00+00:00"},
        advertencias=[
            "ya hay una aplicación en curso desde 2026-09-12T09:00:00+00:00 en el lote 1"
        ],
    )
    texto = _un_mensaje(respuesta, [resultado])
    assert texto == (
        "⚠️ *Ya hay una aplicación en curso*\n"
        "- ya hay una aplicación en curso desde 2026-09-12T09:00:00+00:00 en el lote 1"
    )


def test_agenda_vacia():
    respuesta = RespuestaAgente(tipo="agenda")
    resultado = ResultadoTool(estado="ok", datos={"fecha": "2026-09-12", "tareas": [], "total": 0})
    texto = _un_mensaje(respuesta, [resultado])
    assert texto == "No tenés tareas agendadas para el 2026-09-12."


def test_agenda_con_tareas():
    respuesta = RespuestaAgente(tipo="agenda")
    resultado = ResultadoTool(
        estado="ok",
        datos={
            "fecha": "2026-09-12",
            "total": 2,
            "tareas": [
                {"cultivo": "soja", "lote": "A", "estado_tarea": "pendiente"},
                {"cultivo": "maiz", "lote": "B", "estado_tarea": "en_curso"},
            ],
        },
    )
    texto = _un_mensaje(respuesta, [resultado])
    assert texto == (
        "*Agenda del 2026-09-12* (2)\n"
        "1. ⏳ soja — lote A (pendiente)\n"
        "2. 🚜 maiz — lote B (en_curso)"
    )


def test_dictamen_sin_normativa_municipal_lo_aclara_junto_a_la_distancia_provincial():
    condiciones = {
        "localidad": "Rosario", "tipo_aplicacion": "terrestre", "banda": "IV",
        "banda_color": "verde", "sin_normativa_municipal": True,
        "distancias_minimas": [{
            "tipo_zona": "zona_urbana", "distancia_min_m": 300.0,
            "norma_limitante": {"fuente": "normativa", "norma": "ley-13740-2017", "articulo": "2"},
        }],
        "advertencias": [
            "No se cuenta con la normativa municipal de Rosario: la distancia se basa en la "
            "normativa provincial"
        ],
    }
    resultado = ResultadoTool(
        estado="ok",
        datos={"dictamen": {"resultado": "APTA", "condiciones": condiciones}},
    )
    texto = _un_mensaje(RespuestaAgente(tipo="dictamen"), [resultado])
    assert "- *Distancia mínima a zona urbana:* 300 m (Ley 13740/2017, art. 2)" in texto
    assert "⚠️ No se cuenta con la normativa municipal de Rosario" in texto


def test_consulta_normativa_sin_normativa_municipal_lo_aclara():
    resultado = ResultadoTool(
        estado="ok",
        datos={"veredicto": "No", "regla": "La distancia mínima es de 300 metros."},
        citas=[Cita(fuente="normativa", norma="ley-13740-2017", articulo="2")],
        advertencias=[
            "No se cuenta con la normativa municipal de Rosario: la respuesta se basa en la "
            "normativa provincial"
        ],
    )
    texto = _un_mensaje(RespuestaAgente(tipo="consulta_normativa"), [resultado])
    assert texto == (
        "*No.* La distancia mínima es de 300 metros.\n\n"
        "⚠️ No se cuenta con la normativa municipal de Rosario: la respuesta se basa en la "
        "normativa provincial\n\n"
        "*Fuentes*\n"
        "- Ley 13740/2017, art. 2"
    )


def test_dictamen_avisa_cuando_la_distancia_se_leyo_del_texto_de_la_norma():
    condiciones = {
        "localidad": "Rosario", "tipo_aplicacion": "aerea", "banda": "II",
        "banda_color": "amarilla",
        "distancias_minimas": [{
            "tipo_zona": "zona_urbana", "distancia_min_m": 3000.0, "extraida_de_pdf": True,
            "norma_limitante": {"fuente": "normativa", "norma": "ley-11273-1995", "articulo": "33"},
        }],
        "advertencias": [],
    }
    resultado = ResultadoTool(
        estado="ok", datos={"dictamen": {"resultado": "APTA", "condiciones": condiciones}},
    )
    texto = _un_mensaje(RespuestaAgente(tipo="dictamen"), [resultado])
    assert "- *Distancia mínima a zona urbana:* 3000 m (Ley 11273/1995, art. 33)" in texto
    assert (
        "⚠️ La distancia a zona urbana se leyó del texto de Ley 11273/1995, art. 33 "
        "(la norma no tiene reglas.csv): verificala con la norma."
    ) in texto


def test_repregunta_de_un_dato_es_solo_la_pregunta_con_sus_opciones():
    respuesta = RespuestaAgente(tipo="repregunta", faltantes=[
        CampoFaltante(campo="productos", motivo="ambiguo",
                      pregunta_sugerida="Hay varios productos parecidos a 'Glifosato'. ¿Cuál es?",
                      tipo_entrada="lista", opciones=["Glifosato 48 Kemsure", "Glifosato 48 Sem"]),
    ])
    assert _un_mensaje(respuesta, []) == (
        "Hay varios productos parecidos a 'Glifosato'. ¿Cuál es?" + chr(10)
        + "   - Glifosato 48 Kemsure" + chr(10) + "   - Glifosato 48 Sem"
    )
