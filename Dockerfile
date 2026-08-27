FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.5.9 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

# Dependencies resolve from the manifest alone, so this layer caches across code changes.
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN uv pip install --system --no-cache .

FROM python:3.12-slim
WORKDIR /app

RUN useradd --create-home --uid 1000 app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY src/ ./src/
USER app

ENV PORT=8080 PYTHONUNBUFFERED=1
EXPOSE 8080

# Cloud Run injects $PORT; uvicorn must bind it and 0.0.0.0 or the revision never goes ready.
CMD exec uvicorn sikia_lab.transport:app --host 0.0.0.0 --port ${PORT}
