from PySide6 import QtWidgets, QtCore, QtGui
import i18n
import settings_manager
from i18n import N_, tr
from styles import TOGGLE_STYLE, TOGGLE_BARE_STYLE
from themes import NEON_COLORS, DEFAULT_NEON_COLOR, apply_theme
from settings_manager import QUALITIES

# Dedicated data role for PriorityList enabled state.
# Qt6 silently ignores CheckStateRole when ItemIsUserCheckable is absent,
# so we store the bool in a custom role that has no such restriction.
_PRIORITY_ENABLED_ROLE = int(QtCore.Qt.ItemDataRole.UserRole) + 1

# Where to get help or the latest build, listed on the Support tab as
# (name, what it is for, link).
SUPPORT_LINKS: list[tuple[str, str, str]] = [
    ("Discord", N_("Questions, bug reports and announcements"),
     "https://discord.gg/XqTaqUcdb2"),
    ("GitHub", N_("Source code and releases"),
     "https://github.com/NINJAMINEBRO/Aniloader_public"),
    ("itch.io", N_("Official download page"),
     "https://ninjaminebro.itch.io/aniloader"),
]

# The themes the Theme picker offers.  The English names are what the settings
# file stores; the picker shows them translated.
THEMES = [N_("Dark"), N_("Light"), N_("Neon")]

# Width the rows of the General tab have had from the start.  A row only grows
# past it when a translation needs the room, and then all of them grow together
# so they stay one column.
_ROW_WIDTH = 200


def _format_path(path: str) -> str:
    return path if len(path) <= 50 else "…" + path[-47:]


# ----------------------------------------------------------------------
# Chevron stepper button (used by every numeric stepper on the Settings page)
# ----------------------------------------------------------------------

class _ChevronButton(QtWidgets.QAbstractButton):
    """A small flat button that paints a thin up- or down-chevron.

    Replaces a QSpinBox's native vertical stepper with two horizontal chevrons
    sat side by side.  The glyph is drawn with QPainter so it stays crisp and
    follows the active theme's text/highlight colours on every platform,
    instead of depending on a font glyph or a bundled image.
    """

    def __init__(self, direction: str, parent=None):
        super().__init__(parent)
        self._direction = direction          # "up" or "down"
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.setFixedSize(18, 22)
        # Hold the button to keep stepping, like a native spin box.
        self.setAutoRepeat(True)
        self.setAutoRepeatDelay(300)
        self.setAutoRepeatInterval(60)

    def paintEvent(self, _event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        pal = self.palette()
        color = pal.buttonText().color()
        if not self.isEnabled():
            color.setAlpha(90)
        elif self.underMouse() or self.isDown():
            color = pal.highlight().color()

        pen = QtGui.QPen(color, 1.4)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        rect = self.rect()
        cx = rect.center().x() + 0.5
        cy = rect.center().y() + 0.5
        half_w = 4.0
        half_h = 2.5
        if self._direction == "up":
            painter.drawLine(QtCore.QPointF(cx - half_w, cy + half_h),
                             QtCore.QPointF(cx, cy - half_h))
            painter.drawLine(QtCore.QPointF(cx, cy - half_h),
                             QtCore.QPointF(cx + half_w, cy + half_h))
        else:
            painter.drawLine(QtCore.QPointF(cx - half_w, cy - half_h),
                             QtCore.QPointF(cx, cy + half_h))
            painter.drawLine(QtCore.QPointF(cx, cy + half_h),
                             QtCore.QPointF(cx + half_w, cy - half_h))
        painter.end()


# ----------------------------------------------------------------------
# Delegate for PriorityList rows
# ----------------------------------------------------------------------

class PriorityItemDelegate(QtWidgets.QStyledItemDelegate):
    """Renders each PriorityList row as a compact toggle-style strip.

    Checked   → green background, white text, green divider line.
    Unchecked → palette button colours, mid-tone divider line.
    No checkbox is drawn; toggling is handled by PriorityList.itemClicked.
    """

    _ROW_H = 30

    def paint(self, painter, option, index):
        checked = bool(index.data(_PRIORITY_ENABLED_ROLE))
        painter.save()
        rect = option.rect

        if checked:
            bg  = QtGui.QColor("#166034")
            fg  = QtGui.QColor("#ffffff")
            div = QtGui.QColor("#27ae60")
        else:
            pal = option.palette
            bg  = pal.button().color()
            fg  = pal.buttonText().color()
            div = pal.mid().color()

        # Fill background (paints over any selection highlight)
        painter.fillRect(rect, bg)

        # Divider along the bottom edge
        painter.setPen(QtGui.QPen(div, 1))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

        painter.setPen(fg)
        fm = painter.fontMetrics()

        # ON / OFF label - right-aligned
        status   = tr("ON") if checked else tr("OFF")
        status_w = fm.horizontalAdvance(status)
        painter.drawText(
            rect.adjusted(0, 0, -10, 0),
            QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter,
            status,
        )

        # Name with ⠿ grip prefix - left-aligned, clipped so it never overlaps the label
        text      = index.data(QtCore.Qt.ItemDataRole.DisplayRole) or ""
        text_rect = rect.adjusted(10, 0, -(status_w + 20), 0)
        painter.drawText(
            text_rect,
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter,
            fm.elidedText(text, QtCore.Qt.TextElideMode.ElideRight, text_rect.width()),
        )

        painter.restore()

    def sizeHint(self, option, index):
        return QtCore.QSize(
            super().sizeHint(option, index).width(),
            self._ROW_H,
        )


# ----------------------------------------------------------------------
# Priority list widget  (shared by providers and languages)
# ----------------------------------------------------------------------

class PriorityList(QtWidgets.QWidget):
    """Drag-to-reorder, checkable list for any global priority setting.

    Each row has a grip icon, a checkbox, and a display name.  Rows can be
    dragged to change priority order; checking/unchecking toggles the entry.
    Every change is persisted immediately via settings_manager.  The name is
    shown translated but saved as it is in the settings file, which is also
    how the sites and the download worker know it.

    Parameters
    ----------
    settings_state : dict
        Shared mutable settings dict - changes are written back in-place.
    key : str
        The settings key holding a ``[{"name": str, "enabled": bool}, …]`` list.
    label : str
        Section header displayed above the list.
    """

    _GRIP = "⠿  "

    def __init__(
        self,
        settings_state: dict,
        key: str,
        label: str,
        parent=None,
    ):
        super().__init__(parent)
        self._settings = settings_state
        self._key = key
        self._build(label)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build(self, label: str) -> None:
        header = QtWidgets.QLabel(label)
        header.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet("font-size: 11px; font-weight: 600;")

        hint = QtWidgets.QLabel(tr("Drag to reorder  ·  click to toggle"))
        hint.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: gray; font-size: 10px;")

        self._list = QtWidgets.QListWidget()
        self._list.setItemDelegate(PriorityItemDelegate(self._list))
        self._list.setSpacing(0)
        self._list.setDragDropMode(
            QtWidgets.QAbstractItemView.DragDropMode.InternalMove
        )
        self._list.setDefaultDropAction(QtCore.Qt.DropAction.MoveAction)

        for p in self._settings.get(self._key, []):
            self._append_item(p["name"], p["enabled"])

        # Wide enough that the longest name isn't elided next to the ON/OFF
        # label (the delegate reserves 10px left and status + 20px right),
        # but never narrower than the original 200px.
        fm = self._list.fontMetrics()
        longest = max(
            (fm.horizontalAdvance(self._list.item(i).text()) for i in range(self._list.count())),
            default=0,
        )
        status_w = max(fm.horizontalAdvance(tr("ON")), fm.horizontalAdvance(tr("OFF")))
        self._list.setFixedWidth(max(
            200,
            longest + status_w + 40 + 2 * self._list.frameWidth(),
        ))

        # Size to exactly fit all rows - no scrollbar
        row_h = self._list.sizeHintForRow(0) if self._list.count() else 28
        row_h = row_h if row_h > 0 else 28
        self._list.setFixedHeight(
            row_h * self._list.count() + 2 * self._list.frameWidth() + 2
        )

        # Connect *after* populating so construction doesn't trigger saves
        self._list.itemChanged.connect(self._save)
        self._list.itemClicked.connect(self._toggle_item)
        self._list.model().rowsMoved.connect(self._save)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(header)
        layout.addWidget(hint)
        layout.addWidget(self._list)

    def _append_item(self, name: str, enabled: bool) -> None:
        item = QtWidgets.QListWidgetItem(f"{self._GRIP}{tr(name)}")
        item.setData(QtCore.Qt.ItemDataRole.UserRole, name)
        item.setFlags(
            QtCore.Qt.ItemFlag.ItemIsEnabled
            | QtCore.Qt.ItemFlag.ItemIsSelectable
            | QtCore.Qt.ItemFlag.ItemIsDragEnabled
        )
        item.setData(_PRIORITY_ENABLED_ROLE, enabled)
        self._list.addItem(item)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self) -> None:
        entries = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            entries.append({
                "name":    item.data(QtCore.Qt.ItemDataRole.UserRole),
                "enabled": bool(item.data(_PRIORITY_ENABLED_ROLE)),
            })
        self._settings[self._key] = entries
        settings_manager.save(self._settings)

    def _toggle_item(self, item: QtWidgets.QListWidgetItem) -> None:
        """Flip the enabled state of a row when the user clicks it."""
        item.setData(_PRIORITY_ENABLED_ROLE, not bool(item.data(_PRIORITY_ENABLED_ROLE)))


# ----------------------------------------------------------------------
# Settings page
# ----------------------------------------------------------------------

class SettingsPage(QtWidgets.QWidget):
    """
    Self-contained settings page with a QTabWidget.

    Tabs:
      General     - app language, theme, quality range, download options, path.
      Search bars - site toggles (which search bars are active).
      Providers   - global provider priority list.
      Languages   - global language priority list.
      Support     - links to the Discord server, GitHub repo and itch.io page.

    Parameters
    ----------
    settings_state : dict
        Shared mutable dict from MyWidget - changes here are reflected everywhere.
    on_back : callable
        Called when the back button is clicked (typically switches stacked page).
    on_site_toggle : callable, optional
        Called with (site: str, enabled: bool) when a site toggle changes.
    on_cache_toggle : callable, optional
        Called with (site: str, enabled: bool) when a site *cache* toggle changes.
    """

    def __init__(
        self,
        settings_state: dict,
        on_back: callable,
        on_site_toggle: callable = None,
        on_cache_toggle: callable = None,
        parent=None,
    ):
        super().__init__(parent)
        self._settings = settings_state
        self._on_back = on_back
        self._on_site_toggle = on_site_toggle
        self._on_cache_toggle = on_cache_toggle
        # Every (spin box, up chevron, down chevron) built by
        # _build_stepper_control, so one stepper can clear the value highlight
        # its neighbours were left holding.
        self._steppers: list[tuple[QtWidgets.QSpinBox,
                                   QtWidgets.QAbstractButton,
                                   QtWidgets.QAbstractButton]] = []
        self._build()
        # Stepping selects the spin box's text and the chevrons deliberately
        # take no focus, so nothing would ever clear that highlight again.
        # Watch every mouse press instead and drop it as soon as a click lands
        # anywhere but that field's own chevrons.
        QtWidgets.QApplication.instance().installEventFilter(self)

    def _build(self) -> None:
        # ===== Back Button =====
        back_button = QtWidgets.QPushButton(f"← {tr('Back')}")
        back_button.clicked.connect(self._on_back)

        top_layout = QtWidgets.QHBoxLayout()
        top_layout.addWidget(back_button)
        top_layout.addStretch()

        # ===== Tab widget =====
        self._tabs = QtWidgets.QTabWidget()
        self._tabs.addTab(self._build_general_tab(),     tr("General"))
        self._tabs.addTab(self._build_search_bars_tab(), tr("Search bars"))
        self._tabs.addTab(self._build_providers_tab(),   tr("Providers"))
        self._tabs.addTab(self._build_languages_tab(),   tr("Languages"))
        self._tabs.addTab(self._build_support_tab(),     tr("Support"))

        # ===== Page layout =====
        page_layout = QtWidgets.QVBoxLayout(self)
        page_layout.setContentsMargins(10, 10, 10, 10)
        page_layout.addLayout(top_layout)
        page_layout.addWidget(self._tabs)

        nmb_lbl = QtWidgets.QLabel("Made by NMB")
        nmb_lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        nmb_lbl.setStyleSheet(
            "color: rgba(128, 128, 128, 0.22); font-size: 17px; background: transparent;"
        )
        page_layout.addWidget(nmb_lbl, alignment=QtCore.Qt.AlignmentFlag.AlignLeft)

    # ------------------------------------------------------------------
    # Tab builders
    # ------------------------------------------------------------------

    def _build_general_tab(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        _ctr = QtCore.Qt.AlignmentFlag.AlignCenter
        _top = QtCore.Qt.AlignmentFlag.AlignTop

        # Language of the interface itself.  Each language is listed under its
        # own name; the settings file stores its English key (i18n.LANGUAGES).
        self.app_language_combo = QtWidgets.QComboBox()
        for language, (native_name, _table, _locale) in i18n.LANGUAGES.items():
            self.app_language_combo.addItem(native_name, language)
        self._select_data(
            self.app_language_combo,
            self._settings.get("app_language", i18n.DEFAULT_LANGUAGE),
        )
        self.app_language_combo.currentIndexChanged.connect(self._on_app_language_changed)
        app_language_row = self._build_combo_row(tr("App language:"), self.app_language_combo)

        # The interface only changes language on the next start (see i18n), so
        # picking another one says so - in the language just picked.
        self.app_language_note = QtWidgets.QLabel()
        self.app_language_note.setWordWrap(True)
        self.app_language_note.setAlignment(_ctr)
        self.app_language_note.setStyleSheet("color: #c98a00; font-size: 10px;")
        self.app_language_note.setFixedWidth(220)
        self._update_app_language_note()

        # Theme selection - shown translated, stored under its English name.
        self.theme_combo = QtWidgets.QComboBox()
        for theme in THEMES:
            self.theme_combo.addItem(tr(theme), theme)
        self._select_data(self.theme_combo, self._settings.get("theme", "Dark"))
        self.theme_combo.currentIndexChanged.connect(
            lambda _index: self._on_theme_changed(self.theme_combo.currentData())
        )
        theme_row = self._build_combo_row(tr("Theme:"), self.theme_combo)

        # Neon colour selection - only visible when Neon is active
        self.neon_color_combo = QtWidgets.QComboBox()
        for color in NEON_COLORS:
            self.neon_color_combo.addItem(tr(color), color)
        self._select_data(
            self.neon_color_combo, self._settings.get("neon_color", DEFAULT_NEON_COLOR)
        )
        self.neon_color_combo.currentIndexChanged.connect(
            lambda _index: self._on_neon_color_changed(self.neon_color_combo.currentData())
        )
        neon_row = self._build_combo_row(tr("Neon color:"), self.neon_color_combo)
        neon_row.setVisible(self._settings.get("theme", "Dark") == "Neon")
        self._neon_row = neon_row

        # Quality range selection.  A download is attempted from the max tier
        # downwards and gives up once it drops past the min tier, so the two
        # combos together bound which resolutions are acceptable.
        self.max_quality_combo, max_quality_row = self._build_quality_row(
            tr("Max quality:"), "max_quality", "1080p"
        )
        self.min_quality_combo, min_quality_row = self._build_quality_row(
            tr("Min quality:"), "min_quality", "360p"
        )
        self.max_quality_combo.currentTextChanged.connect(self._on_max_quality_changed)
        self.min_quality_combo.currentTextChanged.connect(self._on_min_quality_changed)

        # Shutdown when done
        self.toggle_shutdown = self._make_simple_toggle(tr("Shutdown when done"), "shutdown_when_done")

        # Simultaneous downloads row
        sim_dl_box, self.sim_dl_spinbox = self._build_stepper_control(
            minimum=1,
            maximum=20,
            value=self._settings.get("simultaneous_downloads", 3),
            on_change=self._on_sim_dl_changed,
        )
        sim_dl_row = self._build_stepper_row(tr("Simultaneous DLs:"), sim_dl_box)

        # Note shown only when the value is high enough to strain bandwidth-
        # capped hosts (some then drop the odd episode to a lower quality).
        self.sim_dl_note = QtWidgets.QLabel(tr(
            "More than 4 at once can cause occasional quality drops on some "
            "hosts - 3-4 is recommended."
        ))
        self.sim_dl_note.setWordWrap(True)
        self.sim_dl_note.setAlignment(_ctr)
        self.sim_dl_note.setStyleSheet("color: #c98a00; font-size: 10px;")
        self.sim_dl_note.setFixedWidth(220)
        self.sim_dl_note.setVisible(
            self._settings.get("simultaneous_downloads", 3) > 4
        )

        # Download delay row - how long the queue waits between starting one
        # episode and the next, to stay under a host's rate limit.
        delay_box, self.delay_spinbox = self._build_stepper_control(
            minimum=0,
            maximum=300,
            value=self._settings.get("download_delay", 2),
            on_change=self._on_download_delay_changed,
            suffix=" s",
        )
        # The unit lives in the box rather than the label: "Download delay (s):"
        # is wider than the longest label the 200px row can hold and would be
        # clipped mid-word.
        delay_row = self._build_stepper_row(tr("Download delay:"), delay_box)

        # Retries row - how often an episode that found no working combination
        # is sent to the back of the queue and tried again.
        retries_box, self.retries_spinbox = self._build_stepper_control(
            minimum=0,
            maximum=5,
            value=self._settings.get("failed_retries", 1),
            on_change=self._on_failed_retries_changed,
        )
        retries_row = self._build_stepper_row(tr("Retries:"), retries_box)

        # Download path
        path_button = QtWidgets.QPushButton(f"📁  {tr('Set Download Path')}")
        path_button.clicked.connect(self._choose_download_path)

        saved_path = self._settings.get("download_path", "")
        self.path_label = QtWidgets.QLabel(
            _format_path(saved_path) if saved_path else tr("No path set")
        )
        self.path_label.setAlignment(_ctr)
        self.path_label.setStyleSheet("color: gray; font-size: 11px;")

        # Every field shows the same size box, sized for the longest value any
        # of them can reach ("300 s"), in rows of one shared width so the boxes
        # sit at the same offset - and the pickers, toggle and path button take
        # that width too, so the whole tab reads as one column however long the
        # labels of the chosen language are.
        self._align_stepper_widths(
            self.sim_dl_spinbox, self.delay_spinbox, self.retries_spinbox
        )
        self._align_labels(
            app_language_row, theme_row, neon_row, max_quality_row, min_quality_row
        )
        width = self._align_rows(
            app_language_row, theme_row, neon_row, max_quality_row, min_quality_row,
            sim_dl_row, delay_row, retries_row,
        )
        self._fit_toggle_width(self.toggle_shutdown, tr("Shutdown when done"), width)
        path_button.setFixedWidth(max(width, path_button.sizeHint().width()))

        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter | _top)
        layout.addWidget(app_language_row,     alignment=_ctr)
        layout.addWidget(self.app_language_note, alignment=_ctr)
        layout.addSpacing(14)
        layout.addWidget(theme_row,            alignment=_ctr)
        layout.addWidget(self._neon_row,       alignment=_ctr)
        layout.addWidget(max_quality_row,      alignment=_ctr)
        layout.addWidget(min_quality_row,      alignment=_ctr)
        layout.addSpacing(14)
        layout.addWidget(self.toggle_shutdown, alignment=_ctr)
        layout.addSpacing(14)
        layout.addWidget(sim_dl_row,           alignment=_ctr)
        layout.addWidget(self.sim_dl_note,     alignment=_ctr)
        layout.addSpacing(14)
        layout.addWidget(delay_row,            alignment=_ctr)
        layout.addSpacing(14)
        layout.addWidget(retries_row,          alignment=_ctr)
        layout.addSpacing(14)
        layout.addWidget(path_button,          alignment=_ctr)
        layout.addWidget(self.path_label,      alignment=_ctr)
        layout.addStretch()

        return tab

    # ------------------------------------------------------------------
    # Quality-range controls
    # ------------------------------------------------------------------

    def _build_quality_row(
        self, label: str, key: str, default: str
    ) -> tuple[QtWidgets.QComboBox, QtWidgets.QWidget]:
        """Build one ``label: [tier]`` quality row.

        Returns the combo box and its containing row so the caller can connect
        a handler and place the row itself.  The two ends of the quality range
        are laid out identically, so they share this builder.
        """
        combo = QtWidgets.QComboBox()
        combo.addItems(QUALITIES)
        combo.setCurrentText(self._settings.get(key, default))
        return combo, self._build_combo_row(label, combo)

    @staticmethod
    def _build_combo_row(label: str, combo: QtWidgets.QComboBox) -> QtWidgets.QWidget:
        """Wrap a picker in a ``label [picker]`` row.

        The width is left to :meth:`_align_rows`, which sizes the tab's rows
        together.
        """
        row = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(QtWidgets.QLabel(label))
        row_layout.addWidget(combo)
        return row

    @staticmethod
    def _align_labels(*rows: QtWidgets.QWidget) -> None:
        """Give the labels of *rows* one width, so their pickers start at one edge.

        Left to itself each row splits its width between label and picker on
        its own, and labels of different lengths would leave the pickers
        staggered.
        """
        labels = [row.findChild(QtWidgets.QLabel) for row in rows]
        width = max(label.sizeHint().width() for label in labels)
        for label in labels:
            label.setFixedWidth(width)

    @staticmethod
    def _select_data(combo: QtWidgets.QComboBox, value) -> None:
        """Select the entry whose data is *value*; an unknown one keeps the first."""
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    @staticmethod
    def _set_combo_silently(combo: QtWidgets.QComboBox, text: str) -> None:
        """Change a combo's selection without re-entering its own change slot.

        Used when one end of the quality range has to drag the other along;
        without blocking, that programmatic change would fire the opposite
        handler and the two would push each other back and forth.
        """
        combo.blockSignals(True)
        combo.setCurrentText(text)
        combo.blockSignals(False)

    # ------------------------------------------------------------------
    # Stepper controls (Simultaneous DLs, Download delay, Retries)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_stepper_row(label: str, control: QtWidgets.QWidget) -> QtWidgets.QWidget:
        """Wrap a stepper control in a ``label ....... [control]`` row.

        The width is left to :meth:`_align_rows`, which sizes every stepper row
        together.
        """
        row = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(QtWidgets.QLabel(label))
        row_layout.addStretch()
        row_layout.addWidget(control)
        return row

    @staticmethod
    def _align_stepper_widths(*spinboxes: QtWidgets.QSpinBox) -> None:
        """Give every stepper spin box the same width: the widest any of them needs.

        Each field on its own only needs room for its own longest value, but
        fields sat under each other with different box widths read as sloppy,
        so they all take the widest.  Measuring the text (rather than hard-coding
        a pixel width) keeps the longest value readable whatever system font
        and suffix are in play.
        """
        width = 0
        for spinbox in spinboxes:
            metrics = spinbox.fontMetrics()
            for value in (spinbox.minimum(), spinbox.maximum()):
                text = f"{spinbox.prefix()}{value}{spinbox.suffix()}"
                width = max(width, metrics.horizontalAdvance(text))
        width += 16   # the spin box's own padding, plus room for the caret
        for spinbox in spinboxes:
            spinbox.setFixedWidth(width)

    @staticmethod
    def _align_rows(*rows: QtWidgets.QWidget) -> int:
        """Give *rows* one shared width so their boxes line up; return it.

        200px matches the other rows on the tab and is what these normally come
        out at. A label that needs more than that - a wider system font, a
        translated string - widens every row equally instead of being clipped,
        which would also leave the boxes at different offsets since the rows
        are centred.

        Call after :meth:`_align_stepper_widths`, so the boxes are already at
        their final size.
        """
        width = max([_ROW_WIDTH] + [row.sizeHint().width() for row in rows])
        for row in rows:
            row.setFixedWidth(width)
        return width

    def _build_stepper_control(
        self,
        *,
        minimum: int,
        maximum: int,
        value: int,
        on_change,
        suffix: str = "",
    ) -> tuple[QtWidgets.QWidget, QtWidgets.QSpinBox]:
        """Build one numeric field: a borderless spin box with two chevron
        stepper buttons side by side, wrapped in one themed border so it reads
        as a single control.

        The box is left unsized here; pass every spin box built this way to
        :meth:`_align_stepper_widths` so they all end up identical.

        Returns the container and the spin box itself, so the caller can place
        the control and keep a handle on the value.
        """
        spinbox = QtWidgets.QSpinBox()
        spinbox.setMinimum(minimum)
        spinbox.setMaximum(maximum)
        spinbox.setValue(value)
        if suffix:
            spinbox.setSuffix(suffix)
        spinbox.setButtonSymbols(
            QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons
        )
        spinbox.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        spinbox.valueChanged.connect(on_change)
        # The container frame carries the border; the spin box sits flush inside
        # it (override the theme's own border/background for this one widget).
        spinbox.setStyleSheet(
            "QSpinBox { border: none; background: transparent; padding: 2px 0 2px 4px; }"
            "QSpinBox:focus { border: none; }"
        )

        up = _ChevronButton("up")
        down = _ChevronButton("down")
        up.clicked.connect(spinbox.stepUp)
        down.clicked.connect(spinbox.stepDown)

        # Grey the arrows out at the min/max bounds.
        def refresh_arrows(current: int) -> None:
            up.setEnabled(current < spinbox.maximum())
            down.setEnabled(current > spinbox.minimum())

        spinbox.valueChanged.connect(refresh_arrows)
        refresh_arrows(spinbox.value())

        arrows = QtWidgets.QHBoxLayout()
        arrows.setContentsMargins(0, 0, 4, 0)
        arrows.setSpacing(2)
        arrows.addWidget(up)
        arrows.addWidget(down)

        box = QtWidgets.QFrame()
        box.setObjectName("stepperBox")
        box.setFixedHeight(28)
        box.setStyleSheet(
            "#stepperBox { border: 1px solid palette(mid); border-radius: 4px;"
            " background: palette(base); }"
        )
        box_layout = QtWidgets.QHBoxLayout(box)
        box_layout.setContentsMargins(0, 0, 0, 0)
        box_layout.setSpacing(0)
        box_layout.addWidget(spinbox)
        box_layout.addLayout(arrows)

        self._steppers.append((spinbox, up, down))
        return box, spinbox

    # ------------------------------------------------------------------
    # Stepper value highlight
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event):
        """Drop stale stepper highlights on any click outside their chevrons.

        Installed on the application, so it sees the press wherever it lands -
        another stepper's chevron, a toggle, the tab bar - not just the clicks
        that reach this page itself.
        """
        if event.type() == QtCore.QEvent.Type.MouseButtonPress:
            self._clear_stepper_highlight(keep=self._stepper_for_chevron(obj))
        return super().eventFilter(obj, event)

    def _stepper_for_chevron(self, obj) -> QtWidgets.QSpinBox | None:
        """The spin box *obj* steps, or None when it isn't a chevron at all."""
        for spinbox, up, down in self._steppers:
            if obj is up or obj is down:
                return spinbox
        return None

    def _clear_stepper_highlight(self, keep: QtWidgets.QSpinBox | None = None) -> None:
        """Deselect every stepper's value except *keep*'s (the one being used)."""
        for spinbox, _up, _down in self._steppers:
            if spinbox is not keep:
                spinbox.lineEdit().deselect()

    def _build_search_bars_tab(self) -> QtWidgets.QWidget:
        """Per-site search bar toggles + cache toggle, then global cache settings."""
        tab = QtWidgets.QWidget()
        _ctr = QtCore.Qt.AlignmentFlag.AlignCenter
        _top = QtCore.Qt.AlignmentFlag.AlignTop

        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter | _top)

        # --- Per-site grid: Website | Search bar | Caching ---
        _h_style  = "font-size: 11px; font-weight: 600;"
        _left_mid = QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter

        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)

        # Column headers
        h_website = QtWidgets.QLabel(tr("Website"))
        h_website.setStyleSheet(_h_style)
        h_search  = QtWidgets.QLabel(tr("Search bar"))
        h_search.setStyleSheet(_h_style)
        h_search.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        h_cache   = QtWidgets.QLabel(tr("Caching"))
        h_cache.setStyleSheet(_h_style)
        h_cache.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(h_website, 0, 0, _left_mid)
        grid.addWidget(h_search,  0, 1, QtCore.Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(h_cache,   0, 2, QtCore.Qt.AlignmentFlag.AlignCenter)

        # Site rows
        _sites = [
            ("aniworld.to",  "aniworld.to",  "aniworld.to_cache"),
            ("s.to",         "s.to",         "s.to_cache"),
            ("bs.to",        "bs.to",        "bs.to_cache"),
            ("anikototv.to", "anikototv.to", "anikototv.to_cache"),
            ("hanime.tv",    "hanime.tv",    "hanime.tv_cache"),
            ("animepahe.ch", "animepahe.ch", "animepahe.ch_cache"),
        ]
        for i, (site_label, site_key, cache_key) in enumerate(_sites, start=1):
            name_lbl  = QtWidgets.QLabel(site_label)
            site_btn  = self._make_bare_toggle(site_key,  notify_site=True)
            cache_btn = self._make_bare_toggle(cache_key, notify_cache=True)
            setattr(self, "toggle_"       + site_key.replace(".", "_"), site_btn)
            setattr(self, "toggle_cache_" + site_key.replace(".", "_"), cache_btn)
            grid.addWidget(name_lbl,  i, 0, _left_mid)
            grid.addWidget(site_btn,  i, 1, QtCore.Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(cache_btn, i, 2, QtCore.Qt.AlignmentFlag.AlignCenter)

        grid_container = QtWidgets.QWidget()
        grid_container.setLayout(grid)
        layout.addWidget(grid_container, alignment=_ctr)

        # --- Separator ---
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        sep.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        layout.addSpacing(6)
        layout.addWidget(sep)
        layout.addSpacing(6)

        # --- Global: cache duration row ---
        # Same chevron stepper as Simultaneous DLs and Download delay, so every
        # numeric field in Settings looks and behaves the same.  Its width is
        # measured on its own rather than shared with the General tab's pair:
        # "365 days" is the longest value here and would bloat those two boxes
        # for no reason, and the tabs are never on screen together anyway.
        cache_days_box, self.cache_days_spinbox = self._build_stepper_control(
            minimum=1,
            maximum=365,
            value=self._settings.get("cache_days", 7),
            on_change=self._on_cache_days_changed,
            suffix=f" {tr('days')}",
        )
        cache_days_row = self._build_stepper_row(tr("Cache duration:"), cache_days_box)
        self._align_stepper_widths(self.cache_days_spinbox)
        self._align_rows(cache_days_row)
        layout.addWidget(cache_days_row, alignment=_ctr)

        layout.addStretch()
        return tab

    def _build_providers_tab(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        self.provider_list = PriorityList(
            self._settings, key="providers", label=tr("Providers")
        )
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignTop
        )
        layout.addWidget(self.provider_list, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()
        return tab

    def _build_languages_tab(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        self.language_list = PriorityList(
            self._settings, key="languages", label=tr("Languages")
        )
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignTop
        )
        layout.addWidget(self.language_list, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()
        return tab

    def _build_support_tab(self) -> QtWidgets.QWidget:
        """One button per SUPPORT_LINKS entry, opening it in the browser.

        Each address is printed under its button as well, selectable, so it can
        be copied or passed on without opening it.
        """
        tab = QtWidgets.QWidget()
        _ctr = QtCore.Qt.AlignmentFlag.AlignCenter

        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(4)
        layout.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignTop
        )

        intro = QtWidgets.QLabel(tr(
            "Need help, found a bug or have an idea?  Get in touch on Discord, "
            "or find the source code and the latest version below."
        ))
        intro.setWordWrap(True)
        intro.setAlignment(_ctr)
        intro.setFixedWidth(320)
        intro.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(intro, alignment=_ctr)
        layout.addSpacing(14)

        for name, purpose, url in SUPPORT_LINKS:
            button = QtWidgets.QPushButton(f"{name}  ↗")
            button.setFixedWidth(200)
            button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            button.setToolTip(url)
            # clicked passes checked:bool first - absorb it so url stays bound.
            button.clicked.connect(
                lambda _checked=False, u=url: QtGui.QDesktopServices.openUrl(QtCore.QUrl(u))
            )

            purpose_label = QtWidgets.QLabel(tr(purpose))
            purpose_label.setAlignment(_ctr)
            purpose_label.setStyleSheet("font-size: 11px;")

            address = QtWidgets.QLabel(url.removeprefix("https://"))
            address.setAlignment(_ctr)
            address.setStyleSheet("color: gray; font-size: 11px;")
            address.setTextInteractionFlags(
                QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
            )

            layout.addWidget(button, alignment=_ctr)
            layout.addWidget(purpose_label, alignment=_ctr)
            layout.addWidget(address, alignment=_ctr)
            layout.addSpacing(14)

        layout.addStretch()
        return tab

    # ------------------------------------------------------------------
    # Toggle helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _toggle_text(label: str, checked: bool) -> str:
        """A labelled toggle's text, e.g. ``"  Shutdown when done  ON"``."""
        return f"  {label}  {tr('ON') if checked else tr('OFF')}"

    def _fit_toggle_width(self, btn: QtWidgets.QPushButton, label: str,
                          minimum: int = _ROW_WIDTH) -> None:
        """Size a labelled toggle for the longer of its two texts, at least *minimum*.

        Fixed rather than left to follow the text, so the button keeps its
        width as it flips between ON and OFF - which differ in length once
        translated.
        """
        metrics = btn.fontMetrics()
        widest = max(metrics.horizontalAdvance(self._toggle_text(label, state))
                     for state in (True, False))
        # TOGGLE_STYLE's 16px padding on each side and its border, plus air.
        btn.setFixedWidth(max(minimum, widest + 40))

    def _make_toggle(self, label: str, key: str) -> QtWidgets.QPushButton:
        btn = QtWidgets.QPushButton(self._toggle_text(label, False))
        btn.setCheckable(True)
        btn.setStyleSheet(TOGGLE_STYLE)
        self._fit_toggle_width(btn, label)
        # Connect before setChecked so a saved True restores the label correctly
        btn.toggled.connect(
            lambda checked, b=btn, k=key, l=label: self._on_toggle(b, k, l, checked)
        )
        btn.setChecked(self._settings[key])
        return btn

    def _on_toggle(self, btn: QtWidgets.QPushButton, key: str, label: str, checked: bool):
        self._settings[key] = checked
        btn.setText(self._toggle_text(label, checked))
        settings_manager.save(self._settings)
        if self._on_site_toggle is not None:
            self._on_site_toggle(key, checked)

    def _make_simple_toggle(self, label: str, key: str) -> QtWidgets.QPushButton:
        """Toggle that only saves to settings - does not fire _on_site_toggle."""
        btn = QtWidgets.QPushButton(self._toggle_text(label, False))
        btn.setCheckable(True)
        btn.setStyleSheet(TOGGLE_STYLE)
        self._fit_toggle_width(btn, label)
        btn.toggled.connect(
            lambda checked, b=btn, k=key, l=label: self._on_simple_toggle(b, k, l, checked)
        )
        btn.setChecked(self._settings.get(key, False))
        return btn

    def _on_simple_toggle(self, btn: QtWidgets.QPushButton, key: str, label: str, checked: bool):
        self._settings[key] = checked
        btn.setText(self._toggle_text(label, checked))
        settings_manager.save(self._settings)

    def _make_bare_toggle(self, key: str, notify_site: bool = False, notify_cache: bool = False) -> QtWidgets.QPushButton:
        """Compact ON/OFF toggle for grid layouts - no label embedded in the button text."""
        btn = QtWidgets.QPushButton(tr("OFF"))
        btn.setCheckable(True)
        btn.setStyleSheet(TOGGLE_BARE_STYLE)
        # 70px fits ON/OFF in every language shipped; measured all the same, in
        # case a translation ever runs longer.
        metrics = btn.fontMetrics()
        btn.setFixedWidth(max(70, 16 + max(metrics.horizontalAdvance(tr("ON")),
                                          metrics.horizontalAdvance(tr("OFF")))))
        if notify_site:
            btn.toggled.connect(
                lambda checked, b=btn, k=key: self._on_bare_site_toggle(b, k, checked)
            )
        elif notify_cache:
            btn.toggled.connect(
                lambda checked, b=btn, k=key: self._on_bare_cache_toggle(b, k, checked)
            )
        else:
            btn.toggled.connect(
                lambda checked, b=btn, k=key: self._on_bare_toggle(b, k, checked)
            )
        btn.setChecked(self._settings.get(key, False))
        return btn

    def _on_bare_toggle(self, btn: QtWidgets.QPushButton, key: str, checked: bool):
        self._settings[key] = checked
        btn.setText(tr("ON") if checked else tr("OFF"))
        settings_manager.save(self._settings)

    def _on_bare_site_toggle(self, btn: QtWidgets.QPushButton, key: str, checked: bool):
        self._on_bare_toggle(btn, key, checked)
        if self._on_site_toggle is not None:
            self._on_site_toggle(key, checked)

    def _on_bare_cache_toggle(self, btn: QtWidgets.QPushButton, key: str, checked: bool):
        self._on_bare_toggle(btn, key, checked)
        if self._on_cache_toggle is not None:
            # key is e.g. "aniworld.to_cache" - strip the suffix to get the site name
            site = key.removesuffix("_cache")
            self._on_cache_toggle(site, checked)

    def _on_app_language_changed(self, _index: int) -> None:
        self._settings["app_language"] = self.app_language_combo.currentData()
        settings_manager.save(self._settings)
        self._update_app_language_note()

    def _update_app_language_note(self) -> None:
        """Say the picked language applies from the next start - in that language.

        Hidden again when the pick goes back to the language already running,
        since then there is nothing to wait for.
        """
        picked = self.app_language_combo.currentData()
        self.app_language_note.setText(i18n.translate(
            "Restart Aniloader to switch to this language.", picked
        ))
        self.app_language_note.setVisible(picked != i18n.current_language())

    def _on_theme_changed(self, theme: str) -> None:
        self._settings["theme"] = theme
        settings_manager.save(self._settings)
        self._neon_row.setVisible(theme == "Neon")
        apply_theme(self._settings)

    def _on_neon_color_changed(self, color: str) -> None:
        self._settings["neon_color"] = color
        settings_manager.save(self._settings)
        apply_theme(self._settings)

    # QUALITIES runs highest → lowest, so a *larger* index means a *lower*
    # resolution and a valid range always has index(max) <= index(min).
    # Whichever end the user moves, the other is dragged along to keep that
    # true, rather than rejecting the choice they just made.

    def _on_max_quality_changed(self, quality: str) -> None:
        self._settings["max_quality"] = quality
        if QUALITIES.index(quality) > QUALITIES.index(self.min_quality_combo.currentText()):
            # The new maximum sits below the minimum - pull the minimum down.
            self._set_combo_silently(self.min_quality_combo, quality)
            self._settings["min_quality"] = quality
        settings_manager.save(self._settings)

    def _on_min_quality_changed(self, quality: str) -> None:
        self._settings["min_quality"] = quality
        if QUALITIES.index(quality) < QUALITIES.index(self.max_quality_combo.currentText()):
            # The new minimum sits above the maximum - push the maximum up.
            self._set_combo_silently(self.max_quality_combo, quality)
            self._settings["max_quality"] = quality
        settings_manager.save(self._settings)

    def _on_sim_dl_changed(self, value: int):
        self._settings["simultaneous_downloads"] = value
        settings_manager.save(self._settings)
        if hasattr(self, "sim_dl_note"):
            self.sim_dl_note.setVisible(value > 4)

    def _on_download_delay_changed(self, value: int):
        self._settings["download_delay"] = value
        settings_manager.save(self._settings)

    def _on_failed_retries_changed(self, value: int):
        self._settings["failed_retries"] = value
        settings_manager.save(self._settings)

    def _on_cache_days_changed(self, value: int):
        self._settings["cache_days"] = value
        settings_manager.save(self._settings)

    # ------------------------------------------------------------------
    # Focus handling
    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        """Clicking empty space clears focus from the spinbox (and any other widget)."""
        self.setFocus()
        super().mousePressEvent(event)

    # ------------------------------------------------------------------
    # Download path
    # ------------------------------------------------------------------

    def _choose_download_path(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(self, tr("Select Download Folder"))
        if path:
            self._settings["download_path"] = path
            self.path_label.setText(_format_path(path))
            settings_manager.save(self._settings)