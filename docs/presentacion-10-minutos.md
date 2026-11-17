# SobraCero: guion para exponer en 10 minutos

Cada bloque tiene su tiempo, lo que dices y lo que muestras. Si te falta tiempo, recorta los
bloques marcados con ✂.

## Antes de empezar (5 minutos antes, no en directo)

- Backend, frontend y sitio de prueba corriendo (`http://localhost:3200/en`).
- Cuatro pestañas ya con sesión: comercio, cliente, receptor y administrador.
- Pestaña del comercio en *My shop*; pestaña del cliente en *Find a pickup*; mapa abierto en otra.
- Una segunda ventana en la página de un lote, para mostrar el stock en vivo.
- **Decide la IA**: si pones la clave de Groq bien en `.env` (`LLM_PROVIDER=groq`, `LLM_API_KEY=...`),
  los textos serán de Groq. Si no, corre el proveedor simulado y debes decirlo. Nunca digas que usas
  Groq si no lo estás usando en ese momento.

## 0:00 – 1:00 El problema y la propuesta

**Dices:** «Los comercios de alimentos pierden comida que aún sirve; y quien podría aprovecharla
no sabe que existe ni si llega a tiempo. SobraCero conecta comercios, clientes y organizaciones
receptoras. No decimos que sea único: ya existen plataformas parecidas. Lo que proponemos es un
flujo explicable: cada decisión muestra sus motivos, una persona aprueba, y todo queda registrado.»

**Muestras:** la pantalla de inicio.

## 1:00 – 2:30 Las tecnologías (una diapositiva o el diagrama de `docs/architecture.md`)

| Capa | Qué usamos | Para qué |
| --- | --- | --- |
| Frontend | Next.js 15 (App Router), React 19, TypeScript, Tailwind, next-intl, next-themes, Zod | Interfaz en inglés y español, tema claro/oscuro, validación de cada respuesta |
| Backend | FastAPI, SQLAlchemy 2, Alembic (12 migraciones) | API y reglas de negocio por capas |
| Datos | PostgreSQL (SQLite en pruebas), Redis | Persistencia, sesiones, tareas |
| Tareas | Celery worker y beat | Vencimiento de lotes, ejecuciones programadas |
| Tiempo real | WebSockets | Stock que cambia sin recargar |
| Servicio de análisis | gRPC con respaldo local | Plan de rescate calculado en un servicio aparte |
| Recolección | Scrapy | Datos públicos con permiso y con límites |
| Mapa | Leaflet + OpenStreetMap, Nominatim | Mapa y búsqueda de lugares |
| IA | Groq (modelo `gpt-oss-20b`) por una interfaz intercambiable; también Anthropic y uno simulado | Redactar y leer texto, nunca decidir |
| Calidad | Pruebas (462 backend, 244 frontend, 3 e2e), CI en GitHub Actions, SonarCloud | Evidencia, no promesas |
| Despliegue | Docker, Railway | Backend y frontend publicados |

**Ancla del curso (dilo):** las páginas usan cinco estrategias de renderizado a propósito: SSG
(cómo funciona), SSR (detalle de un lote, porque el stock cambia), streaming (el mercado), ISR (perfil
de un comercio) y CSR (paneles privados y el mapa).

## 2:30 – 4:30 Demo 1: el comercio y el plan de rescate

1. Entra como comercio, *My shop*. Muestra el **diagnóstico diario**: alertas, números y «lo que este
   resumen no puede saber».
2. Analiza un lote. Aparece el **plan de rescate** con sus motivos (por ejemplo, «el stock supera las
   ventas esperadas»). Pulsa **Explain in plain words** (aquí actúa la IA).
3. Pulsa **Compare scenarios**: mantener, descontar o donar, siempre marcado como hipotético.
4. **Approve**. «Sin esta aprobación humana no cambia nada.»

**Dices:** «Los números salen de código con pruebas: la IA solo explica con palabras, y no puede
escribir un número, el esquema lo rechaza.»

## 4:30 – 6:00 Demo 2: el cliente (IA + reserva + QR + tiempo real)

1. Como cliente: **Find a pickup**. Escribe «tengo 20 dólares, 2 porciones de panadería» y pulsa
   *Fill the form with AI*. «La IA solo copia lo que escribí; yo reviso los valores antes de buscar.»
2. Busca. Muestra que lista solo lo que **alcanza a recoger antes de que cierre** y explica por qué
   deja fuera los demás.
3. Reserva. Aparece el código y el **QR de recogida**.
4. Con dos ventanas abiertas en el mismo lote: reserva en una y señala cómo baja el stock en la otra
   **sin recargar** (WebSockets).

**Dices:** «Probamos la concurrencia con hilos reales: la última unidad no se vende dos veces y una
recogida repetida cuenta una sola vez. Esas pruebas encontraron un fallo real que corregimos.»

## 6:00 – 7:00 ✂ La donación

Comercio: **Offer as a donation** → buscar receptores compatibles (muestra uno dejado fuera y su
razón) → **Draft with AI** → editar → enviar. Receptor: **Accept**. Comercio: **Confirm delivery**.

**Dices:** «Primero reglas duras (categoría, capacidad, refrigeración, distancia, horario), después un
orden justo. Solo cuenta como donado lo que se entrega. No verificamos organizaciones ni certificamos la
comida: la pantalla lo dice.»

## 7:00 – 8:30 El mapa y el Scanner

1. **Mapa**: disco sólido = afiliado; anillo punteado = encontrado en una fuente pública, **nunca se
   muestra como afiliado**. Abre una ficha: fuente, enlace y fecha de última vez visto.
2. **Scanner** (admin): registra `http://127.0.0.1:8099/catalogo`; intenta ejecutarlo (está
   bloqueado); **Review terms**; activa; **Run now**. Muestra el resultado, el registro rechazado con su
   motivo y el historial de precios.

**Dices:** «Que un `robots.txt` lo permita no basta. Cada fuente exige que una persona registre que
revisó sus términos. El motor se detiene ante un 401, 403 o 429 y nunca intenta saltarse un bloqueo. Un
precio publicado no es stock ni excedente.»

## 8:30 – 9:30 Cómo usamos la IA (el centro de la exposición)

**Una frase para repetir: «el código decide, el modelo redacta».**

| Uso | Qué ve el modelo | Qué nunca decide |
| --- | --- | --- |
| Texto de promoción | Datos del lote | Descuento y precio |
| Leer la fecha de una etiqueta | Una foto | Nada se aplica sin confirmación |
| Explicar el plan de rescate | Códigos de motivos | La acción, las cifras, la aprobación |
| Leer una petición de recogida | Una frase | Qué lotes caben ni su orden |
| Redactar el mensaje de donación | Título y categoría | Quién es compatible ni cantidades |
| Resumen del diagnóstico | Códigos de alertas | Todas las cifras |

**Controles:** respuesta validada con esquema y un reintento, cuota diaria por usuario, caché, límite de
tokens, el texto del usuario va entre delimitadores como dato no confiable, y si la IA falla el
producto **sigue funcionando** (el diagnóstico sale igual, sin el resumen).

## 9:30 – 10:00 Limitaciones y cierre

- «Los datos de recolección y los precios no son existencias. Las distancias son en línea recta.»
- «Los receptores no están verificados y no certificamos inocuidad.»
- «Pendiente: prueba en vivo con Groq y la consulta real a Overpass desde mi máquina; reconocimiento de
  alimentos por foto y OCR no se implementaron.»
- Cierre: «No prometemos eliminar el desperdicio. Mostramos un flujo donde cada decisión se explica, se
  aprueba y se puede comprobar con pruebas.»

---

## Preguntas probables y respuestas honestas

**¿Por qué no deja que la IA calcule?** Porque no se puede probar ni explicar. El código calcula y se
prueba; el modelo solo lo redacta. Además la IA puede fallar y el sistema no debe depender de ella.

**¿Qué pasa si la IA no responde?** El diagnóstico devuelve todas las cifras y alertas y dice que el
resumen no está disponible; el plan de rescate también funciona porque no depende del modelo.

**¿Para qué gRPC?** Para separar el cálculo del plan en un servicio con contrato (`.proto`) y tener
respaldo local si cae. No decimos que sea más rápido.

**¿Cómo evitan que se venda dos veces la última unidad?** Con actualizaciones condicionales atómicas en
base de datos y pruebas con hilos reales.

**¿Es legal hacer scraping?** Depende de cada sitio. Por eso cada fuente necesita revisión de términos
registrada, respetamos `robots.txt`, nos detenemos ante bloqueos y la fuente principal es OpenStreetMap
(licencia ODbL con atribución). Las tiendas grandes quedan desactivadas hasta que alguien revise sus términos.

**¿Qué demuestra que funciona?** 462 pruebas del backend con 97,8 % de cobertura en dominio y
aplicación, 244 del frontend, 3 e2e, CI en verde en los dos repositorios y un recorrido en navegador real.

**¿Qué no funciona todavía?** La subida de imágenes en Railway (faltan las credenciales del
almacenamiento), la prueba en vivo con Groq y la consulta real a Overpass.
