FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# The virtual environment is outside /app, because Compose mounts the repository on /app.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml uv.lock ./
# The Makefile passes one "--group phaseN" for each phase that you started.
ARG UV_GROUPS=""
RUN uv sync --frozen --no-dev $UV_GROUPS

COPY . .
EXPOSE 8000
CMD ["uvicorn", "assistant.api:app", "--host", "0.0.0.0", "--port", "8000"]
