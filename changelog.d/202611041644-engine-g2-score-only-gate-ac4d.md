### Wire G2 score-only control into engine test runner
- `run_engine_test.py gates` now runs G2 after G1 (Vina vs smina-default `--score_only` on nine poses for the first five pilot receptors, 0.01 kcal/mol) and skips G5 when G2 fails; `engine_g2_score_only.py` holds the measurement.
