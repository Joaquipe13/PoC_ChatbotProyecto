"""Carga de marbetes al índice del RAG, con un PDF generado (sin los reales)."""

from fpdf import FPDF

from fitosanitarios.senasa.loader_marbetes import (
    cargar_marbetes,
    fragmentos_de_paginas,
    marbetes_por_registro,
)


def test_los_fragmentos_guardan_su_pagina():
    paginas = ["", "Carencia: cítricos 7 días. " * 10, "Precauciones: usar guantes. " * 60]
    fragmentos = fragmentos_de_paginas(paginas)
    assert {p for p, _, _ in fragmentos} == {2, 3}
    assert [o for p, o, _ in fragmentos if p == 3][:2] == [0, 1]  # la 3 se partió en varios


def test_los_pdf_se_agrupan_por_numero_de_inscripcion(tmp_path):
    nombres = (
        "30116_1_Marbete.pdf", "30116_2_Marbete.pdf", "30116_0_HDS.pdf", "41881_1_Marbete.pdf"
    )
    for nombre in nombres:
        (tmp_path / nombre).write_bytes(b"")
    grupos = marbetes_por_registro(tmp_path)
    assert {k: len(v) for k, v in grupos.items()} == {"30116": 2, "41881": 1}


def _pdf(ruta, paginas: list[str]) -> None:
    pdf = FPDF()
    pdf.set_font("Helvetica", size=11)
    for texto in paginas:
        pdf.add_page()
        pdf.multi_cell(0, 6, texto)
    pdf.output(str(ruta))


def test_carga_un_marbete_con_sus_fragmentos(conexion, modelo_embeddings, tmp_path):
    with conexion.cursor() as cur:
        cur.execute("SELECT id, numero_inscripcion FROM catalogo.producto ORDER BY id LIMIT 1")
        producto_id, registro = cur.fetchone()
    _pdf(tmp_path / f"{registro}_1_Marbete.pdf", [
        "PRECAUCIONES: usar guantes y mascara durante la aplicacion del producto. " * 3,
        "CARENCIA: citricos 7 dias; hortalizas 3 dias. No reingresar hasta que seque. " * 3,
    ])
    try:
        resumen = cargar_marbetes(
            conexion, tmp_path, modelo_embeddings, solo_faltantes=False
        )
        assert resumen["productos"] == 1 and resumen["documentos"] == 1
        with conexion.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT pagina FROM catalogo.fragmento_marbete WHERE producto_id = %s",
                (producto_id,),
            )
            assert sorted(r[0] for r in cur.fetchall()) == [1, 2]
    finally:
        with conexion.cursor() as cur:
            cur.execute(
                "DELETE FROM catalogo.documento WHERE producto_id = %s AND tipo = 'marbete'",
                (producto_id,),
            )
        conexion.commit()
