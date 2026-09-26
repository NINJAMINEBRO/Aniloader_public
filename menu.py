from PySide6 import QtWidgets, QtCore, QtGui
from urllib.parse import urlparse
from pathlib import Path
import os
import validations as validate
import url_autocorrect
import site_mirrors
import settings_manager
import cache_manager
import i18n
from i18n import tr
# Site modules are imported explicitly (not filesystem-scanned) so PyInstaller
# bundles them and they stay discoverable in a frozen build, where scanning the
# package directory returns nothing. To add a site: add it here and to the
# registration loop in __init__.
from pages import anikototv_to, animepahe_ch, aniworld_to, bs_to, hanime_tv, s_to
from settings_page import SettingsPage
from title_fetcher import TitleFetcher
from fetch_status import FetchStatusTracker
from styles import ENTRY_ERROR_STYLE, ENTRY_NORMAL_STYLE
from title_delegate import TitleDelegate
from themes import apply_theme
from download_manager import DownloadManager
import updater
import version
from rounded_popup import round_combo_popup, round_popup


def _make_watermark_label() -> QtWidgets.QLabel:
    """Returns a barely-visible 'Made by NMB' credit label."""
    lbl = QtWidgets.QLabel("Made by NMB")
    lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
    lbl.setStyleSheet(
        "color: rgba(128, 128, 128, 0.22); font-size: 17px; background: transparent;"
    )
    return lbl


class MyWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(f"Aniloader by NMB - {version.display()}")

        self.settings_state = settings_manager.load()
        # First, before anything is built: every widget takes its text from it.
        i18n.set_language(self.settings_state.get("app_language", i18n.DEFAULT_LANGUAGE))
        apply_theme(self.settings_state)

        # {url: [title, alt_title?]} - master title store
        self._url_titles: dict[str, list[str]] = {}
        # {url: site} - fast site lookup used by TitleDelegate and completions
        self._url_to_site: dict[str, str] = {}
        # Lower-cased search index derived from _url_titles, built on demand and
        # dropped whenever the titles change.  None means "rebuild on next search".
        self._search_index: list[tuple[str, str, tuple[str, ...]]] | None = None
        # {site: {url, ...}} - tracks which URLs belong to each site for removal
        self._site_urls: dict[str, set[str]] = {}
        # {site: TitleFetcher} - live background threads
        self._fetchers: dict[str, TitleFetcher] = {}
        # sites whose in-memory data came from a live scrape (not a cache load)
        self._scraped_sites: set[str] = set()
        # False during __init__ so startup toggle callbacks don't force re-scrapes
        self._initialized: bool = False

        # Display name of the series the user most recently navigated to -
        # used as the top-level download folder name.
        self._current_series_name: str = ""

        # Download subsystem: owns the queue, worker pool, status panels, and
        # shutdown-when-done.  The main page drops its widget into the layout
        # (see _build_main_page) and feeds it episodes via enqueue().
        self.download_manager = DownloadManager(self.settings_state, parent=self)

        self._fetch_status = FetchStatusTracker(self)
        self._fetch_status.updated.connect(self._on_fetch_status_updated)

        # ===== Stacked Widget =====
        self.stacked = QtWidgets.QStackedWidget()
        self.stacked.addWidget(self._build_main_page())  # index 0
        self.stacked.addWidget(                          # index 1
            SettingsPage(
                self.settings_state,
                on_back=lambda: self.stacked.setCurrentIndex(0),
                on_site_toggle=self._on_site_toggle,
                on_cache_toggle=self._on_cache_toggle,
            )
        )

        # Register every site module in the pages/ package.
        # Each module must expose HOSTNAME (str) and build_content() -> QWidget.
        # Modules are listed explicitly (see the import above) rather than
        # filesystem-scanned, so they're bundled by PyInstaller and still found
        # in a frozen build.  To add a site: import it above and add it here.
        #
        # Each entry is a 5-tuple:
        #   (page, url_label, content_widget, supported_providers, supported_languages)
        self._host_pages: dict[str, tuple] = {}

        for mod in (anikototv_to, animepahe_ch, aniworld_to, bs_to, hanime_tv, s_to):
            if not (hasattr(mod, "HOSTNAME") and hasattr(mod, "build_content")):
                continue
            sp = getattr(mod, "SUPPORTED_PROVIDERS", [])
            sl = getattr(mod, "SUPPORTED_LANGUAGES", [])
            # Optional: site-internal language codes and episode URL converter.
            # When present, the download worker uses them to resolve the episode
            # page URL into a provider-specific redirect URL before downloading.
            lc = getattr(mod, "LANGUAGE_CODES", {})
            uc = getattr(mod, "get_provider_url", None)
            # A site may be wired up for browsing before it can download -
            # hanime.tv is.  Such a page gets no Confirm button, since the only
            # thing it could do there is fail.
            downloads = getattr(mod, "DOWNLOADS_SUPPORTED", True)
            page, label, content = self._build_host_page(
                mod.build_content,
                supported_providers=sp,
                supported_languages=sl,
                language_codes=lc,
                url_converter=uc,
                show_confirm=downloads,
            )
            self._host_pages[mod.HOSTNAME] = (page, label, content, sp, sl, downloads)
            self.stacked.addWidget(page)
        # Fallback for unrecognised hostnames
        self._fallback_page, self._fallback_label, _ = self._build_host_page(
            self._build_fallback_content, show_confirm=False
        )
        self.stacked.addWidget(self._fallback_page)

        # Clear any lingering error whenever the user returns to the main page,
        # regardless of how they got back (Settings ← Back, content ← Back, etc.)
        self.stacked.currentChanged.connect(
            lambda idx: self._clear_entry_error() if idx == 0 else None
        )

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.stacked)

        # Give every QComboBox dropdown the same rounded corners as the search
        # bar popup.  This covers the season/episode range pickers on each site
        # page plus the theme, neon-colour and quality selectors in Settings -
        # all of them are children of this widget and built by now.
        for combo in self.findChildren(QtWidgets.QComboBox):
            round_combo_popup(combo)

        # Start background fetches for every site that is already enabled
        for site, value in self.settings_state.items():
            if site in validate.supported_websites() and value:
                self._start_fetch(site)

        # Ask GitHub whether a newer build has been published.  Runs in the
        # background so a slow or unreachable GitHub never holds up startup.
        self._latest_build: int = 0
        self._update_checker = updater.UpdateChecker(self)
        self._update_checker.result_ready.connect(self._on_update_check_finished)
        self._update_checker.start()

        # All startup callbacks have fired; manual toggles from here on should
        # force a fresh scrape and may safely persist to cache.
        self._initialized = True

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        """Close instantly, cleaning up downloads but never blocking on fetches.

        Download workers get cancel() - which kills the in-flight ffmpeg/ffprobe
        and removes the partial file - and are waited on just long enough for
        that cleanup to finish.  Title fetchers can't be interrupted mid-scrape,
        so they are never waited on: the window is hidden immediately and, if
        anything is still running, the process exits hard via os._exit.  That
        skips object teardown, so an abandoned fetcher can't trigger a "QThread
        destroyed while running" abort - the close is instant even mid-fetch.
        """
        # Vanish right away so closing always feels instant.
        self.hide()

        running = [t for t in self.findChildren(QtCore.QThread) if t.isRunning()]
        for t in running:
            # No late slot should fire into a torn-down UI, and no finishing
            # worker should relaunch the queue while we're shutting down.
            t.blockSignals(True)

        # Stop downloads cleanly (kills ffmpeg, deletes the partial file) and
        # wait only as long as that cleanup needs - fast, since ffmpeg is killed.
        workers = [t for t in running if hasattr(t, "cancel")]
        for w in workers:
            w.cancel()
        for w in workers:
            w.wait(10000)

        # Anything still running is a title fetcher mid-scrape (uninterruptible).
        # Discard it and exit hard rather than wait - that's what keeps the close
        # instant; os._exit avoids the destroy-while-running abort.
        if any(t.isRunning() for t in self.findChildren(QtCore.QThread)):
            os._exit(0)

        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Updates
    # ------------------------------------------------------------------

    def _on_update_check_finished(self, latest_build: int) -> None:
        """Show the update button when the published build is newer than ours.

        A failed check arrives as 0 and is ignored - being offline is not
        something to nag the user about.
        """
        if latest_build <= version.BUILD:
            return
        self._latest_build = latest_build
        self.update_button.setText(f"⬆  {tr('Update to {build}', build=latest_build)}")
        self.update_button.setToolTip(
            tr("Installed build: {build}", build=version.BUILD) + "\n"
            + tr("Available build: {build}", build=latest_build)
        )
        self.update_button.setVisible(True)
        print(f"[update] Build {latest_build} available (running {version.BUILD})")

    def _on_update_clicked(self) -> None:
        """Confirm, then download the new build and restart into it."""
        # From source there is no single file to swap, so hand the user the
        # release page instead of pretending to update.
        if not updater.is_frozen():
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(updater.RELEASES_PAGE))
            return

        downloading, queued = self.download_manager.pending_work()
        warning = ""
        if downloading or queued:
            warning = "\n\n" + tr(
                "{downloading} download(s) in progress and {queued} queued "
                "will be cancelled.  Part-finished episodes are deleted and can "
                "be queued again after the restart.",
                downloading=downloading, queued=queued,
            )

        box = QtWidgets.QMessageBox(
            QtWidgets.QMessageBox.Icon.Question,
            tr("Update Aniloader"),
            tr("Update from build {installed} to {available}?",
               installed=version.BUILD, available=self._latest_build)
            + "\n\n"
            + tr("The new version is downloaded and started, and this one is "
                 "removed once it has closed.")
            + warning,
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            self,
        )
        box.setDefaultButton(QtWidgets.QMessageBox.StandardButton.No)
        # Qt only translates its standard buttons for a few languages, so they
        # are labelled here like everything else.
        yes = box.button(QtWidgets.QMessageBox.StandardButton.Yes)
        yes.setText(tr("Yes"))
        box.button(QtWidgets.QMessageBox.StandardButton.No).setText(tr("No"))
        box.exec()
        if box.clickedButton() is not yes:
            return

        self.update_button.setEnabled(False)
        self.update_button.setText(f"⬇  {tr('Downloading…')}")
        self._update_downloader = updater.UpdateDownloader(self)
        self._update_downloader.progress.connect(self._on_update_progress)
        self._update_downloader.done.connect(self._on_update_downloaded)
        self._update_downloader.start()

    def _on_update_progress(self, percent: int) -> None:
        text = f"⬇  {tr('Downloading…')}"
        self.update_button.setText(f"{text} {percent}%" if percent >= 0 else text)

    def _on_update_downloaded(self, ok: bool, payload: str) -> None:
        """Swap in the downloaded build and restart, or report why we can't."""
        if ok:
            try:
                updater.apply_update(Path(payload))
            except updater.UpdateError as exc:
                ok, payload = False, str(exc)
            except Exception as exc:            # noqa: BLE001 - shown to the user
                ok, payload = False, f"{tr('Could not install the update:')}\n{exc}"

        if not ok:
            self.update_button.setEnabled(True)
            self.update_button.setText(f"⬆  {tr('Update to {build}', build=self._latest_build)}")
            box = QtWidgets.QMessageBox(
                QtWidgets.QMessageBox.Icon.Warning, tr("Update failed"), payload,
                QtWidgets.QMessageBox.StandardButton.Ok, self,
            )
            box.button(QtWidgets.QMessageBox.StandardButton.Ok).setText(tr("OK"))
            box.exec()
            return

        # The new build is already running; close this one so it stops holding
        # the replaced file open.
        self.close()

    # ------------------------------------------------------------------
    # Page builders
    # ------------------------------------------------------------------

    def _build_main_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()

        self.settings_button = QtWidgets.QPushButton(f"⚙ {tr('Settings')}")
        self.settings_button.clicked.connect(lambda: self.stacked.setCurrentIndex(1))

        # Hidden until the version check finds a newer published build.
        self.update_button = QtWidgets.QPushButton(f"⬆  {tr('Update')}")
        self.update_button.setVisible(False)
        self.update_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.update_button.setStyleSheet(
            "QPushButton { font-weight: 600; color: #1b5e20;"
            " background: #c8e6c9; border: 1px solid #81c784;"
            " border-radius: 4px; padding: 4px 10px; }"
            "QPushButton:hover:enabled { background: #a5d6a7; }"
            "QPushButton:disabled { color: #555; background: palette(button);"
            " border: 1px solid palette(mid); }"
        )
        self.update_button.clicked.connect(self._on_update_clicked)

        top_layout = QtWidgets.QHBoxLayout()
        top_layout.addStretch()
        top_layout.addWidget(self.update_button)
        top_layout.addWidget(self.settings_button)

        self.entry = QtWidgets.QLineEdit()
        self.entry.setPlaceholderText(tr("Type something..."))
        self.entry.setFixedWidth(500)
        self.entry.setLayoutDirection(QtCore.Qt.LayoutDirection.LeftToRight)
        self.entry.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        self.entry.textEdited.connect(self._clear_entry_error)
        self.entry.textEdited.connect(self.update_completions)
        self.entry.returnPressed.connect(self._on_confirm)

        # QStringListModel works reliably with QCompleter's internal proxy filter.
        # The model stores URLs (always unique); the delegate resolves each URL
        # to a human-readable title + site label for display.
        self.completer_model = QtCore.QStringListModel(self)
        self.completer = QtWidgets.QCompleter(self.completer_model, self)
        self.completer.setCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
        # UnfilteredPopupCompletion: show all model items as-is.
        # update_completions() handles all filtering manually, so we don't want
        # the completer to re-filter URL strings against the typed text.
        self.completer.setCompletionMode(
            QtWidgets.QCompleter.CompletionMode.UnfilteredPopupCompletion
        )
        self.entry.setCompleter(self.completer)
        # When the user picks a suggestion the activated signal delivers the URL
        # directly - no title→URL reverse lookup required.
        self.completer.activated.connect(self._on_completion_activated)
        # Attach the custom delegate - every row renders "Title - site.name"
        popup = self.completer.popup()
        popup.setItemDelegate(TitleDelegate(self._url_titles, self._url_to_site, popup))
        # Every row is the same fixed height (TitleDelegate._ROW_HEIGHT), so tell
        # the view that.  Without it QListView asks the delegate for a sizeHint
        # on *every* row to work out its geometry, and each of those lays the
        # text out - with thousands of matches that alone costs hundreds of ms
        # per keystroke.
        popup.setUniformItemSizes(True)

        # Frame the popup like the QComboBox dropdowns: the theme stylesheet
        # targets this object name (see themes._BASE_QSS) so the border colour
        # tracks the active theme.  round_popup() then clips it to rounded
        # corners with the same bitmap-mask technique the combo dropdowns use.
        popup.setObjectName("searchCompleterPopup")
        round_popup(popup)

        self.error_label = QtWidgets.QLabel()
        self.error_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.error_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
        self.error_label.hide()

        self.confirm_button = QtWidgets.QPushButton(tr("Confirm"))
        self.confirm_button.setFixedWidth(120)
        self.confirm_button.clicked.connect(self._on_confirm)

        self.fetch_status_label = QtWidgets.QLabel()
        self.fetch_status_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.fetch_status_label.setStyleSheet("color: gray; font-size: 10px;")
        self.fetch_status_label.hide()

        center_layout = QtWidgets.QVBoxLayout()
        center_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        center_layout.setSpacing(6)
        center_layout.addWidget(self.entry, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(self.error_label, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(self.confirm_button, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        # ===== Download status panels (currently downloading + pending) =====
        # Built and owned by self.download_manager; just place its widget here.

        main_layout = QtWidgets.QVBoxLayout(page)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.addLayout(top_layout)
        main_layout.addLayout(center_layout)
        main_layout.addSpacing(10)
        main_layout.addWidget(self.download_manager, 1)   # expands to fill the page
        main_layout.addWidget(self.fetch_status_label, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(_make_watermark_label(), alignment=QtCore.Qt.AlignmentFlag.AlignLeft)

        return page

    def _build_host_page(
        self,
        content_builder,
        *,
        show_confirm: bool = True,
        supported_providers: list[str] | None = None,
        supported_languages: list[str] | None = None,
        language_codes: dict | None = None,
        url_converter=None,
    ) -> tuple[QtWidgets.QWidget, QtWidgets.QLabel, QtWidgets.QWidget]:
        """Build the shared chrome (back button + centred title) for a host page.

        Calls *content_builder()* for the body widget placed below it.

        Parameters
        ----------
        content_builder:
            Zero-argument callable that returns the site-specific body widget.
        show_confirm:
            When True a Confirm button is added that kicks off downloads for
            the episode range selected in *content*.
        supported_providers / supported_languages:
            Passed through to the download confirm handler so it knows which
            providers and languages this site supports.
        language_codes:
            Optional ``{display_name: site_code}`` mapping forwarded to each
            ``EpisodeDownloadWorker`` so it can resolve language display names
            to site-internal codes before calling *url_converter*.
        url_converter:
            Optional callable ``(episode_url, lang_code, provider) -> str | None``
            that converts an episode page URL into the provider redirect URL.

        Returns
        -------
        (page_widget, url_label, content_widget)
        """
        page = QtWidgets.QWidget()

        back_button = QtWidgets.QPushButton(f"← {tr('Back')}")
        back_button.clicked.connect(lambda: self.stacked.setCurrentIndex(0))

        mirror = QtWidgets.QWidget()
        mirror.setFixedSize(back_button.sizeHint())

        url_label = QtWidgets.QLabel()
        url_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        url_label.setStyleSheet("font-size: 18px; font-weight: 600;")

        top_layout = QtWidgets.QHBoxLayout()
        top_layout.addWidget(back_button)
        top_layout.addWidget(url_label, 1)
        top_layout.addWidget(mirror)

        content = content_builder()

        page_layout = QtWidgets.QVBoxLayout(page)
        page_layout.setContentsMargins(10, 10, 10, 10)
        page_layout.addLayout(top_layout)
        page_layout.addWidget(content)
        page_layout.addStretch()
        if show_confirm:
            confirm_btn = QtWidgets.QPushButton(tr("Confirm"))
            confirm_btn.setFixedWidth(120)
            # QPushButton.clicked emits checked:bool as a positional arg.
            # Absorb it with _ so the captured lists keep their correct values.
            _sp = supported_providers or []
            _sl = supported_languages or []
            _lc = language_codes or {}
            _uc = url_converter
            confirm_btn.clicked.connect(
                lambda _, sp=_sp, sl=_sl, lc=_lc, uc=_uc:
                    self._on_download_confirm(content, sp, sl, lc, uc)
            )
            page_layout.addWidget(confirm_btn, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
            page_layout.addSpacing(8)
        page_layout.addWidget(_make_watermark_label(), alignment=QtCore.Qt.AlignmentFlag.AlignLeft)

        return page, url_label, content

    def _build_fallback_content(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        label = QtWidgets.QLabel(tr("Under Development"))
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(label)
        layout.addWidget(_make_watermark_label(), alignment=QtCore.Qt.AlignmentFlag.AlignLeft)
        return w

    # ------------------------------------------------------------------
    # Confirm / validation / routing
    # ------------------------------------------------------------------

    def _on_confirm(self):
        url = self._resolve_entry_url(self.entry.text().strip())
        if not validate.is_valid_url(url):
            self._show_entry_error(tr("Invalid URL"))
            return

        # A link pasted from a backup domain names the same series as the
        # primary one, so it is folded onto the primary here - before the title
        # lookup and before routing - and the rest of the app never sees the
        # mirror.  site_mirrors puts it back at request time if that domain is
        # the one currently answering.
        url = site_mirrors.to_canonical(url)
        parsed = urlparse(url)
        host = site_mirrors.canonical(parsed.hostname) or ""
        last_segment = parsed.path.rstrip("/").split("/")[-1]
        titles = self._url_titles.get(url)
        display_text = titles[0] if titles else last_segment.replace("-", " ")

        host_entry = self._host_pages.get(host)
        if host_entry is not None:
            (page, label, content, supported_providers,
             supported_languages, downloads) = host_entry

            # Guard: require at least one enabled provider and one enabled language
            # that this site actually supports before allowing navigation.
            # Skipped for a site that cannot download yet - it has no providers or
            # languages by definition, and refusing to open it over that would
            # report a settings problem the user has no way to fix.
            if downloads:
                enabled_providers = settings_manager.get_enabled_providers(
                    self.settings_state, supported_providers
                )
                enabled_languages = settings_manager.get_enabled_languages(
                    self.settings_state, supported_languages
                )
                if not enabled_providers and not enabled_languages:
                    self._show_entry_error(tr("No enabled providers or languages for this site"))
                    return
                if not enabled_providers:
                    self._show_entry_error(tr("No enabled providers for this site"))
                    return
                if not enabled_languages:
                    self._show_entry_error(tr("No enabled languages for this site"))
                    return
        else:
            page, label, content = self._fallback_page, self._fallback_label, None

        self._clear_entry_error()
        # Remember the series name for the download folder structure.
        self._current_series_name = display_text
        label.setText(display_text)
        if content is not None and hasattr(content, "load"):
            content.load(url)
        self.stacked.setCurrentWidget(page)

    def _resolve_entry_url(self, raw: str) -> str:
        """Return the URL to open for the typed text, repairing it if it won't work.

        A hand-typed link often fails over something obvious - a missing
        ``https://``, a lower-cased bs.to slug, an episode URL where the series
        URL belongs. When :mod:`url_autocorrect` can say with confidence what
        was meant, the repaired link is used *and written back into the entry*,
        so the address on screen is always the one actually being opened - the
        same feedback a browser's address bar gives.  Anything it can't repair
        confidently is returned untouched and fails validation as before.
        """
        fix = url_autocorrect.autocorrect(raw, self._url_to_site)
        if fix is None:
            return raw
        print(f"[url] Autocorrected {raw!r} → {fix.url!r} ({fix.reason})")
        # setText emits textChanged, not textEdited, so this doesn't re-enter
        # the _clear_entry_error / update_completions hookups.
        self.entry.setText(fix.url)
        self.entry.setCursorPosition(len(fix.url))
        return fix.url

    def _show_entry_error(self, message: str | None = None):
        self.entry.setStyleSheet(ENTRY_ERROR_STYLE)
        self.error_label.setText(message or tr("Invalid URL"))
        self.error_label.show()

    def _clear_entry_error(self):
        self.entry.setStyleSheet(ENTRY_NORMAL_STYLE)
        self.error_label.hide()

    # ------------------------------------------------------------------
    # Download orchestration
    # ------------------------------------------------------------------

    def _on_download_confirm(
        self,
        content: QtWidgets.QWidget,
        supported_providers: list[str],
        supported_languages: list[str],
        language_codes: dict,
        url_converter,
    ) -> None:
        """Queue downloads for every episode in the content widget's selected range.

        Only widgets that expose ``get_selected_urls()`` participate - other
        site pages remain no-ops until they implement that interface.
        """
        if not hasattr(content, "get_selected_urls"):
            return

        episodes = content.get_selected_urls()
        if not episodes:
            return

        self.download_manager.enqueue(
            episodes,
            supported_providers,
            supported_languages,
            language_codes,
            url_converter,
        )

        # Confirming a download closes this page and returns to the main menu
        # (where the downloading/pending panels are visible), and clears the
        # search entry so it's ready for the next series.
        self.entry.clear()
        self._clear_entry_error()
        self.stacked.setCurrentIndex(0)

    # ------------------------------------------------------------------
    # Autocomplete
    # ------------------------------------------------------------------

    def _on_completion_activated(self, url: str):
        # The model stores URLs directly - no reverse lookup needed.
        # Defer one event-loop tick so our setText fires after the completer's
        # own insertion, guaranteeing the URL value wins.
        QtCore.QTimer.singleShot(0, lambda: self._apply_completion(url))

    def _apply_completion(self, url: str):
        self.entry.setText(url)
        self.entry.setCursorPosition(len(url))
        self._clear_entry_error()

    # Most suggestions the popup will ever show at once.  A single letter can
    # match tens of thousands of titles, and handing all of them to the popup is
    # what made typing lag: the user only ever sees about ten rows, and the
    # buckets below are ordered by relevance, so anything past this is noise
    # that costs time to build.  Narrowing the query is what surfaces the rest.
    MAX_COMPLETIONS = 10000

    def _search_entries(self) -> list[tuple[str, str, tuple[str, ...]]]:
        """``(url, primary_lower, alt_titles_lower)`` for every searchable title.

        Lower-casing 36k titles takes ~15ms, which is fine once but not on every
        keystroke, so the result is cached until the titles themselves change
        (see :meth:`_invalidate_search_entries`).

        A URL whose title list is empty is deliberately left out: that is how a
        site says "this link is mine, but do not offer it as its own row".
        anikototv uses it for the seasons it folds into one series - the series
        is searched for once, while each season's own address stays a link the
        app recognises and routes.
        """
        if self._search_index is None:
            self._search_index = [
                (url, titles[0].lower(), tuple(t.lower() for t in titles[1:]))
                for url, titles in self._url_titles.items()
                if titles
            ]
        return self._search_index

    def _invalidate_search_entries(self) -> None:
        """Drop the cached search index; the next search rebuilds it."""
        self._search_index = None

    def update_completions(self, text: str):
        text = text.strip()
        if not text:
            self.completer.popup().hide()
            return

        text_lower = text.lower()

        # Five priority buckets:
        #   b0 - exact match on primary title
        #   b1 - primary title starts with the query
        #   b2 - an alt title starts with the query
        #   b3 - query appears anywhere in the primary title
        #   b4 - query appears anywhere in an alt title
        #
        # Each bucket stores URLs (the model's item strings).  Using URLs as
        # keys means two sites that share the same title both appear as
        # distinct rows - no title-based deduplication is needed.
        b0, b1, b2, b3, b4 = [], [], [], [], []

        for url, first_lower, others_lower in self._search_entries():
            if first_lower == text_lower:
                b0.append(url)
            elif first_lower.startswith(text_lower):
                b1.append(url)
            elif any(t.startswith(text_lower) for t in others_lower):
                b2.append(url)
            elif text_lower in first_lower:
                b3.append(url)
            elif any(text_lower in t for t in others_lower):
                b4.append(url)

        # Take whole buckets in priority order, stopping at the cap - so the
        # rows that do show are always the best matches, not an arbitrary slice.
        results: list[str] = []
        for bucket in (b0, b1, b2, b3, b4):
            results += bucket
            if len(results) >= self.MAX_COMPLETIONS:
                results = results[: self.MAX_COMPLETIONS]
                break

        self.completer_model.setStringList(results)

        if results:
            self.completer.complete()

    # ------------------------------------------------------------------
    # Title fetching
    # ------------------------------------------------------------------

    def _start_fetch(self, site: str, force: bool = False) -> None:
        """Spawn a background TitleFetcher for *site* (no-op if one is already running).

        Cache-first behaviour when caching is enabled for *site*:
          - If a valid (non-stale) cache file exists the titles are loaded
            immediately and no network request is made.
          - If the cache exists but has expired the cached titles are loaded
            right away (so the search bar is usable instantly) and a background
            fetch is still started to refresh them.
          - If no cache file exists a normal background fetch is performed.

        Pass ``force=True`` to always run a network fetch even when the cache is
        fresh (e.g. after a manual search-bar re-enable).  The cache is still
        pre-loaded so completions are available instantly while the fetch runs.
        """
        if site in self._fetchers and self._fetchers[site].isRunning():
            return

        if self.settings_state.get(f"{site}_cache", False):
            payload = cache_manager.load_cache(site)
            if payload:
                # Make titles available immediately from cache
                self._apply_titles(site, payload.get("data", {}))
                if not force:
                    cache_days = self.settings_state.get("cache_days", 7)
                    if not cache_manager.is_stale(payload, cache_days):
                        return  # Cache is fresh - skip the network request entirely

        # Network fetch (no cache, stale cache, or forced refresh)
        fetcher = TitleFetcher(site, self)
        fetcher.titles_ready.connect(self._on_titles_ready)
        # Built-in finished (after run() returns): drop the thread from the
        # registry and delete it so finished fetchers don't accumulate.
        fetcher.finished.connect(self._on_fetcher_thread_finished)
        self._fetchers[site] = fetcher
        self._fetch_status.add(site)
        fetcher.start()

    def _apply_titles(self, site: str, data: dict, from_scrape: bool = False) -> None:
        """Insert a {url: titles} mapping into the live lookup tables for *site*.

        Called both when loading from cache (synchronously in the main thread)
        and from _on_titles_ready (after a live scrape).  Pass ``from_scrape=True``
        in the latter case so _on_cache_toggle knows the data is fresh.
        """
        if from_scrape:
            self._scraped_sites.add(site)
        self._site_urls[site] = set(data.keys())
        for url, titles in data.items():
            self._url_titles[url] = titles
            self._url_to_site[url] = site
        self._invalidate_search_entries()

    def _on_titles_ready(self, site: str, data: dict):
        """Slot called in the main thread when a TitleFetcher finishes."""
        # Clear whatever was loaded before (live data or stale cache)
        self._remove_site_titles(site)
        self._fetch_status.remove(site)
        # Discard results if the site was toggled off while we were fetching
        if not self.settings_state.get(site, False):
            return
        self._apply_titles(site, data, from_scrape=True)
        # Persist the fresh results when caching is enabled for this site
        if data and self.settings_state.get(f"{site}_cache", False):
            cache_manager.save_cache(site, data)

    def _on_fetcher_thread_finished(self) -> None:
        """Drop a finished TitleFetcher from the registry and delete it.

        Connected to the thread's built-in ``finished`` (fired once run() has
        returned), so the QThread object is freed instead of lingering as a
        child for the rest of the session.
        """
        fetcher = self.sender()
        if fetcher is None:
            return
        for site, existing in list(self._fetchers.items()):
            if existing is fetcher:
                del self._fetchers[site]
                break
        fetcher.deleteLater()

    def _remove_site_titles(self, site: str):
        """Remove every title that belongs to *site* from all lookup structures."""
        self._scraped_sites.discard(site)
        for url in self._site_urls.pop(site, set()):
            self._url_titles.pop(url, None)
            self._url_to_site.pop(url, None)
        self._invalidate_search_entries()

    def _on_site_toggle(self, site: str, enabled: bool):
        """Called by SettingsPage whenever a website toggle changes."""
        if enabled:
            self._start_fetch(site, force=self._initialized)
        else:
            self._remove_site_titles(site)

    def _on_cache_toggle(self, site: str, enabled: bool):
        """Called by SettingsPage whenever a site's cache toggle changes.

        When the user switches caching ON and titles for that site were freshly
        scraped during this session (not just loaded from an existing cache file),
        write them to disk immediately so the next startup can skip the scrape.
        No action is needed when caching is turned off - the existing cache file
        is left intact and will simply be ignored.
        """
        if not enabled:
            return
        # Only persist if the in-memory data actually came from a live scrape.
        # Titles loaded from the cache file must not reset the cache timestamp.
        if site not in self._scraped_sites:
            return
        urls = self._site_urls.get(site, set())
        if not urls:
            return  # Nothing in memory yet; cache will be written after the next fetch
        data = {url: self._url_titles[url] for url in urls if url in self._url_titles}
        if data:
            cache_manager.save_cache(site, data)

    def _on_fetch_status_updated(self, text: str):
        """Slot wired to FetchStatusTracker.updated - show or hide the label."""
        if text:
            self.fetch_status_label.setText(text)
            self.fetch_status_label.show()
        else:
            self.fetch_status_label.hide()