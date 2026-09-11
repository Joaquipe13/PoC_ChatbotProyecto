from fitosanitarios.dominio.motivos import DESCRIPCION_MOTIVO, MotivoNoResuelto


def test_todos_los_motivos_tienen_descripcion():
    for motivo in MotivoNoResuelto:
        assert motivo in DESCRIPCION_MOTIVO
        assert DESCRIPCION_MOTIVO[motivo].strip() != ""


def test_son_nueve_motivos_segun_la_skill():
    assert len(list(MotivoNoResuelto)) == 9


def test_motivo_es_comparable_con_string():
    assert MotivoNoResuelto.PRODUCTO_NO_ENCONTRADO == "producto_no_encontrado"
