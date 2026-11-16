# Session notes (per-PR working drafts)

Agents and maintainers keep **draft commit messages**, **PR bodies**, and **small measurement scripts** here so nothing useful is lost in repo-root scratch files or chat-only handoffs. This is not user documentation; it is an audit trail for how a branch was verified and what was decided.

## When to add a folder

Add a subdirectory for any PR that is **multi-commit**, **naming/vendor/fork paired**, or **relied on measured probes** (OPSIN, ORCA, drive JSON, and similar). Skip one-line fixes unless the session produced a non-obvious PR body or verification command list worth keeping.

## Layout

```
docs/session-notes/
  README.md                          ← this file
  YYYY-MM-DD-short-slug/
    README.md                          ← what the branch/PRs were, links, one table of files
    pr_body_*.md                       ← bodies passed to `gh pr create --body-file` (Windows)
    commitmsg*.txt                     ← commit messages drafted before `git commit -F`
    scratch_*.py                       ← throwaway probes; must run under `uv run` from repo root
```

**Naming:** use ISO date and a slug tied to the branch or programme id (`2026-11-16-naming-ws3-nl012`, not `_pr_body.md` at the repository root).

## Relationship to shipped docs

| Ship here | Ship elsewhere |
|-----------|----------------|
| Draft PR text, draft commits, probe scripts | `changelog.d/*` for release notes |
| Measured commands copied into PR **Verified** | Final architecture in `docs/ARCHITECTURE.md` |
| Fork/app PR cross-links while open | `src/openchem/vendor/VENDORING.md` after fork merge |

Do not put secrets, paywalled PDF paths with credentials, or regulatory ruleset substance in session notes (same rules as PR bodies and chat).

## Workflow (Windows-friendly)

1. Create the folder early in the session (`docs/session-notes/YYYY-MM-DD-slug/`).
2. Write PR bodies to `pr_body_*.md`; open PRs with `gh pr create --body-file path` (heredocs are unreliable in PowerShell).
3. Write commit messages to `commitmsg_*.txt`; commit with `git commit -F path`.
4. In the folder `README.md`, list fork PR numbers, app PR numbers, and what was measured.
5. Commit the folder on the feature branch **or** open a small docs-only PR to `master` first so notes survive if the main PR is long-lived or rebased.

Example bundle: [`2026-11-16-naming-ws3-nl012/`](2026-11-16-naming-ws3-nl012/).