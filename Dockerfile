# --- Stage 1: Builder ---
FROM python:3.12-slim as builder

WORKDIR /app

# Install system dependencies needed for building packages
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
# We do this in the builder so the artifacts are ready
COPY prisma/ ./prisma/
RUN prisma generate

# --- PRE-DOWNLOAD AI MODEL ---
# We download the model now so it is saved inside the Docker image.
# This prevents the app from trying to download 1GB+ at runtime (which might fail or be slow).
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"


# --- Stage 2: Runner (Rahti Production) ---
FROM python:3.12-slim

WORKDIR /app

# Install runtime libs (libatomic1 is often needed for Prisma/Node binaries on Slim)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libatomic1 \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual env from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy the downloaded AI model cache from builder
# HuggingFace saves models to /root/.cache by default. We move them to /app/.cache
# so the non-root user can read them.
COPY --from=builder /root/.cache /app/.cache

# Copy application code
COPY . .

# --- RAHTI SECURITY CONFIGURATION (CRITICAL) ---
# OpenShift (Rahti) runs containers as a random user ID.
# That random user is always part of the "root" group (GID 0).
# We must allow the GID 0 to write to the app directory (for cache, logs, etc.)
RUN chgrp -R 0 /app && \
    chmod -R g+rwX /app

# Set environment variables to point caches to our writable /app directory
ENV TRANSFORMERS_CACHE=/app/.cache/huggingface
ENV TORCH_HOME=/app/.cache/torch
ENV HF_HOME=/app/.cache/huggingface
ENV MPLCONFIGDIR=/app/.cache/matplotlib

# Expose the port
EXPOSE 8080

# Run the application
# We use port 8080 because Rahti/OpenShift sometimes restricts low ports like 80.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]