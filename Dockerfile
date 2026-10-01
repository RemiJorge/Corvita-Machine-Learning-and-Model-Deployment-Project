# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --frozen --no-dev

FROM python:3.12-slim AS runtime

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"
ENV PORT=8080

RUN groupadd --system app && useradd --system --gid app app

COPY --from=builder /app/.venv /app/.venv
COPY src ./src
COPY config ./config
COPY models/1.0.0 ./models/1.0.0
COPY models/1.0.1 ./models/1.0.1

USER app

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8080\")}/health')"

CMD ["sh", "-c", "uvicorn icu.api.app:app --host 0.0.0.0 --port ${PORT:-8080}"]
