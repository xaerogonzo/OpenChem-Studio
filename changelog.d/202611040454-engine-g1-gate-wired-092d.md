### Wire G1 survey-repro gate into engine test runner
- `run_engine_test.py gates` now reruns Vina at seed 20261029 against `artifacts_prep_box` before G5, writes `g1_results.jsonl`, and skips G5 when G1 fails; logic lives in `engine_g1_survey.py` with tests pinning the 47-receptor recorded set.
