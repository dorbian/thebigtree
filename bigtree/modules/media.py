from __future__ import annotations
import os
import time
import threading
from io import BytesIO
from typing import Dict, List, Optional
from tinydb import TinyDB, Query

try:
    import bigtree
except Exception:
    bigtree = None

try:
    from bigtree.inc.logging import logger
except Exception:
    import logging
    logger = logging.getLogger("bigtree")

_MEDIA_DB_PATH: Optional[str] = None
_IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
_MAX_IMAGE_PIXELS = 48_000_000


def _now() -> float:
    return time.time()

def _get_base_dir() -> str:
    base = None
    try:
        if getattr(bigtree, "settings", None):
            base = bigtree.settings.get("BOT.DATA_DIR", None)
    except Exception:
        base = None
    if not base:
        base = os.getenv("BIGTREE__BOT__DATA_DIR") or os.getenv("BIGTREE_DATA_DIR")
    if not base:
        base = os.getenv("BIGTREE_WORKDIR") or os.path.join(os.getcwd(), ".bigtree")
    return base

def get_media_dir() -> str:
    base = _get_base_dir()
    path = os.path.join(base, "media")
    os.makedirs(path, exist_ok=True)
    return path

def get_media_thumbs_dir() -> str:
    base = get_media_dir()
    path = os.path.join(base, "thumbs")
    os.makedirs(path, exist_ok=True)
    return path

def get_media_thumb_path(filename: str) -> str:
    safe = os.path.basename(filename or "")
    return os.path.join(get_media_thumbs_dir(), f"{safe}.thumb.webp")

def get_media_previews_dir() -> str:
    base = get_media_dir()
    path = os.path.join(base, "previews")
    os.makedirs(path, exist_ok=True)
    return path

def get_media_preview_path(filename: str) -> str:
    safe = os.path.basename(filename or "")
    return os.path.join(get_media_previews_dir(), f"{safe}.preview.webp")

def _derivative_current(target_path: str, source_path: str) -> bool:
    try:
        return os.path.exists(target_path) and os.path.getmtime(target_path) >= os.path.getmtime(source_path)
    except OSError:
        return False


def _derivative_tmp_path(target_path: str) -> str:
    return f"{target_path}.{os.getpid()}.{threading.get_ident()}.tmp"


def validate_image_bytes(data: bytes) -> tuple[bool, str]:
    """Validate an uploaded image without fully decoding it on the event loop.

    A 32 MB compressed upload can expand into hundreds of MB of pixels.  The
    Pi has much less spare memory than a desktop host, so reject implausibly
    large raster dimensions before creating derivatives.
    """
    if not data:
        return False, "empty image"
    try:
        from PIL import Image
        with Image.open(BytesIO(data)) as img:
            width, height = img.size
            if width <= 0 or height <= 0:
                return False, "invalid image dimensions"
            if width * height > _MAX_IMAGE_PIXELS:
                return False, f"image dimensions are too large ({width}x{height})"
            if (img.format or "").upper() not in {"JPEG", "PNG", "GIF", "BMP", "WEBP"}:
                return False, "unsupported image format"
            img.verify()
    except Exception:
        return False, "invalid or damaged image"
    return True, ""


def _ensure_derivative(filename: str, target_path: str, size: tuple[int, int], *, quality: int) -> bool:
    if not filename:
        return False
    filename = os.path.basename(filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _IMG_EXTS:
        return False
    source = os.path.join(get_media_dir(), filename)
    if not os.path.exists(source):
        return False
    if _derivative_current(target_path, source):
        return True
    try:
        from PIL import Image, ImageOps
    except Exception:
        return False
    try:
        with Image.open(source) as img:
            try:
                img.seek(0)
            except Exception:
                pass
            img = ImageOps.exif_transpose(img)
            img.thumbnail(size, Image.Resampling.LANCZOS)
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA" if "transparency" in img.info else "RGB")
            tmp_path = _derivative_tmp_path(target_path)
            img.save(tmp_path, "WEBP", quality=quality, method=4)
            os.replace(tmp_path, target_path)
    except Exception:
        try:
            if 'tmp_path' in locals() and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        return False
    return True

def ensure_thumb(filename: str, size: tuple[int, int] = (480, 672)) -> bool:
    """Create the inexpensive media-grid derivative."""
    return _ensure_derivative(filename, get_media_thumb_path(filename), size, quality=76)

def ensure_preview(filename: str, size: tuple[int, int] = (1600, 1200)) -> bool:
    """Create a screen-sized derivative for modals and full-page backgrounds.

    Originals stay untouched for download/open actions. This keeps uploaded 4K
    artwork from becoming the default transfer for every UI view.
    """
    return _ensure_derivative(filename, get_media_preview_path(filename), size, quality=82)


def ensure_derivatives(filename: str) -> tuple[bool, bool]:
    """Generate the grid thumbnail and screen preview from one source decode.

    Upload is the best time to pay this CPU cost.  Decoding once also avoids
    competing Pillow workers on the Raspberry Pi for the same source image.
    """
    if not filename:
        return False, False
    filename = os.path.basename(filename)
    source = os.path.join(get_media_dir(), filename)
    thumb_path = get_media_thumb_path(filename)
    preview_path = get_media_preview_path(filename)
    thumb_ok = _derivative_current(thumb_path, source)
    preview_ok = _derivative_current(preview_path, source)
    if thumb_ok and preview_ok:
        return True, True
    try:
        from PIL import Image, ImageOps
        with Image.open(source) as original:
            try:
                original.seek(0)
            except Exception:
                pass
            original = ImageOps.exif_transpose(original)
            def write(target: str, size: tuple[int, int], quality: int) -> bool:
                tmp = _derivative_tmp_path(target)
                try:
                    img = original.copy()
                    img.thumbnail(size, Image.Resampling.LANCZOS)
                    if img.mode not in ("RGB", "RGBA"):
                        img = img.convert("RGBA" if "transparency" in img.info else "RGB")
                    img.save(tmp, "WEBP", quality=quality, method=4)
                    os.replace(tmp, target)
                    return True
                except Exception:
                    try:
                        if os.path.exists(tmp):
                            os.remove(tmp)
                    except Exception:
                        pass
                    return False
            if not thumb_ok:
                thumb_ok = write(thumb_path, (480, 672), 76)
            if not preview_ok:
                preview_ok = write(preview_path, (1600, 1200), 82)
    except Exception:
        return thumb_ok, preview_ok
    return thumb_ok, preview_ok


def delete_derivatives(filename: str) -> None:
    for path in (get_media_thumb_path(filename), get_media_preview_path(filename)):
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            logger.warning("[media] unable to remove derivative %s", path)

def _get_db_path() -> str:
    global _MEDIA_DB_PATH
    if _MEDIA_DB_PATH:
        return _MEDIA_DB_PATH
    _MEDIA_DB_PATH = os.path.join(get_media_dir(), "media.json")
    return _MEDIA_DB_PATH

def _db() -> TinyDB:
    return TinyDB(_get_db_path())

def list_media() -> List[Dict]:
    db = _db(); q = Query()
    rows = db.search(q._type == "media")
    rows.sort(key=lambda r: float(r.get("created_at") or 0), reverse=True)
    return rows

def get_media(filename: str) -> Optional[Dict]:
    if not filename:
        return None
    db = _db(); q = Query()
    return db.get((q._type == "media") & (q.filename == filename))

def get_media_by_discord_url(url: str) -> Optional[Dict]:
    if not url:
        return None
    db = _db(); q = Query()
    return db.get((q._type == "media") & (q.discord_url == url))

def add_media(
    filename: str,
    original_name: Optional[str] = None,
    artist_id: Optional[str] = None,
    title: Optional[str] = None,
    discord_url: Optional[str] = None,
    origin_type: Optional[str] = None,
    origin_label: Optional[str] = None,
) -> Dict:
    db = _db(); q = Query()
    payload = {
        "_type": "media",
        "filename": filename,
        "original_name": original_name or "",
        "artist_id": artist_id or None,
        "title": title or "",
        "discord_url": discord_url or "",
        "origin_type": origin_type or "",
        "origin_label": origin_label or "",
        "created_at": _now(),
    }
    existing = get_media(filename)
    if existing:
        existing.update({
            "original_name": payload["original_name"] or existing.get("original_name", ""),
            "artist_id": payload["artist_id"],
            "title": payload["title"] or existing.get("title", ""),
            "discord_url": payload["discord_url"] or existing.get("discord_url", ""),
            "origin_type": payload["origin_type"] or existing.get("origin_type", ""),
            "origin_label": payload["origin_label"] or existing.get("origin_label", ""),
        })
        db.update(existing, (q._type == "media") & (q.filename == filename))
        return existing
    db.insert(payload)
    return payload

def delete_media(filename: str) -> bool:
    if not filename:
        return False
    db = _db(); q = Query()
    removed = db.remove((q._type == "media") & (q.filename == filename))
    return bool(removed)
