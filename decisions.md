# MtgSage: propuesta de solución productiva

**Documento explicativo, apartado 1**  
**Proyecto:** asistente de Magic: The Gathering para atención al usuario  
**Fuente de reglas utilizada en la demo:** *Magic: The Gathering Comprehensive Rules*, versión del 17 de abril de 2026

## 1. Qué queremos resolver

El objetivo de MtgSage es atender consultas sobre Magic: The Gathering desde una interfaz conversacional. Debemos cubrir cuatro situaciones: explicar reglas básicas, resolver preguntas sobre interacciones entre cartas, localizar cartas a partir de descripciones en lenguaje natural y, como funcionalidad adicional, crear cartas personalizadas.

El requisito que más condiciona nuestra solución no es acertar todas las interacciones posibles. El enunciado distingue expresamente entre la precisión de una respuesta y **la capacidad de justificarla con información de referencia**. Por eso hemos priorizado que el sistema sepa cuándo consultar el reglamento o la base de cartas, que conserve lo que ha recibido y que muestre las fuentes utilizadas. No damos por demostrada la corrección de una respuesta solo porque incluya una cita.

Hemos trabajado con dos alcances diferentes. En la **demo** buscamos demostrar el recorrido completo de una pregunta, con herramientas reales, memoria conversacional, una interfaz utilizable y fuentes visibles. En la **propuesta de producción** abordamos cómo sostendríamos ese mismo comportamiento con usuarios concurrentes, actualizaciones del reglamento, límites de coste, seguridad, observabilidad y recuperación ante fallos.

Esta separación es deliberada. No necesitamos desplegar toda la infraestructura productiva para probar una idea, pero sí queremos que las decisiones de la demo nos permitan evolucionar sin sustituir todo el código.

## 2. Qué hemos construido y por qué lo hemos hecho así

Hemos desarrollado el proyecto desde las fuentes hacia la interfaz. Primero comprobamos que podíamos extraer el reglamento y consultar cartas. Después añadimos búsqueda semántica, herramientas para el agente, generación de respuestas y, finalmente, la aplicación conversacional. De esta forma, cada pieza se pudo probar antes de depender de la siguiente.

| Componente | Decisión en la demo | Motivo |
| --- | --- | --- |
| Reglas | PDF de referencia procesado con PyMuPDF | Conservamos una fuente identificable y sus páginas. |
| Unidad de conocimiento | Una regla numerada o entrada del glosario por documento | Evitamos fragmentar arbitrariamente conceptos que ya tienen identificador propio. |
| Embeddings | `qwen3-embedding:0.6b` mediante Ollama | Podemos generar vectores localmente y evitar costes por documento durante las pruebas. |
| Búsqueda vectorial | ChromaDB persistente | Resolvemos similitud y metadatos sin operar una base vectorial remota. |
| Información de cartas | Cliente HTTP de Magic API y modelos de dominio propios | Aislamos las particularidades del proveedor y la paginación. |
| Generación | Gemini con el SDK `google-genai` | Tenemos generación de lenguaje y llamadas a herramientas sin cargar otro modelo grande en nuestra CPU. |
| Orquestación | Un agente con `search_rules`, `search_cards` y `get_card` | Controlamos las decisiones, los límites y las fuentes desde un único punto. |
| Conversación | Historial por sesión, limitado y en memoria | Mantenemos el contexto sin añadir persistencia que la demo no necesita. |
| Interfaz | Streamlit | Ofrecemos chat e indexación desde una misma aplicación sin desarrollar un frontend adicional. |
| Operación | `logging` centralizado y progreso de indexación | Podemos saber qué se ha completado, cuánto ha tardado y dónde ha fallado. |

La extracción del PDF produce **3.138 reglas y 730 términos de glosario**, un total de **3.868 documentos indexables**. Cada uno conserva su identificador de origen, contenido, páginas, tipo de documento y versión del reglamento. Hemos preferido usar esos identificadores como unidad de referencia porque una regla como `104.3b` es más útil para justificar una respuesta que un fragmento anónimo de texto.

La indexación es incremental. Comparamos el contenido con lo almacenado, evitamos generar embeddings cuando no ha cambiado y podemos reanudar un proceso interrumpido. Durante las pruebas detuvimos la indexación completa por su coste temporal en CPU y continuamos trabajando con una colección parcial. Esto permite demostrar el funcionamiento, pero no permite prometer cobertura de todo el reglamento.

Las cuatro funcionalidades comparten el mismo agente, aunque no recorren exactamente el mismo camino. Para reglas consultamos ChromaDB; para cartas traducimos la petición a filtros y consultamos la API; para interacciones podemos combinar ambas fuentes; para una carta personalizada utilizamos directamente la capacidad generativa de Gemini. En este último caso marcamos el resultado como **no oficial** y no fabricamos referencias de cartas existentes.

## 3. Arquitectura que llevaríamos a producción

Mantendríamos **un único agente especializado en Magic**, respaldado por servicios con responsabilidades concretas. Esta elección no responde a una preferencia genérica por las arquitecturas simples, sino al tipo de problema que tenemos delante.

Las preguntas comparten el mismo contexto y las mismas fuentes. Una consulta sobre una interacción puede empezar buscando dos cartas y terminar necesitando una regla de combate. Si dividimos ese trabajo entre un agente de cartas, otro de reglas y un tercer agente coordinador, tendremos que transferir contexto entre modelos, acordar quién decide cuándo termina la consulta y reconstruir qué agente aportó cada evidencia. Añadiríamos llamadas al LLM, latencia, coste y nuevos puntos de fallo, sin una mejora demostrada para estos cuatro casos de uso.

En cambio, **un agente puede decidir qué herramienta necesita y ejecutar varias dentro de una misma consulta**. Los servicios no deciden qué debe contestar al usuario: reciben parámetros concretos, consultan su fuente y devuelven resultados estructurados. Esa separación hace más fáciles las pruebas, las sustituciones de proveedores y la auditoría. Solo estudiaríamos dividir el agente en varios si apareciesen responsabilidades realmente independientes y una evaluación demostrase mejores resultados que esta opción.

Para producción organizaríamos el sistema en las siguientes responsabilidades:

| Responsabilidad | Solución propuesta | Qué resolvemos con ella |
| --- | --- | --- |
| Entrada de aplicación | API HTTP con FastAPI | Autenticación, sesiones, validación, cuotas y un contrato independiente de la interfaz. |
| Orquestación | MtgSageAgent | Selección de herramientas, contexto conversacional, límites y composición de la respuesta. |
| Generación | Adaptador de proveedor LLM | Aislamos el SDK, los modelos, los timeouts y el control del consumo. |
| Recuperación de reglas | Servicio de búsqueda semántica | Devolvemos contenido, identificadores, páginas y versión de la fuente. |
| Consulta de cartas | Adaptador de Magic API con caché | Normalizamos filtros, paginación y datos sin acoplar el agente al proveedor. |
| Ingesta | Worker separado del servicio de chat | Procesamos documentos largos sin bloquear las peticiones de usuarios. |
| Persistencia | PostgreSQL y pgvector | Guardamos sesiones, metadatos y vectores con una operativa razonable para el volumen inicial. |
| Trabajos y archivos | Cola persistente y almacenamiento de objetos | Conservamos los PDFs originales y procesamos actualizaciones con reintentos y seguimiento. |
| Observabilidad | Logs estructurados, métricas y trazas | Diagnosticamos latencias, errores, consumo y calidad de la evidencia. |

No necesitamos convertir cada fila en un microservicio desde el primer día. Empezaríamos con una **API y un worker desplegables por separado**, y mantendríamos los demás elementos como módulos o servicios gestionados según su necesidad operativa. Esa distinción evita que una arquitectura bien separada en código termine convirtiéndose en demasiadas piezas que mantener en infraestructura.

Para el índice proponemos PostgreSQL con pgvector porque nuestro volumen inicial es pequeño y ya necesitamos una base relacional para sesiones y control de versiones. Antes de introducir una base vectorial especializada mediríamos latencia de búsqueda, concurrencia y tamaño real del conocimiento. Conservando el contrato del recuperador, podríamos cambiar el motor sin modificar las herramientas del agente.

## 4. Cómo atendemos una consulta y justificamos la respuesta

Cuando recibimos una pregunta, identificamos la sesión y recuperamos un historial limitado. Enviamos al modelo la instrucción del agente, la pregunta y el contexto necesario. El modelo puede responder directamente o solicitar alguna de las herramientas permitidas. **La elección la propone el LLM, pero la ejecución la controla nuestro código**.

Para una pregunta sobre las fases de un turno, `search_rules` convierte la consulta en un embedding, busca documentos relevantes y devuelve texto y metadatos del reglamento. Para localizar guerreros blancos de coste inferior a dos, `search_cards` recibe filtros estructurados y el adaptador se ocupa de convertirlos en peticiones compatibles con Magic API. Para analizar una interacción podemos buscar las cartas implicadas y recuperar las reglas que aporten contexto.

El agente valida los argumentos antes de ejecutar una herramienta y solo admite funciones registradas expresamente. Conservamos el mensaje original de Gemini cuando devolvemos resultados de herramientas, porque el protocolo de llamadas del modelo necesita ese contexto. También limitamos el número de rondas y ejecuciones para que una pregunta no provoque llamadas indefinidas.

Una vez recuperados los datos, pedimos al modelo que redacte la respuesta. Junto al texto devolvemos las **fuentes realmente obtenidas por las herramientas**, no una lista de referencias inventada por el LLM. La interfaz permite ver qué se ha consultado y, en el caso del reglamento, qué identificadores y páginas se han recuperado.

Aquí debemos distinguir dos conceptos. **Trazabilidad** significa que sabemos qué documentos se consultaron. **Justificación efectiva** significa que una afirmación concreta está respaldada por uno de esos documentos. La demo demuestra el primer nivel, que es esencial para el reto. En producción añadiríamos una verificación de citas y una política que impida contestar preguntas factuales sin evidencia suficiente, porque comprobamos que un modelo puede redactar una regla plausible sin haber consultado el índice.

No todas las consultas necesitan referencias externas. Si nos piden crear una carta de Han Solo blanca y roja con dañar primero, generamos un diseño no oficial y lo indicamos claramente. Si después nos preguntan si esa habilidad funciona de una manera determinada, la nueva pregunta sí puede activar la búsqueda de reglas. Así distinguimos la creación original de la información presentada como factual.

Cuando el proveedor o una herramienta fallan, no los presentamos como si hubieran funcionado. Podemos utilizar las evidencias ya obtenidas, señalar la limitación o devolver una respuesta degradada. Si agotamos las rondas, cerramos el turno sin permitir más herramientas. El objetivo es que un fallo parcial no acabe convertido en una afirmación sin respaldo.

## 5. Cómo mantenemos actualizado el conocimiento

Hemos separado la preparación del reglamento de las conversaciones. **No tiene sentido volver a leer el PDF ni regenerar miles de embeddings cada vez que alguien abre el chat**. La aplicación consume un índice ya publicado; un proceso distinto se encarga de prepararlo.

El ciclo de actualización que proponemos tiene cinco pasos:

1. **Recepción y versionado.** Conservamos el PDF original, su fecha, procedencia y huella de contenido.
2. **Extracción.** Identificamos reglas y términos de glosario, y comprobamos duplicados, recuentos y metadatos.
3. **Sincronización.** Generamos embeddings por lotes únicamente para contenido nuevo o modificado, utilizando identificadores estables.
4. **Validación.** Verificamos cobertura, consistencia de fuentes y una muestra de consultas representativas.
5. **Publicación.** Activamos la nueva versión del índice una vez validada, conservando la anterior para poder revertir el cambio.

En la demo usamos ChromaDB persistente y podemos elegir entre continuar una indexación o reconstruir la colección. En producción **no reconstruiríamos en el mismo índice desde el que están consultando los usuarios**. Prepararíamos una versión nueva y cambiaríamos la referencia activa al terminar. Con eso evitamos mezclar reglas de ediciones diferentes durante una actualización.

También hemos incorporado progreso y cancelación cooperativa entre lotes. En las primeras pruebas vimos que calcular el tiempo restante a partir de todos los documentos procesados producía estimaciones engañosas: revisar un documento ya indexado es mucho más rápido que generar un embedding nuevo en CPU. Por eso diferenciamos documentos reutilizados de documentos realmente pendientes. Cuando no tenemos mediciones suficientes, es preferible mostrar que todavía estamos calculando el tiempo restante.

En Streamlit impedimos que el chat y la indexación operen simultáneamente sobre el almacenamiento local. Es una protección adecuada para la demo, pero **en producción coordinaríamos los trabajos entre procesos e instancias**, no mediante un estado compartido dentro de un único servidor web.

## 6. Sesiones, modelos y respuesta ante fallos

**Sesiones y contexto.** Actualmente conservamos un número limitado de intercambios en memoria. Esto permite preguntas encadenadas y revisiones de cartas personalizadas sin introducir una base de datos para la demo. En producción guardaríamos las sesiones en PostgreSQL, vinculadas a la identidad del usuario, con caducidad y posibilidad de borrado. No enviaríamos siempre toda la conversación al modelo: controlaríamos el tamaño del contexto y resumiríamos información antigua solo cuando hiciera falta.

**Modelos y recursos.** Hemos separado el modelo de embeddings del modelo generativo porque cumplen funciones distintas. El primero transforma texto en vectores para recuperación; el segundo interpreta la conversación, solicita herramientas y redacta respuestas. En desarrollo utilizamos Ollama para embeddings y Gemini para generación, evitando cargar dos modelos grandes en el equipo. En producción compararíamos inferencia propia y servicios gestionados utilizando mediciones de latencia, concurrencia y coste total, sin fijar una tecnología antes de conocer la carga.

**API de cartas.** Dependemos de un proveedor externo que puede cambiar sus respuestas, tardar o no estar disponible. Mantendríamos timeouts, reintentos acotados para errores transitorios y caché con caducidad. El adaptador seguiría ofreciendo nuestros modelos `Card` y `CardQuery`, de modo que cambiar de proveedor no obligase a reescribir el agente. También dejaríamos explícito que los resultados son impresiones de cartas, que una carta puede aparecer en varios sets y que buscar cartas que contienen blanco no equivale a buscar solo monoblancas.

**Degradación controlada.** Si falla Gemini o una herramienta, registraríamos el error sin mostrar trazas internas al usuario. No afirmaríamos haber recuperado datos que no se han obtenido. Si la información disponible no basta, responderíamos con una limitación clara en lugar de completar los huecos con referencias inventadas.

## 7. Qué monitorizaríamos

No nos basta con saber que una petición terminó con HTTP 200. Necesitamos entender si el agente consultó lo necesario, cuánto tardó y qué dependencia concentró el coste o el fallo.

| Área | Qué mediríamos | Para qué nos sirve |
| --- | --- | --- |
| Disponibilidad | Tasa de errores, fallos de proveedores, solicitudes fallidas | Detectar caídas o degradaciones externas. |
| Latencia | Tiempo total, p50 y p95, latencia del LLM y de cada herramienta | Separar lentitud del modelo, búsqueda y API de cartas. |
| Consumo | Tokens de entrada y salida, llamadas al modelo y herramientas por turno | Vigilar gasto, cuota y comportamiento anómalo. |
| Evidencia | Consultas factuales sin fuentes, documentos recuperados, versión del índice | Detectar respuestas sin respaldo y problemas de cobertura. |
| Ingesta | Pendientes, nuevos, reutilizados, fallidos y duración por lote | Saber si una actualización progresa y dónde se detiene. |
| Operación | Reintentos, respuestas degradadas, límites alcanzados y cancelaciones | Encontrar patrones que no aparecen en un error aislado. |

Ya hemos introducido logging centralizado por módulo y mensajes en hitos relevantes. Evitamos registrar cada regla o cada línea ejecutada, porque eso añade ruido y dificulta encontrar lo importante. En producción generaríamos logs estructurados e incorporaríamos identificadores de petición y sesión, versión del índice y duración de operaciones. Utilizaríamos OpenTelemetry para correlacionar el recorrido entre API, agente, herramientas y worker, con cuadros de mando y alertas sobre errores y latencias.

No registraríamos claves, respuestas completas del proveedor ni conversaciones personales por defecto. Si necesitáramos ejemplos de consultas para evaluar calidad, estableceríamos controles de acceso, retención y un tratamiento de datos compatible con el contexto de uso.

No fijamos objetivos numéricos de disponibilidad o latencia como si ya estuvieran validados. Primero mediríamos una línea base y acordaríamos niveles de servicio realistas para el volumen y las expectativas del producto.

## 8. Seguridad y control de acceso

Desde el desarrollo hemos tratado las credenciales como secretos. La API key se obtiene de variables de entorno cargadas localmente desde un `.env` excluido de Git; el repositorio puede incluir un `.env.example` sin valores reales. En producción inyectaríamos credenciales desde un gestor de secretos, con identidades de servicio, permisos mínimos y capacidad de rotación. Nunca entregaríamos la clave del proveedor al navegador.

En la API aplicaríamos autenticación, autorización y cuotas. No todos los usuarios deberían poder lanzar una reconstrucción del índice, consultar información operativa o modificar la configuración del agente. Separaríamos los permisos de conversación de los administrativos y validaríamos los tamaños de entrada y los argumentos de cada herramienta.

Aunque una regla o una carta proceda de una fuente legítima, su contenido se trata como **dato externo, no como una instrucción del sistema**. El agente no ejecuta código arbitrario indicado por el modelo, solo funciones previamente autorizadas. Esta frontera reduce el riesgo de que un texto recuperado cambie el comportamiento del asistente mediante *prompt injection*.

Si el producto atendiera a varias organizaciones, aislaríamos sesiones y datos entre ellas. También definiríamos plazos de retención y borrado, y revisaríamos las condiciones de los proveedores antes de enviar contenido de usuarios a modelos externos. El nivel gratuito resulta útil para la demo, pero no constituye por sí mismo una política de operación productiva.

## 9. Cómo probaríamos la solución

Hemos comprobado las partes importantes de forma independiente antes de unirlas. Esto nos ha permitido localizar errores concretos, como una incompatibilidad en la construcción de respuestas de herramientas del SDK o una situación en la que Gemini seguía solicitando herramientas después de agotar las rondas permitidas.

Para producción mantendríamos tres niveles de pruebas:

**Pruebas de componentes.** Validaríamos los parsers frente al PDF de referencia, la normalización y paginación de Magic API, la sincronización incremental, la separación de sesiones y la validación de argumentos. Usaríamos clientes simulados para evitar llamadas reales al proveedor en cada ejecución de CI.

**Pruebas del agente.** Simularíamos respuestas con una o varias llamadas a herramientas, argumentos incorrectos, proveedores caídos, ausencia de texto final y límites agotados. También comprobaríamos que las referencias presentadas existen en las respuestas de las herramientas y que una carta personalizada no se presenta como una carta oficial.

**Pruebas de extremo a extremo.** Ejecutaríamos escenarios representativos de los cuatro requisitos del reto, con el sistema integrado. Para la demo basta con demostrar que los flujos funcionan y que la evidencia es visible. Para producción necesitaríamos ampliar la batería con casos ambiguos, preguntas sin cobertura y consultas complejas revisadas por personas con conocimiento de reglas.

No equipararíamos una buena búsqueda vectorial con una respuesta correcta. Durante el desarrollo observamos que una consulta general recuperaba reglas relacionadas pero incompletas, mientras que otra más precisa encontraba varias condiciones de derrota dentro de `104.3`. Esto valida la utilidad del recuperador, no su precisión absoluta. En producción mediríamos cobertura, relevancia, exactitud de citas y utilidad real mediante un conjunto de evaluación versionado.

## 10. Despliegue y evolución

No desplegaríamos todas las capacidades posibles el primer día. Empezaríamos con una versión operable y ampliaríamos componentes a partir de datos de uso.

**Primera versión productiva.** Desplegaríamos la API y el worker de ingesta por separado, respaldados por PostgreSQL con pgvector, almacenamiento de documentos y una cola persistente. Mantendríamos los clientes de modelos y cartas detrás de sus adaptadores. Añadiríamos autenticación, configuración segura, migraciones y pruebas automáticas en el proceso de despliegue.

**Estabilización.** Incorporaríamos publicación atómica de índices, caché de cartas, observabilidad distribuida, alarmas y pruebas de carga. Las actualizaciones del conocimiento tendrían reintentos e historial propio, y podríamos revertirlas sin interrumpir el chat.

**Escalado.** Solo si las medidas lo justificasen separaríamos más servicios, adoptaríamos un motor vectorial especializado o desplegaríamos inferencia propia. La API y los workers tienen perfiles de consumo distintos, por lo que preferimos escalarlos de manera independiente antes que multiplicar agentes o microservicios.

Mantendríamos entornos separados, controles de salud, copias de seguridad y un procedimiento de rollback. También presupuestaríamos el coste de los modelos según tokens, volumen de peticiones e indexaciones periódicas. El objetivo no sería minimizar un coste aislado, sino encontrar una relación sostenible entre calidad, latencia y operación.

## 11. Qué hemos decidido no complicar

**No hemos creado varios agentes.** No tenemos tres problemas independientes que necesiten tres modelos conversando entre sí, sino un asistente que consulta fuentes diferentes para responder una pregunta. Con tres herramientas y una política común de evidencia, dividir el razonamiento solo añadiría coordinación y dificultaría seguir el origen de cada decisión. Revisaríamos esta decisión si surgiesen tareas autónomas con requisitos distintos y pudiéramos demostrar una mejora medible.

**No hemos incorporado LangChain o LangGraph.** Nuestro bucle de herramientas es pequeño, tiene un límite claro y se puede probar con Python y el SDK del proveedor. Un framework tendría sentido si aumentase realmente la complejidad de estados, bifurcaciones o ejecuciones duraderas. Incorporarlo solo por abstracción añadiría dependencias sin resolver un problema actual.

**No hemos entrenado un modelo propio.** Las reglas son una fuente versionable y cambiante. Recuperarlas cuando se necesitan permite mantener referencias explícitas sin depender de que el modelo memorice una edición concreta del reglamento.

**No hemos obligado a completar la indexación para abrir la demo.** El índice parcial basta para enseñar el circuito funcional, pero esa decisión no se trasladaría sin más a producción. Publicaríamos únicamente una colección validada para la cobertura que se anuncie al usuario.

**No hemos convertido las cartas custom en un subsistema aparte.** Gemini ya puede generar contenido creativo y el historial permite editar un diseño anterior. Si más adelante necesitáramos cartas listas para exportar o validar mecánicamente, añadiríamos un esquema estructurado y comprobaciones específicas, no otra capa de agentes por defecto.

## 12. Conclusiones

Hemos construido la demo empezando por fuentes concretas, incorporando las herramientas necesarias y dejando la conversación y la interfaz para el final. Eso nos ha permitido comprobar cada integración por separado y terminar con un sistema capaz de consultar reglas, buscar cartas, tratar interacciones, mantener contexto y crear cartas personalizadas.

La propuesta de producción mantiene el mismo núcleo, pero cambia las garantías operativas. Separaríamos el chat de la ingesta, publicaríamos versiones verificadas del índice, persistiríamos sesiones, controlaríamos permisos y costes y observaríamos cada dependencia. Sobre todo, reforzaríamos la diferencia entre **mostrar una fuente consultada** y **demostrar que esa fuente respalda una afirmación**.

Hemos evitado añadir agentes, frameworks o servicios que todavía no aportan una mejora verificable. Preferimos una solución cuyas decisiones podamos explicar, probar y modificar con facilidad. Para MtgSage, ese es el criterio principal: responder utilizando las fuentes adecuadas, saber qué ha ocurrido durante la ejecución y poder evolucionar el sistema sin perder el control de sus resultados.
