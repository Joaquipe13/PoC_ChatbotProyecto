from fitosanitarios.llm.fake import ClienteLLMFake


def test_fake_devuelve_respuestas_en_orden():
    fake = ClienteLLMFake(respuestas=["uno", "dos"])
    assert fake.generar("cualquier prompt") == "uno"
    assert fake.generar("otro prompt") == "dos"


def test_fake_registra_llamadas():
    fake = ClienteLLMFake(respuestas=["ok"])
    fake.generar("hola", system="sos un asistente")
    assert fake.llamadas == [{"prompt": "hola", "system": "sos un asistente"}]


def test_fake_con_funcion_responder():
    fake = ClienteLLMFake(responder=lambda prompt, system: f"eco:{prompt}")
    assert fake.generar("hola") == "eco:hola"


def test_fake_sin_respuestas_configuradas_devuelve_vacio():
    fake = ClienteLLMFake()
    assert fake.generar("hola") == ""
