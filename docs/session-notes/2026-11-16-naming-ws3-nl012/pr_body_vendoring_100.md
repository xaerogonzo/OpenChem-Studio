## Summary

Records app pull request #576 as squash-merged on master at `cf8fe964` with base `f503ba5b` in the fork #100 row of `VENDORING.md` (replaces `squash pending` and the stale base). Fork open-iupac-namer#100 remains open until merged there.

## Verified

`uv run --no-sync python tools/changelog.py check` — 177 fragments ok. `uv run --no-sync python tools/vendoring_mark_synced.py --check` — exit 0. `uv run --no-sync python -m pytest tests/test_vendoring_mark_synced.py` — 3 passed.
