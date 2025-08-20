# Stage 1: Builder
# This stage installs the dependencies into a virtual environment.
FROM python:3.12 as builder

# Set the working directory in the container
WORKDIR /app

# Create and activate a virtual environment
# This isolates the application's dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy the requirements file into the container
COPY requirements.txt .

# Install system build dependencies needed for packages like pandas
RUN apt-get update && apt-get install -y build-essential

# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the prisma schema file
COPY prisma/schema.prisma ./prisma/

# 1. Fetch the correct binary query engine for Linux
RUN prisma py fetch

# 2. Generate the Python client code
RUN prisma generate

# Stage 2: Runner
# This stage copies the application code and the virtual environment
# from the builder stage to create a lean final image.
FROM python:3.12-slim

WORKDIR /app

# Copy the virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy the downloaded Prisma binaries from the builder stage
COPY --from=builder /root/.cache/prisma-python /root/.cache/prisma-python

# Copy the application code into the container
# The .dockerignore file will be used to exclude unnecessary files
COPY . .

# Activate the virtual environment
ENV PATH="/opt/venv/bin:$PATH"

# Expose the port the app will run on
EXPOSE 8000

# Command to run the Uvicorn server
# Replace `main:app` with your application's entry point if it's different.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]