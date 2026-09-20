"""Genera 3 recetas de ejemplo para probar el flujo completo (leer_receta +
evaluar_viabilidad_legal) contra los datos reales de El Trébol cargados en
esta sesión (ver DECISIONES.md, "Carga de datos reales de El Trébol").

A diferencia de `generar_fixtures_recetas.py` (Fase 4, casos sintéticos para
probar extracción de campos), estas 3 usan productos y dosis reales del
catálogo SENASA ya cargado, pensadas para ejercitar las reglas de la
Ordenanza 841/2010 de El Trébol (arts. 6 y 7).

Las imágenes no llevan localidad: se le dice al bot por texto ("en El
Trébol"). El sistema ya no usa la ubicación del lote; informa la banda de la
aplicación y la distancia mínima según la localidad (ver DECISIONES.md).

No se versionan (`data/recetas_ejemplo/` está en `.gitignore`, salvo el
README).

Uso: uv run python scripts/generar_recetas_ejemplo_el_trebol.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generar_fixtures_recetas import dibujar_receta  # noqa: E402

BASE = Path(__file__).resolve().parent.parent / "data" / "recetas_ejemplo"

CASOS = [
    {
        "archivo": "01_apta_terrestre.jpg",
        "numero": "1001",
        "campos": {
            "Cultivo": "Soja",
            "Lote": "8",
            "Adversidad": "Chinche de la alfalfa",
            "Producto": "Flyer 10 Ec - 170 cm3/ha",
            "Superficie": "40 ha",
            "Tipo de aplicacion": "Terrestre",
        },
        "nota": (
            "Reg. SENASA 41881, Banda II. Dosis 170 cm3/ha, dentro del rango "
            "registrado (160-180 cm3/ha). Decirle al bot: 'en El Trebol'. "
            "Esperado: APTA; la Ordenanza 841/2010 no fija distancia para "
            "aplicacion terrestre y el bot lo avisa en vez de inventar un valor."
        ),
    },
    {
        "archivo": "02_apta_aerea_banda_ii.jpg",
        "numero": "1002",
        "campos": {
            "Cultivo": "Soja",
            "Lote": "3",
            "Adversidad": "Chinche de la alfalfa",
            "Producto": "Flyer 10 Ec - 170 cm3/ha",
            "Superficie": "25 ha",
            "Tipo de aplicacion": "Aerea",
        },
        "nota": (
            "Mismo producto que el caso 1 (Reg. 41881, Banda II / amarilla), "
            "pero aplicacion AEREA. Decirle al bot: 'en El Trebol'. Esperado: "
            "APTA, con distancia minima a zona urbana de 3.000 m (Ordenanza "
            "841/2010, art. 7, banda amarilla); el art. 6 (500 m, todas las "
            "bandas) queda en Fuentes."
        ),
    },
    {
        "archivo": "03_observada_dosis_fuera_de_rango.jpg",
        "numero": "1003",
        "campos": {
            "Cultivo": "Soja",
            "Lote": "12",
            "Adversidad": "Verdolaga",
            "Producto": "Imazamox 70 Wg Brilliance - 150 g/ha",
            "Superficie": "30 ha",
            "Tipo de aplicacion": "Terrestre",
        },
        "nota": (
            "Reg. SENASA 41759, Banda III. Dosis declarada 150 g/ha vs. "
            "registrada 70 g/ha (mas del doble, muy por encima de "
            "DOSIS_TOLERANCIA_PCT). Decirle al bot: 'en El Trebol'. Esperado: "
            "OBSERVADA por dosis (no ofrece agendar)."
        ),
    },
]


AVISO_LOCALIDAD = (
    "Para probar con otra localidad (p. ej. 'en Rosario'): el bot pide la "
    "provincia y se basa en la normativa provincial, aclarando que no cuenta "
    "con la municipal.\n"
)


def main() -> None:
    notas = ["Recetas de ejemplo para El Trebol -- ver DECISIONES.md.\n", AVISO_LOCALIDAD]
    for caso in CASOS:
        dibujar_receta(BASE / caso["archivo"], caso["campos"], numero=caso["numero"])
        notas.append(f"## {caso['archivo']}\n{caso['nota']}\n")

    (BASE / "notas.txt").write_text("\n".join(notas), encoding="utf-8")
    print("Recetas de ejemplo generadas en", BASE)


if __name__ == "__main__":
    main()
