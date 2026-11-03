"""Render the real window's menus with their icons, in Light and Dark, and print what each icon painted.

Run on the real Windows platform (the offscreen platform ignores a forced colour scheme):

    uv run --no-sync python -I benchmarks/menu_icons/render_menus.py OUTPUT_DIR [DEVICE_PIXEL_RATIO]

Writes `<menu>-<look>.png` for File, Edit and Help, grabbed from the menu widgets themselves and magnified 3x
with smooth scaling off, so a one-pixel misalignment stays visible. Prints, per menu, each icon entry's text, its
icon column width and the ink pixels the icon painted (an icon that painted nothing is a defect), and for the
Edit menu the same for Undo/Redo with the stack empty (both disabled).
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from openchem.app import menu_layout
from openchem.app.main_window import MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.domain.appearance import EffectiveAppearance
from openchem.ui import theme


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="menu_icons_"))
    out.mkdir(parents=True, exist_ok=True)
    if len(sys.argv) > 2:
        os.environ["QT_SCALE_FACTOR"] = sys.argv[2]
    app = QApplication(sys.argv[:1])
    print("platform:", app.platformName(), "style:", app.style().objectName())
    services = build_service_container()
    settings = Settings(services.event_bus)
    with tempfile.TemporaryDirectory() as scratch:
        settings.set("plugins/project_directory", scratch)
        settings.set("plugins/user_directory", scratch)
        window = MainWindow(services, settings, SessionManager())
        keep = []
        for scheme, look in ((Qt.ColorScheme.Light, EffectiveAppearance.LIGHT), (Qt.ColorScheme.Dark, EffectiveAppearance.DARK)):
            app.styleHints().setColorScheme(scheme)
            app.processEvents()
            theme.set_effective(look)
            for top in window.menuBar().actions():
                title = menu_layout.label_of(top)
                if title not in ("File", "Edit", "Help", "Tools"):
                    continue
                menu = top.menu()
                keep.append(top)
                menu.popup(QPoint(40, 40))
                app.processEvents()
                image = menu.grab().toImage()
                scaled = image.scaled(image.width() * 3, image.height() * 3, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
                path = out / f"{title.lower()}-{look.name.lower()}.png"
                scaled.save(str(path))
                icons = [a for a in menu.actions() if not a.icon().isNull()]
                for action in icons:
                    geom = menu.actionGeometry(action)
                    ink = 0
                    for x in range(geom.left(), geom.left() + 28):
                        for y in range(geom.top(), geom.bottom() + 1):
                            if x < image.width() and image.pixelColor(x, y).name() != image.pixelColor(geom.right() - 4, y).name():
                                ink += 1
                    print(f"{look.name:5s} {title:5s} {menu_layout.label_of(action):28s} enabled={action.isEnabled()!s:5s} ink_px_left={ink}")
                print(f"{look.name:5s} {title:5s} {len(icons)} icons of {len([a for a in menu.actions() if not a.isSeparator()])} entries -> {path}")
                menu.hide()
        window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
