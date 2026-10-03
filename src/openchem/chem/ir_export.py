"""Writing a PREDICTED IR spectrum out as JCAMP-DX.

**A PEAK TABLE, NOT A TRACE, AND THAT IS THE SAME DECISION THE VIEWER MAKES.**
`IrSpectrumWidget` applies no lineshape because a linewidth is information this
calculation has no basis to choose, and the NMR export (`nmr_export`) could
broaden because a first-order NMR display model already carries a width. A
harmonic IR calculation yields positions and integrated intensities, so that is
what is written: `##PEAKTABLE=(XY..XY)`, wavenumber in cm-1 and intensity in
km/mol.

**IT SAYS WHAT IT IS.** Like the NMR export, the file carries that the numbers are
PREDICTED, harmonic, and (when one was applied) the frequency scaling, so it is
not later read as an instrument's spectrum.

**IMAGINARY MODES ARE NOT WRITTEN AS BANDS.** A negative wavenumber is the finding
that the geometry is a saddle point, not a band at a negative position, so it is
named in a comment and left out of the table, exactly as the plot does.

**THIS APPLICATION'S OWN JCAMP READER REFUSES PEAK TABLES BY DESIGN** (it reads
`##XYDATA=(X++(Y..Y))`, the form instruments emit), so this file does not round
trip through the measured-overlay import; other tools read peak tables.
"""

from __future__ import annotations

from collections.abc import Sequence

from openchem.domain.scientific_result import VibrationalMode


def export_jcamp_peaks(
    modes: Sequence[VibrationalMode],
    *,
    method: str = "",
    scaling_factor: float = 1.0,
    title: str = "OpenChem Studio predicted IR spectrum",
) -> str:
    """The predicted spectrum as JCAMP-DX text, high wavenumber first (the IR
    convention). Raises `ValueError` when no real band exists: an empty table
    would read as a flat measurement."""
    real = sorted((m for m in modes if not m.is_imaginary), key=lambda m: -m.wavenumber_cm1)
    if not real:
        raise ValueError("There are no real bands to export.")
    imaginary = len(modes) - len(real)
    lines = [
        f"##TITLE={title}",
        "##JCAMP-DX=5.00",
        "##DATA TYPE=INFRARED SPECTRUM",
        "##ORIGIN=OpenChem Studio",
        "##OWNER=",
        "$$ PREDICTED, not a measurement. Harmonic normal modes with integrated IR intensities;",
        "$$ no lineshape, overtones or anharmonicity." + (f" Method: {method}." if method else ""),
        *([f"$$ Frequencies were scaled by {scaling_factor:g}."] if scaling_factor != 1.0 else []),
        *([f"$$ {imaginary} imaginary mode(s) are not listed: the geometry is a saddle point."] if imaginary else []),
        "##XUNITS=1/CM",
        "##YUNITS=KM/MOL",
        f"##NPOINTS={len(real)}",
        "##PEAKTABLE=(XY..XY)",
    ]
    for mode in real:
        intensity = mode.ir_intensity_km_mol
        lines.append(f"{mode.wavenumber_cm1:.4f}, {0.0 if intensity is None else intensity:.4f}")
    lines.append("##END=")
    return "\n".join(lines) + "\n"
