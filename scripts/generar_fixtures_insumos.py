"""Genera las fixtures sintéticas de insumos de tests/fixtures/insumos/ (Fase 3).

Contenido ficticio, con la misma estructura que usan los ejemplos de la
skill agente-fitosanitarios (San Carlos Centro, Ordenanza 914/2018, art. 8),
para tener continuidad con esos casos de referencia en fases futuras. Se
corre una sola vez para (re)generar las fixtures; no es parte del pipeline
de carga en sí.

Uso: uv run python scripts/generar_fixtures_insumos.py
"""

import json
from pathlib import Path

from fpdf import FPDF

BASE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "insumos"


def escribir_pdf(ruta: Path, titulo: str, articulos: list[tuple[str, str]]) -> None:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_x(pdf.l_margin)  # multi_cell no resetea X solo; sin esto, la 2da llamada falla
    pdf.multi_cell(0, 10, titulo)
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 11)
    for numero, texto in articulos:
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 7, f"Articulo {numero}.-")
        pdf.set_font("Helvetica", "", 11)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 7, texto)
        pdf.ln(2)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(ruta))


def main() -> None:
    # --- San Carlos Centro (Santa Fe) ---

    localidad_scc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "tipo": "limite", "nombre": "San Carlos Centro", "provincia": "santa-fe"
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [-60.660, -32.930], [-60.640, -32.930],
                        [-60.640, -32.910], [-60.660, -32.910],
                        [-60.660, -32.930],
                    ]],
                },
            },
            {
                "type": "Feature",
                "properties": {"tipo": "escuela", "nombre": "Escuela N 12"},
                "geometry": {"type": "Point", "coordinates": [-60.6505, -32.9295]},
            },
            {
                "type": "Feature",
                "properties": {"tipo": "curso_agua", "nombre": "Arroyo del Medio (ficticio)"},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-60.660, -32.920], [-60.640, -32.918]],
                },
            },
            {
                "type": "Feature",
                "properties": {"tipo": "zona_urbana", "nombre": "Casco urbano"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [-60.652, -32.922], [-60.648, -32.922],
                        [-60.648, -32.918], [-60.652, -32.918],
                        [-60.652, -32.922],
                    ]],
                },
            },
        ],
    }
    (BASE / "santa-fe" / "san-carlos-centro" / "localidad.geojson").write_text(
        json.dumps(localidad_scc, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    escribir_pdf(
        BASE / "santa-fe" / "san-carlos-centro" / "ordenanza-914-2018.pdf",
        "Ordenanza 914/2018 - Aplicacion de fitosanitarios (texto ficticio, fixture de prueba)",
        [
            ("8", "Prohibese la aplicacion terrestre de fitosanitarios a menos de 100 metros "
                  "de establecimientos educativos, cualquiera sea la banda toxicologica del "
                  "producto utilizado."),
            ("9", "Prohibese la aplicacion aerea de fitosanitarios a menos de 200 metros de "
                  "establecimientos educativos. Debera notificarse a la direccion del "
                  "establecimiento con 48 horas de anticipacion."),
            ("10", "Prohibese la aplicacion de fitosanitarios, cualquiera sea su modalidad, a "
                   "menos de 50 metros de cursos de agua permanentes o transitorios."),
        ],
    )

    # --- Colonia Vecina (Santa Fe), localidad limitrofe mas simple ---

    localidad_cv = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "tipo": "limite", "nombre": "Colonia Vecina", "provincia": "santa-fe"
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [-60.630, -32.930], [-60.610, -32.930],
                        [-60.610, -32.910], [-60.630, -32.910],
                        [-60.630, -32.930],
                    ]],
                },
            },
            {
                "type": "Feature",
                "properties": {"tipo": "escuela", "nombre": "Escuela Rural N 3"},
                "geometry": {"type": "Point", "coordinates": [-60.6295, -32.9205]},
            },
        ],
    }
    (BASE / "santa-fe" / "colonia-vecina" / "localidad.geojson").write_text(
        json.dumps(localidad_cv, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    escribir_pdf(
        BASE / "santa-fe" / "colonia-vecina" / "ordenanza-45-2019.pdf",
        "Ordenanza 45/2019 - Aplicacion de fitosanitarios (texto ficticio, fixture de prueba)",
        [
            ("5", "Prohibese la aplicacion terrestre de fitosanitarios a menos de 150 metros "
                  "de establecimientos educativos."),
        ],
    )

    # --- Provincial: Santa Fe ---

    escribir_pdf(
        BASE / "santa-fe" / "ley-13740-2017.pdf",
        "Ley 13.740/2017 - Fitosanitarios, Provincia de Santa Fe "
        "(texto ficticio, fixture de prueba)",
        [
            ("1", "La presente ley regula el uso de productos fitosanitarios en todo el "
                  "territorio de la provincia de Santa Fe."),
            ("2", "Prohibese la aplicacion de fitosanitarios de cualquier modalidad a menos de "
                  "300 metros de zonas urbanas, salvo que una norma municipal fije una "
                  "distancia mayor."),
            ("3", "Los municipios y comunas podran dictar normas mas restrictivas que la "
                  "presente ley, nunca menos restrictivas."),
        ],
    )

    # --- Nacional (sin filas en reglas.csv: es solo para consultas) ---

    escribir_pdf(
        BASE / "normativa-general" / "nacional" / "ley-27302-2016.pdf",
        "Ley 27.302/2016 - Presupuestos minimos fitosanitarios (texto ficticio, fixture de prueba)",
        [
            ("1", "Establecense los presupuestos minimos de proteccion ambiental para la "
                  "aplicacion de productos fitosanitarios en todo el territorio nacional."),
            ("2", "Las provincias y municipios conservan la facultad de dictar normas "
                  "complementarias mas restrictivas."),
        ],
    )

    # Un solo reglas.csv para todas las jurisdicciones (ver docs/contrato-insumos.md).
    # La provincial trae una fila S (condicional) para probar que se carga aparte.
    (BASE / "reglas.csv").write_text(
        "provincia,jurisdiccion,tipo_zona,tipo_aplicacion,banda_toxicologica,distancia_min_m,"
        "permitido,condiciones,norma,articulo,observaciones\n"
        "santa-fe,san-carlos-centro,escuela,terrestre,todas,100,N,,ordenanza-914-2018,8,\n"
        "santa-fe,san-carlos-centro,escuela,aerea,todas,200,N,,ordenanza-914-2018,9,"
        "Aviso previo a la direccion de la escuela\n"
        "santa-fe,san-carlos-centro,curso_agua,todas,todas,50,N,,ordenanza-914-2018,10,\n"
        "santa-fe,colonia-vecina,escuela,terrestre,todas,150,N,,ordenanza-45-2019,5,\n"
        ",santa-fe,zona_urbana,todas,todas,300,N,,ley-13740-2017,2,\n"
        ",santa-fe,zona_urbana,aerea,II,100,S,\"con autorizacion del municipio\","
        "ley-13740-2017,2,\n",
        encoding="utf-8",
    )

    print("fixtures generadas en", BASE)


if __name__ == "__main__":
    main()
