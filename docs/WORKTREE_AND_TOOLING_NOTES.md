# Worktree, tooling and GUI-driving notes

Working in git worktrees on Windows, the code-graph tool's blind spots, driving and measuring the real Qt/Ketcher application without the mouse, and the traps found in guards, probes and sweeps.

These sections were moved here on 2026-10-29 from the assistant's private memory, so they are readable, searchable and versioned with the code. The text is kept as it was written (headings demoted one level, memory links written as plain names); dates and PR numbers are those of the time. Treat a measurement as true of the commit it was made on, and check a file or function named here still exists before relying on it.

## Contents

- [reference-removing-a-worktree-on-windows](#reference-removing-a-worktree-on-windows) — `git worktree remove` fails on Windows here — the tokensave db holds a lock, and the session's own cwd pins the bare directory
- [reference-worktree-isolation-guard](#reference-worktree-isolation-guard) — A worktree-bound session cannot Edit files in, or run `git -C` against, another worktree; the way to work in a second worktree is EnterWorktree(path), not a shell workaround
- [reference-two-sessions-can-share-a-worktree](#reference-two-sessions-can-share-a-worktree) — Another Claude session can be merging and running tests INSIDE your worktree; a conflict event may describe a merge you did not start. How to tell, back it up, and coordinate before aborting anything
- [reference-worktree-reuse-and-squash-stack-artifact](#reference-worktree-reuse-and-squash-stack-artifact) — A session's branch can show a huge \"Create PR\" diff after its stacked PRs were squash-merged; how to prove it is an artifact, and that the app reuses worktree folders under new branches
- [reference-task-items-on-an-unmerged-branch](#reference-task-items-on-an-unmerged-branch) — A fresh worktree starts at master, but the Known TODOs entry / DEFERRALS row a task names can exist only on an unmerged sibling program branch; grep `git log --all` for the quoted text first
- [reference-tokensave-in-worktrees](#reference-tokensave-in-worktrees) — tokensave silently serves the MAIN checkout's code when run inside a git worktree; fix is `tokensave init` in the worktree BEFORE the session starts
- [reference-tokensave-blind-spots-here](#reference-tokensave-blind-spots-here) — The vendored engine was excluded from the index until 2026-09-19 (vendor exclude, now removed); and three of tokensave's twelve health tools return numbers that do not describe this codebase — the measured causes are committed at benchmarks/code_health/audit_093105a.json
- [reference-no-jq-on-this-machine](#reference-no-jq-on-this-machine) — jq is not on PATH here, so any gh|jq watch or script is silently empty; use gh's built-in --jq
- [reference-pgrep-wrapper-on-this-machine](#reference-pgrep-wrapper-on-this-machine) — pgrep does not exist in Git Bash here; ~/.local/bin/pgrep is a PowerShell-backed wrapper (2026-09-20) whose -f mode hides its own ancestors, because every tool call is bash -c '<whole line>'
- [reference-gitbash-pythonpath-separator](#reference-gitbash-pythonpath-separator) — In Git Bash on Windows a PYTHONPATH of two Windows paths needs `;` — a `:` splits the drive letter, and the import silently resolves to the editable install instead
- [reference-bash-tool-heredoc-quoting](#reference-bash-tool-heredoc-quoting) — Python patch scripts with backslashes or adjacent quotes get mangled inside Bash-tool heredocs; write the script with the Write tool and run it instead
- [reference-driving-the-gui-on-windows](#reference-driving-the-gui-on-windows) — How to drive OpenChem Studio's GUI on Alex's machine without input landing in his other windows
- [reference-driven-window-activation-steals-keys](#reference-driven-window-activation-steals-keys) — A drive step that opens a window with text fields must not ACTIVATE it; the person's keystrokes land in it. Found 2026-10-15 as the cause of the one unexplained score_dialog.json failure
- [reference-qt-gui-and-driving-index](#reference-qt-gui-and-driving-index) — driving and measuring the real app, and the Qt/Ketcher traps found doing it
- [reference-qt-dialog-default-button](#reference-qt-dialog-default-button) — A QDialog shown with no default makes the first auto-default QPushButton in its focus chain the default; Enter passed on by a list or spin box presses it if visible
- [reference-qt-runjavascript-primitives-only](#reference-qt-runjavascript-primitives-only) — QWebEnginePage.runJavaScript on this Qt build returns primitives only — arrays and objects arrive as '', which looks like the page failing
- [reference-qt-svg-ignores-dominant-baseline](#reference-qt-svg-ignores-dominant-baseline) — Qt's SVG renderer silently drops dominant-baseline AND dy — only x/y move a glyph, so text centred for a browser draws half an em high in a QSvgWidget
- [qfiledialog-is-patchable](#qfiledialog-is-patchable) — QFileDialog's static methods ARE monkeypatchable under PySide6, unlike QMenu.exec
- [reference-ketcher-hover-and-keys-from-automation](#reference-ketcher-hover-and-keys-from-automation) — A Ketcher hover CAN be set from automation via editor.hover(editor.findItem(...)); the key goes inside the editor's DOM; and a number over a bond is NOT native in the vendored bundle
- [reference-molstar-shows-assembly-one](#reference-molstar-shows-assembly-one) — Mol* loadStructureFromData builds biological assembly 1, not the deposited file — and the option that looks like the fix is ignored
- [reference-probes-need-pytest-for-settings](#reference-probes-need-pytest-for-settings) — An ad-hoc script that builds a Settings object writes to Alex's real registry — the isolation is a pytest fixture, so probes must run through pytest
- [probe-sidecars-with-configured-paths](#probe-sidecars-with-configured-paths) — Passing None as an interpreter path makes every optional sidecar report \"not installed\" on a machine where it is working
- [reference-registry-pollution-disables-plugins](#reference-registry-pollution-disables-plugins) — A leaked plugins/project_directory in the real registry silently turns off every plugin; how to read and check it without writing
- [reference-guard-lessons-index](#reference-guard-lessons-index) — lessons about writing and trusting repo guards: mutate before believing, existence vs correctness, one-file vs tree, matching own prose, shipped vs reachable
- [reference-docsweep-what-to-check](#reference-docsweep-what-to-check) — How a docsweep goes here — most claims are now guarded, so the finds are dated measurements reading as live claims
- [reference-sweep-every-calculator-report-line](#reference-sweep-every-calculator-report-line) — benchmarks/report_lines/sweep.py — run it before changing either string parser (report_adapter or result_reduction); it overruled an obviously-correct fix once
- [reference-perf-census-measurement-traps](#reference-perf-census-measurement-traps) — Traps hit while building the resource census — each produced a plausible wrong number before it was caught
- [project-perf-census](#project-perf-census) — Resource census of the running app (PR #252, merged 2026-10-08) — what it found, what was fixed, the ranked open items, and where the raw data is

## reference-removing-a-worktree-on-windows

*From the assistant's notes (`reference_removing_a_worktree_on_windows.md`, type: n/a).*  
*`git worktree remove` fails on Windows here — the tokensave db holds a lock, and the session's own cwd pins the bare directory*

`git worktree remove` on this machine fails with `Invalid argument` and
**leaves a half-done state: git deregisters the worktree and deletes its
`.git` marker, but the files stay.** After that `git worktree list` shows only
master, so the leftover directory is inert junk rather than a worktree.

Two separate locks, in this order:

1. **`.tokensave/tokensave.db`**, held open by the tokensave server started as
   a bare `tokensave.exe serve` (no `-p`). That is the instance that resolves
   its root by searching *upward*, so it binds to the worktree's index — see
   `reference-tokensave-in-worktrees`. Servers launched as
   `serve -p "<main checkout>"` are rooted elsewhere and are NOT the holder,
   which is what makes the bare one identifiable. `Stop-Process` on it clears
   this.

   **THERE CAN BE SEVERAL BARE ONES — one per concurrent session — and only
   one holds THIS worktree.** Measured 2026-08-12: four servers, two bare
   (started 6 minutes apart), and stopping just the newer freed the lock.
   Killing bare servers as a class would have taken out the one serving
   `adoring-germain-a86974`, a LIVE registered worktree belonging to another
   session. `handle.exe` is not installed here, so the cheap discriminator is
   to stop ONE and retry the delete, rather than to guess or to kill all.

   **Test the lock without deleting anything**, so "is it still held" and
   "did stopping that server help" are answerable without a destructive
   retry:

   `[System.IO.File]::Open('<worktree>\.tokensave\tokensave.db','Open','ReadWrite','None')`

   throws when held and returns a handle to close when free. Confirmed
   2026-08-12 on `adoring-germain-a86974`: LOCKED, with three servers
   running. It does not say WHICH process holds it -- it replaces the
   delete-and-see step, not the stop-one-and-retry loop.
2. **The bare directory itself**, `Device or resource busy` — the harness
   resets the shell's cwd into the worktree after *every* command, so a
   process always has it as its working directory and it cannot be deleted
   from inside the session. `cd` away in the same command does not help.

**BOTH LOCKS ARE CONDITIONAL, AND A WORKTREE FROM AN ENDED SESSION HAS
NEITHER.** Measured 2026-08-14, cleaning up after the gallery-overlay
merge: `git worktree remove .claude/worktrees/pensive-napier-19b09d`
**succeeded outright** — no `Invalid argument`, no residue — and the
leftover empty `adoring-germain-a86974` from an earlier session went with
a plain `rmdir` from inside the session, which the note above says cannot
be done. Neither claim is wrong; both are narrower than they read:

- lock 1 needs a **live** bare `tokensave.exe serve` bound to *that*
  worktree. A session that has ended has no such server, so the db is
  free.
- lock 2 needs the shell's cwd to be **inside** that worktree. Running
  from the main checkout, it never is.

So the failure mode is specific to removing a worktree **the current or a
concurrent session is still using**. Try the plain `git worktree remove`
first; only if it errors is the stop-one-server-and-retry loop needed.

**How to apply:** if removal does fail, delete the contents (all children,
then `.tokensave` once its server is stopped) and accept that the empty
directory survives until the session ends — that is the normal outcome for
a live worktree, not a failure, and is why old `.claude/worktrees/*`
directories sit around empty and deregistered. Verify success with
`git worktree list` plus `git worktree prune -v`, not with whether the
directory exists.

**2026-10-06, `strange-mahavira-17f2fa` (a live session's worktree, with a `.venv`):**
`git worktree remove` failed `Invalid argument`, deregistered it, and deleted NOTHING
(11,616 files left). `.venv\Lib\site-packages\PySide6\qml\...\.qt\rcc\...` paths run 240-250+
characters, so the cause is probably MAX_PATH (not proven: the tokensave db was never tested,
and `.tokensave` went with everything else). What worked: a `.ps1` script file (quoting the
`\\?\` path inline from bash failed silently: `Test-Path` said "already gone" while the folder
existed) calling `[System.IO.Directory]::Delete('\\?\<path>', $true)`, with a guard that refuses
if a `.git` entry still exists. It took the tree from 11,616 files to 79.

**A third lock: an ORPHANED worker from a run I had killed.** The last 79 files (numpy/rdkit
`.pyd`/`.dll`) were `Access denied`. Matching processes by command line found nothing; matching
by loaded module did: `foreach ($p in Get-Process) { try { $p.Modules | ? FileName -like '*<wt>*' } catch {} }`
found one idle `multiprocessing.spawn` python (parent already exited, 0 MB working set) left by
`naming_ref_compare.py` / the census scan after I `Stop-Process`ed their launchers. Its
`ExecutablePath` is the uv base interpreter, not the venv, so an executable-path filter misses it.
Check its parent pid against the processes you killed before stopping it. Then the delete finished
and only the empty directory (pinned by the session's own cwd) remained, as above.

Confirm the tracked work is merged first (`git log master..<branch>` empty),
since everything in the worktree is then either in master or regenerable
(`.venv`, `.pytest_cache`, `node_modules`).

#### Index line before it was shortened (2026-10-18, MEMORY.md has a size limit)

- [Removing a worktree on Windows](reference_removing_a_worktree_on_windows.md) — half-fails only for a worktree a live session holds; from the main checkout a plain remove works

## reference-worktree-isolation-guard

*From the assistant's notes (`reference_worktree_isolation_guard.md`, type: n/a).*  
*A worktree-bound session cannot Edit files in, or run `git -C` against, another worktree; the way to work in a second worktree is EnterWorktree(path), not a shell workaround*

Seen 2026-10-07 finishing #243 from a session bound to a different worktree. The guard is NOT in Alex's `~/.claude/settings.json` (its only PreToolUse hook is tokensave's, matching `Agent|Grep|Bash|Glob`) or the project's `.claude`; it appears to be built into the desktop app's worktree sessions.

- **`Edit` into another worktree is refused** ("This session is running in an isolated git worktree ... Do not write to other worktrees' files"). **Bash `git -C <other worktree>` is refused**, and so is a `gh` command inside a loop or construct it cannot prove is not git (split it into plain separate commands). Shell commands that merely `cd` into another worktree and write files are NOT stopped: it is a tripwire, not a sandbox, so treat its intent as the rule.
- **The sanctioned route:** `git worktree add` the second worktree, run `uv sync` and `tokensave init` in it (CLAUDE.md), then `EnterWorktree` with `path`. After a switch the previous worktree is no longer writable from that session.
- **Consequence:** a session cannot inspect another session's worktree (`git status` there is blocked), so before archiving sessions it cannot confirm they hold no uncommitted work; Alex checks in each, or from a terminal. `ListAgents` shows which peer sessions are idle.
- A branch checked out in an idle session's worktree cannot be checked out again: push your work with `git push origin HEAD:<remote branch>` (fast-forward), and say that session's local branch is now behind so it is archived rather than resumed.

Related: `reference_two_sessions_can_share_a_worktree`, `reference_merging_prs_and_required_checks`.

## reference-two-sessions-can-share-a-worktree

*From the assistant's notes (`reference_two_sessions_can_share_a_worktree.md`, type: n/a).*  
*Another Claude session can be merging and running tests INSIDE your worktree; a conflict event may describe a merge you did not start. How to tell, back it up, and coordinate before aborting anything*

Measured 2026-10-06 on PR #239 (P-45.2.3). The app's auto-fix event said a merge was "in progress in your worktree (the app's earlier host-side merge of origin/master, or one you started)". It was neither: `MERGE_HEAD` was 2fd6583c, the tip of another session's branch (the #235 work), fully resolved to the index and uncommitted, and a pytest plus `naming_ref_compare.py` were running from MY worktree's venv. The other session (named "Fix wrong molecules...", later renamed "Merge 235 into 239" for the same user) had been asked to integrate the two PRs and used my worktree to do it.

**How it showed, in order of cheapness:**
- `cat <gitdir>/worktrees/<name>/MERGE_HEAD` against `git rev-parse origin/master`: they differed.
- File mtimes (`stat -c '%y'`) of engine.py and a test file were hours AFTER my last reflog entry (`git reflog --date=iso`), so someone edited while I was idle.
- A test failed with `PermissionError ... py2opsin_temp_input.txt`: two OPSIN callers in one cwd (`reference-py2opsin-cwd-collision`).
- Process ancestry: walk each suspicious python/pytest up its parents (`Get-CimInstance Win32_Process`) to the `claude.exe`; compare with your own shell's chain. Mine was a `--resume=<my session id>` process; the foreign runs hung off a different one.
- `ListAgents` names the peers and which are busy; a foreground test run makes a session "busy".

**What worked:** save the staged state before touching it (`git write-tree`, then `git commit-tree <tree> -p HEAD -p MERGE_HEAD` and `git update-ref refs/backup/<name> <commit>`, local only, so the other session's resolution survives); abort with the app's `sync_with_base_branch abort:true`; redo the merge with the same tool (master, not the sibling's branch, so the PR does not drag in a branch master already has squashed); reuse the sibling's resolution of the code files; `SendMessage` the peer saying what you found, what you did, and that its results from the transient window are suspect, and `notify_when_idle` so you do not poll. It replied within minutes, confirmed, credited its fix, and stopped using the worktree.

**How to apply:** before resolving a conflict event, run `git status`, compare `MERGE_HEAD` with `origin/master`, and look at mtimes against the reflog. If anything is not yours, back it up and ask the owner before aborting; never commit someone else's staged merge unreviewed. Run your own OPSIN tests from a separate cwd (`cd <scratch>; PYTHONPATH=<worktree> python -m pytest <abs paths> --rootdir=<worktree> -c <worktree>/pyproject.toml`).

**2026-10-15 addendum:** the DESKTOP APP also starts merges in my worktree (Auto-fix's 'host-side merge' of master into whatever branch is checked out), so a conflict event can arrive with a merge already in progress on a DIFFERENT PR's branch (`git status` showed UU + MERGE_HEAD on typed-polarizability while the event named #345). `git checkout -B x origin/x | tail -1 && git merge ...` HID the failed checkout (pipe exit status = tail's) and then tried to merge into the wrong branch. Check `git branch --show-current` and MERGE_HEAD first; finish the in-progress merge (it is a PR I own that also conflicts), push, then check out the event's branch.

## reference-worktree-reuse-and-squash-stack-artifact

*From the assistant's notes (`reference_worktree_reuse_and_squash_stack_artifact.md`, type: n/a).*  
*A session's branch can show a huge \"Create PR\" diff after its stacked PRs were squash-merged; how to prove it is an artifact, and that the app reuses worktree folders under new branches*

Measured 2026-10-12: the app showed `claude/calculator-organization-ux-32c9fe  +15,401 -1,149  Create PR` after its stack was squash-merged as five PRs (#278-#282). The commit SHAs on the branch match nothing on master, so `git cherry` marks them all `+` and a merge-tree against master is polluted by conflict markers. **The test that works:** for every file the branch changed, take the lines it added (`git diff -U0 <merge-base> <branch>`) and check each is present in master's version of that file. Result: 12,424 of 12,451 present; the 27 missing were wording deliberately superseded later. No file existed only on the branch. A new PR from it would duplicate merged work.

**The folder is not the branch:** the app reuses a worktree folder for a new session under a new branch (the archived "Calculator result selection UX" session had folder `calculator-result-selection-ff3f27`; this long session later lived in the same folder on `claude/calculator-organization-ux-32c9fe`, the original branch having been deleted). `list_sessions` excludes the CURRENT session, so a worktree that matches no listed session may be your own. Do not remove it while the session is open.

**Cleanup limits for me:** the isolation guard refuses `git -C` and any git against another worktree, so I cannot inspect it for uncommitted changes or remove it; `ExitWorktree` only handles worktrees `EnterWorktree` made; `clean_up_worktrees` is age-based (30/60/90 days idle); `discard_kept_worktree` only for archived sessions that kept a dirty worktree. A branch checked out in a worktree cannot be deleted until that worktree is gone or detached (`git switch --detach origin/master` then `git branch -D`). Project rule: never delete a remote branch; give Alex the `git push origin --delete` command instead. See `reference_removing_a_worktree_on_windows`, `feedback_worktree_cleanup_stalls`, `reference_merging_prs_and_required_checks`.

#### Index line before it was shortened (2026-10-18, MEMORY.md has a size limit)

- [Worktree reuse and the squash-stack artifact](reference_worktree_reuse_and_squash_stack_artifact.md) — a huge Create PR diff after squash-merged stacks is an artifact

## reference-task-items-on-an-unmerged-branch

*From the assistant's notes (`reference_task_items_on_an_unmerged_branch.md`, type: n/a).*  
*A fresh worktree starts at master, but the Known TODOs entry / DEFERRALS row a task names can exist only on an unmerged sibling program branch; grep `git log --all` for the quoted text first*

On 2026-09-14 the task quoted a Known TODOs entry and a `DEFERRALS` row verbatim, and **neither existed in the worktree I was given** (branch at master `e4d4f77`). They had been added an hour earlier on `close-the-96-open-items` (`c79dd46`), an unmerged branch another session was driving, and that branch had also edited the very files the fix touched (`collapsible_section.py`, `fact_view.py`).

Found with `git grep -n "<quoted phrase>" <branch>` and `git log --all -S"<phrase>"`, after a plain grep returned nothing. A worktree with no unique commits can be fast-forwarded onto that branch losslessly (`git merge --ff-only <sha>`), which is what was done; the work was committed on the worktree's own branch, never on the other session's.

**How to apply:** when a task cites doc text, a test, or a tracked item that grep cannot find, check the other branches before concluding it is gone or misquoted. Also check `git worktree list` and running `pytest` processes: that branch's full suite was running in a detached worktree (`D:/ocsA`) at the time, which must not be touched. Related: `feedback-measure-on-the-target-commit`, `reference-tokensave-in-worktrees`, project_wrapped_row_height_fix (pruned 2026-10-06).

## reference-tokensave-in-worktrees

*From the assistant's notes (`reference_tokensave_in_worktrees.md`, type: n/a).*  
*tokensave silently serves the MAIN checkout's code when run inside a git worktree; fix is `tokensave init` in the worktree BEFORE the session starts*

**A tokensave-enabled session started in a git worktree reads the wrong tree.** Confirmed 2026-08-04 doing the `external_tools_dialog` refactor (PR #9) in `.claude/worktrees/recursing-moore-34307e`: every `tokensave_*` MCP call returned the MAIN checkout's code, and `tokensave_search` for a class I had just written returned `[]`.

**Mechanism.** The MCP server is registered globally with no `--root`:
`D:/Claude Co worker/Token Save/tokensave.exe serve`. It searches upward from its cwd for a `.tokensave/` directory. A worktree under `.claude/worktrees/` sits *inside* the main repo folder and has no `.tokensave/` of its own, so the search walks up and finds the main repo's index. `tokensave list` from the worktree confirms it: one project, the main repo.

It does emit a `worktree_mismatch` warning on every call — **that warning is not cosmetic, it means the answers are about different code.** Never ignore it.

**Fix — run in the worktree before starting the session:**

```bash
"D:/Claude Co worker/Token Save/tokensave.exe" init
```

Measured: **2 seconds**, 343 files, 8038 nodes. `git status` stays clean afterwards. Use `sync --force` to rebuild, since `init` refuses when an index already exists and prints a "use sync" hint instead — I once measured a stale index for several minutes because of that.

**Caveat that cost me the most time: initialising mid-session does NOT rebind the MCP tools.** The server process resolved its root at startup, so `tokensave_*` MCP calls kept hitting the old index even after a local `.tokensave/` existed. Until the session restarts, query the new index through the CLI instead:

```bash
"D:/Claude Co worker/Token Save/tokensave.exe" tool health --path src/openchem
"D:/Claude Co worker/Token Save/tokensave.exe" tool search SomeClass
```

**`tokensave branch` does not solve this.** It tracks branches within one checkout ("copies nearest ancestor DB + incremental sync"), and syncs from that checkout's files — it cannot see a different directory's working tree.

The binary is not on PATH; call it by full path. Related: project_codebase_health_baseline (pruned 2026-10-06).

#### Index line before it was shortened (2026-10-18, MEMORY.md has a size limit)

- [tokensave in worktrees](reference_tokensave_in_worktrees.md) — in a worktree tokensave silently serves the MAIN checkout; `init` there first; mid-session init won't rebind the MCP tools

## reference-tokensave-blind-spots-here

*From the assistant's notes (`reference_tokensave_blind_spots_here.md`, type: n/a).*  
*The vendored engine was excluded from the index until 2026-09-19 (vendor exclude, now removed); and three of tokensave's twelve health tools return numbers that do not describe this codebase — the measured causes are committed at benchmarks/code_health/audit_093105a.json*

Before drawing any conclusion from a tokensave health/structure tool on
this repo, read `benchmarks/code_health/audit_093105a.json`. It records the
raw figures beside the analyzer's **measured** blind spots, so the
calibration does not have to be re-derived.

The three that cannot be read as-is (tokensave 7.11.0):

- **`hotspots` and `coupling(fan_in)`** fold unrelated symbols together.
  A call to an unqualified common name binds to whichever project symbol
  shares it, so `rank_power.py::append` reports **fan_in 1509** — that is
  `list.append`. All nine "hotspots" are accessors named `text`, `values`,
  `a`, `n`. `coupling(fan_out)` is unaffected and usable.
- **`circular` and `imports`** report one cycle spanning ~350 files, which
  would need `src/` to import from `tests/`. Cause: `import urllib.request`
  resolving to `services/spatial_overlay_service.py`. **So the `acyclicity`
  sub-score is not a measurement of this codebase** and the headline
  `quality_signal` understates.
- **`unsafe_patterns` searches Rust** (`unwrap`, `panic!`, `unsafe {}`).
  On Python it returns 0, meaning *not applicable*, never *clean*.

`dead_code` needs reading, not acting on: eight false-positive classes are
recorded with an example each, five of them **not** on the tool's own
documented caveat list. `unused_imports` came out clean under the same
scrutiny, and the artifact records the control that establishes it.

`equality` (gini over per-file complexity) is the one bad sub-score that is
real.

Related: `feedback-break-a-guard-before-believing-it` — same instinct,
pointed at the analyzer instead of at a test.

**A fourth, and the biggest: the vendored engine was not indexed at all
until 2026-09-19.** `.tokensave/config.json` carried the default exclude
`**/vendor/**` (meant for third-party dependency folders), which hid
`src/openchem/vendor/` -- the naming engine every naming round edits -- and
`tests/vendor/`. Symptom: `tokensave_search PrefixEntry` returned only an app
file, and `tokensave_context` answered "no candidates". Alex approved
removing the pattern (backup `.tokensave/config.json.backup.1789805287659`);
`sync --force` indexed it and the MCP tools saw it with NO restart. If a
vendored symbol goes missing again, check that exclude list first.

## reference-no-jq-on-this-machine

*From the assistant's notes (`reference_no_jq_on_this_machine.md`, type: n/a).*  
*jq is not on PATH here, so any gh|jq watch or script is silently empty; use gh's built-in --jq*

`jq` is **not installed** on Alex's machine (`which jq` → nothing, and it is
absent from a very long PATH). Any pipeline of the shape
`gh ... --json ... | jq -r '...'` produces an **empty string, not an error the
caller notices** — so a settlement loop built on it compares two empties, is
never true, and runs to its timeout in total silence.

Measured 2026-09-09: a 60-minute watch on PR #81's checks emitted nothing
while both checks had already passed 40 minutes earlier.

**Use `gh`'s own `--jq` flag**, which is built into the binary and cannot be
missing wherever `gh` itself works:

```bash
gh run view RUN_ID --json jobs --jq '.jobs[] | "\(.name): \(.conclusion)"'
```

Better still for a settlement test, `gh pr checks N` prints plain rows and
needs no JSON at all.

Same family as `feedback_check_for_a_summary_line` — an absence of output is
not an absence of events. Before arming a watch, ask what it prints if the
thing it watches has *already* happened; if the answer is "nothing", it cannot
tell that from "not yet".

## reference-pgrep-wrapper-on-this-machine

*From the assistant's notes (`reference_pgrep_wrapper_on_this_machine.md`, type: n/a).*  
*pgrep does not exist in Git Bash here; ~/.local/bin/pgrep is a PowerShell-backed wrapper (2026-09-20) whose -f mode hides its own ancestors, because every tool call is bash -c '<whole line>'*

Git for Windows ships no procps, so `pgrep` was "command not found". A wait loop written as
`until ! pgrep -f X ...` therefore exited at once (`! <missing command>` is true) and a background task reported
"completed" while a 22-minute suite was still running. Fixed for good on 2026-09-20 at Alex's request:
`C:\Users\pmpd\.local\bin\pgrep` (already on PATH), flags `-f -l -a -x -c`, exit 0/1/2 like the real one, PIDs are WINDOWS pids.

**Why the ancestor exclusion exists:** each Bash-tool call runs as `bash -c "<the whole command>"`, so with `-f` the calling shell's own
command line contains the pattern and matches itself; the first version made `pgrep -f zzz-no-such-thing` succeed forever. MSYS `exec` also
detaches a script's Win32 parent link, so the chain is collected from `/proc/$$` (winpid) in bash and the Windows walk continues from each.
Ancestors are hidden ONLY for `-f`; by name (`pgrep -x explorer.exe`) only pgrep itself is excluded, like the real one.

**How to apply:** use it in wait loops. Still check the loop can end: a wrapper that can't find a command makes `!`-loops exit instantly. The
other reliable route without it is `tasklist //FI "PID eq N"`. Related: `reference-no-jq-on-this-machine`.

## reference-gitbash-pythonpath-separator

*From the assistant's notes (`reference_gitbash_pythonpath_separator.md`, type: n/a).*  
*In Git Bash on Windows a PYTHONPATH of two Windows paths needs `;` — a `:` splits the drive letter, and the import silently resolves to the editable install instead*

Measured 2026-10-06 (P-45.2.3), while running the engine from a scratch copy to compare it with the worktree.

`PYTHONPATH="D:/x/src:D:/x" python -c "import openchem; print(openchem.__file__)"` printed the WORKTREE's path, not `D:/x/src`: the colon cut `D:` into `D` and `/x/src`, neither a directory, so the venv's editable install won with no error. A single path (`PYTHONPATH="D:/_scratch/copy/src"`) works, and so does `"$A/src;$A"` with a semicolon. This is the same silent-wrong-tree shape as the tokensave-in-a-worktree trap (`reference-tokensave-in-worktrees`): a run that imports the wrong tree reads as a result.

**How to apply:** use `;` between Windows paths in PYTHONPATH, and print `openchem.__file__` (or the engine's) at the top of any script that is meant to run a particular tree, as `stability.py` and `p452_measure.py` did. The PATH variable in Git Bash is the opposite: it wants POSIX `/d/...` entries separated by `:` (a `D:/...` entry is split there too, so `java` was "not found" until the JRE directory was written as `/d/Random Programs/...`).

## reference-bash-tool-heredoc-quoting

*From the assistant's notes (`reference_bash_tool_heredoc_quoting.md`, type: n/a).*  
*Python patch scripts with backslashes or adjacent quotes get mangled inside Bash-tool heredocs; write the script with the Write tool and run it instead*

Measured 2026-09-24 while patching CRLF source files. Two failures, both silent or misleading:

- `\n\n` typed inside a `python - <<'EOF'` heredoc reached Python as `\n\n` (a real newline), so a `str.replace` on text containing a literal backslash-n asserted "not found" while a diff of the same text looked identical.
- A heredoc containing `f"{count} calculator{'' if count == 1 else 's'}"` made bash report `unexpected EOF while looking for matching '` even though the terminator was quoted.

Hit twice more on 2026-10-06 (P-45.2.3): a `'''` entry text containing `N'-` and backticks ended the string early (`unterminated triple-quoted string literal`), and a `"...\\n"` snippet inserted into a script became a real newline inside the string literal. Prose with quotes in it goes in a file written with the Write tool, then a short script appends it.

**How to apply:** for any multi-line edit that involves backslash escapes or adjacent quotes, put the script in a file with the Write tool (scratchpad) and run `python <file>`. For single edits, the Edit tool works on these CRLF files and handles the line endings; a Python `read_text`/`write_text` round trip on Windows also preserves them. Never use the Bash tool to grep a symbol-looking pattern in indexed code (hook blocks it): `tokensave_search literal=true` instead.

Hit again 2026-10-15 in three more shapes: a `\n` inside a python heredoc string became a real newline (a mutation script then failed to compile and the 35-minute background run printed nothing, so check a background run's FIRST lines before waiting on it); a nested `'''` inside a heredoc; and **backticks inside a double-quoted bash ARGUMENT run as commands** (a docs script argument containing `bounded_json` lost the word and printed "command not found"). Pass prose through a file written with the Write tool, never as a quoted argument or heredoc.

#### Index line before it was shortened (2026-10-18, MEMORY.md has a size limit)

- [Bash-tool heredoc quoting](reference_bash_tool_heredoc_quoting.md) — backslashes mangled in python heredocs, and backticks in a quoted ARGUMENT run as commands (hit AGAIN 2026-10-15); write scripts and prose with the Write tool; read a background run's first lines before waiting

**2026-10-18 again:** a python heredoc that patched ANOTHER script's source (a `.replace("

", "
")` written through it) put real CR/LF characters inside the string literal and broke that script's syntax; an `Edit` cannot match a string containing a CR either. Write any script that carries escapes with the Write tool as a file, and for line-ending logic use `chr(13) + chr(10)`.

## reference-driving-the-gui-on-windows

*From the assistant's notes (`reference_driving_the_gui_on_windows.md`, type: n/a).*  
*How to drive OpenChem Studio's GUI on Alex's machine without input landing in his other windows*

**Never send input without first confirming the foreground window is the
app's process.** `SetForegroundWindow` fails silently on Windows, and
clicks have landed elsewhere **three times now** — twice opening his
Phone Link and surfacing private messages, once clicking and scrolling a
YouTube page in his Firefox.

**The third time (2026-08-07) was because I did not follow this file.** I
wrote ad-hoc `Tap` helpers with no focus check instead of rebuilding
`gui.ps1`, then aimed a click at a notification toast's close button; the
toast belongs to another process, so the click opened Phone Link
full-screen over the app. `Assert-Mine` would have refused that click
outright. Rebuild the script FIRST — the ten seconds it costs is the
whole protection, and skipping it has now cost the same mistake twice.

Corollary: **never click a toast, the system tray, or anything outside
the app's own rect.** Dismiss a notification by ignoring it, or close the
offending app by process afterwards. A toast overlapping the app is not
part of the app.

`Capture-App` filters by window TITLE, and the app's window belongs to
a CHILD process: launching `python -m openchem.main` leaves the parent
owning only a `PseudoConsoleWindow`, with `MainWindowHandle == 0`. Find
the GUI by title across all python processes, then pin `$script:AppPid`
to that child -- `Get-Process python | Where MainWindowTitle -like
'OpenChem*'`.

The working recipe is `scratchpad/gui.ps1` (rebuild it if gone):

- `Assert-Mine` compares `GetForegroundWindow`'s pid to the app's pid,
  retries focus once, then **throws** rather than sending input. Every
  click/type/scroll helper calls it first.
- `Capture-App` uses `PrintWindow(h, dc, 2)` (`PW_RENDERFULLCONTENT`),
  which captures the window **without needing focus** — safe even when
  `Assert-Mine` would refuse, and the way to check state after a failure.
- Modal dialogs are SEPARATE top-level windows of the same process, so a
  main-window capture misses them. Enumerate the process's visible
  windows to find one, then `PrintWindow` it by handle. `Assert-Mine`
  still passes for them (same pid), which is correct.
- Maximized window rect is `(-8, -8)`, so **`screen = capture − 8`**.
  This is easy to read and still not apply, because a LARGE target
  absorbs 8px silently: menu bars and rail entries were hit correctly
  with raw capture coordinates on 2026-08-08, so nothing looked wrong
  until a ~22px tree row. Clicking it 8px high selected the PARENT
  category, whose handler returns "no issue selected" — so the Fix
  button stayed greyed and it read as a broken feature rather than a
  missed click. Three captures went into diagnosing code that was
  correct. **Subtract the 8 for every click, not only the fiddly ones.**

The Windows-MCP `Click` tool's `loc` array does not serialize (arrives as
a string), and its `Shortcut` tool errors on a list. Its `Snapshot`
element labels also go stale as soon as the UI changes. Driving via
P/Invoke from PowerShell is more reliable than either.

**The guard earned its keep again on 2026-08-08.** Launching the app and
checking the foreground BEFORE the first click found **Phone Link** in
front, unprompted — so the very first click of the session would have
landed in his messages for the fourth time. `SetForegroundWindow` alone
did not raise the app; it needed `AttachThreadInput` to the current
foreground thread, then `ShowWindow(SW_RESTORE)` + `SetForegroundWindow`,
then a re-assert. Phone Link stayed visible behind the app for the whole
session and never took focus again.

Two mechanics from that session worth keeping:

- **`mouse_event`'s wheel delta must be declared `int`, not `uint`** —
  a `uint32` signature makes scrolling down (`-360`) a conversion error
  that fires once per scroll and does nothing.
- **The app does not exit on `CloseMainWindow()`.** Clicking the X and
  then calling it both left the process alive; `Stop-Process -Force` was
  needed. Check `QtWebEngineProcess` count afterwards (it went to 0), or
  helper processes accumulate exactly as `CLAUDE.md`'s suite section
  describes.

**Re-assert focus BETWEEN steps, not once per sequence (2026-08-09).**
Launching via `Start-Process uv ...` leaves a console window that grabs
focus part-way through a scripted drive, so a `SendKeys` paste landed
somewhere else while the file dialog sat there empty — and the run looked
like the app had ignored the import. Check the pid before EVERY input,
and click a dialog's field before typing into it rather than trusting
that the dialog opened focused.

**Read `openchem.log` from the LAST `session started` banner.** It is
append-only across every run, so filtering for "the second dump in the
file" silently mixes an old broken session with the current one. That
produced one confident wrong verdict about whether a fix worked, in a
session whose whole point was not repeating wrong verdicts:
`LAST=$(grep -n "session started" openchem.log | tail -1 | cut -d: -f1)`
then `tail -n +$LAST`.

Alex suggested a second virtual desktop to isolate the app; the focus
guard turned out to be the thing that actually fixed it, so that was not
needed. See `feedback-verify-real-backends` — live checks keep finding
things tests cannot, so it is worth doing properly rather than skipping.

## reference-driven-window-activation-steals-keys

*From the assistant's notes (`reference_driven_window_activation_steals_keys.md`, type: n/a).*  
*A drive step that opens a window with text fields must not ACTIVATE it; the person's keystrokes land in it. Found 2026-10-15 as the cause of the one unexplained score_dialog.json failure*

`MainWindow.show_scores()` does `show()` + `raise_()` + `activateWindow()`, right for a person, wrong for a script on a timer. While Alex typed in another window the app (which holds the OS foreground after a driven launch: `QApplication.activeWindow()` was `MainWindow`) passed his next key to the freshly activated dialog, so its Name field gained one stray letter and the form was "unsaved" after Save (`Blend with a defaultr`, `...defaultt`). A fifteen-run loop of just the save sequence reproduced it **2 of 15**; with the driven open non-activating (`show_scores(activate=False)`, `WA_ShowWithoutActivating`) it was **0 of 15**. This was the cause of the one "unexplained 1-in-14" `score_dialog.json` failure in the design record.

**Why:** the harness promises Alex can keep working during a run; any step that moves keyboard focus into a text field breaks it, and the symptom reads as an app bug (a dirty form, a changed label), not an input problem.

**How to apply:** when a failure shows ONE extra character at the end of the focused field, suspect keyboard input from outside before the app. A new drive step that shows a window with text fields should not activate it; log `QApplication.activeWindow()` to see which window holds the keyboard. Not fixed: the app still takes the foreground when a driven run starts, so Alex should type nothing into it in the first seconds. See `reference_qt_gui_and_driving_index`.

#### Index line before it was shortened (2026-10-18, MEMORY.md has a size limit)

- [Driven window activation steals keys](reference_driven_window_activation_steals_keys.md) — a stray letter in a dialog's Name field was a person typing into a window the drive activated; 2/15 -> 0/15 with `show_scores(activate=False)`

## reference-qt-gui-and-driving-index

*From the assistant's notes (`reference_qt_gui_and_driving_index.md`, type: n/a).*  
*driving and measuring the real app, and the Qt/Ketcher traps found doing it*

Moved verbatim out of MEMORY.md on 2026-10-06 to keep the always-loaded index small.

- [Driving the GUI on Windows](reference_driving_the_gui_on_windows.md) — assert the foreground window is the app BEFORE any click; skipping it has opened his Phone Link three times
- [Count pixels, not screenshots](feedback_count_pixels_not_screenshots.md) — the crystal render failed 2 in 5 launches; build the N-run harness before tuning anything visual
- [Live-check the adjacent case](feedback_live_check_the_adjacent_case.md) — the happy path passed live while clicking a hydrogen crashed; walk the neighbouring gesture too
- [Verify index spaces on edited state](feedback_verify_index_spaces_on_edited_state.md) — a fresh load makes Ketcher pool ids and molfile positions agree by accident; only a partial delete shows the divergence
- [runJavaScript returns primitives only](reference_qt_runjavascript_primitives_only.md) — arrays/objects come back as '' from QWebEnginePage; use JSON.stringify
- [Measure in the running app](feedback_measure_in_the_running_app.md) — a Qt harness lied four times about the Properties panel, then the panel suite stayed green through three visibly broken layouts; drive the app AND magnify the shot
- [Qt SVG ignores dominant-baseline](reference_qt_svg_ignores_dominant_baseline.md) — and ignores dy; only x/y move a glyph, browser-correct centring draws half an em high in QSvgWidget
- [Automate the live check](feedback_automate_the_live_check.md) — Alex was right that "needs a human reader" was wrong; the philosophy goes to his other projects, 4 of them have a GUI with no tests at all
- [Qt dialog default button](reference_qt_dialog_default_button.md) — a QDialog makes its first auto-default button the default on show; setAutoDefault(False) when buttons act at once
- [Ketcher hover/keys from automation](reference_ketcher_hover_and_keys_from_automation.md) — hover settable via editor.hover(findItem); key inside editor DOM; number over a bond is NOT native
- [A driven window that activates takes the person's keystrokes](reference_driven_window_activation_steals_keys.md) — `show_scores()` raised+focused the dialog, so a person typing elsewhere put a stray letter in its Name field: 2 of 15 saves failed (the old "unexplained 1-in-14"), 0 of 15 with `activate=False`

#### Index line before it was shortened (2026-10-18, MEMORY.md has a size limit)

- [Qt GUI & driving the app](reference_qt_gui_and_driving_index.md) — foreground check before clicks, count pixels, live-check the adjacent case, index spaces on edited state, Ketcher traps

## reference-qt-dialog-default-button

*From the assistant's notes (`reference_qt_dialog_default_button.md`, type: n/a).*  
*A QDialog shown with no default makes the first auto-default QPushButton in its focus chain the default; Enter passed on by a list or spin box presses it if visible*

Measured 2026-09-14 on the Settings window (PR B). Every test was green. The magnified shot drew the first **Forget** button with a default-button border.

- `QDialog.setVisible(True)` with no explicit default picks the first auto-default push button in the focus chain. Every `QPushButton` inside a `QDialog` is auto-default unless told otherwise.
- `QAbstractItemView` (a `QListWidget`) and `QAbstractSpinBox` ignore Return after handling it, so it reaches the dialog. `QDialog.keyPressEvent` clicks the default button **only if it is visible**.
- So pressing Enter on the section list, with the File dialogs page showing, forgot the projects folder. The same Enter in the revisions spin box on the Results page did nothing, because the button was on a hidden page. The first test written used the spin box and passed with the defect present.

**How to apply:** in any dialog whose buttons act immediately (no OK/Cancel), call `setAutoDefault(False)` on its push buttons after building them. Test Enter from a control that is on the SAME page as the button. Related: `measure-in-the-running-app`, `count-pixels-not-screenshots`.

## reference-qt-runjavascript-primitives-only

*From the assistant's notes (`reference_qt_runjavascript_primitives_only.md`, type: n/a).*  
*QWebEnginePage.runJavaScript on this Qt build returns primitives only — arrays and objects arrive as '', which looks like the page failing*

`QWebEnginePage.runJavaScript` in OpenChem Studio's PySide6 build marshals
**primitives only**. Measured against the vendored Ketcher page:

    return 42            -> 42.0
    return 'hi'          -> 'hi'
    return [1,2,3]       -> ''        <- not an error, just empty
    return {a: 1}        -> ''
    JSON.stringify({..}) -> '{"a":1}'

**Why it matters:** an empty string is what you also get from a script that
threw or returned nothing, so a probe reading a list of ids back reads `''`
and looks like the web app failing rather than the marshalling failing. This
cost a whole probe run — every result came back empty and the first guess was
that Ketcher had not initialised.

**How to apply:** wrap anything structural in `JSON.stringify` on the JS side
and `json.loads` on the Python side. `_run_js_json` in
`tests/test_ketcher_editor_backend.py` is the helper; copy it rather than
re-deriving. Booleans in a `!!(...)` readiness poll are fine, which is why a
wait-loop can appear to work while every real read returns nothing.

Related: `reference-probe-ketcher-through-its-own-api`

## reference-qt-svg-ignores-dominant-baseline

*From the assistant's notes (`reference_qt_svg_ignores_dominant_baseline.md`, type: n/a).*  
*Qt's SVG renderer silently drops dominant-baseline AND dy — only x/y move a glyph, so text centred for a browser draws half an em high in a QSvgWidget*

Measured 2026-08-11 against PySide6's `QSvgRenderer`, rendering the same
fragment with and without the attribute and comparing ink bounding boxes.
**Byte-identical output in all of these:**

    plain                      ink centre 0.5 em ABOVE the anchor
    dominant-baseline=central  identical
    dominant-baseline=middle   identical
    dy="0.35em"                identical
    dy="6.3"                   identical
    y shifted by +6.3          moved

So **only `x` and `y` move a glyph**, and `text-anchor="middle"` *is*
honoured (horizontal is fine; vertical is not).

The needed correction is exactly half the font size, glyph-independent,
checked at 12/18/24/36 px.

**Writing the shift into `y` costs nothing in a browser.** Measured in
Chromium via `getBBox` on an inline SVG: `dominant-baseline="central"`
shifts a text element by **+6.00 px at font-size 18 = +0.333 em**, which
is `(ascent − descent)/2` for Arial. So emitting `y + 1/3 em` with no
attribute gives the same placement a compliant renderer does, and the
exported file stays correct.

**Why:** this is invisible until something else depends on where the
label *is*. In OpenChem it reproduced the canvas overlay's label-box
failure exactly — the dot-placement checker centred its box on the atom,
the page drew the glyph half an em higher, and both agreed the dot was
clear. Every test passed. See `feedback_live_check_the_adjacent_case`
and `feedback_count_pixels_not_screenshots`.

**How to apply:** never rely on `dominant-baseline` or `dy` in SVG that a
`QSvgWidget`/`QSvgRenderer` will draw. Put the offset in `y`, and guard
it two ways — a cheap string check that the attribute is absent, plus one
pixel test that renders through Qt and asserts the ink lands inside the
box the rest of the code assumes.

Two probe traps hit while measuring, both worth reusing:

- Sampling a pixel column through the atom does not isolate its label —
  it catches nearby marks too, and measured a 13 px "O" as 35 px tall.
  Render twice, once with the text stripped, and difference.
- `runJavaScript` cannot return a Promise (see
  `reference_qt_runjavascript_primitives_only`), so the obvious
  Image/canvas probe comes back empty for every variant and reads as
  "nothing rendered". Inline the SVG in the DOM and return a
  `JSON.stringify` synchronously.

## qfiledialog-is-patchable

*From the assistant's notes (`reference_qfiledialog_is_patchable.md`, type: n/a).*  
*QFileDialog's static methods ARE monkeypatchable under PySide6, unlike QMenu.exec*

`monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(fake))` works
under PySide6 — the fake runs and the real `dir` argument is readable from it.
Measured 2026-08-30.

This matters because CLAUDE.md records `QMenu.exec` as un-patchable (it is a C++
slot), and that was being generalised to the file dialogs without measuring.
Prefer a behavioural wiring test over an AST check for anything going through
QFileDialog; keep the AST check alongside when it covers many call sites cheaply.

## reference-ketcher-hover-and-keys-from-automation

*From the assistant's notes (`reference_ketcher_hover_and_keys_from_automation.md`, type: n/a).*  
*A Ketcher hover CAN be set from automation via editor.hover(editor.findItem(...)); the key goes inside the editor's DOM; and a number over a bond is NOT native in the vendored bundle*

Measured 2026-09-24 (`benchmarks/visual/ketcher_hover_keys.json`, step `ketcher_hover`, `docs/KETCHER_SPIKE.md`).

- **Setting a hover:** `editor.hover(editor.findItem({clientX, clientY, pageX, pageY, target: render.clientArea}, null), null, ev)`; the
  client position comes from inverting `render.page2obj` at two probe points. Synthetic DOM mousemove and `QTest.mouseMove` never set the
  flag (that is why the first spike note said "impossible" — wrongly).
- **Pressing a key:** dispatch a bubbling `KeyboardEvent('keydown')` on `render.clientArea.firstChild`; on `document` it is never seen
  (`initKeydownListener` is on the app element). `preventDefault` true = handled.
- **What is native here:** atom + element key (`n` -> N) works; `/` over a bond opens `bondProps-dialog`; a number over a hovered BOND does
  nothing (`getToolHandler` has atoms/sgroups, no bonds). So bond hover+number and click-to-cycle are ours to build — OPEN in
  ARCHITECTURE Known TODOs. Untested idea: the hover trick may be the missing state that made synthetic clicks fail to arm Ketcher's atom/charge tools.
- Related: `reference_qt_runjavascript_primitives_only`, `feedback_a_deferrals_reasons_rot_independently`.

## reference-molstar-shows-assembly-one

*From the assistant's notes (`reference_molstar_shows_assembly_one.md`, type: n/a).*  
*Mol* loadStructureFromData builds biological assembly 1, not the deposited file — and the option that looks like the fix is ignored*

`Viewer.loadStructureFromData` builds **biological assembly 1** by default.
That is not the deposited file, and it is not what docking runs against.

Measured on 6WGT, which has three copies of 7LD and a `REMARK 350`
assembly per chain:

    A/1201  (24.28,  41.05, 54.36)   all Mol* displayed
    B/1201  ( 6.71,   2.21, 54.62)   what binding_site._single_copy boxes
    C/1201  (24.01, -37.77, 54.49)

So a geometrically correct search box rendered ~43 Å from anything on
screen.

**Passing `structure: {name: 'model'}` in the options is accepted and
silently ignored** — the state tree still shows
`type: {name: "assembly", params: {id: "1"}}`. The `structure-from-model`
transform has to be UPDATED after the load, which is what
`showDepositedCoordinates()` in `resources/molstar/viewer.html` does.

**A circular frame test would have passed.** Comparing `box_from_ligand`'s
centre against the box the page was handed compares a value with itself.
Read the ligand's coordinates out of **Mol\*'s own loaded state** instead —
that reported 0 of 24 atoms inside the box immediately. And compare against
the copy `_single_copy` chose (`BindingSite.ligand_positions`), or a
multi-copy deposit reports a large offset that is not a frame error.

`molstar.lib` is exposed and `StateTransforms.Shape.BoxShape3D` exists with
`{bottomLeft, topRight, radius, color}` — probe the vendored bundle in a
bare `QWebEngineView` rather than reasoning about it.

**Measuring a render over the whole window lies**: ink went 39940 → 39942
and read as "nothing drew", because the scene was empty and Mol\*'s UI
chrome is ~57% of the window. Crop to the 3D canvas with a structure
loaded: 16778 → 20270.

#### 2026-08-30: the fix has NO TEST, and a hole on the docking path

Alex reported tryptamines docked into 6WGT "way outside the receptor" —
the same symptom, after the fix shipped. `showDepositedCoordinates()` is
still present, but:

- **Zero test coverage.** `deposited`, `assembly` and `structure-from-model`
  all match nothing in `tests/test_molstar_viewer_backend.py`. It was
  verified once by a live pixel measurement and nothing guards it.
- **It was verified by loading a receptor ALONE**, which is the one path
  that cannot show the defect below.

`_on_docking_result_ready` calls `load_macromolecule` then
`load_additional_structure` back to back. In `viewer.html`, `loadStructure`
does all its work inside `plugin.clear().then(...)` and returns
immediately; `loadAdditionalStructure` has **no such wrapper and runs
synchronously**. So the pose can interleave into the middle of the receptor
load, and `showDepositedCoordinates` keeps the **LAST** matching cell:

    if (... === 'ms-plugin.structure-from-model') { ref = cellRef; }

With the pose's cell present that is the *pose*. Retargeting a
single-ligand structure is a no-op, so the **receptor stays on assembly 1**
and nothing reports a problem.

**This is a LEAD, not a finding** — it is read off the source and was never
run. The gate is `test_the_docking_sequence_leaves_the_receptor_on_deposited_coordinates`
in that test file, which must FAIL first; if it passes, the diagnosis is
wrong and the fix must not be written anyway.

**The box itself was never wrong.** The panel reported "0.0 Å from the 7LD
site, 217 receptor atoms" against `describe_box_placement`'s own pinned
218 — so Vina searched the right pocket and only the picture was wrong.

See project_docking_and_tooltips_branch (pruned 2026-10-06) and
project_dialog_directories_and_viewer_chain (pruned 2026-10-06).

## reference-probes-need-pytest-for-settings

*From the assistant's notes (`reference_probes_need_pytest_for_settings.md`, type: n/a).*  
*An ad-hoc script that builds a Settings object writes to Alex's real registry — the isolation is a pytest fixture, so probes must run through pytest*

Building `Settings(services.event_bus)` in a throwaway script writes to
**HKCU\Software\OpenChemStudio\OpenChemStudio**, the key a shipped install
reads. I did this while probing the menu bar and left
`plugins/project_directory` and `plugins/user_directory` pointing at a temp
directory that had already been deleted. Removed again; the app falls back
to its defaults.

CLAUDE.md documents the suite's isolation at length, but the isolation IS
`isolated_settings`, an autouse **pytest fixture**. Nothing protects a
script run with plain `python`. The file's warnings all read as being about
the suite, so it is easy to conclude the machine is safe when it is not.

**How to probe the real window safely:** write the probe as a temporary
test file under `tests/`, run it with `pytest -s`, and delete it. That
picks up `isolated_settings` and the `qapp` fixture for free. Verify
afterwards with:

```
reg query "HKCU\Software\OpenChemStudio\OpenChemStudio\plugins"
```

Related: `feedback-measure-in-the-running-app` — driving the real app is
routine here, which is exactly why the probe hazard keeps coming up.

## probe-sidecars-with-configured-paths

*From the assistant's notes (`reference_probe_sidecars_with_configured_paths.md`, type: n/a).*  
*Passing None as an interpreter path makes every optional sidecar report \"not installed\" on a machine where it is working*

`pka_predictor_available(None)` and `admet_available(None)` both return
False. They only check that the given path exists, so `None` always means
"not configured" — even when pkasolver and ADMET are both installed and
working.

Read the configured value instead. The keys are
`pka/pkasolver_python_path` and `admet/admet_python_path`, and on Alex's
machine both point under `D:\Random Programs\OpenChemStudio_Data\`
(`pkasolver_env` / `admet_env`, `.venv/Scripts/python.exe`).

**Why it matters:** during the solubility work this produced a whole
design built on "the pKa predictor is unavailable" — including a
Dimorphite-DL fallback that was then measured and found to put
propranolol at 5.65 against a real 9.42. Alex corrected it with a
screenshot of the External Tools dialog.

Measured costs when they ARE configured: pkasolver ~6.7 s per molecule,
the ADMET sidecar ~6 s warm (its docstring's ~300 s is the cold model
load, not the usual case).

Related: `feedback_verify_real_backends`,
`project_external_tools_paths`, `feedback_check_state_before_expensive_work`

## reference-registry-pollution-disables-plugins

*From the assistant's notes (`reference_registry_pollution_disables_plugins.md`, type: n/a).*  
*A leaked plugins/project_directory in the real registry silently turns off every plugin; how to read and check it without writing*

On this machine the real settings live in `HKCU\Software\OpenChemStudio\OpenChemStudio` (QSettings native format). If `plugins/project_directory` or `plugins/user_directory` points at a missing folder, the app loads NO plugins (AI Assistant, Database Search, Reaction Prediction) and the only visible sign was "(none found)" under Plugins > Installed. Found 2026-10-12; the values were `...\Temp\tmpvk7c2jpw/none`, a leftover from before `tests/conftest.py` got its session-scoped settings isolation.

**Why it matters:** "the feature is missing" can be a settings leftover rather than a code bug. A driven run (`OPENCHEM_DRIVE`) reads the REAL registry, so it reproduces exactly what Alex sees; the console dock logs `Loaded plugin ...` lines when it works.

**How to apply:** read without writing: `QSettings("OpenChemStudio","OpenChemStudio").allKeys()` filtered on `plugins`. Never write the registry from an ad-hoc script without asking (see `reference-probes-need-pytest-for-settings`). Since commit 0c797728 `PluginManager.load_all` logs a warning naming the folder and setting.

## reference-guard-lessons-index

*From the assistant's notes (`reference_guard_lessons_index.md`, type: n/a).*  
*lessons about writing and trusting repo guards: mutate before believing, existence vs correctness, one-file vs tree, matching own prose, shipped vs reachable*

Moved verbatim out of MEMORY.md on 2026-10-06 to keep the always-loaded index small.

- [Break a guard before believing it](feedback_break_a_guard_before_believing_it.md) — twelve of my own guards passed while testing nothing; mutate before calling anything coverage, check the guard isn't encoding MY machine
- [Shipped is not reachable](feedback_shipped_is_not_reachable.md) — four modules nothing could reach; the guard I wrote for it under-reported reachability three ways
- [A guard that checks existence](feedback_a_guard_that_checks_existence.md) — my guards keep asking "does X exist" instead of "is X right"; I built the same flaw twice in one session
- [A guard that checks one file](feedback_a_guard_that_checks_one_file.md) — one doc's count was held while three unguarded ones rotted; walk what git tracks, keep the narrow half
- [A guard matches its own prose](feedback_a_guard_matches_its_own_prose.md) — a source scan for a forbidden word keeps hitting the docstring explaining the ban; seven instances, three in one branch
- [Run every tree-sweeping guard](feedback_run_every_tree_sweeping_guard.md) — PR #148 went red on the sources guard I did not run; run all test_*_are_current.py before pushing docs/data
- [Mutation runner discipline](feedback_mutation_runner_discipline.md) — count only pytest exit 1 as a kill, baseline each selection first, `-k` deselects across files, a survivor can be the wrong test selection (Settings dialog vs main-window tooltip walk)

#### Index line before it was shortened (2026-10-18, MEMORY.md has a size limit)

- [Guard lessons](reference_guard_lessons_index.md) — mutate a guard before trusting it; existence is not correctness; shipped is not reachable; run every tree-sweeping guard

## reference-docsweep-what-to-check

*From the assistant's notes (`reference_docsweep_what_to_check.md`, type: n/a).*  
*How a docsweep goes here — most claims are now guarded, so the finds are dated measurements reading as live claims*

Guards now cover the counts that used to rot: calculator counts across
every tracked markdown file, the guide's category count, the README's, the
sources registry, and every cited path and test name. So a docsweep is
mostly **confirming the guards hold** and then hunting the claims they do
not cover.

```bash
uv run --no-sync python -m pytest -q tests/test_docs_are_current.py \
  tests/test_calculator_sections.py tests/test_help.py tests/test_sources_are_current.py
```

**The finds are no longer wrong numbers — they are DATED MEASUREMENTS
phrased as live claims.** 2026-08-26: `SCIENTIFIC_LIMITATIONS.md` said
"Measured across all 48 curated docking targets ... 0 of 48 matched before
this was chased, 38 of 48 match now." The catalogue holds 49 now.

**Correcting 48 to 49 would have FALSIFIED the measurement** — that study
ran on 48 receptors and 38/48 is its recorded result. The fix is to say
which moment it describes, never to bump the figure. Same rule the
calculator guard encodes with `CALCULATOR_COUNTS_ARE_HISTORY`: a count that
is history gets an exemption WITH a reason, not an update.

So the question for each hit is **"is this a claim about today, or a
measurement of a moment?"** — and only the first kind gets corrected.

**Check the live figures rather than trusting a doc.** Measured 2026-09-16:
`CALCULATOR_DEFINITIONS` 60, `RECEPTOR_LIBRARY` 49, `openchem.help.topics()`
120, calculator categories 20, and `docs/sources.toml` 171 entries (101
shipped, 54 reference_only, 16 assessed_not_shipped; 78 citation_and_claim, 93
citation, **0 unverified**). The help topics and the source count both moved a
long way from this file's earlier figures (44 and 94), so re-measure rather
than reusing these.

**2026-09-16 finds, for the shape of what the guards miss.** The guards passed
365/365 and the sweep still found six things, five of them the same kind: a
claim about today that had quietly become false.

- Two documents said an accompanying file "is not held" when it had arrived.
- ROADMAP still called a shipped feature "Not started".
- The USER_GUIDE's list of what a report contains was missing two sections
  that document themselves further down the same file.
- The README's capability tables had no row for a whole feature area.
- **`docs/ARCHITECTURE.md` described `chem` as 83 modules against 115**, with
  37 named nowhere. A count with no guard rots exactly like the calculator
  counts did before theirs was written.

So the sweep questions that actually pay: **does a "not held" / "not started" /
"none of these" claim still hold**, does a list of what something contains
match what it contains, and **is any bare count unguarded**.

Related: `a-guard-that-checks-one-file`, `measure-on-the-target-commit`

## reference-sweep-every-calculator-report-line

*From the assistant's notes (`reference_sweep_every_calculator_report_line.md`, type: n/a).*  
*benchmarks/report_lines/sweep.py — run it before changing either string parser (report_adapter or result_reduction); it overruled an obviously-correct fix once*

OpenChem has **two** free-text parsers judging `matched` lines written
across 49 calculators:

    chem/report_adapter._MEASUREMENT              presentation: recover a label
    chem/result_reduction.parse_reported_numbers  numeric batch columns

**Neither can be reviewed by reading its producers**, and "which lines
does my change affect" is not a grep question. Shipped 2026-08-13 as
`benchmarks/report_lines/sweep.py` (with README and `molecules.json`):

```bash
uv run --no-sync python benchmarks/report_lines/sweep.py --candidate '<value pattern>'
```

It instruments `report_adapter._split` and runs the real registry — **484
distinct lines** — then diffs a candidate value pattern in both
directions. ~2 min. A pattern starting with `-` needs the `=` form
(`--candidate='-?\d...'`) or argparse exits 2, which misreads as the
sweep failing.

**Why it exists.** Fixing `"Dipole Z: +0.16"` (the pattern took a leading
minus, not a leading plus — 18 lines refused for their sign alone), my
first candidate added a `(?=\s|$)` boundary to stop value lists
mis-splitting. Obvious, reads as correct, and the sweep said it
**regresses 31 real lines**: `"C: 23.79%"` and `"Percent buried volume:
13.30%"` attach their unit with no space. Shipped instead: `-?` →
`[-+]?`. Same family as `feedback-calibration-set-shape` — validated
against the reported example, not against the population.

**How to apply:** run it, read *both* directions (a newly refused line
can be the intent — the boundary's 36 were 5 intended + 31 regressions;
the exit code only tells you to look), and check the candidate against
`result_reduction._as_float` too: a value that newly floats turns a text
column into a numeric one asserting something false. **Do not "align" the
two parsers** — the numeric one may refuse what the presentation one must
still show.

Declared gap: it reaches only `bootstrap.CALCULATOR_DEFINITIONS`, never
the `ServiceExecution` panels (Docking, Quantum Chemistry).

## reference-perf-census-measurement-traps

*From the assistant's notes (`reference_perf_census_measurement_traps.md`, type: n/a).*  
*Traps hit while building the resource census — each produced a plausible wrong number before it was caught*

* **Working set lies at idle on Windows.** A background window's RSS and USS get trimmed (400 -> 50 MiB while doing nothing). Use Windows *private bytes* (`memory_info().private`) for idle and slopes.
* **A harness-built window is not the app's window.** The driver's `inspect` / `dialog` steps build dialogs without the `WA_DeleteOnClose` the real paths set, and read +150 MiB/open that the app does not have. Drive the code a click reaches (`call_window`, the real reveal path).
* **Check a parameter exists before using it.** `gasteiger_charge_at_ph` + an invented `ph_dependent` param ran pH-dependent every time and spawned the pKa sidecar; a whole "cheap calculator" batch measured that. Real params are `method`, `pH`. The cheap in-process one is `oxidation_states`.
* **Two batches of the same code can disagree.** Inspector (+80 MiB/open x3) and edit loop (+3.7 MiB/cycle x3) did not reproduce when rerun alone. One batch is not evidence of a trend.
* **A fixed start-up wait is not "pages loaded".** The pages took 3-71 s; use `wait_web_loaded`. Phases read before that measure the load.
* **`ForceField.Minimize` holds the GIL; `MMFFOptimizeMoleculeConfs` and `EmbedMultipleConfs` release it.** Proven with a ticking thread beside a worker (`benchmarks/perf/probes/rdkit_gil.py`).
* **A stack watchdog names the call** (`stack_watchdog` -> `<report>.stacks.txt`): it found the Lewis rebuild and the `setCurrentWidget` freeze. If the innermost frame is `app.exec()` the thread is in native code.
* **Shell mistakes that cost runs:** a Python heredoc turning `\n` into a real newline inside an f-string (the app then fails to import — parse-check after every edit to `debug_drive.py`); running a tool from the wrong cwd after `cd` into the results dir; an ad-hoc `rmtree` of the results folder. New test files need `python tools/suite_shards.py --pin-new` or the shard guard fails CI.

## project-perf-census

*From the assistant's notes (`project_perf_census.md`, type: n/a).*  
*Resource census of the running app (PR #252, merged 2026-10-08) — what it found, what was fixed, the ranked open items, and where the raw data is*

**State: MERGED** as #252 (squash `7380ecaf`). Write-up: `docs/PERFORMANCE_CENSUS.md` (findings F1-F12, "Unresolved", "where the instruments were wrong"). Tools: `tools/perf_census.py`, `benchmarks/perf/scenarios.py`, `src/openchem/app/drive_probes.py`, probes in `benchmarks/perf/probes/`. `psutil` lives in the `perf` dependency group (`uv sync --group perf`); CI's suite job syncs it and the sampler test FAILS in CI if it is missing.

**Raw results are git-ignored.** A copy is at `D:\_scratch\perf-census-2026-10-07` (13 MB, incl. `_superseded/` batches the report cites).

**Fixed (merged):** conformer "Normal" level now uses `MMFFOptimizeMoleculeConfs` (ForceField.Minimize holds the GIL and froze the UI thread; slicing it was measured and rejected); Atom Inspector runs Lewis/oxidation analysis once per table build (`SHARED_ANALYSES` scope). Conformer-phase worst stall 0.45-0.87 s -> 0.13-0.25 s. Conformer benchmark corpus identical (4,793 values).

**Follow-up 2026-10-08 (MERGED 2026-10-09 as #258, squash `88207b4f`; branch `claude/performance-issues-priority-040303`. CI: 3 shards + gating benchmarks green; the NON-BLOCKING linux job was cancelled at its 45-min limit with no failing test = infrastructure, as before):**
- F7 DONE: NP-likeness on a 0-atom structure refuses (`NO_KNOWN_FRAGMENTS`) instead of raising.
- F2 DONE, AND MY ORIGINAL FRAMING WAS WRONG: pKa results were ALREADY cached per structure (`_PAYLOADS`, pH not in the key); the cost is per NEW structure per process. `chem/pka_worker.py` keeps one pkasolver sidecar warm (`pka_runner.py --serve`, owner thread + queue, 120 s idle, killed on timeout, `OPENCHEM_PKA_WORKER=0` disables; the suite sets it to 0). Measured: 3 sidecars/run -> 1; new structure 2.6-4.5 s -> 0.3-0.45 s warm; first startup 2.3-2.6 s, or ~31 s on a cold file cache (a worker cannot remove that). `use_cache=False` stays one-shot.
- F1 PARTLY: Mol* and the Alignment 3D view build on first use (`ensure_built()`, stable container). Measured idle tree 1,604-1,638 -> 1,441-1,453 MiB (~10%, NOT the "half" I had guessed), children 4 -> 2, no startup-time gain, no new first-use stall; Mol* users pay ~140-160 MiB when they open it and end at the same memory.
- Items 4 (3D freezes) and 5 (inspector/edit "leaks") deliberately NOT chased; reopen only on a reproducible user-visible report / fresh dynamic signal.
- Lessons: (1) a venv `python.exe` on Windows is a launcher but `Popen.kill()` ends its child too (job object) - I wrote and removed a taskkill on a wrong suspicion; (2) the machine hit 98% memory mid-session and gave 122 s startups: log `psutil.virtual_memory().available` at the start of every census arm and discard contaminated batches (kept as `*__contaminated`); (3) `probes=["heartbeat"]` in a Scenario is metadata only - stalls need explicit `loop_lag` steps; (4) doc-citation guards resolve files through the git index, so `git add -N` a new file before running them.
- Test-suite facts learned: a full single-process run needs a JRE on PATH (the app's own is at `D:/Random Programs/OpenChemStudio_Data/jre/jdk-21.0.12+8-jre/bin`); `test_perf_census::test_object_census_sees_retained_widgets_and_an_active_timer` passes alone and in CI shard 2 but fails in one long process (it reads only the first 40 active timers); `test_the_3d_view_grabs_a_real_png` is flaky locally; new test files must be pinned with `tools/suite_shards.py --pin-new`; shard file lists have CRLF endings.
- Raw results of the follow-up: `D:/_scratch/perf-census-followup-2026-10-08/` (3 MiB; the probes, step0, the png/ and timers/ investigations, both pKa-sidecar arms, the `*__contaminated` batches, and the AFTER arms of the web-view runs). **The BEFORE arms of the web-view measurement are gone** (they ran in a scratch checkout I removed); only the numbers in `docs/PERFORMANCE_CENSUS.md` remain.

**Why:** Alex said the app felt sluggish/expensive compared with his other projects.
**How to apply:** read the report's Unresolved + "where they were wrong" sections before trusting any number here; re-measure a finding alone and on a quiet machine before acting on it.
See `reference-perf-census-measurement-traps`.

- Later the same day: #260 (census test reads all timers, not the first 40; 131 leftover 500 ms timers from test modules that keep a MainWindow alive) and #263 (the two 3D grab tests skip when WebGL cannot draw a known colour; they now run nowhere that fails the probe, CI blocklists WebGL). The PNG-grab flake was NOT root-caused (see `png/FINDINGS.md` in the folder above). The remote branches of #258/#260/#263 were left (never delete a remote branch).
