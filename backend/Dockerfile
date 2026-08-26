# Multi-arch build: python:3.12-slim ships images for amd64, arm64, arm/v7,
# ppc64le, s390x and riscv64, but a few compiled dependencies (asyncpg, uvloop,
# httptools, Pillow, …) only publish wheels for amd64/arm64. The builder stage
# compiles those missing wheels from sdist (a C toolchain + Pillow's image
# library headers, plus a modern Rust for cryptography on s390x/riscv64); the
# runtime stage only installs the resulting wheels, so it stays slim and has no
# compilers in the final image.
FROM python:3.12-slim AS builder
WORKDIR /wheels
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        python3-dev \
        pkg-config \
        curl \
        zlib1g-dev \
        libjpeg62-turbo-dev \
        libwebp-dev \
        libtiff-dev \
        liblcms2-dev \
        libfreetype6-dev \
        libopenjp2-7-dev \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*
# cryptography >= 50 builds from sdist with maturin and needs a recent rustc;
# Debian bookworm's packaged rustc (1.63) is too old, so use rustup (which has
# prebuilt binaries for every architecture we target). The toolchain is only
# exercised on s390x/riscv64, where cryptography has no wheels.
ENV RUSTUP_HOME=/opt/rustup CARGO_HOME=/opt/cargo \
    PATH=/opt/cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
        | sh -s -- -y --profile minimal --default-toolchain stable --no-modify-path \
    && rm -rf /opt/rustup/tmp /opt/cargo/registry
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends unrar-free tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime
# Run the server as an unprivileged user (see entrypoint.sh, which chowns the
# writable mount roots and drops privileges before starting uvicorn).
RUN useradd --uid 10001 --create-home app
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl \
    && rm -rf /wheels
COPY pyproject.toml README.md ./
COPY galleryvault ./galleryvault
COPY alembic.ini ./
COPY alembic ./alembic
COPY entrypoint.sh /app/entrypoint.sh
RUN pip install --no-cache-dir --no-deps . && chmod +x /app/entrypoint.sh
EXPOSE 8001
ENTRYPOINT ["/app/entrypoint.sh"]
