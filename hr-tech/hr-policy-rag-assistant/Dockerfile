# Stage 1: compile the TypeScript front end
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/tsconfig.json ./
RUN npm install --no-audit --no-fund
COPY web/src ./src
RUN npx tsc -p tsconfig.json

# Stage 2: the Python service
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src PORT=8000
WORKDIR /app
COPY requirements.txt requirements-postgres.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-postgres.txt
COPY src ./src
COPY policies ./policies
COPY eval ./eval
COPY web/index.html ./web/index.html
COPY --from=web /web/dist ./web/dist
RUN useradd --create-home --uid 10001 app && mkdir -p /app/outputs && chown -R app /app/outputs
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"
CMD ["python", "-m", "hrrag.api"]
