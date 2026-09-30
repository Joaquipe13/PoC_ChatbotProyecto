from fitosanitarios.dominio.motivos import DESCRIPCION_MOTIVO, MotivoNoResuelto


def test_todos_los_motivos_tienen_descripcion():
    for motivo in MotivoNoResuelto:
        assert motivo in DESCRIPCION_MOTIVO
        assert DESCRIPCION_MOTIVO[motivo].strip() != ""


def test_son_siete_motivos_del_nucleo_segun_la_skill_mas_los_de_extensiones():
    # La skill documenta 7 para el núcleo (RF1-5, RF10, RF11): `dosis_no_comparable` y
    # `servicio_no_disponible` se sacaron el 29/09/2026 porque nada los emitía.
    # Los otros 4 son extensiones: 2 de la Fase 9 (RF6/RF7, fuera del alcance de
    # la skill, ver DECISIONES.md), `articulo_no_encontrado`, de la consulta de
    # artículos por número, y `marbete_sin_respaldo`, del RAG de marbetes. No cuentan
    # contra "la skill es la fuente de verdad" porque la skill nunca definió motivos
    # para esos casos.
    motivos_del_nucleo = {
        "jurisdiccion_no_cubierta", "sin_regla_aplicable", "producto_no_encontrado",
        "sin_usos_registrados", "normativa_sin_respaldo", "imagen_ilegible",
        "limite_repreguntas",
    }
    todos = {m.value for m in MotivoNoResuelto}
    assert motivos_del_nucleo <= todos
    assert len(motivos_del_nucleo) == 7
    assert len(todos - motivos_del_nucleo) == 4


def test_motivo_es_comparable_con_string():
    assert MotivoNoResuelto.PRODUCTO_NO_ENCONTRADO == "producto_no_encontrado"
