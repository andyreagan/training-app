ARG PYTHON_VERSION=3.12-slim-bookworm
FROM python:${PYTHON_VERSION}

# Grab the uv binary from the official image — no separate install step needed.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Layer-cache-friendly dep install ─────────────────────────────────────────
# Copy only the files uv needs to resolve deps; the rest of the source comes
# later so code changes don't invalidate this cache layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ── Application source ────────────────────────────────────────────────────────
COPY . /app

# Install the project package itself (fast – just the editable wheel metadata).
RUN uv sync --frozen --no-dev

# Put the venv's bin on PATH so python/gunicorn/manage.py just work.
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# Production: gunicorn.  Dev compose overrides CMD with runserver.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "60", "config.wsgi"]
