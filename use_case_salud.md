# Apartado 3 — Caso de cliente: diseño de solución (Senior+)

**Propuesta:** asistente interno para consulta de documentación clínica, cálculos controlados y, en una fase posterior, prevaloración de ECG.  
**Cliente:** clínica privada de aproximadamente 80 profesionales sanitarios.  
**Criterio de diseño:** seguridad clínica, trazabilidad y una operación asumible por una sola persona de IT.

# 1. Resumen ejecutivo

Proponemos desarrollar un **asistente clínico inteligente, privado y de fácil mantenimiento**, que permita a los aproximadamente 80 profesionales sanitarios de la clínica acceder a protocolos, fichas de medicamentos y procedimientos mediante preguntas en lenguaje natural.

El objetivo no es sustituir el criterio médico, sino **facilitar el acceso a información clínica fiable, actualizada y verificable**, reduciendo el tiempo dedicado a consultar documentación y minimizando el riesgo de trabajar con información obsoleta.

La solución ofrecerá las siguientes capacidades:

- **Consultas clínicas:** responder preguntas sobre protocolos, medicamentos y procedimientos, incluyendo información contenida en tablas de dosificación. Las respuestas incorporarán referencias al documento, versión y página de origen.
- **Cálculos asistidos:** realizar operaciones como el cálculo de dosis según el peso o la función renal, utilizando fórmulas previamente validadas por profesionales sanitarios, en lugar de confiar los cálculos directamente al modelo de IA.
- **Especialización médica:** ofrecer asistentes configurados para distintas especialidades, utilizando sus protocolos y herramientas correspondientes, sin necesidad de entrenar y mantener un modelo diferente para cada una.
- **Prevaloración de electrocardiogramas (ECG):** incorporar un sistema especializado capaz de identificar determinados signos de riesgo y orientar su nivel de urgencia. Esta funcionalidad requerirá un componente clínicamente validado y se incorporará cuando se hayan verificado sus garantías de seguridad y viabilidad.

## ¿Por qué esta solución?

La propuesta está diseñada específicamente para las características y limitaciones de esta clínica.

En lugar de desarrollar una plataforma de IA desde cero, utilizaremos **Open WebUI como interfaz y plataforma de gestión**, junto con modelos de lenguaje ejecutados localmente mediante Ollama y herramientas de procesamiento documental como Docling.

Este enfoque presenta cuatro ventajas principales:

1. **Privacidad y control:** el procesamiento de las consultas, los documentos y los datos clínicos se realizará dentro de la infraestructura de la clínica, sin enviarlos a APIs externas. La base de datos MySQL de pacientes permanecerá aislada del asistente, al no ser necesaria su integración para las funcionalidades documentales iniciales.

2. **Mantenimiento sencillo:** priorizaremos herramientas existentes, interfaces gráficas y configuraciones reutilizables. El personal de IT podrá realizar las operaciones habituales, como gestionar usuarios y actualizar documentación, sin necesidad de programar en Python. Las integraciones clínicas especializadas y las incidencias avanzadas requerirán soporte técnico del proveedor.

3. **Coste controlado:** utilizaremos preferentemente tecnologías de código abierto y evitaremos entrenar modelos propios o mantener infraestructuras complejas. El dimensionamiento del servidor se determinará mediante pruebas de rendimiento, buscando un equilibrio entre inversión, calidad y capacidad.

4. **Seguridad clínica:** las respuestas estarán fundamentadas en documentación aprobada, los cálculos utilizarán herramientas validadas y el asistente reconocerá cuándo no dispone de información suficiente. El diagnóstico y las decisiones terapéuticas seguirán siendo responsabilidad de los profesionales sanitarios.

## Estrategia de implantación

Proponemos una implantación progresiva para reducir riesgos y evitar inversiones innecesarias.

La **primera fase** se centrará en la consulta documental, las referencias verificables, la especialización por áreas médicas y los cálculos clínicos validados.

La **segunda fase** incorporará el análisis de ECG, condicionado a encontrar una solución compatible con los requisitos de privacidad, presupuesto, validación clínica y cumplimiento normativo.

Antes de poner el sistema en producción, validaremos su comportamiento con preguntas y casos representativos seleccionados por los responsables médicos.

**En definitiva, buscamos una solución que la clínica pueda utilizar y mantener de forma sostenible, sin depender de un equipo especializado en inteligencia artificial y sin comprometer la privacidad de los pacientes ni la seguridad de las decisiones clínicas.**

## 2. Arquitectura propuesta

Proponemos una arquitectura sencilla, basada en componentes existentes y desplegada íntegramente en la infraestructura de la clínica.

**Open WebUI será el punto central del sistema**, proporcionando la interfaz de conversación, la gestión de usuarios y la búsqueda documental (RAG). El procesamiento mediante inteligencia artificial se realizará localmente utilizando Ollama.

### 2.1. Diagrama de arquitectura

```text
       INFRAESTRUCTURA LOCAL DE LA CLÍNICA

  ┌──────────────────────────────────────────┐
  │               Open WebUI                 │
  │       Interfaz, usuarios, RAG y citas    │
  └──────────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
     Ollama         ChromaDB      Herramientas
   Modelo LLM       Índice de       clínicas
   y embeddings     documentos    ├─ Cálculos
                                 └─ ECG (fase 2)

  PDF / Word ── Docling ── Índice documental
             Extracción    (con Ollama
             de contenido   y ChromaDB)


  SISTEMA EXISTENTE (AISLADO)
  ┌──────────────────────────────────────────┐
  │ Sistema de citas ── MySQL (pacientes)     │
  └──────────────────────────────────────────┘

  Sin conexiones a APIs externas con datos clínicos.
```

Todos los componentes del asistente se ejecutarán en la red privada de la clínica. El sistema MySQL existente permanecerá separado y no será accesible por el asistente.

### 2.2. Componentes principales

| Componente | Responsabilidad |
|---|---|
| **Open WebUI** | Interfaz web para los médicos. Gestiona usuarios, asistentes especializados, búsqueda documental y presentación de respuestas con sus fuentes. |
| **Ollama** | Ejecuta localmente el modelo de lenguaje y el modelo de embeddings necesario para la búsqueda semántica. |
| **ChromaDB** | Almacena los fragmentos de los documentos, sus vectores y metadatos. Utilizaremos el almacenamiento integrado de Open WebUI, evitando administrar un servidor vectorial independiente. |
| **Docling** | Procesa documentos PDF y Word, extrayendo texto y tablas para su posterior indexación. |
| **Herramientas clínicas** | Servicios internos para cálculos validados y, en una segunda fase, análisis de ECG mediante un componente especializado. |
| **MySQL** | Base de datos existente de pacientes y citas. Permanece aislada y fuera del alcance del asistente. |

**No necesitamos desarrollar un sistema de agentes personalizado.** Aprovecharemos las capacidades de Open WebUI y sus integraciones existentes, limitando el desarrollo específico a las funcionalidades clínicas que realmente lo requieran.

### 2.3. Separación y almacenamiento de datos

Distinguimos dos tipos de información:

- **Documentación clínica:** los PDF y Word permanecerán en el almacenamiento interno de la clínica. Docling extraerá su contenido y Open WebUI lo indexará mediante Ollama y ChromaDB. Se conservarán las referencias a los documentos originales, incluyendo versión y página.
- **Datos de pacientes:** permanecerán en MySQL, dentro del sistema de citas existente. No se consultarán ni indexarán en ChromaDB, ya que el asistente solo necesita los protocolos clínicos y los datos que el médico introduzca manualmente para realizar consultas o cálculos.

Los datos que un médico introduzca manualmente en una consulta, cálculo o ECG también se considerarán sensibles y permanecerán dentro de la infraestructura local.

### 2.4. Uso de servicios cloud

**Ningún componente que procese información clínica necesitará utilizar servicios cloud.**

Tanto la generación de respuestas como los embeddings, el procesamiento documental y las herramientas clínicas se ejecutarán localmente.

El cloud podrá utilizarse únicamente para tareas técnicas que no involucren información clínica, como obtener actualizaciones de software previamente autorizadas.

Para garantizar esta separación, restringiremos las conexiones salientes mediante controles de red, deshabilitando proveedores externos, herramientas y funcionalidades que puedan transmitir datos fuera de la clínica.

### 2.5. Flujo de una consulta

Supongamos que un médico pregunta:

*"¿Cuál es la dosis máxima del medicamento X para un paciente con insuficiencia renal?"*

1. **Consulta:** el médico accede a Open WebUI mediante su usuario corporativo y escribe la pregunta.

2. **Búsqueda:** Open WebUI recupera desde ChromaDB los fragmentos relevantes de los protocolos previamente procesados con Docling, incluyendo información de tablas de dosificación.

3. **Generación:** el modelo local, ejecutado mediante Ollama, recibe la pregunta y la información recuperada. Si faltan datos clínicos necesarios, debe solicitarlos en lugar de asumirlos.

4. **Cálculo, si procede:** cuando la respuesta requiere una operación, el asistente utiliza una herramienta clínica con fórmulas previamente validadas, en lugar de improvisar el cálculo.

5. **Respuesta:** el médico recibe una explicación en lenguaje natural, acompañada de las condiciones aplicables y las referencias al documento original. Si no existe evidencia suficiente, el asistente debe indicarlo expresamente.

Las referencias deberán verificarse contra los fragmentos recuperados para evitar citas inventadas o incorrectas.

### 2.6. Mantenimiento y operación

La infraestructura se desplegará mediante contenedores Docker, con configuraciones reproducibles, copias de seguridad y procedimientos documentados de actualización y restauración.

El personal de IT podrá gestionar las tareas habituales desde las interfaces de administración, sin necesidad de programar en Python.

La aprobación y revisión de los protocolos corresponderá a profesionales sanitarios autorizados. Las incidencias técnicas avanzadas y el mantenimiento de componentes médicos especializados contarán con soporte del proveedor.

De esta manera, **la complejidad técnica queda concentrada en el despliegue inicial**, mientras que la operación cotidiana se mantiene lo más sencilla posible para una clínica con recursos informáticos limitados.

## 3. Decisiones tecnológicas clave

| Componente | Elección | Justificación |
|---|---|---|
| **Modelo LLM** | Ollama + modelo local | Garantiza que las consultas y los datos clínicos no se envíen a APIs externas. Evita costes recurrentes por uso. |
| **Base de datos vectorial** | ChromaDB | Integrada en Open WebUI, sencilla de mantener y suficiente para los ~80 documentos de la clínica. |
| **Tablas de dosificación** | Docling | Extrae tablas de PDF conservando su estructura. Las tablas críticas se validarán antes de utilizarlas en respuestas clínicas. |
| **Imágenes clínicas en PDF** | Docling + documentos originales | Extraeremos las imágenes y conservaremos su relación con el documento. No realizaremos interpretaciones diagnósticas automáticas sin modelos validados. |
| **Herramienta de cálculos** | Calculadoras clínicas mediante API local | Utilizaremos fórmulas previamente validadas, evitando que el LLM improvise cálculos o dosis. |
| **Interfaz de usuario** | Open WebUI | Interfaz lista para usar, con gestión de usuarios, RAG y asistentes por especialidad. Reduce el desarrollo y facilita el mantenimiento sin Python. |

## 4. Lo que el sistema NO hará

Es importante definir estos límites para evitar expectativas equivocadas y garantizar un uso seguro del asistente.

- **No diagnosticará ni prescribirá tratamientos:** el asistente proporcionará información y cálculos de apoyo, pero las decisiones clínicas seguirán siendo responsabilidad del médico. Un LLM puede cometer errores, incluso cuando utiliza fuentes fiables.

- **No accederá directamente a los datos de pacientes:** la base de datos MySQL permanecerá aislada. Integrarla añadiría riesgos de privacidad y complejidad que no son necesarios para los objetivos iniciales.

- **No interpretará cualquier imagen médica:** el análisis de ECG se limitará a las capacidades de un módulo especializado y clínicamente validado. No se ofrecerán diagnósticos generales a partir de radiografías u otras imágenes.

Definir estas limitaciones permite **controlar el alcance, reducir riesgos y evitar costes innecesarios**, especialmente con un equipo de IT tan reducido.

## 5. Riesgos del proyecto

1. **Errores en las tablas de dosificación:** una extracción incorrecta de dosis, unidades o condiciones médicas podría generar respuestas peligrosas.
   - **Mitigación:** utilizar Docling y validar las tablas críticas con profesionales sanitarios antes de incorporarlas al sistema.

2. **Información clínica desactualizada:** los protocolos cambian cada 3-6 meses y el asistente podría consultar versiones obsoletas.
   - **Mitigación:** establecer un proceso de actualización y aprobación documental, manteniendo únicamente las versiones vigentes en las búsquedas.

3. **Errores en la interpretación de ECG:** un falso negativo podría retrasar la atención de un paciente con una condición grave.
   - **Mitigación:** utilizar exclusivamente un módulo especializado y clínicamente validado, siempre bajo supervisión médica.

4. **Dependencia de una única persona de IT:** es uno de los riesgos más graves del proyecto. Aunque Open WebUI simplifica la operación, las actualizaciones, fallos de infraestructura e integraciones clínicas pueden superar los conocimientos del responsable técnico.
   - **Mitigación:** minimizar los componentes, documentar los procedimientos, automatizar copias de seguridad y contratar soporte externo para incidencias avanzadas. Además, formar al responsable de IT antes de entregar el sistema.