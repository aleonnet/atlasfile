# Estágio 1 — bundle de produção da UI (tsc + vite build). O contexto do build
# é a raiz do repo e o .dockerignore exclui frontend/node_modules e
# frontend/dist do host: o install é sempre nativo do container e o dist é
# sempre recompilado aqui (nada pré-buildado do host entra).
FROM node:22-alpine AS webbuild

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# Estágio 2 — app consolidado: uvicorn serve API (/api/*, /health), MCP (/mcp)
# e a UI estática (/) num único processo. 1 worker por desenho: sessões do MCP
# streamable HTTP vivem em memória por worker e os watchers (auto-reconcile,
# auto-ingest, channels) não podem rodar N vezes — escalar exigiria
# stateless_http e extrair os background jobs.
FROM python:3.12-slim

# Versão do artefato, injetada no build (release.yml passa a tag; o overlay de
# dev passa "dev"). Vira env porque .dockerignore exclui .git — não há como
# derivar a versão de dentro do build — e o settings a expõe em /api/setup/status.
ARG ATLASFILE_VERSION=dev
ENV ATLASFILE_VERSION=${ATLASFILE_VERSION}

WORKDIR /workspace/backend

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-por \
    unrar-free \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/unrar-free /usr/bin/unrar

# O lock trava o resolve inteiro (transitivos inclusive); requirements.txt
# segue como fonte dos top-level e insumo para regenerar o lock.
COPY backend/requirements.lock.txt ./requirements.lock.txt
RUN pip install --no-cache-dir -r requirements.lock.txt

COPY backend/app ./app
COPY config /workspace/config
# UI de produção no caminho que settings.static_dir aponta — o mount em "/"
# (fim de app/main.py) só acontece quando este diretório existe.
COPY --from=webbuild /app/dist /workspace/static

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
