# SobraCero: guion para exponer en 5 minutos

Una sola ruta de demostración. Todo lo demás se menciona en una frase y se deja para preguntas.
Unas 650 palabras habladas, con la demo en vivo ocupando más de la mitad del tiempo.

## Antes de empezar (no cuenta en los 5 minutos)

- Servicios corriendo (`http://localhost:3200/en`) y tres pestañas con sesión: comercio en *My shop*,
  cliente en *Find a pickup*, y el mapa.
- Una segunda ventana con el mismo lote abierto, para el stock en vivo.
- Ensaya **una vez con cronómetro**. Si te pasas, recorta primero el mapa.
- Decide la IA: con Groq real (`LLM_PROVIDER=groq` y la clave en `.env`) o simulada. Si es simulada,
  dilo; no digas «Groq» si no lo estás usando.

## 0:00 – 0:30 Qué es

> «SobraCero conecta comercios de alimentos con clientes y organizaciones receptoras para que la
> comida que sobra se aproveche. No decimos que sea único; lo que hicimos es un flujo **explicable**:
> cada decisión muestra sus motivos, una persona aprueba, y todo está probado.»

## 0:30 – 1:15 Tecnologías (una diapositiva, una línea por capa)

> «Frontend en **Next.js 15 con TypeScript**, en inglés y español y con tema claro y oscuro. Backend en
> **FastAPI** con **PostgreSQL**, **Redis y Celery** para las tareas, y **WebSockets** para el stock en
> vivo. Un servicio de análisis por **gRPC**. Un motor de recolección con **Scrapy**, un mapa con
> **Leaflet y OpenStreetMap**, y la **IA** a través de una interfaz intercambiable: **Groq**, Anthropic o
> una simulada. Desplegado en **Railway**, con **462 pruebas** del backend, **244** del frontend y CI en verde.»

Una frase de curso: «Usamos las cinco estrategias de renderizado a propósito: estático, servidor,
streaming, regeneración incremental y cliente.»

## 1:15 – 2:15 Demo del comercio (60 s)

1. *My shop*: señala el **diagnóstico** (alertas y «lo que no puede saber»).
2. Analiza un lote: aparece el **plan de rescate con sus motivos**.
3. Pulsa **Explain in plain words** y di: «aquí actúa la IA: solo redacta, no puede escribir cifras».
4. **Approve**: «sin aprobación humana no cambia nada».

## 2:15 – 3:15 Demo del cliente (60 s)

1. **Find a pickup**: escribe «tengo 20 dólares, 2 porciones de panadería» → *Fill the form with AI*.
   «La IA solo copia lo que escribí; yo reviso antes de buscar.»
2. Busca: muestra que solo lista lo que **alcanza a recoger antes de que cierre**, y por qué deja fuera el resto.
3. Reserva y señala el **QR**. Con la segunda ventana, muestra el **stock bajando sin recargar**.

## 3:15 – 3:45 Mapa (30 s, es lo primero que recortas)

> «Disco sólido: comercio afiliado. Anillo punteado: negocio encontrado en una fuente pública; **nunca se
> muestra como afiliado**. Cada ficha dice su fuente y cuándo se vio por última vez.»

Una frase para el resto: «También hay donaciones a organizaciones receptoras y un Scanner que recolecta
datos públicos solo de fuentes cuyos términos una persona revisó; puedo mostrarlos si preguntan.»

## 3:45 – 4:30 Cómo usamos la IA (lo que más se recuerda)

> **«El código decide, el modelo redacta.»**
> Usamos el modelo en seis sitios: texto de promociones, lectura de fechas en fotos, explicación del
> plan de rescate, lectura de una petición del cliente, borrador del mensaje de donación y resumen del
> diagnóstico. En ninguno decide precios, cantidades ni aprobaciones: esos números salen de código con
> pruebas, y el esquema rechaza cualquier número escrito por el modelo. El texto del usuario se trata como
> dato no confiable, hay cuota diaria y caché, y **si la IA falla, el producto sigue funcionando**.»

## 4:30 – 5:00 Limitaciones y cierre

> «Los precios recolectados no son existencias, las distancias son en línea recta y no certificamos la
> inocuidad de la comida. Pendiente: probar en vivo con Groq y reconocimiento de alimentos por foto. No
> prometemos eliminar el desperdicio: mostramos un flujo donde cada decisión se explica, se aprueba y se
> puede comprobar.»

---

## Si te preguntan (respuestas de una línea)

- **¿Por qué la IA no calcula?** Porque no se puede probar ni explicar; el código calcula y se prueba.
- **¿Qué pasa si la IA cae?** Las cifras y alertas salen igual; solo falta el resumen redactado.
- **¿Cómo evitan vender dos veces la última unidad?** Actualizaciones atómicas en base de datos, con pruebas de hilos reales.
- **¿Es legal el scraping?** Cada fuente exige una revisión de términos registrada, se respeta `robots.txt` y se detiene ante cualquier bloqueo.
- **¿Qué demuestra que funciona?** 462 + 244 + 3 pruebas, 97,8 % de cobertura en dominio y aplicación, y CI en verde.

Más detalle en [`presentacion-10-minutos.md`](presentacion-10-minutos.md).
