"""Normal-mode animation.

The test that matters here is `test_the_animated_motion_matches_the_label`:
it drives real ORCA modes through the animator and measures the resulting
GEOMETRY, so it fails if the frames do not actually show what the mode is
called. Everything else is guard rails around it.

The modes come from `tests/fixtures/orca/water_freq.out`, a real ORCA
6.1.1 transcript, so the displacement vectors are the real ones rather
than something shaped to make this pass.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem import rdMolTransforms as transforms

from openchem.chem.mode_animation import (
    DEFAULT_FRAMES,
    NoConformerError,
    mode_period_fs,
    normal_mode_frames,
    normal_mode_trajectory,
)
from openchem.chem.orca_engine import OrcaQuantumEngineProvider
from openchem.domain.common import CacheState
from openchem.domain.scientific_result import VibrationalMode

_FIXTURES = Path(__file__).parent / "fixtures" / "orca"

# Atom order for AddHs(MolFromSmiles("O")): oxygen 0, hydrogens 1 and 2 --
# and the same order ORCA was handed, which is what makes the displacement
# vectors line up with these indices.
_OXYGEN, _H1, _H2 = 0, 1, 2


@pytest.fixture(scope="module")
def water():
    mol = Chem.AddHs(Chem.MolFromSmiles("O"))
    AllChem.EmbedMolecule(mol, randomSeed=1)
    return mol


@pytest.fixture(scope="module")
def water_modes(water):
    text = (_FIXTURES / "water_freq.out").read_text(encoding="latin-1")
    spectrum = OrcaQuantumEngineProvider().parse_vibrational_spectrum(
        text, water, "uuid", "opt_freq"
    )
    return spectrum.modes


def _geometry_swing(mol, displacements):
    """How far the O-H bond and the H-O-H angle travel over a full cycle."""
    frames = [
        Chem.MolFromMolBlock(block, removeHs=False, sanitize=False)
        for block in normal_mode_frames(mol, displacements)
    ]
    lengths = [
        transforms.GetBondLength(frame.GetConformer(), _OXYGEN, _H1) for frame in frames
    ]
    angles = [
        transforms.GetAngleDeg(frame.GetConformer(), _H1, _OXYGEN, _H2)
        for frame in frames
    ]
    return max(lengths) - min(lengths), max(angles) - min(angles)


def test_the_animated_motion_matches_the_label(water, water_modes):
    """THE test. Water's bend must actually bend and its stretches must
    actually stretch, measured on the produced frames rather than on the
    vectors that went in.

    Measured margins are wide, not marginal: the bend swings the angle
    61.6 degrees while moving the bond 0.04 A; the stretches move the bond
    0.52 A while swinging the angle 1.3 and 4.3 degrees. An animator that
    mixed up the vectors, dropped an atom's row, or normalised per axis
    would collapse that separation."""
    by_character = {}
    for mode in water_modes:
        bond_swing, angle_swing = _geometry_swing(water, mode.displacements)
        by_character.setdefault(mode.character, []).append((bond_swing, angle_swing))

    assert set(by_character) == {"bend", "stretch"}

    (bend_bond, bend_angle), = by_character["bend"]
    assert bend_angle > 30.0, "the bend must visibly change the H-O-H angle"
    assert bend_bond < 0.1, "the bend must not stretch the bond"

    for stretch_bond, stretch_angle in by_character["stretch"]:
        assert stretch_bond > 0.3, "a stretch must visibly change the bond length"
        assert stretch_angle < 15.0, "a stretch must not swing the angle like a bend"


def test_the_amplitude_keeps_a_bond_recognisable(water, water_modes):
    """At the first amplitude tried (0.5 A) water's O-H ran 0.460 to 1.501
    A -- a dissociation rather than a vibration, because both atoms of a
    bond move in antiphase and the bond length swings by twice the
    per-atom amplitude."""
    stretch = max(water_modes, key=lambda mode: mode.wavenumber_cm1)
    frames = [
        Chem.MolFromMolBlock(block, removeHs=False, sanitize=False)
        for block in normal_mode_frames(water, stretch.displacements)
    ]
    lengths = [
        transforms.GetBondLength(frame.GetConformer(), _OXYGEN, _H1) for frame in frames
    ]

    assert min(lengths) > 0.6
    assert max(lengths) < 1.4


def test_a_cycle_starts_and_ends_at_the_equilibrium_geometry(water, water_modes):
    """A full sine period, so a viewer looping the frames sees no jump."""
    frames = normal_mode_frames(water, water_modes[0].displacements, frames=8)
    first = Chem.MolFromMolBlock(frames[0], removeHs=False, sanitize=False)
    reference = water.GetConformer()

    assert len(frames) == 8
    # 1e-4, because a V2000 molblock writes coordinates to four decimal
    # places -- an exact comparison fails on the format, not on the maths
    # (-0.00081616 comes back as -0.0008).
    for index in range(water.GetNumAtoms()):
        moved = first.GetConformer().GetAtomPosition(index)
        rest = reference.GetAtomPosition(index)
        assert moved.x == pytest.approx(rest.x, abs=1e-4)
        assert moved.y == pytest.approx(rest.y, abs=1e-4)
        assert moved.z == pytest.approx(rest.z, abs=1e-4)


def test_the_period_is_the_real_one():
    """1637 cm-1 really is 20.4 fs, so `times` carries physics rather than
    a frame counter."""
    assert mode_period_fs(1637.69) == pytest.approx(20.4, abs=0.1)
    assert mode_period_fs(-1436.0) is None
    assert mode_period_fs(0.0) is None


def test_a_trajectory_carries_frames_times_and_the_amplitude_caveat(water, water_modes):
    trajectory = normal_mode_trajectory(water, water_modes[0], "uuid", mode_index=6)

    assert len(trajectory.frames) == DEFAULT_FRAMES
    assert len(trajectory.times) == DEFAULT_FRAMES
    assert trajectory.times[0] == 0.0
    assert trajectory.trajectory_id == "normal_mode_6"
    assert "1638" in trajectory.name and "bend" in trajectory.name
    # No energies: the only energy available is a function of the VIEWING
    # amplitude, and would be read as a computed quantity.
    assert trajectory.energies == []
    assert "legibility" in trajectory.metadata["caveat"]


def test_an_imaginary_mode_animates_and_says_so():
    """Not refused: watching the motion along an imaginary mode is how a
    chemist sees which way the geometry falls off the saddle."""
    mol = Chem.AddHs(Chem.MolFromSmiles("O"))
    AllChem.EmbedMolecule(mol, randomSeed=1)
    mode = VibrationalMode(
        wavenumber_cm1=-1436.0,
        displacements=((0.0, 0.0, 0.1), (0.0, 0.5, -0.2), (0.0, -0.5, -0.2)),
        character="bend",
    )

    trajectory = normal_mode_trajectory(mol, mode, "uuid")

    assert trajectory.cache_state is not CacheState.FAILED
    assert len(trajectory.frames) == DEFAULT_FRAMES
    assert "IMAGINARY" in trajectory.name
    # No period, so no time axis at all rather than a row of zeros that
    # would plot as a trajectory taking no time.
    assert trajectory.times == []
    assert "saddle point" in trajectory.metadata["caveat"]


def test_a_mode_with_no_displacements_fails_rather_than_animating_nothing(water):
    trajectory = normal_mode_trajectory(
        water, VibrationalMode(wavenumber_cm1=1600.0), "uuid"
    )

    assert trajectory.cache_state is CacheState.FAILED
    assert trajectory.frames == []
    assert "no displacement" in trajectory.error


def test_a_displacement_count_mismatch_is_refused(water):
    """Two molecules' data crossed would animate the wrong atoms."""
    with pytest.raises(ValueError, match="different molecules"):
        normal_mode_frames(water, ((0.0, 0.0, 1.0),))


def test_a_molecule_without_a_conformer_is_refused():
    mol = Chem.AddHs(Chem.MolFromSmiles("O"))

    with pytest.raises(NoConformerError):
        normal_mode_frames(mol, ((0.0, 0.0, 1.0),) * 3)


def test_every_mode_swings_its_fastest_atom_by_the_same_amount(water, water_modes):
    """Scaled by the largest ATOMIC displacement, not the 3N norm -- so a
    mode spread over many atoms is not drawn motionless beside a
    localised one."""
    peaks = []
    for mode in water_modes:
        frames = [
            Chem.MolFromMolBlock(block, removeHs=False, sanitize=False)
            for block in normal_mode_frames(water, mode.displacements)
        ]
        reference = water.GetConformer()
        largest = 0.0
        for frame in frames:
            for index in range(water.GetNumAtoms()):
                a = frame.GetConformer().GetAtomPosition(index)
                b = reference.GetAtomPosition(index)
                largest = max(largest, ((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2) ** 0.5)
        peaks.append(largest)

    for peak in peaks:
        assert peak == pytest.approx(peaks[0], abs=0.02)
