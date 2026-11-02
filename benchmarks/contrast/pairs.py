"""Spike for PR E: measure the contrast of the colour pairs the application really uses.

Pure arithmetic over (a) Qt's own palette in each look, read on the real Windows platform, and
(b) the theme's literal table against the surfaces it sits on. No window is shown.
"""
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from openchem.ui import theme

app = QApplication(sys.argv)
print("platform:", app.platformName(), "style:", app.style().objectName())

R = QPalette.ColorRole
G = QPalette.ColorGroup
roles = [
    ("Text on Window", R.WindowText, R.Window, 4.5),
    ("Text on Base", R.Text, R.Base, 4.5),
    ("ButtonText on Button", R.ButtonText, R.Button, 4.5),
    ("HighlightedText on Highlight", R.HighlightedText, R.Highlight, 4.5),
    ("Link on Window", R.Link, R.Window, 4.5),
    ("PlaceholderText on Base", R.PlaceholderText, R.Base, 4.5),
    ("ToolTipText on ToolTipBase", R.ToolTipText, R.ToolTipBase, 4.5),
    ("Mid (border) on Window", R.Mid, R.Window, 3.0),
    ("Dark (border) on Window", R.Dark, R.Window, 3.0),
    ("Highlight (focus/selection) on Window", R.Highlight, R.Window, 3.0),
    ("Highlight on Base", R.Highlight, R.Base, 3.0),
]
for scheme in (Qt.ColorScheme.Light, Qt.ColorScheme.Dark):
    app.styleHints().setColorScheme(scheme)
    app.processEvents()
    pal = app.palette()
    print(f"\n== {scheme.name} (palette read from Qt) ==")
    for label, fg, bg, need in roles:
        a, b = pal.color(G.Active, fg), pal.color(G.Active, bg)
        r = theme.contrast(a, b)
        print(f"  {label:40s} {a.name()} on {b.name()}  {r:5.2f}  need {need}  {'ok' if r >= need else 'FAIL'}")
    for label, fg, bg, need in (
        ("DISABLED text on Window", R.WindowText, R.Window, None),
        ("DISABLED text on Base", R.Text, R.Base, None),
        ("DISABLED button text", R.ButtonText, R.Button, None),
    ):
        a, b = pal.color(G.Disabled, fg), pal.color(G.Disabled, bg)
        print(f"  {label:40s} {a.name()} on {b.name()}  {theme.contrast(a, b):5.2f}  (no WCAG minimum: inactive)")

print("\n== theme literals (text colours the theme maps) ==")
light_surfaces = ["#ffffff", "#f3f3f3"]
dark_surfaces = ["#1e1e1e", "#2d2d2d"]
for light, dark in sorted(theme.dark_values().items()):
    rl = min(theme.contrast(light, s) for s in light_surfaces)
    rd = min(theme.contrast(dark, s) for s in dark_surfaces)
    print(f"  {light} light {rl:5.2f} {'ok' if rl >= 4.5 else 'FAIL'} | {dark} dark {rd:5.2f} {'ok' if rd >= 4.5 else 'FAIL'}")
