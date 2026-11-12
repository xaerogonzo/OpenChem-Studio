"""The icon and installer artwork the spec and Setup script name must exist and be the right size.

A missing file would not fail loudly: PyInstaller with a bad icon path stops, but Inno's wizard
image error appears only when the installer is compiled, and the window icon silently falls
back to Qt's default. This keeps all three honest.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent


def test_icon_has_every_size_windows_asks_for():
    with Image.open(ROOT / "packaging" / "icon.ico") as icon:
        sizes = set(icon.info.get("sizes", set()))
    assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= sizes


def test_window_icon_is_square():
    with Image.open(ROOT / "src" / "openchem" / "resources" / "branding" / "app_icon.png") as image:
        assert image.width == image.height >= 128


def test_wizard_images_have_inno_sizes():
    folder = ROOT / "packaging" / "installer"
    for name, size in (
        ("wizard_large.bmp", (164, 314)),
        ("wizard_large_2x.bmp", (328, 628)),
        ("wizard_small.bmp", (55, 55)),
        ("wizard_small_2x.bmp", (110, 110)),
    ):
        with Image.open(folder / name) as image:
            assert image.size == size, name


def test_spec_and_setup_script_name_files_that_exist():
    spec = (ROOT / "packaging" / "openchem.spec").read_text(encoding="utf-8")
    script = (ROOT / "packaging" / "openchem.iss").read_text(encoding="utf-8")
    assert 'ROOT / "packaging" / "icon.ico"' in spec
    for needle in ("icon.ico", "wizard_large.bmp", "wizard_large_2x.bmp", "wizard_small.bmp", "wizard_small_2x.bmp"):
        assert needle in script
