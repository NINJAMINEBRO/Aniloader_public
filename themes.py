"""Application-wide theme engine.

Provides three themes - Dark, Light, Neon - applied via QPalette + QSS.
The Neon theme supports a user-selectable accent colour.

Usage::

    from themes import apply_theme
    apply_theme(settings_state) # call on startup and on any theme change
"""

from PySide6 import QtWidgets, QtGui

# Available neon accent colours {display name: hex}
NEON_COLORS: dict[str, str] = {
    "Aqua":   "#00F7FF",
    "Green":  "#39FF14",
    "Pink":   "#FF007F",
    "Purple": "#BD00FF",
    "Orange": "#FF5C00",
    "Yellow": "#FFFF00",
    "Blue":   "#1F51FF",
    "Red":    "#FF073A",
    "White":  "#FAFAFF",
}

DEFAULT_NEON_COLOR = "Aqua"


# ------------------------------------------------------------------
# Palette builders
# ------------------------------------------------------------------

def _pal(**kw) -> QtGui.QPalette:
    """Build a QPalette from keyword args mapping short names to hex strings."""
    _ROLES = {
        "window":           QtGui.QPalette.ColorRole.Window,
        "window_text":      QtGui.QPalette.ColorRole.WindowText,
        "base":             QtGui.QPalette.ColorRole.Base,
        "alt_base":         QtGui.QPalette.ColorRole.AlternateBase,
        "text":             QtGui.QPalette.ColorRole.Text,
        "button":           QtGui.QPalette.ColorRole.Button,
        "button_text":      QtGui.QPalette.ColorRole.ButtonText,
        "highlight":        QtGui.QPalette.ColorRole.Highlight,
        "highlighted_text": QtGui.QPalette.ColorRole.HighlightedText,
        "mid":              QtGui.QPalette.ColorRole.Mid,
        "midlight":         QtGui.QPalette.ColorRole.Midlight,
        "bright_text":      QtGui.QPalette.ColorRole.BrightText,
        "link":             QtGui.QPalette.ColorRole.Link,
        "tooltip_base":     QtGui.QPalette.ColorRole.ToolTipBase,
        "tooltip_text":     QtGui.QPalette.ColorRole.ToolTipText,
        "placeholder_text": QtGui.QPalette.ColorRole.PlaceholderText,
    }
    p = QtGui.QPalette()
    for name, hex_val in kw.items():
        if name in _ROLES:
            p.setColor(_ROLES[name], QtGui.QColor(hex_val))
    return p


def _dark_palette() -> QtGui.QPalette:
    return _pal(
        window="#1e1e2e",       window_text="#cdd6f4",
        base="#313244",         alt_base="#181825",
        text="#cdd6f4",
        button="#313244",       button_text="#cdd6f4",
        highlight="#89b4fa",    highlighted_text="#1e1e2e",
        mid="#45475a",          midlight="#585b70",
        bright_text="#ffffff",  link="#89b4fa",
        tooltip_base="#313244", tooltip_text="#cdd6f4",
        placeholder_text="#585b70",
    )


def _light_palette() -> QtGui.QPalette:
    return _pal(
        window="#f5f5f7",       window_text="#1d1d1f",
        base="#ffffff",         alt_base="#f0f0f2",
        text="#1d1d1f",
        button="#e5e5ea",       button_text="#1d1d1f",
        highlight="#0071e3",    highlighted_text="#ffffff",
        mid="#c7c7cc",          midlight="#d5d5da",
        bright_text="#000000",  link="#0071e3",
        tooltip_base="#ffffff", tooltip_text="#1d1d1f",
        placeholder_text="#a0a0a5",
    )


def _neon_palette(color: str) -> QtGui.QPalette:
    return _pal(
        window="#0a0a0f",       window_text="#e0e0e0",
        base="#111118",         alt_base="#08080d",
        text="#e0e0e0",
        button="#111118",       button_text="#e0e0e0",
        highlight=color,        highlighted_text="#0a0a0f",
        mid="#1c1c28",          midlight="#242434",
        bright_text="#ffffff",  link=color,
        tooltip_base="#111118", tooltip_text="#e0e0e0",
        placeholder_text="#3a3a55",
    )


# ------------------------------------------------------------------
# QSS helpers
# ------------------------------------------------------------------

def _rgba(hex_color: str, alpha: float) -> str:
    """Convert ``#rrggbb`` + alpha (0-1) to a CSS ``rgba()`` string."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha:.2f})"


# Shared template - Python double-brace escaping for CSS braces.
_BASE_QSS = """\
QTabWidget::pane {{
    border: 1px solid {border};
}}
QTabBar::tab {{
    background: {tab_bg};
    color: {tab_fg};
    padding: 6px 16px;
    border: 1px solid {border};
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background: {win};
    color: {accent};
}}
QTabBar::tab:hover:!selected {{
    background: {tab_hover};
}}
QScrollBar:vertical {{
    background: {win};
    width: 8px;
    border: none;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {scroll};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {scroll_hover};
}}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0;
    border: none;
}}
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{
    background: none;
}}
QLineEdit, QSpinBox, QComboBox {{
    background-color: palette(base);
    color: palette(text);
    border: 1px solid {border};
    border-radius: 4px;
    padding: 3px 7px;
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border: 1px solid {accent};
}}
QComboBox::drop-down {{
    border: none;
    width: 18px;
}}
QComboBox QAbstractItemView {{
    border: 1px solid {border};
    outline: none;
}}
QListView#searchCompleterPopup {{
    background-color: palette(base);
    color: palette(text);
    border: 1px solid {border};
    padding: 4px;
    outline: none;
}}
"""

_DARK_QSS = _BASE_QSS.format(
    win="#1e1e2e",  border="#45475a",   accent="#89b4fa",
    tab_bg="#313244",  tab_fg="#9399b2",  tab_hover="#45475a",
    scroll="#45475a",  scroll_hover="#585b70",
)

_LIGHT_QSS = _BASE_QSS.format(
    win="#f5f5f7",  border="#c7c7cc",   accent="#0071e3",
    tab_bg="#e5e5ea",  tab_fg="#6e6e73",  tab_hover="#d5d5da",
    scroll="#c7c7cc",  scroll_hover="#a0a0a5",
)


def _neon_qss(color: str) -> str:
    border = _rgba(color, 0.35)
    glow   = _rgba(color, 0.12)
    return _BASE_QSS.format(
        win="#0a0a0f",  border=border,  accent=color,
        tab_bg="#111118",  tab_fg="#55556a",  tab_hover="#1c1c28",
        scroll=border,  scroll_hover=color,
    ) + f"""\
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border: 1px solid {color};
    background-color: {glow};
}}
"""


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def apply_theme(settings: dict) -> None:
    """Apply the active theme to the running QApplication.

    Switches to the Fusion style so QPalette colours are respected on
    all platforms.  Safe to call multiple times (e.g. on every change).
    """
    app = QtWidgets.QApplication.instance()
    if app is None:
        return

    app.setStyle("Fusion")

    theme = settings.get("theme", "Dark")
    if theme == "Light":
        app.setPalette(_light_palette())
        app.setStyleSheet(_LIGHT_QSS)
    elif theme == "Neon":
        color_name = settings.get("neon_color", DEFAULT_NEON_COLOR)
        color_hex  = NEON_COLORS.get(color_name, NEON_COLORS[DEFAULT_NEON_COLOR])
        app.setPalette(_neon_palette(color_hex))
        app.setStyleSheet(_neon_qss(color_hex))
    else:  # "Dark" - also the fallback for unknown values
        app.setPalette(_dark_palette())
        app.setStyleSheet(_DARK_QSS)