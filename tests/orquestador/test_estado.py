from fitosanitarios.orquestador.estado import LIMITE_INTENTOS_POR_CAMPO, ContadorRepreguntas


def test_primer_intento_no_excede_limite():
    contador = ContadorRepreguntas()
    contador.registrar_intento("thread-1", "lote")
    assert not contador.excede_limite("thread-1", "lote")


def test_dos_intentos_excede_el_limite():
    contador = ContadorRepreguntas()
    for _ in range(LIMITE_INTENTOS_POR_CAMPO):
        contador.registrar_intento("thread-1", "lote")
    assert contador.excede_limite("thread-1", "lote")


def test_campos_distintos_no_se_mezclan():
    contador = ContadorRepreguntas()
    contador.registrar_intento("thread-1", "lote")
    contador.registrar_intento("thread-1", "lote")
    assert contador.excede_limite("thread-1", "lote")
    assert not contador.excede_limite("thread-1", "cultivo")


def test_threads_distintos_no_se_mezclan():
    contador = ContadorRepreguntas()
    contador.registrar_intento("thread-1", "lote")
    contador.registrar_intento("thread-1", "lote")
    assert contador.excede_limite("thread-1", "lote")
    assert not contador.excede_limite("thread-2", "lote")


def test_resetear_campo_borra_el_conteo():
    contador = ContadorRepreguntas()
    contador.registrar_intento("thread-1", "lote")
    contador.registrar_intento("thread-1", "lote")
    contador.resetear_campo("thread-1", "lote")
    assert not contador.excede_limite("thread-1", "lote")


def test_resetear_thread_borra_todos_los_campos():
    contador = ContadorRepreguntas()
    contador.registrar_intento("thread-1", "lote")
    contador.registrar_intento("thread-1", "cultivo")
    contador.resetear_thread("thread-1")
    assert not contador.excede_limite("thread-1", "lote")
    assert not contador.excede_limite("thread-1", "cultivo")


def test_registrar_intento_devuelve_el_conteo_actual():
    contador = ContadorRepreguntas()
    assert contador.registrar_intento("thread-1", "lote") == 1
    assert contador.registrar_intento("thread-1", "lote") == 2
