"""The arithmetic of the displaced-restart protocol (`PREREGISTRATION.md` of this folder): read a normal mode from ORCA's Hessian file, displace along it, decide which structures are restarted, and the two rules the preregistration states in numbers
(the stress set's adoption rule and the bias test). Pure functions with no engine and no file read, tested in `tests/test_restart_v2_runner.py`.

THE RESTART (section 3): for a structure still imaginary after v1's own `Calc_Hess` re-run, take the normal mode of the most negative frequency, scale it so its LARGEST single Cartesian component is 1, and displace the geometry by +0.15 and -0.15 Angstrom
along it. One amplitude, ever; one restart.

ORCA's `.hess` file ends its `$normal_modes` block with `#` comment lines, not with the next `$` section, and the matrix is printed in blocks of columns: the parser stops at the first `#` line and reassembles the blocks. The columns follow the
`$vibrational_frequencies` list index by index (the translations and rotations come first, at zero).
"""
from __future__ import annotations

import math

import numpy as np

#: The one displacement amplitude, in Angstrom: the largest Cartesian component of the scaled mode.
AMPLITUDE = 0.15
#: A vibrational frequency below this (cm-1) makes a structure not accepted (the first run's rule, unchanged).
IMAGINARY_CM = -20.0


def read_hessian_modes(hess_text: str) -> tuple[np.ndarray, np.ndarray]:
    """(modes, frequencies) of an ORCA `.hess` file: `modes[:, k]` is the displacement vector (3N numbers) of the vibration whose frequency (cm-1) is `frequencies[k]`. Raises ValueError naming what is missing."""
    if "$normal_modes" not in hess_text or "$vibrational_frequencies" not in hess_text:
        raise ValueError("the Hessian file has no $normal_modes or $vibrational_frequencies block")
    block = hess_text.split("$normal_modes")[1].split("$")[0].split("\n#")[0].strip().splitlines()
    size = int(block[0].split()[0])
    modes = np.zeros((size, size))
    line = 1
    while line < len(block):
        columns = [int(c) for c in block[line].split()]
        for row in range(size):
            values = block[line + 1 + row].split()
            modes[row, columns] = [float(v) for v in values[1:]]
        line += size + 1
    listed = hess_text.split("$vibrational_frequencies")[1].split("$")[0].strip().splitlines()
    count = int(listed[0].split()[0])
    frequencies = np.array([float(entry.split()[1]) for entry in listed[1:1 + count]])
    if count != size:
        raise ValueError(f"{count} frequencies for {size} modes")
    return modes, frequencies


BOHR = 0.529177210903


def read_hessian_atoms(hess_text: str) -> tuple[list[str], np.ndarray]:
    """(element symbols, coordinates in Angstrom) of the `$atoms` block, the frame the modes are written in (ORCA prints Bohr)."""
    if "$atoms" not in hess_text:
        raise ValueError("the Hessian file has no $atoms block")
    rows = hess_text.split("$atoms")[1].split("$")[0].strip().splitlines()
    count = int(rows[0].split()[0])
    entries = [row.split() for row in rows[1:1 + count]]
    return [e[0] for e in entries], np.array([[float(v) for v in e[2:5]] for e in entries]) * BOHR


def same_frame(hess_text: str, symbols: list[str], coordinates, tolerance: float = 1e-3) -> bool:
    """Whether the modes of the Hessian file are written in the frame of the geometry that is displaced: the same atoms in the same order, differing at most by one common translation (ORCA moves the centre of mass; measured on a water in an arbitrary pose, 2026-10-22).
    A rotation would make the displacement a different direction in the molecule, so it is refused."""
    found_symbols, found = read_hessian_atoms(hess_text)
    xyz = np.asarray(coordinates, dtype=float)
    if [s.capitalize() for s in found_symbols] != [s.capitalize() for s in symbols] or found.shape != xyz.shape:
        return False
    shift = found - xyz
    return bool(np.abs(shift - shift[0]).max() <= tolerance)


def lowest_mode(hess_text: str) -> tuple[float, np.ndarray]:
    """(the most negative frequency, its displacement vector as N x 3), the vector scaled so its largest single component (absolute value) is 1."""
    modes, frequencies = read_hessian_modes(hess_text)
    k = int(np.argmin(frequencies))
    vector = modes[:, k].reshape(-1, 3)
    scale = float(np.abs(vector).max())
    if scale == 0.0:
        raise ValueError("the lowest mode is a zero vector")
    return float(frequencies[k]), vector / scale


def displaced(coordinates, vector: np.ndarray, amplitude: float = AMPLITUDE) -> tuple[np.ndarray, np.ndarray]:
    """The geometry (Angstrom, N x 3) moved by +amplitude and by -amplitude along the scaled mode `vector` (N x 3, largest component 1)."""
    xyz = np.asarray(coordinates, dtype=float)
    if xyz.shape != vector.shape:
        raise ValueError(f"{xyz.shape} coordinates against a {vector.shape} mode")
    return xyz + amplitude * vector, xyz - amplitude * vector


def accepted_record(record: dict) -> bool:
    """The first run's acceptance of one finished job: completed, no frequency below -20 cm-1, and the species is still itself (an atom is always accepted)."""
    if not record.get("completed"):
        return False
    if record.get("role") == "atom":
        return True
    return record["lowest_frequency"] >= IMAGINARY_CM and bool(record.get("skeleton_kept"))


def needs_restart(record: dict) -> bool:
    """Whether the job that ended the first run's two stages (the `Calc_Hess` re-run) triggers the restart: it finished, it still has a frequency below -20 cm-1, and its skeleton is intact.

    A structure whose skeleton changed (a radical that lost its hydrogen elsewhere, a ring that opened) is a FAILED structure, not a saddle point near a minimum, and a displacement along its mode would not make it the species; it is not restarted."""
    return bool(record.get("completed")) and record.get("role") != "atom" and record["lowest_frequency"] < IMAGINARY_CM and bool(record.get("skeleton_kept"))


# --- the stress set's adoption rule (section 4) -----------------------------------------------------------------------------------


#: The restart enters the calculators' protocol only if at least this many structures triggered it ...
ADOPT_MIN_TRIGGERS = 2
#: ... and at least this fraction of the triggered structures were accepted after it.
ADOPT_MIN_RESCUED_FRACTION = 0.5


def adoption(triggered: int, rescued: int) -> dict:
    """The stress set's rule on the non-control structures: `{"adopt": bool, "triggered": n, "rescued": n, "why": str}`."""
    if triggered < ADOPT_MIN_TRIGGERS:
        return {"adopt": False, "triggered": triggered, "rescued": rescued, "why": f"only {triggered} structure(s) triggered the restart, fewer than {ADOPT_MIN_TRIGGERS}"}
    fraction = rescued / triggered
    if fraction < ADOPT_MIN_RESCUED_FRACTION:
        return {"adopt": False, "triggered": triggered, "rescued": rescued, "why": f"{rescued} of {triggered} triggered structures were rescued, under {ADOPT_MIN_RESCUED_FRACTION:.0%}"}
    return {"adopt": True, "triggered": triggered, "rescued": rescued, "why": f"{rescued} of {triggered} triggered structures were rescued"}


# --- the bias test (section 7) -----------------------------------------------------------------------------------------------------


#: The first run's mean signed error over its 22 computed deciding bonds (kcal/mol), fixed by the preregistration: the offset under test.
FIRST_RUN_BIAS = -1.53


def bias_test(errors: list[float], offset: float = FIRST_RUN_BIAS) -> dict:
    """The preregistered test of whether the first run's bias reproduces on the held-out errors (computed minus reference, kcal/mol).

    `reproduced`: the held-out mean +/- 2 standard errors (SD / sqrt(n), the sample SD) contains `offset`. `corrected_mae`: the mean absolute error of `e - offset` (the first run's -1.53 added back). `correction_supported`: reproduced AND the corrected
    mean absolute error is below the uncorrected one. Needs at least three errors for a standard deviation."""
    n = len(errors)
    if n < 3:
        raise ValueError("a bias test needs at least three errors")
    mean = sum(errors) / n
    sd = math.sqrt(sum((e - mean) ** 2 for e in errors) / (n - 1))
    se = sd / math.sqrt(n)
    low, high = mean - 2 * se, mean + 2 * se
    mae = sum(abs(e) for e in errors) / n
    corrected = [e - offset for e in errors]
    corrected_mae = sum(abs(e) for e in corrected) / n
    reproduced = low <= offset <= high
    return {
        "n": n, "mean": mean, "sd": sd, "se": se, "interval": (low, high), "offset": offset, "reproduced": reproduced,
        "mae": mae, "corrected_mae": corrected_mae, "corrected_mean": sum(corrected) / n, "correction_supported": reproduced and corrected_mae < mae,
    }
