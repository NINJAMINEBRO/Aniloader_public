"""Vidoza downloader.

A Vidoza embed page serves the video as one or more ``<source>`` elements
holding a direct MP4 URL (no HLS master like VOE).  Most uploads expose a
single source, but when several are present (each tagged with a resolution)
this module selects the one matching the requested quality tier and otherwise
falls back to the next tier - mirroring the VOE behaviour so quality selection
works identically.  When a page exposes only one untagged source, its height is
probed with ffprobe so it too joins the worker's quality sweep at its real tier
rather than short-circuiting it.

The site-agnostic flow (fetch redirect page → read ``<source>`` → ffmpeg) means
any website that resolves an episode to a Vidoza redirect URL can reuse this
module unchanged; only aniworld is wired up for it today.
"""

from re import compile, search
import threading

from bs4 import BeautifulSoup

from downloaders import common

# Fallback for pages that embed the URL in a JS player config rather than a
# <source> tag, e.g.  sources: [{src:"https://….mp4", …}]  /  file:"https://….mp4"
_JS_SOURCE_PATTERN = compile(r'(?:file|src)\s*:\s*"(?P<url>https?://[^"]+\.mp4[^"]*)"')

# Per-process cache: Vidoza page URL -> [(src, height|None), …].  The page is
# fetched once even though the worker's quality loop calls in repeatedly.
_sources_cache: dict[str, list[tuple[str, int | None]]] = {}
_cache_lock = threading.Lock()


def _source_height(tag) -> int | None:
    """Best-effort pixel height for a ``<source>`` tag from its attributes.

    Reads res/label/size-style attributes (e.g. ``res="1280x720"``,
    ``label="720p"``) and returns the vertical resolution, or None if unknown.
    """
    for attr in ("res", "label", "data-res", "size", "title"):
        val = str(tag.get(attr, "")).strip()
        if not val:
            continue
        # "1280x720" → take the height after the 'x'
        m = search(r"\d+\s*[xX]\s*(\d+)", val)
        if m:
            return int(m.group(1))
        # "720", "720p", "1080P" → take the number
        m = search(r"(\d{3,4})", val)
        if m:
            return int(m.group(1))
    return None


def _get_sources(url: str) -> list[tuple[str, int | None]]:
    """Fetch the Vidoza page and return its ``[(mp4_url, height|None), …]`` (cached)."""
    with _cache_lock:
        if url in _sources_cache:
            return _sources_cache[url]

    sources: list[tuple[str, int | None]] = []
    try:
        html = common.http_get(url).text
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all("source"):
            src = tag.get("src") or tag.get("data-src")
            if src:
                sources.append((src.strip(), _source_height(tag)))
        # Fall back to a JS player config if no <source> elements were present.
        if not sources:
            m = _JS_SOURCE_PATTERN.search(html)
            if m:
                sources.append((m.group("url"), None))
    except Exception:
        sources = []

    with _cache_lock:
        _sources_cache[url] = sources
    return sources


def find_content_url(url: str) -> str | None:
    """Return the best available MP4 URL for *url* (highest known resolution)."""
    sources = _get_sources(url)
    if not sources:
        return None
    return sorted(sources, key=lambda s: s[1] or 0, reverse=True)[0][0]


def _resolve_target_url(url: str, quality: str | None) -> str | None:
    """Resolve the MP4 URL to hand ffmpeg for the requested *quality*.

    Returns None to signal "this tier isn't offered" so the worker falls back
    to the next lower tier (exactly like the VOE resolver).
    """
    sources = _get_sources(url)
    if not sources:
        return None

    # No specific tier requested → just take the best stream.
    if not quality:
        return sorted(sources, key=lambda s: s[1] or 0, reverse=True)[0][0]

    tiered: dict[str, str] = {}
    untiered: list[str] = []
    for src, height in sources:
        if height:
            tiered.setdefault(common.height_to_tier(height), src)
        else:
            untiered.append(src)

    if tiered:
        # Exact tier match, or signal "try the next lower tier".
        return tiered.get(quality)

    # Only quality-less sources → a single stream of unknown resolution.  Probe
    # it with ffprobe so it joins the quality sweep at its real tier instead of
    # masquerading as whatever tier the worker is on (which would short-circuit
    # the search before a higher-resolution provider is tried).  A failed or
    # unavailable probe leaves height None → best-effort download, as before.
    if not untiered:
        return None
    src = untiered[0]
    cache_key = "vidoza:" + src
    height = common.cached_height(cache_key)
    if height is common.UNSET:
        height = common.ffprobe_height(src)
        common.store_height(cache_key, height)
    if common.tier_blocks(height, quality):
        return None
    return src


def download(url, download_path, file_name, quality=None):
    """Download the Vidoza video at *url* into download_path/file_name.

    Returns True on success, False on failure (so the worker can fall back to
    the next quality tier or provider).
    """
    target_url = _resolve_target_url(url, quality)
    if not target_url:
        return False
    return common.run_ffmpeg(target_url, download_path, file_name)