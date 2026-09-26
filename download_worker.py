"""Background worker that downloads a single episode.

Tries every enabled Language → Quality → Provider combination in order,
stopping at the first successful download.

Downloads are organised on disk as::

    <download_path>/<Series Name>/<Season>/<Episode file>.mp4

If a *url_converter* is supplied, it is called before each provider attempt
to resolve the episode page URL into the provider-specific redirect URL.
If it returns ``None`` (language/provider unavailable for this episode),
that combination is skipped silently.
"""

import os
import re
import shutil
import threading
from PySide6 import QtCore

import settings_manager
import downloader_mapper
from downloaders import common
from app_paths import base_dir
from i18n import tr


def _safe_filename(name: str) -> str:
    """Remove characters that are illegal in Windows / Linux / macOS filenames."""
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()


def _season_number(season_label: str) -> int:
    """Extract the numeric season from a label like ``"Season 2"`` (→ 2).

    Only what follows "Season" is read, so a label that qualifies the season
    after its number still lands in the right one: anikototv names the halves of
    a split season "Season 4: Part 1" and "Season 4: Part 2", and both belong to
    season 4.  They keep separate folders - the label is the folder name - so
    the shared ``S04E01`` numbering collides with nothing.

    Non-numeric labels such as ``"Movies"``, ``"OVA"`` or ``"Specials"`` fall
    back to 0, giving e.g. ``"S00E03 …"``.
    """
    match = re.match(r"\s*season\s+(\d+)", season_label, re.IGNORECASE)
    return int(match.group(1)) if match else 0


def episode_code(ep_num: "int | float") -> str:
    """The episode number as written after the "E": ``7`` → ``"07"``.

    animepahe numbers its recaps and specials between the episodes they follow
    (``12.5``); those keep their fraction - ``"12.5"`` - so the file sorts right
    after episode 12 instead of overwriting it.
    """
    if isinstance(ep_num, float):
        if not ep_num.is_integer():
            whole, fraction = str(ep_num).split(".", 1)
            return f"{int(whole):02d}.{fraction}"
        ep_num = int(ep_num)
    return f"{ep_num:02d}"


def episode_dir_and_name(settings: dict, series_name: str, season_label: str,
                         ep_num: "int | float", title: str) -> tuple[str, str]:
    """Return the ``(download_dir, file_name)`` for one episode.

    Single source of truth for where an episode is written, so the worker and
    the "already downloaded" check in the main menu always agree on the path.
    """
    base_path = settings.get("download_path", ".")
    series_dir = _safe_filename(series_name) or "Unknown Series"
    season_dir = _safe_filename(season_label) or "Season"
    download_dir = os.path.join(base_path, series_dir, season_dir)
    season_num = _season_number(season_label)
    file_name = f"S{season_num:02d}E{episode_code(ep_num)} {_safe_filename(title)}.mp4"
    return download_dir, file_name


def episode_output_path(settings: dict, series_name: str, season_label: str,
                        ep_num: int, title: str) -> str:
    """Full path the episode would be written to."""
    download_dir, file_name = episode_dir_and_name(
        settings, series_name, season_label, ep_num, title
    )
    return os.path.join(download_dir, file_name)


def is_already_downloaded(settings: dict, series_name: str, season_label: str,
                          ep_num: int, title: str) -> bool:
    """True if the episode's target file already exists on disk.

    Detection is by output path only (quality-agnostic) - matching the agreed
    behaviour that a file present from any source/website counts as done.
    """
    return os.path.exists(
        episode_output_path(settings, series_name, season_label, ep_num, title)
    )


def _ffmpeg_available() -> bool:
    """Return True if ffmpeg can be launched.

    Checks the system PATH and the app's own folder (base_dir), which is where
    a bundled ``ffmpeg.exe`` is shipped next to the packaged exe.  The app folder
    is used rather than the working directory, which is not the exe's folder when
    the app is launched from a shortcut.
    """
    if shutil.which("ffmpeg"):
        return True
    return any((base_dir() / name).is_file() for name in ("ffmpeg.exe", "ffmpeg"))


class EpisodeDownloadWorker(QtCore.QThread):
    """Attempts to download one episode by cycling Language → Quality → Provider.

    Signals
    -------
    progress(url, message)
        Fired on each provider attempt or skip.
    download_finished(url, success, winning_combo)
        Fired once when all combinations have been tried.
        On success ``winning_combo`` is a human-readable string like
        ``"German Dub / 1080p / VOE"``; on failure it is an empty string.
    """

    progress = QtCore.Signal(str, str)                 # (url, status_message)
    download_finished = QtCore.Signal(str, bool, str)  # (url, success, combo)

    def __init__(
        self,
        url: str,
        series_name: str,
        season_label: str,
        ep_num: int,
        title: str,
        settings_state: dict,
        supported_providers: list[str],
        supported_languages: list[str],
        language_codes: dict[str, str] | None = None,
        url_converter=None,
        parent=None,
    ):
        """
        Parameters
        ----------
        url:
            Episode page URL (e.g. an aniworld.to episode URL).
        series_name:
            Human-readable series name used as the top-level download folder.
        season_label:
            Human-readable season name used as the season sub-folder and in
            the output filename.
        ep_num:
            Episode number within the season, used in the filename.
        title:
            Episode title, used in the filename.
        settings_state:
            Shared settings dict (read-only inside the thread).
        supported_providers:
            Provider names this site supports, in priority order.
        supported_languages:
            Language names this site supports, in priority order.
        language_codes:
            Optional mapping from display name → site-internal code, e.g.
            ``{"German Dub": "1"}``.  Used when calling *url_converter*.
        url_converter:
            Optional callable ``(episode_url, lang_code, provider) -> str | None``.
            Converts the episode page URL to a provider redirect URL.
            When ``None``, the episode URL is passed directly to the downloader
            (useful for sites where the episode URL *is* the provider URL).
        """
        super().__init__(parent)
        self._url = url
        self._series_name = series_name
        self._season_label = season_label
        self._ep_num = ep_num
        self._title = title
        self._settings = settings_state
        self._supported_providers = supported_providers
        self._supported_languages = supported_languages
        self._language_codes = language_codes or {}
        self._url_converter = url_converter
        # Set to this thread's id once run() starts; used by cancel() to kill
        # an in-flight ffmpeg/ffprobe in the correct thread.
        self._tid: int | None = None

    # ------------------------------------------------------------------
    # Cancellation
    # ------------------------------------------------------------------

    def cancel(self) -> None:
        """Request a clean stop (called from the GUI thread, e.g. on app close).

        Sets the interruption flag so the combo loop bails out at its next
        check, and terminates any ffmpeg/ffprobe currently running in this
        worker's thread so the in-flight mux stops immediately.  The partial
        output file is removed by ``common.run_ffmpeg``.
        """
        self.requestInterruption()
        if self._tid is not None:
            common.cancel(self._tid)

    # ------------------------------------------------------------------
    # Thread entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        self._tid = threading.get_ident()
        # A recycled thread id must not inherit a previous worker's cancel flag.
        common.clear_cancel(self._tid)

        # ffmpeg is required to mux every download.  Check once up front so we
        # fail fast with a clear message instead of re-resolving the stream URL
        # for every language/quality/provider combination only to hit the same
        # missing-ffmpeg wall each time.
        if not _ffmpeg_available():
            self.progress.emit(
                self._url,
                tr("ffmpeg not found - install it and add it to your PATH, then retry"),
            )
            self.download_finished.emit(self._url, False, "")
            return

        enabled_languages = settings_manager.get_enabled_languages(
            self._settings, self._supported_languages
        )
        enabled_providers = settings_manager.get_enabled_providers(
            self._settings, self._supported_providers
        )
        available_qualities = settings_manager.get_available_qualities(self._settings)

        # Resolve the destination via the shared helper so it always matches
        # the main-menu "already downloaded" check.
        download_path, file_name = episode_dir_and_name(
            self._settings, self._series_name, self._season_label,
            self._ep_num, self._title,
        )

        # Last-ditch guard: if the file appeared since it was queued (e.g. a
        # parallel download of the same title from another site), skip it.
        if os.path.exists(os.path.join(download_path, file_name)):
            self.progress.emit(self._url, "  ↳ " + tr("already downloaded - skipping"))
            self.download_finished.emit(self._url, True, "already downloaded")
            return

        try:
            os.makedirs(download_path, exist_ok=True)
        except OSError as exc:
            self.progress.emit(self._url, "  ↳ " + tr(
                "could not create folder {folder}: {error}",
                folder=repr(download_path), error=exc,
            ))

        for language in enabled_languages:
            # Resolve the display name to the site-internal language code.
            lang_code = self._language_codes.get(language, language)

            for quality in available_qualities:
                for provider in enabled_providers:

                    # Stop promptly when a shutdown/cancel has been requested,
                    # before doing any more network work or launching ffmpeg.
                    if self.isInterruptionRequested():
                        self.download_finished.emit(self._url, False, "")
                        return

                    # --- URL conversion -----------------------------------
                    if self._url_converter is not None:
                        provider_url = self._url_converter(self._url, lang_code, provider)
                        if provider_url is None:
                            # This language/provider combo doesn't exist for
                            # this episode - skip without counting as a failure.
                            self.progress.emit(
                                self._url,
                                "  ↳ " + tr("skipped: {language} / {provider} not available",
                                            language=tr(language), provider=provider),
                            )
                            continue
                    else:
                        provider_url = self._url
                    # ------------------------------------------------------

                    combo = f"{language} / {quality} / {provider}"
                    self.progress.emit(self._url, tr(
                        "Trying {combination}",
                        combination=f"{tr(language)} / {quality} / {provider}",
                    ))

                    try:
                        success = downloader_mapper.map(
                            provider, provider_url, download_path, file_name, quality
                        )
                    except Exception as exc:
                        self.progress.emit(self._url, "  ↳ " + tr(
                            "error with {provider}: {error}", provider=provider, error=exc,
                        ))
                        success = False

                    if success:
                        self.download_finished.emit(self._url, True, combo)
                        return

        # All combinations exhausted without a successful download
        self.download_finished.emit(self._url, False, "")