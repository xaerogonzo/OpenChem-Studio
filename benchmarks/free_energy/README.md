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

## THE WINDOWS WALLS: three stood, and two have fallen

Recorded because each cost time and none is obvious from a failure message.
**Two of the three are now solved**, and the account of one of them was
wrong in a way that mattered -- it named a platform incompatibility where
there was a missing file.

### STILL STANDING: AmberTools has no win-64 build

conda-forge publishes linux-64, linux-aarch64, linux-ppc64le, osx-64 and
osx-arm64 -- nothing else. Since `openmmforcefields` requires it,
**GAFF/AM1-BCC cannot run on Windows**, and that is the protocol FreeSolv's
reference column was computed with. Re-checked rather than assumed, and the
refusal is total: every published version of that package pins AmberTools,
so its SMIRNOFF template generator is unreachable too even though it needs
none of AmberTools itself.

    openmmforcefields 0.9.0 .. 0.11.2    ambertools >=20.0,<23
    openmmforcefields 0.13.0 .. 0.14.1   ambertools >=22,<24
    openmmforcefields 0.14.1 .. 0.16.0   ambertools >=22,<25 / >=22,<27

Worse, including it in a Windows conda spec makes the whole solve
unsatisfiable, and **conda reports that while exiting 0**.

### SOLVED: NAGL did not import, and it was ONE MISSING DLL

This file previously recorded that NAGL *"does not import on Windows
either... `ImportError: DLL load failed while importing _C`, which is
PyTorch's extension"*, and concluded that **both** charge routes were
blocked on the shipping platform. That reads as a platform incompatibility.
It is not one.

**`DLL load failed while importing _C` names the module that FAILED and
never the dependency that was absent**, so one message covers a dozen
unrelated causes and every fix for it is a guess. Reading `torch_cpu.dll`'s
own PE import table settles it in seconds -- 26 imports, 25 resolvable, and
exactly one not:

    libomp140.x86_64.dll        MISSING

`pe_imports.py` in this directory is that instrument, kept because the next
opaque DLL error will otherwise be re-derived from PE struct offsets:

    <env>/python.exe benchmarks/free_energy/pe_imports.py torch_cpu.dll

It reported one missing name before the fix and none after, so it can say
no as well as yes.

That is LLVM's OpenMP runtime under the name MSVC-built binaries link it by.
**AND IT IS NOT conda-forge's PACKAGE, WHICH THIS FILE SAID FOR A WHILE.**
That was asserted because the environment recipe says `-c conda-forge` and
never checked against what the solver did. Read out of `conda-meta`, the
build is

    pytorch  2.10.0  gpu_cuda130_py311h12d642b_203
    channel  https://repo.anaconda.com/pkgs/main/win-64

so `pytorch` and `libtorch` come from **Anaconda's `defaults`**, and they are
4 of the 227 packages in that environment that do. The error would have been
invisible until somebody filed a bug against the wrong maintainers, which is
exactly how it was caught. Same failure as this project's citation audit:
every one of those six errors was in the field nothing could check.

Neither package declares **any** OpenMP dependency -- not `pytorch`, not
`libtorch` -- so nothing installs the runtime and the solve looks clean. And
no candidate provider ships that name:

    intel-openmp   (defaults)      libiomp5md.dll, libiompstubs5md.dll, ...
    llvm-openmp    (conda-forge)   libomp.dll, libiomp5md.dll

**The build is a `nomkl`/openblas variant**, which matters: a pure-defaults
solve pulls `_openmp_mutex 52_intel` and `intel-openmp` through MKL, and this
environment has `nomkl` from conda-forge's openblas instead, so no OpenMP
runtime arrives at all. Whether the current defaults build (2.13.0, MKL) links
the same name was **not tested** -- it needs a 367 MB `libtorch` download --
so the scope of the upstream defect is one build and one variant.

The fix is two steps and 334 KB:

```bash
conda install -n <env> -c conda-forge llvm-openmp
# it ships libomp.dll; the binary wants the MSVC name for the same library
copy "%CONDA_PREFIX%\Library\bin\libomp.dll" "%CONDA_PREFIX%\Library\bin\libomp140.x86_64.dll"
```

Measured after: `torch 2.10.0`, `torch.cuda.is_available() True`, a CPU
matmul correct, and a bare import with the environment **not** activated.

**AND THE CHARGES IT UNBLOCKS AGREE WITH AMBERTOOLS.** NAGL is a graph
network trained to reproduce AM1-BCC, so the question is not whether it is
good in the abstract but whether it lands on the same numbers. Against the
WSL AmberTools values measured through the real `sqm` path:

    compound            max |dq|   RMSD q   mu NAGL   mu AmberTools    exp
    hydrogen sulfide      0.0003   0.0002     1.670          1.671    0.97
    ammonia               0.0014   0.0008     1.579          1.577    1.47
    methane               0.0003   0.0001     0.009          0.009    0.00
    methanol              0.0005   0.0002     1.833          1.833    1.70
    ethane                0.0005   0.0003     0.027          0.027    0.00

**Worst single-atom disagreement across all five: 0.0014 e**, against NAGL's
own published RMSE near 0.02 e. So on these solutes the Windows route is an
order better than the model's stated accuracy, and the charge step is not a
compromise.

Two false leads were eliminated first, each cheaply, and both are the kind
that would have been fixed by guessing:

- **PATH.** This project already records that a conda environment's Python
  invoked by absolute path does not get the environment's `bin`. It is the
  obvious explanation and it is wrong here: since CPython 3.8, PATH no
  longer resolves an extension module's dependent DLLs on Windows at all, so
  putting `Library\bin` on it changes nothing. Measured both ways.
- **A broken install.** `torch/lib` holds **zero** DLLs, which reads as a
  truncated download. It is the ordinary conda-forge Windows layout -- the
  libraries live in `Library\bin` -- and conda's own manifest reports 9111
  files recorded and **0 missing**. My first probe looked in the wrong
  directory and reached a confident wrong conclusion from it.

### SOLVED: the rest of the chain, with neither AmberTools nor packmol

Unblocking `import torch` unblocks CHARGES, and nothing else. Saying
"Windows works" on the strength of it would have been the same
over-reading, so the whole chain was run: parameterise, solvate, build the
alchemical system, sample, analyse.

Two further win-64 walls turned up there, and a third stood behind them:

    openmmforcefields   unsatisfiable, so BOTH template generators are gone
    packmol             no win-64 build, so Interchange's own solvation
                        route is gone with it

Neither is needed. **OpenMM will solvate an EMPTY topology**, which asks
nothing about the solute and therefore needs no template for it; the waters
that clash are then dropped geometrically, and Interchange parameterises
solute and water together from Sage plus TIP3P. About forty lines, no new
dependency. Measured end to end on ammonia, CPU, 8 iterations:

    NAGL charges, Sage + TIP3P system of 1276 atoms, alchemical system
    built, replica exchange run, MBAR analysed
    dG(decouple, solvated) = +3.051 +/- 1.725 kcal/mol in 238 s

Eight iterations is not a result and the number is not offered as one. What
it establishes is that **nothing after the charge step is blocked**.

`windows_route.py` is that route kept runnable, because the alternative is a
claim in this file that nobody can check. It imports `build_states` from
`hydration.py` rather than carrying a schedule of its own -- a five-state
demo schedule was tried first and produced a NaN at `lambda_sterics = 0.5`,
and sharing the real one also means this route cannot drift away from the
protocol it exists to show is reachable.

**THE REMAINING LIMIT IS SCIENTIFIC RATHER THAN TECHNICAL, and it does not
go away.** Windows runs **Sage**, not GAFF, because GAFF needs AmberTools.
So a Windows answer cannot be checked against FreeSolv's GAFF column at all
-- that comparison isolates the protocol precisely because both sides use
one force field, and a Sage-versus-GAFF difference would be the force field
speaking. Validation stays in WSL; Windows is the platform that would ship,
running a different and arguably better force field, and it needs its own
reference before any number of its own is believed.

### STILL STANDING, and harmless: conda-forge's CUDA outruns the WSL driver

The driver reports CUDA 13.2 and conda installed the 13.3 toolkit, giving
`CUDA_ERROR_UNSUPPORTED_PTX_VERSION`. The symptom is nasty: OpenMM **lists**
the CUDA platform and then cannot build a context on it. Pinning
`cuda-version=12.6` fixes it.

**And a conda environment's Python invoked by absolute path does not get the
environment's `bin` on `PATH`.** openff-toolkit then silently degrades to
whatever wrappers it can find and reports "no registered toolkits can provide
am1bcc" rather than "activate your environment". Use `conda run -n fep`. That
trap is real and is NOT what broke the Windows torch import, which is why
both are recorded rather than one being folded into the other.

### AND THE TWO GPUs ARE ONE GPU

Running the Windows CUDA probes while the WSL arms were sampling killed a
three-replicate arm with `CUDA_ERROR_UNKNOWN (999)` -- WSL2's passthrough
shares the physical device with the host. This project's rule against
concurrent work during a run it intends to cite was written about the
filesystem; it holds in the GPU dimension too, and did not survive first
contact with a machine that has one card and two operating systems on it.

## The environments

```bash
# WSL, for validation: the reference protocol, GAFF/AM1-BCC + CUDA
wsl -d Ubuntu -- ~/miniforge3/bin/mamba create -y -n fep -c conda-forge \
    python=3.11 openmm openmmtools openff-toolkit openmmforcefields \
    ambertools pymbar "cuda-version=12.6"

# Windows, for what would ship: no AmberTools, so Sage + NAGL.
# `openff-interchange` is what replaces openmmforcefields here, and
# `llvm-openmp` is what makes PyTorch import at all -- see the walls above.
conda create -y -n openchem-fep -c conda-forge python=3.11 \
    openmm openmmtools openff-toolkit openff-interchange openff-forcefields \
    openff-nagl openff-nagl-models llvm-openmp pymbar rdkit
```

**The Windows environment is not usable as created**, and that is the whole
point of the entry above: the win-64 `pytorch` that resolves here comes
from **Anaconda's defaults**, links `libomp140.x86_64.dll`, and declares no
OpenMP dependency, so the solve succeeds and the import does not. One copy
finishes the job:

```bash
copy "%CONDA_PREFIX%\Library\bin\libomp.dll" ^
     "%CONDA_PREFIX%\Library\bin\libomp140.x86_64.dll"
```

A shipped installer would carry that step, or better, the feedstock would
declare the dependency and it would not exist.

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

## What it measured: a failure, its cause, and the repeat

### FIRST, THE FAILURE -- kept, because the cause is the finding

This is what the benchmark reported for as long as it existed. Five
compounds, 150 iterations, 15 states, against FreeSolv's published GAFF
column:

    compound                        ours     GAFF    diff   sigma     exp  verdict
    hydrogen sulfide      -1.201 +/-0.209    -1.14  -0.061  0.209   -0.70  agrees
    ammonia               -1.219 +/-0.28     -4.02  +2.80    0.28   -4.29  DISAGREES
    methane                2.035 +/-0.164     2.45  -0.415  0.165    2.00  DISAGREES
    methanol              -3.171 +/-0.215    -3.49  +0.319  0.216   -5.10  agrees
    ethane                 1.876 +/-0.199     2.46  -0.584  0.200    1.83  DISAGREES

    MAE against GAFF 0.836 kcal/mol   agreeing 2/5   not converged 0 of 5

**THE ACCEPTANCE TEST FAILED, AND THAT WAS THE ACCEPTANCE TEST WORKING.**
MAE 0.836 against a per-run sigma near 0.2 is not a reproduction of
anything. The line that mattered most was `not converged 0 of 5`: every leg
passed its own two-halves consistency check while three results were wrong
by up to 2.8 kcal/mol.

That reads as the documented "an unconverged FEP returns a confident number"
failure, and it is worse than that. **The runs were not unconverged.** They
were converging correctly on a different force field -- and no convergence
diagnostic can detect that, because nothing is wrong with the sampling. A
diagnostics layer built without this external oracle would have pronounced
all five converged and been right to.

### THE CAUSE: two force fields, and nothing recorded which

`GAFFTemplateGenerator(molecules=...)` picks **the newest GAFF installed**,
which here is `gaff-2.2.20`. FreeSolv's reference column is labelled
*"Mobley group calculated value (GAFF)"* in the database's own header and
dates from 2017. The benchmark had been comparing GAFF2 against GAFF1 since
the day it was written, and **the stored result never said which force field
ran**, which is why four investigations went past it.

Ammonia is where the two part company hardest, because GAFF2 gives it an
atom type of its own -- `gaff2.dat` describes `n9` as literally "NH3":

    gaff-1.81    N sigma 0.32500 nm   epsilon 0.71128 kJ/mol   (n3)
    gaff-2.2.20  N sigma 0.40447 nm   epsilon 0.03975 kJ/mol   (n9)

A core 24% wider with a twentieth of the well depth is a much less well
hydrated ammonia. Read off the parameters, before any dynamics were run:

    compound          the biggest GAFF1 -> GAFF2 change       predicted
    methane           H epsilon +32.5%                        more soluble
    ethane            H epsilon +32.5%, six of them           more, and more
                                                              than methane
    methanol          O epsilon -55.8%, and the OH hydrogen
                      gains a core it did not have            LESS soluble
    hydrogen sulfide  S epsilon +13.0% vs H epsilon -21.0%    little change
    ammonia           N: a DIFFERENT ATOM TYPE                far less soluble

### THE REPEAT, at gaff-1.81

Identical protocol, identical schedule, identical code. One argument changed:

    compound                        ours     GAFF    diff   sigma     exp    ovl  verdict
    hydrogen sulfide      -1.064 +/-0.246   -1.14  +0.076  0.246   -0.70  0.137  agrees
    ammonia               -3.758 +/-0.251   -4.02  +0.262  0.251   -4.29  0.139  agrees
    methane                2.415 +/-0.164    2.45  -0.035  0.164    2.00  0.113  agrees
    methanol              -3.080 +/-0.303   -3.49  +0.410  0.303   -5.10  0.152  agrees
    ethane                 2.611 +/-0.207    2.46  +0.151  0.207    1.83  0.121  agrees

    MAE against GAFF 0.187 kcal/mol   agreeing 5/5   not converged 0 of 5

**THE ACCEPTANCE TEST PASSES.** MAE **0.836 -> 0.187**, and the compound that was
wrong by 2.8 kcal/mol is now inside its own uncertainty.

### WHAT THE REPEAT SAYS ABOUT THE PREDICTION -- three of five, honestly

A hypothesis that explains only the row it was invented for is worth little,
so the parameter-level predictions above are scored against what moved. The
noise is the measured one: the independent-replicate SD is 0.141, so the
difference of two single runs carries about 0.20.

    compound            GAFF2 diff   GAFF1 diff    moved    in units of the noise
    hydrogen sulfide      -0.061       +0.076    +0.137             0.7
    ammonia               +2.800       +0.262    -2.538            12.7
    methane               -0.415       -0.035    +0.380             1.9
    methanol              +0.319       +0.410    +0.091             0.5
    ethane                -0.584       +0.151    +0.735             3.7

    ammonia   12.7 sigma, and in the predicted direction. Decisive.
    ethane     3.7 sigma, predicted, and larger than methane's as predicted
    methane    1.9 sigma, predicted direction, marginal on its own
    H2S        0.7 sigma -- consistent with "little change", and equally
               consistent with nothing having happened
    methanol   0.5 sigma, and in the direction OPPOSITE to the prediction

**The methanol prediction is not confirmed.** It was predicted to move
toward the reference and moved 0.091 away from it, which is well inside the
noise -- so the honest statement is that methanol's row did not move
resolvably and the parameter argument is unsupported for it, not that it was
wrong. Two of the five rows cannot discriminate at this sample size.

So the account rests on ammonia and ethane, where the effect is many times
the noise and in the predicted direction, and on the aggregate: five rows
that disagreed 2/5 now agree 5/5 with a single argument changed.

`AMMONIA.md` carries the preregistered experiment that was running when this
turned up -- a lambda-schedule hypothesis, refuted, and stopped early with
the reason recorded. It is kept because the way it was aimed is the lesson:
the same hypothesis had been "tested" earlier on METHANE, whose largest
partial charge is 0.108 e against ammonia's 1.010, so that arm could not
have detected a coarse ELECTROSTATIC schedule however it came out.

### The run-to-run spread, which every other arm depends on

Methane at fixed settings, and the harness design turned out to matter more
than anything being measured:

    one process, 5 replicates      SD 0.042   mean sigma 0.174   chi2/dof 0.06
    separate processes, 3          SD 0.141   mean sigma 0.190   chi2/dof 0.58
                                   ratio 3.4x

**Sequential replicates in one process are correlated** -- openmmtools'
`ContextCache` is global -- so the in-process harness reported a third of the
real spread, and reported it as "the uncertainties are conservative".
`--repeat` forks per replicate for that reason, and **`validate()` now forks
per compound too**: the GAFF2 table above ran all five in one process, which
is the arrangement measured to correlate replicates of one molecule and was
never established to be safe across different ones. The table above it does
not.

With independent replicates the stated uncertainties are **about right**
(chi2/dof 0.58 on 2 dof, noisy but showing no underestimation). An earlier
suspicion that they were optimistic is not supported.

### What the diagnostics could not do, and now can

The two-halves test asks whether a run is consistent with its own claimed
uncertainty. It cannot ask whether the right thing was simulated, and the
GAFF2 table is what that distinction costs: five green verdicts over three
wrong answers. Three things were added because of it:

    the force field       recorded in every result, and pinned
    the free energy SPLIT dG_electrostatic and dG_steric, per leg
    the overlap column    reported per compound in `validate`

The split is the diagnostic one level finer than overlap. Ammonia at
gaff-1.81 reports `elec +5.855, steric -1.729` on the solvated leg -- an
H-bonding solute that costs a lot to discharge and gains a little to
deflate. A total alone cannot say which half is wrong, and ammonia's whole
discrepancy lived in one of them.

**AND THE OVERLAP COLUMN WAS VACUOUS ON ITS FIRST RUN.** Taking the minimum
over BOTH legs is the obvious form, and it printed **0.067 for all five
compounds** -- exactly 1/15, because a small neutral solute has no
intramolecular nonbonded pairs, so every vacuum state is identical and its
overlap is 1/n_states by construction. A column that always prints a
constant is a check that cannot fail. It reports the solvated leg now, where
the five range 0.113 to 0.153.

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
