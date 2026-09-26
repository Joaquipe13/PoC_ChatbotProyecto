"""`cargar_reglas` con un cursor simulado: la lógica de reparto por jurisdicción,
sin Postgres. La carga real contra la base está en `test_loaders_integracion.py`."""

import pytest

from fitosanitarios.insumos import loader_reglas
from fitosanitarios.insumos.loader_reglas import cargar_reglas
from fitosanitarios.insumos.reglas_csv import COLUMNAS

CABECERA = ",".join(COLUMNAS) + "\n"


class CursorFalso:
    """Una provincia (santa-fe), una localidad (el-trebol) y sus normas."""

    def __init__(self):
        self.ejecutadas: list[tuple[str, tuple]] = []
        self._resultado: list[tuple] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        sql = " ".join(sql.split())
        self.ejecutadas.append((sql, tuple(params)))
        self._resultado = []
        if sql.startswith("SELECT id FROM territorio.provincia"):
            self._resultado = [(1,)] if params[0] == "santa-fe" else []
        elif sql.startswith("SELECT id FROM territorio.localidad"):
            self._resultado = [(10,)] if params[0] == "el-trebol" else []
        elif sql.startswith("SELECT n.archivo, n.id FROM territorio.norma n"):
            if "'provincial'" in sql:
                self._resultado = [("ley-11273-1995", 100), ("ley-055297-2017", 101)]
            elif "'municipal'" in sql:
                self._resultado = [("ordenanza-841-2010", 200)]
            else:
                self._resultado = [("ley-1-2000", 300)]
        elif sql.startswith("SELECT id FROM territorio.articulo"):
            norma_id, numero = params
            self._resultado = [(norma_id * 1000 + int(numero),)] if int(numero) < 90 else []

    def fetchone(self):
        return self._resultado[0] if self._resultado else None

    def fetchall(self):
        return self._resultado

    def de_tipo(self, prefijo: str) -> list[tuple[str, tuple]]:
        return [e for e in self.ejecutadas if e[0].startswith(prefijo)]


class ConexionFalsa:
    def __init__(self):
        self.cur = CursorFalso()
        self.commits = 0

    def cursor(self):
        return self.cur

    def commit(self):
        self.commits += 1


@pytest.fixture
def insumos(tmp_path):
    (tmp_path / "santa-fe" / "el-trebol").mkdir(parents=True)
    (tmp_path / "normativa-general" / "nacional").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def extracciones(monkeypatch):
    """Registra los alcances a los que se les leería el PDF."""
    llamadas: list[tuple] = []

    def falsa(cur, filtro, params):
        llamadas.append((filtro, params))
        return 0

    monkeypatch.setattr(loader_reglas, "extraer_reglas_de_pdfs", falsa)
    return llamadas


def _escribir(insumos, *filas: str) -> None:
    (insumos / "reglas.csv").write_text(CABECERA + "\n".join(filas) + "\n", encoding="utf-8")


PROHIBICION = ",santa-fe,zona_urbana,aerea,Ia;Ib,3000,N,,ley-11273-1995,33,"
CONDICIONAL = ',santa-fe,zona_urbana,aerea,II,500,S,"con ordenanza",ley-055297-2017,51,'
MUNICIPAL = "santa-fe,el-trebol,zona_urbana,aerea,todas,500,N,,ordenanza-841-2010,6,"


def test_cada_fila_va_a_la_norma_de_su_jurisdiccion_con_permitido_y_condiciones(
    insumos, extracciones
):
    _escribir(insumos, PROHIBICION, CONDICIONAL, MUNICIPAL)
    conn = ConexionFalsa()

    total = cargar_reglas(conn, insumos)

    assert total == 3 and conn.commits == 1
    insertadas = [p for _, p in conn.cur.de_tipo("INSERT INTO territorio.regla_distancia")]
    # (norma_id, articulo_id, tipo_zona, aplicacion, bandas, distancia, permitido, condiciones, obs)
    prohibicion = (100, 100033, "zona_urbana", "aerea", ["Ia", "Ib"], 3000.0, False, None, None)
    condicional = (101, 101051, "zona_urbana", "aerea", ["II"], 500.0, True, "con ordenanza", None)
    assert prohibicion in insertadas
    assert condicional in insertadas
    assert (200, 200006, "zona_urbana", "aerea", ["todas"], 500.0, False, None, None) in insertadas


def test_sin_filas_las_municipales_y_provinciales_se_leen_del_pdf_pero_la_nacional_no(
    insumos, extracciones
):
    _escribir(insumos)  # solo el encabezado
    conn = ConexionFalsa()

    total = cargar_reglas(conn, insumos)

    assert total == 0
    assert sorted(f for f, _ in extracciones) == [
        "n.ambito = 'municipal' AND n.localidad_id = %s",
        "n.ambito = 'provincial' AND n.provincia_id = %s",
    ]
    # La nacional solo se limpia: sin reglas viejas, y nunca se le leen distancias del PDF.
    borrados = [e for e in conn.cur.de_tipo("DELETE FROM territorio.regla_distancia")]
    assert any("'nacional'" in sql for sql, _ in borrados)
    assert not conn.cur.de_tipo("INSERT")


def test_sin_reglas_csv_se_comporta_como_un_csv_vacio(insumos, extracciones):
    conn = ConexionFalsa()
    assert cargar_reglas(conn, insumos) == 0
    assert len(extracciones) == 2


def test_una_jurisdiccion_con_filas_no_lee_su_pdf_y_reemplaza_lo_anterior(insumos, extracciones):
    _escribir(insumos, MUNICIPAL)
    conn = ConexionFalsa()
    cargar_reglas(conn, insumos)
    # La municipal tiene filas (CSV); la provincial no (PDF).
    assert [f for f, _ in extracciones] == ["n.ambito = 'provincial' AND n.provincia_id = %s"]
    assert conn.cur.de_tipo("DELETE FROM territorio.regla_distancia")


def test_jurisdiccion_sin_carpeta_falla_antes_de_tocar_la_base(insumos, extracciones):
    fantasma = "santa-fe,pueblo-fantasma,escuela,terrestre,todas,100,N,,x-1-2000,1,"
    _escribir(insumos, PROHIBICION, fantasma)
    conn = ConexionFalsa()
    with pytest.raises(ValueError, match="pueblo-fantasma"):
        cargar_reglas(conn, insumos)
    assert not conn.cur.de_tipo("DELETE") and not conn.cur.de_tipo("INSERT")
    assert conn.commits == 0


def test_fila_con_formato_invalido_falla_antes_de_tocar_la_base(insumos, extracciones):
    _escribir(insumos, PROHIBICION.replace(",N,", ",TAL VEZ,"))
    conn = ConexionFalsa()
    with pytest.raises(ValueError, match="línea 2"):
        cargar_reglas(conn, insumos)
    assert not conn.cur.ejecutadas


def test_una_norma_de_otra_jurisdiccion_no_se_resuelve(insumos, extracciones):
    # ordenanza-841-2010 es de El Trébol: citada desde la provincia no existe.
    _escribir(insumos, ",santa-fe,zona_urbana,aerea,todas,500,N,,ordenanza-841-2010,6,")
    with pytest.raises(ValueError, match="línea 2.*ordenanza-841-2010"):
        cargar_reglas(ConexionFalsa(), insumos)


def test_articulo_inexistente_falla_con_la_linea(insumos, extracciones):
    _escribir(insumos, ",santa-fe,zona_urbana,aerea,Ia,3000,N,,ley-11273-1995,99,")
    with pytest.raises(ValueError, match="línea 2.*artículo 99"):
        cargar_reglas(ConexionFalsa(), insumos)


def test_una_regla_nacional_explicita_se_carga(insumos, extracciones):
    _escribir(insumos, ",ARGENTINA,zona_urbana,todas,todas,10,N,,ley-1-2000,1,")
    conn = ConexionFalsa()
    assert cargar_reglas(conn, insumos) == 1
    (fila,) = [p for _, p in conn.cur.de_tipo("INSERT INTO territorio.regla_distancia")]
    assert fila[0] == 300
