"""hanime.tv downloader.

hanime.tv hands its player a stream manifest through a signed handshake rather
than putting URLs in the page, so there are three steps between a video URL and
something ffmpeg can read:

1. A signature.  The site's player computes ``window.ssignature`` /
   ``window.stime`` from a WASM bundle.  Reproducing that in Python is not
   realistic, so the values are read out of a real page in the undetected
   browser this project already uses for Cloudflare elsewhere.
2. A handshake.  ``POST /api/v11/handshake`` with an AES-256-GCM encrypted
   payload naming the video slug; the reply carries an ``X-Token`` header
   encrypted under the same key, which decrypts to the manifest.
3. The manifest lists one HLS playlist per tier, which ffmpeg can mux directly.

Two things make this cheap enough to use per episode.  A signature is *not*
bound to the slug it was minted on - one covers any number of videos - so the
browser runs once per batch instead of once per episode, and both the signature
and each slug's manifest are cached for the worker's repeated per-tier calls.

Guests are served 720p at best: the manifest still lists 1080p but with an empty
``src`` and ``kind`` of "promotion", which is the site withholding it rather
than anything this module can unlock.  Those entries are filtered out, so a
1080p request finds no match and returns False - the same "tier not offered"
signal VOE gives - and the worker falls back to 720p on its own.
"""

import json
import threading
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from os import urandom
from urllib.parse import urljoin

from Crypto.Cipher import AES

from downloaders import common

HOST = "https://hanime.tv"
HANDSHAKE_URL = "https://auth.hanime.tv/api/v11/handshake"
_VIDEO_PATH = "/videos/hentai/"

# Key and associated-data for the handshake envelope.  Both are fixed client-side
# constants of the player; the site's own name for the scheme is the AAD below.
_AES_KEY = bytes.fromhex(
    "5d657a4dcb0bad1c637ff2e221059b10ff17ae39fe855003e846918941f4ebe3"
)
_AES_AAD = b"htv-insecure-v1"

# How long a minted signature is reused before the browser is asked for another.
# The real lifetime isn't advertised, so this is deliberately short of any
# plausible one; an expired signature is also recovered from at the point of
# failure, which is what actually guarantees correctness here.
_SIGNATURE_TTL = 600.0

# Sources the site marks as anything but "normal" (currently "promotion") are
# placeholders with no URL behind them.
_GUEST_KIND = "normal"

_creds_lock = threading.Lock()
_creds: "tuple[str, int, float] | None" = None   # (signature, stime, minted_at)

_manifest_lock = threading.Lock()
_manifests: "dict[str, dict]" = {}


# ----------------------------------------------------------------------
# URL helpers
# ----------------------------------------------------------------------

def slug_from_url(url: str) -> "str | None":
    """Return the video slug in *url*, or None when it isn't a video link."""
    if not url or _VIDEO_PATH not in url:
        return None
    tail = url.split(_VIDEO_PATH, 1)[1]
    slug = tail.split("?", 1)[0].split("#", 1)[0].strip("/")
    # A slug is a single path segment; anything deeper is some other page.
    return slug if slug and "/" not in slug else None


def _label_height(label: str) -> int:
    """Numeric height behind a tier label like ``"720p"`` (0 when unparsable)."""
    digits = "".join(ch for ch in label if ch.isdigit())
    return int(digits) if digits else 0


# ----------------------------------------------------------------------
# Handshake envelope
# ----------------------------------------------------------------------

def _b64url_encode(raw: bytes) -> str:
    return urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return urlsafe_b64decode(text + padding)


def _encrypt_token(payload: dict) -> str:
    """Wrap *payload* in the AES-256-GCM envelope the handshake expects."""
    nonce = urandom(12)
    cipher = AES.new(_AES_KEY, AES.MODE_GCM, nonce=nonce)
    cipher.update(_AES_AAD)
    body, tag = cipher.encrypt_and_digest(
        json.dumps(payload, separators=(",", ":")).encode()
    )
    envelope = {
        "v": 1,
        "alg": "AES-256-GCM",
        "iv": _b64url_encode(nonce),
        "tag": _b64url_encode(tag),
        "data": _b64url_encode(body),
    }
    return _b64url_encode(json.dumps(envelope, separators=(",", ":")).encode())


def _decrypt_token(token: str) -> dict:
    """Unwrap an ``X-Token`` response envelope into the manifest it carries."""
    envelope = json.loads(_b64url_decode(token))
    cipher = AES.new(_AES_KEY, AES.MODE_GCM, nonce=_b64url_decode(envelope["iv"]))
    cipher.update(_AES_AAD)
    plain = cipher.decrypt_and_verify(
        _b64url_decode(envelope["data"]), _b64url_decode(envelope["tag"])
    )
    return json.loads(plain.decode())


# ----------------------------------------------------------------------
# Signature minting (the only step that needs a browser)
# ----------------------------------------------------------------------

def _mint_credentials() -> "tuple[str, int] | None":
    """Read a fresh ``ssignature``/``stime`` pair out of a real page.

    Any page carrying the player bundle will do - the signature is not tied to
    the slug it came from - so the front page is used and nothing is played.
    """
    from seleniumbase import SB  # imported lazily - heavy and browser-dependent

    try:
        with SB(uc=True, headless2=True) as sb:
            sb.uc_open_with_reconnect(HOST, reconnect_time=6)
            # The signature appears only once the player bundle has run; poll
            # rather than sleeping a fixed span so a fast load isn't penalised.
            for _ in range(20):
                if common.is_cancelled():
                    return None
                found = sb.execute_script(
                    "return (typeof window.ssignature !== 'undefined'"
                    " && typeof window.stime !== 'undefined')"
                    " ? [String(window.ssignature), String(window.stime)] : null;"
                )
                if found:
                    return found[0], int(found[1])
                sb.sleep(1)
    except Exception as exc:
        if "Chrome not found" in str(exc):
            print("[hanime] Chrome must be installed to download from hanime.tv.")
        else:
            print(f"[hanime] could not obtain a signature: {exc}")
    return None


def _credentials(refresh: bool = False) -> "tuple[str, int] | None":
    """Return cached credentials, minting new ones when stale or *refresh*."""
    global _creds
    with _creds_lock:
        if not refresh and _creds is not None:
            signature, stime, minted_at = _creds
            if time.time() - minted_at < _SIGNATURE_TTL:
                return signature, stime

        minted = _mint_credentials()
        if minted is None:
            # Leave any existing pair in place: a failed refresh (no Chrome, a
            # transient block) shouldn't discard credentials that still work.
            return None if _creds is None else _creds[:2]

        _creds = (minted[0], minted[1], time.time())
        return minted


# ----------------------------------------------------------------------
# Manifest retrieval
# ----------------------------------------------------------------------

def _handshake(slug: str, signature: str, stime: int) -> "dict | None":
    """Perform one handshake for *slug*; None when it is rejected."""
    payload = {
        "timestamp_unix": int(time.time()),
        "directive": "htv_player_handshake",
        "slug": slug,
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": HOST,
        "Referer": HOST + "/",
        "User-Agent": common.USER_AGENT,
        "X-Csrf-Token": "null",
        "X-Signature": signature,
        "X-Time": str(stime),
        "X-Signature-Version": "web2",
    }
    try:
        response = common._session().post(
            HANDSHAKE_URL,
            json={"token": _encrypt_token(payload)},
            headers=headers,
            timeout=30,
        )
    except Exception as exc:
        print(f"[hanime] handshake request failed for {slug}: {exc}")
        return None

    token = response.headers.get("X-Token")
    if response.status_code != 200 or not token:
        return None
    try:
        return _decrypt_token(token)
    except Exception as exc:
        # A key rotation lands here: the envelope arrives but no longer opens.
        print(f"[hanime] could not decrypt the manifest for {slug}: {exc}")
        return None


def fetch_manifest(slug: str) -> "dict | None":
    """Return the stream manifest for *slug*, cached per slug.

    A rejected handshake is retried once against a freshly minted signature,
    which is what recovers from an expired one without having to know its real
    lifetime.
    """
    with _manifest_lock:
        cached = _manifests.get(slug)
    if cached is not None:
        return cached

    for refresh in (False, True):
        if common.is_cancelled():
            return None
        creds = _credentials(refresh=refresh)
        if creds is None:
            return None
        manifest = _handshake(slug, creds[0], creds[1])
        if manifest is not None:
            with _manifest_lock:
                _manifests[slug] = manifest
            return manifest

    print(f"[hanime] handshake rejected for {slug}")
    return None


def guest_sources(manifest: dict) -> "dict[str, str]":
    """Map ``{tier_label: absolute_stream_url}`` for guest-playable sources.

    Entries the site lists without a URL (its withheld premium tiers) are left
    out, so a request for one of those finds nothing rather than appearing to
    succeed and handing ffmpeg an empty string.
    """
    sources: dict[str, str] = {}
    for source in manifest.get("sources") or []:
        src = (source.get("src") or "").strip()
        if not src or source.get("kind") not in (_GUEST_KIND, None):
            continue
        label = (source.get("label") or "").strip()
        if not label:
            height = str(source.get("height") or "").strip()
            if not height:
                continue
            label = f"{height}p"
        # Keep the first URL seen for a tier: the manifest lists them best-first.
        sources.setdefault(label, urljoin(HOST, src))
    return sources


def _resolve_target_url(url: str, quality: "str | None") -> "str | None":
    """Resolve *url* to the stream for *quality*.

    Returns None when the tier isn't offered, which tells the worker to fall
    back rather than accept a different resolution than it asked for.
    """
    slug = slug_from_url(url)
    if not slug:
        print(f"[hanime] not a hanime video URL: {url}")
        return None

    manifest = fetch_manifest(slug)
    if manifest is None:
        return None

    sources = guest_sources(manifest)
    if not sources:
        print(f"[hanime] no guest-playable stream for {slug}")
        return None

    if quality:
        return sources.get(quality)

    # No tier requested: take the best on offer.
    return sources[max(sources, key=_label_height)]


# ----------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------

def download(url, download_path, file_name, quality=None):
    """Download one hanime.tv video; False on any failure."""
    try:
        if common.is_cancelled():
            return False

        target = _resolve_target_url(url, quality)
        if not target:
            return False

        return common.run_ffmpeg(target, download_path, file_name, referer=HOST + "/")
    except Exception as exc:  # never let a provider crash the worker
        print(f"[hanime] error for {url}: {exc}")
        return False
