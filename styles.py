ENTRY_ERROR_STYLE = "border: 1px solid #e74c3c;"
ENTRY_NORMAL_STYLE = ""

TOGGLE_BARE_STYLE = """
    QPushButton {
        background-color: palette(button);
        color: palette(button-text);
        border: 1px solid palette(mid);
        border-radius: 4px;
        padding: 6px 4px;
        text-align: center;
    }
    QPushButton:checked {
        background-color: #166034;
        color: white;
        border: 1px solid #27ae60;
    }
    QPushButton:hover {
        border: 1px solid palette(highlight);
    }
    QPushButton:checked:hover {
        background-color: #166034;
    }
"""

TOGGLE_STYLE = """
    QPushButton {
        background-color: palette(button);
        color: palette(button-text);
        border: 1px solid palette(mid);
        border-radius: 4px;
        padding: 6px 16px;
        min-width: 180px;
        text-align: left;
    }
    QPushButton:checked {
        background-color: #166034;
        color: white;
        border: 1px solid #27ae60;
    }
    QPushButton:hover {
        border: 1px solid palette(highlight);
    }
    QPushButton:checked:hover {
        background-color: #166034;
    }
"""
