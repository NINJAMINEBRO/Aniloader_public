"""Grouping animepahe.ch's per-season catalogue entries into one series.

animepahe lists every season as its own entry, the same way anikototv does, so
"Grand Blue Dreaming Season 2" and "Grand Blue Dreaming Season 3" arrive as two
unrelated rows.  Unlike anikototv there is no endpoint to ask: the site is a
WordPress theme with no relation data anywhere on a series page, so the only
thing tying two entries together is how they are named.

That makes the season number itself the interesting part, because animepahe's
catalogue is *sparse*.  It carries whichever seasons it happens to carry: Spy x
Family starts at season 3 with no season 1 or 2 anywhere on the site, and
"+Himitsu no AiPri 3rd Season" sits next to "Himitsu no AiPri" with nothing in
between.  So a season is never renumbered to close a gap - what the site calls
season 3 is offered as season 3, and the seasons missing around it are listed
too, greyed out, so the gap is visible in the picker rather than hidden by
rebasing the list to 1.

Reading the number out of a title is guesswork, so the markers are split by how
much they can be trusted:

*Explicit* - "Season 3", "3rd Season", "Part 2", "Final Season".  Unambiguous,
and trusted even when the entry is alone in the catalogue, which is the common
case here.

*Ambiguous* - a bare trailing number ("Black Butler 2") or a trailing Roman
numeral ("Date A Live V").  These are usually seasons and occasionally part of
the name, so they are bounded: Roman numerals stop at VII, because "To Be Hero
X" is a title and not a tenth season, and bare numbers stop at 20, which keeps
"An Adventurer's Daily Grind at Age 29" intact while still reading the sixteen
seasons of Yamishibai.  Against the 675-entry catalogue this reads 18 of 19
ambiguous titles correctly; the exception is "Thunder 3", a series whose name
ends in a number, which is offered as season 3 of "Thunder".

Qualifiers in brackets are kept apart from the name but not thrown away: a
"(Dub)" or "[Uncensored]" entry is the same season as its plain counterpart, not
a different one, so both appear in the picker under the one season, labelled.
Only a known set is treated this way - a year like "Ranma ½ (2024)" belongs to
the series' identity, and "(And Proud of It)" is simply part of the title.
"""

import re
import unicodedata

import cache_manager
from i18n import tr

# Stored next to the ordinary title cache (as ``animepahe_ch_seasons.json``),
# the arrangement anikototv's season index and hanime's episode index both use.
SEASON_INDEX_SITE = "animepahe.ch_seasons"

# Bracketed words that qualify an entry rather than name it.  Everything else in
# brackets - years, and the handful of titles that genuinely end in a
# parenthetical - is left in the name.
_QUALIFIERS = {"dub", "sub", "subbed", "dubbed", "tv", "uncensored", "censored", "raw"}
_BRACKETED = re.compile(r"[\[(]\s*([^\])]*?)\s*[\])]")

# Of those qualifiers, the ones that name an audio track rather than a cut of
# the show.  A "(Dub)" entry is the same season as its plain counterpart, so it
# is never a season of its own: which of the two a season is taken from is the
# language question, answered by Settings -> Languages, exactly as it is on
# every other site.  The rest ("Uncensored", "TV") really are different versions
# and keep their own row.
SUB = "sub"
DUB = "dub"
_DUB_WORDS = {"dub", "dubbed"}
_SUB_WORDS = {"sub", "subbed"}


def language_of(qualifier: str) -> str:
    """Which audio track *qualifier* names - :data:`DUB` or :data:`SUB`.

    animepahe subtitles everything it does not dub, and marks only the dub, so
    an unmarked entry is the subbed one.
    """
    return DUB if (qualifier or "").strip().lower() in _DUB_WORDS else SUB


def _version(qualifier: str) -> str:
    """The part of *qualifier* that is not about language, e.g. "Uncensored"."""
    text = (qualifier or "").strip()
    return "" if text.lower() in _DUB_WORDS | _SUB_WORDS else text

# "Season 3", optionally introduced by a colon, comma or dash.
_SEASON_WORD = re.compile(r"\s*[:,\-]?\s*\bseason\s*(\d+)\b", re.IGNORECASE)
# "3rd Season", "2nd Season".
_ORDINAL_SEASON = re.compile(r"\s*[:,\-]?\s*\b(\d+)(?:st|nd|rd|th)\s+season\b", re.IGNORECASE)
# "Final Season" / "The Final Season" - a season with no number of its own.
_FINAL_SEASON = re.compile(r"\s*[:,\-]?\s*\b(?:the\s+)?final\s+season\b", re.IGNORECASE)
# "Part 2" / "Cour 2" - a half of a season rather than a season.
_PART = re.compile(r"\s*[:,\-]?\s*\b(?:part|cour)\s*(\d+)\b", re.IGNORECASE)

# Ambiguous markers, and the bounds that keep them from eating real titles.
_ROMAN_TAIL = re.compile(r"\s+(II|III|IV|V|VI|VII)$")
_ROMAN_VALUES = {"II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7}
_DIGIT_TAIL = re.compile(r"\s+(\d{1,2})$")
_MAX_BARE_SEASON = 20

# Sorts after every numbered season, and labels itself.
FINAL = "final"


# ----------------------------------------------------------------------
# Title parsing
# ----------------------------------------------------------------------

def normalise(name: str) -> str:
    """A comparison key for a series name.

    Accents, curly quotes and punctuation are all folded away, because the
    catalogue is inconsistent about them - ``"Oshi no Ko" 2nd Season`` and
    ``[Oshi no Ko] 3rd Season`` are the same show written two ways.
    """
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("’", "'").replace("‘", "'")
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _split_qualifier(title: str) -> "tuple[str, str]":
    """Pull a trailing ``(Dub)``-style qualifier out of *title*.

    Returns ``(title without it, qualifier)``; the qualifier is "" when the
    brackets hold something that belongs to the name.
    """
    for match in reversed(list(_BRACKETED.finditer(title))):
        inner = match.group(1)
        if inner.lower() in _QUALIFIERS:
            remainder = (title[: match.start()] + title[match.end():])
            return re.sub(r"\s{2,}", " ", remainder).strip(), inner
    return title, ""


def parse_title(title: str) -> "tuple[str, int | str | None, int | None, str]":
    """Split *title* into ``(base name, season, part, qualifier)``.

    *season* is an int, :data:`FINAL`, or None when the title names no season -
    which is read as season 1, but only once the whole catalogue has been seen
    (see :func:`build_index`), so that a lone "Black Butler 2" is not forced to
    be season 1 of "Black Butler 2".
    """
    text, qualifier = _split_qualifier(title or "")

    part = None
    match = _PART.search(text)
    if match:
        part = int(match.group(1))
        text = (text[: match.start()] + text[match.end():]).strip()

    season = None
    for pattern in (_SEASON_WORD, _ORDINAL_SEASON):
        match = pattern.search(text)
        if match:
            season = int(match.group(1))
            text = (text[: match.start()] + text[match.end():]).strip()
            break

    if season is None:
        match = _FINAL_SEASON.search(text)
        if match:
            season = FINAL
            text = (text[: match.start()] + text[match.end():]).strip()

    if season is None:
        # Bounded guesses - see the module docstring for why each bound is here.
        match = _ROMAN_TAIL.search(text)
        if match:
            season = _ROMAN_VALUES[match.group(1)]
            text = text[: match.start()].strip()
        else:
            match = _DIGIT_TAIL.search(text)
            if match and 2 <= int(match.group(1)) <= _MAX_BARE_SEASON:
                season = int(match.group(1))
                text = text[: match.start()].strip()

    return text.strip(" :,---"), season, part, qualifier


# ----------------------------------------------------------------------
# Labels and ordering
# ----------------------------------------------------------------------

def season_label(season, part: "int | None" = None, qualifier: str = "") -> str:
    """How one season is named in the pickers, e.g. ``"Season 3: Part 2"``.

    A language qualifier is deliberately left out: sub and dub are the same
    season, and picking between them is the language setting's job, not the
    range selector's.  A qualifier that names a different *cut* - "Uncensored" -
    is kept, because that is a genuinely different version of the episode.
    """
    if season == FINAL:
        label = "Final Season"
    elif isinstance(season, int):
        label = f"Season {season}"
    else:
        label = "Season 1"
    if part:
        label += f": Part {part}"
    version = _version(qualifier)
    if version:
        label += f" ({version})"
    return label


def _sort_key(member) -> tuple:
    """Numbered seasons in order, then Final, then anything unnumbered."""
    season, part, qualifier = member[0], member[1], member[2]
    if isinstance(season, int):
        rank, number = 0, season
    elif season == FINAL:
        rank, number = 1, 0
    else:
        rank, number = 2, 0
    return rank, number, part or 0, qualifier or ""


# ----------------------------------------------------------------------
# Index building and persistence
# ----------------------------------------------------------------------

def build_index(titles: "dict[str, list]") -> "dict[str, list]":
    """Group *titles* (``{url: [title, ...]}``) into ``{entry_url: [members]}``.

    A member is ``[season, part, qualifier, url, title]``.  Only series with
    more than one entry are indexed - a show with a single entry needs no
    grouping, and the page falls back to showing it on its own.  The group is
    keyed by its lowest season, which is the row the search bar will offer.
    """
    grouped: dict[str, list] = {}
    for url, values in titles.items():
        title = values[0] if values else ""
        if not title:
            continue
        base, season, part, qualifier = parse_title(title)
        grouped.setdefault(normalise(base) or normalise(title), []).append(
            [season, part, qualifier, url, title]
        )

    index: dict[str, list] = {}
    for members in grouped.values():
        if len(members) < 2:
            continue
        # An entry that named no season is season 1 of the series it shares a
        # name with - which is only knowable now that the group is assembled.
        for member in members:
            if member[0] is None:
                member[0] = 1
        members.sort(key=_sort_key)
        index[members[0][3]] = members
    return index


def base_name(members) -> str:
    """The series' own name, taken from its lowest season's title.

    The season marker is stripped off, so a group whose only entry is "Spy x
    Family Season 3" is still offered as "Spy x Family" - the season it does and
    does not have belongs in the picker, not in the name.
    """
    if not members:
        return ""
    base, _season, _part, _qualifier = parse_title(members[0][4])
    return base or members[0][4]


def save_index(index: "dict[str, list]") -> None:
    """Persist *index* so the page can expand a series without re-deriving it."""
    cache_manager.save_cache(SEASON_INDEX_SITE, index)


def load_index() -> "dict[str, list]":
    """Return the stored index, or ``{}`` when there isn't one yet."""
    payload = cache_manager.load_cache(SEASON_INDEX_SITE)
    if not payload:
        return {}
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def _clean(members) -> list:
    """Read one stored group back, skipping anything a bad write left malformed."""
    cleaned = []
    for entry in members or []:
        if not isinstance(entry, (list, tuple)) or len(entry) != 5:
            continue
        season, part, qualifier, url, title = entry
        if not isinstance(url, str) or not url:
            continue
        cleaned.append([
            season if isinstance(season, int) or season == FINAL else 1,
            part if isinstance(part, int) else None,
            str(qualifier or ""),
            url,
            str(title or ""),
        ])
    return cleaned


def grouped_away(index: "dict[str, list]") -> "set[str]":
    """Every URL the search bar should stop offering as a row of its own."""
    away: set[str] = set()
    for entry, members in index.items():
        away.update(m[3] for m in _clean(members) if m[3] != entry)
    return away


def seasons_for_url(url: str) -> list:
    """The stored group the series *url* belongs to, or ``[]``.

    Any member answers with the whole group, so a link pasted for season 3 opens
    the same page as the row picked from the search bar.
    """
    url = (url or "").rstrip("/")
    if not url:
        return []

    index = load_index()
    for candidate in (url, url + "/"):
        members = _clean(index.get(candidate))
        if members:
            return members

    for members in index.values():
        cleaned = _clean(members)
        if any(m[3].rstrip("/") == url for m in cleaned):
            return cleaned
    return []


# ----------------------------------------------------------------------
# Gaps
# ----------------------------------------------------------------------

def _slug(url: str) -> str:
    """The last path segment of *url* - what distinguishes two look-alike entries."""
    return (url or "").rstrip("/").rsplit("/", 1)[-1]


def season_slots(members, languages=(SUB,)) -> list:
    """The season picker's rows: what the site has, and what it is missing.

    Returns ``[[label, url, title, available, language, version, has], ...]``
    in season order, where *has* lists the audio tracks the site carries for
    that season.  There is one row per season - never one per audio track.
    *languages* is the user's enabled languages as :data:`SUB`/:data:`DUB`
    codes, most-wanted first; each season is taken from the first of those it
    actually has, and *language* says which one that turned out to be.

    Every numbered season up to the highest the site carries is accounted for,
    so a series that starts at season 3, or skips season 2, says so in the list
    instead of quietly renumbering what is there.  A season the site has only in
    a language that is switched off is a hole too, and is reported as one -
    ``language`` is None on those rows.  Unavailable rows carry no URL and are
    shown disabled.

    A run of missing seasons collapses into one row ("Seasons 1-13"), because
    animepahe sometimes joins a long-running series near the end - Yamishibai
    starts at season 14 - and thirteen identical rows would bury the three that
    can actually be picked.

    Two rows can still land on the same label: animepahe lists a few shows
    twice, once under each of their names, and marks an uncensored cut only in
    the slug.  Those are told apart by that slug rather than silently stacked.
    """
    members = list(members)
    if not members:
        return []

    wanted = [code for code in languages if code in (SUB, DUB)] or [SUB]

    # One slot per (season, part, version), with that season's audio tracks
    # inside it.  A track that is already taken starts a new slot instead of
    # overwriting: animepahe lists a few shows twice under different names, and
    # those are two real pages, not one page's sub and dub.
    slots: list = []
    for season, part, qualifier, url, title in members:
        identity = (season if isinstance(season, int) else str(season),
                    part or 0, _version(qualifier).lower())
        language = language_of(qualifier)
        slot = next(
            (s for s in slots
             if s["identity"] == identity and language not in s["tracks"]),
            None,
        )
        if slot is None:
            slot = {"identity": identity, "season": season, "part": part,
                    "qualifier": qualifier, "tracks": {}}
            slots.append(slot)
        slot["tracks"][language] = (url, title)

    present = {s["season"] for s in slots if isinstance(s["season"], int)}
    highest = max(present) if present else 0

    def rows_for(slot) -> list:
        label = season_label(slot["season"], slot["part"], slot["qualifier"])
        has = sorted(slot["tracks"])
        for code in wanted:
            if code in slot["tracks"]:
                url, title = slot["tracks"][code]
                return [label, url, title, True, code, _version(slot["qualifier"]), has]
        # The season is here, but only in a language that is switched off.
        return [label, "", "", False, None, _version(slot["qualifier"]), has]

    rows: list = []
    missing_run: list[int] = []

    def flush_missing():
        if not missing_run:
            return
        first, last = missing_run[0], missing_run[-1]
        # The season names stay English like every season label here (they are
        # the download folders' names); only the note after them is translated.
        name = f"Season {first}" if first == last else f"Seasons {first}-{last}"
        rows.append([f"{name} - {tr('not on animepahe')}", "", "", False, None, "", []])
        missing_run.clear()

    for number in range(1, highest + 1):
        if number in present:
            flush_missing()
            for slot in slots:
                if slot["season"] == number:
                    rows.append(rows_for(slot))
        else:
            missing_run.append(number)
    flush_missing()

    # Final Season, and anything that never carried a number, come last.
    for slot in slots:
        if not isinstance(slot["season"], int):
            rows.append(rows_for(slot))

    seen: dict = {}
    for row in rows:
        seen[row[0]] = seen.get(row[0], 0) + 1
    for row in rows:
        if row[3] and seen[row[0]] > 1:
            row[0] = f"{row[0]}  [{_slug(row[1])}]"
    return rows


def missing_summary(members) -> str:
    """One line naming the seasons the site does not carry, or "" when it has all.

    Shown above the pickers so the gaps are stated as well as drawn, with runs
    written as ranges to match the rows in :func:`season_slots`.
    """
    present = sorted({m[0] for m in members if isinstance(m[0], int)})
    if not present:
        return ""
    missing = [n for n in range(1, present[-1] + 1) if n not in present]
    if not missing:
        return ""

    runs: list[list[int]] = []
    for number in missing:
        if runs and number == runs[-1][-1] + 1:
            runs[-1].append(number)
        else:
            runs.append([number])

    listed = ", ".join(
        str(run[0]) if len(run) == 1 else f"{run[0]}-{run[-1]}" for run in runs
    )
    if len(missing) == 1:
        return tr("animepahe does not have season {seasons}", seasons=listed)
    return tr("animepahe does not have seasons {seasons}", seasons=listed)
