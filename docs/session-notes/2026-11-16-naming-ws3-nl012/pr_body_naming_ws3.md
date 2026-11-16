## Summary

Close WS3 naming-limitations work for 2026-11-15: Blue Book V3 source pins for NL-023 and NL-024, CIP Validation Suite inventory (`benchmarks/naming/CIP_VALIDATION_SUITE.md` and probe), and WS3 P3 closure tests for NL-020, NL-050, NL-080, NL-085, NL-088, NL-089, and NL-106. The limitations plan and rounds handoff mark these rows closed; diazepam `engine_name` in `adjudication.toml` matches the current engine hydro spelling while the row stays UNDECIDED.

## Verified

`uv run --no-sync python -m pytest tests/test_namer_nl020_ws3_heptalene_bi_validator.py tests/test_namer_nl080_ws3_betaine_prefix_sources.py tests/test_namer_nl085_ws3_hypoboric_validator.py tests/test_namer_nl088_nl089_ws3_bench_policies.py tests/test_namer_nl050_ws3_radical_anion_validator.py tests/test_namer_nl106_ws3_adjudication_undecided.py tests/test_namer_nl023_ws3_cation_ester_sources.py tests/test_namer_nl024_ws3_ring_ketone_substituent_sources.py -q` — 12 passed, 10 skipped (no Java on PATH for OPSIN read-back). `uv run --no-sync python tools/changelog.py check` — 27 fragment(s) ok.