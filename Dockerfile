FROM node:20-slim AS frontend
WORKDIR /app
COPY frontend/package*.json frontend/
RUN cd frontend && npm ci
COPY frontend/ frontend/
RUN cd frontend && npm run build

FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ src/
COPY templates/ templates/
COPY scripts/ scripts/

RUN pip install --no-cache-dir -e .

COPY --from=frontend /app/static static/
RUN mkdir -p data

EXPOSE 8080

CMD ["python", "-m", "src.cli", "serve"]
