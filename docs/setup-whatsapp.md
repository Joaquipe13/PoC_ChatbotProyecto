# Configurar WhatsApp Cloud API (número de prueba)

Guía para levantar el canal real de WhatsApp para desarrollo y para la
defensa (Fase 8). No versionar ningún valor real (token, App Secret,
verify token) -- todos van en `.env`, nunca en este documento ni en git.

## 1. App de Meta for Developers

1. Crear una cuenta de negocio (Business Portfolio) si no existe una, en
   [business.facebook.com](https://business.facebook.com).
2. Crear una app en [developers.facebook.com/apps](https://developers.facebook.com/apps)
   con el tipo "Business", agregando el producto **WhatsApp**.
3. En el panel de WhatsApp > Primeros pasos, Meta asigna automáticamente un
   **número de prueba** (gratuito, hasta 5 destinatarios verificados) y un
   `Phone number ID` -- copiarlo a `WHATSAPP_PHONE_NUMBER_ID` en `.env`.
4. Agregar hasta 5 números de teléfono destinatarios de prueba (los que van
   a mandar mensajes al bot durante desarrollo/defensa) y verificarlos con
   el código que llega por WhatsApp/SMS.

## 2. Token de System User (no el token temporal del panel)

El token temporal que muestra el panel "Primeros pasos" vence en 24 h --
sirve para probar con `curl` una vez, no para dejar el webhook corriendo.

1. En el Business Manager, ir a Configuración del negocio > Usuarios >
   Usuarios del sistema, crear un System User con rol "Admin" (o el mínimo
   necesario: administrar la app de WhatsApp).
2. Asignar la app de WhatsApp creada en el paso 1 a ese System User, con
   permiso `whatsapp_business_messaging` (y `whatsapp_business_management`
   si se va a administrar el número desde la API).
3. Generar un token para el System User, marcando esos mismos permisos, sin
   fecha de expiración (o la más larga disponible).
4. Copiar ese token a `WHATSAPP_ACCESS_TOKEN` en `.env`. Este es el que usa
   `canales/whatsapp/cliente_graph.py` para enviar mensajes y descargar
   media -- **no** el token temporal del panel.

## 3. App Secret y verify token

1. En el panel de la app, Configuración básica > mostrar el `App Secret` ->
   copiarlo a `WHATSAPP_APP_SECRET` en `.env`. Se usa para validar
   `X-Hub-Signature-256` en cada `POST` del webhook (ver
   `canales/whatsapp/webhook.py::verificar_firma`).
2. Inventar un `WHATSAPP_VERIFY_TOKEN` propio (cualquier string) y ponerlo
   en `.env` -- es el que Meta va a devolver en el handshake `GET` para
   confirmar que el endpoint es tuyo (no lo genera Meta, lo elegís vos y lo
   repetís en el paso 5).

## 4. Túnel HTTPS para desarrollo

Meta exige que el webhook sea HTTPS público. Para desarrollo local, un
túnel:

```bash
# cloudflared (no requiere cuenta para un túnel efímero)
cloudflared tunnel --url http://localhost:8000

# o ngrok
ngrok http 8000
```

Copiar la URL HTTPS que da el túnel (cambia cada vez que se reinicia, salvo
que se use un túnel nombrado/pago) -- se usa en el paso siguiente como
`https://<url-del-tunel>/webhook`.

## 5. Suscribir el webhook

1. Levantar el servidor local con `USE_FIXTURES=false` (en `.env` o en la
   línea de comando): `uv run uvicorn fitosanitarios.canales.whatsapp.app_produccion:app --port 8000`.
   Al arrancar se chequean las credenciales (`canales/chequeo_credenciales.py`):
   Postgres y el catálogo, cada `GEMINI_API_KEY_*` y el token de WhatsApp
   contra la Graph API (muestra el número asociado). Si algo falla, el
   servidor no arranca y dice qué corregir. El `WHATSAPP_APP_SECRET` no se
   puede verificar al arrancar: si está mal, cada mensaje entrante deja en
   la consola "Mensaje rechazado por firma inválida".
2. En el panel de WhatsApp > Configuración > Webhook, pegar la URL del
   túnel + `/webhook` y el `WHATSAPP_VERIFY_TOKEN` del paso 3.
3. Meta hace un `GET` de verificación (`hub.mode=subscribe`); si el
   `verify_token` coincide, el webhook queda confirmado.
4. Suscribirse al campo **`messages`** (no hace falta ningún otro campo
   para este proyecto).

## 6. Verificar versión de Graph API vigente

`WHATSAPP_GRAPH_VERSION` en `.env` (default `v26.0`, ver `config.py`) --
confirmar la versión estable vigente en la
[changelog de Graph API](https://developers.facebook.com/docs/graph-api/changelog)
antes de la defensa, por si Meta deprecó la versión configurada.

## 7. Prueba manual de punta a punta

Con el túnel activo y el número de prueba configurado:

1. Mandar "Hola" desde un número destinatario verificado -> debería llegar
   la respuesta de `tipo=ayuda`.
2. Mandar una foto real de una receta agronómica -> debería llegar la
   confirmación de datos extraídos (`tipo=confirmacion_receta`).
3. Revisar los logs del proceso: cada turno deja una fila en
   `operacion.turno` (ver `orquestador/estado.py::registrar_turno`).

Esta prueba es manual, no corre en CI (depende de credenciales reales y del
túnel). Si el túnel falla el día de la defensa, el plan B es
`notebooks/demo_e2e.ipynb` (invoca el orquestador directo, sin depender de
Meta).

**Verificada (12/09/2026):** paso 1 confirmado con cloudflared + el número
de prueba real -- webhook verificado, `POST /webhook` con firma válida,
respuesta generada por Gemini real y recibida en el teléfono. Dos ajustes
necesarios que no estaban bien en el `.env` cargado: token de acceso
vencido (había que regenerar el temporal del panel, o usar uno de System
User que no venza) y `WHATSAPP_AR_QUITAR_9=true` (con `false` la Graph API
rechazaba el envío con `131030`, "recipient phone number not in allowed
list" -- ver `DIFICULTADES.md` para el diagnóstico completo).

## Errores comunes

- **`131030` al enviar**: número argentino sin normalizar -- ver
  `canales/whatsapp/normalizacion.py` y `WHATSAPP_AR_QUITAR_9`.
- **401 en el `POST` del webhook**: `WHATSAPP_APP_SECRET` no coincide con
  el de la app real, o Meta está firmando con una versión de la app
  distinta a la configurada (verificar que el número de prueba pertenezca
  a la misma app cuyo secreto se copió).
- **Token vencido**: si se usó el token temporal del panel en vez del de
  System User, empieza a devolver 401 a las 24 h -- ver paso 2.
- **La app no aparece habilitada para mensajes de producción**: Meta
  restringe (desde el 15/01/2026) el uso de bots de propósito general en
  WhatsApp Business API -- la descripción de la app en Meta for Developers
  debe reflejar una función de negocio acotada (validación de recetas
  fitosanitarias), no un asistente conversacional genérico.
