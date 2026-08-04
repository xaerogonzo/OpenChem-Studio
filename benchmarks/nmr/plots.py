"""SVG for the benchmark report, generated rather than plotted.

No charting dependency, matching what this project already does everywhere
it draws (`ChemistryEngine.render_2d_svg` for structures, `QPainter` for the
NMR spectrum and correlation widgets). A scatter plot and a histogram are
tens of lines of coordinate arithmetic; a plotting library would be a new
dependency for a benchmark script.

Styled for a plain white page because these land in a Markdown report, not
in the themed app.
"""

from __future__ import annotations

from dataclasses import dataclass

W, H = 520, 400
PAD_L, PAD_R, PAD_T, PAD_B = 62, 18, 30, 48


@dataclass(frozen=True)
class Series:
    label: str
    colour: str
    points: list[tuple[float, float]]


def _axes(x0: float, x1: float, y0: float, y1: float, xlabel: str, ylabel: str, title: str):
    """Frame, ticks and labels. Returns the SVG parts plus a mapper."""
    def sx(v: float) -> float:
        return PAD_L + (v - x0) / (x1 - x0) * (W - PAD_L - PAD_R)

    def sy(v: float) -> float:
        return H - PAD_B - (v - y0) / (y1 - y0) * (H - PAD_T - PAD_B)

    parts = [
        f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
        f'<text x="{W/2}" y="18" font-size="13" font-family="sans-serif" '
        f'text-anchor="middle" fill="#111">{title}</text>',
        f'<rect x="{PAD_L}" y="{PAD_T}" width="{W-PAD_L-PAD_R}" height="{H-PAD_T-PAD_B}" '
        f'fill="none" stroke="#bbb"/>',
    ]
    for i in range(6):
        v = x0 + (x1 - x0) * i / 5
        x = sx(v)
        parts.append(f'<line x1="{x:.1f}" y1="{H-PAD_B}" x2="{x:.1f}" y2="{H-PAD_B+4}" stroke="#666"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{H-PAD_B+17}" font-size="10" font-family="sans-serif" '
            f'text-anchor="middle" fill="#444">{v:.0f}</text>'
        )
        v = y0 + (y1 - y0) * i / 5
        y = sy(v)
        parts.append(f'<line x1="{PAD_L-4}" y1="{y:.1f}" x2="{PAD_L}" y2="{y:.1f}" stroke="#666"/>')
        parts.append(
            f'<text x="{PAD_L-8}" y="{y+3:.1f}" font-size="10" font-family="sans-serif" '
            f'text-anchor="end" fill="#444">{v:.0f}</text>'
        )
    parts.append(
        f'<text x="{(PAD_L+W-PAD_R)/2}" y="{H-8}" font-size="11" font-family="sans-serif" '
        f'text-anchor="middle" fill="#222">{xlabel}</text>'
    )
    parts.append(
        f'<text x="14" y="{(PAD_T+H-PAD_B)/2}" font-size="11" font-family="sans-serif" '
        f'text-anchor="middle" fill="#222" transform="rotate(-90 14 {(PAD_T+H-PAD_B)/2})">'
        f"{ylabel}</text>"
    )
    return parts, sx, sy


def _legend(series: list[Series], x: float, y: float) -> list[str]:
    parts = []
    for i, s in enumerate(series):
        yy = y + i * 15
        parts.append(f'<rect x="{x}" y="{yy-8}" width="9" height="9" fill="{s.colour}"/>')
        parts.append(
            f'<text x="{x+14}" y="{yy}" font-size="10" font-family="sans-serif" '
            f'fill="#222">{s.label}</text>'
        )
    return parts


def scatter(series: list[Series], title: str, xlabel: str, ylabel: str) -> str:
    """Predicted against experimental, with the y = x line.

    The diagonal is the whole point of this plot: distance from it IS the
    error, so a method's failures are visible as position rather than
    having to be read off a table.
    """
    values = [v for s in series for point in s.points for v in point]
    if not values:
        return ""
    lo, hi = min(values), max(values)
    pad = max(4.0, (hi - lo) * 0.06)
    lo, hi = lo - pad, hi + pad
    parts, sx, sy = _axes(lo, hi, lo, hi, xlabel, ylabel, title)
    parts.append(
        f'<line x1="{sx(lo):.1f}" y1="{sy(lo):.1f}" x2="{sx(hi):.1f}" y2="{sy(hi):.1f}" '
        f'stroke="#999" stroke-dasharray="4 3"/>'
    )
    for s in series:
        for x, y in s.points:
            parts.append(
                f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="3" fill="{s.colour}" '
                f'fill-opacity="0.65"/>'
            )
    parts += _legend(series, PAD_L + 10, PAD_T + 18)
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}">' + "".join(parts) + "</svg>"


def histogram(named_errors: list[tuple[str, str, list[float]]], title: str, bins: int = 24) -> str:
    """Overlaid error distributions -- the shape an MAE hides.

    Outlined rather than filled bars, because the interesting comparison is
    where the tails sit and solid fills would hide whichever is drawn last.
    """
    everything = [e for _l, _c, errs in named_errors for e in errs]
    if not everything:
        return ""
    hi = max(everything)
    edges = [hi * i / bins for i in range(bins + 1)]
    counts = []
    for _label, _colour, errs in named_errors:
        row = [0] * bins
        for e in errs:
            slot = min(bins - 1, int(e / hi * bins)) if hi else 0
            row[slot] += 1
        counts.append(row)
    top = max(max(row) for row in counts) or 1
    parts, sx, sy = _axes(0, hi, 0, top, "absolute error (ppm)", "atoms", title)
    for (label, colour, _errs), row in zip(named_errors, counts, strict=True):
        path = []
        for i, n in enumerate(row):
            x1, x2 = sx(edges[i]), sx(edges[i + 1])
            y = sy(n)
            path.append(f"M{x1:.1f},{sy(0):.1f} L{x1:.1f},{y:.1f} L{x2:.1f},{y:.1f} L{x2:.1f},{sy(0):.1f}")
        parts.append(f'<path d="{" ".join(path)}" fill="none" stroke="{colour}" stroke-width="1.6"/>')
    parts += _legend([Series(l, c, []) for l, c, _e in named_errors], W - 150, PAD_T + 18)
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}">' + "".join(parts) + "</svg>"
