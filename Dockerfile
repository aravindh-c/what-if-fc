# Stage 1 – build the React frontend
FROM node:22-slim AS web-builder
WORKDIR /build
COPY web/package.json web/package-lock.json ./web/
RUN npm ci --prefix web
COPY web ./web
RUN npm --prefix web run build

# Stage 2 – Python runtime
FROM python:3.12-slim
WORKDIR /app

# Non-root user
RUN adduser --disabled-password --gecos "" --uid 1000 appuser

# Install Python package (runtime deps only, no pytest/ruff/httpx)
COPY pyproject.toml .
COPY core core
COPY simulator simulator
COPY analytics analytics
COPY agents agents
COPY api api
RUN pip install --no-cache-dir .

# Copy built frontend from stage 1
COPY --from=web-builder /build/web/dist ./web/dist

ENV WHATIF_MODE=replay

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" \
    || exit 1

USER appuser

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
