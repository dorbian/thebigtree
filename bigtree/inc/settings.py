# bigtree/inc/settings.py
from __future__ import annotations
import os, json
from pathlib import Path
from configobj import ConfigObj  # keeps unknown keys, preserves case, nested sections
from typing import Any, Callable, Dict, Optional

CFG_PATH_DEFAULT = Path(os.getenv("HOME", "")) / ".config" / "bigtree.ini"

# --------- helpers ---------
def _coerce_bool(v: Any, default: bool=False) -> bool:
    if isinstance(v, bool): return v
    if v is None: return default
    s = str(v).strip().lower()
    return s in ("1", "true", "yes", "on")

def _coerce_int(v: Any, default: int=0) -> int:
    try: return int(str(v).strip())
    except Exception: return default

def _coerce_float(v: Any, default: float=0.0) -> float:
    try: return float(str(v).strip())
    except Exception: return default
def _parse_json(v, default=None):
    if v is None:
        return default
    # If ConfigObj already parsed it to list/dict, just return it
    if isinstance(v, (list, dict)):
        return v
    s = str(v).strip()
    if not s:
        return default
    try:
        return json.loads(s)
    except Exception:
        return default

def _clean_key_name(k: str) -> str:
    # remove zero-width/control chars and trim
    bad = {0x200B, 0x200C, 0x200D, 0xFEFF}
    out = []
    for ch in k:
        oc = ord(ch)
        if oc < 32 or oc == 127 or oc in bad:
            continue
        out.append(ch)
    return "".join(out).strip()

def _normalize_section_keys(sec: Dict[str, Any]):
    for k in list(sec.keys()):
        nk = _clean_key_name(k)
        if nk != k:
            sec[nk] = sec.pop(k)
        # normalize nested dicts too
        if isinstance(sec[nk], dict):
            _normalize_section_keys(sec[nk])

def _env_overrides(cfg: ConfigObj, prefix: str="BIGTREE__"):
    """
    Overlay env vars onto config without needing code for each new key.
    Patterns:
      BIGTREE__Section__Key=val         (string)
      BIGTREE_INT__Section__Key=123     (int)
      BIGTREE_BOOL__Section__Key=true   (bool)
      BIGTREE_JSON__Section__Key={...}  (json array/object or primitive)
      BIGTREE_FILE__Section__Key=/path  (contents of file, trimmed)
    """
    def set_val(sec: str, key: str, value: Any):
        cfg.setdefault(sec, {})
        cfg[sec][key] = value

    for name, val in os.environ.items():
        if not name.startswith(prefix) and not name.startswith("BIGTREE_INT__") and \
           not name.startswith("BIGTREE_BOOL__") and not name.startswith("BIGTREE_JSON__") and \
           not name.startswith("BIGTREE_FILE__"):
            continue

        kind = "STR"
        raw = name
        if name.startswith("BIGTREE_INT__"):
            kind, _, rest = "INT", None, name[len("BIGTREE_INT__"):]
        elif name.startswith("BIGTREE_BOOL__"):
            kind, _, rest = "BOOL", None, name[len("BIGTREE_BOOL__"):]
        elif name.startswith("BIGTREE_JSON__"):
            kind, _, rest = "JSON", None, name[len("BIGTREE_JSON__"):]
        elif name.startswith("BIGTREE_FILE__"):
            kind, _, rest = "FILE", None, name[len("BIGTREE_FILE__"):]
        else:
            rest = name[len(prefix):]

        parts = rest.split("__", 1)
        if len(parts) != 2:  # malformed
            continue
        sec, key = parts[0], parts[1]
        sec = sec.strip()
        key = key.strip()
        if not sec or not key:
            continue

        if kind == "INT":
            value = _coerce_int(val, 0)
        elif kind == "BOOL":
            value = _coerce_bool(val, False)
        elif kind == "JSON":
            value = _parse_json(val, None)
        elif kind == "FILE":
            try:
                with open(val, "r", encoding="utf-8") as f:
                    value = f.read().strip()
            except Exception:
                continue
        else:
            value = val

        set_val(sec, key, value)

class Settings:
    """
    Dynamic, schema-optional settings:
      - Read INI once (no write-backs)
      - Normalize key names (no invisible junk)
      - Overlay environment variables (patterns above)
      - Access new keys/sections without code
      - Helpers to parse types on-demand
      - Modules can self-validate required keys at runtime
    """
    def __init__(self, path: Path = CFG_PATH_DEFAULT):
        self.path = Path(path)
        if self.path.exists():
            self._cfg = ConfigObj(str(self.path), encoding="utf-8")
        else:
            self._cfg = ConfigObj(encoding="utf-8")

        # aggressively normalize keys across all sections
        for secname, sec in list(self._cfg.items()):
            if isinstance(sec, dict):
                nk = _clean_key_name(secname)
                if nk != secname:
                    self._cfg[nk] = self._cfg.pop(secname)
                    secname = nk
                _normalize_section_keys(self._cfg[secname])

        # apply env overlays
        _env_overrides(self._cfg)

    # -------- raw access (no code changes needed for new keys) --------
    def __getitem__(self, section: str) -> Dict[str, Any]:
        return self._cfg.get(section, {})

    def section(self, name: str) -> Dict[str, Any]:
        return self._cfg.get(name, {})

    # -------- dotted access with casting --------
    def get(self, dotted: str, default: Any=None, cast: Optional[Callable[[Any], Any]]=None) -> Any:
        """
        settings.get("Section.key", default, cast=int/bool/float/json or custom)
        """
        if "." not in dotted:
            return default
        sec, key = dotted.split(".", 1)
        secmap = self._cfg.get(sec, {})
        val = secmap.get(key, default)
        if cast is None:
            return val
        if cast is bool:
            return _coerce_bool(val, bool(default) if isinstance(default, bool) else False)
        if cast is int:
            return _coerce_int(val, int(default) if isinstance(default, int) else 0)
        if cast is float:
            return _coerce_float(val, float(default) if isinstance(default, float) else 0.0)
        if cast == "json":
            return _parse_json(val, default)
        try:
            return cast(val)
        except Exception:
            return default

    # -------- module-side assertions (no central edits) --------
    def require(self, section: str, *keys: str, allow_empty: bool=True):
        """
        Fail loud if section/keys missing. Modules call this themselves when they need it.
        """
        if section not in self._cfg:
            raise RuntimeError(f"Config error: missing [{section}] in {self.path}")
        sec = self._cfg[section]
        missing = []
        empties = []
        for k in keys:
            if k not in sec:
                missing.append(k)
            elif not allow_empty:
                v = sec.get(k)
                if v is None or (isinstance(v, str) and v.strip() == ""):
                    empties.append(k)
        if missing or empties:
            msg = [f"Config error in [{section}] ({self.path}):"]
            if missing:
                msg.append(f"  - missing keys: {', '.join(missing)}")
            if empties:
                msg.append(f"  - empty keys: {', '.join(empties)}")
            raise RuntimeError("\n".join(msg))

def load_settings(path: Path = CFG_PATH_DEFAULT) -> Settings:
    return Settings(path)
