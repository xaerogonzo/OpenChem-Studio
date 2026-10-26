# Changelog fragments

A pull request does **not** edit `CHANGELOG.md`. It adds one file here. Two PRs add two
differently named files, so they cannot conflict, which is the whole point: every PR used to
insert its section at the same line of `## [Unreleased]`, and the second to merge had to be
rebased and wait for CI again.

```bash
uv run --no-sync python tools/changelog.py new short-topic-name   # prints the new path
# edit it: one "### Title" line, then "- " bullets, exactly the shape of a CHANGELOG section
uv run --no-sync python tools/changelog.py check                  # read-only
uv run --no-sync python tools/changelog.py preview                # the CHANGELOG.md build would write
```

- **Filename** `YYYYMMDDHHMM-<slug>-<4 hex>.md` (UTC). The hex keeps two same-slug fragments
  from independent branches apart. The stamp is the order, newest first: when the author
  started the fragment, not when it merged. It needs no Git history.
- **`check` rejects** an unedited template, a missing or doubled `###` title, no bullet outside
  a code block, an unclosed fence, and a title that duplicates another fragment or one already in
  `[Unreleased]`. It runs in the test suite (`tests/test_changelog_fragments.py`).
- **Nothing enforces that a PR adds a fragment.** `check` validates the ones that exist. It is
  a convention; a reviewer notices a missing one.
- **`build`** (release preparation only, see `docs/RELEASING.md`) writes the fragments into
  `[Unreleased]` ahead of the older entries, then deletes them. It changes no Git index and makes
  no commit. The release workflow fails a tag that still has fragments (`check --no-pending`).
- This folder is development material and is not shipped (`docs/RELEASE_CONTENTS.md`).
