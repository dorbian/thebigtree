import bigtree
import logging
import logging.handlers
import os

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

logger = logging.getLogger('discord.bigtree')
logger.setLevel(logging.DEBUG)
logging.getLogger('discord.http').setLevel(logging.INFO)

log_path = _resolve_log_path()
log_dir = os.path.dirname(log_path)
if log_dir:
    os.makedirs(log_dir, exist_ok=True)

handler = logging.handlers.RotatingFileHandler(
    filename=log_path,
    encoding='utf-8',
    maxBytes=32 * 1024 * 1024,  # 32 MiB
    backupCount=5,  # Rotate through 5 files
)

dt_fmt = '%Y-%m-%d %H:%M:%S'
formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {name}: {message}', dt_fmt, style='{')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Assume client refers to a discord.Client subclass...
# Suppress the default configuration since we have our own
