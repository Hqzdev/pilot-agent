# ---- builder ----
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY devagent/ devagent/
RUN touch README.md
RUN uv sync --frozen --no-dev

# ---- runtime ----
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates nodejs npm \
    && npm i -g vercel \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -m agent
USER agent
WORKDIR /workspace
COPY --from=builder --chown=agent /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    DEVAGENT_HOME=/home/agent/.devagent
ENTRYPOINT ["devagent"]
CMD ["run"]
