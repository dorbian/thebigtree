#!/usr/bin/env python3
"""Create reproducible pre-compressed static assets for the runtime image.

BigTree runs on a Raspberry Pi and sits behind Traefik.  Compressing the large
JavaScript/CSS bundles once while the container image is built is much cheaper
than spending Pi CPU compressing the same bytes for every cold browser cache.
The web server transparently falls back to the original file when a client does
not advertise gzip support or when this build helper has not been run.
"""
from __future__ import annotations

import gzip
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "bigtree" / "web" / "static"
COMPRESSIBLE = {".css", ".js", ".json", ".svg", ".txt", ".md"}
MIN_BYTES = 1024
MAX_RATIO = 0.95


def precompress(root: Path = ROOT) -> tuple[int, int, int]:
    written = 0
    original_bytes = 0
    compressed_bytes = 0
    if not root.exists():
        return written, original_bytes, compressed_bytes

    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in COMPRESSIBLE:
            continue
        data = path.read_bytes()
        if len(data) < MIN_BYTES:
            continue
        packed = gzip.compress(data, compresslevel=9, mtime=0)
        target = path.with_name(path.name + ".gz")
        if len(packed) >= int(len(data) * MAX_RATIO):
            target.unlink(missing_ok=True)
            continue
        target.write_bytes(packed)
        written += 1
        original_bytes += len(data)
        compressed_bytes += len(packed)
    return written, original_bytes, compressed_bytes


def main() -> int:
    count, before, after = precompress()
    saving = 0.0 if before <= 0 else (1.0 - (after / before)) * 100.0
    print(f"precompressed {count} static assets: {before} -> {after} bytes ({saving:.1f}% smaller)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
