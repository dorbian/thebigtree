# syntax=docker/dockerfile:1.6
# TheBigTree container using uv for dependency installation

FROM python:3.11-slim-bookworm

# System deps (Pillow build + tools for uv install)
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl \
      ca-certificates \
      git \
      build-essential \
      zlib1g-dev \
      libjpeg62-turbo-dev \
      libpng-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv (Astral's fast Python package/venv manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && ln -s /root/.local/bin/uv /usr/local/bin/uv

WORKDIR /opt/thebigtree

# Copy dependency spec first to maximize layer cache
COPY requirements.txt .

# Install deps into the system Python environment using uv
# (so we can keep CMD as `python thebigtree.py`)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system --no-cache -r requirements.txt

# Now copy the actual application code
COPY . .

# Runtime user + data
RUN useradd -m -u 1000 bigtree \
    && mkdir -p /data/contest \
    && chown -R bigtree:bigtree /opt/thebigtree /data

USER bigtree

ENV PYTHONUNBUFFERED=1 \
    BIGTREE__BOT__contest_dir=/data/contest \
    BIGTREE__BOT__DATA_DIR=/data \
    BIGTREE__WEB__listen_host=0.0.0.0 \
    BIGTREE__WEB__listen_port=8443

VOLUME ["/data"]

EXPOSE 8443

CMD ["python", "thebigtree.py"]
