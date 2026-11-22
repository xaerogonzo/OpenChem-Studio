## Summary

- A Quantum radio in Run Calculators by Goal stages from the wizard’s own **Run on** box. Properties **Run on** is ignored, so the panel can sit on all molecules while the wizard stages this one.
- All or chosen wizard scope still refuses: this is not a batch Quantum path, and the wizard does not start the job.
- Later leftovers stay later: start-from-wizard, a global Method combo, Quantum on ticks/Fill, same-family Quantum compare.

## Cross-links

Follows mixed history compare #638. Design §2 and §12 in `docs/RESULTS_PROPERTIES_QUANTUM_DESIGN.md`.

## Verified

On `D:\_scratch\OpenChem-Studio-e262d953` with `PYTHONPATH=src`, `QT_QPA_PLATFORM=offscreen`, and `D:\_scratch\OpenChem-Studio-d7b5ea33\.venv\Scripts\python.exe`: `pytest tests/test_quantum_goal_action.py tests/test_goal_wizard.py tests/test_goal_run.py tests/test_changelog_fragments.py tests/test_docs_are_current.py tests/test_help.py tests/test_layering.py` 395 passed; a second run of the new MainWindow tests plus changelog/docs 300 passed.
