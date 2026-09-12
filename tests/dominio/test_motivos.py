from fitosanitarios.dominio.motivos import DESCRIPCION_MOTIVO, MotivoNoResuelto


def test_todos_los_motivos_tienen_descripcion():
    for motivo in MotivoNoResuelto:
        assert motivo in DESCRIPCION_MOTIVO
        assert DESCRIPCION_MOTIVO[motivo].strip() != ""


def test_son_nueve_motivos_del_nucleo_segun_la_skill_mas_los_de_extensiones():
    # La skill documenta exactamente 9 para el núcleo (RF1-5, RF10, RF11).
    # Los otros 2 son de la Fase 9 (RF6/RF7, fuera del alcance de la skill,
    # ver DECISIONES.md) -- no cuentan contra "la skill es la fuente de
    # verdad" porque la skill nunca definió motivos para esos RF.
    motivos_del_nucleo = {
        "jurisdiccion_no_cubierta", "sin_regla_aplicable", "producto_no_encontrado",
        "sin_usos_registrados", "dosis_no_comparable", "normativa_sin_respaldo",
        "imagen_ilegible", "limite_repreguntas", "servicio_no_disponible",
    }
    todos = {m.value for m in MotivoNoResuelto}
    assert motivos_del_nucleo <= todos
    assert len(motivos_del_nucleo) == 9
    assert len(todos - motivos_del_nucleo) == 2


def test_motivo_es_comparable_con_string():
    assert MotivoNoResuelto.PRODUCTO_NO_ENCONTRADO == "producto_no_encontrado"
