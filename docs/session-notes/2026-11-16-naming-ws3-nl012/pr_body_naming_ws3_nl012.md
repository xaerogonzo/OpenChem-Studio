## Summary

This branch closes WS3 naming-limitations P3 work (NL-020, NL-050, NL-080, NL-085, NL-088, NL-089, NL-106, NL-023, NL-024) and finishes NL-012 spiro joints left open after naming rounds 84–85: mixed primed/unprimed spiro ring diketones now cite `-2',4(3H)-dione` so OPSIN read-back succeeds on the pteridinone matrix pairs; adamantane substituent shape (1) is pinned as a name, not a naming error. Merge the matching fork PR first so standalone `open-iupac-namer` carries the same `engine.py` change.

## Cross-links

Fork PR https://github.com/xaerogonzo/open-iupac-namer/pull/101 (branch `claude/nl012-spiro-diketone-opsin`), ported with `tools/fork_port.py --base 3bb0de4c --head 8b27c049`. Merge fork #101 first; then add the VENDORING.md row and run `tools/vendoring_mark_synced.py` as usual.

## Verified

Pushed branch `naming/ws3-nl023-p3-closure` at `8b27c049`. With `C:\Program Files\Bitwig Studio\jre\bin` on PATH: `uv run --no-sync python -m pytest tests/test_namer_nl012_spiro_open_defects_post_round84.py -q` — 6 passed (OPSIN read-back on adamantane and both pteridin pins). Fork clone `D:\_scratch\open-iupac-namer-port` (same JRE on PATH, `PYTHONPATH` set to that tree): the ported NL-012 test files — 10 passed. `uv run --no-sync python tools/changelog.py check` was run on the branch before this push in the same session.