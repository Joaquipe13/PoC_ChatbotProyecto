"""Resuelve un producto declarado contra el catálogo y arma su chequeo de
registro + dosis. Reutilizado tanto por `validar_producto_registro` como por
`evaluar_riesgo`/`evaluar_viabilidad_legal` (ver skill, "Arquitectura":
`evaluar_viabilidad_legal` ejecuta internamente los mismos chequeos que las
otras dos tools, no las vuelve a invocar como tools separadas)."""

from dataclasses import dataclass

from fitosanitarios.datos.retrievers.catalogo import buscar_productos_por_nombre
from fitosanitarios.dominio.modelos import Cita
from fitosanitarios.dominio.motivos import MotivoNoResuelto
from fitosanitarios.servicios.dictamen import ChequeoProducto
from fitosanitarios.servicios.dosis import ChequeoDosis, comparar_dosis
from fitosanitarios.servicios.matching import Candidato, hay_empate_ambiguo, rankear_candidatos


@dataclass
class ResolucionProducto:
    motivo_no_resuelto: MotivoNoResuelto | None = None
    producto_id: int | None = None  # para buscar en su marbete si no tiene usos
    opciones_ambiguas: list[str] | None = None
    chequeo_producto: ChequeoProducto | None = None
    chequeo_dosis: ChequeoDosis | None = None
    numero_inscripcion: str | None = None
    marca: str | None = None
    banda_toxicologica: str | None = None
    usos_registrados: list[dict] | None = None
    # Solo los usos del cultivo consultado (y de la adversidad, si se dio): es lo único
    # que se le puede mostrar al usuario como "la dosis registrada".
    usos_del_cultivo: list[dict] | None = None


def _dosis_sin_ambiguedad_de_adversidad(
    usos_cultivo: list[dict], adversidad: str | None
) -> dict | None:
    """Si no se especificó `adversidad` y los usos para el cultivo tienen
    rangos de dosis DISTINTOS entre sí, no hay un único rango contra el que
    comparar (ver skill, "Dosis": "Rangos distintos por adversidad y
    adversidad desconocida: faltan_datos"). Devuelve `None` en ese caso --
    nunca se elige un rango al azar entre varios posibles.

    Hallazgo real (Fase 7): antes de este chequeo, se usaba directamente
    `usos_cultivo[0]`, lo que podía comparar la dosis declarada contra un
    rango que no correspondía a la adversidad real y dar un OBSERVADA
    equivocado. Ver DECISIONES.md.
    """
    if not usos_cultivo:
        return None
    if adversidad:
        # Si `adversidad` se especificó, `usos_cultivo` ya viene filtrado a
        # esa adversidad (si hubo match) más arriba: no hay ambigüedad.
        return usos_cultivo[0].get("dosis")

    rangos_distintos = {
        (
            (u.get("dosis") or {}).get("valor_min"),
            (u.get("dosis") or {}).get("valor_max"),
            (u.get("dosis") or {}).get("unidad"),
        )
        for u in usos_cultivo
    }
    if len(rangos_distintos) > 1:
        return None
    return usos_cultivo[0].get("dosis")


def _chequeo_sin_un_unico_rango(
    usos_cultivo: list[dict], cultivo: str, dosis_valor: float, dosis_unidad: str,
    tolerancia_pct: float,
) -> ChequeoDosis:
    """La dosis contra varios rangos registrados para el cultivo (uno por plaga) cuando no se
    sabe la plaga. Fuera de todos, es una observación sea cual sea la plaga (se compara contra
    el rango completo, del mínimo al máximo). Si entra en alguno, o cae entre dos, depende de
    la plaga: no se verifica y se dice por qué, nunca se elige un rango (ver
    `_dosis_sin_ambiguedad_de_adversidad`)."""
    rangos = [
        u["dosis"] for u in usos_cultivo
        if (u.get("dosis") or {}).get("parseable")
        and u["dosis"].get("valor_min") is not None and u["dosis"].get("valor_max") is not None
    ]
    no_verificada = ChequeoDosis(
        cumple=False, comparable=False, valor_declarado=dosis_valor,
        unidad_declarada=dosis_unidad, valor_min_registrado=None, valor_max_registrado=None,
        porcentaje_desvio=None,
        motivo_no_comparable=(
            f"el rango registrado para {cultivo} depende de la plaga; indicá contra qué plaga "
            "se aplica" if rangos else
            f"el registro no trae un rango de dosis comparable para {cultivo}"
        ),
    )
    if not rangos:
        return no_verificada
    por_rango = [
        comparar_dosis(
            dosis_valor, dosis_unidad, r["valor_min"], r["valor_max"], r.get("unidad"),
            tolerancia_pct,
        )
        for r in rangos
    ]
    if not all(c.comparable for c in por_rango) or any(c.cumple for c in por_rango):
        return no_verificada
    unidades = {r.get("unidad") for r in rangos}
    if len(unidades) != 1:
        return no_verificada
    completo = comparar_dosis(
        dosis_valor, dosis_unidad, min(r["valor_min"] for r in rangos),
        max(r["valor_max"] for r in rangos), unidades.pop(), tolerancia_pct,
    )
    # Entre dos rangos (fuera de cada uno pero dentro del completo): también depende de la plaga.
    return completo if completo.comparable and not completo.cumple else no_verificada


def resolver_y_validar_producto(
    conn,
    modelo_embeddings,
    producto_nombre: str,
    cultivo: str | None,
    adversidad: str | None,
    dosis_valor: float | None,
    dosis_unidad: str | None,
    tolerancia_pct: float,
) -> ResolucionProducto:
    candidatos_db = buscar_productos_por_nombre(conn, producto_nombre, modelo_embeddings)
    if not candidatos_db:
        return ResolucionProducto(motivo_no_resuelto=MotivoNoResuelto.PRODUCTO_NO_ENCONTRADO)

    candidatos_matching = [Candidato(id=c.id, nombre=c.marca) for c in candidatos_db]
    ranking = rankear_candidatos(producto_nombre, candidatos_matching, top_k=5)
    if hay_empate_ambiguo(ranking):
        return ResolucionProducto(opciones_ambiguas=[r.candidato.nombre for r in ranking[:5]])

    producto = candidatos_db[0]
    citas = [
        Cita(fuente="senasa", registro_senasa=producto.numero_inscripcion, documento="detalle API")
    ]

    if cultivo is None:
        # Solo el producto ("¿qué banda tiene el Tordon?"): registro y banda, sin chequear
        # ningún cultivo. La banda se sabe aunque el producto no tenga usos registrados.
        return ResolucionProducto(
            numero_inscripcion=producto.numero_inscripcion,
            marca=producto.marca,
            banda_toxicologica=producto.banda_toxicologica,
            chequeo_producto=ChequeoProducto(
                producto_nombre=producto.marca, registrado=True, activo=True,
                cultivo_autorizado=None, banda_toxicologica=producto.banda_toxicologica,
                citas=citas,
            ),
            usos_registrados=producto.usos_registrados,
        )

    if not producto.usos_registrados:
        return ResolucionProducto(
            motivo_no_resuelto=MotivoNoResuelto.SIN_USOS_REGISTRADOS,
            producto_id=producto.id,
            numero_inscripcion=producto.numero_inscripcion,
            marca=producto.marca,
            banda_toxicologica=producto.banda_toxicologica,
            chequeo_producto=ChequeoProducto(
                producto_nombre=producto.marca, registrado=True, activo=True,
                cultivo_autorizado=None, banda_toxicologica=producto.banda_toxicologica,
                citas=citas,
            ),
        )

    cultivo_norm = cultivo.strip().lower()
    usos_cultivo = [
        u for u in producto.usos_registrados
        if (u.get("cultivo") or "").strip().lower() == cultivo_norm
    ]
    if adversidad and usos_cultivo:
        adversidad_norm = adversidad.strip().lower()
        usos_con_adversidad = [
            u for u in usos_cultivo
            if (u.get("adversidad") or "").strip().lower() == adversidad_norm
        ]
        if usos_con_adversidad:
            usos_cultivo = usos_con_adversidad

    cultivo_autorizado = len(usos_cultivo) > 0
    chequeo_producto = ChequeoProducto(
        producto_nombre=producto.marca, registrado=True, activo=True,
        cultivo_autorizado=cultivo_autorizado,
        banda_toxicologica=producto.banda_toxicologica, citas=citas,
    )

    chequeo_dosis = None
    if cultivo_autorizado and dosis_valor is not None and dosis_unidad is not None:
        dosis_registrada = _dosis_sin_ambiguedad_de_adversidad(usos_cultivo, adversidad)
        if dosis_registrada is not None and dosis_registrada.get("parseable"):
            chequeo_dosis = comparar_dosis(
                dosis_valor, dosis_unidad,
                dosis_registrada.get("valor_min"), dosis_registrada.get("valor_max"),
                dosis_registrada.get("unidad"), tolerancia_pct,
            )
        else:
            # Antes, sin un único rango (depende de la plaga y no se dijo cuál, o el registro
            # no trae uno comparable) la dosis no se comparaba ni se avisaba: 500 cm3/ha de
            # Flyer en soja, sin plaga, daba APTA (plan del video, 27/09/2026).
            chequeo_dosis = _chequeo_sin_un_unico_rango(
                usos_cultivo, cultivo, dosis_valor, dosis_unidad, tolerancia_pct
            )

    return ResolucionProducto(
        numero_inscripcion=producto.numero_inscripcion, marca=producto.marca,
        banda_toxicologica=producto.banda_toxicologica,
        chequeo_producto=chequeo_producto, chequeo_dosis=chequeo_dosis,
        usos_registrados=producto.usos_registrados, usos_del_cultivo=usos_cultivo,
    )
