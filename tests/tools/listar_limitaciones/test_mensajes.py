"""Plantilla de `listar_limitaciones`, en particular la convención de
`DISTANCIA_SIN_LIMITE_M` (ver DECISIONES.md, "Localidades y normas sin
fuente oficial")."""

from fitosanitarios.dominio.modelos import ResultadoTool
from fitosanitarios.servicios.reglas import DISTANCIA_SIN_LIMITE_M
from fitosanitarios.tools.listar_limitaciones.mensajes import plantilla_limitaciones


def _regla(distancia, tipo_aplicacion="terrestre", bandas=None):
    return {
        "tipo_zona": "zona_urbana", "tipo_aplicacion": tipo_aplicacion,
        "bandas": bandas or ["Ia", "Ib"], "distancia_min_m": distancia,
        "norma": "ordenanza-1174-2019", "articulo": None, "jurisdiccion_id": "sastre",
        "observaciones": None, "condiciones": None, "extraida_de_pdf": False,
    }


def test_distancia_sin_limite_se_muestra_como_toda_la_jurisdiccion():
    resultado = ResultadoTool(
        estado="ok",
        datos={
            "localidad": "Sastre", "filtros": {},
            "prohibiciones": [_regla(DISTANCIA_SIN_LIMITE_M)], "condicionales": [],
        },
    )
    texto = plantilla_limitaciones(None, [resultado])
    assert "no se puede aplicar en toda la jurisdicción" in texto
    assert str(int(DISTANCIA_SIN_LIMITE_M)) not in texto


def test_distancia_normal_se_muestra_en_metros():
    resultado = ResultadoTool(
        estado="ok",
        datos={
            "localidad": "Sastre", "filtros": {},
            "prohibiciones": [_regla(1000)], "condicionales": [],
        },
    )
    texto = plantilla_limitaciones(None, [resultado])
    assert "a menos de 1000 m no se puede aplicar" in texto


def _restriccion(tipo_aplicacion, bandas, distancia, norma, articulo=None, excepciones=()):
    prohibicion = {**_regla(distancia, tipo_aplicacion, bandas), "norma": norma,
                   "articulo": articulo, "observaciones": "texto largo de la fuente"}
    return {"prohibicion": prohibicion, "excepciones": list(excepciones)}


def _a_1500(restricciones, localidad="Sastre"):
    return ResultadoTool(
        estado="ok",
        datos={
            "localidad": localidad, "filtros": {"tipo_zona": "zona_urbana"},
            "distancia_m": 1500, "restricciones": restricciones,
            "prohibiciones": [], "condicionales": [],
        },
    )


def test_a_una_distancia_dice_que_aplicaciones_y_bandas_se_pueden_sin_transcribir():
    excepcion = {**_regla(500, "aerea", ["II"]), "norma": "ley-055297-2017", "articulo": "51",
                 "condiciones": "Excepcion para clase B entre 500 y 3000 m: ordenanza..."}
    texto = plantilla_limitaciones(None, [_a_1500([
        _restriccion("aerea", ["Ia", "Ib"], 3000, "ley-11273-1995", "33"),
        _restriccion("aerea", ["II"], 3000, "ley-11273-1995", "33", [excepcion]),
        _restriccion("aerea", ["todas"], 3000, "ordenanza-1174-2019"),
        _restriccion("terrestre", ["Ia", "Ib"], DISTANCIA_SIN_LIMITE_M, "ordenanza-1174-2019"),
    ])])
    assert texto.startswith(
        "*A 1500 m de la zona urbana en Sastre*\n"
        "- *Terrestre:* ✅ II, III y IV · ❌ Ia y Ib\n"
        "- *Aérea:* ❌ ninguna banda"
    )
    assert "texto largo" not in texto and "Excepcion para clase B" not in texto


def test_a_una_distancia_la_excepcion_solo_referencia_la_norma():
    excepcion = {**_regla(500, "aerea", ["II"]), "norma": "ley-055297-2017", "articulo": "51",
                 "jurisdiccion_id": None, "condiciones": "condiciones largas"}
    texto = plantilla_limitaciones(None, [_a_1500([
        _restriccion("aerea", ["II"], 3000, "ley-11273-1995", "33", [excepcion]),
    ], localidad="Rafaela")])
    assert (
        "- *Aérea:* ✅ Ia, Ib, III y IV · ⚠️ II solo con excepción (Ley 055297/2017, art. 51)"
        in texto
    )
    assert "condiciones largas" not in texto


def test_listado_general_no_transcribe_observaciones_ni_condiciones():
    condicional = {**_regla(500, "aerea", ["II"]), "condiciones": "condiciones largas",
                   "observaciones": "nota larga", "norma": "ley-055297-2017", "articulo": "51"}
    resultado = ResultadoTool(
        estado="ok",
        datos={
            "localidad": "Sastre", "filtros": {},
            "prohibiciones": [{**_regla(1000), "observaciones": "nota larga"}],
            "condicionales": [condicional],
        },
    )
    texto = plantilla_limitaciones(None, [resultado])
    assert "nota larga" not in texto and "condiciones largas" not in texto
    assert "se puede desde 500 m con condiciones (Ley 055297/2017, art. 51)" in texto


def test_con_producto_dice_con_que_banda_se_filtro():
    resultado = ResultadoTool(
        estado="ok",
        datos={
            "localidad": "El Trébol", "filtros": {"bandas": ["III"]},
            "prohibiciones": [_regla(500, "aerea", ["III", "IV"])], "condicionales": [],
            "producto": {"marca": "Tordon D 30", "numero_inscripcion": "30735",
                         "banda": "III", "variantes": []},
        },
    )
    texto = plantilla_limitaciones(None, [resultado])
    assert texto.startswith("*Limitaciones en El Trébol*\n\nPara *Tordon D 30*: banda III (azul)")


def test_con_producto_a_una_distancia_tambien_dice_la_banda():
    resultado = ResultadoTool(
        estado="ok",
        datos={
            "localidad": "El Trébol", "filtros": {"bandas": ["IV"]}, "distancia_m": 300.0,
            "prohibiciones": [], "condicionales": [], "restricciones": [],
            "producto": {"marca": "Roundup", "numero_inscripcion": None, "banda": "IV",
                         "variantes": ["Roundup Fg", "Roundup Wg"]},
        },
    )
    texto = plantilla_limitaciones(None, [resultado])
    assert "Para *Roundup*: banda IV (verde), la de todas sus variantes registradas" in texto


def test_arriba_de_la_lista_dice_la_distancia_que_rige():
    regla = _regla(3000, "aerea", ["todas"])
    resultado = ResultadoTool(
        estado="ok",
        datos={
            "localidad": "Sastre", "filtros": {"bandas": ["III"]},
            "prohibiciones": [regla], "condicionales": [],
            "que_rige": [{
                "tipo_zona": "zona_urbana", "tipo_aplicacion": "aerea",
                "tramos": [{"bandas": ["III"], "regla": regla, "con_excepciones": False}],
            }],
        },
    )
    texto = plantilla_limitaciones(None, [resultado])
    assert "*Distancia mínima que rige*\n- Zona urbana · aérea: banda III: 3000 m (" in texto
    assert texto.index("Distancia mínima que rige") < texto.index("*Aplicación aérea*")


def test_la_distancia_que_rige_marca_excepciones_y_bandas_sin_distancia():
    regla = _regla(500, "terrestre", ["Ia", "Ib", "II"])
    resultado = ResultadoTool(
        estado="ok",
        datos={
            "localidad": "El Trébol", "filtros": {},
            "prohibiciones": [regla], "condicionales": [],
            "que_rige": [{
                "tipo_zona": "zona_urbana", "tipo_aplicacion": "terrestre",
                "tramos": [
                    {"bandas": ["Ia", "Ib", "II"], "regla": regla, "con_excepciones": True},
                    {"bandas": ["III", "IV"], "regla": None, "con_excepciones": False},
                ],
            }],
        },
    )
    texto = plantilla_limitaciones(None, [resultado])
    assert (
        "- Zona urbana · terrestre: bandas Ia, Ib, II: 500 m, salvo excepciones "
        in texto
    )
    assert "bandas III, IV: sin distancia fija" in texto
