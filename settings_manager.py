import json
from pathlib import Path

from app_paths import base_dir

# Always sits next to this file (and the widget script)
_SETTINGS_FILE = base_dir() / "settings.json"

# All supported quality tiers, ordered from highest to lowest.
QUALITIES: list[str] = ["4K", "1080p", "720p", "480p", "360p"]

DEFAULTS: dict = {
    "aniworld.to": False,
    "s.to": False,
    "bs.to": False,
    "anikototv.to": False,
    "hanime.tv": False,
    "animepahe.ch": False,
    "aniworld.to_cache": True,
    "s.to_cache": True,
    "bs.to_cache": True,
    "anikototv.to_cache": True,
    "hanime.tv_cache": True,
    "animepahe.ch_cache": True,
    "cache_days": 7,
    "download_path": str(base_dir()),
    "simultaneous_downloads": 3,
    "download_delay": 3,
    "failed_retries": 1,
    "shutdown_when_done": False,
    "max_quality": "1080p",
    "min_quality": "360p",
    "theme": "Dark",
    "neon_color": "Aqua",
    # The language of the interface itself - a key of i18n.LANGUAGES.
    "app_language": "English",
    "providers": [
        {"name": "VOE",        "enabled": True},
        {"name": "Vidmoly",    "enabled": True},
        {"name": "Doodstream", "enabled": True},
        {"name": "Filemoon",   "enabled": False},
        {"name": "Vidoza",   "enabled": True},
        {"name": "SpeedFiles",   "enabled": True},
        {"name": "Vidstream",   "enabled": True},
        {"name": "Kiwi-Stream",   "enabled": True},
        # The Blogger video player some animepahe episodes use - it streams
        # straight from Google's servers, and appears on no other site.
        {"name": "Blogger",   "enabled": True},
        # hanime.tv is its own host rather than an embed provider, so this entry
        # only ever applies to that site's pages.  It still lives here because
        # the worker resolves providers through the shared enabled-list.
        {"name": "Hanime",   "enabled": True},
    ],
    "languages": [
        {"name": "Japanese · English Sub", "enabled": True},
        {"name": "English Dub",            "enabled": True},
        {"name": "Japanese · German Sub",  "enabled": False},
        {"name": "German Dub",             "enabled": False},
        # Only offered where separate subtitle tracks exist (the Vidstream /
        # MegaPlay player on anikototv and animepahe), so they start disabled.
        {"name": "Japanese · Portuguese (Brazil) Sub",     "enabled": False},
        {"name": "Japanese · Spanish Sub",                 "enabled": False},
        {"name": "Japanese · Spanish (Latin America) Sub", "enabled": False},
        {"name": "Japanese · French Sub",                  "enabled": False},
        {"name": "Japanese · Indonesian Sub",              "enabled": False},
        {"name": "Japanese · Thai Sub",                    "enabled": False},
        {"name": "Japanese · Vietnamese Sub",              "enabled": False},
    ],
}


def _merge_named_list(saved: list[dict], defaults: list[dict]) -> list[dict]:
    """Merge an on-disk ``{"name": ..., "enabled": ...}`` list with the current defaults.

    - Existing entries keep their saved position and enabled state.
    - Entries present in *defaults* but absent from *saved* (newly added) are appended.
    - Entries in *saved* but absent from *defaults* (removed from code) are dropped.
    """
    default_names = {p["name"] for p in defaults}
    saved_names   = {p["name"] for p in saved}

    kept     = [p for p in saved    if p["name"] in default_names]
    appended = [p.copy() for p in defaults if p["name"] not in saved_names]
    return kept + appended


def load() -> dict:
    """
    Return settings from disk, merged with DEFAULTS so any key added
    in a future version is always present even on old save files.
    Creates the file with defaults if it doesn't exist yet.
    """
    if not _SETTINGS_FILE.exists():
        save(DEFAULTS.copy())
        return DEFAULTS.copy()

    try:
        with _SETTINGS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)

        merged = {**DEFAULTS, **data}

        # A shallow dict merge replaces whole lists, losing any entry added to
        # DEFAULTS after the file was first written.  Re-merge each named list
        # by name so new defaults are always picked up.
        for key in ("providers", "languages"):
            merged[key] = _merge_named_list(
                data.get(key, []),
                DEFAULTS[key],
            )

        # If any list changed, write back so the next load() is a no-op.
        if any(merged[k] != data.get(k, []) for k in ("providers", "languages")):
            save(merged)

        return merged

    except (json.JSONDecodeError, OSError):
        return DEFAULTS.copy()


def save(settings: dict) -> None:
    """Persist the current settings dict to disk."""
    try:
        with _SETTINGS_FILE.open("w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except OSError as e:
        print(f"[settings] Could not save: {e}")


# ------------------------------------------------------------------
# Shared query helpers
# ------------------------------------------------------------------

def _get_enabled(settings: dict, key: str, supported: list[str]) -> list[str]:
    supported_set = set(supported)
    return [
        p["name"]
        for p in settings.get(key, [])
        if p["enabled"] and p["name"] in supported_set
    ]


def get_enabled_providers(settings: dict, supported: list[str]) -> list[str]:
    """Return enabled provider names in global priority order, filtered to *supported*.

    Example::

        for provider in get_enabled_providers(settings_state, SUPPORTED_PROVIDERS):
            url = try_provider(provider, episode_url)
            if url:
                break
    """
    return _get_enabled(settings, "providers", supported)


def get_enabled_languages(settings: dict, supported: list[str]) -> list[str]:
    """Return enabled language names in global priority order, filtered to *supported*.

    Example::

        for lang in get_enabled_languages(settings_state, SUPPORTED_LANGUAGES):
            code = LANGUAGE_CODES[lang]
            ...
    """
    return _get_enabled(settings, "languages", supported)


def _quality_index(quality: str, fallback: int) -> int:
    """Position of *quality* in QUALITIES, or *fallback* if it isn't recognised."""
    try:
        return QUALITIES.index(quality)
    except ValueError:
        return fallback


def get_available_qualities(settings: dict) -> list[str]:
    """Return the quality tiers between the user's maximum and minimum, inclusive.

    The list is ordered highest → lowest so callers can iterate and try each
    tier in turn, falling back to the next lower one on failure.  Tiers below
    the configured minimum are left out entirely, so an episode that is only
    offered below that floor fails instead of downloading at a resolution the
    user does not want.

    Example::

        for quality in get_available_qualities(settings_state):
            stream_url = try_quality(quality, episode_url)
            if stream_url:
                break

    An unrecognised saved value falls back to the widest bound on its side, so
    no tier is silently excluded by a typo in the settings file.
    """
    # QUALITIES runs highest → lowest, so the maximum tier starts the slice and
    # the minimum tier ends it.
    start_idx = _quality_index(settings.get("max_quality", "1080p"), 0)
    end_idx = _quality_index(settings.get("min_quality", QUALITIES[-1]), len(QUALITIES) - 1)
    # A minimum above the maximum is contradictory and only reachable from a
    # hand-edited settings file - the Settings page keeps the two in order.
    # Let the maximum win so the sweep collapses to that single tier rather
    # than returning an empty list, which would download nothing at all.
    end_idx = max(end_idx, start_idx)
    return QUALITIES[start_idx:end_idx + 1]