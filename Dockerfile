# One image serves the website and the API from the same address.

# 1. Build the website
FROM node:22-slim AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web/ ./
# The blame lexicon is shared with the Python engine.
COPY packages/narrative_core/lexicon.json /packages/narrative_core/lexicon.json
RUN npm run build

# 2. Python API, agents and engine
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.9.14 /uv /bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY packages ./packages
COPY services ./services
COPY demo_data ./demo_data
COPY --from=web /web/dist ./apps/web/dist
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH="/app:/app/packages"
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/v1/health')"
CMD ["uvicorn", "services.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
