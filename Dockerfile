# --- Stage 1: Builder ---
FROM python:3.12-slim as builder

WORKDIR /app

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
COPY prisma/ ./prisma/
RUN prisma generate

# Download the AI Model now to save time later
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# --- Stage 2: Runner (Rahti Production) ---
FROM python:3.12-slim

WORKDIR /app

# Install runtime libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    libatomic1 \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual env from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# --- FIX: Move Prisma Binaries to /app ---
# 1. Create the directory
RUN mkdir -p /app/.cache/prisma-python

# 2. Copy from the forbidden /root to the friendly /app
COPY --from=builder /root/.cache/prisma-python /app/.cache/prisma-python

# 3. Tell Prisma where to look for them
ENV PRISMA_CACHE_DIR="/app/.cache/prisma-python"

# --- Fix: Move AI Models to /app ---
COPY --from=builder /root/.cache/huggingface /app/.cache/huggingface

# Copy application code
COPY . .

# --- RAHTI PERMISSIONS FIX ---
# Give the "root group" (GID 0) ownership of the app folder.
# Rahti's random user always belongs to GID 0.
RUN chgrp -R 0 /app && \
    chmod -R g+rwX /app

# Environment variables for AI models
ENV TRANSFORMERS_CACHE=/app/.cache/huggingface
ENV TORCH_HOME=/app/.cache/torch
ENV HF_HOME=/app/.cache/huggingface
ENV MPLCONFIGDIR=/app/.cache/matplotlib

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]