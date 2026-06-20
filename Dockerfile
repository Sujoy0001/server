FROM python:3.11-slim

# Install system dependencies for build requirements
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /workspace

# Copy configuration files
COPY pyproject.toml ./

# Install dependencies using uv into the system site-packages for container simplicity
RUN uv pip install --system -r pyproject.toml

# Copy application source code
COPY app ./app

# Export PYTHONPATH to locate 'app' module
ENV PYTHONPATH=/workspace
