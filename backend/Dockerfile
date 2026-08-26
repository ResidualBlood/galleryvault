FROM python:3.12-slim
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends unrar-free tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime
# Run the server as an unprivileged user (see entrypoint.sh, which chowns the
# writable mount roots and drops privileges before starting uvicorn).
RUN useradd --uid 10001 --create-home app
# Dependencies first: this layer is cached unless requirements.txt changes,
# so code-only edits rebuild in seconds instead of re-installing everything.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY pyproject.toml README.md ./
COPY galleryvault ./galleryvault
COPY alembic.ini ./
COPY alembic ./alembic
COPY entrypoint.sh /app/entrypoint.sh
RUN pip install --no-cache-dir --no-deps . && chmod +x /app/entrypoint.sh
EXPOSE 8001
ENTRYPOINT ["/app/entrypoint.sh"]