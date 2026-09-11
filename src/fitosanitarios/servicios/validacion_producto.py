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
    opciones_ambiguas: list[str] | None = None
    chequeo_producto: ChequeoProducto | None = None
    chequeo_dosis: ChequeoDosis | None = None
    numero_inscripcion: str | None = None
    marca: str | None = None
    banda_toxicologica: str | None = None
    usos_registrados: list[dict] | None = None


def resolver_y_validar_producto(
    conn,
    modelo_embeddings,
    producto_nombre: str,
    cultivo: str,
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

    if not producto.usos_registrados:
        return ResolucionProducto(
            motivo_no_resuelto=MotivoNoResuelto.SIN_USOS_REGISTRADOS,
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
        dosis_registrada = usos_cultivo[0].get("dosis") or {}
        if dosis_registrada.get("parseable"):
            chequeo_dosis = comparar_dosis(
                dosis_valor, dosis_unidad,
                dosis_registrada.get("valor_min"), dosis_registrada.get("valor_max"),
                dosis_registrada.get("unidad"), tolerancia_pct,
            )

    return ResolucionProducto(
        numero_inscripcion=producto.numero_inscripcion, marca=producto.marca,
        banda_toxicologica=producto.banda_toxicologica,
        chequeo_producto=chequeo_producto, chequeo_dosis=chequeo_dosis,
        usos_registrados=producto.usos_registrados,
    )
