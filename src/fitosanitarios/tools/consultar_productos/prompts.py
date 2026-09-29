"""Lo que el orquestador (el LLM) lee de esta tool: su descripción y la de sus
argumentos."""

DESCRIPCION = """\
Lista productos registrados en SENASA filtrando por cualquier combinación de sus datos
("¿qué hay para yuyo colorado en soja?", "fungicidas de Syngenta banda verde"). Con una
localidad y una distancia al pueblo, lista solo los de las bandas que se pueden aplicar
ahí: "¿qué fungicidas para trigo puedo aplicar con avión a 1500 m de El Trébol?" es UNA
llamada (aptitud, cultivo, tipo_aplicacion, distancia_m, localidad), no dos tools. Para UN
producto puntual: `validar_producto_registro`. Informa lo registrado, no recomienda.

Args:
    cultivo: solo el que nombró; nunca lo deduzcas del producto. Una localidad ("en El
        Trébol") no es un cultivo.
    adversidad: plaga, maleza o enfermedad, si la mencionó.
    principio_activo: principio activo ("glifosato", "metsulfuron"), si lo mencionó.
    aptitud: herbicida, insecticida, fungicida, curasemilla, etc. (una o varias), si la dijo.
    banda: Ia, Ib, II, III, IV o su color, una o varias, si la dijo.
    banda_maxima: la banda más peligrosa que acepta ("hasta banda azul"), si la dijo.
    firma: empresa registrante ("Syngenta"), si la dijo.
    marca: parte del nombre comercial ("los Roundup"), si la dijo. Nunca un principio
        activo: ese va en principio_activo.
    localidad: la localidad que nombró; solo filtra si también dio una distancia.
    provincia: solo si la tool la pidió.
    tipo_aplicacion: el tipo o el equipo tal como lo dijo ("avión", "mosquito"), si lo
        dijo; sin él se responde para aérea y terrestre.
    distancia_m: metros entre el lote y el pueblo, si los dio."""
