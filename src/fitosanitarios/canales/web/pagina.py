"""Página de chat servida por el canal web (Fase 11): un único HTML
autocontenido (sin CDN externo) que habla con `POST /api/mensaje`. Reproduce
las modalidades de entrada de WhatsApp que el agente usa (texto, imagen,
botones/listas) con equivalentes de navegador: input de texto, `<input
type=file>`, y botones generados a partir de los
patrones `[Opción]` y `   - opción` que ya emite `orquestador/formateador.py`
(no hay estructura de botones separada: WhatsApp también los recibe como
texto plano dentro del mensaje, ver skill "Formato de respuestas")."""

PAGINA_CHAT = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agente fitosanitarios — chat</title>
<style>
  :root {
    color-scheme: light dark;
    --fondo: #f4f5f0;
    --burbuja-bot: #ffffff;
    --burbuja-user: #2f6f3e;
    --texto-user: #ffffff;
    --texto: #1c1c1c;
    --borde: #d9dcd3;
    --acento: #2f6f3e;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--fondo);
    color: var(--texto);
    font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif;
    display: flex;
    flex-direction: column;
    height: 100vh;
  }
  header {
    padding: 12px 16px;
    background: var(--acento);
    color: white;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
  }
  header h1 { font-size: 16px; margin: 0; font-weight: 600; }
  header button {
    background: rgba(255,255,255,0.15);
    color: white;
    border: 1px solid rgba(255,255,255,0.4);
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
    cursor: pointer;
  }
  #chat {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .fila { display: flex; }
  .fila.user { justify-content: flex-end; }
  .burbuja {
    max-width: 80%;
    padding: 10px 14px;
    border-radius: 14px;
    line-height: 1.4;
    font-size: 14px;
    white-space: normal;
    box-shadow: 0 1px 2px rgba(0,0,0,0.08);
  }
  .fila.bot .burbuja { background: var(--burbuja-bot); border: 1px solid var(--borde); }
  .fila.user .burbuja { background: var(--burbuja-user); color: var(--texto-user); }
  .burbuja img.miniatura { max-width: 160px; border-radius: 8px; display: block; margin-top: 6px; }
  .opciones { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
  .chip {
    border: 1px solid var(--acento);
    color: var(--acento);
    background: white;
    border-radius: 999px;
    padding: 5px 12px;
    font-size: 13px;
    cursor: pointer;
  }
  .chip:disabled { opacity: 0.4; cursor: default; }
  .chip:disabled:hover { background: white; color: var(--acento); }
  .chip:hover { background: var(--acento); color: white; }
  #estado { font-size: 12px; color: #666; padding: 0 16px 4px; min-height: 14px; }
  #adjunto-preview {
    display: none;
    padding: 8px 16px;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: #555;
  }
  #adjunto-preview img { max-height: 48px; border-radius: 6px; }
  #adjunto-preview button {
    border: none; background: none; color: #b00020; cursor: pointer; font-size: 13px;
  }
  footer {
    border-top: 1px solid var(--borde);
    background: var(--burbuja-bot);
    padding: 8px 10px;
    display: flex;
    gap: 6px;
    align-items: flex-end;
  }
  footer textarea {
    flex: 1;
    resize: none;
    border: 1px solid var(--borde);
    border-radius: 10px;
    padding: 8px 10px;
    font-size: 14px;
    font-family: inherit;
    max-height: 120px;
  }
  footer button.icono {
    border: none;
    background: none;
    font-size: 20px;
    cursor: pointer;
    padding: 4px 6px;
  }
  footer button.enviar {
    border: none;
    background: var(--acento);
    color: white;
    border-radius: 10px;
    padding: 0 16px;
    font-size: 14px;
    cursor: pointer;
  }
  footer button:disabled { opacity: 0.5; cursor: default; }
</style>
</head>
<body>
<header>
  <h1>🌱 Agente de recetas fitosanitarios</h1>
  <button id="btn-nueva">Nueva conversación</button>
</header>
<div id="chat"></div>
<div id="estado"></div>
<div id="adjunto-preview">
  <img id="adjunto-img" alt="receta adjunta">
  <span>Foto de receta lista para enviar</span>
  <button id="adjunto-quitar">Quitar</button>
</div>
<footer>
  <button class="icono" id="btn-imagen" title="Adjuntar foto de receta">📎</button>
  <input type="file" id="input-imagen" accept="image/*" hidden>
  <textarea id="input-texto" rows="1" placeholder="Escribí tu mensaje..."></textarea>
  <button class="enviar" id="btn-enviar">Enviar</button>
</footer>
<script>
(function () {
  "use strict";

  const CLAVE_SESION = "fitosanitarios_session_id";
  function idSesion() {
    let id = localStorage.getItem(CLAVE_SESION);
    if (!id) {
      id = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random());
      localStorage.setItem(CLAVE_SESION, id);
    }
    return id;
  }

  const chat = document.getElementById("chat");
  const estado = document.getElementById("estado");
  const inputTexto = document.getElementById("input-texto");
  const btnEnviar = document.getElementById("btn-enviar");
  const btnImagen = document.getElementById("btn-imagen");
  const inputImagen = document.getElementById("input-imagen");
  const btnNueva = document.getElementById("btn-nueva");
  const previewBox = document.getElementById("adjunto-preview");
  const previewImg = document.getElementById("adjunto-img");
  const btnQuitarAdjunto = document.getElementById("adjunto-quitar");

  let adjuntoBase64 = null;   // pendiente de enviar
  let adjuntoDataUrl = null;  // para mostrarlo en la burbuja propia

  function escaparHtml(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // Extrae líneas de botones ([Opción] [Opción]) y de lista ("   - opción",
  // exactamente 3 espacios: así las emite `formateador.py` para
  // CampoFaltante.tipo_entrada == "lista"), dejando el resto como texto.
  function partirTextoYOpciones(texto) {
    const lineas = texto.split("\\n");
    const textoLineas = [];
    const opciones = [];
    const reBotones = /^(\\s*\\[[^\\]]+\\]\\s*)+$/;
    const reLista = /^   - (.+)$/;
    for (const linea of lineas) {
      const matchLista = linea.match(reLista);
      if (reBotones.test(linea) && linea.includes("[")) {
        const re = /\\[([^\\]]+)\\]/g;
        let m;
        while ((m = re.exec(linea)) !== null) opciones.push(m[1]);
      } else if (matchLista) {
        opciones.push(matchLista[1]);
      } else {
        textoLineas.push(linea);
      }
    }
    return { texto: textoLineas.join("\\n").trim(), opciones };
  }

  function renderTextoConNegritas(texto) {
    let html = escaparHtml(texto);
    html = html.replace(/\\*([^*\\n]+)\\*/g, "<b>$1</b>");
    html = html.replace(/\\n/g, "<br>");
    return html;
  }

  function agregarBurbuja(texto, esUsuario, dataUrlImagen) {
    const fila = document.createElement("div");
    fila.className = "fila " + (esUsuario ? "user" : "bot");
    const burbuja = document.createElement("div");
    burbuja.className = "burbuja";

    if (esUsuario) {
      burbuja.innerHTML = renderTextoConNegritas(texto || "");
      if (dataUrlImagen) {
        const img = document.createElement("img");
        img.className = "miniatura";
        img.src = dataUrlImagen;
        burbuja.appendChild(img);
      }
    } else {
      const { texto: textoLimpio, opciones } = partirTextoYOpciones(texto);
      burbuja.innerHTML = renderTextoConNegritas(textoLimpio);
      if (opciones.length) {
        const cont = document.createElement("div");
        cont.className = "opciones";
        opciones.forEach((op) => {
          const chip = document.createElement("button");
          chip.className = "chip";
          chip.type = "button";
          chip.textContent = op;
          chip.addEventListener("click", () => {
            cont.querySelectorAll("button").forEach((b) => { b.disabled = true; });
            enviar(op);
          });
          cont.appendChild(chip);
        });
        burbuja.appendChild(cont);
      }
    }

    fila.appendChild(burbuja);
    chat.appendChild(fila);
    chat.scrollTop = chat.scrollHeight;
  }

  function limpiarAdjunto() {
    adjuntoBase64 = null;
    adjuntoDataUrl = null;
    inputImagen.value = "";
    previewBox.style.display = "none";
  }

  inputImagen.addEventListener("change", () => {
    const archivo = inputImagen.files[0];
    if (!archivo) return;
    const lector = new FileReader();
    lector.onload = () => {
      adjuntoDataUrl = lector.result;
      adjuntoBase64 = adjuntoDataUrl.split(",", 2)[1];
      previewImg.src = adjuntoDataUrl;
      previewBox.style.display = "flex";
    };
    lector.readAsDataURL(archivo);
  });
  btnImagen.addEventListener("click", () => inputImagen.click());
  btnQuitarAdjunto.addEventListener("click", limpiarAdjunto);

  btnNueva.addEventListener("click", () => {
    localStorage.removeItem(CLAVE_SESION);
    chat.innerHTML = "";
    limpiarAdjunto();
    estado.textContent = "Nueva conversación iniciada.";
    setTimeout(() => { estado.textContent = ""; }, 2000);
  });

  async function enviar(textoForzado) {
    const texto = (typeof textoForzado === "string" ? textoForzado : inputTexto.value).trim();
    const imagenParaEnviar = adjuntoBase64;
    const dataUrlParaEcho = adjuntoDataUrl;

    if (!texto && !imagenParaEnviar) return;

    agregarBurbuja(texto, true, dataUrlParaEcho);

    inputTexto.value = "";
    limpiarAdjunto();
    btnEnviar.disabled = true;
    estado.textContent = "El agente está pensando...";

    try {
      const resp = await fetch("/api/mensaje", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: idSesion(),
          texto: texto,
          imagen_base64: imagenParaEnviar,
        }),
      });
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      const data = await resp.json();
      (data.mensajes || []).forEach((m) => agregarBurbuja(m, false));
    } catch (err) {
      agregarBurbuja("⚠️ No pude conectarme con el servidor. Probá de nuevo.", false);
    } finally {
      estado.textContent = "";
      btnEnviar.disabled = false;
      inputTexto.focus();
    }
  }

  btnEnviar.addEventListener("click", () => enviar());
  inputTexto.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      enviar();
    }
  });

  agregarBurbuja(
    "Hola 👋 Soy el asistente de recetas fitosanitarios. Mandame una foto de tu receta, " +
    "preguntame por un producto o por la normativa de tu localidad.",
    false
  );
})();
</script>
</body>
</html>
"""
