FROM node:20-slim AS frontend
WORKDIR /app
COPY frontend/package*.json frontend/
RUN cd frontend && npm install
COPY frontend/ frontend/
RUN cd frontend && npm run build

FROM python:3.11-slim
WORKDIR /app

COPY pyproject.toml .
COPY src/ src/
COPY templates/ templates/
COPY scripts/ scripts/

RUN pip install --no-cache-dir -i https://mirrors.cloud.tencent.com/pypi/simple --trusted-host mirrors.cloud.tencent.com -e .

COPY --from=frontend /app/static static/
RUN mkdir -p data

EXPOSE 8080

CMD ["python", "-m", "src.cli", "serve"]
