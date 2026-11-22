# Una sola imagen con el código de todos los microservicios; cada contenedor corre un comando distinto
# (docker-compose.yml). Versiones fijas, sin la última: Python 3.14.7 y uv 0.12.19.
FROM python:3.14.7-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# Primero las dependencias (capa que casi no cambia), luego el código.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY db ./db
COPY catalog ./catalog
COPY evidence ./evidence
RUN uv sync --frozen --no-dev

# Los servicios no corren como root.
RUN useradd --create-home --uid 1000 servicio \
    && mkdir -p /datos/fotos && chown servicio /datos/fotos   # el volumen de fotos hereda este dueño
USER servicio
