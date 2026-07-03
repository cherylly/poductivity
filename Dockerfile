FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM python:3.11-slim
WORKDIR /app

COPY pyproject.toml .
COPY src/ src/
COPY templates/ templates/

RUN pip install --no-cache-dir -e .

COPY --from=frontend /app/static static/
RUN mkdir -p data

EXPOSE 8080

CMD ["python", "-m", "src.cli", "serve"]
