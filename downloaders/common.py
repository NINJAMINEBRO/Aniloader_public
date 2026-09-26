"""Shared helpers for provider downloaders.

Every hoster needs the same handful of primitives: a way to mux a resolved
stream with ffmpeg (handling a missing ffmpeg and partial-file cleanup), a
mapping from pixel height to the app's quality tiers, an HLS master-playlist
parser, and a small HTTP helper.  Centralising them here means new providers
- and, later, other websites - can reuse the logic instead of copying it.

A provider downloader only has to:
  1. resolve a page/redirect URL to the actual stream URL for a quality tier
  2. hand that URL to ``run_ffmpeg``.
"""

from os import path, makedirs, remove
import re
import subprocess
import threading
from time import sleep
from urllib.parse import urljoin

import requests

from app_paths import base_dir

# Shared browser-like headers; reused for every plain HTTP request.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": USER_AGENT}


# ------------------------------------------------------------------
# Quality tiers
# ------------------------------------------------------------------
# Map a rendition's pixel height onto one of the app's quality tiers.
# Ordered high → low; the first tier whose minimum height is met wins, so
# slightly non-standard heights (e.g. 1088, 540) still bucket sensibly.
QUALITY_TIERS = [("4K", 1440), ("1080p", 900), ("720p", 600), ("480p", 420), ("360p", 0)]


def height_to_tier(height: int) -> str:
    """Return the quality-tier name for a pixel *height* (e.g. 1080 → '1080p')."""
    for tier, min_h in QUALITY_TIERS:
        if height >= min_h:
            return tier
    return "360p"


# ------------------------------------------------------------------
# HTTP
# ------------------------------------------------------------------

# HTTP statuses worth retrying - transient server/edge errors and rate limits.
# 4xx codes other than 429 are the caller's problem, not a transient glitch, so
# they are returned as-is rather than retried.
_RETRY_STATUSES = {429, 500, 502, 503, 504}

# A per-thread requests.Session so a worker reuses one connection and carries
# cookies across all the requests it makes while resolving an episode (embed
# page → redirect hops → master playlist).  Thread-local rather than one global
# session because downloads run in concurrent QThreads and a Session's cookie
# jar isn't guaranteed safe to mutate from several threads at once; per-thread
# sidesteps that race while still giving keep-alive + cookie persistence within
# each worker's own scraping.
_sessions = threading.local()


def _session() -> requests.Session:
    """Return this thread's reusable Session, creating it on first use."""
    s = getattr(_sessions, "session", None)
    if s is None:
        s = requests.Session()
        _sessions.session = s
    return s


def http_get(url: str, headers: dict | None = None, timeout: int = 15,
             retries: int = 3, backoff: float = 0.5) -> requests.Response:
    """``requests.get`` with shared headers, a default timeout, and retries.

    Uses a per-thread :class:`requests.Session` so connections are kept alive
    and cookies persist across the requests a worker makes for one episode
    (helps when a hoster gates on a session/clearance cookie).

    Transient failures - connection errors, timeouts, and the HTTP statuses in
    ``_RETRY_STATUSES`` - are retried up to *retries* times, sleeping
    ``backoff * 2**attempt`` seconds between tries (0.5s, 1s, 2s by default).

    On success the ``Response`` is returned.  After the final attempt the last
    response is returned as-is when it carried a non-fatal but retryable status
    (so the caller's existing ``.text`` parsing still runs), or the last
    connection/timeout exception is raised - matching the old behaviour where a
    dead endpoint surfaced as an exception.  A pending cancellation stops the
    retry loop early so app shutdown isn't held up by backoff sleeps.
    """
    session = _session()
    last_exc: Exception | None = None
    resp: requests.Response | None = None
    for attempt in range(retries + 1):
        try:
            resp = session.get(url, headers=headers or HEADERS, timeout=timeout)
        except requests.RequestException as exc:
            last_exc = exc
            resp = None
        else:
            if resp.status_code not in _RETRY_STATUSES:
                return resp
        # Transient failure (exception or retryable status): back off and retry,
        # unless this was the last attempt or a cancellation is pending.
        if attempt < retries and not is_cancelled():
            sleep(backoff * (2 ** attempt))
        else:
            break

    if resp is not None:
        return resp
    raise last_exc


# ------------------------------------------------------------------
# Cooperative cancellation
# ------------------------------------------------------------------
# run_ffmpeg / ffprobe_height execute inside an EpisodeDownloadWorker's thread.
# They register their live subprocess here keyed by the worker's thread id, so
# the GUI thread can terminate an in-flight ffmpeg/ffprobe when the app is
# closing.  A per-thread "cancelled" flag also stops a subprocess that is just
# about to launch.  Worker threads clear their own flag at the start of each run
# so a recycled thread id never inherits a stale cancellation.

_active_procs: "dict[int, subprocess.Popen]" = {}
_cancelled_tids: set[int] = set()
_cancel_lock = threading.Lock()


def cancel(tid: int) -> None:
    """Mark thread *tid* cancelled and terminate any ffmpeg/ffprobe it is running.

    Safe to call from another thread (e.g. the GUI thread on close).
    """
    with _cancel_lock:
        _cancelled_tids.add(tid)
        proc = _active_procs.get(tid)
    if proc is not None:
        try:
            proc.terminate()
        except Exception:
            pass


def is_cancelled(tid: int | None = None) -> bool:
    """True if cancellation was requested for *tid* (default: current thread)."""
    if tid is None:
        tid = threading.get_ident()
    with _cancel_lock:
        return tid in _cancelled_tids


def clear_cancel(tid: int | None = None) -> None:
    """Clear the cancelled flag for *tid* (default: current thread)."""
    if tid is None:
        tid = threading.get_ident()
    with _cancel_lock:
        _cancelled_tids.discard(tid)


def _register_proc(proc) -> None:
    with _cancel_lock:
        _active_procs[threading.get_ident()] = proc


def _unregister_proc() -> None:
    with _cancel_lock:
        _active_procs.pop(threading.get_ident(), None)


# ------------------------------------------------------------------
# ffmpeg
# ------------------------------------------------------------------

# Switch for ffmpeg download diagnostics.  When True, a failed mux prints the
# tail of ffmpeg's stderr and each retry is announced - useful for debugging
# downloads that fall back to a lower quality/provider.  Off by default.  (The
# one-time "ffmpeg not found" message below is always shown regardless of this
# flag, since without ffmpeg nothing can download at all.)
FFMPEG_DEBUG = False

# Printed at most once per process so a missing ffmpeg doesn't spam the console.
_warned_no_ffmpeg = False
_warn_lock = threading.Lock()


def _tool_path(tool: str) -> str:
    """Resolve an ffmpeg/ffprobe executable.

    Prefers a binary shipped next to the app (base_dir); otherwise returns the
    bare name so the system PATH is searched.  Using the full path means the
    sidecar ffmpeg/ffprobe is found regardless of the process's working
    directory - which is not the exe's folder when launched from a shortcut.
    """
    for name in (f"{tool}.exe", tool):
        candidate = base_dir() / name
        if candidate.is_file():
            return str(candidate)
    return tool


def run_ffmpeg(target_url: str, download_path: str, file_name: str,
               referer: str | None = None, attempts: int = 3,
               retry_delay: float = 2.0,
               extra_inputs: list[str] | None = None,
               output_args: list[str] | None = None) -> bool:
    """Mux *target_url* into ``download_path/file_name`` with ffmpeg.

    Returns True on success, False on any failure.  Creates the (possibly
    nested) destination directory, cleans up a partial file on error, and
    reports a missing ffmpeg once.

    The mux is retried up to *attempts* times.  These hosters serve segments
    from a bandwidth-capped, IP-locked CDN, and under several concurrent 1080p
    downloads a segment occasionally arrives truncated/misaligned - ffmpeg then
    aborts with "Invalid data found" or a timestamp discontinuity.  That failure
    is intermittent (re-downloading the same URL usually comes down clean), so
    retrying the same stream recovers the wanted quality instead of immediately
    dropping to a lower tier or another provider.  The wait between attempts
    grows each time (``retry_delay × attempt`` → 2s, 4s, …) so later attempts
    land after some concurrent downloads have finished and bandwidth has freed
    up.

    *referer* adds an HTTP ``Referer`` header to the ffmpeg request, which some
    hosters require.  Vidoza/VOE don't need it, so it defaults to None.

    *extra_inputs* are further ``-i`` inputs (e.g. subtitle files) and
    *output_args* extra output options placed after ``-c copy`` (e.g. the
    ``-map``/``-metadata`` options that go with those inputs).
    """
    global _warned_no_ffmpeg

    output_path = path.join(download_path, file_name)
    try:
        makedirs(download_path, exist_ok=True)
    except OSError:
        pass

    cmd = [_tool_path("ffmpeg")]
    if referer:
        cmd += ["-headers", f"Referer: {referer}"]
    # Resilience for HTTP/HLS inputs: without these, ffmpeg aborts the entire
    # mux the first time a single segment request is dropped or reset.  They are
    # input options, so they must precede -i.  A local input file (e.g. segments
    # a provider already downloaded itself) rejects them, so only add them for
    # URLs.
    if target_url.startswith(("http://", "https://")):
        cmd += ["-reconnect", "1", "-reconnect_streamed", "1",
                "-reconnect_on_network_error", "1", "-reconnect_delay_max", "5"]
    cmd += ["-i", target_url]
    for extra in extra_inputs or []:
        cmd += ["-i", extra]
    cmd += ["-c", "copy", *(output_args or []), "-nostdin", output_path]

    for attempt in range(1, attempts + 1):
        # Bail before launching if this worker thread was already cancelled.
        if is_cancelled():
            return False

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except FileNotFoundError:
            # ffmpeg itself could not be launched - not installed / not on PATH
            # (surfaces as "[WinError 2]" on Windows).  Retrying won't help, so
            # report once and fail clean.
            with _warn_lock:
                if not _warned_no_ffmpeg:
                    print("[downloaders] ffmpeg was not found. Install ffmpeg and make sure "
                          "it is on your PATH - downloads cannot run without it.")
                    _warned_no_ffmpeg = True
            return False

        # Register so cancel() can terminate this mux from the GUI thread, then
        # re-check in case cancellation landed between the guard and registration.
        _register_proc(proc)
        if is_cancelled():
            try:
                proc.terminate()
            except Exception:
                pass
        try:
            _out, err = proc.communicate()
        finally:
            _unregister_proc()

        if proc.returncode == 0:
            return True

        # Failed - remove the partial file before retrying or giving up (and so
        # a cancelled download leaves nothing half-written behind).
        if path.exists(output_path):
            try:
                remove(output_path)
            except OSError:
                pass

        # A cancellation isn't a real failure: don't log it or retry.
        if is_cancelled():
            return False

        # Surface the tail of ffmpeg's stderr (when enabled) so a failed
        # download is diagnosable instead of silently becoming a fallback.
        if FFMPEG_DEBUG and err:
            tail = err.decode("utf-8", "ignore").strip().splitlines()[-4:]
            label = f"attempt {attempt}/{attempts}" if attempts > 1 else "run"
            print(f"[downloaders] ffmpeg {label} failed for {output_path}:")
            for ln in tail:
                print(f"    {ln}")

        if attempt < attempts:
            if FFMPEG_DEBUG:
                print(f"[downloaders] retrying {file_name} (attempt {attempt + 1}/{attempts})…")
            # Grow the wait each attempt so later tries land after some of the
            # concurrent downloads have finished and freed up bandwidth.
            sleep(retry_delay * attempt)

    return False


# ------------------------------------------------------------------
# ffprobe - resolution detection for single-stream hosts
# ------------------------------------------------------------------
# HLS hosters (VOE, Vidmoly) advertise every rendition in their master
# playlist, so the worker can ask for an exact tier and get None back when it
# isn't offered.  Single-MP4 hosters (Doodstream, SpeedFiles, a lone-source
# Vidoza) expose no such metadata: without help they accept whatever tier the
# worker happens to be on and "succeed", short-circuiting the quality sweep
# before a genuinely higher-resolution provider is tried.
#
# ffprobe (shipped alongside ffmpeg) closes that gap.  It reads only the MP4
# header over HTTP range requests - not the whole file - and reports the video
# height, which we bucket into a tier.  Results are cached so the worker's
# repeated per-tier calls probe at most once per stream.

_UNSET = object()
UNSET = _UNSET  # public sentinel: "no probe cached for this key yet"

_probe_cache: dict[str, "int | None"] = {}
_probe_cache_lock = threading.Lock()
_warned_no_ffprobe = False


def cached_height(cache_key: str):
    """Return a previously probed height for *cache_key*, or ``UNSET``.

    Lets a caller decide whether it still needs to resolve a stream URL before
    probing - on a cache hit it can skip the resolve entirely.
    """
    with _probe_cache_lock:
        return _probe_cache.get(cache_key, _UNSET)


def store_height(cache_key: str, height: "int | None") -> None:
    """Remember a probed *height* (possibly None) for *cache_key*."""
    with _probe_cache_lock:
        _probe_cache[cache_key] = height


def ffprobe_height(stream_url: str, referer: str | None = None) -> "int | None":
    """Return the video pixel height of *stream_url* via ffprobe, or None.

    Reads only the file header (a few range requests), never the whole video.
    Returns None when ffprobe is missing, the probe times out/fails, or no
    video stream is found; callers treat None as "undetermined" and fall back
    to a best-effort download.  *referer* mirrors what ``run_ffmpeg`` sends so
    the probe and the eventual download are seen identically by the hoster.
    """
    global _warned_no_ffprobe
    if not stream_url:
        return None

    cmd = [_tool_path("ffprobe"), "-v", "error"]
    if referer:
        cmd += ["-headers", f"Referer: {referer}\r\n"]
    cmd += [
        "-select_streams", "v:0",
        "-show_entries", "stream=height",
        "-of", "default=noprint_wrappers=1:nokey=1",
        "-i", stream_url,
    ]

    if is_cancelled():
        return None

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        # ffprobe absent (e.g. a stripped ffmpeg build).  Degrade gracefully:
        # without a probe these hosters behave as before (accept-as-asked).
        with _warn_lock:
            if not _warned_no_ffprobe:
                print("[downloaders] ffprobe was not found (it ships with ffmpeg). "
                      "Quality pre-checks for single-stream hosts are disabled; "
                      "downloads will still run.")
                _warned_no_ffprobe = True
        return None
    except OSError:
        return None

    _register_proc(proc)
    if is_cancelled():
        try:
            proc.terminate()
        except Exception:
            pass
    try:
        out, _err = proc.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.communicate()
        except Exception:
            pass
        return None
    except (subprocess.SubprocessError, OSError):
        return None
    finally:
        _unregister_proc()

    for line in (out or b"").decode("utf-8", "ignore").splitlines():
        line = line.strip()
        if line.isdigit():
            return int(line)
    return None


def tier_blocks(height: "int | None", requested_quality: str | None) -> bool:
    """True when a probed *height* should be SKIPPED for *requested_quality*.

    A single-stream downloader calls this and returns failure when it's True,
    so the worker moves on to the next provider/tier.  Returns False (i.e.
    "go ahead and download") when no specific tier was requested or the height
    couldn't be determined - preserving best-effort behaviour in those cases.
    """
    if not requested_quality or height is None:
        return False
    return height_to_tier(height) != requested_quality


# ------------------------------------------------------------------
# HLS master playlist parsing (used by HLS providers such as VOE)
# ------------------------------------------------------------------

def parse_hls_master(text: str, base_url: str) -> dict[str, str]:
    """Parse an HLS master playlist into ``{quality_tier: variant_url}``.

    Tries the ``m3u8`` library first (more tolerant of attribute ordering and
    formatting quirks) and falls back to a small built-in parser when the
    library isn't installed, errors, or finds nothing.  Both paths produce the
    same result: the highest-bandwidth variant per tier, resolution-less
    variants skipped (they can't be bucketed into a tier).

    Returns an empty dict when *text* is a single-quality media playlist rather
    than a master (no ``#EXT-X-STREAM-INF`` renditions).
    """
    variants = _parse_hls_master_m3u8(text, base_url)
    if not variants:  # library unavailable/errored (None) or found nothing ({})
        variants = _parse_hls_master_regex(text, base_url)
    return variants


def _parse_hls_master_m3u8(text: str, base_url: str) -> dict[str, str] | None:
    """Parse with the ``m3u8`` library, or return None to signal "fall back".

    Returns a ``{tier: url}`` dict on success (possibly empty for a media
    playlist) and None when the library is missing or raises, so the caller
    knows to try the regex parser instead.
    """
    try:
        import m3u8
    except ImportError:
        return None
    try:
        playlist = m3u8.loads(text)
    except Exception:
        return None

    best: dict[str, tuple[int, str]] = {}
    for variant in playlist.playlists:
        info = getattr(variant, "stream_info", None)
        resolution = getattr(info, "resolution", None) if info else None
        if not resolution:
            continue  # no height ⇒ can't map to a tier (matches regex parser)
        tier = height_to_tier(int(resolution[1]))
        bw = getattr(info, "bandwidth", 0) or 0
        url = urljoin(base_url, variant.uri)
        if tier not in best or bw > best[tier][0]:
            best[tier] = (bw, url)
    return {tier: url for tier, (_bw, url) in best.items()}


def _parse_hls_master_regex(text: str, base_url: str) -> dict[str, str]:
    """Built-in fallback parser (no third-party dependency).

    Scans for ``#EXT-X-STREAM-INF`` rendition entries, reads RESOLUTION/
    BANDWIDTH, and keeps the highest-bandwidth variant per tier.
    """
    variants: dict[str, tuple[int, str]] = {}
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not line.startswith("#EXT-X-STREAM-INF"):
            continue
        res_m = re.search(r"RESOLUTION=\d+x(\d+)", line)
        if not res_m:
            continue
        bw_m = re.search(r"BANDWIDTH=(\d+)", line)
        # The variant URI is the next non-comment, non-empty line.
        url_line = None
        for j in range(i + 1, len(lines)):
            cand = lines[j].strip()
            if cand and not cand.startswith("#"):
                url_line = cand
                break
        if not url_line:
            continue
        tier = height_to_tier(int(res_m.group(1)))
        bw = int(bw_m.group(1)) if bw_m else 0
        if tier not in variants or bw > variants[tier][0]:
            variants[tier] = (bw, urljoin(base_url, url_line))
    return {tier: url for tier, (_bw, url) in variants.items()}