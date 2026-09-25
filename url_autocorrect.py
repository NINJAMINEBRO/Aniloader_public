"""Repair series links that were typed by hand in the main entry.

Small mistakes make a link fail even though what the user meant is obvious: a
missing ``https://``, a stray quote dragged along by a copy-paste, ``aniworld.tv``
for ``aniworld.to``, a lower-cased bs.to slug (whose slugs carry capitals), or an
episode URL pasted where the series URL belongs.  :func:`autocorrect` recognises
those cases and hands back the link that was meant, so the caller can open it
instead of showing "Invalid URL".

Repairs come in two flavours:

*Deterministic* - the fix follows from the text itself, or from an exact
(case-insensitive) hit in the cached title list. These are always applied.

*Fuzzy* - the slug is close to exactly one known series. These need a high
similarity score, and are refused outright when two slugs differ only by a
trailing number: that is how sequels are named (``kaiju-no-8`` beside
``kaiju-no-9``), and guessing between them would quietly download the wrong show.

The cached titles are what make slug repairs possible. For a site with no cache
loaded only the text-level fixes apply, which is the honest outcome - there is
nothing to check a slug against.
"""

import re
from difflib import get_close_matches
from typing import NamedTuple
from urllib.parse import urlparse, urlunparse

import site_mirrors


class Correction(NamedTuple):
    """A repaired link, plus a short note on what was changed."""

    url: str
    reason: str


# The path each site puts in front of its series slug.  Only consulted when the
# site has no cached titles; with a cache loaded the real URLs are matched
# directly, which is both stricter and always up to date.
SITE_PATH_PREFIX: dict[str, str] = {
    "aniworld.to": "/anime/stream/",
    "s.to": "/serie/",
    "bs.to": "/serie/",
    "anikototv.to": "/watch/",
    "hanime.tv": "/videos/hentai/",
    "animepahe.ch": "/series/",
}

# How close a mistyped slug must be to a known one before it is accepted…
_SLUG_CUTOFF = 0.86
# …and how close a mistyped hostname must be to one of the supported sites.
_HOST_CUTOFF = 0.75

# A leading "scheme://" - or "scheme:/", or "scheme:///", however it was typed.
# A slash after the colon is required so that a host:port is never mistaken for
# a scheme and stripped.
_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:/+")
# Characters a copy-paste tends to wrap a link in…
_WRAPPING = "<>\"'`«»()[]{} \t\r\n"
# …and punctuation it tends to leave hanging off the end.
_TRAILING_JUNK = ".,;:!?"
# Trailing digits: how sequels are numbered.
_TRAILING_NUMBER_RE = re.compile(r"\d+$")


# ----------------------------------------------------------------------
# Text-level tidying
# ----------------------------------------------------------------------

def _strip_wrapping(raw: str) -> str:
    """Drop quotes, brackets and trailing punctuation left by a copy-paste."""
    text = raw.strip()
    while text and text[0] in _WRAPPING:
        text = text[1:]
    while text and (text[-1] in _WRAPPING or text[-1] in _TRAILING_JUNK):
        text = text[:-1]
    return text


def _looks_like_link(text: str) -> bool:
    """True when *text* is an attempt at a link rather than a series name.

    A bare title belongs to the search bar's suggestion list; rewriting one into
    a URL here would hijack the entry's other job, so it is left alone.
    """
    if not text:
        return False
    head = _SCHEME_RE.sub("", text).split("/", 1)[0]
    return "." in head and " " not in head


def _build(host: str, path: str, query: str = "", fragment: str = "") -> str:
    return urlunparse(("https", host, path, "", query, fragment))


def _normalise(text: str) -> tuple[str, str, str, str] | None:
    """Split *text* into ``(host, path, query, fragment)``, or None if unusable.

    The scheme the user typed is discarded rather than repaired - every
    supported site serves https, so there is only one right answer.  The host is
    lower-cased and stripped of ``www.``; the path is left exactly as typed,
    because bs.to slugs are capitalised and lowering them would break links that
    were already correct.
    """
    body = _SCHEME_RE.sub("", text).lstrip("/")
    if not body:
        return None
    try:
        parsed = urlparse("https://" + body)
        host = (parsed.hostname or "").lower().removeprefix("www.")
    except ValueError:
        return None
    if not host:
        return None
    return host, parsed.path.rstrip("/"), parsed.query, parsed.fragment


def _correct_host(host: str) -> str | None:
    """Map *host* onto a supported site, allowing for a typo.  None if too far off.

    Backup domains are matched as readily as the primaries, but the answer is
    always the primary: it is what the cached links, the settings and the page
    routing are keyed on, and site_mirrors swaps it back to whichever domain is
    actually up when the request goes out.  So a typo'd ``burningserie.cx``
    still ends up on the bs.to page.
    """
    supported = sorted(site_mirrors.all_hosts())
    if host in supported:
        return site_mirrors.canonical(host)
    match = get_close_matches(host, supported, n=1, cutoff=_HOST_CUTOFF)
    return site_mirrors.canonical(match[0]) if match else None


# ----------------------------------------------------------------------
# Slug repair against the cached title list
# ----------------------------------------------------------------------

def _slug(url_or_path: str) -> str:
    """The last path segment - the part that names the series."""
    return url_or_path.rstrip("/").rsplit("/", 1)[-1]


def _is_sequel_pair(typed: str, match: str) -> bool:
    """True when two slugs differ only by a trailing number.

    ``kaiju-no-8`` and ``kaiju-no-9`` are different shows that score as an
    almost perfect fuzzy match, so a pair shaped like this is never corrected -
    the user gets "Invalid URL" and picks the right one themselves, which beats
    silently queueing a season of the wrong series.
    """
    return typed != match and (
        _TRAILING_NUMBER_RE.sub("", typed) == _TRAILING_NUMBER_RE.sub("", match)
    )


def _repair_path(url: str, path: str, candidates: list[str]) -> tuple[str, str] | None:
    """Map *url* - which is not itself a known link - onto one that is.

    Ordered most certain first, so a fuzzy guess is only ever reached once every
    exact reading of the link has been ruled out.
    """
    lowered = url.lower()

    # 1. A season or episode page pasted where the series page belongs - the
    #    series URL is a prefix of it, so trimming back is exact, not a guess.
    for candidate in candidates:
        if lowered.startswith(candidate.lower() + "/"):
            return candidate, "trimmed it to the series page"

    typed_slug = _slug(path).lower()
    if not typed_slug:
        return None

    # 2. Right series name, wrong (or missing) path in front of it.
    slugs: dict[str, str] = {}
    for candidate in candidates:
        slugs.setdefault(_slug(candidate).lower(), candidate)
    if typed_slug in slugs:
        return slugs[typed_slug], "fixed the link path"

    # 3. The slug is the start of exactly one known slug.  anikototv.to appends
    #    a short random id to every slug, which nobody types from memory.
    starts = [url_ for slug, url_ in slugs.items() if slug.startswith(typed_slug + "-")]
    if len(starts) == 1:
        return starts[0], "completed the series id"

    # 4. Last resort: the closest known slug, if it is close enough to trust.
    match = get_close_matches(typed_slug, list(slugs), n=1, cutoff=_SLUG_CUTOFF)
    if match and not _is_sequel_pair(typed_slug, match[0]):
        return slugs[match[0]], "corrected the series name"
    return None


def _describe_text_fix(raw: str, host_was_corrected: bool) -> str:
    """Name the text-level change made to *raw*.

    Used as the starting reason, and kept only when no slug repair replaces it -
    so what it describes is always the address itself rather than which series
    the link points at.  Several fixes can apply at once; the most surprising
    one is reported.
    """
    text = raw.strip()
    if host_was_corrected:
        return "corrected the site address"
    if _strip_wrapping(text) != text:
        return "removed stray characters"
    if not _SCHEME_RE.match(text):
        return "added the missing https://"
    if text.lower().startswith("http://"):
        return "switched it to https"
    if "//www." in text.lower():
        return "dropped the www."
    return "tidied up the address"


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------

def autocorrect(raw: str, known_urls: dict[str, str] | None = None) -> Correction | None:
    """Return the link *raw* was meant to be, or None to leave it alone.

    None covers three cases that all mean "don't touch it": the text already
    points at a working link, it is not a link at all, or nothing could be
    repaired with enough confidence to be worth doing silently.

    Parameters
    ----------
    raw:
        Whatever the user typed into the main entry.
    known_urls:
        The ``{url: site}`` map of every cached series link (the main menu's
        ``_url_to_site``).  Optional: without it, only the text-level fixes
        apply, since there is nothing to check a slug against.
    """
    text = _strip_wrapping(raw or "")
    if not _looks_like_link(text):
        return None

    parts = _normalise(text)
    if parts is None:
        return None
    host, path, query, fragment = parts

    corrected_host = _correct_host(host)
    if corrected_host is None:
        return None                       # not one of our sites, nor close to one
    host_was_corrected = corrected_host != host
    host = corrected_host

    url = _build(host, path, query, fragment)
    reason = _describe_text_fix(raw, host_was_corrected)

    candidates = [u for u, site in (known_urls or {}).items() if site == host]
    if candidates:
        canonical = {c.lower(): c for c in candidates}.get(url.lower())
        if canonical is not None:
            # Already a real link - at most the capitalisation is off, which
            # matters because bs.to slugs carry capitals.
            if canonical != url:
                reason = "fixed the capitalisation"
                url = canonical
        else:
            repair = _repair_path(url, path, candidates)
            if repair is not None:
                url, reason = repair
    elif path.strip("/") and "/" not in path.strip("/") and host in SITE_PATH_PREFIX:
        # A bare slug and no cached titles to check it against: put the site's
        # series path in front so the link at least has the right shape, and let
        # the site page report it if the slug itself turns out to be wrong.
        url = _build(host, SITE_PATH_PREFIX[host] + path.strip("/"), query, fragment)
        reason = "fixed the link path"

    if url == raw:
        return None                       # already exactly right - nothing to do
    return Correction(url, reason)