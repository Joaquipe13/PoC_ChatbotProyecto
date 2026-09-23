"""Búsqueda híbrida (similitud + BM25 fusionados), con los números reales del marbete de
Banvel que la motivaron (ver DECISIONES.md, "Búsqueda híbrida en los marbetes")."""

from fitosanitarios.servicios.busqueda_hibrida import bm25, fusionar, seleccionar

# Un marbete de juguete: "lot" y "tiemp" están en todas las páginas; "reingres", en una.
PAGINAS = [
    ["herbic", "lot", "tiemp", "composicion"],
    ["residu", "carenci", "reingres", "lot", "tiemp", "resistent"],
    ["dosis", "lot", "tiemp", "maiz"],
    ["precaucion", "lot", "tiemp", "guant"],
]
PREGUNTA = ["cuant", "tiemp", "esper", "reingres", "lot"]


def test_bm25_pesa_las_palabras_raras():
    scores = bm25(PREGUNTA, PAGINAS)
    assert max(range(4), key=lambda i: scores[i]) == 1  # la única con "reingres"
    assert scores[0] == scores[2] == scores[3]  # "lot" y "tiemp" no distinguen


def test_la_fusion_sube_lo_que_esta_arriba_en_cualquiera_de_las_dos():
    # La vectorial la deja tercera; por palabras es primera: en la fusión gana.
    puntajes = fusionar([0.39, 0.38, 0.40, 0.10], [0.0, 3.1, 0.0, 0.0])
    assert puntajes[0].indice == 1


def test_entra_por_palabras_aunque_no_llegue_al_umbral_de_similitud():
    """El caso de Banvel: el fragmento del reingreso tiene 0,38 de similitud (umbral 0,42)
    en un marbete de unos 20 fragmentos; ninguno llega al umbral."""
    paginas = PAGINAS + [["dosis", "lot", "tiemp", f"cultiv{i}"] for i in range(16)]
    vector = [0.39, 0.38, 0.40, 0.10] + [0.35] * 16
    elegidos = seleccionar(vector, paginas, PREGUNTA, 0.42, top_k=5)
    assert [p.indice for p in elegidos] == [1]


def test_una_raiz_compartida_por_casualidad_no_alcanza():
    """"¿Quién ganó el mundial?" -> "gan", como "ganado": BM25 alto pero ningún parecido de
    significado."""
    paginas = [["ganad", "gan", "pec"], ["dosis", "maiz"]]
    elegidos = seleccionar([0.03, 0.33], paginas, ["gan", "mundial"], 0.42, top_k=5)
    assert elegidos == []


def test_lo_que_pasa_el_umbral_de_similitud_entra_igual():
    elegidos = seleccionar([0.60, 0.20], [["x"], ["y"]], ["z"], 0.42, top_k=5)
    assert [p.indice for p in elegidos] == [0]
