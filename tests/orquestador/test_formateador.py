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
        "- *Adversidad:* malezas de hoja ancha\n"
        "- *Producto:* Glifosato 48% — 2 L/ha\n"
        "- *Superficie:* 35 ha\n"
        "- *Tipo de aplicación:* no figura ⚠️\n"
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
        "¿Querés que agende la aplicación?"
    )


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
    assert "*Fuentes*" in texto


def test_consulta_producto_puntual():
    respuesta = RespuestaAgente(tipo="consulta_producto")
    resultado = ResultadoTool(
        estado="ok",
        datos={
            "producto": "Flyer 10 Ec", "numero_inscripcion": "41881",
            "banda_toxicologica": "II", "cultivo_autorizado": True,
        },
        citas=[Cita(fuente="senasa", registro_senasa="41881", documento="detalle API")],
    )
    texto = _un_mensaje(respuesta, [resultado])
    assert texto.startswith("*Flyer 10 Ec* · Reg. SENASA 41881 · Banda II · ✅")


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
        "Para continuar necesito 2 datos:\n"
        "1. *ubicacion_lote*: Mandá la ubicación del lote\n"
        "2. *tipo_aplicacion*: Elegí una opción\n"
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
