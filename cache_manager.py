"""Simple JSON-based title cache.

Each site gets one file: cache/<site_safe_name>.json
Format: {"timestamp": "<ISO 8601 UTC>", "data": {url: [title, ...], ...}}

Public API
----------
load_cache(site)            -> dict | None
save_cache(site, data)      -> None
is_stale(payload, days)     -> bool
clear_cache(site)           -> None
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from app_paths import base_dir

# Next to the .exe when frozen, project root from source.  Must not be derived
# from __file__: in a PyInstaller build that resolves into the temporary
# extraction folder, which is wiped on exit - the cache would silently vanish
# after every run.
_CACHE_DIR = base_dir() / "cache"


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _cache_path(site: str) -> Path:
    safe = site.replace(".", "_")
    return _CACHE_DIR / f"{safe}.json"


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def load_cache(site: str) -> dict | None:
    """Return the raw payload ``{timestamp, data}`` or *None* if absent / corrupt."""
    path = _cache_path(site)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_cache(site: str, data: dict) -> None:
    """Write *data* to disk under a fresh UTC timestamp.

    The cache directory is created automatically if it does not yet exist;
    a directory that cannot be created (e.g. an exe placed in a read-only
    folder) is reported and skipped rather than raised at the call site.
    No indentation is used so large title lists stay compact on disk while
    still being valid JSON.  ``ensure_ascii=False`` preserves CJK characters.
    """
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with _cache_path(site).open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except OSError as e:
        print(f"[cache] Could not save {site}: {e}")


def is_stale(payload: dict, cache_days: int) -> bool:
    """Return *True* if the payload's timestamp is older than *cache_days* days.

    An unreadable or missing timestamp is treated as stale so a fresh fetch
    is always triggered for malformed files.
    """
    try:
        ts = datetime.fromisoformat(payload["timestamp"])
        # Normalise to tz-aware (handles files written before tz info was added)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).days >= cache_days
    except (KeyError, ValueError, TypeError):
        return True


def clear_cache(site: str) -> None:
    """Delete the cache file for *site* (e.g. when the user disables caching)."""
    try:
        _cache_path(site).unlink(missing_ok=True)
    except OSError as e:
        print(f"[cache] Could not clear {site}: {e}")
