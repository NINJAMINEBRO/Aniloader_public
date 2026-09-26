"""Grouping hanime.tv's flat video list into series.

hanime.tv publishes every episode as its own video with no series metadata
anywhere - "succubus-connect-1" and "succubus-connect-2" are unrelated as far
as the site is concerned.  The trailing number in a slug is the only thing
tying them together, so that is what this module keys on: strip it and what
remains names the series.

Measured against the full catalogue (3395 videos) this yields 1559 series with
no episode number claimed twice, so the rule is taken as reliable rather than
guarded with tie-breaking that would never run.

Both the catalogue fetcher and the hanime page need this identically - one to
collapse the search bar down to series, the other to expand a series back into
its episodes - which is why it lives here instead of in either of them.  The
episode index is written alongside the title cache so the page can expand a
series without going back to the network.
"""

import re

import cache_manager

VIDEO_BASE = "https://hanime.tv/videos/hentai/"

# Stored next to the ordinary title cache (as ``hanime_tv_episodes.json``).  It
# is written whenever the catalogue is fetched, whether or not title caching is
# enabled for the site, because the page depends on it to offer a range at all.
EPISODE_INDEX_SITE = "hanime.tv_episodes"

# Greedy on purpose: the *last* number in a slug is the episode, so
# "15-bishoujo-hyouryuuki-1" is episode 1 of "15-bishoujo-hyouryuuki" rather
# than episode 15 of something.  A slug with no trailing number is a series of
# one and keeps its own name.
_TRAILING_NUMBER = re.compile(r"^(?P<stem>.+)-(?P<number>\d+)$")


def slug_from_url(url: str) -> str:
    """Return the video slug in *url*, or "" when it isn't a video link."""
    if not url or VIDEO_BASE not in url:
        return ""
    tail = url.split(VIDEO_BASE, 1)[1]
    slug = tail.split("?", 1)[0].split("#", 1)[0].strip("/")
    # A slug is a single path segment; anything deeper is some other page.
    return slug if slug and "/" not in slug else ""


def url_for_slug(slug: str) -> str:
    """The canonical video URL for *slug*."""
    return VIDEO_BASE + slug


def split_slug(slug: str) -> "tuple[str, int]":
    """Split *slug* into ``(series_slug, episode_number)``."""
    match = _TRAILING_NUMBER.match(slug)
    if not match:
        return slug, 1
    return match.group("stem"), int(match.group("number"))


def title_from_slug(slug: str) -> str:
    """Human-readable title for *slug* ("succubus-connect" -> "Succubus Connect")."""
    return slug.replace("-", " ").title()


def group_slugs(slugs) -> "dict[str, list[tuple[int, str]]]":
    """Group video *slugs* into ``{series_slug: [(episode_number, slug), ...]}``.

    Each series' episodes come back in episode order.
    """
    grouped: dict[str, list[tuple[int, str]]] = {}
    for slug in slugs:
        series_slug, number = split_slug(slug)
        grouped.setdefault(series_slug, []).append((number, slug))

    for episodes in grouped.values():
        episodes.sort()
    return grouped


# ----------------------------------------------------------------------
# Episode index persistence
# ----------------------------------------------------------------------

def save_index(grouped: "dict[str, list[tuple[int, str]]]") -> None:
    """Persist *grouped* so the page can expand a series offline."""
    cache_manager.save_cache(
        EPISODE_INDEX_SITE,
        {series: [[number, slug] for number, slug in episodes]
         for series, episodes in grouped.items()},
    )


def load_index() -> "dict[str, list[tuple[int, str]]]":
    """Return the stored episode index, or ``{}`` when there isn't one yet."""
    payload = cache_manager.load_cache(EPISODE_INDEX_SITE)
    if not payload:
        return {}

    index: dict[str, list[tuple[int, str]]] = {}
    for series, episodes in (payload.get("data") or {}).items():
        # Written as JSON lists; a hand-edited or truncated entry is skipped
        # rather than allowed to break the page that reads it.
        cleaned = [
            (int(entry[0]), str(entry[1]))
            for entry in episodes
            if isinstance(entry, (list, tuple)) and len(entry) == 2
        ]
        if cleaned:
            index[series] = sorted(cleaned)
    return index


def episodes_for_url(url: str) -> "list[tuple[int, str]]":
    """Every ``(episode_number, slug)`` of the series *url* belongs to.

    Falls back to the single video in *url* when the index is missing or does
    not know it, so a page opened before the catalogue was ever fetched still
    offers that one episode instead of nothing.
    """
    slug = slug_from_url(url)
    if not slug:
        return []

    series_slug, number = split_slug(slug)
    episodes = load_index().get(series_slug)
    if episodes:
        return episodes
    return [(number, slug)]
