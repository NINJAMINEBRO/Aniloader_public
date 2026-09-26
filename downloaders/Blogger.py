"""Blogger (animepahe) downloader.

Some animepahe episodes - "Link Click Season 3" is one - play through Blogger's
video player (``https://www.blogger.com/video.g?token=…``) instead of an embed
host.  ``pages/animepahe_ch.py`` hands that player URL here.

The player page no longer carries any stream URLs itself; it asks for them
through Google's batchexecute RPC (``WcwnYd``), keyed by the player's token.
That call answers a plain POST - no browser, no cookies - with the video's
progressive MP4 renditions on googlevideo.com (itag 18 = 360p, itag 22 = 720p)
and, alongside them, each rendition's dimensions.

Two quirks of those googlevideo URLs decide how the file is fetched:

* They refuse a request that does not look like it came from a browser: ffmpeg's
  own User-Agent and python-requests' both get a 403.  Every request here
  carries the shared browser User-Agent instead.
* One connection reading the whole file is throttled to barely more than
  playback speed - ffmpeg took eleven minutes for a 22-minute 360p episode -
  while the very same file fetched as a run of ranged requests arrives in
  seconds.  So the file is downloaded here in chunks, and only the finished MP4
  goes through ffmpeg, which remuxes it locally.

The URLs are signed for the address that asked for them and expire after a few
hours, so a resolution is only reused briefly and is dropped when a download
fails, letting a retried episode ask for fresh ones.

Quality handling mirrors every other provider: :func:`download` attempts the
exact tier it is asked for and returns ``False`` when Blogger has no rendition
at that tier, so ``EpisodeDownloadWorker`` falls back to the next-lower one.
"""

import json
import os
import threading
from time import monotonic
from urllib.parse import parse_qs, urlsplit

import requests

from downloaders import common

_RPC_URL = "https://www.blogger.com/_/BloggerVideoPlayerUi/data/batchexecute"
_RPC_ID = "WcwnYd"

# Heights of the itags Blogger serves, for a response that leaves out the
# streamingData block the dimensions normally come from.
_ITAG_HEIGHTS = {18: 360, 22: 720, 37: 1080, 59: 480}

# Size of one ranged request.  Chunks this size come down at full speed; see the
# module docstring for why the file is not fetched in one go.
_CHUNK_SIZE = 10 * 1024 * 1024
_CHUNK_TIMEOUT = 60

# How long resolved stream URLs are reused.  They stay valid for hours, but the
# worker only needs them for the few minutes it spends on one episode.
_STREAMS_TTL = 600.0

# Per-process cache so the worker's quality loop doesn't repeat the RPC once
# per tier: player URL -> (resolved at, {tier: stream URL}).
_streams_cache: dict[str, tuple[float, dict[str, str]]] = {}
_cache_lock = threading.Lock()


# ----------------------------------------------------------------------
# Player URL → stream URLs
# ----------------------------------------------------------------------

def _token(player_url: str) -> str | None:
    """The ``token`` query parameter that identifies the video to the RPC."""
    values = parse_qs(urlsplit(player_url).query).get("token")
    return values[0] if values else None


def _rpc_result(text: str) -> list | None:
    """Pull the ``WcwnYd`` result out of a batchexecute response body.

    The body opens with the ``)]}'`` guard line and then carries the envelope
    either as one JSON array or, in the chunked format, as length-prefixed
    lines.  Both are handled so a change of format on Google's side doesn't
    silently break every Blogger download.
    """
    body = text.split("\n", 1)[1] if text.startswith(")]}'") else text
    try:
        envelopes = [json.loads(body)]
    except ValueError:
        envelopes = []
        for line in body.splitlines():
            line = line.strip()
            if line.startswith("["):
                try:
                    envelopes.append(json.loads(line))
                except ValueError:
                    continue

    for envelope in envelopes:
        for entry in envelope if isinstance(envelope, list) else []:
            if (isinstance(entry, list) and len(entry) > 2
                    and entry[0] == "wrb.fr" and entry[1] == _RPC_ID
                    and isinstance(entry[2], str)):
                try:
                    result = json.loads(entry[2])
                except ValueError:
                    return None
                return result if isinstance(result, list) else None
    return None


def _streams_from_result(result: list) -> dict[str, str]:
    """``{tier: stream URL}`` from the RPC result, highest bitrate per tier.

    The result holds the renditions twice: as ``[url, [itag]]`` pairs, and as a
    YouTube-style ``streamingData`` JSON string that also gives each one's
    height.  The latter is preferred; the pairs are the fallback, bucketed by
    their itag's known height.
    """
    found: dict[str, tuple[int, str]] = {}

    def keep(height: int, url: str, bitrate: int = 0) -> None:
        tier = common.height_to_tier(height)
        if tier not in found or bitrate > found[tier][0]:
            found[tier] = (bitrate, url)

    for item in result:
        if not (isinstance(item, str) and '"streamingData"' in item):
            continue
        try:
            formats = json.loads(item).get("streamingData", {}).get("formats", [])
        except (ValueError, AttributeError):
            continue
        for fmt in formats:
            url = fmt.get("url") if isinstance(fmt, dict) else None
            height = fmt.get("height") if isinstance(fmt, dict) else None
            if isinstance(url, str) and url.startswith("http") and isinstance(height, int):
                keep(height, url, int(fmt.get("bitrate") or 0))

    if not found:
        for item in result:
            if not isinstance(item, list):
                continue
            for pair in item:
                if (isinstance(pair, list) and len(pair) >= 2
                        and isinstance(pair[0], str) and pair[0].startswith("http")
                        and isinstance(pair[1], list) and pair[1]):
                    height = _ITAG_HEIGHTS.get(pair[1][0])
                    if height:
                        keep(height, pair[0])

    return {tier: url for tier, (_bitrate, url) in found.items()}


def _streams(player_url: str) -> dict[str, str]:
    """Return ``{tier: stream URL}`` for a Blogger player URL (briefly cached)."""
    with _cache_lock:
        cached = _streams_cache.get(player_url)
        if cached and monotonic() - cached[0] < _STREAMS_TTL:
            return cached[1]

    token = _token(player_url)
    if not token:
        return {}

    request = json.dumps([[[_RPC_ID, json.dumps([token, "", 0]), None, "generic"]]])
    try:
        resp = requests.post(
            _RPC_URL,
            params={"rpcids": _RPC_ID, "source-path": "/video.g", "hl": "en-US"},
            data={"f.req": request},
            headers={
                **common.HEADERS,
                "Origin": "https://www.blogger.com",
                "Referer": player_url,
            },
            timeout=30,
        )
    except Exception:
        return {}
    if resp.status_code != 200:
        return {}

    result = _rpc_result(resp.text)
    streams = _streams_from_result(result) if result else {}
    # Only a successful resolution is cached, so a transient failure isn't
    # remembered for the rest of the session.
    if streams:
        with _cache_lock:
            _streams_cache[player_url] = (monotonic(), streams)
    return streams


def _forget(player_url: str) -> None:
    """Drop a cached resolution so the next attempt asks for fresh URLs."""
    with _cache_lock:
        _streams_cache.pop(player_url, None)


# ----------------------------------------------------------------------
# Chunked download
# ----------------------------------------------------------------------

def _total_size(resp) -> int | None:
    """The full file size from a 206 response's ``Content-Range``, or None."""
    content_range = resp.headers.get("Content-Range", "")
    total = content_range.rsplit("/", 1)[-1] if "/" in content_range else ""
    return int(total) if total.isdigit() else None


def _fetch_file(stream_url: str, path: str) -> bool:
    """Download *stream_url* to *path* as a run of ranged requests.

    True only when every byte the server announced arrived, so a transfer cut
    short is never passed off as a finished episode.
    """
    total = None
    position = 0
    with open(path, "wb") as out:
        while total is None or position < total:
            if common.is_cancelled():
                return False
            resp = common.http_get(
                stream_url,
                headers={**common.HEADERS,
                         "Range": f"bytes={position}-{position + _CHUNK_SIZE - 1}"},
                timeout=_CHUNK_TIMEOUT,
            )
            if resp.status_code == 200:
                # The range was ignored and the whole file sent at once.
                out.write(resp.content)
                return bool(resp.content)
            if resp.status_code != 206 or not resp.content:
                return False
            total = _total_size(resp) or total
            out.write(resp.content)
            position += len(resp.content)
            if total is None:
                return False  # no size to check against - don't guess
    return position == total


# ----------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------

def download(url, download_path, file_name, quality=None):
    """Download one episode from its Blogger player *url*.

    Returns True on success and False on any failure - including when
    *quality* isn't offered, which lets the worker retry at a lower tier.
    """
    try:
        streams = _streams(url)
        if not streams:
            return False
        if quality:
            target = streams.get(quality)  # None ⇒ tier unavailable, try next
        else:
            order = [tier for tier, _min_h in common.QUALITY_TIERS]
            target = streams[min(streams, key=order.index)]
        if not target:
            return False

        os.makedirs(download_path, exist_ok=True)
        part_path = os.path.join(download_path, file_name + ".part.mp4")
        try:
            if not _fetch_file(target, part_path):
                _forget(url)
                return False
            # Remux the finished MP4 locally: fast, and a file ffmpeg can't
            # read fails here rather than landing in the library.
            if not common.run_ffmpeg(part_path, download_path, file_name):
                _forget(url)
                return False
            return True
        finally:
            try:
                os.remove(part_path)
            except OSError:
                pass
    except Exception as exc:  # never let a provider crash the worker
        print(f"[Blogger] error for {url}: {exc}")
        _forget(url)
        return False
