FROM python:3.12-slim
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends unrar-free tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime
COPY pyproject.toml README.md ./
COPY galleryvault ./galleryvault
COPY alembic.ini ./
COPY alembic ./alembic
RUN pip install --no-cache-dir .
EXPOSE 8001
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn galleryvault.app.main:app --host 0.0.0.0 --port 8001"]