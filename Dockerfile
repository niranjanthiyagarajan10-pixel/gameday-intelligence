# One container serves the API and the built dashboard. Used by Azure Container Apps.

FROM node:20-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app
COPY pyproject.toml README.md ./
COPY engine/ engine/
COPY agents/ agents/
COPY app/ app/
COPY mcp_server/ mcp_server/
RUN pip install --no-cache-dir .
COPY data/ data/
COPY --from=web /web/dist web/dist
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
