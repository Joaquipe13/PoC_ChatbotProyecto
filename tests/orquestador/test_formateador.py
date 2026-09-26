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
        estado="ok",
        datos={
            "numero": "0042", "cultivo": "soja", "lote": "4", "localidad": "El Trébol",
            "adversidad": "malezas de hoja ancha",
            "items": [{"producto_nombre": "Glifosato 48%", "dosis_declarada": "2 L/ha"}],
            "superficie_ha": 35, "tipo_aplicacion": "aerea",
        },
    )
    texto = _un_mensaje(respuesta, [resultado])
    assert texto == (
        "*Leí la receta N.° 0042*. Confirmá los datos:\n"
        "- *Cultivo:* soja\n"
        "- *Lote:* 4\n"
        "- *Localidad:* El Trébol\n"
        "- *Superficie:* 35 ha\n"
        "- *Adversidad:* malezas de hoja ancha\n"
        "- *Producto:* Glifosato 48% — 2 L/ha\n"
        "- *Tipo de aplicación:* aérea\n"
        "[Confirmar] [Corregir]"
    )


def test_confirmacion_receta_con_datos_obligatorios_faltantes_los_pregunta_sin_ofrecer_confirmar():
    """El caso real del 23/09/2026: la receta 1001 sin cultivo ni localidad se mostraba con
    "no figura ⚠️" y [Confirmar]; ahora se pregunta lo que falta antes de confirmar."""
    from fitosanitarios.servicios.receta import faltantes_de_receta

    datos = {
        "numero": "1001", "cultivo": None, "lote": "8", "localidad": None,
        "adversidad": "Chinche de la alfalfa", "superficie_ha": 40,
        "items": [{"producto_nombre": "Flyer 10 Ec", "dosis_declarada": "170 cm3/ha"}],
        "tipo_aplicacion": "terrestre",
    }
    resultado = ResultadoTool(
        estado="faltan_datos", datos=datos, faltantes=faltantes_de_receta(datos)
    )
    texto = _un_mensaje(RespuestaAgente(tipo="confirmacion_receta"), [resultado])
    assert texto == (
        "*Leí la receta N.° 1001*. Falta la siguiente información obligatoria:\n\n"
        "1. *Cultivo:* ¿Qué cultivo es?\n"
        "2. *Localidad:* ¿En qué localidad se aplica?\n\n"
        "*Lo que pude leer:*\n"
        "- *Lote:* 8\n"
        "- *Superficie:* 40 ha\n"
        "- *Adversidad:* Chinche de la alfalfa\n"
        "- *Producto:* Flyer 10 Ec — 170 cm3/ha\n"
        "- *Tipo de aplicación:* terrestre"
    )
    assert "[Confirmar]" not in texto


def test_confirmacion_receta_con_campos_descriptivos_completos():
    """Los campos agregados el 12/09/2026 (ver DECISIONES.md) se muestran sin
    ⚠️: son descriptivos, no bloquean la confirmación si faltan."""
    respuesta = RespuestaAgente(tipo="confirmacion_receta")
    resultado = ResultadoTool(
        estado="ok",
        datos={
            "cultivo": "soja", "lote": "4", "localidad": "El Trébol", "superficie_ha": 35,
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
        "- *Localidad:* El Trébol\n"
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
            "jurisdiccion_id": "el-trebol",
            "dictamen": {
                "resultado": "OBSERVADA",
                "observaciones": [
                    {"descripcion": "Aplicación aérea con banda II a menos de 3000 m de la "
                                    "zona urbana."},
                ],
                "chequeos_no_realizados": [],
                "citas": [
                    {"fuente": "normativa", "norma": "ordenanza-841-2010", "articulo": "7",
                     "jurisdiccion_id": "el-trebol"},
                ],
            },
        },
        citas=[Cita(fuente="normativa", norma="ordenanza-841-2010", articulo="7",
                    jurisdiccion_id="el-trebol")],
    )
    texto = _un_mensaje(respuesta, [resultado])
    assert texto == (
        "*Dictamen* — el-trebol\n"
        "*Resultado:* ❌ OBSERVADA\n\n"
        "*Observaciones*\n"
        "1. Aplicación aérea con banda II a menos de 3000 m de la zona urbana.\n\n"
        "*Fuentes*\n"
        "- Ordenanza 841/2010, art. 7 (el-trebol)"
    )


def test_dictamen_apta_sin_observaciones():
    respuesta = RespuestaAgente(tipo="dictamen")
    resultado = ResultadoTool(
        estado="ok",
        datos={
            "jurisdiccion_id": "el-trebol",
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
        "¿Agendamos la aplicación?\n[Agendar] [No, gracias]"
    )


def test_dictamen_no_muestra_la_banda_de_cada_producto_hasta_que_se_pide():
    texto = _un_mensaje(RespuestaAgente(tipo="dictamen"), [_dictamen_el_trebol()])
    assert "Producto A" not in texto


def test_dictamen_observado_no_ofrece_agendar():
    texto = _un_mensaje(RespuestaAgente(tipo="dictamen"), [_dictamen_el_trebol("OBSERVADA")])
    assert texto.endswith("¿Querés la banda de cada producto?\n[Sí] [No]")
    assert "Agendar" not in texto


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
    assert texto.endswith("[Agendar] [No, gracias]")


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
        "¿Agendamos la aplicación?\n[Agendar] [No, gracias]"
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
    salía una sola frase."""
    resultado = ResultadoTool(
        estado="faltan_datos",
        faltantes=[CampoFaltante(
            campo="provincia", motivo="la localidad no tiene normativa cargada",
            pregunta_sugerida="¿En qué provincia queda Pergamino?", tipo_entrada="texto",
        )],
    )
    respuesta = RespuestaAgente(tipo="dictamen")
    texto = _un_mensaje(respuesta, [resultado])
    assert "¿En qué provincia queda Pergamino?" in texto


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


def test_consulta_producto_listado_largo_dice_cuantos_muestra_y_la_plaga():
    """Se muestran 10: el encabezado lo dice. El mismo producto aparece una vez por plaga
    registrada; sin la plaga, las filas se veían repetidas."""
    respuesta = RespuestaAgente(tipo="consulta_producto")
    productos = [
        {"marca": "2,4-db 93.1 Brilliance", "numero_inscripcion": "41974",
         "banda_toxicologica": "III", "adversidad": f"Maleza {i}",
         "dosis": {"texto_original": "40 cm3/ha"}}
        for i in range(20)
    ]
    resultado = ResultadoTool(estado="ok", datos={"total": 20, "productos": productos})
    texto = _un_mensaje(respuesta, [resultado])
    assert "*Productos registrados* (10 de 20)" in texto
    assert "Banda III · Maleza 0 · 40 cm3/ha" in texto
    assert "Maleza 10" not in texto


def test_consulta_producto_puntual():
    respuesta = RespuestaAgente(tipo="consulta_producto")
    resultado = ResultadoTool(
        estado="ok",
        datos={
            "producto": "Flyer 10 Ec", "numero_inscripcion": "41881",
            "banda_toxicologica": "II", "cultivo": "soja", "cultivo_autorizado": True,
            "usos_del_cultivo": [
                {"cultivo": "Soja", "adversidad": "Chinche De La Alfalfa",
                 "dosis": {"texto_original": "160-180 cm3/ha"}}
            ],
        },
        citas=[Cita(fuente="senasa", registro_senasa="41881", documento="detalle API")],
    )
    texto = _un_mensaje(respuesta, [resultado])
    assert texto == (
        "*Flyer 10 Ec* · Reg. SENASA 41881 · Banda II · ✅ autorizado para soja\n"
        "Dosis registrada para soja: 160-180 cm3/ha (Chinche De La Alfalfa)"
    )
    assert "*Fuentes*" not in texto


def test_consulta_producto_sin_cultivo_muestra_la_banda_con_su_color():
    """"¿Qué banda tiene el Flyer?": sin cultivo no hay autorización que mostrar."""
    resultado = ResultadoTool(
        estado="ok",
        datos={
            "producto": "Flyer 10 Ec", "numero_inscripcion": "41881",
            "banda_toxicologica": "II", "cultivo": None, "cultivo_autorizado": None,
            "usos_del_cultivo": [],
        },
    )
    texto = _un_mensaje(RespuestaAgente(tipo="consulta_producto"), [resultado])
    assert texto == "*Flyer 10 Ec* · Reg. SENASA 41881 · Banda II (amarilla)"


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


def test_consulta_producto_muestra_la_dosis_del_cultivo_consultado_y_no_la_de_otro():
    """Bug real (Gemini): "¿el Flyer 10 Ec está registrado para soja?" respondía
    "Dosis registrada: 10 cm3/hl", la del primer uso registrado, que es de duraznero."""
    resultado = ResultadoTool(
        estado="ok",
        datos={
            "producto": "Flyer 10 Ec", "numero_inscripcion": "41881", "banda_toxicologica": "II",
            "cultivo": "soja", "cultivo_autorizado": True,
            # datos de otro cultivo que la tool ya no trae; si llegaran, no se usan
            "usos_registrados": [
                {"cultivo": "Duraznero", "dosis": {"texto_original": "10 cm3/hl"}}
            ],
            "usos_del_cultivo": [
                {"cultivo": "Soja", "adversidad": "Chinche De La Alfalfa",
                 "dosis": {"texto_original": "160-180 cm3/ha"}},
                {"cultivo": "Soja", "adversidad": "Oruga",
                 "dosis": {"texto_original": "25 a 35 cm3/ha"}},
            ],
        },
    )
    texto = _un_mensaje(RespuestaAgente(tipo="consulta_producto"), [resultado])
    assert texto == (
        "*Flyer 10 Ec* · Reg. SENASA 41881 · Banda II · ✅ autorizado para soja\n"
        "Dosis registrada para soja:\n"
        "- 160-180 cm3/ha (Chinche De La Alfalfa)\n"
        "- 25 a 35 cm3/ha (Oruga)"
    )
    assert "10 cm3/hl" not in texto


def test_consulta_producto_sin_dosis_para_el_cultivo_no_muestra_ninguna():
    resultado = ResultadoTool(
        estado="observado",
        datos={
            "producto": "Flyer 10 Ec", "numero_inscripcion": "41881", "banda_toxicologica": "II",
            "cultivo": "maiz", "cultivo_autorizado": False, "usos_del_cultivo": [],
        },
    )
    texto = _un_mensaje(RespuestaAgente(tipo="consulta_producto"), [resultado])
    assert texto == "*Flyer 10 Ec* · Reg. SENASA 41881 · Banda II · ⚠️ no autorizado para maiz"


def test_consulta_producto_con_muchas_dosis_muestra_las_primeras_y_cuenta_el_resto():
    usos = [
        {"cultivo": "Soja", "adversidad": f"Plaga {i}", "dosis": {"texto_original": f"{i} g/ha"}}
        for i in range(1, 7)
    ]
    resultado = ResultadoTool(estado="ok", datos={
        "producto": "X", "numero_inscripcion": "1", "banda_toxicologica": "IV",
        "cultivo": "soja", "cultivo_autorizado": True, "usos_del_cultivo": usos,
    })
    texto = _un_mensaje(RespuestaAgente(tipo="consulta_producto"), [resultado])
    assert texto.count("\n- ") == 5 and texto.endswith("- y 2 más")


def test_consulta_normativa():
    respuesta = RespuestaAgente(tipo="consulta_normativa")
    resultado = ResultadoTool(
        estado="ok",
        datos={"veredicto": "Si", "regla": "Hay que comunicarlo y adjuntar la receta agronómica."},
        citas=[Cita(fuente="normativa", norma="ordenanza-841-2010", articulo="5",
                    jurisdiccion_id="el-trebol")],
    )
    texto = _un_mensaje(respuesta, [resultado])
    assert texto == (
        "*Si.* Hay que comunicarlo y adjuntar la receta agronómica.\n\n"
        "*Fuentes*\n"
        "- Ordenanza 841/2010, art. 5 (el-trebol)"
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
    respuesta = RespuestaAgente(tipo="fuera_de_dominio")
    texto = _un_mensaje(respuesta, [])
    assert texto.startswith("Solo puedo ayudarte con recetas de fitosanitarios")


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
            "tipo_zona": "zona_urbana", "distancia_min_m": 500.0,
            "norma_limitante": {"fuente": "normativa", "norma": "ley-11273-1995", "articulo": "34"},
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
    assert "- *Distancia mínima a zona urbana:* 500 m (Ley 11273/1995, art. 34)" in texto
    assert "⚠️ No se cuenta con la normativa municipal de Rosario" in texto


def test_consulta_normativa_sin_normativa_municipal_lo_aclara():
    resultado = ResultadoTool(
        estado="ok",
        datos={"veredicto": "No", "regla": "La distancia mínima es de 500 metros."},
        citas=[Cita(fuente="normativa", norma="ley-11273-1995", articulo="34")],
        advertencias=[
            "No se cuenta con la normativa municipal de Rosario: la respuesta se basa en la "
            "normativa provincial"
        ],
    )
    texto = _un_mensaje(RespuestaAgente(tipo="consulta_normativa"), [resultado])
    assert texto == (
        "*No.* La distancia mínima es de 500 metros.\n\n"
        "⚠️ No se cuenta con la normativa municipal de Rosario: la respuesta se basa en la "
        "normativa provincial\n\n"
        "*Fuentes*\n"
        "- Ley 11273/1995, art. 34"
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
        "(no hay reglas cargadas a mano para esa jurisdicción): verificala con la norma."
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


# --- consulta_articulo ---


def _resultado_articulo(partes, **extra):
    return ResultadoTool(
        estado="ok",
        datos={
            "numero": "33", "norma": "ley-11273-1995", "norma_legible": "Ley 11273/1995",
            "jurisdiccion_id": "santa-fe", "partes": [{"texto": t, "pagina": 1} for t in partes],
        },
        citas=[Cita(fuente="normativa", jurisdiccion_id="santa-fe", norma="ley-11273-1995",
                    articulo="33")],
        **extra,
    )


def test_consulta_articulo_muestra_el_texto_literal_con_su_encabezado():
    texto = _un_mensaje(
        RespuestaAgente(tipo="consulta_articulo"),
        [_resultado_articulo(["Prohíbese la aplicación aérea dentro de 3.000 metros."])],
    )
    assert texto == (
        "*Ley 11273/1995, art. 33 (santa-fe)*\n"
        "Prohíbese la aplicación aérea dentro de 3.000 metros."
    )


def test_consulta_articulo_con_varios_textos_para_el_mismo_numero():
    texto = _un_mensaje(
        RespuestaAgente(tipo="consulta_articulo"), [_resultado_articulo(["Uno.", "Dos."])]
    )
    assert texto == (
        "*Ley 11273/1995, art. 33 (santa-fe) — texto 1 de 2*\nUno.\n\n"
        "*Ley 11273/1995, art. 33 (santa-fe) — texto 2 de 2*\nDos."
    )


def test_consulta_articulo_muestra_las_advertencias():
    texto = _un_mensaje(
        RespuestaAgente(tipo="consulta_articulo"),
        [_resultado_articulo(["Texto."], advertencias=["Busqué en la normativa provincial"])],
    )
    assert texto.endswith("⚠️ Busqué en la normativa provincial")


def test_consulta_articulo_que_repregunta_la_norma_muestra_la_lista():
    resultado = ResultadoTool(
        estado="faltan_datos",
        faltantes=[CampoFaltante(
            campo="norma", motivo="varias",
            pregunta_sugerida="El artículo 33 está en varias normas. ¿De cuál?",
            tipo_entrada="lista",
            opciones=["Ley 11273/1995 (santa-fe)", "Ordenanza 841/2010 (el-trebol)"],
        )],
    )
    texto = _un_mensaje(RespuestaAgente(tipo="consulta_articulo"), [resultado])
    assert texto == (
        "El artículo 33 está en varias normas. ¿De cuál?\n"
        "   - Ley 11273/1995 (santa-fe)\n"
        "   - Ordenanza 841/2010 (el-trebol)"
    )


def test_consulta_articulo_no_encontrado_usa_el_no_resuelto():
    resultado = ResultadoTool(
        estado="no_resuelto", motivo=MotivoNoResuelto.ARTICULO_NO_ENCONTRADO,
        advertencias=["No hay un artículo 999 en la normativa consultada"],
    )
    texto = _un_mensaje(RespuestaAgente(tipo="consulta_articulo"), [resultado])
    assert "No pude completar la consulta" in texto
    assert "No hay un artículo con ese número" in texto and "artículo 999" in texto


# --- limitaciones ---


def _regla(zona, aplicacion, bandas, distancia, norma, articulo, **extra):
    return {
        "tipo_zona": zona, "tipo_aplicacion": aplicacion, "bandas": bandas,
        "distancia_min_m": distancia, "norma": norma, "articulo": articulo,
        "jurisdiccion_id": "santa-fe", "observaciones": None, "condiciones": None,
        "extraida_de_pdf": False, **extra,
    }


AEREA_II = _regla("zona_urbana", "aerea", ["II"], 3000, "ley-11273-1995", "33")
TERRESTRE = _regla("zona_urbana", "terrestre", ["Ia", "Ib", "II"], 500, "ley-11273-1995", "34")
EXCEPCION = _regla(
    "zona_urbana", "aerea", ["II"], 500, "ley-055297-2017", "51",
    condiciones="ordenanza que la autorice",
)


def _citas(*reglas):
    return [Cita(fuente="normativa", jurisdiccion_id="santa-fe", norma=r["norma"],
                 articulo=r["articulo"]) for r in reglas]


def test_limitaciones_agrupa_por_aplicacion_y_lista_las_excepciones():
    resultado = ResultadoTool(
        estado="ok",
        datos={
            "localidad": "Rosario", "distancia_m": None,
            "prohibiciones": [TERRESTRE, AEREA_II], "condicionales": [EXCEPCION],
        },
        citas=_citas(TERRESTRE, AEREA_II, EXCEPCION),
        advertencias=["No se cuenta con la normativa municipal de Rosario: las limitaciones "
                      "son las de la normativa provincial"],
    )
    texto = _un_mensaje(RespuestaAgente(tipo="limitaciones"), [resultado])
    assert texto == (
        "*Limitaciones en Rosario*\n\n"
        "⚠️ No se cuenta con la normativa municipal de Rosario: las limitaciones son las de la "
        "normativa provincial\n\n"
        "*Aplicación aérea*\n"
        "- Zona urbana · banda II: a menos de 3000 m no se puede aplicar (Ley 11273/1995, art. 33)"
        "\n\n"
        "*Aplicación terrestre*\n"
        "- Zona urbana · bandas Ia, Ib, II: a menos de 500 m no se puede aplicar "
        "(Ley 11273/1995, art. 34)\n\n"
        "*Excepciones*\n"
        "- Zona urbana · aérea · banda II: se puede desde 500 m con condiciones "
        "(Ley 055297/2017, art. 51)\n\n"
        "*Fuentes*\n"
        "- Ley 11273/1995, art. 34 (santa-fe)\n"
        "- Ley 11273/1995, art. 33 (santa-fe)\n"
        "- Ley 055297/2017, art. 51 (santa-fe)"
    )


def test_limitaciones_a_una_distancia_muestra_que_aplicaciones_y_bandas_se_pueden():
    resultado = ResultadoTool(
        estado="ok",
        datos={
            "localidad": "Rosario", "distancia_m": 1000,
            "restricciones": [
                {"prohibicion": AEREA_II, "excepciones": [EXCEPCION]},
                {"prohibicion": TERRESTRE, "excepciones": []},
            ],
        },
        citas=_citas(AEREA_II, EXCEPCION, TERRESTRE),
    )
    texto = _un_mensaje(RespuestaAgente(tipo="limitaciones"), [resultado])
    assert texto.startswith(
        "*A 1000 m de la zona urbana en Rosario*\n"
        "- *Terrestre:* ✅ III y IV · ❌ Ia, Ib y II\n"
        "- *Aérea:* ✅ Ia, Ib, III y IV · ⚠️ II solo con excepción (Ley 055297/2017, art. 51)"
        "\n\n*Fuentes*"
    )
    assert "ordenanza que la autorice" not in texto


def test_limitaciones_a_una_distancia_que_cumple_todo():
    resultado = ResultadoTool(
        estado="ok", datos={"localidad": "Rosario", "distancia_m": 5000, "restricciones": []},
    )
    texto = _un_mensaje(RespuestaAgente(tipo="limitaciones"), [resultado])
    assert texto == (
        "*A 5000 m en Rosario*\n\nA esa distancia no hay ninguna prohibición para lo consultado."
    )


def test_limitaciones_marca_lo_leido_del_pdf_y_no_transcribe_las_observaciones():
    regla = _regla("zona_urbana", "aerea", ["todas"], 500, "ley-1-2000", "3",
                   extraida_de_pdf=True, observaciones="Aviso previo")
    resultado = ResultadoTool(
        estado="ok",
        datos={
            "localidad": "X", "distancia_m": None, "prohibiciones": [regla], "condicionales": [],
        },
    )
    texto = _un_mensaje(RespuestaAgente(tipo="limitaciones"), [resultado])
    assert "Aviso previo" not in texto
    assert "  ⚠️ Distancia leída del texto de la norma: verificala con la norma." in texto


def test_limitaciones_sin_datos_por_falta_de_localidad_repregunta():
    resultado = ResultadoTool(
        estado="faltan_datos",
        faltantes=[CampoFaltante(
            campo="localidad", motivo="falta", pregunta_sugerida="¿En qué localidad se aplica?",
            tipo_entrada="texto",
        )],
    )
    assert _un_mensaje(RespuestaAgente(tipo="limitaciones"), [resultado]) == (
        "¿En qué localidad se aplica?"
    )


# --- mensajes largos ---


def test_un_articulo_mas_largo_que_el_limite_se_parte_por_oraciones_sin_cortar_palabras():
    oracion = "Prohíbese la aplicación de productos fitosanitarios en las inmediaciones."
    largo = " ".join([oracion] * 12)  # un solo renglón, sin línea en blanco
    partes = partir_por_seccion(largo, limite=200)
    assert len(partes) > 1 and all(len(p) <= 200 for p in partes)
    assert " ".join(p.replace("\n", " ") for p in partes) == largo  # no se pierde nada


def test_un_renglon_sin_puntos_mas_largo_que_el_limite_se_parte_por_palabras():
    largo = " ".join(["palabra"] * 100)
    partes = partir_por_seccion(largo, limite=120)
    assert all(len(p) <= 120 for p in partes)
    assert " ".join(p.replace("\n", " ") for p in partes).split() == largo.split()


# --- las opciones de la tool mandan sobre las que reescribe el LLM ---


def test_repregunta_usa_las_opciones_de_la_tool_y_no_las_que_escribio_el_llm():
    """Bug real (Gemini): la tool ofrecía las 3 normas donde está el artículo y el LLM
    repreguntó con opciones propias, entre ellas una norma que no existe."""
    de_la_tool = CampoFaltante(
        campo="norma", motivo="varias", pregunta_sugerida="¿De cuál?", tipo_entrada="lista",
        opciones=["Ley 11273/1995 (santa-fe)", "Ordenanza 841/2010 (el-trebol)"],
    )
    inventada = CampoFaltante(
        campo="norma", motivo="varias", pregunta_sugerida="¿De qué norma?", tipo_entrada="lista",
        opciones=["Ordenanza 841/2010", "Ordenanza 1152/2018"],
    )
    texto = _un_mensaje(
        RespuestaAgente(tipo="repregunta", faltantes=[inventada]),
        [ResultadoTool(estado="faltan_datos", faltantes=[de_la_tool])],
    )
    assert texto == "¿De cuál?\n   - Ley 11273/1995 (santa-fe)\n   - Ordenanza 841/2010 (el-trebol)"
    assert "1152" not in texto


def test_repregunta_sin_tool_usa_lo_que_dijo_el_llm():
    faltante = CampoFaltante(
        campo="localidad", motivo="falta", pregunta_sugerida="¿En qué localidad?",
        tipo_entrada="texto",
    )
    assert _un_mensaje(RespuestaAgente(tipo="repregunta", faltantes=[faltante]), []) == (
        "¿En qué localidad?"
    )


# --- la forma de los datos manda sobre el tipo que eligió el LLM ---


def _riesgo_suelto() -> ResultadoTool:
    return ResultadoTool(
        estado="ok",
        datos={"condiciones": {
            "localidad": "El Trébol", "tipo_aplicacion": "aerea", "banda": "II",
            "banda_color": "amarilla", "productos_por_banda": {"Flyer 10 Ec": "II"},
            "distancias_minimas": [{
                "tipo_zona": "zona_urbana", "distancia_min_m": 3000,
                "norma_limitante": {"fuente": "normativa", "norma": "ordenanza-841-2010",
                                    "articulo": "7"},
            }],
        }},
    )


def test_si_el_llm_dice_limitaciones_para_un_riesgo_se_muestra_como_dictamen():
    """Bug real (Gemini): tras `evaluar_riesgo` respondió tipo="limitaciones" y salía un
    "*Limitaciones en *" vacío."""
    texto = _un_mensaje(RespuestaAgente(tipo="limitaciones"), [_riesgo_suelto()])
    assert "*Condiciones de aplicación* — El Trébol" in texto
    assert "- *Distancia mínima a zona urbana:* 3000 m (Ordenanza 841/2010, art. 7)" in texto
    assert "Limitaciones en" not in texto


def test_si_el_llm_dice_dictamen_para_las_limitaciones_se_muestran_las_limitaciones():
    resultado = ResultadoTool(
        estado="ok",
        datos={"localidad": "Rosario", "distancia_m": None,
               "prohibiciones": [AEREA_II], "condicionales": []},
        citas=_citas(AEREA_II),
    )
    texto = _un_mensaje(RespuestaAgente(tipo="dictamen"), [resultado])
    assert texto.startswith("*Limitaciones en Rosario*")


def test_si_el_llm_dice_consulta_normativa_para_un_articulo_se_muestra_el_articulo():
    texto = _un_mensaje(
        RespuestaAgente(tipo="consulta_normativa"), [_resultado_articulo(["Texto del artículo."])]
    )
    assert texto.startswith("*Ley 11273/1995, art. 33 (santa-fe)*")


def test_un_tipo_compatible_con_los_datos_no_se_toca():
    # detalle_bandas usa los mismos datos que un riesgo suelto: no se lo pasa a dictamen.
    texto = _un_mensaje(RespuestaAgente(tipo="detalle_bandas"), [_riesgo_suelto()])
    assert texto.startswith("*Banda de cada producto*")


def test_los_campos_descriptivos_de_una_receta_no_se_confunden_con_una_forma_propia():
    # `restricciones` y `condiciones` de una receta leída son texto, no las listas y dicts
    # de las limitaciones o del riesgo.
    resultado = ResultadoTool(
        estado="ok",
        datos={"cultivo": "soja", "restricciones": "no aplicar con viento",
               "condiciones": "T < 30 °C", "items": []},
    )
    texto = _un_mensaje(RespuestaAgente(tipo="confirmacion_receta"), [resultado])
    assert texto.startswith("*Leí la receta*")


def test_la_pregunta_de_una_tool_no_se_tapa_con_el_listado_vacio_de_otra():
    """Bug real (Gemini): `validar_producto_registro` preguntó cuál de 5 productos y
    `consultar_productos` devolvió un listado vacío: salía "No encontré productos"."""
    pregunta = ResultadoTool(estado="faltan_datos", faltantes=[CampoFaltante(
        campo="producto_nombre", motivo="varios", tipo_entrada="lista",
        pregunta_sugerida="Hay varios productos parecidos a 'glifosato'. ¿Cuál es?",
        opciones=["Glifosato 48 Sl Assa", "Glifosato Full Sigma"],
    )])
    listado_vacio = ResultadoTool(estado="ok", datos={"productos": [], "total": 0})
    texto = _un_mensaje(RespuestaAgente(tipo="consulta_producto"), [pregunta, listado_vacio])
    assert texto.startswith("Hay varios productos parecidos a 'glifosato'. ¿Cuál es?")
    assert "   - Glifosato Full Sigma" in texto and "No encontré" not in texto


def test_una_receta_leida_con_faltantes_sigue_siendo_una_confirmacion():
    # leer_receta devuelve faltan_datos CON datos: se confirma lo leído, no se repregunta.
    resultado = ResultadoTool(
        estado="faltan_datos", datos={"cultivo": "soja", "items": []},
        faltantes=[CampoFaltante(campo="lote", motivo="x", pregunta_sugerida="¿Lote?",
                                 tipo_entrada="texto")],
    )
    texto = _un_mensaje(RespuestaAgente(tipo="confirmacion_receta"), [resultado])
    assert texto.startswith("*Leí la receta*")


# --- un mensaje con varias preguntas se contesta entero ---


def _limitaciones(localidad, distancia=None, regla=AEREA_II):
    datos = {"localidad": localidad, "distancia_m": distancia, "prohibiciones": [regla],
             "condicionales": []}
    if distancia is not None:
        datos["restricciones"] = [{"prohibicion": regla, "excepciones": []}]
    return ResultadoTool(estado="ok", datos=datos, citas=_citas(regla))


def _todo(respuesta, resultados) -> str:
    return "\n\n".join(formatear_respuesta(respuesta, resultados))


def test_dos_consultas_en_un_turno_se_contestan_las_dos():
    """Hallazgo H3: "y en trebol tmb a 1000? y pasame el texto del art 33" se contestaba solo
    lo segundo. Ahora, si el LLM llama a las dos tools, se muestran las dos."""
    texto = _todo(
        RespuestaAgente(tipo="consulta_articulo"),
        [_limitaciones("El Trébol", distancia=1000), _resultado_articulo(["Texto del art. 33."])],
    )
    assert "*A 1000 m de la zona urbana en El Trébol*" in texto
    assert "*Ley 11273/1995, art. 33 (santa-fe)*\nTexto del art. 33." in texto
    assert texto.index("A 1000 m de la zona urbana") < texto.index("*Ley 11273/1995, art. 33")


def test_dos_localidades_en_un_turno_muestran_cada_una():
    texto = _todo(
        RespuestaAgente(tipo="limitaciones"),
        [_limitaciones("Rosario"), _limitaciones("El Trébol")],
    )
    assert "*Limitaciones en Rosario*" in texto and "*Limitaciones en El Trébol*" in texto


def test_una_tool_llamada_varias_veces_con_lo_mismo_se_muestra_una_sola_vez():
    """Gemini llegó a llamar 3 veces a `listar_limitaciones` con los mismos argumentos."""
    tres = [_limitaciones("El Trébol") for _ in range(3)]
    texto = _un_mensaje(RespuestaAgente(tipo="limitaciones"), tres)
    assert texto.count("*Limitaciones en El Trébol*") == 1


def test_una_consulta_contestada_y_otra_que_pide_un_dato_muestra_las_dos_cosas():
    pregunta = ResultadoTool(estado="faltan_datos", faltantes=[CampoFaltante(
        campo="norma", motivo="varias", tipo_entrada="lista",
        pregunta_sugerida="El artículo 7 está en varias normas. ¿De cuál?",
        opciones=["Ley 11273/1995 (santa-fe)", "Ordenanza 841/2010 (el-trebol)"],
    )])
    texto = _todo(
        RespuestaAgente(tipo="limitaciones"), [_limitaciones("El Trébol"), pregunta]
    )
    respondido = texto.index("*Limitaciones en El Trébol*")
    assert respondido < texto.index("El artículo 7 está en varias normas")
    assert "   - Ordenanza 841/2010 (el-trebol)" in texto


def test_el_tipo_que_elige_el_llm_no_cambia_lo_que_muestra_la_forma_de_los_datos():
    normativa = ResultadoTool(
        estado="ok", datos={"veredicto": "Si", "regla": "Se avisa 48 h antes."},
        citas=_citas(AEREA_II),
    )
    texto = _un_mensaje(RespuestaAgente(tipo="limitaciones"), [normativa])
    assert texto.startswith("*Si.* Se avisa 48 h antes.")


def test_los_datos_de_un_riesgo_no_se_confunden_con_un_listado_de_productos():
    riesgo = ResultadoTool(estado="ok", datos={
        "productos": [{"nombre": "Flyer 10 Ec", "numero_inscripcion": "41881",
                       "banda_toxicologica": "II"}],
        "condiciones": {"localidad": "El Trébol", "tipo_aplicacion": "aerea", "banda": "II",
                        "productos_por_banda": {"Flyer 10 Ec": "II"}, "distancias_minimas": []},
    })
    texto = _un_mensaje(RespuestaAgente(tipo="detalle_bandas"), [riesgo])
    assert texto.startswith("*Banda de cada producto*")
