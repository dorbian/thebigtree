# Containerfile for TheBigTree Discord bot + webserver
# Build with:
#   podman build -t thebigtree:latest -f Containerfile .
#
# This image expects:
#   - DISCORD_TOKEN environment variable set
#   - BIGTREE__BOT__guildid set to your Discord guild/server ID
#
# Optional env overrides (see README-podman.md for more):
#   - BIGTREE__BOT__contest_dir
#   - BIGTREE__WEB__listen_host
#   - BIGTREE__WEB__listen_port
#   - OPENAI_API_KEY, BIGTREE__openai__openai_model, etc.

FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      git \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /opt/thebigtree

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the TheBigTree source into the image.
# When building, run the build command from the root of your
# thebigtree git clone so that thebigtree.py and the bigtree/
# package are in this context.
COPY . .

# Runtime user + data directory
RUN useradd -m -u 1000 bigtree \
    && mkdir -p /data/contest \
    && chown -R bigtree:bigtree /opt/thebigtree /data
USER bigtree

# Default runtime configuration (can be overridden with env)
ENV PYTHONUNBUFFERED=1 \
    BIGTREE__BOT__contest_dir=/data/contest \
    BIGTREE__WEB__listen_host=0.0.0.0 \
    BIGTREE__WEB__listen_port=8443

VOLUME ["/data"]

EXPOSE 8443

# Start the Discord bot + webserver
#
# thebigtree.py wraps bigtree.initialize() which starts the bot and
# attaches the aiohttp webserver through the existing hooks.
CMD ["python", "thebigtree.py"]
