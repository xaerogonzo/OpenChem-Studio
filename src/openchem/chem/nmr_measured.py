"""A MEASURED NMR spectrum read from JCAMP-DX, to be drawn beside a prediction.

**IT IS NEVER A PREDICTION AND NEVER BECOMES ONE.** An imported spectrum is a
separate record with its own provenance; it is not merged into an
`NMRSignal`, never feeds a calculator, and removing it changes nothing the
application computed. Importing, removing or rescaling it must leave every
signal, `coupling_groups`, shift, integral and result identity exactly as it
was (tests assert that).

**THE ORIGINAL TRACE IS IMMUTABLE.** `NmrReference.ppm` / `.intensity` are what
the file said (the x axis converted to ppm if it was in Hz, nothing else). A
display scale is view state held by the widget and applied when drawing; it is
never written back here, so scaling is reversible and two views can scale the
same record differently.

**IDENTITY IS THE ORIGINAL BYTES.** `content_sha256` is taken over the file's
bytes as read, not over the converted or scaled trace, so two different files
stay distinguishable even if they render alike, and the same file imported
twice is recognisably the same.

Reading is `chem.jcamp.parse`'s job and it handles only the
`##XYDATA=(X++(Y..Y))` form; a processed spectrum stored as NTUPLES, a peak
table or an FID is refused by name rather than mis-read.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from openchem.chem import jcamp

#: Nuclei this viewer can draw a reference for, keyed by the nucleus a JCAMP
#: header spells (`^1H`, `1H`, `H1`...). Anything else is kept as the raw text
#: and simply never matches the viewer's current nucleus.
_NUCLEUS_BY_MASS = {"1H": "H", "13C": "C"}

#: A real NMR file spells its spectrometer frequency in MHz.
_MIN_POINTS = 2


@dataclass(frozen=True)
class NmrReference:
    """One measured spectrum and where it came from."""

    filename: str
    #: SHA-256 of the file's ORIGINAL bytes -- see the module docstring.
    content_sha256: str
    title: str
    #: "H" or "C" when recognised, else the header's own text (never matches).
    nucleus: str
    #: MHz from the file, or None when it did not say (then only a ppm axis is
    #: readable; an Hz axis is refused).
    frequency_mhz: float | None
    solvent: str
    #: The axis unit the FILE used ("PPM" or "HZ"); `ppm` below is always ppm.
    source_x_units: str
    ppm: tuple[float, ...]
    intensity: tuple[float, ...]
    source_format: str = "JCAMP-DX"

    @property
    def point_count(self) -> int:
        return len(self.ppm)

    def matches(self, element: str) -> bool:
        """Whether this was acquired on `element`'s nucleus ("H" or "C")."""
        return self.nucleus == element

    def describe(self) -> str:
        """One honest line saying what this is and that it is not a prediction."""
        parts = [self.nucleus if self.nucleus in ("H", "C") else self.nucleus or "?"]
        if self.frequency_mhz:
            parts.append(f"{self.frequency_mhz:g} MHz")
        if self.solvent:
            parts.append(self.solvent)
        return f"{self.filename} ({', '.join(parts)}) -- imported measurement, not a prediction"


def _nucleus_from(header: str) -> str:
    """`^1H`, `1H`, `H1`, `^13C` ... -> "H" / "C"; unknown text is returned
    stripped so it is visible in the provenance and matches nothing."""
    text = header.strip().lstrip("^")
    match = re.match(r"^(\d+)\s*([A-Za-z]+)$", text) or re.match(r"^([A-Za-z]+)\s*(\d+)$", text)
    if match:
        a, b = match.groups()
        mass, symbol = (a, b) if a.isdigit() else (b, a)
        key = f"{mass}{symbol.capitalize()}"
        return _NUCLEUS_BY_MASS.get(key, text)
    return text


def read_nmr_reference(data: bytes | str, filename: str) -> NmrReference:
    """Parse an NMR JCAMP-DX document into an `NmrReference`.

    Raises `jcamp.JcampError` for anything that is not a plain NMR SPECTRUM in
    the supported form -- an FID, a non-NMR file, an Hz axis with no
    spectrometer frequency, or fewer than two points -- so the caller shows the
    reason instead of drawing something.
    """
    raw = data if isinstance(data, bytes) else data.encode("utf-8")
    text = raw.decode("utf-8", errors="replace")
    spectrum = jcamp.parse(text)
    headers = spectrum.headers

    data_type = (spectrum.data_type or "").upper()
    if "NMR" not in data_type:
        raise jcamp.JcampError(f"This is not an NMR spectrum (##DATA TYPE={spectrum.data_type!r}).")
    if "FID" in data_type:
        raise jcamp.JcampError(
            "This file holds an FID (time-domain data), not a processed spectrum; "
            "process it in your NMR software and export the spectrum."
        )
    if spectrum.point_count < _MIN_POINTS:
        raise jcamp.JcampError("That file parsed but contains fewer than two points.")

    frequency = None
    raw_frequency = headers.get(".OBSERVEFREQUENCY", "").split()
    if raw_frequency:
        try:
            frequency = float(raw_frequency[0])
        except ValueError:
            frequency = None

    units = (spectrum.x_units or "").upper().strip()
    if units in ("PPM", ""):
        ppm = list(spectrum.x)
        units = units or "PPM"
    elif units in ("HZ", "HERTZ"):
        if not frequency:
            raise jcamp.JcampError(
                "The x axis is in Hz but the file gives no .OBSERVE FREQUENCY, so it cannot "
                "be converted to ppm."
            )
        # A frequency OFFSET from the reference, so ppm = Hz / spectrometer MHz.
        ppm = [x / frequency for x in spectrum.x]
        units = "HZ"
    else:
        raise jcamp.JcampError(f"Unsupported x axis unit {spectrum.x_units!r} (expected PPM or HZ).")

    return NmrReference(
        filename=filename,
        content_sha256=hashlib.sha256(raw).hexdigest(),
        title=spectrum.title,
        nucleus=_nucleus_from(headers.get(".OBSERVENUCLEUS", "")),
        frequency_mhz=frequency,
        solvent=headers.get(".SOLVENTNAME", "").strip(),
        source_x_units=units,
        ppm=tuple(ppm),
        intensity=tuple(spectrum.y),
    )


def reference_peaks(reference: NmrReference, min_fraction: float = 0.1) -> list[tuple[float, float]]:
    """Local maxima of the measured trace as `(ppm, intensity)`, tallest first
    kept in ppm order: a point higher than both neighbours and at least
    `min_fraction` of the tallest point. Plain local-maximum picking on the
    ORIGINAL trace (no smoothing, no scaling); a noisy baseline above the
    threshold will pick noise, which the viewer shows rather than hides."""
    values = reference.intensity
    if len(values) < 3:
        return []
    ceiling = max(values)
    if ceiling <= 0:
        return []
    floor = ceiling * min_fraction
    return [
        (reference.ppm[i], values[i])
        for i in range(1, len(values) - 1)
        if values[i] > values[i - 1] and values[i] >= values[i + 1] and values[i] >= floor
    ]
