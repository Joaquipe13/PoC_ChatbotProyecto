"""Piezas de formato de los mensajes de WhatsApp que usan varias tools.

Cada tool define su propia plantilla en `tools/<tool>/mensajes.py`; lo que se
repite entre ellas (cómo se escribe una cita, un número, la sección *Fuentes*, el
bloque de condiciones de aplicación, una lista de tareas) vive acá, para que
ninguna tool dependa de otra ni del formateador.
"""

import re

from fitosanitarios.dominio.modelos import Cita, ResultadoTool
from fitosanitarios.servicios.condiciones_aplicacion import COLOR_BANDA

NOMBRE_ZONA = {
    "zona_urbana": "zona urbana",
    "escuela": "escuelas",
    "curso_agua": "cursos de agua",
    "otro": "otras zonas protegidas",
}

# Lo que se le ofrece al operario después de un dictamen o de una evaluación de riesgo.
SEGUIMIENTO_COMPLETO = "¿Querés más info (la banda de cada producto) o que agende la aplicación?"
SEGUIMIENTO_SOLO_INFO = "¿Querés más info (la banda de cada producto)?"

_ICONO_TAREA = {"pendiente": "⏳", "en_curso": "🚜", "finalizada": "✅"}


def num(valor) -> str:
    if valor is None:
        return "no figura"
    if isinstance(valor, bool):
        return str(valor)
    if isinstance(valor, int) or (isinstance(valor, float) and float(valor).is_integer()):
        return str(int(valor))
    return f"{valor}".replace(".", ",")


def norma_legible(norma: str) -> str:
    """"ordenanza-841-2010" (nombre del PDF) -> "Ordenanza 841/2010"."""
    m = re.fullmatch(r"(ordenanza|decreto|resolucion|ley)-(\w+)-(\d{4})", norma)
    if not m:
        return norma
    tipo = "Resolución" if m[1] == "resolucion" else m[1].capitalize()
    return f"{tipo} {m[2]}/{m[3]}"


def cita_norma(cita: Cita) -> str:
    """Norma y artículo sin la jurisdicción: "Ordenanza 841/2010, art. 7"."""
    partes = [
        p for p in (
            norma_legible(cita.norma) if cita.norma else None,
            f"art. {cita.articulo}" if cita.articulo else None,
        ) if p
    ]
    return ", ".join(partes) if partes else "normativa"


def texto_cita(cita: Cita) -> str:
    if cita.fuente == "normativa":
        texto = cita_norma(cita)
        if cita.jurisdiccion_id:
            texto += f" ({cita.jurisdiccion_id})"
        return texto
    partes = [p for p in (
        f"Reg. {cita.registro_senasa}" if cita.registro_senasa else None,
        f"({cita.documento})" if cita.documento else None,
    ) if p]
    return "SENASA" + (", " + " ".join(partes) if partes else "")


def seccion_fuentes(citas: list[Cita]) -> str:
    if not citas:
        return ""
    vistas: list[str] = []
    for c in citas:
        texto = texto_cita(c)
        if texto not in vistas:
            vistas.append(texto)
    return "\n".join(["*Fuentes*"] + [f"- {v}" for v in vistas])


def unir_secciones(*secciones: str) -> str:
    return "\n\n".join(s for s in secciones if s.strip())


def primer_dato(resultados: list[ResultadoTool]) -> dict | None:
    for r in resultados:
        if r.datos:
            return r.datos
    return None


def todas_las_citas(resultados: list[ResultadoTool]) -> list[Cita]:
    citas: list[Cita] = []
    for r in resultados:
        citas.extend(r.citas)
    return citas


def bloque_no_verificado(chequeos_no_realizados: list[str]) -> str:
    if not chequeos_no_realizados:
        return ""
    return "\n".join(["*No se pudo verificar*"] + [f"- {c}" for c in chequeos_no_realizados])


def lineas_agenda(tareas: list[dict]) -> list[str]:
    """Las tareas de un día, numeradas, con su estado."""
    lineas = []
    for i, t in enumerate(tareas, start=1):
        icono = _ICONO_TAREA.get(t.get("estado_tarea"), "⚠️")
        hora = f"{t['hora']} — " if t.get("hora") else ""
        cultivo = t.get("cultivo") or "sin cultivo"
        lote = t.get("lote") or "sin lote"
        lineas.append(f"{i}. {icono} {hora}{cultivo} — lote {lote} ({t.get('estado_tarea')})")
    return lineas


def bloque_condiciones(condiciones: dict | None) -> str:
    """Lo más concreto posible: distancia mínima y la norma que la fija. La
    banda de cada producto queda para cuando el usuario pide más info. No
    compara contra la ubicación del lote."""
    if not condiciones:
        return ""
    tipo = "aérea" if condiciones["tipo_aplicacion"] == "aerea" else condiciones["tipo_aplicacion"]
    banda = condiciones.get("banda")
    if banda:
        color = f" ({condiciones['banda_color']})" if condiciones.get("banda_color") else ""
        detalle = f"{tipo} · banda {banda}{color}"
    else:
        detalle = f"{tipo} · banda no determinada ⚠️"
    lineas = [f"*Condiciones de aplicación* — {condiciones['localidad']} · {detalle}"]
    for d in condiciones.get("distancias_minimas", []):
        zona = NOMBRE_ZONA.get(d["tipo_zona"], d["tipo_zona"])
        limitante = d.get("norma_limitante")
        norma = f" ({cita_norma(Cita.model_validate(limitante))})" if limitante else ""
        lineas.append(f"- *Distancia mínima a {zona}:* {num(d['distancia_min_m'])} m{norma}")
    for d in condiciones.get("distancias_minimas", []):
        if d.get("extraida_de_pdf") and d.get("norma_limitante"):
            zona = NOMBRE_ZONA.get(d["tipo_zona"], d["tipo_zona"])
            fuente = cita_norma(Cita.model_validate(d["norma_limitante"]))
            lineas.append(
                f"⚠️ La distancia a {zona} se leyó del texto de {fuente} (no hay reglas "
                "cargadas a mano para esa jurisdicción): verificala con la norma."
            )
        lineas.extend(f"⚠️ {a}" for a in d.get("advertencias", []))
    lineas.extend(f"⚠️ {a}" for a in condiciones.get("advertencias", []))
    return "\n".join(lineas)


def citas_no_mostradas_inline(citas: list[Cita], condiciones: dict | None) -> list[Cita]:
    """La norma que limita cada distancia ya va en su línea: en *Fuentes*
    queda el resto (SENASA, otras reglas que aplican) sin repetirla."""
    if not condiciones:
        return citas
    inline = [
        Cita.model_validate(d["norma_limitante"])
        for d in condiciones.get("distancias_minimas", []) if d.get("norma_limitante")
    ]
    return [c for c in citas if c not in inline]


__all__ = [
    "COLOR_BANDA", "NOMBRE_ZONA", "SEGUIMIENTO_COMPLETO", "SEGUIMIENTO_SOLO_INFO",
    "bloque_condiciones", "bloque_no_verificado", "cita_norma", "citas_no_mostradas_inline",
    "lineas_agenda", "norma_legible", "num", "primer_dato", "seccion_fuentes", "texto_cita",
    "todas_las_citas", "unir_secciones",
]
