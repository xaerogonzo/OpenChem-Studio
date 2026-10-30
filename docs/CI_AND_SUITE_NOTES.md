# CI and test-suite notes

CI timeouts, Windows and Linux shard crashes, suite timing, how PRs are merged here, and the mechanics of running the suite. Most entries record a measurement and what it ruled out, so the next person does not repeat the chase.

These sections were moved here on 2026-10-29 from the assistant's private memory, so they are readable, searchable and versioned with the code. The text is kept as it was written (headings demoted one level, memory links written as plain names); dates and PR numbers are those of the time. Treat a measurement as true of the commit it was made on, and check a file or function named here still exists before relying on it.

## Contents

- [project-shard3-timeout-2026-10-14](#project-shard3-timeout-2026-10-14) — CI shard 3/3 timed out at the 30-min step on master and on two PRs on 2026-10-14; the red is capacity, not a test; how it was told apart from a regression
- [project-handoff-2026-10-07-shards-and-naming-prs](#project-handoff-2026-10-07-shards-and-naming-prs) — State of play at 2026-10-07 ~03:30 UTC when Alex archived the sessions to start over: open PRs #239 and #242, the fork ports of #235 and #239 (DONE, fork #24), three-shard CI + ruleset facts, and what is deliberately NOT being done
- [project-suite-time-and-linux-closed](#project-suite-time-and-linux-closed) — MERGED #92/#93 (2026-09-12): 30% of the suite is one gc.collect() that nothing cheaper can replace, the suite is sharded, and the Linux crash chase is CLOSED by Alex's decision
- [project-windows-crash-chase-2026-10](#project-windows-crash-chase-2026-10) — the 2026-10 Windows crash measurements: what was measured and ruled out, what is open, and that Alex stopped the chase on purpose
- [project-disposal-flush-experiment](#project-disposal-flush-experiment) — RESULT: the disposal flush is NOT the cause -- 13/20 vs 11/20, p=0.75 over 40 CI legs. The Linux victim spans FIVE files and the fixed-tree rate is 0.54
- [reference-ci-and-windows-crash-index](#reference-ci-and-windows-crash-index) — CI, suite timing and the Windows/Linux crash work, including the 2026-10 crash-measurement harness, its null results and the shard pins
- [reference-ci-vendor-tests-timeout](#reference-ci-vendor-tests-timeout) — vendor-tests.yml's 40-min CI timeout was set for a 3209-test suite; it grew to 5212 (+62.5%) with the timeout never recalibrated — bumped to 90 min, 2026-09-22
- [reference-actions-workflow-traps](#reference-actions-workflow-traps) — GitHub Actions traps hit building the crash-measurement workflow: YAML comment in a name, colon in artifact names, same-named job logs, SHA dispatch
- [reference-linux-crash-is-one-file](#reference-linux-crash-is-one-file) — SUPERSEDED TWICE: not one file, and the investigation is now CLOSED (2026-09-12). The victim tracks DEPTH, not a fragile test. Read leg.json, not the annotation -- the annotation API drops ~1 in 4 verdicts
- [reference-windows-gate-timeout](#reference-windows-gate-timeout) — Windows CI timeout, three rounds: gates split into their own job (09-10), then the suite itself SHARDED into two jobs at 30 min each (PR #93, 09-12) after measuring that 30% of it is one gc.collect() nothing cheaper can replace
- [reference-windows-shard-crash-and-composition](#reference-windows-shard-crash-and-composition) — the Windows CI shards crash in conftest.dispose at ~77% (test_result_presentation), and adding a test file re-balances the split so master's green history is not your shard's
- [reference-suite-shard-pins](#reference-suite-shard-pins) — tools/suite-shard-pins.json pins each test file to its Windows shard so adding a file moves no other file; how to add and re-pin
- [reference-one-run-is-not-a-duration](#reference-one-run-is-not-a-duration) — Suite-duration comparisons here are noise-dominated: the same tree measured 28:04 and 34:30, so never attribute a slowdown from one run per side
- [reference-measure-test-counts-on-a-clean-tree](#reference-measure-test-counts-on-a-clean-tree) — Test counts measured in Alex's main checkout are inflated by his in-progress work; collect against a clean worktree before quoting a number
- [reference-full-suite-needs-background](#reference-full-suite-needs-background) — OpenChem's full suite (6-19 min) exceeds the Bash tool's 10-minute cap, so it must be run with run_in_background
- [reference-waiting-for-background-jobs](#reference-waiting-for-background-jobs) — How to wait on a long real-ORCA drive or full suite without flooding the session -- foreground until-loop, ONE Monitor at most, 600 s foreground cap
- [reference-run-tests-with-python-m-pytest](#reference-run-tests-with-python-m-pytest) — ten OpenChem test files import tests.conftest; `uv run pytest <file>` cannot import it and `python -m pytest` can, so a targeted run of them reads as a harness artifact while testing nothing
- [reference-vendored-suite-needs-jre-on-path](#reference-vendored-suite-needs-jre-on-path) — tests/vendor needs the JRE on PATH *and* JAVA_HOME set -- PATH alone silently SKIPS the OPSIN round-trip tests, which is worse than the failure it prevents
- [reference-run-app-gate-out-collision](#reference-run-app-gate-out-collision) — tools/run_app_gate.sh --out colliding with the --sha-derived worktree path makes the script's own rm -rf wipe the fresh worktree
- [reference-dipole-test-signed-zero-flake](#reference-dipole-test-signed-zero-flake) — tests/test_dipole_typed.py failed shard 3 intermittently on unrelated PRs (benzene | eem and | qeq): the fixture recorded the SIGN of 1e-15 D noise; fixed in PR #374 (cf773a4b) by ignoring the sign of a number that prints as zero
- [reference-merging-prs-and-required-checks](#reference-merging-prs-and-required-checks) — How a PR actually gets merged here: gh-api merge is blocked by the auto-mode classifier, auto-merge needs the ruleset, a path-filtered workflow cannot be a required check, and how to rebase a stack onto a squash-merged base without force
- [reference-branch-and-scratch-cleanup-rule](#reference-branch-and-scratch-cleanup-rule) — What is safe to delete after a naming round: local branches with a MERGED PR whose tip is on a remote branch, merged fork branches, merged-round scratch dirs; what to keep and report
- [project-conformer-descriptor-race-stack](#project-conformer-descriptor-race-stack) — #334 MERGED (restore path, one owner per shape id); #336 (in-flight drawing run, _GeometryClaims) retargeted to master, CI running, merge is Alex's call

## project-shard3-timeout-2026-10-14

*From the assistant's notes (`project_shard3_timeout_2026_10_14.md`, type: n/a).*  
*CI shard 3/3 timed out at the 30-min step on master and on two PRs on 2026-10-14; the red is capacity, not a test; how it was told apart from a regression*

On 2026-10-14 `test suite 3/3` failed on the last three completed `tests` runs: master `445de7e` (a push, no PR code), `claude/derived-scores-slice-1` `d8fa80d`, and PR #330 `04abeea`. Each was `The action 'Run this shard of the test suite' has timed out after 30 minutes` with no failed test: slice-1 even printed `3944 passed ... in 1791.67s (0:29:51)` and then timed out on the step total. The crash classifier then logs "CRASHED, retrying once (no test failed)" and the next step "FAILED: ... This was not a crash", which reads as a crash and is neither. At the base commit `4f4c47f` the same shard passed in 27:17. Job durations across the three shards that day: 30.8 + 27.5 + 30.8 = 89 min against 90 of budget (shard 1 sits at 30.4-30.8 and passes by seconds).

**Why:** the pinned split models per-test time and the shards are at capacity, so a good day is ~2-3 min under the cap and run-to-run variation is bigger than that (see `reference_windows_gate_timeout`: same tree, 21% apart). A PR's own contribution (PR #330 added ~16 tests to shard 3, a few seconds) is below that variation.

**How to apply:** when a PR is red on a shard, read the shard log for the pytest summary line and for `timed out after 30 minutes` BEFORE looking at tests; compare against the last master run of the same shard (`gh run view <id> --json jobs` gives start/completion times; `gh run view <id> --job <jobId> --log` gives the log, and `gh run view --log` collapses same-named jobs). Re-run the failed job once on the same SHA. A third shard timeout in a row on unrelated code means the fix is the capacity one, not the PR's: `--splits=4` plus the matrix, which also needs the owner to edit the master ruleset's required check names (`test suite 1/3...` are matched by exact name; see `reference_windows_gate_timeout`). Do not raise the 30.

Which shard a new test file lands on: `tools/suite-shard-pins.json` is keyed by split count then file; shard index 2 (CI "3/3") holds only 45 files (the heavy census-type ones), and `--pin-new` put the new file there because the model thought it the lightest.

**Runner speed, not code, decides it (measured later the same day, PR #330).** Shard 3 is BIMODAL: 18.9 / 19.9 / 20.0 min on a fast runner, 27-31 on a slow one, on the same files. The tell is the timeline of the FIRST 10% of tests, which are identical in every run: 2.9 min (master `84469fd`, passed in 20.0), 4.2 (base `4f4c47f`), 4.6-4.7 (PR #330 both runs) - and the ratio holds to 90% (16.6 vs 23-26 min), about 1.5x uniformly. So compare milestone minutes between runs (`[ NN%]` lines with timestamps in the job log, fetched with `gh api repos/OWNER/REPO/actions/jobs/<jobId>/logs --allow-escape-sequences`, which works while the run is open; `gh run view --log` refuses until the informational `linux` job's 45-min cap ends) before blaming a diff. A shard on a slow runner cannot fit in 30 min, whoever's PR it is; the same red hit shards 1 and 3 on different pushes of one PR.

**You cannot `gh run rerun --failed` while the run is open**, and the non-blocking `linux 1` job holds every run open for its 45-minute cap: the retry works once, after `startedAt + 45 min`.

**The fix is PR #333 (`claude/fourth-test-shard`, opened 2026-10-14): four shards.** It needs Alex to edit the master ruleset "Basic" (id 20312707; required checks read 2026-10-14: `gating benchmarks`, `test suite 1/3`, `2/3`, `3/3`) to `test suite 1/4`..`4/4`; after that every other open PR is BLOCKED on the `/4` names until it merges master in (#330 included). Method worth reusing: the weights (`tools/suite-durations.json`, 103 of 580 files had none) were rebuilt with `suite_shards.py --update=<combined junit>` from the run whose three shards had a SIMILAR runner speed (run 38544751527 at `4f4c47f`; artifacts `suite-timings-windows-<run_number>-<shard>`, one XML per shard, merge them into one `<testsuites>` file first), then `--count-qapp`, then `--repin --splits=4`; coverage was verified by collecting each shard separately and summing (19276). The cost model is a fit to that run, so the first CI run of the new layout is the real test of balance. Correction to the bimodality note above: the 18.9 and 19.9 minute shard-3 figures are from earlier, smaller suites; the clean same-era evidence is `84469fd` at 20.0 min against 27-31 on the others.

**DONE 2026-10-14/15: #333 squash-merged to master as `4bfedc25`; Alex edited the ruleset (saved 21:04 ET) so the required checks are `gating benchmarks` + `test suite 1/4`..`4/4`** (only `1/4` kept the GitHub Actions integration pin 15368; `2/4`-`4/4` read back as any source, optional to re-pin). #333's own first run on four shards: 18.9 / 19.4 / 19.6 / 13.3 min. The cost model over-predicted every shard (real pytest session 988 / 1093 / 1103 / 751 s against 1215 modelled) because the gc hook price is per-heap, about 0.6x the flat 0.4 s in the smaller 4-way processes; left alone on purpose, since one run is not enough to re-weigh (see the one-shot-model lesson). `mergeStateStatus` reads UNSTABLE, not CLEAN, when the informational `linux 1` job is CANCELLED at its cap; that is mergeable. Any open PR now needs master merged in to report `/4`, and any PR that adds a test file needs `tools/suite_shards.py --pin-new` against the 4-table. Also: `git show rev:path` is mangled by MSYS in this shell (it turns `a:b` into a path list); use `git grep -n PATTERN rev -- path`.

#### Index line before it was shortened (2026-10-18, MEMORY.md has a size limit)

- [Shard 3 timeout, 2026-10-14](project_shard3_timeout_2026_10_14.md) — 3/3 hit the 30-min step on master and two PRs; a capacity red, not a test; how to tell and what the fix needs

## project-handoff-2026-10-07-shards-and-naming-prs

*From the assistant's notes (`project_handoff_2026_10_07_shards_and_naming_prs.md`, type: n/a).*  
*State of play at 2026-10-07 ~03:30 UTC when Alex archived the sessions to start over: open PRs #239 and #242, the fork ports of #235 and #239 (DONE, fork #24), three-shard CI + ruleset facts, and what is deliberately NOT being done*

Written so nothing is lost when the sessions are archived (Alex's goal, 2026-10-07: "archive all these sessions and start over, without losing anything"). It is a dated snapshot: check `gh pr list` before trusting any line.

**master = `13ea375b`** (#235 squashed 2026-10-07 01:15 UTC; before it #241, #240, #238, #237, #232, #227). Everything below is verified against GitHub at ~03:20 UTC.

#### STATE AT 2026-10-07 ~13:45 UTC: NO PRs OPEN in xaerogonzo/OpenChem-Studio. #243 MERGED 13:23 UTC (`d758011c`, by auto-merge, all four required checks green; `linux 1` informational, failed at its 45-min limit as usual). The bullet below about #243 being open/armed is history. (Supersedes the Open list this section used to hold.)

- **#239 (P-45.2.3) MERGED** (`3d895b5d`); **#244 (VENDORING row for fork #24) MERGED 13:03 UTC** (`6219303b`, by Alex); **#242 (shard re-pin) CLOSED unmerged** with an explanatory comment (its slowest shard was no faster: job times 15m16 / 24m45 / 17m50 against 22m17 / 17m22 / 23m26 on #244's run, one run each; its docs claim something the run disproved; it conflicted with master). Its branch `claude/repin-three-shards` is still on origin. If a re-pin is wanted again, start from the timing artifacts of runs 37540165666 and 37555533718.
- **#243 (`openchem-cli`, branch `claude/openchem-agent-cli`) is the only open PR of this batch**, pushed `7bc76e70` by the session that finished it: master merged in (only the root `CHANGELOG.md` conflicted, newest-first, both entries kept), `tests/test_cli.py` pinned under table "3", and 15 constants in `src/openchem/cli/` given `#:` comments because `tests/test_constant_docs.py` failed on the branch itself (that guard was not among the ones its description said it ran; it would have failed the shards). Auto-merge (squash) is armed; CI was running (gating benchmarks passed, three shards pending); the monitor/auto-fix is OFF. If a shard fails with a green pytest summary and exit 1 that is the known teardown flake: `gh run rerun <run> --failed`. The session that built it ("Using project source code as Claude tools") still has the branch checked out in worktree `agent-cli` at the OLD tip `a38950a0`; do not resume it, archive it.

#### Owed, not started

- **CORRECTION 2026-10-07 (checked at ~11 UTC): the fork ports of #235 AND #239 are DONE, together.** Fork PR #24 (`naming-p45-2-3-and-stereo-parent-choice`, code commit `4f05db4`) was merged by Alex at 10:52 UTC as `a4fdedb`. Verified independently: the fork's `iupac_namer/` + `data/` equal app master `3d895b5d` in all 80 files under `fork_port.py`'s rewrite (no extras), the ported `test_namer_stereo_parent_choice.py` is identical to the app's (19 tests), and it plus the two sibling stereo files pass in the fork under the app interpreter (91 passed). The only open piece is **app PR #244 (`vendoring-row-235-239`, the VENDORING row, all required checks green, mergeable)**: it needs Alex's merge, I cannot merge it. Do not start another port; the text that used to be here said "owed, not started" and was stale within hours.
- D-193..D-196 and the rest of the list below are unchanged.
- D-193..D-196 (see `project_d191_d192_lambda_and_nuclide`).

#### Facts that took time to find

- CI is **three Windows shards** since #240: job names `test suite N/3` (the count is `strategy.job-total`). master has a **ruleset**, not classic branch protection (`branches/master/protection` 404s): "Basic", id 20312707, required checks `test suite 1/3`, `2/3`, `3/3`, `gating benchmarks`, matched by exact job name. **Edit it at `https://github.com/xaerogonzo/OpenChem-Studio/settings/rules/20312707`** (the `/rules/<id>` link the API returns is the read-only viewer). Any change to the shard count changes the job names and needs this edit, by Alex.
- Master run 743 (first on three shards): step times 1313 / 725 / 1055 s against the 1800 s limit; the four required jobs green; the run-level `cancelled` was only `linux 1` (informational) hitting its 45-minute limit.
- Raw timing data is re-downloadable: artifacts `suite-timings-windows-743-1..3` of run 37540165666 and `...-748-1..3` of run 37555533718 (`gh run download <run> -n <artifact>`). The analysis scripts lived in a session scratchpad and are gone; they were ~40 lines each: per-file reported time by shard from the JUnit, and the same file's time in run 743 vs 748 split into moved/unmoved.
- A required check cannot be satisfied by a job that no longer exists, and PRs whose last run predates #240 report `test suite 1/2`/`2/2`: they need a new push (merge master) to run the three-shard workflow.
- Worktree `amazing-grothendieck-ed467f` is clean and everything in it is pushed; its branches `claude/third-test-shard` (merged, #240) and `claude/repin-three-shards` (#242) exist on origin. Never delete remote branches; remove a stray worktree from the main checkout.

How this was learned: `reference_windows_gate_timeout`, `reference_ci_and_windows_crash_index`, `project_p14_4j_stereo_tiebreak`, `reference_naming_rounds_index`.

## project-suite-time-and-linux-closed

*From the assistant's notes (`project_suite_time_and_linux_closed.md`, type: n/a).*  
*MERGED #92/#93 (2026-09-12): 30% of the suite is one gc.collect() that nothing cheaper can replace, the suite is sharded, and the Linux crash chase is CLOSED by Alex's decision*

Master `5c21f2a`. Two PRs, both merged 2026-09-12.

#### #92 -- where the time goes, and why the policy did not change

One `gc.collect()` in `tests/conftest.py`'s `pytest_runtest_logfinish` is
**30% of the Windows suite's wall clock**. It was invisible because that hook
fires outside setup/call/teardown, which is all a JUnit case's `time` covers.
`tools/suite_timings.py` now splits the remainder into test time / hook / rest.

Re-measured arms (`OPENCHEM_COLLECT_POLICY`), 7865 tests:

    none    ~950 s   late 285-295   crashes 1/8
    qapp   ~1400 s   late 100       crashes 0/5   <- shipped, still right
    always  2999 s   late 100       crashes 0/2   (strictly dominated)
    gen0    ~890 s   late 100-110   crashes 1/6
    gen1       --        --         crashes 2/2

The docstring's old table (138 / 0 / 4) was wrong in every cell.

**Late destructions are NOT the discriminator** -- gen0 matches qapp's count
and still crashes. What tracked crashes was full gen-2 vs anything less
(0/7 vs 4/16). Small n; an observation.

**Per-collect cost is flat w.r.t. frequency (~215 ms)** -> it walks the live
heap -> collecting more often can never help. The cheaper walk (gen0/gen1) was
the only real candidate and it crashes. **Alex declined the n=10 gen0
experiment** (it would have ~6 h to confirm a candidate that already crashed,
with no decision hanging on it). Do not re-propose it without a new reason.

#### #93 -- shard the suite

The timeout is per job. `tools/suite_shards.py` partitions `tests/test_*.py`
FROM DISK (never a committed list -- a stale list silently drops new files);
`suite-durations.json` is only weights. Matrix of 2, `timeout-minutes: 30`,
`fail-fast: false`. First run: 17m05 / 13m08, coverage verified exact. Details
in `reference-windows-gate-timeout`.

#### The Linux decision

Alex, frustrated after a dozen-plus sessions: keep the job, **close the chase**.
Recorded in `docs/ARCHITECTURE.md` Known TODOs with a `DEFERRALS` row, and in
the crash annotation text. Reopen conditions and the depth distribution are in
`reference-linux-crash-is-one-file`.

**Why:** these are the decisions a future session is most likely to undo by
accident -- re-proposing gen0, "fixing" the imbalanced shards, or reopening the
Linux crash because a leg went red.

**How to apply:** a red Linux leg in a recorded depth mode is expected; read its
`leg.json` and move on. A tight shard budget means `--splits=3`, not a bigger
timeout. The crash class reproduces on WINDOWS in ~40 s under the gen0/gen1 arms
-- a far better handle than Linux, recorded in case Alex ever wants it solved,
but not a reason to start.

**Loose ends: none.** The 03:39 orphans from the crashed arm runs had already
exited by the time Alex asked to kill them. Both branches deleted 2026-09-12,
recorded with full SHAs in `docs/BRANCH_CLEANUP.md`'s "Later deletions" table
(`4aad1cb`) -- that table is where every future branch deletion goes.

## project-windows-crash-chase-2026-10

*From the assistant's notes (`project_windows_crash_chase_2026_10.md`, type: n/a).*  
*the 2026-10 Windows crash measurements: what was measured and ruled out, what is open, and that Alex stopped the chase on purpose*

The harness is `.github/workflows/windows-crash-rate.yml` (manual dispatch: `ranges`, `attempts`, `treatments`, opt-in minidumps,
`OPENCHEM_PYSIDE_VERSION`) with `tools/crash_rate.py`; every record, with its pre-registration, is in `benchmarks/windows_crash/`.

**Settled / measured**
- #197 (dispose fix) on shard 2, pre-registered n=15: 0/15 vs 2/15 without, p=0.483, INCONCLUSIVE.
- The early shard 1 crash (4-8% of the run, no frame outside pytest) lives in window `15:20` (files 15-19 of shard 1, ending in
  `test_calculator_inspector_structure.py`; about 12% of attempts, 33 of 280; 0/60 for that file alone).
- Native minidump (WER kept 1 of ~15): null READ in `shiboken6.abi3.dll`, `BindingManager::releaseWrapper`, same build as local PySide6 6.11.1.
- PySide6 6.9.3 crashed 1/100 in that window vs 8/100 locked (p=0.035), 6.10.0+ crash; BUT 6.9.3 crashed 8 of 8 whole-shard legs
  (locked 2 of 8), inside the app's own `eventFilter` first lines. A downgrade is NOT a fix.
- No effect: `--disable-gpu`, `--in-process-gpu`, `QT_OPENGL=software`, `AA_ShareOpenGLContexts` in the test qapp.
- Pre-registered `__del__` that destroys a dialog's web view first: 7/100 vs 15/100, p=0.112, wrong direction. Code left unmerged on the
  remote branch `eventfilter-hardening`.
- 3000-iteration local create-and-discard loop of that dialog: no crash. This crash does not reproduce on the dev machine.

**Open, none favoured by evidence:** stale non-QObject (`QStandardItem`) wrappers during dialog teardown; GC timing at the end of a test;
the Python `eventFilter` overrides. **Alex stopped the chase on purpose (2026-10-06)**: the suite is mostly green and the retry covers
the rest. Do not restart it without a new hypothesis, and pre-register (`feedback_heldout_experiment_discipline`).

## project-disposal-flush-experiment

*From the assistant's notes (`project_disposal_flush_experiment.md`, type: n/a).*  
*RESULT: the disposal flush is NOT the cause -- 13/20 vs 11/20, p=0.75 over 40 CI legs. The Linux victim spans FIVE files and the fixed-tree rate is 0.54*

**MERGED as PR #62, master `591cee3`, 2026-08-30.** Six commits off
`96e8c9c`. Scope was: correct the record, consolidate the recipe, build
the harness, run the A/B -- all four done, plus a CI timeout found by
accident along the way.

#### What was built

- **`tools/disposal_inventory.py`** -- walks every hand-written Qt
  disposal sequence under `tests/`, grouped by exact call sequence.
  Writes `benchmarks/disposal/inventory.{md,json}`; `--check` fails on
  drift. **The pre-consolidation state is `git show
  dba03eb:benchmarks/disposal/inventory.md`** -- 64 sequences, 8
  distinct, 46 files.
- **`tests/conftest.py::dispose()`** -- the ONE implementation, plus a
  `widgets` fixture. 58 of the 64 sites now call it; 64 -> 7 sequences.
- **`OPENCHEM_DISPOSE_FLUSH=0`** -- the experimental arm, env-gated in
  `conftest.flush_at_dispose`. Only the exact string `"0"` turns it off,
  so a typo runs the CONTROL.
- **`workflow_dispatch` + a replica matrix** on the `linux` job. Push and
  PR still run exactly one leg (`github.event.inputs` is null -> the
  `|| '[1]'` fallback).
- **`benchmarks/disposal/score.py`** -- `leg` (one Bernoulli trial) and
  `score` (the 2x2, Fisher exact, odds ratio, Wilson CIs), guarded by
  `tests/test_disposal_score.py`.
- **`benchmarks/disposal/README.md`** -- the preregistration.

#### THE RESULT: insufficient evidence, and it is not an underpowered null

Commit `1c8c71f`, 20 legs per arm, all 40 accounted for:

                    crashed  completed
      control            13          7      flush inside dispose()
      treatment          11          9      flush at end of test
      Fisher p = 0.7475        odds ratio 1.519

Powered for near-total elimination; 13 against 11 is NO effect. Both
frames-of-ours naming that flush, and the 8-of-8 `dispose_app_widgets`
prior, survived as a LEAD right up to being measured.

**It refutes the TIMING, not forced delivery as such** -- the treatment
still delivers the same `DeferredDelete`, just later. "Never force it"
is a different arm and is not runnable: it leaves the backlog
`flush_deferred_deletes` exists to prevent.

**THE VICTIM SPANS FIVE FILES.** 50 legs, 27 crashes, fixed-tree rate
**0.54**: `test_nmr_view_dialog.py` x23, then `test_screening_service.py`,
`test_panel_rail.py`, `test_main_window_conformers.py`,
`test_rotation_transaction.py`. `test_panel_rail.py` is the file whose
`_dispose` frame was the ORIGINAL n=1 lead, so its reappearance
corroborates nothing.

#### AND THE SAME MISTAKE WAS MADE AGAIN, ONE COMMIT AFTER CORRECTING IT

The pilot's 3-in-10 was used to amend the preregistration, concluding the
rate was 0.30 not 0.50. Wave 2's control is 13-in-20 on a tree with no
executable difference; p=0.12 between waves, overlapping intervals,
pooled 16/30 = **0.53**. The original assumption was fine and 0.30 was an
n=10 artefact. The amendment's ACTION (n=20) was right; its REASON was
not.

**Before concluding anything from a rate here, ask what n it rests on
and what the interval is.** Ten legs of a coin-flip process supports
almost nothing and looks exactly like data.

#### The four things that decide whether this is honest

1. **One commit, one env var -- NOT two branches.** This branch's own
   finding is that a byte-identical tree crashes differently run to run,
   so an A/B whose arms are different commits invites exactly the
   explanation it cannot rule out.
2. **The refactor is not a variable.** Both arms use the consolidated
   helper.
3. **A partial matrix is REFUSED, not averaged.** `score` requires the
   exact replica set and every leg to carry a pytest summary *or* a
   census trail. An arm that does not run is not an arm.
4. **"Insufficient evidence, change nothing" is an allowed outcome**, and
   at n=10 it is the EXPECTED one for a real-but-partial effect:
   5/10 vs 0/10 gives p=0.033, but 5/10 vs 1/10 gives p=0.14.

#### Three traps paid for while building it

- **`Census.usable` is not optional.** A bare `not finished` scores an
  unreadable trail as a CRASH -- manufacturing data rather than losing
  it. Three states: crashed / completed / could-not-tell.
- **`upload-artifact@v4` FAILS on a duplicate name.** Without
  `-${{ matrix.replica }}` every leg past the first errors and the
  experiment loses the evidence it exists to collect.
- **A population assertion pinned to a real function's shape rots.** The
  guard located `conftest.dispose` and broke the moment that function
  grew an `if` for the experiment. It tests the walker on CONSTRUCTED
  source now, with a near-miss control.

#### The guards caught themselves twice

`test_the_recipe_really_is_findable_...` failed on its FIRST run because
the offender guard was comparing rendered step strings against bare call
names -- vacuous. And the inventory walker mis-grouped one site because
an `import` sat between two steps. Both found by the checks, not review.

**Why:** the experiment's value is entirely in its discipline; run
without the refusals and the preregistration it would produce a number
nobody should believe.

**How to apply:** read `benchmarks/disposal/README.md` BEFORE dispatching
anything, and do not renegotiate the 0.05 threshold after seeing a
number. See `reference-linux-crash-is-one-file` and
`heldout-experiment-discipline`.

## reference-ci-and-windows-crash-index

*From the assistant's notes (`reference_ci_and_windows_crash_index.md`, type: n/a).*  
*CI, suite timing and the Windows/Linux crash work, including the 2026-10 crash-measurement harness, its null results and the shard pins*

Moved verbatim out of MEMORY.md on 2026-10-06 to keep the always-loaded index small. The newest entries are at the bottom.

- [Full suite needs background](reference_full_suite_needs_background.md) — ~25 min; run backgrounded in a short-path detached worktree so edits can continue, never edit what it reads mid-run
- [What the Linux job hides](reference_linux_crash_is_one_file.md) — CLOSED 2026-09-12, do not reopen on "it crashed again"; victim tracks depth, the annotation API drops ~1 in 4
- [Disposal-flush experiment](project_disposal_flush_experiment.md) — MERGED (#62): the flush is NOT the cause (p=0.75/40 legs); victim spans FIVE files, fixed-tree rate 0.54
- [Windows gate timeout](reference_windows_gate_timeout.md) — suite SHARDED at 30 min/job; next time it's tight, add a shard, don't raise the number
- [Suite time & Linux closed](project_suite_time_and_linux_closed.md) — 30% of suite is one gc.collect() nothing cheaper replaces; gen0 experiment declined; Linux chase closed
- [Windows shard crash & composition](reference_windows_shard_crash_and_composition.md) — shards crash in conftest.dispose with no FAILED lines; adding a test file re-balances the split so master's green history is not your shard's
- [vendor-tests.yml CI timeout](reference_ci_vendor_tests_timeout.md) — 40-min budget set for a 3209-test suite that grew to 5212 unnoticed (path-filtered workflow); bumped to 90 min
- [run_app_gate.sh --out collision](reference_run_app_gate_out_collision.md) — passing --out at the same path --sha derives makes the script's own rm -rf wipe the fresh worktree

#### Added 2026-10-06 (the crash-measurement session)

- [Windows crash chase, 2026-10](project_windows_crash_chase_2026_10.md) — what was measured, what was ruled out, what is open; the early shard 1 crash is a null read in shiboken's releaseWrapper, NOT identified further; stopped on purpose
- [GitHub Actions workflow traps](reference_actions_workflow_traps.md) — ' #' in a YAML scalar is a comment; artifact names take no ':'; `gh run view --log` collapses same-named jobs (use the REST job-log endpoint); dispatch from a SHA
- [Suite shard pins](reference_suite_shard_pins.md) — each test file is pinned to its shard so adding a file moves nothing; `suite_shards.py --pin-new` in the PR that adds a test file, `--repin` on its own

**Correction to the 2026-09-24 entry above (shard crash & composition):** the 're-balancing' problem it describes was fixed by the shard pins (#202, #214); the crash itself was NOT explained, see the chase note.

#### Index line before it was shortened (2026-10-18, MEMORY.md has a size limit)

- [CI, Windows crash & suite-run knowledge](reference_ci_and_windows_crash_index.md) — READ BEFORE re-chasing the early shard 1 crash; shard pins, timing, workflow traps

## reference-ci-vendor-tests-timeout

*From the assistant's notes (`reference_ci_vendor_tests_timeout.md`, type: n/a).*  
*vendor-tests.yml's 40-min CI timeout was set for a 3209-test suite; it grew to 5212 (+62.5%) with the timeout never recalibrated — bumped to 90 min, 2026-09-22*

`.github/workflows/vendor-tests.yml` (path-filtered, only runs when `src/openchem/vendor/**` changes) had `timeout-minutes: 40`, set when its own comment said "3209 passed... about 15 minutes." The suite had organically grown to 5212 tests (+62.5%, across rounds 7-8) with nobody re-touching the timeout, because the path filter meant it simply hadn't run against a vendor-touching PR in a while. First one to trigger it (naming round 9's fix-timeout PR) timed out at ~71% on TWO separate re-runs — steady, non-hanging progress each time (not the coronene-class hang, see `reference_...coronene` if it exists), confirmed by re-running with Java properly on PATH locally: full suite completes in ~26 min on Alex's machine, CI runs ~2.2x slower (~56-60 min extrapolated).

Fixed by bumping to 90 min and correcting the stale comment. Re-run after the fix: 43m37s, genuinely green.

**Lesson: a workflow with a path filter can silently go a long time without running, and a timeout budget calibrated once doesn't get revisited unless something actually triggers it.** If a vendor-touching PR ever times out again, check test count growth vs the workflow comment's baseline before assuming a code-level hang — read the failure's own progress dots (steady vs stalled) to distinguish "ran out of budget" from "the coronene-class per-row hang."

## reference-actions-workflow-traps

*From the assistant's notes (`reference_actions_workflow_traps.md`, type: n/a).*  
*GitHub Actions traps hit building the crash-measurement workflow: YAML comment in a name, colon in artifact names, same-named job logs, SHA dispatch*

- **An unquoted ` #` in a YAML scalar starts a comment**: `name: ${{ matrix.arm }} #${{ matrix.replica }}` silently dropped the replica,
  so three legs shared one job name. Quote it.
- **Artifact names cannot contain `:`** (an arm label like `files 0:28` made every upload fail). Use `${{ strategy.job-index }}`.
- **`gh run view --log` and `--job <id> --log` collapse jobs with the same name** and print one leg's log N times. Read each job through
  `gh api --allow-escape-sequences repos/OWNER/REPO/actions/jobs/<id>/logs` (the plain call refuses terminal escapes).
- Dispatch with `-f ref=<full SHA>`, not `master`: a push mid-run changes the tree under later legs. A dry-run of anything the legs apply to
  that exact commit (a `git revert`, an env override) is cheap; it caught a conflict that would have failed every leg.
- A push can fail with a transient `Internal Server Error`; retrying (three times, 15 s apart) worked every time.
- `gh pr merge` right after a push can answer `UNKNOWN` mergeability for a few seconds; wait and re-read before deciding there is a conflict.
- Reading a crash: faulthandler's INNERMOST Python frame being pytest's `pytest_pyfunc_call` means the crash was after the test body, while
  its locals were released; a `tests/` line as innermost means native code was running directly from that statement.

## reference-linux-crash-is-one-file

*From the assistant's notes (`reference_linux_crash_is_one_file.md`, type: n/a).*  
*SUPERSEDED TWICE: not one file, and the investigation is now CLOSED (2026-09-12). The victim tracks DEPTH, not a fragile test. Read leg.json, not the annotation -- the annotation API drops ~1 in 4 verdicts*

**2026-09-12: THE INVESTIGATION IS CLOSED. DO NOT REOPEN IT ON "IT CRASHED
AGAIN".** Alex's decision, after a dozen-plus sessions and no fix. Recorded
as a guarded DECISION in `docs/ARCHITECTURE.md` Known TODOs, and folded into
the crashed-leg annotation text itself. The job STAYS (it found real bugs);
the chase stops. Three reopen conditions only: the failure in the WINDOWS
suite under its shipped config; a real Linux APPLICATION failure; or the
depth distribution shifting downward. See `project-suite-time-and-linux-closed`.

**The current distribution (8 of 8 legs crashed), which condition 3 is
measured against:** modes at ~5% (`test_batch_panel.py`, seen twice),
~56% (`test_nmr_view_dialog.py`) and ~84% (`test_rotation_transaction.py`).
The victim file is a function of how FAR the leg got. A leg landing in any
of those three modes trips nothing. I first wrote the band as "56-84%" and
dropped the 5% mode, which would have caused a false reopen.

**THE NAME OF THIS MEMORY IS WRONG AND IS KEPT SO THE OLD CLAIM STAYS
FINDABLE.** It recorded six (later seven) census-named crashes all in
`tests/test_nmr_view_dialog.py` and concluded "the FILE is the constant".
That went into CLAUDE.md as PR #60. **Its own successor run refuted it
three commits later**, 2026-08-30.

    33298732951  4267fdc  master   test_nmr_view_dialog.py     57%  3683 tests
    33300040059  c6155fa  PR #61   test_nmr_view_dialog.py     57%  3683 tests
    33301056335  96e8c9c  master   test_screening_service.py   83%  5365 tests

**Ten census-named crashes, TWO files. 9 crashes in the last 18 runs.**

#### The counter-example is a BYTE-IDENTICAL TREE, which is why one pair beats nine observations

`git diff c6155fa 96e8c9c` is **empty** -- branch tip and merge commit of
PR #61. Two runs of one tree crashed in **different files, 26 percentage
points apart**. `git diff 0da570c 4267fdc` is empty too, and there one run
was CLEAN and the other crashed.

So on a fixed tree: crash-vs-clean is a coin flip, and when it crashes the
victim is not fixed. No count of same-file observations survives that.

**PR #61 changed `.gitignore` and deleted a tracked binary -- nothing
executable.** Second non-executable commit to "cause" a crash.

#### The mistake worth remembering

Nine samples of a 50/50 process showed a pattern, and the pattern was
written up as a law. CLAUDE.md had *just* finished warning that the
59%/63% figures were the same error one level up. See
`break-a-guard-before-believing-it` -- same family: a claim tightened
past what the data carries.

#### The platforms converge, for the first time

`tests/test_screening_service.py` is the canonical **Windows** victim,
recorded twice at 83% and 84%. Linux has now landed in it at 83%:

    Windows   :120 in _drain     processEvents()
    Linux     :269 in widgets    sendPostedEvents(w, DeferredDelete)

Both event pump/flush moments in one file. A datum, **not** a conclusion:
the signatures still differ (`Aborted` vs access violation) and one bug is
still not established.

#### THE LEAD: both frames of ours name our own disposal recipe

Across the whole Linux history exactly two frames belong to us --
`test_panel_rail.py:19` and `test_screening_service.py:269` -- and both are
`sendPostedEvents(widget, DeferredDelete)`. `late=0` in all ten, so
cross-test late destruction stays ruled out.

The prior that makes it worth testing: the reverted `dispose_app_widgets`
did the same thing automatically and crashed **8 of 8**. The 64
hand-written copies had never been A/B'd. That experiment is now built --
see `project-disposal-flush-experiment`.

**LEAD, not FINDING.** For a fatal signal a frame is still wherever the
process happened to be; what licenses the experiment is the recurrence
plus the prior, not either frame alone.

#### How to read a Linux verdict -- CORRECTED 2026-09-12

`gh run view --json` reports this job `success` no matter what. **And the
annotation recipe below is NOT reliable either**: 2 of 8 recent legs
returned `annotations_count=0` on runs that had crashed. Not delayed --
re-queried hours later, still zero -- and not unemitted: the `##[error]` is
in the job log. The API just doesn't return it. Reading by annotation gave
me "6 of 8 crashed, two clean"; by `leg.json` it was 8 of 8.

**Read `leg.json` from the artifact. That is the verdict:**

    gh run download RUN_ID --repo OWNER/REPO --name linux-suite-log-N-1 --dir legs
    cat legs/leg.json        # crashed, victim, tests_begun, late_during_run

The annotation recipe, now a convenience only:

    gh api repos/OWNER/REPO/commits/SHA/check-runs \
      --jq '.check_runs[] | select(.name|startswith("linux")) | .id'
    gh api repos/OWNER/REPO/check-runs/ID/annotations \
      --jq '.[] | select(.annotation_level=="failure") | .message'

Since PR #57 that message names the victim from `census.txt` itself, so no
artifact download is needed. With the matrix there are now N such
check-runs per run, so do not `head -1`.

#### The Open Babel half -- RESOLVED, and it was never a platform difference

The **Windows** wheel points `BABEL_DATADIR` at
`share/openbabel/<version>/` (one file, `splash.png`) while its data ships
in `bin/data/`; the **Linux** wheel puts all 55 where the variable points.
Linux was correct; Windows was blind, and expanded the issue-#8 fixture
cell only *because* it could not read `space-groups.txt`. PR #57 replaced
the bare assertion with a measured capability gate, and Linux reported
`6325 passed, 0 failed` for the first time. `BABEL_DATADIR` is deliberately
NOT repaired -- the receptor handed to Vina is byte-identical either way.

**Why:** this memory's own headline was believed for three commits and was
wrong. Anything citing "the victim is one file" is citing this, and needs
the correction.

**How to apply:** a fix attempt starts at the disposal flush, not at
`NmrViewDialog` and not at heap-layout roulette. See
`check-for-a-summary-line` and `measure-on-the-target-commit`.

## reference-windows-gate-timeout

*From the assistant's notes (`reference_windows_gate_timeout.md`, type: n/a).*  
*Windows CI timeout, three rounds: gates split into their own job (09-10), then the suite itself SHARDED into two jobs at 30 min each (PR #93, 09-12) after measuring that 30% of it is one gc.collect() nothing cheaper can replace*

**SOLVED. The three gates are their own `jobs.gates` in `tests.yml` now,
with no `needs: suite`.** Nothing in the suite job can skip them any more,
by failing or by timing out. The history below is why that was the fix
rather than a bigger number, and it went wrong twice in the same way.

#### Round one, 2026-08: `timeout-minutes: 30`, at the line

    1555 s   success        86% of budget
    1639 s   success        91%
    1678 s   success        93%
    1710 s   success        95%
    1838 s   CANCELLED     102%   <- run 33333432904

Raised to **45** in PR #62 (`6f5563a`), matching the `linux` job, with a
comment saying the day it was tight again the answer was to find what got
slower rather than raise it a second time.

#### Round two, 2026-09-10: tight again at 44m31 / 45

Run 34452130638 passed all sixteen steps at **99% of budget** -- suite step
33m24, the three benchmarks the other ten minutes.

**"WHAT GOT SLOWER" HAD NO ANSWER, AND THAT DECIDED THE FIX:**

    ae0094ad   suite step 1345 s   7172 collected
    fdf68292   suite step 1633 s   7172 collected   <- +21%, and
                                   `git diff` between them is EMPTY

Byte-identical trees, 288 seconds apart. So the margin was inside the
runner's own noise and the gate was at risk on ANY run, not on a bigger
one -- an argument about COUPLING, not about budget.

**I GOT THIS WRONG FIRST AND SAID SO.** Comparing one run of an old tree
against one run of a new one gave "the suite lost 30% of its throughput",
attributing the whole difference to the trees. The same-tree pair refuted
it. One run per tree supports nothing here.

#### Why splitting beats raising

Every earlier fix bought back one CAUSE of the skip -- deselecting the
network test stopped NCBI doing it, reading the step list stopped a reader
missing it -- and left the coupling, so the next unrelated cause did it
again. Twice that cause was the clock.

**NO `needs: suite`**, deliberately: a red suite skips a dependent job
exactly as it skipped a later step. Cost measured before it was paid: one
checkout and one `uv sync`, and `uv sync` is cached at **5 seconds**.

The suite kept 45 for two days -- ~34 minutes alone, 76% of budget.

#### Round three, 2026-09-12: SHARDED, and the budget went DOWN to 30

The looking the comment demanded was done first (PR #92, see
`project-suite-time-and-linux-closed`): 30% of the wall clock is one
`gc.collect()` per Qt test, and every cheaper collect policy measured worse.
So nothing got slower and no test could be made faster -- but **the timeout
is PER JOB**. PR #93 split the suite into a `shard: [1, 2]` matrix.

    first sharded run 34713707105:   shard 1  17m05   3960 tests  164 files
                                     shard 2  13m08   3917 tests  165 files
                                     overlap 0, 329 files == 329 on disk

**Tightened to 30, not kept at 45** -- a budget with no pressure is not a
gate. Next time it is tight, the move is `--splits=3` plus the matrix, NOT
a bigger number.

**The shards are imbalanced 17 vs 13 minutes, and that was predicted.**
`tools/suite-durations.json` weights per-test time only; the hook is 291 s
in shard 1 against 130 s in shard 2 on near-equal collect counts (944 vs
917), because per-collect cost tracks the LIVE heap and the heavy Qt files
landed together. If balance ever matters, weight by hook cost per file.

**Verify coverage, not the tick, after any change to the split.** A
splitter that drops a file leaves every shard green. Sum `tests=` across the
per-shard JUnit artifacts and count distinct files against `git ls-tree`.

#### Two things worth carrying

**`master` HAS A RULESET, NOT CLASSIC BRANCH PROTECTION** -- the 2026-09-12
note here said "not protected" because `branches/master/protection` returns
404; that endpoint cannot see rulesets. Read `rules/branches/master` and
`rulesets/<id>` instead. Ruleset "Basic" (id 20312707, last updated
2026-10-06 17:30 EDT) requires the status checks `test suite 1/2`,
`test suite 2/2` and `gating benchmarks`, **matched by exact job name**, and
the repo-admin role may bypass on a pull request. So renaming a job, or
changing the shard count (the name carries it), leaves the old required name
"Expected -- Waiting for status to be reported" forever: PR #240 (3 shards)
sat BLOCKED with every real check green. The ruleset has to change with the
shard count -- and that is the owner's to do, not mine. Resolved
2026-10-06: Alex edited the ruleset at `/settings/rules/20312707` (the
`/rules/<id>` link the API returns is the READ-ONLY viewer -- hand out the
`/settings/` one) to require `test suite 1/3`, `2/3`, `3/3` + `gating
benchmarks`; #240 went BLOCKED -> CLEAN and merged as 5041fcb6. The suite is
three shards from here on; any future change of the count repeats this.

**The price of a `gc.collect()` is PER SHARD, set by the MainWindows the process
holds** (`_retained_windows` in `tests/conftest.py`, published as
`openchem_retained_windows`). Master run 743 (first on 3 shards, 2026-10-06):
0.474 / 0.209 / 0.075 s per collect with 182 / 58 / 0 windows held; step times
1313 / 725 / 1055 s against a prediction of 1146 each from a flat 0.40.
PR #242 tried to fix that by moving 31 Qt-free files (289 s) from shard 1 to 2 on
the theory that a file with no qapp test "changes nobody's price". **The theory was
WRONG and the PR's own run (748) showed it:** step times 787 / 1446 / 1040 s against a
predicted ~1030 each; shard 2 became the slowest (worse than master's 1313). Windows
were identical (182 / 58 / 0) but the price moved (shard 1 0.474 -> 0.305, shard 2
0.209 -> 0.300) and the UNMOVED files in shard 2 reported +289 s (x1.6: a pure
file-reading test went 13.5 -> 26.7 s). Reported test time ITSELF carries GC cost that
scales with the live Python heap, and the moved files are namer/OPSIN-heavy, so they
inflate every later test in whatever process holds them. Same test, three heaps:
28.4 s (run 725 shard 1), 13.5 s (743 shard 2), 26.7 s (748 shard 2). So per-file
weights are NOT portable across layouts, and "Qt-free" is not "price-free". 2 runs of
the same unchanged shard-3 files agree to 0.5%, so this is not runner noise. Do not
re-pin by moving files on a one-shot model; a half-move (linear interpolation
between runs 743 and 748 says ~1066 s each) is a guess that costs a CI cycle.
Run-level `cancelled` on master that day was only the informational `linux 1`
hitting its 45-min job limit; the four required jobs were green.

**Check job-level conclusions before believing a run-level one.** Round
one surfaced as a `cancelled` run that read as a voided 20-leg experiment;
all 20 legs had succeeded and only the Windows job timed out.

**Why:** the failure mode is silence rather than noise, so it stays
invisible until somebody reads the step list on a run nobody had reason to
look at twice.

**How to apply:** see `check-for-a-summary-line` -- same family, one
level up: an absence of failure is not the presence of a result. And
before concluding a CI duration changed because the CODE changed, get a
second run of one tree.

#### Round four, 2026-10-06: THREE shards (PR #240)

After #232 the two shards ran 1737 s and 1769 s of the 1800 s step (97% of the pair; 91% before) and master timed out at 99%. They were balanced to 32 s, so moving files could not have fixed it: divide the sum by the capacity BEFORE re-pinning. Wall time per shard = reported test time + a full `gc.collect()` after each `qapp` test (outside reported time; 0.31-0.48 s each in the big shards, 0.058 s in an 11-file process: it walks the live heap) + ~30 s, to the second. `tools/suite_shards.py` `load_costs` weighs on that; `--count-qapp` regenerates the counts (2601 = the shards' `gc_calls` 1433 + 1168). A hook-blind 3-way table is at 2.0% spread, the old 2-way split was 7.2%, the committed one 0.09%: the guard tolerance is 1%.

## reference-windows-shard-crash-and-composition

*From the assistant's notes (`reference_windows_shard_crash_and_composition.md`, type: n/a).*  
*the Windows CI shards crash in conftest.dispose at ~77% (test_result_presentation), and adding a test file re-balances the split so master's green history is not your shard's*

**UPDATE 2026-10-05: the re-balancing trap below is FIXED by the shard pins (#202, #214; see reference_suite_shard_pins). The crash itself was measured at length and is NOT explained; see project_windows_crash_chase_2026_10.**

The Windows `test suite N/2` jobs can crash rather than fail: access
violation, **no FAILED lines**, so `--log-failed` and a grep for FAILED both
report nothing. Read the result as a pair — a summary line must exist AND
`grep -c "Windows fatal exception"` must be 0.

Observed 2026-09-17 on PR #129, and reproducible locally with that shard's
file list: the victim is in the Qt disposal path,
`conftest.dispose` ← `test_result_presentation.py::_dispose`, at 77%, with
the victim alternating between adjacent tests in that file. A **re-run of the
same SHA passed**, which is the project's own way of telling flake from
regression.

**The trap worth remembering: `tools/suite_shards.py` splits by committed
timings, so adding test files MOVES OTHER FILES between shards.** This branch
took shard 2 from 180 to 181 files and pulled
`test_calculator_inspector_structure.py` in from shard 1, plus a dozen other
shifts — so master's twelve consecutive green runs had never executed that
combination, and "master is green" was not the comparison it looked like.
Check with `suite_shards.py --splits=2 --group=N` on both trees and diff.

Two practical notes:
- The splitter prints paths with CRLF; `pytest` then reports
  `tests/test_abraham.py` not found and "no tests ran", which reads as a bad
  invocation. Pipe through `tr -d '\r'`.
- One leg per arm proves nothing here. The control leg of my own A/B failed a
  DIFFERENT WebEngine test (`test_the_3d_view_grabs_a_real_png`), and
  `project_disposal_flush_experiment` measured 13/20 vs 11/20 on a
  byte-identical tree (p=0.75).

**Measured again 2026-09-24 (branch `outcome-model`, gate on b3510161): three consecutive gate attempts of chunk s2c7 all died in
`test_result_presentation.py::_dispose` (exit 139) — read as "deterministic", it was luck.** Replaying that exact chunk with the gate's own
command on an idle machine: branch 2/10 crashes, a detached MASTER tree's equivalent chunk (files 151-175 of shard 2, contains the same file)
3/10, victims in the same file (plus one `test_screening_service`, the other known frame). Rate ~30%, so P(3 in a row) ~ 3-4% per gate: not
attributable to the branch. The gate script's 3-attempt retry is therefore thin for the one chunk that holds this file; if it bites again, run
that chunk's files by hand (`suite_shards.py --splits=2 --group=N | tr -d '\r'`, sed the 25 files) rather than re-running everything.

See `feedback_check_for_a_summary_line` and
`reference_windows_gate_timeout`.

## reference-suite-shard-pins

*From the assistant's notes (`reference_suite_shard_pins.md`, type: n/a).*  
*tools/suite-shard-pins.json pins each test file to its Windows shard so adding a file moves no other file; how to add and re-pin*

Plain timing bin-packing re-sorted everything on every added file (about 50 files changed shard), so each PR ran a shard combination
master had never run. Now `tools/suite-shard-pins.json` pins each file; an unpinned file is packed onto the lighter shard and moves no
pinned file, but unpinned files can move AMONG THEMSELVES, so a guard that asserts all files stay put is wrong (that was a real bug in my
first guard). In the PR that adds a test file run `python tools/suite_shards.py --pin-new --splits=2` (pins unpinned files where they sit,
moves nobody); `--repin` re-packs everything and belongs in a PR of its own. `--slice=a:b` prints a window of a shard (crash bisecting).

## reference-one-run-is-not-a-duration

*From the assistant's notes (`reference_one_run_is_not_a_duration.md`, type: n/a).*  
*Suite-duration comparisons here are noise-dominated: the same tree measured 28:04 and 34:30, so never attribute a slowdown from one run per side*

OpenChem Studio's suite is long enough that run-to-run variance swamps most
real changes. Measured 2026-09-11 on essentially one tree:

```
local, same branch      28:04  and  34:30      (6.5 min apart)
CI master, four runs    35:36  36:59  37:15  35:39
CI branch, two attempts 40:28  and  37:10      (same SHA)
CI timeout              45:00
```

I told Alex a change had "added 9 minutes" from one local run each side, on
trees from different sessions — and then found the branch's own attempts
straddled master's whole band. **The honest answer was that its cost was not
measurable at n=1.**

**Why:** a slowdown attribution is a measurement like any other, and this
repo already records the same lesson against the Windows gate timeout ("same
tree runs differ 21%, so one run per tree proves nothing about a duration
change"). It is easy to forget because a duration *looks* like a fact.

**How to apply:** before blaming a change for suite time, get several runs a
side, or compare against CI's own baseline on master. And check
`--durations`: the single largest cost here is a pre-existing
`test_regulatory_rulesets.py::test_the_build_check_passes_on_the_shipped_sources`
at ~282 s, larger than most branches contribute in total. Related:
`reference_windows_gate_timeout`, `feedback_answer_review_questions_with_measurements`.

## reference-measure-test-counts-on-a-clean-tree

*From the assistant's notes (`reference_measure_test_counts_on_a_clean_tree.md`, type: n/a).*  
*Test counts measured in Alex's main checkout are inflated by his in-progress work; collect against a clean worktree before quoting a number*

Alex's main checkout at `D:\Random Projects\OpenChem Studio` almost always
carries uncommitted work-in-progress, including whole new test files. A
`pytest -q` count taken there is NOT the count a clean checkout of the branch
produces, and CLAUDE.md documents the clean number.

Measured 2026-08-05: main checkout collected 1527, the committed tree 1492
(= the `1490 passed, 2 skipped` CLAUDE.md already stated). The 35-test gap was
his unfinished `test_structure_annotation.py` (29) plus additions to
`test_visualization.py` (6). I reported "1525, up from 1490 — worth updating
the doc" and was wrong; the doc was already correct.

To measure the committed tree without disturbing his working tree, run the
collect from the clean git worktree under `.claude/worktrees/` using the main
venv's interpreter directly (the worktree has no `.venv` of its own):

    cd <worktree>
    "D:/Random Projects/OpenChem Studio/.venv/Scripts/python.exe" -m pytest -q --collect-only

**Why:** quoting a dirty-tree number turns into a wrong edit to a committed
doc, and that doc's test count has already drifted twice.

**How to apply:** before claiming a suite size or proposing a CLAUDE.md count
update, check `git status` first; if the tree is dirty, measure elsewhere or
say which number you measured. Related: `reference-tokensave-in-worktrees`,
`feedback-check-state-before-expensive-work`.

## reference-full-suite-needs-background

*From the assistant's notes (`reference_full_suite_needs_background.md`, type: n/a).*  
*OpenChem's full suite (6-19 min) exceeds the Bash tool's 10-minute cap, so it must be run with run_in_background*

The OpenChem full suite takes **6-19 minutes**, and the Bash tool's
`timeout` maxes out at **600000 ms (10 minutes)** — a larger value is
silently clamped, so the run is killed mid-way with exit 143 and ~10
minutes are wasted. Run it with `run_in_background: true` and wait for
the completion notification instead.

```bash
uv run --no-sync python -u -m pytest -q > /path/suite.log 2>&1
```

Two consequences worth pairing with it:

- **Nothing the suite reads may be edited while it runs** — `src/`,
  `tests/`, CLAUDE.md and `docs/` (the source-scanning guards `ast.parse`
  the tree and `test_docs_are_current.py` reads markdown). If a fix turns
  up mid-run, STOP the run, fix, and restart; a run concurrent with an
  edit is not a measurement. Verify afterwards with
  `find src tests -name "*.py" -newermt "@<start-epoch>"`.
- **Read the result as a PAIR**: a summary line must EXIST
  (`grep -E "[0-9]+ passed"`) and `grep -c "Windows fatal exception"`
  must be 0. A crashed run has no FAILED lines and can exit 0.

**Duration has grown: 23-25 min for ~8100 tests (2026-09-13).**

**To keep editing while it runs, run it in a detached worktree at the commit.** `git worktree add --detach <dir> <sha>`, `uv sync --extra ai --extra network --extra openbabel` there (the worktree has no .venv), then the suite; re-point with `git checkout --detach <newsha>` for the next commit, reusing the venv. This is what makes "never edit what the suite reads" compatible with continuing work. Two costs: put it on a SHORT path — under the session scratchpad `git worktree remove` failed with "Filename too long" (it still de-registered, leaving files behind) — and an order-dependent Windows teardown segfault showed once at `test_batch_panel` (exit 139, no summary line); a same-SHA re-run passed 8111, so treat one crash as a sample, not a verdict.

See `measure_test_counts_on_a_clean_tree` and
`feedback_measure_on_the_target_commit` for the counting discipline
that goes with it.

## reference-waiting-for-background-jobs

*From the assistant's notes (`reference_waiting_for_background_jobs.md`, type: n/a).*  
*How to wait on a long real-ORCA drive or full suite without flooding the session -- foreground until-loop, ONE Monitor at most, 600 s foreground cap*

Learned 2026-10-16 while driving real ORCA and a full local suite.

- A foreground `sleep N` of ~50 s or more is blocked by the harness, but `until grep -q "^exit=" file; do sleep 3; done; tail file` in a foreground Bash call (set `timeout` up to 600000) works and returns the moment the job ends.
- A foreground command still running at 600 s is moved to the background; start anything longer with `run_in_background: true`, write its output to a file in the scratchpad, and wait with the until-loop above.
- **Arm at most one Monitor per job.** Every stream-end produces its own system notification; eight overlapping monitors on one drive produced eight identical notices.
- A job that mutates source for a control run (`control_drive.py` in the session scratchpad pattern: save bytes, mutate, run, restore in `finally`) means NOTHING else may import or test the tree while it runs; wait for it first.
- A full local suite the way CI splits it: `python tools/suite_shards.py --splits=4 --group=N | tr -d '\r'` (the tool prints CRLF; without the `tr` pytest reports "file not found: tests/x.py" and exits 4 with nothing run), `JAVA_HOME` and PATH set from `reference-vendored-suite-needs-jre-on-path`, and `--deselect` the network test named in `tests.yml`.
- **Parallel shards from one cwd collide on py2opsin_temp_input.txt**: two shards at once gave 340 `test_namer_*` failures (FileNotFoundError py2opsin_temp_input.txt); the 25 files passed serially (3008 passed). Group failures by file first; if every one is test_namer_*, rerun just those files in ONE process.
- A shard-parallel run also races on py2opsin_temp_input.txt in files NOT named test_namer* (tests/test_round26_polyol_esters.py failed once with PermissionError on it, 154 passed alone): hold out every test that imports py2opsin/OPSIN, not just test_namer*.

#### Index line before it was shortened (2026-10-18, MEMORY.md has a size limit)

- [Waiting on background jobs](reference_waiting_for_background_jobs.md) — foreground until-loop (not sleep N), ONE Monitor max, 600 s foreground cap, `tr -d CR` on the shard file list

## reference-run-tests-with-python-m-pytest

*From the assistant's notes (`reference_run_tests_with_python_m_pytest.md`, type: n/a).*  
*ten OpenChem test files import tests.conftest; `uv run pytest <file>` cannot import it and `python -m pytest` can, so a targeted run of them reads as a harness artifact while testing nothing*

Ten files under `tests/` do `from tests.conftest import dispose`
(`test_property_panel_reader`, `test_fact_help`, `test_property_panel`,
`test_fact_view_charts`, `test_line_chart_widget`, `test_mutagenicity_alerts`,
`test_property_panel_long_values`, `test_property_panel_status_chips`,
`test_qt_object_disposal`, and `conftest` itself). That import needs the REPO
ROOT on `sys.path`:

```bash
uv run --no-sync pytest tests/test_property_panel_reader.py      # ModuleNotFoundError: No module named 'tests'
uv run --no-sync python -m pytest tests/test_property_panel_reader.py   # runs
```

`python -m pytest` inserts the current directory; the `pytest` console script
does not. The full suite works either way because collecting the package
puts the root on the path.

**Measured cost, 2026-09-17:** every targeted run of that file during the
naming-round-2 branch ended in `ModuleNotFoundError`, which read as a known
partial-run artifact rather than as "this file is not being tested". It held
a real regression from renaming an alert id, and the full suite and CI both
found it afterwards — CI shard 2, one test, after 14 minutes.

So: **use `python -m pytest` for any targeted run**, and treat a collection
error in a file as an unrun file rather than as noise. See
`feedback_front_load_verification` for the wider version of the same
mistake and `feedback_check_for_a_summary_line` for reading a run's result
as a pair.

## reference-vendored-suite-needs-jre-on-path

*From the assistant's notes (`reference_vendored_suite_needs_jre_on_path.md`, type: n/a).*  
*tests/vendor needs the JRE on PATH *and* JAVA_HOME set -- PATH alone silently SKIPS the OPSIN round-trip tests, which is worse than the failure it prevents*

`tests/vendor/iupac_namer` and `benchmarks/naming` call OPSIN through
py2opsin, which shells out to a **bare `java`** and therefore only sees a
runtime on PATH. The app's own code wraps that (`naming_providers._java_on_path`
prepends `openchem.services.java_setup.java_home()`), but pytest does not —
so a plain `uv run pytest tests/vendor` fails ~200 tests with
`FileNotFoundError: [WinError 2]` from `subprocess.CreateProcess`, which looks
exactly like a broken engine. Measured 2026-09-17: a run started that way was
killed at 4% and restarted.

```bash
JRE="/d/Random Programs/OpenChemStudio_Data/jre/jdk-21.0.12+8-jre/bin"
PATH="$JRE:$PATH" uv run --no-sync python -u -m pytest tests/vendor -q
```

**AND PATH ALONE IS NOT ENOUGH: SET `JAVA_HOME` TOO.** Several vendored test
files gate their OPSIN round-trip tests on
`skipif(not JAVA_HOME or not valid)`, so a run with only PATH set reports
them as PASSED-with-skips rather than running them. Measured 2026-09-20
(naming round 5): every vendored run of the whole round was made that way,
16 tests in `test_tautomer_alignment.py` never ran, and CI -- which sets
JAVA_HOME -- failed the round-5 PR on 6 perimidine expectations that N3's
indicated-hydrogen tier had made stale two weeks of work earlier. A skip is
quieter than a failure and cost more.

```bash
export JAVA_HOME="/d/Random Programs/OpenChemStudio_Data/jre/jdk-21.0.12+8-jre"
export PATH="$JAVA_HOME/bin:$PATH"
```

Check the summary line for `skipped` and ask what was skipped before calling
a vendored run green.

The same applies to the standalone fork's suite and to anything that runs
`score.py` outside the app. The path comes from `java_home()`, not a guess —
ask it rather than hard-coding if the install moves.

See `reference_full_suite_needs_background` for the worktree discipline the
long runs use, and `reference_no_jq_on_this_machine` for the other
environment trap of this shape.

**Same-line export trap (2026-09-20):** `export JAVA_HOME=... PATH="$JAVA_HOME/bin:$PATH"` on ONE line expands the OLD (empty) JAVA_HOME, so java never reaches PATH and OPSIN-dependent tests fail like a code regression. Use two separate `export`s (or the literal path in both).

**IT IS NOT ONLY `tests/vendor` (2026-10-14).** A plain full `uv run python -m pytest` in the MAIN suite fails 92 tests in 11 files (`tests/test_namer_numbering.py`, `test_namer_parent_citation_locants.py`, `test_namer_stereo_*`, `test_namer_known_defects.py`, `test_namer_multiple_bonds_parent.py`, `test_namer_round42/44*`, `test_namer_benzo_bridged_heteroatoms.py`, `test_retained_registry_contract.py`) when `java` is not on PATH; the same 11 files give 2096 passed / 15 xfailed with the JRE below on PATH (7m37). I reported a 62-minute local full run as "92 failed" before checking, so the first thing to do with a naming-only failure list from a local run is `which java`. Start any local full run with the two exports below.

**POSIX paths only in Git Bash (2026-09-24):** `export JAVA_HOME="C:/Users/..."` then `PATH="$JAVA_HOME/bin:$PATH"` puts a Windows-style entry on a POSIX PATH, so `command -v java` fails and `tools/run_app_gate.sh` exits with "no `java` on PATH" — and, launched with `&`, the wrapper reported the task "completed" while the gate had never started. Use `/c/Users/pmpd/.jdks/jbr-17.0.14` or the app's own `/d/Random Programs/OpenChemStudio_Data/jre/...`, and check `command -v java` in the same command.

#### Index line before it was shortened (2026-10-18, MEMORY.md has a size limit)

- [Vendored suite needs the JRE on PATH](reference_vendored_suite_needs_jre_on_path.md) — without `java` ~200 tests fail like a regression; ALSO 92 in the MAIN suite's namer tests (a local full run needs the exports)

## reference-run-app-gate-out-collision

*From the assistant's notes (`reference_run_app_gate_out_collision.md`, type: n/a).*  
*tools/run_app_gate.sh --out colliding with the --sha-derived worktree path makes the script's own rm -rf wipe the fresh worktree*

`tools/run_app_gate.sh --sha <sha>` auto-derives the detached worktree path as
`<drive>:/_scratch/<repo-name>-<short-sha>` (Git Bash spelling: `/d/_scratch/...`). `--out` is meant to be a
SEPARATE results directory (defaults to `$TREE/.gate-out`, a subfolder of the worktree) — but if `--out` is
passed pointing at the SAME path the script already derived for the worktree itself, the script's own
`rm -rf "$OUT"; mkdir -p "$OUT"` step (meant to clear stale results before writing new ones) wipes the
freshly-`git worktree add`-ed checkout before any test runs, leaving only the 2 files the script itself had
already written (`head.txt`, `which.txt`).

Measured 2026-09-23 (naming round 11): `--sha 26e0a41c --out D:/_scratch/OpenChem-Studio-26e0a41c` (same
path `--sha` alone would have derived) silently deleted the worktree's `src/`, leaving the preflight import
check failing with "the interpreter imports openchem from somewhere other than $TREE" — which reads like an
editable-install PYTHONPATH bug, not a self-inflicted deletion, and cost real diagnosis time chasing the
wrong theory (checked `.pth` file contents, `sys.path` ordering, meta_path finders) before noticing the
worktree directory itself was nearly empty.

**Fix: never pass `--out` when using `--sha`** — let it default. Recovery when it happens: the worktree
registration is now broken (`.git` file inside points to a non-existent gitdir), so a plain `git worktree
remove` fails; `git worktree prune -v` from the MAIN checkout clears the stale registration, then delete the
leftover empty directory by hand and re-run without `--out`.

No real work was at risk either time this bit — a detached worktree for a gate run holds only a disposable
checkout, never uncommitted changes.

## reference-dipole-test-signed-zero-flake

*From the assistant's notes (`reference_dipole_test_signed_zero_flake.md`, type: n/a).*  
*tests/test_dipole_typed.py failed shard 3 intermittently on unrelated PRs (benzene | eem and | qeq): the fixture recorded the SIGN of 1e-15 D noise; fixed in PR #374 (cf773a4b) by ignoring the sign of a number that prints as zero*

2026-10-18: `tests/test_dipole_typed.py::test_no_line_label_unit_arrow_or_cell_text_moved[eem]` and `[qeq]` ("what a person sees moved for: ['benzene | eem']") failed in shard 3 of PR #371 (naming round 68, run 39112117662) and of PR #374 (Fukui, run 39122836638), and passed on the same code in other runs (probes #372 master, #373 round 68; both closed). Not a crash, not related to either PR.

**Cause (measured):** benzene's dipole is floating-point noise (raw components 1.6e-15, 5.3e-16, -7.5e-17 D), so the `+0.00` / `-0.00` in the fixture is the sign of noise from one machine's summation order; Open Babel's EEM/QEq linear solve flips it on another CPU. Flipping every zero's sign in the fixture reproduces the failure locally.

**Fix:** PR #374 commit cf773a4b: `unsigned_zeros` in the test strips the sign from any number that prints as zero (regex `(?<![\w.])[+-]?(0\.0+)(?!\d)`), a real change still fails, and the assertion now prints a field-by-field DETAIL. The calculator still prints "-0.00" for a noise-negative component (cosmetic, a product change for its own PR). If #371 or another branch still fails that test it needs master/#374 merged in.

**General lesson:** a golden fixture of formatted numbers is fragile wherever a value is a symmetry-forced zero; and "re-run it" is not a diagnosis - a two-branch coincidence plus two probe PRs showed it was intermittent, and the raw values showed why.

## reference-merging-prs-and-required-checks

*From the assistant's notes (`reference_merging_prs_and_required_checks.md`, type: n/a).*  
*How a PR actually gets merged here: gh-api merge is blocked by the auto-mode classifier, auto-merge needs the ruleset, a path-filtered workflow cannot be a required check, and how to rebase a stack onto a squash-merged base without force*

Learned 2026-10-06/07 getting #235 merged. The three-shard and ruleset facts are in `project_handoff_2026_10_07_shards_and_naming_prs`; this is what that note does not say.

- **I cannot merge by `gh api .../pulls/N/merge`.** The auto-mode classifier denied it as "Merge Without Review" even with Alex's "merge it" and all checks pending-or-green; do not retry it another way. What worked: Alex put the required checks in the ruleset, then `mcp__ccd_pr__set_auto_merge` (squash) succeeded and GitHub merged on green. `set_auto_merge` fails with "Protected branch rules not configured" until the ruleset requires checks; "Allow auto-merge" was already on.
- **2026-10-18 update:** `mcp__ccd_pr__set_auto_merge` was DENIED for #374 (CI pending, no reason given; Alex merged it himself), but `gh pr merge 376 --repo xaerogonzo/OpenChem-Studio --squash` (no `--delete-branch`) was ALLOWED once Alex said "merge 376 if green" and I had read the checks myself (`gh pr view --json statusCheckRollup`: four shards + gating benchmarks SUCCESS, the non-blocking linux job CANCELLED, mergeStateStatus UNSTABLE only because of that, `headRefOid` equal to the commit I pushed). So the pattern that works: his explicit go AFTER CI is green, a direct squash merge, branch kept. Do not enable auto-merge on pending CI.
- **Required checks are matched by exact job name, and a workflow with a path filter must never be required.** `vendor-tests.yml` only runs when a PR touches `src/openchem/vendor/**`, `tests/vendor/**` or itself, so `vendored IUPAC namer suite` would hang every other PR on "Expected". `tests.yml` has no filter and no `if:`. The vendored suite is therefore NOT enforced: for a vendor-touching PR, read it by hand before it auto-merges (it took 52 min).
- **A PR whose last run predates a shard-count change sits `BLOCKED` with every check green**, because it reports `test suite 1/2` and the ruleset wants `1/3`. It needs a new push (merge master); and a new test file needs `suite_shards.py --pin-new --splits=3` as well, because `suite-shard-pins.json` is one table per shard count.
- **A green pytest summary then exit 1 on `test suite N/M`** is the known Windows teardown crash; the classifier step says "not a crash" so nothing retries. Re-run the failed job on the same SHA (`gh run rerun <run> --failed`) after reading the summary line; the re-run passed here.
- **Rebasing a stack onto a base that was squash-merged, without force:** `git merge origin/master` conflicts in every hunk the base PR added and the stack then edited (and again on any CHANGELOG/LESSONS tail that another PR also appended). Instead apply only your own delta to master's tree and record a merge commit with that tree on top of the pushed branch: `git diff --binary <base-tip> <my-tip> > d.patch`, `git checkout -b tmp origin/master`, `git apply --3way --index d.patch`, `TREE=$(git write-tree)`, back on the branch `git commit-tree "$TREE" -p HEAD -p origin/master -m ...`, `git merge --ff-only`. The PR diff is then exactly the delta. Use the app's `sync_with_base_branch` for the ordinary case; it left the merge in progress with only the doc-append files conflicting, which resolve by keeping both entries.
- **The simpler form of that recipe (used 2026-10-18 for #376 after #374 was squash-merged):** if the PR head had already merged master, the squash commit's tree equals the PR head's tree (`git rev-parse c65e2d73^{tree}` vs `04e4c508^{tree}`). Then `git merge-tree --write-tree --merge-base=<base PR final head> origin/master <branch>` just returns the branch's own tree (exit 0, no conflicts); `git commit-tree <tree> -p <branch> -p origin/master -F msg` plus `git merge --ff-only <commit>` gives a branch whose merge-base with master is master's tip. Check it: `git diff --shortstat origin/master HEAD` is only your own files, `git diff origin/master HEAD -- src/openchem/vendor` is empty, and the hashes your docs cite still pass `git merge-base --is-ancestor`. No `git apply`, no conflicts, history kept; PowerShell: don't put `$?` inside `( ; )`, use `$LASTEXITCODE`.
- **A PATCH of a PR that sends a null (or empty) body blanks its description.** If the text to send did not load, stop rather than PATCH. Send the body as stdin JSON (`--input -`, never `-f body=`, which URL-encodes markdown), and read the PR back with `gh pr view N --json body` before and after.
- Every naming PR appends to the tail of `src/openchem/vendor/CHANGELOG.md` and `docs/LESSONS.md`, so two open PRs conflict there each time one lands: expect it and keep both entries, the one that merged first on top.

## reference-branch-and-scratch-cleanup-rule

*From the assistant's notes (`reference_branch_and_scratch_cleanup_rule.md`, type: n/a).*  
*What is safe to delete after a naming round: local branches with a MERGED PR whose tip is on a remote branch, merged fork branches, merged-round scratch dirs; what to keep and report*

Done 2026-10-13 before round 50. **Delete** a local `claude/*` branch only if (a) its PR is MERGED and (b) `git branch -r --contains <tip>` finds a remote branch (squash merges leave the local tip != master, so `branch -d` refuses; the remote-contains check is the real safety). Use `-D`. **Keep and report**: a branch with no PR and no remote (unpushed work: calculator-organization-ux-32c9fe), CLOSED PRs, a MERGED branch whose remote was auto-deleted (suite-roadmap-ai-ideas-ecebb7: two pre-squash commits exist nowhere else), and any branch checked out in a worktree that another session owns.

**Worktrees:** `git worktree remove` without --force refuses a dirty one; before forcing, prove every added line already exists on master (`git diff | grep '^+[^+]'` against `git show origin/master:file` with `grep -vxFf`). `git worktree prune` only drops records whose folder is gone. Never touch another session's worktree (finish-agent-cli, calculator-result-selection, frosty-jang were left).

**Remote branches are never deleted** (project baseline). **Fork clone** (D:\_scratch\open-iupac-namer-r31): `checkout main`, `fetch --prune`, `merge --ff-only`, then `git branch --merged main` + `-d`. **Scratch:** the naming-round dirs r31-r45 were removed (about 1.2 GB, regenerable, all merged); kept r46-r49 because memory points at scripts there, and the unrelated nmr-timing / orca_track4 / pdfread / perf-census dirs which are not naming work. Pairs with `feedback_worktree_cleanup_stalls`.

**2026-10-22 pass (Alex asked for "merged branches and work trees").** Script logic that worked: classify each local branch from `gh pr list --state all --json headRefName,state,headRefOid` plus `git branch -r --contains <tip>`; delete only PR MERGED + remote contains the tip + not checked out in a surviving worktree. 56 branches deleted, 30 left (3 merged ones kept by this rule: regulatory-false-positives-62173c, suite-roadmap-ai-ideas-ecebb7, qc-panel-run-history; eight stale `7001b999` session stubs with no PR, which hold nothing unique; unpushed work in changelog-conflict-tool and calculator-organization-ux; the open PR #429 branch). `gh` lists no running sessions (`list_sessions` isRunning false for all), so idle-session worktrees with a merged branch and a clean tree were removed. **`git worktree remove` deletes the files and deregisters, but on 5 of 6 left an EMPTY folder that `rmdir` refuses ("Device or resource busy")**: something (probably an idle session's tokensave server or shell) holds it as cwd. Leave those folders for Alex to delete; they are inert. A worktree whose record says `prunable` is dropped by `git worktree prune`. A detached HEAD (`git switch --detach`) is what lets a session delete the branch it stood on.

**2026-10-23 second pass (Alex: "clean up the local branches and work trees now").** Other sessions had REUSED old worktree folders for new branches (changelog-conflict-tool-d0fa1c, goofy-robinson-d1f250, keen-wilson-49f405 now held live work with open PRs), so a folder name says nothing: re-read `git worktree list --porcelain` right before acting and judge by the branch checked out NOW. The delete script (PR MERGED + a remote branch contains the tip + not checked out anywhere) removed 16 more local branches; 34 remain, all kept for a stated reason. `ExitWorktree` is a no-op for a worktree the app created (it only handles ones this session made with EnterWorktree), and a session cannot remove the folder it stands in: that one is left for Alex to delete after the session ends. Three empty leftover folders from the first pass stayed busy across a restart (calculator-result-selection-ff3f27, regulatory-classifier-lesson-1c71c8, vigorous-gagarin-369689); two others went with a plain rmdir.

**2026-10-29 pass (Alex: "delete the merged branches, local and remote", then "remove the finished work trees").** Two things differ from the rules above, so read them before
repeating it. (1) **Remote deletion was asked for in so many words**, which is the only reason the 328 remote branches went: the baseline rule (never delete a remote branch) holds
unless the user says otherwise for that act. (2) **After a squash merge neither `git branch --merged` nor `git cherry` is reliable**, and the "remote contains the tip" test above
only proves the commits exist somewhere. The test that worked: a branch is finished when its tip SHA equals the `headRefOid` of a MERGED PR (`gh pr list --state merged --limit 1000
--json number,headRefName,headRefOid`) and no OPEN PR has it as head or base. A branch with commits AFTER its merged PR's head (4 such remote branches) or with no merged PR at all
(9) is not deleted; report both lists. Local-only commits are the real risk: one commit existed on no remote, so it was pushed to a new remote branch first and only then was
anything touching it removed. Clean worktrees reported as "unmerged commits" meant "commits not on a remote", not "uncommitted changes"; say which, because the first wording alarmed
the maintainer. Result: 328 remote and 6 local branches and 9 finished worktrees gone, 7 worktrees kept for a stated reason (open PR, live session, or undecided).

## project-conformer-descriptor-race-stack

*From the assistant's notes (`project_conformer_descriptor_race_stack.md`, type: n/a).*  
*#334 MERGED (restore path, one owner per shape id); #336 (in-flight drawing run, _GeometryClaims) retargeted to master, CI running, merge is Alex's call*

Two descriptor-service PRs, 2026-10-15. #334 (squash-merged by Alex as d3c046b4) gives each shape-descriptor id ONE owner when a drawing request sees a conformer and tops up a complete restore (`request_missing_geometric_descriptors`). #336 (`claude/descriptor-inflight-run`, retargeted from #334's branch to master) adds `_GeometryClaims`, so a GEOMETRY dispatch takes the ids from a drawing run already running; it is open on merge commit 92361079 with CI re-running.

**Why:** the in-flight race is real but narrow: a warm drawing run is ~10 ms (cold first run ~2 s, which did not lose it), so only a conformer landing within ~10 ms or a slow plugin provider loses. My first notes called it "about one second" without measuring and had to be corrected on both PRs.

**How to apply:** #336 is not merged and I was not asked to merge it; when its four shards are green it is Alex's call (or `set_auto_merge` squash if he asks). The retarget used the no-force recipe in `reference-merging-prs-and-required-checks` (master's tree plus only the PR's delta as a merge commit): the tree came out byte-identical to the one already tested, so nothing needed re-running. See also `feedback-check-stack-base-before-merging`.

#### Index line before it was shortened (2026-10-18, MEMORY.md has a size limit)

- [Conformer descriptor race stack](project_conformer_descriptor_race_stack.md) — #334 MERGED; #336 (in-flight race, claims) retargeted to master, CI running, merge is Alex's call
