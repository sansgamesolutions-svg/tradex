# Stage 1: install dependencies using uv
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

# Copy only the project manifest first — lets Docker cache the dep-install layer
# independently of source-code changes.
COPY pyproject.toml .

# Install all production dependencies into an in-project venv.
# --no-install-project: skip installing tradex itself (source not copied yet).
# --no-dev: exclude dev tools (pytest, ruff, etc.).
RUN uv sync --no-dev --no-install-project


# Stage 2: lean runtime image
FROM python:3.12-slim-bookworm

WORKDIR /app

# Copy the pre-built venv from the builder stage
COPY --from=builder /app/.venv .venv

# Copy application source
COPY tradex/ tradex/
COPY scripts/ scripts/

# Activate the venv and set Python env flags
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "tradex.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
