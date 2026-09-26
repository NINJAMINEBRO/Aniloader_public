from PySide6 import QtWidgets, QtCore, QtGui


class TitleDelegate(QtWidgets.QStyledItemDelegate):
    """Renders each completer row as:
       Title text (left) - site.name (right, muted)

    The completer model stores URLs as its item strings (guaranteeing
    uniqueness even when two sites share the same title).  This delegate
    resolves the URL back to a human-readable title and site label via the
    two live dicts passed in - no extra signalling required.
    """

    _MARGIN = 8
    _ROW_HEIGHT = 32  # slightly taller than the Qt default (~22 px)

    def __init__(self, url_titles: dict, url_to_site: dict, parent=None):
        super().__init__(parent)
        self._url_titles = url_titles
        self._url_to_site = url_to_site

    def paint(self, painter, option, index):
        self.initStyleOption(option, index)

        # The model item string is a URL; resolve it before drawing.
        url = option.text
        option.text = ""
        titles = self._url_titles.get(url, [])
        title = titles[0] if titles else url
        site = self._url_to_site.get(url, "")

        # CE_ItemViewItem is the full item control: it handles hover highlight,
        # selection colour, focus rect, and every other native state correctly.
        style = option.widget.style() if option.widget else QtWidgets.QApplication.style()
        style.drawControl(
            QtWidgets.QStyle.ControlElement.CE_ItemViewItem,
            option, painter, option.widget,
        )

        rect = option.rect
        m = self._MARGIN
        fm = painter.fontMetrics()
        selected = bool(option.state & QtWidgets.QStyle.StateFlag.State_Selected)

        # Site label - right-aligned, muted colour
        site_w = fm.horizontalAdvance(site)
        if selected:
            site_color = QtGui.QColor(option.palette.highlightedText().color())
            site_color.setAlphaF(0.55)
        else:
            site_color = QtGui.QColor("#888888")
        painter.save()
        painter.setPen(site_color)
        painter.drawText(
            rect.adjusted(0, 0, -m, 0),
            QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter,
            site,
        )
        painter.restore()

        # Title - left-aligned, clipped so it never overlaps the site label
        title_rect = rect.adjusted(m, 0, -(site_w + m * 3), 0)
        painter.save()
        if selected:
            painter.setPen(option.palette.highlightedText().color())
        else:
            painter.setPen(option.palette.text().color())
        painter.drawText(
            title_rect,
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter,
            fm.elidedText(title, QtCore.Qt.TextElideMode.ElideRight, title_rect.width()),
        )
        painter.restore()

    def sizeHint(self, option, index):
        return QtCore.QSize(super().sizeHint(option, index).width(), self._ROW_HEIGHT)
