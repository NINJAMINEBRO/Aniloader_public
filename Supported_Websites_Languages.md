# Supported Websites, Languages & Subtitles

Which languages and subtitles you can actually download from each supported website.
Languages are turned on and ordered in **Settings → Languages**; a website simply skips
any language it does not offer, so having extra ones enabled never breaks a download.

*Current for Aniloader 0.4 Open Beta.*

---

## aniworld.to

**Languages**
- German Dub
- Japanese · German Sub
- Japanese · English Sub

**Subtitles**
The subtitles are part of the video itself, so there is no separate subtitle file and
nothing to pick. You choose the sub language by choosing the language variant, for
example *Japanese · German Sub*.

---

## s.to

**Languages**
- German Dub
- English Dub
- Japanese · German Sub

**Subtitles**
Part of the video, same as aniworld.to. No separate subtitle file.

---

## bs.to

**Languages**
- German Dub
- English Dub
- Japanese · German Sub
- Japanese · English Sub

**Subtitles**
Part of the video, same as aniworld.to. No separate subtitle file.

---

## anikototv.to

**Languages**
- English Dub
- Japanese · English Sub
- Japanese · Portuguese (Brazil) Sub
- Japanese · Spanish Sub
- Japanese · Spanish (Latin America) Sub
- Japanese · German Sub
- Japanese · French Sub
- Japanese · Indonesian Sub
- Japanese · Thai Sub
- Japanese · Vietnamese Sub

**Subtitles**
Together with animepahe.ch this website has real, selectable subtitle tracks, and what
you get depends on which provider the episode is downloaded from:

- **Vidstream**: the sub language is embedded into the video as its default subtitle
  track *and* saved as an `.srt` file with the same name next to the video, so players
  that ignore built-in tracks (Windows Media Player among them) still show it.
  Available tracks: English, Portuguese (Brazil), Spanish, Spanish (Latin America),
  German, French, Indonesian, Thai, Vietnamese.
- **Kiwi-Stream**: subtitles are burned into the video and are always English. The
  other sub languages are never served here.

A non-English sub language is only downloaded when that episode actually offers the
track. If it does not, that combination is skipped and the next enabled
language/provider is tried, so you never get an episode with the wrong subtitles.

---

## animepahe.ch
**WARNING: CAN BE EXTREMELY SLOW**

**Languages**
- Japanese · English Sub
- English Dub
- Japanese · German Sub
- Japanese · French Sub
- Japanese · Indonesian Sub
- Japanese · Thai Sub
- Japanese · Vietnamese Sub
- Japanese · Portuguese (Brazil) Sub
- Japanese · Spanish Sub
- Japanese · Spanish (Latin America) Sub

**Subtitles**
What you get depends on which of the two kinds of episode page a show has:

- **Vidstream** (the MegaPlay player, most shows): works exactly like Vidstream on
  anikototv.to - the sub language is embedded as a subtitle track and saved as an `.srt`
  next to the video. Which tracks exist depends on the show, from English alone to all
  of the languages above.
- **Kiwi-Stream** and **Blogger** (shows with a download box under a Blogger player):
  subtitles are burned into the video and are always English.

Dubs are listed on the site as their own "(Dub)" entries. Each season is taken subbed or
dubbed, whichever comes first in your language order and exists for it. As on
anikototv.to, a non-English sub language is only downloaded when the episode actually
offers the track.

---

## hanime.tv

**Languages**
- Japanese · English Sub

**Subtitles**
English subtitles are part of the video. The site offers no language choice at all.

**Note:** The site serves 720p at most, so a 1080p setting
cannot be fulfilled here. That is a limit of the website, not a failed download.

---

## Notes

- A language must be enabled in **Settings → Languages** before any website will use it.
  The order of that list is the order in which languages are attempted.
- "Jap · … Sub" means the Japanese audio track with subtitles in the named language.
- Not every episode carries every language, even on a website that supports it. Missing
  combinations are skipped automatically and reported in the download log.
