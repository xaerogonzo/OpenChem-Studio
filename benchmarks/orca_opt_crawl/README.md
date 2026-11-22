# ORCA optimization crawl on oenanthotoxin (Phase 0 notes)

Started 2026-11-20. One 41-atom oenanthotoxin conformer, ORCA 6.1.1 `! B3LYP def2-SVP Opt`, `%pal nprocs 12`, no `%geom` block
(the application's own input). This file records what was MEASURED and what has NOT been run yet. Nothing here changed an
application default.

## Measured on the stalled ORCA run (read from its scratch folder, 111 trajectory frames)

* The run took about 27 s per geometry cycle. The energy was within about 0.3 kcal/mol of its final value by cycle 8; the next
  ~100 cycles gained about 0.14 kcal/mol, with heavy atoms drifting about 0.005 A per step (0.35 A in total).
* The maximum gradient sat at 2 to 5e-4 Eh/bohr against the 3e-4 default threshold for about 100 cycles.
* ORCA printed "Reseting .opt file and rebuilding internals" in about 101 of 106 cycles, with about 1,500 "RMS(Cart) too big" and
  500 "RMS(Cart) increases" messages: its internal-to-Cartesian step kept failing and it kept discarding its Hessian history.
  `(2022 redundants)` in that output is the NAME of ORCA's coordinate scheme, not a count.
* The cause is not established. Candidates (not tested): near-linear angles of the C#C-C#C unit in redundant internals, COSX
  gradient noise, a very flat surface. Cicutoxin, which also has a diyne, took about 15 minutes in the same application.
* How the job ended was not observed. ORCA's documented default cap, `max(3N, 50)` = 123 for 41 atoms, was taken from the manual
  and not checked against output; the trajectory ended at 111 frames.

## Measured with xtb 6.7.1 (GFN2-xTB, `--opt`, 4 threads, this machine)

| Start | Converged | Iterations | Wall time | Heavy-atom RMSD to ORCA's last frame |
|---|---|---|---|---|
| ORCA's last frame (cycle 111) | yes | 17 | 1.7 s | 0.087 A (all atoms 0.101 A) |
| The ORIGINAL input geometry | yes | 22 | 0.5 s | 0.346 A |

The two xtb structures are 0.328 A apart (heavy atoms). So for this molecule "converged" geometries from different starts or
methods differ by a few tenths of an angstrom along soft chain modes, and an optimization that keeps creeping is chasing that
softness, not an error that more cycles would remove. One molecule, one run each: this is an observation, not a benchmark. The
earlier 20-small-molecule xtb comparison (`benchmarks/xtb_comparison/PREREGISTRATION.md` section 14, median 0.014 A) does not
cover floppy chains like this.

## NOT run yet: deferred to the next PR (each needs the ORCA job slot and the machine for a while)

Track A (reproduce from the original geometry, unmodified input, record cycles, per-cycle time, five criteria, resets,
termination reason); Track B from the last frame, one change at a time: normal Opt, `COpt`, `%geom cartfallback true`, `DefGrid3`,
`NoCOSX`, `LooseOpt`, BP86 def2-SVP with RI-J, Psi4 B3LYP def2-SVP; thread counts 4, 8, 12; the same on cicutoxin. Only after
these are in should any ORCA default in the application change (Phase 2 of the plan). This PR changes no ORCA default: it adds
the progress readout, the complete log, Stop and keep geometry, and the engine choice (Phases 1 and 3).

Files kept outside the repository: the job's `job.inp`, `job.xyz`, `job_trj.xyz` and `job.opt` in
`Documents\OpenChem Studio random notes\oenanthotoxin_orca_job_c3zwvcct`; the xtb runs in `D:\_scratch\oenan_phase0`.
