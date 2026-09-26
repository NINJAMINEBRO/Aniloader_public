"""SpeedFiles downloader.

The embed page hides the MP4 URL inside an obfuscated variable that has to be
run through a fixed multi-step decode (base64 / swapcase / reverse / hex-pair /
character shift).  Only aniworld lists this hoster.

SpeedFiles serves a single MP4 with no advertised resolution, so it probes the
decoded stream once with ffprobe and reports its real tier: when that tier
doesn't match the one being requested it returns failure, so the worker can try
a higher-resolution provider instead of settling for this one at whatever tier
it happened to be sweeping.  The probed height is cached per embed URL.
"""

from re import compile
from base64 import b64decode

from downloaders import common

SPEEDFILES_PATTERN = compile(r'var _0x5opu234 = "(?P<content>.*?)";')


def _decode(content: str) -> str:
    """Reverse SpeedFiles' obfuscation to recover the direct video URL."""
    content = b64decode(content).decode()          # 1: base64
    content = content.swapcase()                    # 2: swap case
    content = content[::-1]                          # 3: reverse
    content = b64decode(content).decode()           # 4: base64
    content = content[::-1]                          # 5: reverse
    # 6: each pair of hex digits → a character
    hex_pairs = "".join(
        chr(int(content[i:i + 2], 16)) for i in range(0, len(content), 2)
    )
    # 7: shift every character down by 3
    shifted = "".join(chr(ord(c) - 3) for c in hex_pairs)
    shifted = shifted.swapcase()                     # 8: swap case
    shifted = shifted[::-1]                          # 9: reverse
    return b64decode(shifted).decode()              # 10: base64 → final URL


def find_content_url(url: str) -> str | None:
    try:
        html = common.http_get(url).text
        m = SPEEDFILES_PATTERN.search(html)
        if not m:
            return None
        return _decode(m.group("content"))
    except Exception:
        return None


def _detect_height(url: str) -> int | None:
    """Probe the actual video height for a SpeedFiles embed *url* (cached).

    Decodes the direct stream once and runs ffprobe (no Referer needed).  The
    result is cached per embed URL so the worker's per-tier retries reuse it.
    """
    cache_key = "speedfiles:" + url
    cached = common.cached_height(cache_key)
    if cached is not common.UNSET:
        return cached

    target = find_content_url(url)
    height = common.ffprobe_height(target) if target else None
    common.store_height(cache_key, height)
    return height


def download(url, download_path, file_name, quality=None):
    # Quality gate: only download when the host's real resolution matches the
    # requested tier (see Doodstream for the rationale).  A failed/absent probe
    # yields None and falls through to a best-effort download.
    if quality and common.tier_blocks(_detect_height(url), quality):
        return False

    target = find_content_url(url)
    if not target:
        return False
    return common.run_ffmpeg(target, download_path, file_name)