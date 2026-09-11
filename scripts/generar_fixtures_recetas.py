"""Genera las imágenes sintéticas de recetas de tests/fixtures/recetas/ (Fase 4).

No son fotos reales (no las hay disponibles para esta POC): son imágenes
generadas con texto renderizado, con casos de campos faltantes a propósito
-- alcanza para probar la extracción del LLM multimodal, que lee el
contenido visual igual que lo haría con una foto real.

Uso: uv run python scripts/generar_fixtures_recetas.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

BASE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "recetas"

ANCHO, ALTO = 900, 1100


def _fuente(tamano: int) -> ImageFont.FreeTypeFont:
    for candidato in ("arial.ttf", "Arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(candidato, tamano)
        except OSError:
            continue
    return ImageFont.load_default()


def dibujar_receta(
    ruta: Path,
    campos: dict[str, str],
    titulo: str = "RECETA AGRONOMICA",
    numero: str = "0042",
    desenfocar: bool = False,
) -> None:
    img = Image.new("RGB", (ANCHO, ALTO), "white")
    dibujo = ImageDraw.Draw(img)
    fuente_titulo = _fuente(32)
    fuente_texto = _fuente(24)

    y = 60
    dibujo.text((60, y), f"{titulo} N. {numero}", fill="black", font=fuente_titulo)
    y += 60
    dibujo.line((60, y, ANCHO - 60, y), fill="black", width=2)
    y += 40

    for etiqueta, valor in campos.items():
        dibujo.text((60, y), f"{etiqueta}:", fill="black", font=fuente_texto)
        dibujo.text((320, y), valor, fill="black", font=fuente_texto)
        y += 50

    y += 30
    dibujo.line((60, y, ANCHO - 60, y), fill="black", width=1)
    y += 30
    dibujo.text(
        (60, y), "Firma: Ing. Agr. (firma ilegible, sello de matricula)",
        fill="black", font=_fuente(18),
    )

    if desenfocar:
        img = img.filter(ImageFilter.GaussianBlur(radius=8))

    ruta.parent.mkdir(parents=True, exist_ok=True)
    img.save(ruta, "JPEG", quality=85)


def dibujar_no_receta(ruta: Path) -> None:
    img = Image.new("RGB", (ANCHO, ALTO), "white")
    dibujo = ImageDraw.Draw(img)
    dibujo.text((60, 60), "FACTURA N. A-0001-00012345", fill="black", font=_fuente(28))
    dibujo.text((60, 120), "Cliente: Juan Perez", fill="black", font=_fuente(20))
    dibujo.text((60, 160), "Total: $ 45.000,00", fill="black", font=_fuente(20))
    dibujo.rectangle((60, 220, 500, 400), outline="black", width=2)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    img.save(ruta, "JPEG", quality=85)


def main() -> None:
    # 1. Receta completa (mismos datos que el ejemplo de referencia de la skill)
    dibujar_receta(
        BASE / "01_completa.jpg",
        {
            "Cultivo": "Soja",
            "Lote": "4",
            "Adversidad": "Malezas de hoja ancha",
            "Producto": "Glifosato 48% - 2 L/ha",
            "Superficie": "35 ha",
            "Tipo de aplicacion": "Terrestre",
        },
    )

    # 2. Sin tipo de aplicacion
    dibujar_receta(
        BASE / "02_sin_tipo_aplicacion.jpg",
        {
            "Cultivo": "Soja",
            "Lote": "4",
            "Adversidad": "Malezas de hoja ancha",
            "Producto": "Glifosato 48% - 2 L/ha",
            "Superficie": "35 ha",
        },
    )

    # 3. Sin superficie
    dibujar_receta(
        BASE / "03_sin_superficie.jpg",
        {
            "Cultivo": "Maiz",
            "Lote": "7B",
            "Adversidad": "Oruga cogollera",
            "Producto": "Clorpirifos 48% - 1,5 L/ha",
            "Tipo de aplicacion": "Aerea",
        },
    )

    # 4. Dos productos
    dibujar_receta(
        BASE / "04_dos_productos.jpg",
        {
            "Cultivo": "Trigo",
            "Lote": "12",
            "Adversidad": "Roya de la hoja",
            "Producto 1": "Tebuconazole 43% - 0,5 L/ha",
            "Producto 2": "Azoxistrobina 25% - 0,4 L/ha",
            "Superficie": "60 ha",
            "Tipo de aplicacion": "Terrestre",
        },
    )

    # 5. Sin lote
    dibujar_receta(
        BASE / "05_sin_lote.jpg",
        {
            "Cultivo": "Girasol",
            "Adversidad": "Isoca de la cabeza",
            "Producto": "Lambdacialotrina 5% - 0,3 L/ha",
            "Superficie": "20 ha",
            "Tipo de aplicacion": "Terrestre",
        },
    )

    # 6. Sin adversidad
    dibujar_receta(
        BASE / "06_sin_adversidad.jpg",
        {
            "Cultivo": "Soja",
            "Lote": "9",
            "Producto": "Glifosato 74% - 1,5 kg/ha",
            "Superficie": "40 ha",
            "Tipo de aplicacion": "Terrestre",
        },
    )

    # 7. Multiples campos faltantes (solo cultivo y producto)
    dibujar_receta(
        BASE / "07_multiples_faltantes.jpg",
        {
            "Cultivo": "Algodon",
            "Producto": "Acefato 75% - 0,5 kg/ha",
        },
    )

    # 8. Sin numero de receta explicito, resto completo
    dibujar_receta(
        BASE / "08_completa_2.jpg",
        {
            "Cultivo": "Sorgo",
            "Lote": "3",
            "Adversidad": "Pulgon verde",
            "Producto": "Imidacloprid 35% - 0,2 L/ha",
            "Superficie": "15 ha",
            "Tipo de aplicacion": "Terrestre",
        },
        numero="0088",
    )

    # 9. Imagen borrosa (toda la receta, simula foto movida/desenfocada)
    dibujar_receta(
        BASE / "09_borrosa.jpg",
        {
            "Cultivo": "Soja",
            "Lote": "4",
            "Adversidad": "Malezas de hoja ancha",
            "Producto": "Glifosato 48% - 2 L/ha",
            "Superficie": "35 ha",
            "Tipo de aplicacion": "Terrestre",
        },
        desenfocar=True,
    )

    # 10. No es una receta (otro tipo de documento)
    dibujar_no_receta(BASE / "10_no_es_receta.jpg")

    print("fixtures generadas en", BASE)


if __name__ == "__main__":
    main()
