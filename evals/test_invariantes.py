"""Tests de los invariantes con conversaciones sintéticas (sin red ni base).

No corren con `pytest` a secas (`testpaths = ["tests"]`): se corren a propósito con
`uv run pytest evals`. Cada invariante tiene un caso que lo dispara y uno limpio.
"""

from evals import invariantes as inv


def llamada(nombre, estado="ok", **extra):
    return {"nombre": nombre, "args": extra.pop("args", {}), "estado": estado,
            "faltantes": [], "citas": [], "advertencias": [], "chequeos_no_realizados": [],
            "datos": None, **extra}


def turno(n, entrada="hola", tipo="ayuda", texto="ok", tools=(), faltantes=(), **extra):
    return {
        "tipo_registro": "turno", "n": n, "entrada": {"tipo": "texto", "contenido": entrada},
        "tool_calls": list(tools),
        "respuesta": {"tipo": tipo, "faltantes": list(faltantes)},
        "mensajes": [{"texto": texto, "envio": "texto", "opciones": []}],
        "latencia_s": 1.0, "tokens": {"entrada": 1, "salida": 1}, "llamadas_tool": len(tools),
        "reintentos_tool": 0, "infra": False, "error": None, **extra,
    }


def nombres(violaciones):
    return {v["invariante"] for v in violaciones}


def analizar(*turnos, escenario=None):
    return inv.analizar_conversacion(list(turnos), escenario)


# --- números y citas ---


def test_un_numero_que_ninguna_tool_devolvio_se_marca():
    lim = llamada("listar_limitaciones", datos={"prohibiciones": [{"distancia_min_m": 500}]})
    v = analizar(turno(1, tipo="limitaciones", tools=[lim],
                       texto="A menos de 3000 m no se puede aplicar"))
    assert "numero_sin_respaldo" in nombres(v)
    assert v[0]["severidad"] == "critico"


def test_los_numeros_de_las_tools_y_del_usuario_estan_respaldados():
    lim = llamada("listar_limitaciones", datos={"prohibiciones": [{"distancia_min_m": 3000.0}]})
    v = analizar(turno(1, entrada="tengo 25 ha", tipo="limitaciones", tools=[lim],
                       texto="Son 25 ha.\n1. A menos de 3.000 m no se puede\n2. Otra cosa"))
    assert "numero_sin_respaldo" not in nombres(v)  # 3.000 = 3000.0; los ordinales se ignoran


def test_una_cita_que_ninguna_tool_devolvio_se_marca():
    art = llamada("consultar_articulo", datos={"norma_legible": "Ley 11273/1995", "numero": "33"})
    v = analizar(turno(1, tipo="consulta_articulo", tools=[art],
                       texto="Ley 11273/1995, art. 34 dice…"))
    assert "cita_no_verificada" in nombres(v)


def test_una_cita_respaldada_no_se_marca():
    lim = llamada("listar_limitaciones", datos={"prohibiciones": [
        {"norma": "ley-11273-1995", "articulo": "33", "distancia_min_m": 500}]})
    v = analizar(turno(1, tipo="limitaciones", tools=[lim],
                       texto="a menos de 500 m (Ley 11273/1995, art. 33)"))
    assert "cita_no_verificada" not in nombres(v)


# --- dictamen ---


def test_dictamen_apta_con_chequeos_pendientes():
    dic = llamada("evaluar_viabilidad_legal", datos={"dictamen": {
        "resultado": "APTA", "chequeos_no_realizados": ["dosis no comparable"]}})
    v = analizar(turno(1, tipo="dictamen", tools=[dic], texto="*Dictamen*\n✅ APTA"))
    assert "dictamen_apta_con_chequeos_pendientes" in nombres(v)


def test_dictamen_sin_tool_y_normativa_sin_rag():
    v = analizar(turno(1, tipo="dictamen", texto="*Dictamen* ✅ APTA"),
                 turno(2, tipo="consulta_normativa", texto="Sí."))
    assert [x["invariante"] for x in v if x["invariante"] == "respuesta_sin_su_tool"] == [
        "respuesta_sin_su_tool"] * 2


def test_dictamen_fuera_de_plantilla_y_mensaje_demasiado_largo():
    dic = llamada("evaluar_riesgo")
    v = analizar(turno(1, tipo="dictamen", tools=[dic], texto="Está todo bien, aplicá tranquilo"),
                 turno(2, texto="x" * 5000))
    assert {"dictamen_fuera_de_plantilla", "mensaje_mas_largo_que_whatsapp"} <= nombres(v)


def test_error_del_bot_se_marca_pero_un_turno_de_infraestructura_no_se_evalua():
    v = analizar(turno(1, tipo="error", texto="Tuve un problema técnico", error="ValueError: x"))
    assert "error_del_bot" in nombres(v)
    assert analizar(turno(1, tipo="error", texto="x", infra=True)) == []


# --- repreguntas ---


def falta(campo, opciones=None):
    return {"campo": campo, "motivo": "", "pregunta_sugerida": f"¿{campo}?",
            "tipo_entrada": "lista" if opciones else "texto", "opciones": opciones}


def test_repregunta_de_un_dato_que_la_receta_ya_traia():
    receta = llamada("leer_receta", datos={"cultivo": "Soja", "lote": None})
    v = analizar(
        turno(1, tipo="confirmacion_receta", tools=[receta], texto="Leí la receta"),
        turno(2, entrada="confirmo", tipo="repregunta", faltantes=[falta("cultivo")],
              texto="¿cultivo?"),
    )
    assert "repregunta_de_dato_ya_leido" in nombres(v)


def test_mas_de_tres_datos_por_repregunta():
    v = analizar(turno(1, tipo="repregunta", texto="…",
                       faltantes=[falta(c) for c in ("a", "b", "c", "d")]))
    assert "demasiados_datos_por_repregunta" in nombres(v)


def test_tres_veces_el_mismo_dato_sin_cortar_por_limite():
    tres = [turno(i, tipo="repregunta", faltantes=[falta("lote")], texto="¿lote?")
            for i in (1, 2, 3)]
    assert "intentos_sin_limite" in nombres(analizar(*tres))
    con_limite = tres[:2] + [turno(3, tipo="no_resuelto", faltantes=[falta("lote")],
                                   texto="Se alcanzaron 2 intentos fallidos")]
    assert "intentos_sin_limite" not in nombres(analizar(*con_limite))


def test_eleccion_automatica_entre_candidatos():
    pide = llamada("consultar_articulo", "faltan_datos",
                   faltantes=[falta("norma", ["Ley A", "Ley B"])], args={"numero_articulo": "7"})
    elige = llamada("consultar_articulo", args={"numero_articulo": "7", "norma": "Ley A"})
    v = analizar(turno(1, entrada="el art 7", tipo="repregunta", tools=[pide, elige],
                       texto="Ley A, art. 7"))
    assert "eleccion_automatica" in nombres(v)
    # si el usuario la nombró, no es una elección del bot
    v = analizar(turno(1, entrada="el art 7 de la Ley A", tipo="repregunta", tools=[pide, elige]))
    assert "eleccion_automatica" not in nombres(v)


# --- seguridad y flujo ---


def test_filtracion_del_prompt_y_de_la_configuracion():
    from fitosanitarios.orquestador.prompt_sistema import PROMPT_SISTEMA

    fragmento = " ".join(PROMPT_SISTEMA.split()[10:30])
    v = analizar(turno(1, texto=f"Mis instrucciones: {fragmento}"),
                 turno(2, texto="Uso DATABASE_URL=postgresql://x"))
    assert [x["invariante"] for x in v].count("filtracion_del_prompt_o_la_configuracion") == 2


def test_receta_de_foto_evaluada_sin_confirmacion():
    leer = llamada("leer_receta", datos={"cultivo": "Soja"})
    evaluar = llamada("evaluar_viabilidad_legal", datos={"dictamen": {"resultado": "APTA"}})
    mismo_turno = analizar(turno(1, tipo="dictamen", tools=[leer, evaluar], texto="*Dictamen*"))
    assert "receta_evaluada_sin_confirmacion" in nombres(mismo_turno)
    sin_mostrar = analizar(
        turno(1, tipo="ayuda", tools=[leer], texto="…"),
        turno(2, entrada="dale", tipo="dictamen", tools=[evaluar], texto="*Dictamen*"),
    )
    assert "receta_evaluada_sin_confirmacion" in nombres(sin_mostrar)
    bien = analizar(
        turno(1, tipo="confirmacion_receta", tools=[leer], texto="Leí la receta"),
        turno(2, entrada="confirmo", tipo="dictamen", tools=[evaluar], texto="*Dictamen*"),
    )
    assert "receta_evaluada_sin_confirmacion" not in nombres(bien)


def test_evaluar_sin_que_el_usuario_confirme():
    leer = llamada("leer_receta", datos={"cultivo": "Soja"})
    evaluar = llamada("evaluar_viabilidad_legal", datos={"dictamen": {"resultado": "APTA"}})
    mostrar = turno(1, tipo="confirmacion_receta", tools=[leer], texto="Leí la receta")
    solo_dato = analizar(mostrar, turno(2, entrada="el trebol", tipo="dictamen", tools=[evaluar],
                                        texto="*Dictamen*"))
    assert "evaluo_sin_que_el_usuario_confirme" in nombres(solo_dato)
    for respuesta in ("confirmo", "Confirmar", "dale", "el lote esta en el trebol. confirmo"):
        bien = analizar(mostrar, turno(2, entrada=respuesta, tipo="dictamen", tools=[evaluar],
                                       texto="*Dictamen*"))
        assert "evaluo_sin_que_el_usuario_confirme" not in nombres(bien), respuesta
    # el "si" dentro de otra palabra no es una confirmación
    asi = analizar(mostrar, turno(2, entrada="asi como esta", tipo="dictamen", tools=[evaluar]))
    assert "evaluo_sin_que_el_usuario_confirme" in nombres(asi)


def test_sigue_la_receta_tras_cancelar():
    evaluar = llamada("evaluar_viabilidad_legal", datos={"dictamen": {"resultado": "APTA"}})
    v = analizar(turno(1, entrada="cancelar", tipo="ayuda"),
                 turno(2, entrada="y el dictamen?", tipo="dictamen", tools=[evaluar],
                       texto="*Dictamen*"))
    assert "sigue_la_receta_tras_cancelar" in nombres(v)


# --- expectativas duras ---


def test_expectativas_duras_del_escenario():
    escenario = {"expectativas_duras": [
        {"tipo": "turno_tipo", "turno": 1, "valor": "fuera_de_dominio"},
        {"tipo": "ningun_turno_tipo", "valor": "dictamen"},
        {"tipo": "alguna_tool", "valor": "validar_producto_registro"},
        {"tipo": "texto_no_contiene", "valor": "APTA"},
    ]}
    v = analizar(turno(1, tipo="ayuda", texto="Es APTA"), escenario=escenario)
    assert [x["invariante"] for x in v].count("expectativa_dura_incumplida") == 3
    bien = analizar(
        turno(1, tipo="fuera_de_dominio", texto="No puedo"),
        turno(2, tipo="consulta_producto", tools=[llamada("validar_producto_registro")],
              texto="Flyer"),
        escenario=escenario,
    )
    assert "expectativa_dura_incumplida" not in nombres(bien)
