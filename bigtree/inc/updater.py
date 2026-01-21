import json
import os
import sys
import time
import shutil
import tarfile
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any

import requests

import bigtree.inc.logging as loch


@dataclass
class UpdaterConfig:
    """Configuration for the self-updater.

    This updater is designed for containers where the application directory
    (e.g. /opt/thebigtree) may NOT be writable by the runtime user.

    Strategy:
    - Determine latest commit on a tracked branch.
    - If newer than the persisted state, download a tarball for that commit.
    - Stage extracted source under a writable updates directory (default: /data/.bigtree_updates/<sha>).
    - (Best effort) install requirements using `uv pip install --system`.
    - Persist state with `active_root` pointing to the staged directory.
    - Restart the process so the launcher can exec into the new codebase.
    """

    enabled: bool = False
    repo: str = "dorbian/thebigtree"                 # GitHub org/repo
    branch: str = "main"                            # Branch to follow
    check_interval_seconds: int = 300                # How often to check
    state_path: str = "/data/.bigtree_updater.json"  # Persisted state (on volume)
    updates_dir: str = "/data/.bigtree_updates"      # Where new source trees are staged
    keep_versions: int = 3                           # Prune older versions
    restart_mode: str = "exit"                       # "exit" or "exec"


class SelfUpdater:
    def __init__(self, cfg: UpdaterConfig, bundled_root: Path):
        self.cfg = cfg
        self.bundled_root = bundled_root  # immutable/bundled source (e.g. /opt/thebigtree)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if not self.cfg.enabled:
            return
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="SelfUpdater", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        time.sleep(2)
        while not self._stop.is_set():
            try:
                self.check_and_update_once()
            except Exception as e:
                loch.logger.error("[updater] update check failed: %s", e)

            remaining = max(10, int(self.cfg.check_interval_seconds))
            while remaining > 0 and not self._stop.is_set():
                step = min(10, remaining)
                time.sleep(step)
                remaining -= step

    def check_and_update_once(self) -> None:
        state = self._load_state()
        current_commit = str(state.get("current_commit") or "unknown")

        latest_commit = self._get_latest_commit_sha()
        if not latest_commit:
            loch.logger.warning("[updater] unable to determine latest commit; skipping")
            return

        # First-run: if we don’t know what commit we’re running, pin state to latest,
        # but keep running bundled code until a *newer* commit appears.
        if current_commit in ("", "unknown", "none"):
            state["current_commit"] = latest_commit
            state["repo"] = self.cfg.repo
            state["branch"] = self.cfg.branch
            state["last_checked_at"] = int(time.time())
            self._save_state(state)
            loch.logger.info("[updater] state initialized at commit %s", latest_commit)
            return

        if latest_commit == current_commit:
            state["last_checked_at"] = int(time.time())
            self._save_state(state)
            return

        loch.logger.info("[updater] update available: %s -> %s", current_commit, latest_commit)
        self._perform_update(latest_commit, state)

    # ----------------------------
    # Update flow
    # ----------------------------

    def _perform_update(self, commit_sha: str, state: Dict[str, Any]) -> None:
        updates_root = Path(self.cfg.updates_dir)
        updates_root.mkdir(parents=True, exist_ok=True)

        target_dir = updates_root / commit_sha
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)

        # 1) Download source tarball and extract to staging
        stage_root = self._download_repo_tarball(commit_sha)

        # 2) Move staged tree to persistent updates dir
        shutil.copytree(stage_root, target_dir, dirs_exist_ok=True)

        # 3) Install dependencies (best-effort)
        self._install_requirements(target_dir)

        # 4) Persist state + activate
        state["current_commit"] = commit_sha
        state["repo"] = self.cfg.repo
        state["branch"] = self.cfg.branch
        state["active_root"] = str(target_dir)
        state["updated_at"] = int(time.time())
        self._save_state(state)

        # 5) Cleanup older versions
        self._prune_old_versions(updates_root, keep=int(self.cfg.keep_versions))

        # 6) Restart
        self._restart_into_new_code()

    # ----------------------------
    # GitHub I/O
    # ----------------------------

    def _get_latest_commit_sha(self) -> Optional[str]:
        url = f"https://api.github.com/repos/{self.cfg.repo}/commits/{self.cfg.branch}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "thebigtree-self-updater",
        }
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                loch.logger.warning("[updater] GitHub API returned %s for commit lookup", resp.status_code)
                return None
            data = resp.json()
            sha = data.get("sha")
            return str(sha) if sha else None
        except Exception as e:
            loch.logger.error("[updater] GitHub commit lookup error: %s", e)
            return None

    def _download_repo_tarball(self, commit_sha: str) -> Path:
        """Downloads a tarball for the given commit and returns extracted repo root path."""
        url = f"https://codeload.github.com/{self.cfg.repo}/tar.gz/{commit_sha}"
        headers = {"User-Agent": "thebigtree-self-updater"}

        td = Path(tempfile.mkdtemp(prefix=f"bigtree_update_{commit_sha[:12]}_"))
        tar_path = td / "src.tar.gz"
        extract_dir = td / "extract"
        extract_dir.mkdir(parents=True, exist_ok=True)

        loch.logger.info("[updater] downloading source tarball %s", commit_sha[:12])
        with requests.get(url, headers=headers, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(tar_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)

        with tarfile.open(tar_path, "r:gz") as tar:
            tar.extractall(path=extract_dir)

        subdirs = [p for p in extract_dir.iterdir() if p.is_dir()]
        if not subdirs:
            raise RuntimeError("downloaded tarball contained no directory")

        # Return the extracted top-level repo folder
        return subdirs[0]

    # ----------------------------
    # Dependency install
    # ----------------------------

    def _install_requirements(self, new_root: Path) -> None:
        req = new_root / "requirements.txt"
        if not req.exists():
            loch.logger.info("[updater] no requirements.txt found in update; skipping dependency install")
            return

        uv = shutil.which("uv")
        if not uv:
            loch.logger.warning("[updater] uv not found; skipping dependency install")
            return

        loch.logger.info("[updater] installing updated requirements...")
        import subprocess

        try:
            subprocess.run(
                [uv, "pip", "install", "--system", "--no-cache", "-r", str(req)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            out = e.stdout or ""
            loch.logger.warning("[updater] requirements install failed; continuing anyway. Output:\n%s", out)

    # ----------------------------
    # Housekeeping
    # ----------------------------

    def _prune_old_versions(self, updates_root: Path, keep: int) -> None:
        try:
            keep = max(1, int(keep))
        except Exception:
            keep = 3

        try:
            dirs = [p for p in updates_root.iterdir() if p.is_dir()]
            # commit SHAs are not sortable by time; use mtime
            dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            for p in dirs[keep:]:
                shutil.rmtree(p, ignore_errors=True)
        except Exception:
            pass

    # ----------------------------
    # State
    # ----------------------------

    def _load_state(self) -> Dict[str, Any]:
        p = Path(self.cfg.state_path)
        try:
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass

        return {
            "repo": self.cfg.repo,
            "branch": self.cfg.branch,
            "current_commit": "unknown",
            # active_root intentionally absent -> launcher keeps bundled code
        }

    def _save_state(self, state: Dict[str, Any]) -> None:
        p = Path(self.cfg.state_path)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        except Exception as e:
            loch.logger.error("[updater] failed to write state file %s: %s", p, e)

    # ----------------------------
    # Restart
    # ----------------------------

    def _restart_into_new_code(self) -> None:
        mode = (self.cfg.restart_mode or "exit").strip().lower()

        if mode != "exec":
            loch.logger.info("[updater] update applied; exiting so container can restart")
            os._exit(75)

        try:
            # Exec into bundled launcher (it will select active_root)
            target = str(self.bundled_root / "bigtree_runner.py")
            argv = [sys.executable, target] + sys.argv[1:]
            loch.logger.info("[updater] update applied; exec into launcher")
            os.execv(sys.executable, argv)
        except Exception as e:
            loch.logger.error("[updater] exec restart failed: %s; exiting", e)
            os._exit(75)


_updater_singleton: Optional[SelfUpdater] = None


def start_self_updater(settings: Any) -> None:
    """Starts the updater loop if enabled in settings."""
    global _updater_singleton

    try:
        enabled = bool(settings.get("UPDATER.enabled", False))
        repo = settings.get("UPDATER.repo", "dorbian/thebigtree")
        branch = settings.get("UPDATER.branch", "main")
        interval = settings.get("UPDATER.check_interval_seconds", 300, int)
        state_path = settings.get("UPDATER.state_path", "/data/.bigtree_updater.json")
        updates_dir = settings.get("UPDATER.updates_dir", "/data/.bigtree_updates")
        keep_versions = settings.get("UPDATER.keep_versions", 3, int)
        restart_mode = settings.get("UPDATER.restart_mode", "exit")

        cfg = UpdaterConfig(
            enabled=enabled,
            repo=str(repo),
            branch=str(branch),
            check_interval_seconds=int(interval),
            state_path=str(state_path),
            updates_dir=str(updates_dir),
            keep_versions=int(keep_versions),
            restart_mode=str(restart_mode),
        )

        if not cfg.enabled:
            return

        bundled_root = Path(__file__).resolve().parents[2]

        if _updater_singleton is None:
            _updater_singleton = SelfUpdater(cfg, bundled_root)
            _updater_singleton.start()
            loch.logger.info(
                "[updater] enabled: repo=%s branch=%s interval=%ss updates_dir=%s keep=%s restart=%s",
                cfg.repo,
                cfg.branch,
                cfg.check_interval_seconds,
                cfg.updates_dir,
                cfg.keep_versions,
                cfg.restart_mode,
            )

    except Exception as e:
        loch.logger.error("[updater] failed to start: %s", e)
