# MtgSage

Asistente conversacional de **Magic: The Gathering** desarrollado como prueba técnica de ingeniería de IA. Resolvemos dudas de reglas, consultamos interacciones entre cartas, buscamos cartas mediante descripciones en lenguaje natural y generamos cartas personalizadas no oficiales.

La aplicación combina **Gemini** para la generación y selección de herramientas, **Ollama** para embeddings locales, **ChromaDB** para consultar el reglamento y **Magic API** para obtener información de cartas. La interfaz está construida con **Streamlit**.

> **Alcance:** es una demo funcional. Las referencias mostradas indican qué fuentes se han consultado, pero no garantizan que todas las interpretaciones del modelo sean correctas. El índice puede estar parcialmente construido.

## 1. Requisitos

Hemos preparado el proyecto para **Ubuntu 24.04 en WSL2 o Linux**, con estos componentes:

| Componente | Versión utilizada | Para qué lo necesitamos |
| --- | --- | --- |
| Python | **3.14.8** | Ejecución de la aplicación y las pruebas. |
| Poetry | **2.5.1** (compatible con 2.x) | Entorno virtual y dependencias fijadas en `poetry.lock`. |
| Ollama | Versión compatible con `/api/embed` | Servicio local de embeddings. |
| `qwen3-embedding:0.6b` | Modelo de Ollama, aprox. 640 MB de descarga | Embeddings de reglas y preguntas. |
| Google Gemini API | Clave de un proyecto habilitado | Generación de respuestas y llamadas a herramientas. |
| Documento de reglas | **17 de abril de 2026** | Fuente de conocimiento y referencias del agente. |

Necesitamos conexión a Internet para instalar dependencias, descargar el modelo, consultar la API de cartas y utilizar Gemini. El modelo de Ollama se ejecuta en CPU, aunque la indexación completa puede tardar bastante según el equipo. No exigimos Docker ni GPU.

**Descargas y documentación oficial:**

- [Python](https://www.python.org/downloads/) y [pyenv](https://github.com/pyenv/pyenv#installation), para instalar o seleccionar Python 3.14.8.
- [Poetry](https://python-poetry.org/docs/#installation) y [pipx](https://pipx.pypa.io/stable/installation/), para gestionar dependencias.
- [Ollama para Linux](https://ollama.com/download/linux), para instalar el servidor local.
- [Modelo `qwen3-embedding:0.6b`](https://ollama.com/library/qwen3-embedding), disponible desde Ollama.
- [Google AI Studio, claves API](https://aistudio.google.com/apikey), para crear una clave de Gemini. El nivel gratuito está sujeto a cuotas y disponibilidad.
- [Reglas oficiales de Magic](https://magic.wizards.com/en/rules), donde se publican los reglamentos. La demo espera **la edición concreta del 17/04/2026**; una versión más reciente no es un sustituto equivalente.

## 2. Instalación rápida en WSL2 o Linux

Clonamos el repositorio, siempre que tengamos acceso a él:

```bash
git clone https://github.com/fjmoronreyes/mtgsage.git
cd mtgsage
```

Instalamos primero **Python 3.14.x**, **Poetry 2.x** y **Ollama**, si todavía no están disponibles. `setup.sh` comprueba su existencia, puede instalar Poetry mediante `pipx` si este ya existe y prepara automáticamente el entorno Python. No instala componentes del sistema mediante `sudo` sin nuestro conocimiento.

```bash
bash setup.sh
```

El instalador:

1. Comprueba la versión de Python y la presencia de Poetry.
2. Crea o reutiliza `.venv` y ejecuta `poetry sync` desde `poetry.lock`.
3. Crea `.env` a partir de `.env.example` si no existe, sin sobrescribir claves anteriores.
4. Permite introducir `GEMINI_API_KEY` **sin mostrarla en pantalla**, cuando se ejecuta desde una terminal interactiva.
5. Comprueba que `.env` esté fuera de Git, que Ollama responda y que el modelo esté disponible. Puede preguntar si queremos descargarlo.
6. Comprueba que el PDF esperado esté en su ubicación y señala lo que falte.

Si faltan prerrequisitos, nos dirá cómo instalarlos. Podemos ejecutar el script tantas veces como necesitemos: **no borra el índice ni modifica la clave existente**.

Para automatizar también la descarga del modelo, una vez instalado y arrancado Ollama:

```bash
bash setup.sh --yes
```

Para preparar únicamente las dependencias Python, sin consultar ni descargar el modelo:

```bash
bash setup.sh --skip-model
```

### Configurar la clave de Gemini

La clave vive en `.env`, en la raíz del repositorio:

```dotenv
GEMINI_API_KEY=tu_clave_personal
```

**No lleva comillas**, aunque `python-dotenv` también las admite. El archivo no debe subirse a Git, compartirse ni aparecer en logs. `.env.example` contiene solo una plantilla sin secretos.

Podemos comprobar que está configurada sin revelar su valor:

```bash
poetry run python -c "from app.config import GEMINI_API_KEY; print('Gemini configurado:', bool(GEMINI_API_KEY))"
```

Si se expone una clave, debemos revocarla y sustituirla por otra.

### Preparar el PDF de referencia

Situamos el reglamento proporcionado para el reto en esta ubicación **exacta**:

```text
data/MagicCompRules 20260417.pdf
```

El PDF y la base de vectores están excluidos de Git. No los descargamos automáticamente desde una URL variable porque el parser trabaja con la versión y el formato utilizados durante el desarrollo. El programa no puede construir un índice completo sin el PDF.

## 3. Instalación manual

Si preferimos configurar cada componente, este es el procedimiento que hemos utilizado.

**Entorno WSL2 (solo para usuarios de Windows):**

```powershell
wsl --install -d Ubuntu-24.04
```

Reiniciamos Windows si el instalador lo solicita y ejecutamos el resto de comandos **dentro de Ubuntu**, no en PowerShell. Recomendamos clonar el repositorio en el sistema de archivos de Linux, por ejemplo `~/projects/mtgsage`, en lugar de `/mnt/c/`.

**Python y Poetry:**

Instalamos pyenv siguiendo su [guía oficial](https://github.com/pyenv/pyenv#installation) y después ejecutamos:

```bash
pyenv install -s 3.14.8
pyenv local 3.14.8
```

Instalamos pipx y Poetry si todavía no los tenemos:

```bash
sudo apt update
sudo apt install -y pipx
pipx ensurepath
pipx install 'poetry==2.5.1'
```

Si acabamos de instalar `pipx`, puede ser necesario abrir otra terminal para que `poetry` aparezca en el `PATH`.

Desde la raíz del repositorio:

```bash
poetry env use "$(pyenv which python)"
poetry sync
```

Poetry utilizará las dependencias fijadas en `poetry.lock`; **no necesitamos ejecutar `poetry add` ni modificar versiones**.

**Ollama y embeddings:**

Instalamos Ollama siguiendo su [página oficial](https://ollama.com/download/linux), iniciamos el servicio si es necesario y descargamos el modelo:

```bash
sudo systemctl start ollama
ollama pull qwen3-embedding:0.6b
ollama list
```

Si nuestra distribución no utiliza `systemd`, podemos iniciar Ollama manualmente con `ollama serve` en otra terminal. La URL local por defecto del servicio es `http://localhost:11434`.

**Configuración local:**

```bash
cp -n .env.example .env
chmod 600 .env
```

Editamos `.env` para añadir la clave de Gemini y copiamos el PDF de reglas a `data/`. El instalador `setup.sh` puede validar después todos los requisitos.

## 4. Ejecutar MtgSage

Con las dependencias y el PDF preparados, arrancamos la interfaz:

```bash
poetry run python -m streamlit run app/mtg_sage.py
```

Abrimos **http://localhost:8501** en el navegador. Desde Streamlit encontramos dos vistas:

- **Indexación:** podemos continuar una indexación anterior, reconstruir el índice con confirmación, limitar el número de documentos y ver el avance, los documentos reutilizados y el tiempo estimado.
- **Chat:** formulamos preguntas al agente. La respuesta incluye un desplegable con las herramientas ejecutadas y las fuentes realmente consultadas cuando existen.

**Para una primera prueba no hace falta indexar las 3.868 entradas.** Podemos empezar con 20 o 100 documentos. La cobertura de las respuestas dependerá de las reglas que ya estén incorporadas al índice.

### Indexar también desde la terminal

```bash
# Prueba rápida de ingesta
poetry run python -m app.indexer --limit 20

# Añadir los documentos restantes sin recalcular los que no han cambiado
poetry run python -m app.indexer

# Destruir y reconstruir la colección: solo si queremos empezar de cero
poetry run python -m app.indexer --recreate
```

**Importante:** no ejecutamos el indexer por terminal a la vez que la indexación desde Streamlit. La coordinación de acceso a ChromaDB de esta demo solo opera dentro del proceso de la interfaz.

### Ejemplos de preguntas

```text
¿Qué fases tiene un turno de Magic?
¿Cómo funciona dañar primero?
Busca guerreros blancos con un valor de maná inferior a dos.
¿Qué sucede si mi criatura con dañar primero bloquea una criatura con toque mortal?
Crea una carta no oficial de Han Solo, roja y blanca, que tenga dañar primero.
Ahora reduce su coste en un maná y añade prisa.
```

## 5. Pruebas

```bash
poetry run python -m pytest -v
```

El proyecto incluye pruebas de extracción del PDF, de la API de cartas y de la lógica del agente. Algunas requieren el documento local en la ruta prevista; otras utilizan clientes simulados y no consumen cuota de Gemini.

## 6. Estructura del proyecto

```text
MtgSage/
├── app/
│   ├── agents/                # Agente, herramientas y conversación
│   ├── cards/                 # Cliente y modelos de cartas
│   ├── jobs/                  # Indexación en segundo plano
│   ├── llm/                   # Adaptador de Gemini
│   ├── parsers/               # Reglamento y glosario
│   ├── semantic/              # Ollama y ChromaDB
│   ├── config.py              # Rutas y configuración
│   ├── indexer.py             # Indexación también desde CLI
│   ├── logger.py              # Logging centralizado
│   └── mtg_sage.py            # Interfaz Streamlit
├── data/                      # PDF e índice local, no versionados
├── tests/
├── documento_explicativo_apartado1.md
├── .env.example
├── .python-version
├── setup.sh
├── pyproject.toml
└── poetry.lock
```

El documento [`documento_explicativo_apartado1.md`](documento_explicativo_apartado1.md) explica con más detalle la arquitectura productiva, las decisiones tecnológicas, la observabilidad, la gestión de sesiones y los compromisos de la demo.

## 7. Seguridad y límites de la demo

- **Secretos:** `.env` está excluido de Git; solo compartimos `.env.example`. En producción utilizaríamos un gestor de secretos e identidades de servicio. Antes del commit, comprobamos que `.gitignore` contemple estas rutas:

  ```gitignore
  .env
  .env.*
  !.env.example
  .venv/
  data/chroma/
  data/*.pdf
  ```
- **Modelos:** Ollama genera embeddings localmente. Gemini utiliza una API externa con las condiciones de uso y cuotas asociadas a la clave proporcionada.
- **Fuentes:** una carta custom es una creación no oficial, por lo que no necesita una referencia a una carta real. Las preguntas factuales deberían utilizar las fuentes recuperadas.
- **Persistencia:** ChromaDB conserva los vectores en `data/chroma/`. Las conversaciones de la demo viven en memoria y pueden perderse al reiniciar la aplicación.
- **Disponibilidad:** la API de cartas y Gemini requieren Internet. La indexación extensa es costosa en CPU y no se ejecuta automáticamente durante la instalación.

## 8. Problemas habituales

| Síntoma | Comprobación o solución |
| --- | --- |
| `Python 3.14` no disponible | Instalar la versión indicada en `.python-version` con pyenv y repetir `bash setup.sh`. |
| `poetry: command not found` | Ejecutar `pipx ensurepath` y abrir una nueva terminal. |
| Gemini no encuentra la API key | Comprobar que `.env` contiene `GEMINI_API_KEY=` con valor y que no ha sido revocada. |
| Ollama no responde | Verificar `ollama list` y arrancar `ollama serve` o el servicio del sistema. |
| Falta el modelo | Ejecutar `ollama pull qwen3-embedding:0.6b`. |
| No se encuentra el reglamento | Revisar la ruta y el nombre exactos de `data/MagicCompRules 20260417.pdf`. |
| El chat devuelve pocas referencias | Aumentar la cobertura del índice desde la pestaña **Indexación**. |
| La indexación tarda demasiado | Probar primero con 20 o 100 documentos. Los lotes completados se conservan si interrumpimos el proceso. |

---

**Estado del proyecto:** demo técnica local. La arquitectura de producción y sus decisiones están desarrolladas en el documento explicativo del apartado 1.
