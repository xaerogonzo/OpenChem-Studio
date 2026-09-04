# Free energy benchmarks — Route 3

`docs/ROADMAP.md`'s third route to ranking affinities: relative binding free
energy, the method actually designed for "does A bind more tightly than B"
in a congeneric series. Its recorded risk is the silent kind — **an
unconverged FEP returns a confident number** — so nothing here reports a
free energy without the diagnostics that say whether to believe it.

## Feasibility, measured rather than estimated

The roadmap said "hours of GPU per ligand PAIR" and that OpenMM was
installable. Both are now measured on this machine (RTX 4060, 8 GB,
compute 8.9, driver 595.95):

| | |
| --- | --- |
| OpenMM on Windows | **8.6.0 from PyPI**, Python 3.13, no conda, no compiler |
| Windows platforms | Reference, CPU, **OpenCL** — no CUDA in the PyPI wheel |
| Windows OpenCL | **251 ns/day** on a 27k-atom PME system, 2 fs, HBonds |
| WSL2 CUDA | **266 ns/day** on the identical system |
| CPU | 10.3 ns/day (Windows), so the GPU is **24×** |

**CUDA is only 6% faster than OpenCL here**, which is the useful surprise:
the platform this application ships on is not meaningfully penalised, so
WSL's value is AmberTools, not speed.

At 251 ns/day a conventional RBFE pair costs:

    12 windows x 5 ns x 2 legs    120 ns   ~11.5 h per ligand PAIR
    12 windows x 2 ns x 2 legs     48 ns    ~4.6 h
    20 windows x 5 ns x 2 legs    200 ns   ~19.1 h

So the roadmap's estimate stands, and route 3 is a multi-day commitment for
any real series.

## Three toolchain walls, all on Windows

Recorded because each cost time and none is obvious from a failure message.

**AmberTools has no win-64 build.** conda-forge publishes linux-64,
linux-aarch64, linux-ppc64le, osx-64 and osx-arm64 — nothing else. Since
`openmmforcefields` requires it, **GAFF/AM1-BCC cannot run on Windows**, and
that is the protocol FreeSolv's reference column was computed with. Worse,
including `openmmforcefields` in a Windows conda spec makes the whole solve
unsatisfiable, and **conda reports that while exiting 0**.

**NAGL — the AmberTools-free charge route — does not import on Windows
either**, in this environment: `ImportError: DLL load failed while importing
_C`, which is PyTorch's extension. So on Windows *both* charge routes are
currently blocked, and the Sage path needs that fixed before it can ship.

**conda-forge's default CUDA is newer than the WSL driver.** The driver
reports CUDA 13.2 and conda installed the 13.3 toolkit, giving
`CUDA_ERROR_UNSUPPORTED_PTX_VERSION`. The symptom is nasty: OpenMM **lists**
the CUDA platform and then cannot build a context on it. Pinning
`cuda-version=12.6` fixes it.

**And a conda environment's Python invoked by absolute path does not get the
environment's `bin` on `PATH`.** openff-toolkit then silently degrades to
whatever wrappers it can find and reports "no registered toolkits can provide
am1bcc" rather than "activate your environment". Use `conda run -n fep`.

## The environments

```bash
# WSL, for validation: the reference protocol, GAFF/AM1-BCC + CUDA
wsl -d Ubuntu -- ~/miniforge3/bin/mamba create -y -n fep -c conda-forge \
    python=3.11 openmm openmmtools openff-toolkit openmmforcefields \
    ambertools pymbar "cuda-version=12.6"

# Windows, for what would ship: no AmberTools, so Sage + NAGL
conda create -y -n openchem-fep -c conda-forge python=3.11 \
    openmm openmmtools openff-toolkit-base openff-nagl openff-nagl-models \
    pymbar rdkit
```

## `freesolv.py` — the oracle

642 small molecules with experimental hydration free energies **and** the
value the Mobley group calculated with GAFF/AM1-BCC at σ ≈ 0.03.

**The calculated column is the target, not experiment.** Comparing to
experiment conflates a wrong protocol with a right protocol on an imperfect
force field. Measured over all 642 compounds, that force field is itself
**MAE 1.11 / RMSE 1.54 kcal/mol** from experiment — so agreeing with
experiment to better than about a kcal/mol would be luck rather than skill.
Reproducing a number computed with the *same* force field is a statement
about our machinery.

Fetched and cached under `benchmarks/free_energy/cache/`, gitignored;
nothing is committed. The parser fails closed on the column count, because a
reshaped file would silently put the calculated value in the uncertainty's
place.

## `hydration.py` — the smallest honest calculation

A relative binding free energy needs parameterisation, protein prep, an atom
mapping, a lambda schedule, replica exchange and MBAR, and an error in any of
them returns a confident number. A hydration free energy exercises all of
that except the mapping and the protein, runs in minutes, and has a published
value to check against — so it proves the machinery before a protein is
allowed near it.

**The thermodynamic cycle is stated, not implied.** Both legs are run and
subtracted, with both electrostatics and sterics annihilated identically in
each, so the answer does not depend on the annihilation choice:

    dG_hyd = dG_vacuum(decouple) - dG_solvated(decouple)

A dropped leg or a sign error produces a number in the right units and the
right ballpark. That is exactly why the FreeSolv comparison exists.

Electrostatics are switched off **before** sterics — removing charges while
the particle is still soft lets them collapse onto solvent.

## The convergence refusal, and its honest limit

The verdict rests on a **self-consistency test, not a threshold in
kcal/mol**: the trajectory is split into two independent halves, each
analysed alone, and if they disagree by more than their combined uncertainty
allows at α = 0.05, the claimed uncertainty is wrong whatever it says. Same
α as `domain/affinity_range.py`, and for the same reason — a decision
expressed as a confidence level is derived, where one in kcal/mol is a
constant somebody fitted and the next person tunes.

Overlap and mixing are reported as **diagnostics, not gates**. A minimum
overlap threshold is a rule of thumb and this project does not ship rules of
thumb as refusals.

**THE TEST IS NECESSARY AND NOT SUFFICIENT, and its power scales with the
sampling.** A short run has large uncertainties, so its two halves agree
easily — passing means "no inconsistency was detected", not "converged".
Measured directly on methane:

    20 iterations   +2.030 +/- 0.350 kcal/mol
    60 iterations   +2.687 +/- 0.294

The estimate moved **0.66 kcal/mol, about twice the first run's stated
uncertainty**. That is route 3's documented failure mode observed live, and
it is the reason the diagnostics are printed for every leg rather than
summarised into a single verdict.

## What it measured, and it does not reproduce the reference

Five smallest neutral FreeSolv compounds, 150 iterations, 15 states, **all
five in one process** — which is a caveat on the table rather than a detail,
see below:

    compound                        ours     GAFF    diff   sigma     exp  verdict
    hydrogen sulfide      -1.201 +/-0.209    -1.14  -0.061  0.209   -0.70  agrees
    ammonia               -1.219 +/-0.28     -4.02  +2.80    0.28   -4.29  DISAGREES
    methane                2.035 +/-0.164     2.45  -0.415  0.165    2.00  DISAGREES
    methanol              -3.171 +/-0.215    -3.49  +0.319  0.216   -5.10  agrees
    ethane                 1.876 +/-0.199     2.46  -0.584  0.200    1.83  DISAGREES

    MAE against GAFF 0.836 kcal/mol   agreeing 2/5   not converged 0 of 5

**THE ACCEPTANCE TEST FAILS, AND THAT IS THE ACCEPTANCE TEST WORKING.** MAE
0.836 against a per-run sigma near 0.2 is not a reproduction of the
reference protocol.

**The line that matters most is `not converged 0 of 5`.** Every leg passed
its own two-halves consistency check while three results are wrong by up to
2.8 kcal/mol. That is precisely the "an unconverged FEP returns a confident
number" failure, and only the external oracle caught it. A diagnostics layer
built without this benchmark would have pronounced all five converged.

### The run-to-run spread, which every other arm depends on

Methane at fixed settings, and the harness design turned out to matter more
than anything being measured:

    one process, 5 replicates      SD 0.042   mean sigma 0.174   chi2/dof 0.06
    separate processes, 3          SD 0.141   mean sigma 0.190   chi2/dof 0.58
                                   ratio 3.4x

**Sequential replicates in one process are correlated** — openmmtools'
`ContextCache` is global — so the in-process harness reported a third of the
real spread, and reported it as "the uncertainties are conservative".
`--repeat` forks per replicate now, for that reason.

With independent replicates the stated uncertainties are **about right**
(chi2/dof 0.58 on 2 dof, noisy but showing no underestimation). An earlier
suspicion that they were optimistic is not supported.

### So the methane discrepancy is real

    three independent runs   2.010, 2.238, 2.269
    mean                     2.172   SE of the mean 0.082
    GAFF reference           2.45
    difference               -0.278  =  3.4 SE

Not noise. Something in this protocol differs from FreeSolv's, and the
hypotheses tested so far are all refuted:

- **alchemical PME treatment** — already `exact` by default, not
  `direct-space`
- **alchemical dispersion correction** — already enabled by default
- **lambda schedule too coarse** — denser spacing moved the estimate by
  1.1 sigma, i.e. within noise, and moved the minimum adjacent-state
  overlap the *wrong* way (0.111 -> 0.054). Unsupported, and the arm was
  underpowered because the effect sought was the size of the noise
- **state leaking between molecules in one process** — refuted in seconds:
  methane's prepared system is byte-identical whether or not ammonia ran
  first (same AM1-BCC charges, nonbonded parameters, 435 waters, box and
  coordinates)

**Ammonia's 2.8 kcal/mol gap is the outstanding lead**, being far too large
for sampling and an order above the hydrophobes' 0.4-0.6. It has not been
re-measured with independent replicates, and that is the next experiment,
not a conclusion.

### The table above ran all five compounds in ONE process

Which is exactly the arrangement measured to correlate replicates of the
same molecule by 3.4x. Whether it also affects DIFFERENT molecules in
sequence is **untested** — the byte-identical system fingerprint above says
setup is unaffected, and says nothing about sampling.

So each row is one run whose stated sigma may or may not describe it, and
`validate()` should fork per compound as `--repeat` now does before the
table is quoted again. The methane row is the one to weigh: at 2.035 it sits
comfortably inside the three-run independent spread of 2.010-2.269, so for
that compound the single-run value was not misleading. One compound is not
five.

### Three ways a result was destroyed, all harness rather than science

Recorded because each cost a run and none announced itself.

**OpenMM's citation banner writes past Python's buffer.** It interleaved
through half-written lines and an entire ammonia arm became unrecoverable
from the log. Silenced via `MultiStateSampler._global_citation_silence`, and
results now go to JSONL as they are produced, so stdout is never the record.

**WSL clears `/tmp` when the VM shuts down on idle.** A completed
five-replicate JSONL was written and then destroyed between the run
finishing and being read. Results belong under `benchmarks/free_energy/results/`,
which is on the Windows filesystem and gitignored.

**`python` without `-u` buffers a redirected run**, so a 40-minute job looked
silent and dead when it was fine. This project's own suite command uses `-u`.
