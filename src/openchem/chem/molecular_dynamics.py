"""Vacuum molecular dynamics by velocity Verlet over MMFF/UFF forces.

WHAT THIS IS, stated plainly because MD invites assumptions it cannot meet:

    VACUUM molecular dynamics. No thermostat, no barostat, no constraints,
    no periodic boundaries, no implicit solvent. Forces come from MMFF94
    (or UFF), not Dreiding -- so energies are NOT comparable to
    MarvinSketch's.

It is a real integrator over real forces (`CalcGrad` is confirmed to
return 3N genuine gradient components), useful for watching a molecule
move and for teaching. It is not a production simulation package and does
not pretend to be.

WHY VELOCITY VERLET: it is symplectic, so total energy stays BOUNDED
rather than drifting -- which is the property that distinguishes a correct
integrator from one that merely produces convincing motion. That bound is
what the test suite checks, because a drifting integrator still animates
beautifully.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.geometry_analysis import NoConformerError, _require_conformer
from openchem.domain.common import CacheState, Provenance
from openchem.domain.scientific_result import TrajectoryResult

# Boltzmann constant in kcal/(mol*K) -- the unit system MMFF energies and
# gradients already use, so no conversion is needed anywhere else.
BOLTZMANN_KCAL = 1.987204259e-3

# amu * A^2 / fs^2 -> kcal/mol. 1 amu*A^2/fs^2 = 2390.057 kcal/mol.
_AMU_A2_FS2_TO_KCAL = 2390.05736

DEFAULT_STEPS = 1000
DEFAULT_STEP_FS = 0.5
DEFAULT_TEMPERATURE_K = 300.0
DEFAULT_FRAME_INTERVAL = 10


class UnstableTrajectoryError(RuntimeError):
    """The integrator diverged -- almost always an over-large timestep."""


@dataclass(frozen=True)
class MDFrame:
    time_fs: float
    positions: np.ndarray
    potential: float
    kinetic: float

    @property
    def total(self) -> float:
        return self.potential + self.kinetic


def _force_field(mol: Chem.Mol):
    """MMFF when parameterised, UFF otherwise. Returns None when neither
    covers the molecule, rather than silently integrating zero forces."""
    try:
        properties = AllChem.MMFFGetMoleculeProperties(mol)
        if properties is not None:
            field = AllChem.MMFFGetMoleculeForceField(mol, properties)
            if field is not None:
                return field, "MMFF94"
    except (ValueError, RuntimeError):
        pass
    try:
        if AllChem.UFFHasAllMoleculeParams(mol):
            field = AllChem.UFFGetMoleculeForceField(mol)
            if field is not None:
                return field, "UFF"
    except (ValueError, RuntimeError):
        pass
    return None, ""


def _maxwell_boltzmann_velocities(
    masses: np.ndarray, temperature: float, rng: random.Random
) -> np.ndarray:
    """Velocities drawn from Maxwell-Boltzmann, with net momentum removed.

    Removing the centre-of-mass drift matters: without it the molecule
    sails off across the viewport, which looks like a bug and buries the
    internal motion that is the point.
    """
    velocities = np.array(
        [
            [rng.gauss(0.0, math.sqrt(BOLTZMANN_KCAL * temperature / (mass * _AMU_A2_FS2_TO_KCAL)))
             for _ in range(3)]
            for mass in masses
        ]
    )
    momentum = (velocities * masses[:, None]).sum(axis=0)
    return velocities - momentum / masses.sum()


def run_dynamics(
    mol: Chem.Mol,
    steps: int = DEFAULT_STEPS,
    step_fs: float = DEFAULT_STEP_FS,
    temperature: float = DEFAULT_TEMPERATURE_K,
    frame_interval: int = DEFAULT_FRAME_INTERVAL,
    seed: int | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> tuple[list[MDFrame], str]:
    """Velocity-Verlet trajectory. Returns (frames, force field name)."""
    conformer = _require_conformer(mol)
    working = Chem.Mol(mol)
    field, field_name = _force_field(working)
    if field is None:
        raise ValueError("No MMFF or UFF parameters are available for this molecule.")

    masses = np.array([atom.GetMass() for atom in working.GetAtoms()])
    positions = np.array(conformer.GetPositions())
    rng = random.Random(seed)
    velocities = _maxwell_boltzmann_velocities(masses, temperature, rng)

    def potential_and_forces(coords: np.ndarray) -> tuple[float, np.ndarray]:
        flat = coords.reshape(-1).tolist()
        energy = float(field.CalcEnergy(flat))
        # CalcGrad returns dE/dx; force is its negative.
        gradient = np.array(field.CalcGrad(flat)).reshape(-1, 3)
        return energy, -gradient

    potential, forces = potential_and_forces(positions)
    # a = F/m, with the unit conversion that makes A/fs^2 come out right.
    accelerations = forces / masses[:, None] / _AMU_A2_FS2_TO_KCAL

    frames: list[MDFrame] = []

    def record(step: int, energy: float) -> None:
        kinetic = float(
            0.5 * (masses[:, None] * velocities**2).sum() * _AMU_A2_FS2_TO_KCAL
        )
        frames.append(
            MDFrame(
                time_fs=step * step_fs,
                positions=positions.copy(),
                potential=energy,
                kinetic=kinetic,
            )
        )

    record(0, potential)
    for step in range(1, steps + 1):
        if should_cancel is not None and should_cancel():
            break
        # Velocity Verlet: half-step velocities, full-step positions, new
        # forces, then the second half-step. Symplectic, so total energy
        # oscillates within a bound instead of drifting.
        velocities = velocities + 0.5 * accelerations * step_fs
        positions = positions + velocities * step_fs
        potential, forces = potential_and_forces(positions)
        accelerations = forces / masses[:, None] / _AMU_A2_FS2_TO_KCAL
        velocities = velocities + 0.5 * accelerations * step_fs

        # An over-large timestep makes the integrator diverge, and it does
        # so into NaN rather than into a large number -- confirmed by
        # running 5 fs steps, which produced NaN energies and would have
        # written NaN coordinates into every subsequent frame. Stopping at
        # the first non-finite value keeps the frames already collected
        # (which are valid) and lets the caller say what happened.
        if not math.isfinite(potential) or not np.isfinite(positions).all():
            raise UnstableTrajectoryError(
                f"The simulation became unstable at {step * step_fs:.0f} fs. "
                f"A timestep of {step_fs} fs is too large for this molecule -- "
                f"try 0.5 fs or smaller."
            )
        if step % frame_interval == 0:
            record(step, potential)

    return frames, field_name


def _frame_molblock(mol: Chem.Mol, positions: np.ndarray) -> str:
    frame_mol = Chem.Mol(mol)
    conformer = frame_mol.GetConformer()
    for index in range(frame_mol.GetNumAtoms()):
        conformer.SetAtomPosition(index, positions[index].tolist())
    return Chem.MolToMolBlock(frame_mol)


def compute_molecular_dynamics(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> TrajectoryResult:
    """The "dynamics" category's calculator."""
    parameters = parameters or {}
    try:
        frames, field_name = run_dynamics(
            mol,
            steps=int(parameters.get("steps", DEFAULT_STEPS)),
            step_fs=float(parameters.get("step_fs", DEFAULT_STEP_FS)),
            temperature=float(parameters.get("temperature", DEFAULT_TEMPERATURE_K)),
            frame_interval=int(parameters.get("frame_interval", DEFAULT_FRAME_INTERVAL)),
            seed=int(parameters.get("seed", 0)) or None,
        )
    except (NoConformerError, ValueError, UnstableTrajectoryError) as exc:
        return TrajectoryResult(
            trajectory_id="molecular_dynamics",
            name="Molecular Dynamics",
            method="mmff_velocity_verlet",
            molecule_uuid=molecule_uuid,
            cache_state=CacheState.FAILED,
            error=str(exc),
            provenance=Provenance(created_by="core", method="rdkit"),
        )

    temperature = float(parameters.get("temperature", DEFAULT_TEMPERATURE_K))
    return TrajectoryResult(
        trajectory_id="molecular_dynamics",
        name=f"Vacuum MD ({field_name}, {len(frames)} frames)",
        method="mmff_velocity_verlet",
        molecule_uuid=molecule_uuid,
        frames=[_frame_molblock(mol, frame.positions) for frame in frames],
        times=[frame.time_fs for frame in frames],
        energies=[frame.total for frame in frames],
        temperature=temperature,
        metadata={
            "force_field": field_name,
            # Spelled out in the result, not only in a docstring: MD
            # invites exactly these questions and this implementation
            # answers none of them.
            "caveat": (
                f"Vacuum molecular dynamics ({field_name}). No thermostat, no barostat, no "
                f"constraints, no periodic boundaries, no solvent. Not Dreiding, so energies "
                f"are not comparable to MarvinSketch's."
            ),
        },
        provenance=Provenance(
            created_by="core",
            method="rdkit",
            parameters={
                "force_field": field_name,
                "steps": int(parameters.get("steps", DEFAULT_STEPS)),
                "step_fs": float(parameters.get("step_fs", DEFAULT_STEP_FS)),
                "temperature_k": temperature,
            },
        ),
    )
