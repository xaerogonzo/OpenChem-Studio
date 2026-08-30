# Does the mid-test `DeferredDelete` flush move the Linux crash rate?

**THIS IS A PREREGISTRATION. Everything below the line was fixed before
either arm was dispatched**, because a threshold chosen after seeing a
number is a description of that number and not a test of it — the
discipline `benchmarks/solubility/base_bias.py` already applies here, and
the one that made its `0.0009` miss meaningful rather than negotiable.

## Why this experiment exists

Two things, and neither is a traceback frame on its own.

**The recurrence.** Across the whole Linux crash history, exactly two
frames belong to us, and they are the same line of the same three-line
recipe in unrelated files:

    tests/test_panel_rail.py:19        in _dispose
    tests/test_screening_service.py:269 in widgets

Both are `QCoreApplication.sendPostedEvents(widget, DeferredDelete)`.

**The prior.** `tests/conftest.py` documents `dispose_app_widgets`, a
reverted fixture that destroyed abandoned widgets with the same
per-object `deleteLater()` plus flush, and which **crashed the suite 8 of
8 full runs** on master while 8 of 8 completed with it neutered.

That experiment was about the *automatic* fixture, which discovered 112
widgets by itself. The hand-written copies a test hands over explicitly
have never been A/B'd — there were 64 of them across 46 files
(`git show dba03eb:benchmarks/disposal/inventory.md`), and they are now
one `conftest.dispose`.

**This is a LEAD, not a cause.** For a fatal signal a traceback frame is
still wherever the process happened to be. What licenses an experiment is
the recurrence *plus* the prior, not either frame alone.

---

## The variable, in one sentence

**Arm A (control)** is `setParent(None)` + `deleteLater()` + an immediate
per-object `DeferredDelete` flush. **Arm B (treatment)** is
`setParent(None)` + `deleteLater()`, with the normal end-of-test flush
(`flush_deferred_deletes`) performing the deletion.

**Both arms destroy the object. Only the timing of `DeferredDelete`
changes.** Nothing is left queued in either arm.

## One commit, one env var — not two branches

`OPENCHEM_DISPOSE_FLUSH=0` selects the treatment. Both arms therefore run
a **byte-identical tree**.

That is not convenience. This branch's own finding is that a
byte-identical tree crashes in *different files on different runs*, so an
A/B whose arms are different commits invites exactly the explanation it
cannot rule out. The refactor that produced `conftest.dispose` is
likewise **not** an experimental variable: both arms use it.

## The outcome

Per leg, one Bernoulli trial: **crashed = the census trail lacks the
`# session finished` sentinel**, read through `tools/read_census.py`.

Never a grep of `suite.log` — that phrase appears in `conftest`'s own
docstring, so the grep counts its own subject; measured, a run reporting
"crash markers: 4" had not crashed. And never a bare `not finished`
either: `Census.usable` separates *"it crashed"* from *"the trail could
not be read"*, and collapsing those scores a leg that produced no
evidence as a crash.

## Decision rule — fixed now

- **n = 10 per arm.** Both arms dispatched on the same branch with no push
  between them, or `cancel-in-progress` voids one.
- **Two-sided Fisher exact.** `p < 0.05` → an effect. Otherwise
  **insufficient evidence, change nothing**, and report the interval.
- **Escalation:** if wave 1 lands in `[0.05, 0.20]`, run one wave 2 to
  n = 20 per arm and re-test **once**. No further escalation.
- **A partial matrix is refused, not averaged.** `score.py score`
  requires exactly the replica set it was told to expect, and every leg to
  carry a pytest summary *or* a census trail. An arm that does not run is
  not an arm.
- **Arm B does not land on master** unless the experiment says so, and
  then only with its evidence attached.

## The power, stated up front

At n = 10 per arm this detects only near-total elimination:

| control | treatment | Fisher p |
| --- | --- | --- |
| 5/10 | 0/10 | 0.0325 |
| 5/10 | 1/10 | 0.1409 |
| 5/10 | 5/10 | 1.0000 |
| 10/20 | 2/20 | 0.0138 |

So a real-but-partial effect is expected to come back as *insufficient
evidence*, and that is the honest outcome rather than a failure of the
experiment.

**A zero cell is the expected success case**, which makes the odds ratio
infinite. It is reported as `undefined` and the Wilson intervals carry the
claim — applying a continuity correction there would invent a finite
number the data does not contain.

## The control arm is worth having whatever the treatment does

Nobody has ever measured this crash's rate at n = 10 on a **fixed** tree.
The ~50% figure this branch quotes (9 crashes in 18 runs) is across trees
that all differ.

## Running it

```bash
gh workflow run tests.yml --ref BRANCH -f linux_replicas='[1,2,3,4,5,6,7,8,9,10]' -f dispose_flush=1
```

…then the same with `dispose_flush=0`, **after the first run completes**.
Download each leg's `leg.json` from its artifact and:

```bash
uv run --no-sync python benchmarks/disposal/score.py score legs/*.json --expect '{"control":[1,2,3,4,5,6,7,8,9,10],"treatment":[1,2,3,4,5,6,7,8,9,10]}'
```

Reading the per-leg verdict from CI directly, since `gh run view --json`
reports this job as `success` no matter what — three mechanisms
deliberately turn it green:

```bash
gh api repos/xaerogonzo/OpenChem-Studio/commits/SHA/check-runs --jq '.check_runs[] | select(.name|startswith("linux")) | .id'
```

---

# AMENDMENT 1 — the pilot refuted the rate the power was computed against

**What was known when this was written:** the control arm had run at
n = 10 and the treatment arm had **not been dispatched at all**. No
comparison existed, and none was computed until after this was committed.

## The pilot

Run [33330587107](https://github.com/xaerogonzo/OpenChem-Studio/actions/runs/33330587107),
commit `1189098`, control arm, 10 legs, all 10 accounted for:

    crashed  3 / 10     replicas 4, 8, 9 -- all in test_nmr_view_dialog.py
    clean    7 / 10     6382 tests each

**This is the first measurement of this crash's rate on a FIXED tree.**
Every earlier figure — the "9 in 18" this branch quotes — is across trees
that all differ. On one tree it is **0.30**, not the ~0.50 the power
table above assumed.

## Why that breaks the design as written

The whole power calculation was anchored on a control rate near 0.5. At
0.3 the experiment cannot reach its own threshold **even if the treatment
eliminates the crash completely**:

| control | treatment | Fisher p |
| --- | --- | --- |
| 3/10 | 0/10 | **0.2105** |
| 3/10 | 1/10 | 0.5820 |

0.2105 also falls **outside** the preregistered escalation band
`[0.05, 0.20]`, by four thousandths. So the rule as written would have
run arm B, observed the strongest result the experiment can produce,
declared *insufficient evidence*, and then **declined to escalate** —
terminating on a technicality rather than on a finding.

At n = 20 per arm the same rates give `6/20 vs 0/20 → p = 0.0202`, which
can clear the threshold.

## The amendment

**n = 20 per arm, both arms, dispatched fresh.** Everything else — the
0.05 threshold, the refusal, "insufficient evidence, change nothing" as
an allowed outcome — is unchanged.

**THE PILOT'S LEGS ARE NOT POOLED IN**, and that is the point rather
than fastidiousness. Committing this amendment changes the tree, so
wave-1 and wave-2 control legs would run different commits — and this
branch's own finding is that a byte-identical tree crashes differently
run to run. Pooling across commits inside one arm is exactly the confound
the env-var design was chosen to avoid. The pilot is reported as a
pilot: it estimated the rate, and that is all it is used for.

**This is sample-size re-estimation on a NUISANCE parameter, not on the
effect.** The control rate is not what the experiment is about, and the
treatment arm was unrun when this was written. That is a recognised
internal-pilot design; it is not the same as widening a threshold after
seeing a p-value, and it must not be used to license that later.

**The honest admission:** the power table above was written from an
assumed rate rather than a measured one, in a document whose whole
purpose is to fix the rules in advance. Measuring the control rate first
is what a pilot is FOR, and this preregistration should have called for
one instead of guessing.

---

## Results

*Not yet run at n = 20.* This section is written after the dispatch, and
neither the threshold nor the refusal is renegotiated when it is.
