# hutwatch container image.
# Includes Playwright's Chromium + system deps so either fetch.engine value
# ("httpx" or "playwright") works out of the box from config.toml.

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY README.md ./

RUN uv sync --no-dev

RUN uv run playwright install --with-deps chromium

# Mount a real config.toml and .env at runtime, e.g.:
#   docker run --env-file .env -v $(pwd)/config.toml:/app/config.toml:ro \
#     -v hutwatch-data:/app/data hutwatch
# Point state.db_path in config.toml at /app/data/hutwatch.sqlite3 for
# persistence across container restarts.
VOLUME ["/app/data"]

ENTRYPOINT ["uv", "run", "hutwatch"]
CMD []
