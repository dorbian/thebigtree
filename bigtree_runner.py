"""BigTree launcher that supports self-updating.

The container image ships a bundled copy of BigTree under /opt/thebigtree
(read-only from the perspective of the runtime user).

When the self-updater downloads a newer revision, it stages it under the
writable /data volume (default: /data/.bigtree_updates/<commit>). The updater
then writes /data/.bigtree_updater.json with an `active_root` path.

This launcher reads that state and execs into the active codebase.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _load_active_root(state_path: Path) -> Path | None:
    try:
        if not state_path.exists():
            return None
        data = json.loads(state_path.read_text(encoding="utf-8"))
        active = data.get("active_root")
        if not active:
            return None
        p = Path(str(active))
        if (p / "thebigtree.py").exists():
            return p
    except Exception:
        return None
    return None


def main() -> None:
    bundled_root = Path(__file__).resolve().parent

    state_path = Path(os.getenv("BIGTREE_UPDATER_STATE", "/data/.bigtree_updater.json"))
    active_root = _load_active_root(state_path) or bundled_root

    target = active_root / "thebigtree.py"

    # Ensure we always run from the chosen root so relative paths resolve.
    os.chdir(str(active_root))

    argv = [sys.executable, str(target)] + sys.argv[1:]
    os.execv(sys.executable, argv)


if __name__ == "__main__":
    main()
