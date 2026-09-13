"""Logging configuration for BigTree.

The service normally runs in a container, so stdout/stderr is the primary log
transport.  Persistent rotating files remain available for installations that
want them, but use a handler that can recover from stale/invalid file
descriptors (for example after a network-backed /data mount is remounted).

Environment variables:
  BIGTREE_LOG_MODE=console|files|console+files   (default: console in containers; console+files otherwise)
  BIGTREE_LOG_PATH=/path/to/discord.log
  BIGTREE_UPLOAD_LOG_PATH=/path/to/upload.log
  BIGTREE_AUTH_LOG_PATH=/path/to/auth.log
  BIGTREE_LOG_MEMORY_LINES=2000
"""
from __future__ import annotations

from collections import deque
import errno
import logging
import logging.handlers
import os
import sys
import threading
from typing import Deque, Dict, Iterable, List, Optional

import bigtree


def _resolve_log_path() -> str:
    override = os.getenv("BIGTREE_LOG_PATH")
    if override:
        return override
    try:
        settings = getattr(bigtree, "settings", None)
        if settings:
            base = settings.get("BOT.DATA_DIR", None)
            if base:
                return os.path.join(base, "discord.log")
    except Exception:
        pass
    base = os.getenv("BIGTREE__BOT__DATA_DIR") or os.getenv("BIGTREE_DATA_DIR")
    if base:
        return os.path.join(base, "discord.log")
    return "discord.log"


def _resolve_sibling_log(base_path: str, env_name: str, filename: str) -> str:
    override = os.getenv(env_name)
    if override:
        return override
    base_dir = os.path.dirname(base_path)
    return os.path.join(base_dir, filename) if base_dir else filename


class ResilientRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """RotatingFileHandler that can reopen a stale/closed descriptor.

    Python's RotatingFileHandler seeks before every rollover check.  If a
    network-backed bind mount invalidates the underlying descriptor, that seek
    raises EBADF forever.  Reopening once makes logging self-healing without
    allowing logging failure to affect the bot.
    """

    def _reopen_stream(self) -> None:
        try:
            if self.stream is not None:
                self.stream.close()
        except Exception:
            pass
        self.stream = self._open()

    def shouldRollover(self, record: logging.LogRecord) -> bool:  # noqa: N802 (stdlib API)
        try:
            return super().shouldRollover(record)
        except OSError as exc:
            if exc.errno != errno.EBADF:
                raise
            self._reopen_stream()
            return super().shouldRollover(record)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            super().emit(record)
        except OSError as exc:
            # Most stdlib Handler.emit implementations consume exceptions via
            # handleError(), but keep this guard for errors raised by custom
            # streams/filesystems around the handler itself.
            if exc.errno != errno.EBADF:
                raise
            try:
                self._reopen_stream()
                super().emit(record)
            except Exception:
                self.handleError(record)


class MemoryTailHandler(logging.Handler):
    """Small thread-safe ring buffer used by the web admin log viewer."""

    def __init__(self, max_lines: int = 2000):
        super().__init__()
        self._items: Deque[str] = deque(maxlen=max(100, int(max_lines)))
        self._items_lock = threading.RLock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            rendered = self.format(record)
        except Exception:
            rendered = record.getMessage()
        with self._items_lock:
            self._items.append(rendered)

    def tail(self, lines: int = 200) -> List[str]:
        count = max(1, int(lines))
        with self._items_lock:
            items = list(self._items)
        return items[-count:]


_dt_fmt = "%Y-%m-%d %H:%M:%S"
formatter = logging.Formatter(
    "[{asctime}] [{levelname:<8}] {name}: {message}", _dt_fmt, style="{"
)

log_path = _resolve_log_path()
upload_log_path = _resolve_sibling_log(log_path, "BIGTREE_UPLOAD_LOG_PATH", "upload.log")
auth_log_path = _resolve_sibling_log(log_path, "BIGTREE_AUTH_LOG_PATH", "auth.log")

logger = logging.getLogger("discord.bigtree")
upload_logger = logging.getLogger("discord.bigtree.uploads")
auth_logger = logging.getLogger("discord.bigtree.auth")

logger.setLevel(logging.DEBUG)
upload_logger.setLevel(logging.DEBUG)
auth_logger.setLevel(logging.DEBUG)
logging.getLogger("discord.http").setLevel(logging.INFO)

_MEMORY_LINES = max(100, int(os.getenv("BIGTREE_LOG_MEMORY_LINES", "2000") or "2000"))
_memory_handlers: Dict[str, MemoryTailHandler] = {}
_managed_handlers: List[logging.Handler] = []
_config_lock = threading.RLock()
_configured = False


def _parse_mode() -> tuple[bool, bool]:
    # Containers already have a supervised log transport. Avoid needless /data
    # writes there unless persistent files are explicitly requested.
    in_container = os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv")
    default_mode = "console" if in_container else "console+files"
    raw = (os.getenv("BIGTREE_LOG_MODE") or default_mode).strip().lower()
    if raw in {"console", "stdout", "container"}:
        return True, False
    if raw in {"files", "file"}:
        return False, True
    return True, True


def _add_memory_handler(target: logging.Logger, key: str) -> None:
    handler = MemoryTailHandler(_MEMORY_LINES)
    handler.setFormatter(formatter)
    target.addHandler(handler)
    _memory_handlers[key] = handler
    _managed_handlers.append(handler)


def _add_file_handler(
    target: logging.Logger,
    path: str,
    *,
    max_bytes: int,
    backup_count: int,
) -> Optional[logging.Handler]:
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        handler = ResilientRotatingFileHandler(
            filename=path,
            encoding="utf-8",
            maxBytes=max_bytes,
            backupCount=backup_count,
            delay=True,
        )
        handler.setFormatter(formatter)
        target.addHandler(handler)
        _managed_handlers.append(handler)
        return handler
    except Exception as exc:
        # Never make a bot startup depend on a writable persistent log mount.
        print(f"[bigtree.logging] persistent log disabled for {path}: {exc}", file=sys.stderr)
        return None


def configure_logging(force: bool = False) -> None:
    """Configure BigTree-owned handlers exactly once.

    Discord.py configures its own loggers when Bot.run() starts.  BigTree owns
    only the discord.bigtree hierarchy here and avoids duplicate configuration
    if initialize() is invoked more than once in a test/reload process.
    """
    global _configured, handler, upload_handler, auth_handler
    global log_path, upload_log_path, auth_log_path
    with _config_lock:
        if _configured and not force:
            return
        if _configured:
            shutdown_logging()

        # Resolve paths again now that runtime settings may be loaded.
        log_path = _resolve_log_path()
        upload_log_path = _resolve_sibling_log(log_path, "BIGTREE_UPLOAD_LOG_PATH", "upload.log")
        auth_log_path = _resolve_sibling_log(log_path, "BIGTREE_AUTH_LOG_PATH", "auth.log")
        use_console, use_files = _parse_mode()

        # Child feature loggers intentionally propagate to the BigTree logger
        # so one console line is emitted and the combined in-memory tail sees it.
        logger.propagate = False
        upload_logger.propagate = True
        auth_logger.propagate = True

        if use_console:
            console = logging.StreamHandler(sys.stdout)
            console.setFormatter(formatter)
            logger.addHandler(console)
            _managed_handlers.append(console)

        _add_memory_handler(logger, "boot")
        _add_memory_handler(upload_logger, "upload")
        _add_memory_handler(auth_logger, "auth")

        handler = upload_handler = auth_handler = None
        if use_files:
            handler = _add_file_handler(
                logger, log_path, max_bytes=32 * 1024 * 1024, backup_count=5
            )
            upload_handler = _add_file_handler(
                upload_logger,
                upload_log_path,
                max_bytes=16 * 1024 * 1024,
                backup_count=3,
            )
            auth_handler = _add_file_handler(
                auth_logger,
                auth_log_path,
                max_bytes=8 * 1024 * 1024,
                backup_count=3,
            )
        _configured = True


def get_memory_log_tail(kind: str = "boot", lines: int = 200) -> List[str]:
    key = kind if kind in _memory_handlers else "boot"
    handler_obj = _memory_handlers.get(key)
    return handler_obj.tail(lines) if handler_obj else []


def shutdown_logging() -> None:
    global _configured
    with _config_lock:
        for target in (auth_logger, upload_logger, logger):
            for managed in list(_managed_handlers):
                try:
                    target.removeHandler(managed)
                except Exception:
                    pass
        for managed in list(_managed_handlers):
            try:
                managed.flush()
            except Exception:
                pass
            try:
                managed.close()
            except Exception:
                pass
        _managed_handlers.clear()
        _memory_handlers.clear()
        _configured = False


# Keep import-time compatibility for modules that log before initialize().
# initialize() calls configure_logging() again after settings are loaded only if
# no handler has been configured yet.
handler: Optional[logging.Handler] = None
upload_handler: Optional[logging.Handler] = None
auth_handler: Optional[logging.Handler] = None
configure_logging()
