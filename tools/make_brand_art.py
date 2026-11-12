"""Draw OpenChem Studio's icon and installer artwork. Original art, drawn here with Pillow,
so there is no third-party image licence to track.

    uv run --no-sync python tools/make_brand_art.py

Writes (all committed; the build does not run this):
  packaging/icon.ico                          the exe's icon (16 to 256 px)
  src/openchem/resources/branding/app_icon.png  the window icon the running program sets
  packaging/installer/wizard_large[_2x].bmp   the Setup / Uninstall side panel
  packaging/installer/wizard_small[_2x].bmp   the Setup header corner
"""

from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
BIG = 1024  # drawn at this size, then reduced, so edges are smooth

TOP, BOTTOM = (20, 78, 110), (8, 30, 52)  # deep teal to navy
GLASS = (235, 247, 252)
LIQUID_A, LIQUID_B = (64, 224, 208), (30, 150, 200)


def _gradient(size: int, top, bottom) -> Image.Image:
    img = Image.new("RGB", (size, size), top)
    px = img.load()
    for y in range(size):
        t = y / (size - 1)
        row = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        for x in range(size):
            px[x, y] = row
    return img


def _hexagon(draw: ImageDraw.ImageDraw, cx, cy, r, **kw) -> None:
    pts = [(cx + r * math.cos(math.radians(60 * i + 30)), cy + r * math.sin(math.radians(60 * i + 30))) for i in range(6)]
    draw.polygon(pts, **kw)


def flask_mark(size: int = BIG, with_background: bool = True) -> Image.Image:
    """An Erlenmeyer flask holding liquid and a benzene ring, on a rounded teal tile."""
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    if with_background:
        tile = _gradient(s, TOP, BOTTOM).convert("RGBA")
        mask = Image.new("L", (s, s), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=255)
        img.paste(tile, (0, 0), mask)

    def p(x, y):  # unit square -> pixels
        return (x * s, y * s)

    # Flask outline: neck at the top, widening to a flat base.
    outline = [p(0.40, 0.17), p(0.40, 0.42), p(0.19, 0.78), p(0.19, 0.83), p(0.25, 0.87),
               p(0.75, 0.87), p(0.81, 0.83), p(0.81, 0.78), p(0.60, 0.42), p(0.60, 0.17)]
    # Liquid: the lower part of the same shape, clipped by the flask.
    liquid = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ld = ImageDraw.Draw(liquid)
    ld.rectangle([0, int(0.56 * s), s, s], fill=LIQUID_B + (255,))
    ld.rectangle([0, int(0.56 * s), s, int(0.60 * s)], fill=LIQUID_A + (255,))
    clip = Image.new("L", (s, s), 0)
    ImageDraw.Draw(clip).polygon(outline, fill=255)
    img.paste(liquid, (0, 0), clip)

    d = ImageDraw.Draw(img)
    w = int(s * 0.035)
    d.line(outline + [outline[0]], fill=GLASS + (255,), width=w, joint="curve")
    for x, y in outline:  # round the joints
        d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=GLASS + (255,))
    d.line([p(0.36, 0.17), p(0.64, 0.17)], fill=GLASS + (255,), width=w)  # lip
    # Benzene ring in the liquid, with its alternating double bonds.
    cx, cy, r = 0.5 * s, 0.72 * s, 0.085 * s
    _hexagon(d, cx, cy, r, outline=(255, 255, 255, 255), width=int(s * 0.016))
    _hexagon(d, cx, cy, r * 0.62, outline=(255, 255, 255, 170), width=int(s * 0.010))
    # Bubbles.
    for bx, by, br in ((0.40, 0.64, 0.018), (0.60, 0.67, 0.014), (0.47, 0.50, 0.020), (0.55, 0.40, 0.012)):
        d.ellipse([(bx - br) * s, (by - br) * s, (bx + br) * s, (by + br) * s], outline=(255, 255, 255, 210), width=int(s * 0.008))
    return img


def _write_icon() -> None:
    mark = flask_mark()
    sizes = [16, 24, 32, 48, 64, 128, 256]
    ico = ROOT / "packaging" / "icon.ico"
    mark.resize((256, 256), Image.LANCZOS).save(ico, format="ICO", sizes=[(n, n) for n in sizes])
    png = ROOT / "src" / "openchem" / "resources" / "branding" / "app_icon.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    mark.resize((256, 256), Image.LANCZOS).save(png)


def _molecule_field(w: int, h: int, seed: int) -> Image.Image:
    """A navy panel with a faint network of bonds and rings, the flask mark near the top."""
    rng = random.Random(seed)
    img = _gradient(max(w, h), TOP, BOTTOM).crop((0, 0, w, h)).convert("RGBA")
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    nodes = [(rng.uniform(0, w), rng.uniform(0.25 * h, h)) for _ in range(26)]
    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            if math.dist(a, b) < w * 0.55:
                d.line([a, b], fill=(120, 220, 230, 60), width=max(1, w // 90))
    for x, y in nodes:
        r = rng.choice((w * 0.012, w * 0.018, w * 0.026))
        d.ellipse([x - r, y - r, x + r, y + r], fill=(120, 220, 230, 110))
    for _ in range(5):
        _hexagon(d, rng.uniform(0.1 * w, 0.9 * w), rng.uniform(0.3 * h, 0.95 * h), rng.uniform(0.07, 0.15) * w,
                 outline=(150, 235, 240, 70), width=max(1, w // 70))
    img = Image.alpha_composite(img, layer.filter(ImageFilter.GaussianBlur(0.4)))
    mark = flask_mark(int(w * 0.62), with_background=False)
    img.alpha_composite(mark, (int((w - mark.width) / 2), int(h * 0.06)))
    return img.convert("RGB")


def _write_wizard() -> None:
    out = ROOT / "packaging" / "installer"
    out.mkdir(parents=True, exist_ok=True)
    for scale, tag in ((1, ""), (2, "_2x")):
        _molecule_field(164 * scale, 314 * scale, seed=7).save(out / f"wizard_large{tag}.bmp")
        small = flask_mark(BIG).resize((55 * scale, 55 * scale), Image.LANCZOS)
        flat = Image.new("RGB", small.size, (255, 255, 255))
        flat.paste(small, (0, 0), small)
        flat.save(out / f"wizard_small{tag}.bmp")


if __name__ == "__main__":
    _write_icon()
    _write_wizard()
    print("written")
