"""Does an application palette change reach the borders Qt's windows11 style draws?

Renders a few controls in the dark scheme with Qt's own palette and with Mid/Dark/Light raised,
and prints the edge pixels. If the edge does not move, a palette-only 'increased contrast' cannot
lift control borders and would need per-widget stylesheets.
"""
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QPushButton, QVBoxLayout, QWidget

from openchem.ui import theme

app = QApplication(sys.argv)
app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
app.processEvents()


def render():
    box = QWidget()
    lay = QVBoxLayout(box)
    for w in (QLineEdit("text"), QPushButton("button"), QComboBox()):
        lay.addWidget(w)
    box.resize(240, 160)
    box.show()
    app.processEvents()
    out = {}
    for name, w in (("lineedit", lay.itemAt(0).widget()), ("button", lay.itemAt(1).widget()), ("combo", lay.itemAt(2).widget())):
        img = w.grab().toImage()
        out[name] = [img.pixelColor(img.width() // 2, y).name() for y in (0, 1, 2)] + ["bg", img.pixelColor(img.width() // 2, img.height() // 2).name()]
    window = box.palette().color(QPalette.ColorRole.Window)
    box.close()
    return out, window


before, win = render()
print("window", win.name())
for k, v in before.items():
    print("  default ", k, v, "edge contrast vs window %.2f" % theme.contrast(v[0], win.name()))

pal = QPalette(app.palette())
for role in (QPalette.ColorRole.Mid, QPalette.ColorRole.Dark, QPalette.ColorRole.Midlight, QPalette.ColorRole.Light, QPalette.ColorRole.Shadow):
    pal.setColor(role, QColor("#ffffff"))
app.setPalette(pal)
app.processEvents()
after, win = render()
for k, v in after.items():
    print("  raised  ", k, v, "edge contrast vs window %.2f" % theme.contrast(v[0], win.name()))
print("edges moved:", {k: before[k][:3] != after[k][:3] for k in before})
