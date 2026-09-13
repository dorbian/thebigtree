# syntax=docker/dockerfile:1.6
# TheBigTree container. Dependencies are built in a throw-away stage so the
# Raspberry Pi runtime image does not carry compilers, headers, git or uv.

FROM python:3.11-slim-bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl \
      ca-certificates \
      build-essential \
      libpq-dev \
      zlib1g-dev \
      libjpeg62-turbo-dev \
      libpng-dev \
      libwebp-dev \
    && rm -rf /var/lib/apt/lists/*

# Keep uv's faster dependency resolver/install path, but only in the builder.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && ln -s /root/.local/bin/uv /usr/local/bin/uv

WORKDIR /build
COPY requirements.txt .
RUN python -m venv /opt/venv
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python /opt/venv/bin/python --no-cache -r requirements.txt


FROM python:3.11-slim-bookworm AS runtime

ARG BIGTREE_BUILD_SHA=unknown

# Runtime libraries cover the source-build fallback on arm/v7 as well as the
# normal manylinux wheels. In particular, WebP support is required by the
# media thumbnail/preview pipeline.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      libpq5 \
      zlib1g \
      libjpeg62-turbo \
      libpng16-16 \
      libwebp7 \
    && rm -rf /var/lib/apt/lists/*

ENV PATH=/opt/venv/bin:$PATH \
    BIGTREE_BUILD_SHA=$BIGTREE_BUILD_SHA \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BIGTREE__BOT__contest_dir=/data/contest \
    BIGTREE__BOT__DATA_DIR=/data \
    BIGTREE__WEB__listen_host=0.0.0.0 \
    BIGTREE__WEB__listen_port=8443 \
    BIGTREE_LOG_MODE=console \
    BIGTREE__DATABASE__pool_min=1 \
    BIGTREE__DATABASE__pool_max=4 \
    BIGTREE__UPDATER__enabled=0 \
    BIGTREE__UPDATER__repo=dorbian/thebigtree \
    BIGTREE__UPDATER__branch=main \
    BIGTREE__UPDATER__check_interval_seconds=300 \
    BIGTREE__UPDATER__restart_mode=exit

WORKDIR /opt/thebigtree
COPY --from=builder /opt/venv /opt/venv
COPY . .

# Compress cacheable web assets once during the image build. The runtime
# server serves these sidecars only when a browser advertises gzip support.
RUN python tools/precompress_static.py

RUN useradd -m -u 1000 bigtree \
    && mkdir -p /data/contest \
    && chown -R bigtree:bigtree /opt/thebigtree /data

USER bigtree
VOLUME ["/data"]
EXPOSE 8443

# Keep curl out of the runtime image; Python itself is enough for liveness.
# /readyz additionally checks Discord + PostgreSQL and can be used by Traefik
# or deployment automation before sending user traffic.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8443/healthz', timeout=3).read()" || exit 1

STOPSIGNAL SIGTERM
CMD ["python", "thebigtree.py"]
