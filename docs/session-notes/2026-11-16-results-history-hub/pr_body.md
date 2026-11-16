## Summary

- Property executions are a durable history (new id on every Run, `parameters_key` on the execution) beside `SessionResultStore`; the cache slot is unchanged.
- Results lists those executions and Quantum `run_id`s, collapses method groups, labels fingerprint-mismatched rows as historical, and routes delete/compare to the owning store with explicit refusals (including ORCA vs Psi4 when the functional name matches).
- Goal-wizard Quantum staging reads the wizard’s own Run-on box, not Properties’ scope.

## Cross-links

Follows the design in `docs/RESULTS_PROPERTIES_QUANTUM_DESIGN.md` (Option B) after docs PR #629.

## Verified

`PYTHONPATH=src` and `D:\_scratch\OpenChem-Studio-d7b5ea33\.venv\Scripts\python.exe -m pytest` on `tests/test_property_execution.py`, `tests/test_results_history.py`, `tests/test_goal_wizard.py::test_wizard_scope_is_its_own_box_not_properties`, `tests/test_fact_view_copy.py`, `tests/test_results_showing_popup.py`, and `tests/test_help.py::TestHelpRouting::test_focus_in_a_panel_selects_that_panels_topic`: 42 passed.
