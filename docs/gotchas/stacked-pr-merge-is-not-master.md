# GitHub "Merged" is not "on master"

OpenChem Studio, 2026-11-25: #652 and #656. The same GitHub rule applies on any repo that squash-merges stacked PRs.

**Symptom.** A stacked follow-up PR shows **MERGED**. Chat and the GitHub UI treat the work as shipped. `origin/master` does not contain the commits. A later session rediscovers the feature as missing and retargets it.

Measured 2026-11-25 on this repo: #652 (Gasteiger vs QC dipole) and #656 (QC dipole overlay) were MERGED. Their bases were `cursor/qc-dipole-family-compare` and `cursor/qc-dipole-vector-parse`. `git merge-base --is-ancestor <merge-commit> origin/master` was false. The parent PRs (#650, #655) had already squash-merged to `master`, so the follow-ups landed on leftover feature branches.

**Cause.** A GitHub pull request merges the head **into its base**, not into `master` unless the base *is* `master`. Stacking (`gh pr create --base some-feature-branch`) is correct only while that parent is still the integration branch. After the parent is on `master`, leaving the child's base on the old branch means Merge writes into a branch nobody ships.

**Why it hides.** GitHub's MERGED badge, the green merge commit, and `gh pr view --json state` all look like success. Squash-merging the parent also means the child's commits are not even ancestors of `master` in a fast-forward sense. CI on the stacked PR can be green against the parent branch and still never run as `master`.

**Fix.** Before merge, `gh pr view N --json baseRefName` must be `master` (or the real long-lived default). If the parent has landed:

```text
gh pr edit N --base master
```

Then merge. Opening a *new* PR from a rebase onto current `origin/master` is the same rule: `--base master`. Do not treat GitHub MERGED as shipped until `git merge-base --is-ancestor <sha> origin/master` is true.

Stacked PRs stay useful *before* the parent merges. After it merges, retarget or rebase; do not click Merge on a stale base.
