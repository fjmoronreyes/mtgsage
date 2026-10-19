#!/usr/bin/env bash
# Preparación reproducible de MtgSage en Linux o Windows + WSL2.
# No requiere sudo, no almacena secretos en Git y no indexa automáticamente.
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
umask 077

MODEL="qwen3-embedding:0.6b"
SKIP_MODEL=0
ASSUME_YES=0
READY=1

info() { printf '[INFO] %s\n' "$*"; }
ok()   { printf '[ OK ] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*" >&2; READY=0; }
fail() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<'HELP'
Uso: bash setup.sh [--yes] [--skip-model] [--help]

  --yes          Autoriza la descarga del modelo de Ollama si falta.
  --skip-model   Prepara Python y .env sin descargar/comprobar el modelo.
  --help         Muestra esta ayuda.

Requisitos de sistema: Linux o Ubuntu en WSL2, Python 3.14.x,
Poetry 2.x y Ollama instalado. Si falta Poetry y existe pipx,
el script intentará instalar Poetry 2.5.1 para el usuario.
No instala Python ni ejecuta scripts de terceros con sudo.
HELP
}

while (($#)); do
    case "$1" in
        --yes) ASSUME_YES=1 ;;
        --skip-model) SKIP_MODEL=1 ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; fail "Opción no reconocida: $1" ;;
    esac
    shift
done

[[ "$(uname -s)" == 'Linux' ]] || fail \
    "Este instalador se ha preparado para Linux/WSL2. Consulta README.md para otros sistemas."
[[ "${EUID:-$(id -u)}" != '0' ]] || fail \
    "No ejecutes el setup como root. El entorno debe pertenecer a tu usuario."
[[ -f pyproject.toml && -f poetry.lock ]] || fail \
    "No encontramos pyproject.toml y poetry.lock en $ROOT."
[[ -f .env.example ]] || fail \
    "Falta .env.example. Añádelo desde los archivos de instalación."
[[ -f .gitignore ]] || fail "Falta .gitignore; no podemos proteger .env."

# No creamos un archivo con secretos si Git pudiera incluirlo en un commit.
if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git check-ignore -q -- .env || fail \
        "El archivo .env NO está ignorado por Git. Añade '.env' a .gitignore antes de continuar."
    if git ls-files --error-unmatch .env >/dev/null 2>&1; then
        fail "El archivo .env está versionado. Retíralo del índice de Git y rota la clave."
    fi
else
    # Fuera de un clon Git, se exige al menos una regla explícita.
    grep -Eq '^\.env([[:space:]]|$)' .gitignore || fail \
        "Añade '.env' a .gitignore antes de continuar."
fi

info "Proyecto: $ROOT"

# 1. Crear la configuración local sin sobrescribir secretos existentes.
if [[ -L .env ]]; then
    fail "Por seguridad, .env no puede ser un enlace simbólico."
fi
if [[ ! -e .env ]]; then
    cp .env.example .env
    chmod 600 .env
    ok "Creado .env con permisos de lectura para el usuario."
else
    chmod 600 .env
    ok "Conservamos el .env existente."
fi

write_api_key() {
    local key="$1" line replaced=0 tmp
    tmp="$(mktemp "$ROOT/.env.tmp.XXXXXX")"
    chmod 600 "$tmp"
    while IFS= read -r line || [[ -n "$line" ]]; do
        if [[ "$line" == GEMINI_API_KEY=* ]]; then
            if ((replaced == 0)); then
                printf 'GEMINI_API_KEY=%s\n' "$key" >> "$tmp"
                replaced=1
            fi
        else
            printf '%s\n' "$line" >> "$tmp"
        fi
    done < .env
    if ((replaced == 0)); then
        printf 'GEMINI_API_KEY=%s\n' "$key" >> "$tmp"
    fi
    mv -f "$tmp" .env
    chmod 600 .env
}

# Preguntamos la clave de forma oculta solo si es interactivo y no hay una
# variable de entorno preconfigurada. Nunca la imprimimos.
if [[ -z "${GEMINI_API_KEY:-}" ]] && ! grep -Eq '^GEMINI_API_KEY=.+[^[:space:]]' .env; then
    if [[ -t 0 ]]; then
        printf 'Clave de Gemini (entrada oculta, Enter para configurarla después): '
        IFS= read -r -s API_KEY || true
        printf '\n'
        if [[ -n "${API_KEY:-}" ]]; then
            [[ "$API_KEY" != *$'\n'* && "$API_KEY" != *$'\r'* ]] || fail \
                "La clave no puede contener saltos de línea."
            write_api_key "$API_KEY"
            unset API_KEY
            ok "Clave guardada localmente en .env, sin mostrar su valor."
        else
            info "La clave podrá configurarse más tarde en .env."
        fi
    fi
fi

# 2. Seleccionar un intérprete Python compatible con el proyecto.
EXPECTED_PYTHON="$(tr -d '\r\n[:space:]' < .python-version 2>/dev/null || printf '3.14.8')"
[[ -n "$EXPECTED_PYTHON" ]] || EXPECTED_PYTHON='3.14.8'
PY_MINOR="$(printf '%s' "$EXPECTED_PYTHON" | cut -d. -f1,2)"
PYTHON_BIN=''

for candidate in \
    "${PYENV_ROOT:-$HOME/.pyenv}/versions/$EXPECTED_PYTHON/bin/python" \
    "python$PY_MINOR" python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        executable="$(command -v "$candidate")"
        if "$executable" -c \
            'import sys; sys.exit(0 if sys.version_info[:2] == (3, 14) else 1)' \
            >/dev/null 2>&1; then
            PYTHON_BIN="$executable"
            break
        fi
    fi
done

if [[ -z "$PYTHON_BIN" ]]; then
    cat >&2 <<EOF
[ERROR] No encontramos Python 3.14.x.
Instala la versión recomendada ($EXPECTED_PYTHON), por ejemplo con pyenv:
  pyenv install -s $EXPECTED_PYTHON
  pyenv local $EXPECTED_PYTHON
Después vuelve a ejecutar: bash setup.sh
Más detalles: https://github.com/pyenv/pyenv#installation
EOF
    exit 1
fi
PY_VERSION="$($PYTHON_BIN -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
ok "Python encontrado: $PY_VERSION ($PYTHON_BIN)"
if [[ "$PY_VERSION" != "$EXPECTED_PYTHON" ]]; then
    info "El proyecto se desarrolló con Python $EXPECTED_PYTHON; usaremos $PY_VERSION."
fi

# 3. Resolver Poetry sin instalar nada globalmente con pip.
if ! command -v poetry >/dev/null 2>&1; then
    if command -v pipx >/dev/null 2>&1; then
        info "Poetry no está instalado. Intentamos instalar Poetry 2.5.1 con pipx."
        pipx install 'poetry==2.5.1' || fail \
            "No se pudo instalar Poetry. Consulta la instalación manual del README."
        export PATH="$HOME/.local/bin:$PATH"
    else
        fail "Faltan Poetry y pipx. Instala pipx y ejecuta 'pipx install poetry==2.5.1'."
    fi
fi
command -v poetry >/dev/null 2>&1 || fail \
    "Poetry no está en PATH. Ejecuta 'pipx ensurepath' y abre otra terminal."
POETRY_MAJOR="$(poetry --version | grep -oE '[0-9]+' | head -1)"
[[ "$POETRY_MAJOR" == '2' ]] || fail \
    "Necesitamos Poetry 2.x. Versión detectada: $(poetry --version)"
ok "$(poetry --version)"

# 4. Entorno reproducible desde poetry.lock, alojado en .venv.
info "Preparando .venv y sincronizando dependencias desde poetry.lock..."
export POETRY_VIRTUALENVS_IN_PROJECT=true
poetry env use "$PYTHON_BIN" || fail "No se pudo seleccionar Python para Poetry."
poetry sync --no-interaction || fail "Falló poetry sync. Revisa la conexión o el lockfile."
ok "Dependencias instaladas en el entorno de Poetry."

# 5. Confirmación segura, sin imprimir la clave.
if poetry run python -c \
    'from app.config import GEMINI_API_KEY; raise SystemExit(0 if GEMINI_API_KEY else 1)' \
    >/dev/null 2>&1; then
    ok "Gemini configurado (clave oculta)."
else
    warn "Falta GEMINI_API_KEY. Añádela a .env para utilizar el chat."
fi

# 6. Fuente del corpus. No descargamos una versión distinta del reglamento.
if [[ -f 'data/MagicCompRules 20260417.pdf' ]]; then
    ok "PDF de referencia localizado."
else
    warn "Falta data/MagicCompRules 20260417.pdf. Obtén la versión de 17/04/2026 y cópiala en data/."
fi

# 7. Ollama y modelo, respetando las instalaciones del sistema.
if ((SKIP_MODEL == 1)); then
    info "Omitimos la comprobación y descarga del modelo por --skip-model."
elif ! command -v ollama >/dev/null 2>&1; then
    warn "Ollama no está instalado. Consulta https://ollama.com/download/linux"
elif ! ollama list >/dev/null 2>&1; then
    warn "Ollama no responde. Inicia el servicio con 'sudo systemctl start ollama' o 'ollama serve'."
elif ollama list | awk 'NR>1 {print $1}' | grep -Fxq "$MODEL"; then
    ok "Modelo de embeddings disponible: $MODEL"
else
    pull=0
    if ((ASSUME_YES == 1)); then
        pull=1
    elif [[ -t 0 ]]; then
        printf 'Descargar %s con Ollama (aprox. 640 MB)? [s/N]: ' "$MODEL"
        IFS= read -r answer || true
        case "${answer:-}" in s|S|si|sí|SI|SÍ|y|Y) pull=1 ;; esac
    fi
    if ((pull == 1)); then
        info "Descargando $MODEL..."
        if ollama pull "$MODEL"; then
            ok "Modelo de embeddings descargado."
        else
            warn "Falló la descarga de $MODEL. Puedes reintentarlo con 'ollama pull $MODEL'."
        fi
    else
        warn "Modelo pendiente. Ejecuta 'ollama pull $MODEL' cuando estés listo."
    fi
fi

printf '\n'
if ((READY == 1)); then
    if ((SKIP_MODEL == 1)); then
        ok "Entorno Python preparado. Ollama y el modelo no se han verificado."
    else
        ok "MtgSage listo para arrancar."
    fi
    printf '  poetry run python -m streamlit run app/mtg_sage.py\n'
    printf '  poetry run python -m pytest -q\n'
else
    printf '[INFO] El entorno Python se ha preparado, pero quedan requisitos pendientes.\n'
    printf '[INFO] Revisa los avisos anteriores y vuelve a ejecutar bash setup.sh.\n'
    exit 2
fi
