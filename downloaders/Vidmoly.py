"""Vidmoly downloader.

Vidmoly embeds an HLS master playlist in a ``sources: [{file:"…m3u8"}]`` block.
The master lists every rendition, so quality selection works exactly like VOE.
Every request - the master, the variant playlists and the final ffmpeg mux -
needs a ``vidmoly.to`` Referer header.
"""

from re import compile
import threading

from downloaders import common

VIDMOLY_PATTERN = compile(r"sources: \[{file:\"(?P<url>.*?)\"}]")

_REFERER = "https://vidmoly.to/"

# Per-process caches so the worker's quality loop doesn't re-resolve the same
# embed page / master playlist once per tier.
_master_cache: dict[str, str | None] = {}
_variants_cache: dict[str, dict[str, str]] = {}
_cache_lock = threading.Lock()


def _headers() -> dict:
    return {**common.HEADERS, "Referer": _REFERER}


def _get_master(url: str) -> str | None:
    """Return the HLS master-playlist URL embedded in the Vidmoly page (cached)."""
    with _cache_lock:
        if url in _master_cache:
            return _master_cache[url]

    master = None
    try:
        html = common.http_get(url, headers=_headers()).text
        m = VIDMOLY_PATTERN.search(html)
        if m:
            link = m.group("url")
            if link.startswith("//"):
                link = "https:" + link
            master = link
    except Exception:
        master = None

    # Option A: only cache a successful resolution so a transient failure isn't
    # remembered for the rest of the session (the "restart fixes it" bug).
    if master:
        with _cache_lock:
            _master_cache[url] = master
    return master


def _get_variants(master_url: str) -> dict[str, str]:
    """Fetch and parse *master_url* into ``{tier: url}`` (cached)."""
    with _cache_lock:
        if master_url in _variants_cache:
            return _variants_cache[master_url]

    variants: dict[str, str] = {}
    try:
        text = common.http_get(master_url, headers=_headers()).text
        variants = common.parse_hls_master(text, master_url)
    except Exception:
        variants = {}

    # Option A: only cache a non-empty parse (see VOE._get_variants).
    if variants:
        with _cache_lock:
            _variants_cache[master_url] = variants
    return variants


def find_content_url(url: str) -> str | None:
    return _get_master(url)


def _resolve_target_url(url: str, quality: str | None) -> str | None:
    master = _get_master(url)
    if not master:
        return None
    if not quality:
        return master
    variants = _get_variants(master)
    if variants:
        return variants.get(quality)  # None ⇒ tier unavailable, try next
    # Single-quality media playlist (no renditions).
    return master


def download(url, download_path, file_name, quality=None):
    target = _resolve_target_url(url, quality)
    if not target:
        return False
    return common.run_ffmpeg(target, download_path, file_name, referer=_REFERER)