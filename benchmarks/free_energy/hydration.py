"""An absolute hydration free energy, end to end, with its convergence
diagnostics reported beside it.

**THIS IS ROUTE 3's SMALLEST HONEST CALCULATION.** A relative binding free
energy needs ligand parameterisation, protein preparation, an atom mapping
between two ligands, a lambda schedule, replica exchange and MBAR -- and an
error in any of them returns a confident number rather than a failure. A
hydration free energy exercises every one of those except the mapping and
the protein, runs in minutes rather than hours, and has a PUBLISHED value to
check against. So it is what proves the machinery before a protein is
allowed anywhere near it.

**IT RUNS IN WSL, NOT ON WINDOWS, AND THAT IS A MEASUREMENT.** AmberTools has
no win-64 build on conda-forge (checked: linux-64, linux-aarch64,
linux-ppc64le, osx-64, osx-arm64 and nothing else), and `openmmforcefields`
depends on it, so GAFF/AM1-BCC -- the protocol FreeSolv's reference column
was computed with -- cannot run on the platform this application ships on.
Reproducing the reference protocol is worth more than convenience here,
because it is what separates a wrong protocol from a right protocol on an
imperfect force field.

    wsl -d Ubuntu -- ~/miniforge3/envs/fep/bin/python hydration.py --smiles CO

THE THERMODYNAMIC CYCLE IS THE PART MOST LIKELY TO BE SILENTLY WRONG, so it
is stated rather than left implicit. Both legs are run and subtracted:

    solvated leg   fully interacting solute in water  ->  no interactions
    vacuum leg     fully interacting solute in vacuum ->  no interactions
    dG_hyd = dG_vacuum - dG_solvated

Running only the solvated leg and calling it the answer is correct ONLY if
intramolecular interactions are preserved, which depends on the annihilation
flags. Running both makes the answer independent of that choice, at the cost
of one extra cheap leg. A sign error or a dropped leg here produces a number
in the right units and the right ballpark, which is exactly why the FreeSolv
comparison exists.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import tempfile
import time
from pathlib import Path

#: Lambda schedule. Electrostatics are switched off BEFORE sterics, always:
#: removing charges while the particle is still soft leads to charges
#: collapsing onto solvent, and every published protocol orders them this
#: way. The counts are the conventional ones for a small neutral solute.
ELECTROSTATIC_STATES = 5
STERIC_STATES = 11

#: Per-state sampling. Deliberately small by default so the pipeline can be
#: proved in minutes; `--iterations` raises it, and the convergence
#: diagnostics are what say whether a given setting was enough rather than a
#: rule of thumb about how long is long.
DEFAULT_ITERATIONS = 500
STEPS_PER_ITERATION = 500  # 1 ps at 2 fs


#: Two-sided, and the SAME alpha `domain/affinity_range.py` uses for the
#: replicate-separation rule. It is here for the same reason it is there: a
#: decision expressed as a confidence level is derived, where one expressed
#: in kcal/mol is a constant somebody fitted and the next person tunes.
ALPHA = 0.05

#: z for a two-sided ALPHA. Derived rather than typed -- `1.96` written as a
#: literal is a number that quietly stops matching ALPHA the day ALPHA moves.
def _z_for(alpha: float) -> float:
    from statistics import NormalDist

    return NormalDist().inv_cdf(1.0 - alpha / 2.0)


def diagnose(analyzer, kt_kcal: float) -> dict:
    """Everything that says whether the number above it can be believed.

    **THE VERDICT RESTS ON A SELF-CONSISTENCY TEST, NOT ON A THRESHOLD IN
    kcal/mol.** The documented failure mode of free energy work is that an
    unconverged calculation returns a confident number, and the useful
    question is therefore not "is the answer big" but "is the answer
    consistent with the uncertainty it claims". So the trajectory is split
    into two INDEPENDENT halves and each is analysed on its own: if the two
    disagree by more than their combined uncertainty allows at ALPHA, the
    claimed uncertainty is wrong, whatever it says.

    That has no constant in the units of the data for anybody to tune --
    the same property `domain/affinity_range.py`'s rank-based rule has, and
    for the same reason.

    The overlap and mixing numbers are reported as DIAGNOSTICS rather than
    as gates. A minimum overlap threshold is a rule of thumb, and this
    project does not ship rules of thumb as refusals; a reader who sees
    near-zero overlap between adjacent states knows the schedule is too
    coarse without being told a number.
    """
    out: dict = {}
    n = analyzer.n_iterations
    out["iterations"] = n
    out["equilibration_discarded"] = int(analyzer.n_equilibration_iterations)
    out["statistical_inefficiency"] = float(analyzer.statistical_inefficiency)
    out["effective_samples"] = float(analyzer.effective_length)

    try:
        overlap = analyzer.mbar.compute_overlap()["matrix"]
        out["min_nearest_neighbour_overlap"] = float(
            min(overlap[i][i + 1] for i in range(len(overlap) - 1))
        )
    except Exception as exc:  # noqa: BLE001 - a diagnostic must not fail the run
        out["min_nearest_neighbour_overlap"] = None
        out["overlap_error"] = str(exc)[:80]

    return out


def half_estimates(reporter, kt_kcal: float, n_iterations: int):
    """(first half, second half) free energies, as independent samples.

    Independent is the point: comparing the full estimate against its own
    first half compares nested samples, and the variance of THAT difference
    is not the sum of their variances -- so the obvious combination would
    allow far more drift than it should. Two disjoint halves make the
    ordinary combination correct.
    """
    from openmmtools.multistate import MultiStateSamplerAnalyzer

    half = n_iterations // 2
    if half < 2:
        return None

    # Both bounds are CONSTRUCTOR arguments; `n_equilibration_iterations`
    # is a read-only property afterwards, so the split has to be declared
    # when the analyzer is built. Discarding the first half as
    # "equilibration" is how the second half is isolated.
    first = MultiStateSamplerAnalyzer(reporter, max_n_iterations=half)
    f_df, f_ddf = first.get_free_energy()

    second = MultiStateSamplerAnalyzer(reporter, n_equilibration_iterations=half)
    s_df, s_ddf = second.get_free_energy()

    return (
        (f_df[0, -1] * kt_kcal, f_ddf[0, -1] * kt_kcal),
        (s_df[0, -1] * kt_kcal, s_ddf[0, -1] * kt_kcal),
    )


def build_states(n_elec: int = ELECTROSTATIC_STATES, n_steric: int = STERIC_STATES):
    """(electrostatics, sterics) pairs, in the order they are switched off.

    **THE DENSITY IS AN EXPERIMENTAL VARIABLE, NOT A CONSTANT.** A schedule
    too coarse for a given solute biases MBAR AND underestimates its own
    uncertainty, which is the one failure this benchmark cannot detect from
    the inside -- the two-halves consistency test passes happily. The
    minimum adjacent-state overlap printed per leg is the signal, and
    raising these counts is what it asks for.
    """
    schedule = []
    for i in range(n_elec):
        schedule.append((1.0 - i / (n_elec - 1), 1.0))
    for i in range(1, n_steric):
        schedule.append((0.0, 1.0 - i / (n_steric - 1)))
    return schedule


def silence_citations() -> None:
    """Stop openmmtools printing its citation block on every sampler.

    **THIS IS A HARNESS FIX, AND IT COST A RESULT.** OpenMM and openmmtools
    write that block from a layer that does not share Python's stdout
    buffering, so it interleaves through half-written lines. A schedule
    experiment lost its ENTIRE ammonia arm that way -- the rows were
    produced and were not recoverable from the log, and ammonia was the one
    case whose effect was large enough to see through the run-to-run noise.

    Silencing the banner is half the fix. The other half is that results are
    written to a JSONL file as they are produced (`--out`), so stdout is a
    convenience and never the record.
    """
    from openmmtools.multistate import MultiStateSampler

    MultiStateSampler._global_citation_silence = True


def run_leg(molecule, solvated: bool, iterations: int, platform_name: str, scratch: Path,
            n_elec: int = ELECTROSTATIC_STATES, n_steric: int = STERIC_STATES):
    """One leg of the cycle. Returns (dG_kcal, sigma_kcal, diagnostics)."""
    import openmm
    import openmm.app as app
    import openmm.unit as unit
    from openmmforcefields.generators import GAFFTemplateGenerator
    from openmmtools import alchemy, mcmc, multistate, states

    generator = GAFFTemplateGenerator(molecules=molecule)
    forcefield = app.ForceField("amber/tip3p_standard.xml")
    forcefield.registerTemplateGenerator(generator.generator)

    off_topology = molecule.to_topology()
    omm_topology = off_topology.to_openmm()
    positions = molecule.conformers[0].to_openmm()

    modeller = app.Modeller(omm_topology, positions)
    if solvated:
        modeller.addSolvent(forcefield, model="tip3p", padding=1.2 * unit.nanometer)

    system = forcefield.createSystem(
        modeller.topology,
        nonbondedMethod=app.PME if solvated else app.NoCutoff,
        nonbondedCutoff=0.9 * unit.nanometer if solvated else 999 * unit.nanometer,
        constraints=app.HBonds,
        rigidWater=True,
    )

    solute_atoms = list(range(molecule.n_atoms))
    factory = alchemy.AbsoluteAlchemicalFactory(consistent_exceptions=False)
    region = alchemy.AlchemicalRegion(
        alchemical_atoms=solute_atoms,
        # BOTH annihilated, in BOTH legs. That is what makes the two legs
        # subtract to the hydration free energy without depending on how
        # intramolecular terms are treated -- the choice is made once and
        # applied identically, so it cancels.
        annihilate_electrostatics=True,
        annihilate_sterics=True,
    )
    alchemical_system = factory.create_alchemical_system(system, region)

    thermodynamic_state = states.ThermodynamicState(
        system=alchemical_system, temperature=298.15 * unit.kelvin
    )
    if solvated:
        thermodynamic_state.pressure = 1.0 * unit.atmosphere

    alchemical_state = alchemy.AlchemicalState.from_system(alchemical_system)
    compound = states.CompoundThermodynamicState(
        thermodynamic_state, composable_states=[alchemical_state]
    )

    sampler_states = states.SamplerState(
        positions=modeller.positions,
        box_vectors=(alchemical_system.getDefaultPeriodicBoxVectors() if solvated else None),
    )

    thermo_states = []
    for elec, steric in build_states(n_elec, n_steric):
        state = states.CompoundThermodynamicState(
            states.ThermodynamicState(
                system=alchemical_system,
                temperature=298.15 * unit.kelvin,
                pressure=(1.0 * unit.atmosphere) if solvated else None,
            ),
            composable_states=[alchemy.AlchemicalState.from_system(alchemical_system)],
        )
        state.lambda_electrostatics = elec
        state.lambda_sterics = steric
        thermo_states.append(state)

    move = mcmc.LangevinDynamicsMove(
        timestep=2.0 * unit.femtoseconds,
        collision_rate=1.0 / unit.picosecond,
        n_steps=STEPS_PER_ITERATION,
        reassign_velocities=False,
    )
    # REPLICA EXCHANGE, not independent windows. Hamiltonian exchange is what
    # lets a configuration trapped in one state escape through the others,
    # and its acceptance rate is itself a convergence diagnostic that
    # independent windows simply do not have.
    sampler = multistate.ReplicaExchangeSampler(
        mcmc_moves=move, number_of_iterations=iterations
    )
    storage = scratch / ("solvated.nc" if solvated else "vacuum.nc")
    reporter = multistate.MultiStateReporter(str(storage), checkpoint_interval=100)
    sampler.create(thermodynamic_states=thermo_states, sampler_states=sampler_states,
                   storage=reporter)

    platform = openmm.Platform.getPlatformByName(platform_name)
    sampler.energy_context_cache = __import__("openmmtools").cache.ContextCache(platform=platform)
    sampler.sampler_context_cache = __import__("openmmtools").cache.ContextCache(platform=platform)

    started = time.perf_counter()
    sampler.run()
    elapsed = time.perf_counter() - started

    analyzer = multistate.MultiStateSamplerAnalyzer(reporter)
    delta_f, delta_f_err = analyzer.get_free_energy()
    kt_kcal = (
        unit.MOLAR_GAS_CONSTANT_R * 298.15 * unit.kelvin
    ).value_in_unit(unit.kilocalorie_per_mole)

    # [0, -1] is state 0 -> last state, i.e. fully interacting -> decoupled.
    dg = delta_f[0, -1] * kt_kcal
    sigma = delta_f_err[0, -1] * kt_kcal

    diagnostics = diagnose(analyzer, kt_kcal)
    diagnostics.update(
        seconds=elapsed,
        n_states=len(thermo_states),
        atoms=alchemical_system.getNumParticles(),
    )
    halves = half_estimates(reporter, kt_kcal, analyzer.n_iterations)
    if halves is not None:
        (first_dg, first_sigma), (second_dg, second_sigma) = halves
        drift = abs(first_dg - second_dg)
        allowed = _z_for(ALPHA) * math.sqrt(first_sigma**2 + second_sigma**2)
        diagnostics.update(
            first_half=(first_dg, first_sigma),
            second_half=(second_dg, second_sigma),
            drift=drift,
            allowed_drift=allowed,
            self_consistent=drift <= allowed,
        )
    return dg, sigma, diagnostics


def _one_molecule(smiles: str, label: str, iterations: int, platform_name: str) -> dict:
    """Run both legs for one solute and return the answer plus diagnostics."""
    from openff.toolkit import Molecule

    molecule = Molecule.from_smiles(smiles)
    molecule.generate_conformers(n_conformers=1)
    molecule.assign_partial_charges("am1bcc")

    with tempfile.TemporaryDirectory() as scratch_dir:
        scratch = Path(scratch_dir)
        legs = {}
        for solvated in (False, True):
            name = "solvated" if solvated else "vacuum"
            legs[name] = run_leg(molecule, solvated, iterations, platform_name, scratch)

    dg_vac, s_vac, d_vac = legs["vacuum"]
    dg_solv, s_solv, d_solv = legs["solvated"]
    inconsistent = [
        name for name, (_, _, d) in legs.items()
        if "self_consistent" in d and not d["self_consistent"]
    ]
    return {
        "label": label,
        "hydration": dg_vac - dg_solv,
        "sigma": math.sqrt(s_vac**2 + s_solv**2),
        "legs": legs,
        "converged": not inconsistent,
        "inconsistent": inconsistent,
        "seconds": d_vac["seconds"] + d_solv["seconds"],
    }


def validate(count: int, iterations: int, platform_name: str) -> int:
    """Reproduce FreeSolv's own GAFF column on the smallest compounds.

    **THE GAFF COLUMN IS THE TARGET, NOT EXPERIMENT.** Agreeing with
    experiment would conflate a wrong protocol with a right protocol on an
    imperfect force field; measured over all 642 compounds, that force field
    is itself 1.11 kcal/mol MAE from experiment, so experimental agreement
    better than about a kcal/mol would be luck. Reproducing a number
    computed with the SAME force field is a statement about our machinery.
    """
    import freesolv

    compounds = freesolv.easy_subset(freesolv.load(), count)
    print(f"\nreproducing FreeSolv's GAFF/AM1-BCC column on {len(compounds)} compounds, "
          f"{iterations} iterations each\n")
    header = (f"{'compound':<18}{'ours':>18}{'GAFF':>9}{'diff':>8}"
              f"{'sigma':>7}{'exp':>8}  verdict")
    print(header)
    print("-" * len(header))

    rows = []
    for compound in compounds:
        try:
            result = _one_molecule(compound.smiles, compound.name, iterations, platform_name)
        except Exception as exc:  # noqa: BLE001 - one failure must not lose the rest
            print(f"{compound.name[:17]:<18} failed: {str(exc)[:50]}")
            continue
        diff = result["hydration"] - compound.calculated_kcal_mol
        # Combined uncertainty of OURS and THEIRS. Theirs is about 0.01-0.03,
        # so in practice ours dominates -- but including it is what makes the
        # comparison a statement about two measurements rather than about one
        # measurement and a constant.
        combined = math.sqrt(result["sigma"] ** 2 + compound.calculated_uncertainty ** 2)
        agrees = abs(diff) <= _z_for(ALPHA) * combined
        verdict = ("agrees" if agrees else "DISAGREES") if result["converged"] else "not converged"
        rows.append((compound, result, diff, combined, agrees))
        print(f"{compound.name[:17]:<18}{result['hydration']:>10.3f} +/-{result['sigma']:>5.3f}"
              f"{compound.calculated_kcal_mol:>9.2f}{diff:>8.3f}{combined:>7.3f}"
              f"{compound.experimental_kcal_mol:>8.2f}  {verdict}")

    if not rows:
        print("\nNothing completed.")
        return 1

    converged = [r for r in rows if r[1]["converged"]]
    print(f"\n=== against the GAFF column (the PROTOCOL test) ===")
    if converged:
        diffs = [abs(r[2]) for r in converged]
        agree = sum(1 for r in converged if r[4])
        print(f"  n {len(converged)}   MAE {sum(diffs)/len(diffs):.3f} kcal/mol"
              f"   agreeing within {_z_for(ALPHA):.2f} sigma: {agree}/{len(converged)}")
    print(f"  {len(rows) - len(converged)} of {len(rows)} did not converge and are excluded")

    print(f"\n=== against experiment (the FORCE FIELD's error, not ours) ===")
    if converged:
        exp_diffs = [abs(r[1]["hydration"] - r[0].experimental_kcal_mol) for r in converged]
        print(f"  MAE {sum(exp_diffs)/len(exp_diffs):.3f} kcal/mol, against GAFF's own "
              f"1.11 over all 642 compounds")
        print("  This row is context, NOT a result about our protocol.")
    return 0


def repeat(smiles: str, label: str, count: int, iterations: int,
           platform_name: str, out_path: Path | None) -> int:
    """Run ONE molecule N times at fixed settings, and ask whether the
    stated uncertainties are honest.

    **THIS IS THE MEASUREMENT EVERY OTHER ARM HERE DEPENDS ON.** Four runs of
    methane during development spanned 2.03 to 2.69 kcal/mol while each
    claimed a sigma near 0.2, and pairwise they sat at 1.4-1.9 sigma --
    formally consistent, but strained. Until the true run-to-run spread is
    known, every comparison in this directory is underpowered by
    construction, because the effect being looked for is the same size as
    the noise nobody had measured.

    The test is a REDUCED CHI-SQUARE about the weighted mean. If the stated
    uncertainties are right it is about 1; if they are optimistic it is
    greater. That is a statement about self-consistency with no constant in
    kcal/mol to tune -- the same property the two-halves test has, applied
    across runs instead of within one.

    Each run draws its own integrator seed (OpenMM's default is random), so
    these are independent samples of the protocol rather than repeats of one
    trajectory.
    """
    estimates: list[tuple[float, float]] = []
    for index in range(count):
        result = _run_in_subprocess(smiles, label, iterations, platform_name)
        estimates.append((result["hydration_kcal_mol"], result["sigma_kcal_mol"]))
        record = dict(result, run=index + 1)
        _append_record(out_path, record)
        print(f"  run {index + 1}/{count}: {result['hydration_kcal_mol']:8.3f} "
              f"+/- {result['sigma_kcal_mol']:.3f}   "
              f"{'converged' if result['converged'] else 'NOT CONVERGED'}"
              f"   [{result['seconds']:.0f} s]", flush=True)

    values = [v for v, _ in estimates]
    sigmas = [s for _, s in estimates]
    weights = [1.0 / (s * s) for s in sigmas]
    weighted_mean = sum(w * v for w, v in zip(weights, values)) / sum(weights)
    chi2 = sum(w * (v - weighted_mean) ** 2 for w, v in zip(weights, values))
    dof = len(values) - 1
    reduced = chi2 / dof if dof else float("nan")

    spread = max(values) - min(values)
    plain_sd = (sum((v - sum(values) / len(values)) ** 2 for v in values) / dof) ** 0.5 if dof else 0.0

    print(f"\n=== {count} runs of {label} at {iterations} iterations ===")
    print(f"  values          {' '.join(f'{v:.3f}' for v in values)}")
    print(f"  stated sigmas   {' '.join(f'{s:.3f}' for s in sigmas)}")
    print(f"  weighted mean   {weighted_mean:.3f}")
    print(f"  observed spread {spread:.3f}   sample SD {plain_sd:.3f}")
    print(f"  mean stated sigma {sum(sigmas)/len(sigmas):.3f}")
    print(f"\n  reduced chi-square about the weighted mean: {reduced:.2f} on {dof} dof")
    if reduced > 2.0:
        print("  The runs scatter MORE than their stated uncertainties allow, so those")
        print(f"  uncertainties are optimistic by roughly sqrt({reduced:.2f}) = "
              f"{math.sqrt(reduced):.1f}x.")
    elif reduced < 0.5:
        print("  The runs scatter LESS than stated, so the uncertainties are")
        print("  conservative -- unusual, and worth understanding before relying on it.")
    else:
        print("  Consistent with the stated uncertainties being about right.")
    print(f"\n  n = {count}. A reduced chi-square on {dof} dof is itself noisy; this")
    print("  says which way to lean, not a calibration factor to divide by.")
    return 0


def _run_in_subprocess(smiles: str, label: str, iterations: int, platform_name: str) -> dict:
    """One replicate, in a FRESH PROCESS.

    **MEASURED, AND THE OBVIOUS IMPLEMENTATION IS WRONG BY 3.4x.** This
    first looped in-process, and five methane replicates then agreed to
    SD 0.042 while each claimed sigma 0.174 -- a reduced chi-square of
    0.06, which reads as "the uncertainties are conservative" and is not
    what was happening. Three replicates in SEPARATE processes, identical
    settings, gave SD 0.141:

        one process, 5 runs        SD 0.042   chi2/dof 0.06
        separate processes, 3      SD 0.141   chi2/dof 0.58

    openmmtools' `ContextCache` is global, so sequential replicates share
    context and integrator state and are one correlated chain rather than
    independent samples. A harness that silently reports a third of the
    real spread is worse than no harness, because every downstream
    comparison is then powered against the wrong noise.

    Forking costs one interpreter start per replicate -- seconds against a
    run of twelve minutes -- and buys independence by construction rather
    than by hoping the library has no global state.
    """
    import json
    import subprocess

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as handle:
        result_path = Path(handle.name)
    try:
        done = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--smiles", smiles,
             "--name", label, "--iterations", str(iterations),
             "--platform", platform_name, "--emit-json", str(result_path)],
            capture_output=True, text=True,
        )
        if not result_path.is_file() or not result_path.read_text(encoding="utf-8").strip():
            raise RuntimeError(
                "the replicate subprocess produced no result: "
                + (done.stderr or done.stdout or "no output")[-400:]
            )
        return json.loads(result_path.read_text(encoding="utf-8"))
    finally:
        result_path.unlink(missing_ok=True)


def _append_record(out_path: Path | None, record: dict) -> None:
    """One JSON object per line, flushed and closed immediately.

    Opened and closed per record ON PURPOSE: a run that dies part-way must
    leave every completed result on disk, and a held-open buffered handle is
    exactly how the ammonia arm was lost.
    """
    if out_path is None:
        return
    import json

    with out_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
        handle.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=0,
                        help="run one molecule N times and test the stated uncertainties")
    parser.add_argument("--emit-json", default=None,
                        help="internal: write this run's result as JSON and exit")
    parser.add_argument("--out", default=None,
                        help="JSONL results file; written as each run completes")
    parser.add_argument("--smiles", default=None)
    parser.add_argument("--freesolv", type=int, default=0,
                        help="reproduce FreeSolv's GAFF column on N small compounds")
    parser.add_argument("--name", default="")
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    parser.add_argument("--platform", default=None,
                        help="OpenMM platform; the fastest available if omitted")
    args = parser.parse_args()

    import openmm
    from openff.toolkit import Molecule

    if args.platform:
        platform_name = args.platform
    else:
        names = [openmm.Platform.getPlatform(i).getName()
                 for i in range(openmm.Platform.getNumPlatforms())]
        platform_name = next((n for n in ("CUDA", "OpenCL", "CPU") if n in names), "CPU")

    print(f"OpenMM {openmm.version.version}, platform {platform_name}")
    silence_citations()
    out_path = Path(args.out) if args.out else None
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.emit_json:
        if not args.smiles:
            parser.error("--emit-json needs --smiles")
        import json

        result = _one_molecule(args.smiles, args.name or args.smiles,
                               args.iterations, platform_name)
        Path(args.emit_json).write_text(json.dumps({
            "label": result["label"],
            "smiles": args.smiles,
            "iterations": args.iterations,
            "hydration_kcal_mol": result["hydration"],
            "sigma_kcal_mol": result["sigma"],
            "converged": result["converged"],
            "seconds": result["seconds"],
        }), encoding="utf-8")
        return 0

    if args.repeat:
        if not args.smiles:
            parser.error("--repeat needs --smiles")
        print(f"solute: {args.name or args.smiles}   {args.smiles}", flush=True)
        return repeat(args.smiles, args.name or args.smiles, args.repeat,
                      args.iterations, platform_name, out_path)
    if args.freesolv:
        return validate(args.freesolv, args.iterations, platform_name)
    if not args.smiles:
        parser.error("give --smiles or --freesolv N")

    print(f"solute: {args.name or args.smiles}   {args.smiles}")
    print(f"schedule: {ELECTROSTATIC_STATES} electrostatic + {STERIC_STATES - 1} steric "
          f"= {len(build_states())} states, {args.iterations} iterations x "
          f"{STEPS_PER_ITERATION} steps\n")

    molecule = Molecule.from_smiles(args.smiles)
    molecule.generate_conformers(n_conformers=1)
    molecule.assign_partial_charges("am1bcc")

    with tempfile.TemporaryDirectory() as scratch_dir:
        scratch = Path(scratch_dir)
        results = {}
        for solvated in (False, True):
            label = "solvated" if solvated else "vacuum"
            dg, sigma, diag = run_leg(molecule, solvated, args.iterations,
                                      platform_name, scratch)
            results[label] = (dg, sigma, diag)
            print(f"  {label:<9} dG(decouple) = {dg:8.3f} +/- {sigma:.3f} kcal/mol"
                  f"   [{diag['atoms']} atoms, {diag['seconds']:.0f} s]")
            print(f"    {'equilibration discarded':<28} "
                  f"{diag['equilibration_discarded']} of {diag['iterations']} iterations")
            print(f"    {'effective samples':<28} {diag['effective_samples']:.1f}"
                  f"   (statistical inefficiency {diag['statistical_inefficiency']:.1f})")
            overlap = diag.get("min_nearest_neighbour_overlap")
            print(f"    {'min adjacent-state overlap':<28} "
                  f"{'n/a' if overlap is None else format(overlap, '.4f')}")
            if "drift" in diag:
                verdict = "CONSISTENT" if diag["self_consistent"] else "*** NOT CONSISTENT ***"
                print(f"    {'first half':<28} {diag['first_half'][0]:.3f}"
                      f" +/- {diag['first_half'][1]:.3f}")
                print(f"    {'second half':<28} {diag['second_half'][0]:.3f}"
                      f" +/- {diag['second_half'][1]:.3f}")
                print(f"    {'halves differ by':<28} {diag['drift']:.3f}"
                      f", allowed {diag['allowed_drift']:.3f} at alpha={ALPHA}"
                      f"   {verdict}")

        dg_vac, s_vac, _ = results["vacuum"]
        dg_solv, s_solv, _ = results["solvated"]
        hydration = dg_vac - dg_solv
        sigma = math.sqrt(s_vac**2 + s_solv**2)

        print(f"\n  dG_hyd = dG_vacuum - dG_solvated = {hydration:.3f} "
              f"+/- {sigma:.3f} kcal/mol")

        # THE REFUSAL. A leg whose two independent halves disagree by more
        # than its own stated uncertainty allows has an uncertainty that
        # means nothing, and the difference of two such numbers means
        # nothing either. The value is still PRINTED -- withholding it would
        # lose the diagnostic information in it -- but it is labelled as not
        # a result, which is the same shape route 1's "no spread measured"
        # takes.
        inconsistent = [
            name for name, (_, _, d) in results.items()
            if "self_consistent" in d and not d["self_consistent"]
        ]
        if inconsistent:
            print(f"  NOT CONVERGED: the {' and '.join(inconsistent)} leg's two halves "
                  f"disagree by more than its stated uncertainty allows.")
            print("  The number above is NOT a result. Raise --iterations and re-run.")
        else:
            print("  Both legs are self-consistent between their halves at "
                  f"alpha={ALPHA}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
