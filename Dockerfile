FROM python:3.14-slim

# Install uv.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency manifests and install packages first for better caching.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-cache

# Copy the application code.
COPY app ./app

# Run the application on the same port exposed by docker-compose.
CMD ["/app/.venv/bin/fastapi", "run", "app/main.py", "--host", "0.0.0.0", "--port", "8000"]