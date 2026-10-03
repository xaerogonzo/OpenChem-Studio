"""Writing a PREDICTED NMR spectrum out: JCAMP-DX and an SD file.

**EXPORTERS READ THE RESULT, NOT THE SCREEN.** Everything written here comes
from the `NMRSignal` list and the viewer's parameters (frequency, nucleus,
solvent, decoupled) -- never from a screenshot or from label text -- so an
export cannot disagree with the data the viewer holds.

**AND IT SAYS WHAT IT IS.** Both formats carry that the numbers are
PREDICTED, not measured, and where they came from. A file that looked like an
instrument's would be read, later, as one.

The JCAMP-DX is the Lorentzian-broadened trace (the same
`lorentzian_envelope` smooth mode draws) written as `##XYDATA=(X++(Y..Y))`,
the form `chem.jcamp` reads, so it round-trips through this application's own
reader. It is a first-order display model (see `multiplet_lines`), not a
spin-Hamiltonian simulation, and the header says so.
"""

from __future__ import annotations

from rdkit import Chem

from openchem.chem.nmr_signals import (
    DEFAULT_LORENTZIAN_HWHM_PPM,
    NMRSignal,
    lorentzian_envelope,
)

#: How a JCAMP-DX header spells the nuclei this viewer shows.
_NUCLEUS_SPELLING = {"H": "^1H", "C": "^13C"}
#: Points in the exported trace: dense enough to resolve a 0.012 ppm
#: half-width line over a typical window.
_POINTS = 4096
#: Integer Y scale; PAC integers keep the file free of exponent notation,
#: which JCAMP's SQZ letters would otherwise make ambiguous.
_Y_FULL_SCALE = 1_000_000
#: Y values per XYDATA line, after the X checkpoint.
_PER_LINE = 8


def export_jcamp(
    signals: list[NMRSignal],
    *,
    frequency_mhz: float,
    element: str,
    solvent: str = "",
    title: str = "OpenChem Studio predicted NMR spectrum",
    decoupled: bool = False,
    method: str = "",
    hwhm_ppm: float = DEFAULT_LORENTZIAN_HWHM_PPM,
    points: int = _POINTS,
) -> str:
    """The predicted spectrum as JCAMP-DX text, high ppm first (the NMR
    convention). Raises `ValueError` for no signals: an empty file would read
    as a flat measurement."""
    if not signals:
        raise ValueError("There are no signals to export.")
    low = min(s.shift for s in signals) - 0.5
    high = max(s.shift for s in signals) + 0.5
    step = (high - low) / (points - 1)
    xs = [high - i * step for i in range(points)]
    ys = lorentzian_envelope(signals, xs, frequency_mhz, hwhm_ppm, decoupled=decoupled)
    peak = max(ys) or 1.0
    ints = [round(y / peak * _Y_FULL_SCALE) for y in ys]

    lines = [
        f"##TITLE={title}",
        "##JCAMP-DX=5.00",
        "##DATA TYPE=NMR SPECTRUM",
        "##ORIGIN=OpenChem Studio",
        "##OWNER=",
        "$$ PREDICTED, not a measurement. First-order multiplets broadened as Lorentzians;",
        "$$ not a spin-Hamiltonian simulation (no roofing, second-order effects or",
        "$$ magnetic nonequivalence)." + (f" Method: {method}." if method else ""),
        f"##.OBSERVE FREQUENCY={frequency_mhz:g}",
        f"##.OBSERVE NUCLEUS={_NUCLEUS_SPELLING.get(element, element)}",
        *([f"##.SOLVENT NAME={solvent}"] if solvent else []),
        "##XUNITS=PPM",
        "##YUNITS=ARBITRARY UNITS",
        f"##FIRSTX={xs[0]:.6f}",
        f"##LASTX={xs[-1]:.6f}",
        f"##DELTAX={-step:.9f}",
        "##XFACTOR=1",
        "##YFACTOR=1",
        f"##NPOINTS={points}",
        "##XYDATA=(X++(Y..Y))",
    ]
    for start in range(0, points, _PER_LINE):
        chunk = ints[start : start + _PER_LINE]
        lines.append(f"{xs[start]:.6f} " + " ".join(str(v) for v in chunk))
    lines.append("##END=")
    return "\n".join(lines) + "\n"


def export_sdf(
    mol: Chem.Mol,
    signals: list[NMRSignal],
    *,
    frequency_mhz: float,
    element: str,
    solvent: str = "",
    title: str = "",
    method: str = "",
) -> str:
    """A one-record SD file: the molecule WITH its explicit hydrogens (so each
    `NMRSignal`'s atom indices ARE this file's atom numbers, one-based as in
    every molfile) and the predicted shifts as data fields. A field per
    nucleus, one line per atom: `<atom> <shift ppm> <multiplicity>`."""
    block = Chem.MolToMolBlock(mol)
    head, _, _ = block.partition("M  END")
    block = head + "M  END"
    if title:
        rows = block.split("\n")
        rows[0] = title
        block = "\n".join(rows)
    label = {"H": "1H", "C": "13C"}.get(element, element)
    shift_lines = [
        f"{atom + 1} {signal.shift:.3f} {signal.multiplicity}"
        for signal in signals
        for atom in signal.atom_indices
    ]
    fields = {
        f"NMR_{label}_PREDICTED_SHIFTS": "\n".join(shift_lines),
        "NMR_SPECTROMETER_FREQUENCY_MHZ": f"{frequency_mhz:g}",
        "NMR_SOLVENT": solvent,
        "NMR_NOTE": "PREDICTED, not measured"
        + (f"; method: {method}" if method else "")
        + "; atom numbers are 1-based positions in this molfile",
    }
    out = [block]
    for name, value in fields.items():
        if value:
            out += [f"> <{name}>", value, ""]
    out.append("$$$$")
    return "\n".join(out) + "\n"
