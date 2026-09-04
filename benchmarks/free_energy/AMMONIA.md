# The ammonia gap — preregistration

Written **before the arms were run**, for the reason
`benchmarks/disposal/README.md` carries its own: a criterion chosen after
seeing the number is a description of that number, not a test of it. This
project has already recorded amending a preregistration on the strength of
an n=10 pilot and being wrong about the rate.

## What is being explained

`README.md`'s FreeSolv table, five compounds against the published
GAFF/AM1-BCC column:

    hydrogen sulfide      -1.201 +/-0.209    -1.14  -0.061   agrees
    ammonia               -1.219 +/-0.28     -4.02  +2.80    DISAGREES
    methane                2.035 +/-0.164     2.45  -0.415   DISAGREES
    methanol              -3.171 +/-0.215    -3.49  +0.319   agrees
    ethane                 1.876 +/-0.199     2.46  -0.584   DISAGREES

Ammonia is off by **2.80 kcal/mol**, an order above every other row and far
too large for sampling noise — the measured independent-replicate SD is
**0.141** on methane, so 2.80 is about twenty of them.

## The hypothesis, and why the arm that "refuted" it could not have

**H: the electrostatic lambda schedule is too coarse for a solute with a
large partial charge.** The shipped schedule is `ELECTROSTATIC_STATES = 5`,
i.e. lambda_elec at 1.00, 0.75, 0.50, 0.25, 0.00 — four intervals over the
whole of the charge decoupling.

`README.md` records this hypothesis as already tested and unsupported:
*"lambda schedule too coarse — denser spacing moved the estimate by 1.1
sigma, i.e. within noise"*. **That arm was run on METHANE**, and measured
here through the shipped charge path:

    compound            largest |partial charge|      dipole
    methane                        0.108 e            0.009 D
    ethane                         0.094 e            0.027 D
    hydrogen sulfide               0.440 e            1.671 D
    methanol                       0.599 e            1.833 D
    ammonia                        1.010 e            1.577 D

Methane's electrostatic leg is worth almost nothing, so **five windows are
ample there whatever the truth is about ammonia**, and the arm could not
have detected a coarse electrostatic schedule however it came out. That is
this project's own recorded lesson — a fixture is not big or small, it is
degenerate or not with respect to a specific defect — arriving for the
fourth time.

The charges themselves are **not** the explanation, and that was settled
first because it costs a minute rather than an hour: ammonia's AM1-BCC set
is N −1.0104 / H +0.3368, giving a dipole of 1.577 D against an
experimental 1.47 D. AM1-BCC is fitted to HF/6-31G* potentials, which
overestimate gas-phase dipoles by roughly 10–20%, so a ~7% overshoot is
what a *correct* charge set looks like.

## Arms

Ammonia (`N`), 150 iterations, three **forked** replicates each — forked
because in-process replicates were measured to understate the spread by
3.4x through openmmtools' global `ContextCache`.

| arm | schedule | states |
| --- | --- | --- |
| **A — control** | `--elec-states 5` (shipped) | 5 + 10 = 15 |
| **B — treatment** | `--elec-states 11` | 11 + 10 = 21 |

Sterics are held at 11 in both, so the only thing varying is the quantity
under test.

## Predictions, fixed in advance

- **If H is right:** arm A reproduces ≈ −1.2 and reports a poor minimum
  adjacent-state overlap on the solvated leg; arm B moves materially toward
  GAFF's −4.02 and reports better overlap.
- **If H is wrong:** both arms land near −1.2 with comparable overlap, and
  the gap is somewhere else entirely.
- **The overlap is the mechanism column.** It says whether neighbouring
  windows share configuration space at all, which is a statement about the
  schedule; the two-halves consistency test cannot make that distinction,
  which is exactly why it passed all five rows of a table with three wrong
  answers in it.

## Decision rule

Arms are compared as means with the standard error of the mean, against
GAFF's −4.02. An effect the size of the gap is ~20 replicate SDs, so n=3
per arm is ample to see one; if the effect is small, this correctly reports
it as unsupported rather than as absent.

**A null result ships.** If arm B does not move, H is recorded as
unsupported beside the three hypotheses already refuted, and the gap stays
open with one more explanation eliminated.

## Outcome

**H IS UNSUPPORTED, AND THE ARMS DID NOT BOTH RUN.** Stated first because
the preregistration promised them and one of them was stopped: what follows
is weaker evidence than was planned for, and it is reported as such.

    arm B, 11 electrostatic windows, replicate 1     -1.451 +/- 0.169
    arm B, replicate 2                               stopped mid-run
    arm A, 5 windows                                 not re-run; the value
                                                     on record is the
                                                     single -1.219 from the
                                                     original table

**The treatment arm's ABSOLUTE value is what refutes H, so the missing
control costs little.** If the schedule were the cause, doubling the
electrostatic windows would land near GAFF's -4.02. It landed at -1.451,
having moved about 0.23 from the control -- a twelfth of the gap. No
plausible control value makes that a success. The minimum adjacent-state
overlap on the solvated leg was 0.1115, which is not the near-zero a
starved schedule produces.

### Why it was stopped: a better explanation arrived by another route

Not because the result was inconvenient -- it was already going the way
recorded above. While arm B ran, the LJ parameters were checked against
AmberTools' own `gaff.dat` and `gaff2.dat`, and ammonia's nitrogen turned
out not to be typed `n3` at all:

    gaff-1.81    N sigma 0.32500 nm   epsilon 0.71128 kJ/mol   (n3)
    gaff-2.2.20  N sigma 0.40447 nm   epsilon 0.03975 kJ/mol   (n9)

`n9` is described in `gaff2.dat` as literally **"NH3"** -- GAFF2 gives
ammonia an atom type of its own. A core 24% wider with a twentieth of the
well depth is a much less well hydrated ammonia.

`GAFFTemplateGenerator` defaults to the newest installed GAFF, which is
2.2.20 here. FreeSolv's reference column is labelled **"Mobley group
calculated value (GAFF)"** in the database's own header and dates from 2017.
**The benchmark had been comparing two different force fields**, and nothing
in the stored result said which one it used.

### And the confirming run subsumes this experiment

The test of that explanation runs at the DEFAULT five-window schedule, so it
answers H as a side effect -- which is what made finishing arm B redundant
rather than merely expensive. Measured at 40 iterations, everything else
held:

    gaff-2.2.20   -0.672      the force field the benchmark was using
    gaff-1.81     -4.127      the force field its reference column used
    reference     -4.02       FreeSolv, GAFF
    experiment    -4.29

**The gap closes at five electrostatic windows.** So the schedule was never
the constraint, and H is refuted twice over -- once weakly by its own arm
and once decisively by a run that was not testing it.

### What this cost, and the lesson is one this project already had

Two GPU-hours, and both losses were mine rather than the science's. One arm
died to `CUDA_ERROR_UNKNOWN` because Windows CUDA probes were running
against the WSL job -- one physical card, two operating systems, and this
project's rule against concurrent work during a run it means to cite,
broken in a dimension it had not been written for. A second was lost to a
`numpy.bool_` that `json.dumps` refuses, in a field added by the very
harness change meant to enable this experiment; the smoke test could not
have caught it, because at three iterations the diagnostic that carries
that field is never computed.

**A fixture is degenerate or not with respect to a specific defect**, and a
three-iteration run is degenerate with respect to every diagnostic that
needs two halves. That is the fourth instance of that lesson in this
repository and the first where it was written by somebody who had read the
other three the same day.
