"""Animating a normal mode, as frames the existing 3D viewer already plays.

A `TrajectoryResult` rather than a new type, and not by analogy: that
class's own docstring lists "normal-mode animations" among the consumers
it was shaped for, alongside MD, reaction paths and NEB images. So this
produces molblock frames exactly as `chem/molecular_dynamics.py` does and
reuses the whole publish-and-play path unchanged.

THE DISPLACEMENTS ARE CARTESIAN, WHICH WAS MEASURED RATHER THAN ASSUMED,
and the animation would be visibly wrong if they were not. ORCA's NORMAL
MODES block does not say whether its vectors are Cartesian or
mass-weighted, and a mass-weighted vector added straight to coordinates
moves heavy atoms far too far. Checked against the real water transcript
in `tests/fixtures/orca/water_freq.out`:

    antisymmetric stretch, |displacement| per atom
        O 0.0696    H 0.7054    H 0.7054

For a genuine Cartesian mode the centre of mass must not move, which for
this mode predicts an oxygen recoil of 2 * 0.7054 * sin(52.25 deg) / 16 =
0.0697 A against a measured 0.0696. Mass-weighted vectors would have put
the ratio near 0.5 instead of near 0.1. They are Cartesian, and they
conserve momentum to the printed precision.

AMPLITUDE IS A VIEWING CHOICE, NOT A PHYSICAL ONE, and is labelled as
such. The eigenvector fixes the SHAPE of the motion; its length is
normalised and carries no information about how far the atoms actually
move, which depends on the vibrational quantum number and temperature. So
the amplitude here is chosen to be legible on screen and the trajectory's
metadata says so, rather than implying a real vibrational amplitude has
been computed.
"""

from __future__ import annotations

import math

from rdkit import Chem

from openchem.domain.common import CacheState, Provenance
from openchem.domain.scientific_result import TrajectoryResult, VibrationalMode

#: Speed of light in cm/s, for turning a wavenumber into a real period.
_SPEED_OF_LIGHT_CM_S = 2.99792458e10

#: Peak displacement of the fastest-moving atom, in Angstrom.
#:
#: MEASURED, not picked. The first value tried was 0.5, on the reasoning
#: that half an Angstrom is a readable fraction of a 1.09 A C-H bond. It
#: is not, because in a stretch BOTH bonded atoms move and they move in
#: antiphase, so the bond length swings by roughly twice the per-atom
#: amplitude. Animating water's symmetric stretch at 0.5 took the O-H
#: bond from 0.460 A to 1.501 A -- that is not a vibration, it is a
#: dissociation and a re-formation, twenty times a second. At 0.25 the
#: same mode spans about 0.74-1.26 A, a plainly visible swing that still
#: reads as one bond.
DEFAULT_AMPLITUDE_ANGSTROM = 0.25

#: Frames per full cycle. A sine over a whole period means the last frame
#: is adjacent to the first, so a viewer looping the list gets a smooth
#: cycle with no jump and no need for a ping-pong mode.
DEFAULT_FRAMES = 20


class NoConformerError(ValueError):
    """The molecule has no 3D geometry to displace."""


def mode_period_fs(wavenumber_cm1: float) -> float | None:
    """The real oscillation period, in femtoseconds, or None.

    Carried on the trajectory because `TrajectoryResult.times` is
    documented in fs and a normal mode HAS a genuine period -- 1637 cm-1
    is 20.4 fs -- so there is no reason to put a frame counter there
    instead. None for an imaginary or zero mode, which has no period.
    """
    if wavenumber_cm1 <= 0.0:
        return None
    return 1e15 / (_SPEED_OF_LIGHT_CM_S * wavenumber_cm1)


def normal_mode_frames(
    mol: Chem.Mol,
    displacements: tuple[tuple[float, float, float], ...],
    *,
    frames: int = DEFAULT_FRAMES,
    amplitude: float = DEFAULT_AMPLITUDE_ANGSTROM,
) -> list[str]:
    """Molblocks for one full cycle of the mode.

    `mol` must already carry the geometry the frequencies were computed
    at. This does NOT re-optimise or re-read anything: an `opt_freq` job
    optimises first, and the modes describe motion about THAT geometry --
    animating about the submitted one would show the right displacements
    around the wrong structure.
    """
    if mol.GetNumConformers() == 0:
        raise NoConformerError("cannot animate a mode without a 3D conformer")
    if len(displacements) != mol.GetNumAtoms():
        raise ValueError(
            f"{len(displacements)} displacement vectors for "
            f"{mol.GetNumAtoms()} atoms -- these describe different molecules"
        )
    if frames < 2:
        raise ValueError(f"need at least 2 frames, got {frames}")

    largest = max(
        (math.sqrt(x * x + y * y + z * z) for x, y, z in displacements), default=0.0
    )
    if largest <= 0.0:
        raise ValueError("mode has no displacement to animate")
    # Scaled by the LARGEST atomic displacement rather than by the vector
    # norm, so the on-screen swing of the fastest atom is the same for
    # every mode. Normalising by the 3N norm instead would make a mode
    # spread over many atoms look motionless next to a localised C-H
    # stretch, which is a property of the atom count, not the chemistry.
    scale = amplitude / largest

    conformer = mol.GetConformer()
    base = [tuple(conformer.GetAtomPosition(i)) for i in range(mol.GetNumAtoms())]

    molblocks = []
    for frame in range(frames):
        phase = math.sin(2.0 * math.pi * frame / frames)
        frame_mol = Chem.Mol(mol)
        frame_conformer = frame_mol.GetConformer()
        for index, ((x, y, z), (dx, dy, dz)) in enumerate(zip(base, displacements)):
            frame_conformer.SetAtomPosition(
                index,
                (
                    x + scale * phase * dx,
                    y + scale * phase * dy,
                    z + scale * phase * dz,
                ),
            )
        molblocks.append(Chem.MolToMolBlock(frame_mol))
    return molblocks


def normal_mode_trajectory(
    mol: Chem.Mol,
    mode: VibrationalMode,
    molecule_uuid: str,
    *,
    mode_index: int = 0,
    frames: int = DEFAULT_FRAMES,
    amplitude: float = DEFAULT_AMPLITUDE_ANGSTROM,
    provenance: Provenance | None = None,
) -> TrajectoryResult:
    """One mode as a playable trajectory.

    An imaginary mode animates like any other and is deliberately NOT
    refused: watching the motion along an imaginary mode is how a chemist
    sees WHICH way the geometry wants to fall off the saddle, which is the
    most useful thing to do with a failed optimisation. The label says so
    rather than the animation pretending it is a vibration.
    """
    if not mode.displacements:
        return TrajectoryResult(
            trajectory_id=f"normal_mode_{mode_index}",
            name=f"Normal mode {mode_index}",
            method="orca_normal_mode",
            molecule_uuid=molecule_uuid,
            cache_state=CacheState.FAILED,
            error="this mode carries no displacement vectors",
            provenance=provenance or Provenance(created_by="core", method="orca"),
        )

    try:
        molblocks = normal_mode_frames(
            mol, mode.displacements, frames=frames, amplitude=amplitude
        )
    except (NoConformerError, ValueError) as exc:
        return TrajectoryResult(
            trajectory_id=f"normal_mode_{mode_index}",
            name=f"Normal mode {mode_index}",
            method="orca_normal_mode",
            molecule_uuid=molecule_uuid,
            cache_state=CacheState.FAILED,
            error=str(exc),
            provenance=provenance or Provenance(created_by="core", method="orca"),
        )

    period = mode_period_fs(mode.wavenumber_cm1)
    if period is None:
        # An imaginary mode has no period, so there is no honest time axis
        # for it. Empty rather than zeros, which would plot as a real
        # trajectory that takes no time.
        times: list[float] = []
    else:
        times = [period * frame / len(molblocks) for frame in range(len(molblocks))]

    descriptor = f"{abs(mode.wavenumber_cm1):.0f} cm-1"
    if mode.is_imaginary:
        descriptor += " IMAGINARY"
    if mode.character:
        descriptor += f" {mode.character}"

    return TrajectoryResult(
        trajectory_id=f"normal_mode_{mode_index}",
        name=f"Mode {mode_index} ({descriptor})",
        method="orca_normal_mode",
        molecule_uuid=molecule_uuid,
        frames=molblocks,
        times=times,
        # No energies: a harmonic animation's energy is a model value from
        # the amplitude chosen for VIEWING, not a computed quantity, and
        # putting it here would let it be read as one.
        energies=[],
        provenance=provenance or Provenance(created_by="core", method="orca"),
        metadata={
            "wavenumber_cm1": mode.wavenumber_cm1,
            "character": mode.character,
            "imaginary": mode.is_imaginary,
            "period_fs": period,
            "amplitude_angstrom": amplitude,
            "caveat": (
                "Displacement amplitude is chosen for legibility, not computed. "
                "A normal-mode eigenvector fixes the shape of the motion; how far "
                "the atoms actually move depends on the vibrational state and "
                "temperature, which a harmonic frequency calculation does not give."
                + (
                    " This mode is IMAGINARY: the motion shown is the direction the "
                    "geometry falls away from a saddle point, not a vibration."
                    if mode.is_imaginary
                    else ""
                )
            ),
        },
    )
