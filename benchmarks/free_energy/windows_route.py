"""The whole hydration chain on Windows, with neither AmberTools nor packmol.

`hydration.py` is the reference protocol and it needs GAFF, which needs
AmberTools, which has **no win-64 build**. That is not a gap somebody can
close: conda-forge publishes linux-64, linux-aarch64, linux-ppc64le, osx-64
and osx-arm64 and nothing else, and every version of `openmmforcefields`
pins it -- so on Windows both of its template generators are unreachable,
the SMIRNOFF one included even though it needs none of AmberTools itself.
`packmol` has no win-64 build either, which takes Interchange's own
solvation with it.

**THIS IS THE ROUTE THAT NEEDS NEITHER**, kept runnable because the
alternative is a claim in a README that nobody can check:

    charges     NAGL -- a graph network trained to reproduce AM1-BCC,
                measured against the AmberTools values at 0.0014 e worst
                case over five compounds
    solvation   OpenMM solvates an EMPTY topology, which asks nothing about
                the solute and so needs no template for it; the waters that
                land on the solute are then dropped geometrically
    parameters  Interchange, Sage for the solute and TIP3P for the water,
                in one pass

**SAGE IS NOT GAFF, AND THAT LIMIT DOES NOT GO AWAY.** FreeSolv's reference
column was computed with GAFF, and the whole reason that comparison isolates
the protocol is that both sides use one force field. A Sage answer differing
from it would be the force field speaking, not the machinery. So validation
stays under WSL; what this establishes is that **nothing on the shipping
platform is blocked**, never that a Windows number reproduces anything.

It runs on the CPU by default. The GPU is a single physical card shared with
WSL, and running both at once has already killed one arm of an experiment
with `CUDA_ERROR_UNKNOWN`.

    <env>/python.exe benchmarks/free_energy/windows_route.py
    <env>/python.exe benchmarks/free_energy/windows_route.py --platform CUDA

Measured on ammonia, 5 iterations at the reference protocol's own 15-state
schedule, on the CPU:

    Sage + TIP3P, 1276 atoms
    dG(decouple, solvated) = +5.518 +/- 0.726 kcal/mol in 694 s

Five iterations is not a result and that number is not offered as one -- and
note it is a SAGE number, where the GAFF1 reference protocol gives +4.127 for
the same leg. A difference between two force fields is the force fields
speaking. What this establishes is that every stage runs.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

#: Box edge. Small on purpose -- this is a feasibility check, not a
#: measurement, and every second here is a second the GPU is not free.
BOX_NM = 2.4

#: How close a water oxygen may come to a solute atom before it is dropped.
#: Cruder than `Modeller.addSolvent`'s own exclusion, which is why the
#: sampler is minimised afterwards: the GAFF path needs no minimisation
#: because addSolvent knows the solute and avoids it, and this route cannot.
CLASH_NM = 0.32


def build_system(smiles: str, box_nm: float = BOX_NM):
    """A solvated, parameterised OpenMM system, on a platform with no
    AmberTools and no packmol. Returns (system, positions, n_solute_atoms)."""
    import numpy
    import openmm
    import openmm.app as app
    import openmm.unit as unit
    from openff.toolkit import ForceField, Molecule, Topology
    from openff.toolkit.utils.toolkits import NAGLToolkitWrapper
    from openff.units import unit as off_unit

    solute = Molecule.from_smiles(smiles)
    solute.generate_conformers(n_conformers=1)
    solute.assign_partial_charges("openff-gnn-am1bcc-1.0.0.pt",
                                  toolkit_registry=NAGLToolkitWrapper())

    # A pure water box. `addSolvent` on an EMPTY topology needs no residue
    # template for anything, which is precisely how this sidesteps the wall.
    empty = app.Modeller(app.Topology(), [])
    empty.addSolvent(app.ForceField("amber14/tip3p.xml"), model="tip3p",
                     boxSize=openmm.Vec3(box_nm, box_nm, box_nm) * unit.nanometer)
    water_positions = numpy.array(empty.positions.value_in_unit(unit.nanometer))
    placed = water_positions.shape[0] // 3

    solute_xyz = numpy.array(solute.conformers[0].m_as("nanometer"))
    solute_xyz = solute_xyz - solute_xyz.mean(axis=0) + box_nm / 2.0

    kept = [index for index in range(placed)
            if numpy.min(numpy.linalg.norm(
                solute_xyz - water_positions[index * 3], axis=1)) >= CLASH_NM]

    water = Molecule.from_smiles("O")
    water.generate_conformers(n_conformers=1)
    topology = Topology.from_molecules([solute] + [water] * len(kept))
    coordinates = [solute_xyz] + [water_positions[i * 3:i * 3 + 3] for i in kept]
    topology.set_positions(numpy.concatenate(coordinates) * off_unit.nanometer)
    topology.box_vectors = numpy.eye(3) * box_nm * off_unit.nanometer

    force_field = ForceField("openff-2.2.1.offxml", "tip3p.offxml")
    interchange = force_field.create_interchange(
        topology, charge_from_molecules=[solute])
    system = interchange.to_openmm(combine_nonbonded_forces=True)
    return system, interchange.positions.to_openmm(), solute.n_atoms, len(kept)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smiles", default="N")
    parser.add_argument("--iterations", type=int, default=8)
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--platform", default="CPU")
    args = parser.parse_args()

    import openmm
    import openmm.unit as unit
    from openmmtools import alchemy, cache, mcmc, multistate, states

    names = [openmm.Platform.getPlatform(i).getName()
             for i in range(openmm.Platform.getNumPlatforms())]
    print(f"OpenMM {openmm.version.version}   platforms {names}")
    started = time.time()

    system, positions, n_solute, n_waters = build_system(args.smiles)
    print(f"  Sage + TIP3P: {system.getNumParticles()} atoms, {n_waters} waters"
          f"   {time.time() - started:5.1f} s")

    factory = alchemy.AbsoluteAlchemicalFactory(consistent_exceptions=False)
    region = alchemy.AlchemicalRegion(
        alchemical_atoms=list(range(n_solute)),
        annihilate_electrostatics=True, annihilate_sterics=True)
    alchemical_system = factory.create_alchemical_system(system, region)

    # THE REFERENCE PROTOCOL'S OWN SCHEDULE, imported rather than invented.
    # A five-state demo schedule was tried first and produced a NaN at
    # lambda_sterics = 0.5: stepping the soft-core in halves is too coarse to
    # integrate through. Sharing `build_states` also means this route cannot
    # drift away from the protocol it exists to show is reachable.
    from hydration import build_states

    thermo_states = []
    for elec, steric in build_states():
        state = states.CompoundThermodynamicState(
            states.ThermodynamicState(system=alchemical_system,
                                      temperature=298.15 * unit.kelvin),
            composable_states=[alchemy.AlchemicalState.from_system(alchemical_system)])
        state.lambda_electrostatics = elec
        state.lambda_sterics = steric
        thermo_states.append(state)

    sampler_state = states.SamplerState(
        positions=positions,
        box_vectors=alchemical_system.getDefaultPeriodicBoxVectors())

    cache.global_context_cache.platform = openmm.Platform.getPlatformByName(args.platform)
    move = mcmc.LangevinDynamicsMove(timestep=2.0 * unit.femtoseconds,
                                     collision_rate=1.0 / unit.picosecond,
                                     n_steps=args.steps, reassign_velocities=True)
    sampler = multistate.ReplicaExchangeSampler(
        mcmc_moves=move, number_of_iterations=args.iterations)
    scratch = Path(tempfile.mkdtemp(prefix="windows_route_"))
    reporter = multistate.MultiStateReporter(str(scratch / "probe.nc"),
                                             checkpoint_interval=args.iterations)
    sampler.create(thermodynamic_states=thermo_states,
                   sampler_states=sampler_state, storage=reporter)
    # Required here and NOT in the GAFF path: the geometric water cull is
    # cruder than addSolvent's, and without this the first step is a NaN.
    sampler.minimize()
    sampler.run()

    analyzer = multistate.MultiStateSamplerAnalyzer(reporter)
    delta_f, delta_f_err = analyzer.get_free_energy()
    kt = (unit.MOLAR_GAS_CONSTANT_R * 298.15 * unit.kelvin).value_in_unit(
        unit.kilocalorie_per_mole)
    print(f"\n  dG(decouple, solvated) = {delta_f[0, -1] * kt:+.3f} "
          f"+/- {delta_f_err[0, -1] * kt:.3f} kcal/mol")
    print(f"  total {time.time() - started:.1f} s on {args.platform}")
    print("\nEVERY STAGE RAN, with no AmberTools and no packmol. The number")
    print("above is from a deliberately short run and is not a result; what")
    print("this establishes is that nothing on this platform is blocked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
