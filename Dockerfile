# --- Stage 1: Builder ---
FROM python:3.12-slim as builder

# CRITICAL: Tell the system that /app is the home directory
# This forces Prisma and other tools to save files here instead of /root
WORKDIR /app
ENV HOME=/app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Prisma schema and generate client
# Because HOME=/app, this will generate files into /app/.cache/prisma-python
COPY prisma/ ./prisma/
RUN prisma generate

# Download AI Model
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# --- Stage 2: Runner (Rahti Production) ---
FROM python:3.12-slim

# CRITICAL: Set HOME again for the runtime
WORKDIR /app
ENV HOME=/app

# Install runtime libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    libatomic1 \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual env
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy the cache folder (which contains Prisma binaries AND AI models)
# Since we set HOME=/app in builder, the files are now in /app/.cache
COPY --from=builder /app/.cache /app/.cache

# Copy application code
COPY . .

# --- RAHTI PERMISSIONS ---
# Allow the random Rahti user (GID 0) to write to /app
RUN chgrp -R 0 /app && \
    chmod -R g+rwX /app

# Point Environment Variables explicitly to /app/.cache just to be safe
ENV PRISMA_CACHE_DIR="/app/.cache/prisma-python"
ENV TRANSFORMERS_CACHE="/app/.cache/huggingface"
ENV TORCH_HOME="/app/.cache/torch"
ENV HF_HOME="/app/.cache/huggingface"

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]