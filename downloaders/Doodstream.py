"""Doodstream downloader.

Doodstream serves a single MP4 assembled from a ``/pass_md5/`` token embedded
in the page:

  1. fetch the embed page,
  2. read the ``/pass_md5/<id>/<token>`` path,
  3. GET that pass_md5 endpoint (with a Referer) to obtain a base URL,
  4. append a random suffix + ``?token=…&expiry=…``.

ffmpeg needs the same Referer.  Doodstream rotates its domain often, so the
domain is taken from the URL the embed actually resolved to rather than being
hard-coded.

Doodstream serves a single MP4 with no advertised resolution, so to take part
in the worker's quality sweep it probes the stream once with ffprobe and
reports the real tier: when that tier doesn't match the one being requested it
returns failure, letting the worker try a higher-resolution provider instead of
short-circuiting on whatever tier it happened to be on.  The probed height is
cached per embed URL so the repeated per-tier calls only resolve/probe once.
"""

from re import compile
from time import time
from random import choices
from string import ascii_letters, digits
from urllib.parse import urlsplit

from downloaders import common

DOODSTREAM_PATTERN = compile(r"/pass_md5/[\w-]+/(?P<token>[\w-]+)")


def _resolve_direct_url(url: str):
    """Return ``(direct_mp4_url, referer)`` for a Doodstream embed *url*.

    Returns ``(None, None)`` when the page doesn't contain a pass_md5 token.
    """
    resp = common.http_get(url)
    html = resp.text

    # The pass_md5 endpoint lives on whatever domain the embed resolved to.
    final = urlsplit(str(resp.url))
    base = f"{final.scheme}://{final.netloc}"
    referer = base + "/"

    m = DOODSTREAM_PATTERN.search(html)
    if not m:
        return None, None
    pass_md5 = m.group()
    token = m.group("token")

    pass_resp = common.http_get(
        base + pass_md5,
        headers={**common.HEADERS, "Referer": referer},
    )
    prefix = pass_resp.text.strip()
    if not prefix:
        return None, None

    suffix = "".join(choices(ascii_letters + digits, k=10))
    direct = f"{prefix}{suffix}?token={token}&expiry={int(time() * 1000)}"
    return direct, referer


def find_content_url(url: str) -> str | None:
    direct, _referer = _resolve_direct_url(url)
    return direct


def _detect_height(url: str) -> int | None:
    """Probe the actual video height for a Doodstream embed *url* (cached).

    Resolves the direct stream once and runs ffprobe with the required Referer.
    The result (an int, or None when it couldn't be determined) is cached per
    embed URL so the worker's per-tier retries don't re-resolve or re-probe.
    """
    cache_key = "doodstream:" + url
    cached = common.cached_height(cache_key)
    if cached is not common.UNSET:
        return cached

    direct, referer = _resolve_direct_url(url)
    height = common.ffprobe_height(direct, referer=referer) if direct else None
    common.store_height(cache_key, height)
    return height


def download(url, download_path, file_name, quality=None):
    # Quality gate: only download when the host's real resolution matches the
    # tier the worker is asking for, so a 480p file doesn't get grabbed during
    # the 1080p pass and pre-empt a higher-resolution provider.  If ffprobe is
    # unavailable or the probe fails, height is None and we fall through to a
    # best-effort download (the pre-probe behaviour).
    if quality and common.tier_blocks(_detect_height(url), quality):
        return False

    direct, referer = _resolve_direct_url(url)
    if not direct:
        return False
    return common.run_ffmpeg(direct, download_path, file_name, referer=referer)