from PySide6 import QtWidgets
from menu import MyWidget as Menu
import sys
import updater

if __name__ == '__main__':
    # If this launch came from an update, the build it replaced is still sat
    # next to us -s delete it now that nothing is running from it.
    updater.cleanup_previous_build()

    app = QtWidgets.QApplication([])

    widget = Menu()
    widget.resize(800, 600)
    widget.show()

    sys.exit(app.exec())
