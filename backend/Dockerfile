FROM python:3.12-slim
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends unrar-free tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /usr/share/doc /usr/share/man /usr/share/locale \
    && ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime

# Base unprivileged user (can be mapped dynamically to PUID/PGID at runtime via entrypoint.sh)
RUN useradd --uid 10001 --create-home app

# Dependencies first: this layer is cached unless requirements.txt changes,
# so code-only edits rebuild in seconds instead of re-installing everything.
COPY requirements.txt ./
RUN --mount=from=ghcr.io/astral-sh/uv:latest,source=/uv,target=/bin/uv \
    uv pip install --system --no-cache -r requirements.txt

COPY pyproject.toml README.md ./
COPY galleryvault ./galleryvault
COPY alembic.ini ./
COPY alembic ./alembic
COPY entrypoint.sh /app/entrypoint.sh

# Slim the image: the stdlib ships idle/tk modules this app never uses, and
# __pycache__ can be dropped (Python regenerates/skips it at runtime).
RUN --mount=from=ghcr.io/astral-sh/uv:latest,source=/uv,target=/bin/uv \
    uv pip install --system --no-cache --no-deps . \
    && chmod +x /app/entrypoint.sh \
    && find /usr/local/lib/python3.12 -type d -name __pycache__ -prune -exec rm -rf {} + \
    && rm -rf /usr/local/lib/python3.12/idlelib \
              /usr/local/lib/python3.12/turtledemo \
              /usr/local/lib/python3.12/tkinter \
              /usr/local/lib/python3.12/test \
              /usr/local/lib/python3.12/lib2to3 \
    && find /usr/local/lib/python3.12/lib-dynload -name "_tkinter*" -delete \
    && rm -f /usr/local/bin/idle3 /usr/local/bin/idle3.12

EXPOSE 8001
ENTRYPOINT ["/app/entrypoint.sh"]
