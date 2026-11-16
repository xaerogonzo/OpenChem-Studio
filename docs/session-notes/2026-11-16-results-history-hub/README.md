# Results history hub (2026-11-16)

Branch `cursor/results-history-hub`. Implements Option B from `docs/RESULTS_PROPERTIES_QUANTUM_DESIGN.md`: property-execution store beside the cache; Results lists, groups, deletes, and compares; wizard Quantum staging uses the wizard scope.

## Verified

`PYTHONPATH=src` with `D:\_scratch\OpenChem-Studio-d7b5ea33\.venv\Scripts\python.exe -m pytest` on `tests/test_property_execution.py`, `tests/test_results_history.py`, `tests/test_goal_wizard.py::test_wizard_scope_is_its_own_box_not_properties`, `tests/test_fact_view_copy.py`, `tests/test_results_showing_popup.py`, and the Results help-routing case: **42 passed**.
