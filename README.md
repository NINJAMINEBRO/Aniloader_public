**Handbook for Aniloader ver 0.5 Open Beta**

*I might forget to update this for some versions, but it shouldn't really change much. If you have any*

*questions on this program, just message me via discord.*



Aniloader by NMB is a anime/series/movies downloader that supports various websites.

To properly use this program, I have made this "Handbook" in which I try to explain the features and how to use them



**Main page features:**

Main entry where series links from supported websites can be pasted into,

this is also a search bar if a Search bar is enabled for at least 1 website.

If a search bar is enabled the results will be shown directly below the entry with suggestion

that can be selected with a simple click on them, which will paste the correct link into the entry.

Pressing confirm validates the link and gets all the available info for that anime+website combination

in the background and builds the download page.

Links you type by hand get corrected automatically when they would not work and the fix is obvious:

a missing https://, a leftover quote or bracket from a copy-paste, a wrong domain ending,

the wrong upper/lower case, or an episode link where the series link belongs.

If the series name itself is only slightly misspelled it is matched against the titles

of that website, so this works best with a search bar enabled for it.

The corrected link is put back into the entry so you always see what is actually being opened.

Sequels that only differ by a number at the end are never guessed between, so for those

you get the normal Invalid URL and pick the right one yourself.

The settings button in the top right corner takes you to the settings page.

An update button appears left of it whenever a newer version has been published,

it stays hidden when you are already on the newest one. It shows the build number

you would move to, and hovering it tells you which build you are on right now.

Clicking it asks you to confirm, then downloads the new version, starts it and closes

the old one, the old version is deleted automatically the next time the program starts.

Your settings, downloads (by standard) and the ffmpeg files sit next to the program and are never

touched by an update. Downloads that are still running are cancelled by the restart,

so it warns you first and tells you how many would be lost, part finished episodes are

deleted and can simply be queued again afterwards.

If the check cannot reach GitHub nothing is shown at all, the program just carries on.



**Settings page features:**

The settings page is split into 5 Tabs.

***General:***

Here the you can set settings that I consider general.

App language sets the language of the program itself: English (the default), German, Spanish, French,

Portuguese (Brazil), Vietnamese, Indonesian or Thai. Every language is listed under its own name so you can always

find your way back. The new language is used from the next start of the program, a note under the selection reminds you.

Series, season and episode names from the websites and the names of your downloaded folders and files are never translated.

Max quality and Min quality set the resolution range you are willing to download.

Every episode is attempted at the max quality first and then steps down one tier

at a time, stopping at the min quality. Anything below the min is never downloaded,

so if an episode is only offered below that floor it will fail instead. Leaving

Min quality at 360p keeps the old behaviour of always taking whatever is available.

Setting both to the same tier means only that exact resolution is accepted.

Shutdown when done will turn off the PC after all downloads have finished.

One minute before, a window pops up on top of everything, even a game running in fullscreen,

with a button to cancel the shutdown. Closing that window or doing nothing lets the PC shut down as planned.

Keys do nothing in that window, so it can only be cancelled or closed with a click, not by accident while typing or playing.

Simultaneous DLs can be increased up to 20 and tells the program how many downloads can run at once

setting this to high with a slow internet connection is not recommended. try to find a sweet spot for

the website and provider you usually download from.

Download delay is how many seconds the queue waits between starting one episode and the next.

Some providers rate limit when too many requests arrive in quick succession, so the starts are

spaced out even when Simultaneous DLs would allow several at the same moment. This only delays

the start of a download, downloads that are already running keep going in the background.

The default is 2 seconds, it can be set up to 300 and setting it to 0 starts everything as fast

as the Simultaneous DLs limit allows. Raise it if a provider keeps rate limiting you.

Retries is how often an episode that found no working combination is sent to the back of

the queue and tried again. Whatever made it fail, a provider having a bad minute or a host rate

limiting you, has usually passed by the time the rest of the queue has been worked through.

The default is 1 and it can be set from 0, which gives up on the first failure, up to 5. An

episode waiting for another attempt is shown in the Pending panel with a (retry n/m) marker.

Set Download Path allows you to set the folder your series should be downloaded to and

the selected path is shown directly underneath.



***Search bars:***

Here you can set the websites you want search results in the search bar in the main menu.

Enabling Caching for that websites will save the titles and links locally so on a future startup

the program does not need to scrape the titles and links again.

Toggling a search bar off and on will force a new scrape and update the cache.

You can also set the cache duration up to 1 year, when the duration is exceeded the program will

automatically scrape the website again and update the cache, the old cache is still used while

scraping again meaning you can still use the search bar with the old titles.



***Providers:***

Here you can toggle the providers you want to use and also change their priority via drag and drop.
I recommend keeping the main providers enabled and leave them in the standard priority,

except there was some update and should be changed, which will probably be announced in my discord.



***Languages:***

Here you can toggle the languages you want to use and change their priority.
I recommend only having the languages you actually want turned on in your preferred order.
Not all websites support all languages.
On anikototv and animepahe the sub language is embedded into Vidstream downloads as a subtitle track
and also saved as an .srt file with the same name next to the video (for players like Windows Media Player),
Portuguese, Spanish, French, Indonesian, Thai and Vietnamese subs are only available there,
and only for episodes that actually have that subtitle track.



***Support:***

Links to my Discord server (questions, bug reports and announcements), the GitHub page of this project

(source code and releases) and the itch.io page (the official download page).

Clicking a button opens the link in your browser, the address is also shown underneath so you can copy it.



**Download page features:**

This page is custom for every website meaning the layout might be slightly different for each website.

Here you can set the range of episodes you want to download.

From season is the season you want to start from and to season the last season you want to download.

From episode is the episode you want to start from (in the season if available for that website)

and to episode is the last episode you want to download (same as above).

The episode selection shows the episode number in the season (same as above),

the episode name (if available) and the overall episode number from that series.

**Links:**
[Discord](https://discord.com/invite/XqTaqUcdb2)
[Itch](https://ninjaminebro.itch.io/)



**INFO:**

This is a partial closed/open source Program that I "NMB" have made on my own with assistance of multiple tools including AI.

Please redirect anyone you share this program with to my itch.io page which is the official download page as of right now, although the program is also on my GitHub.

I am planning on making everything open source in a few days.

