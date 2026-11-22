## Summary

- Goal wizard **Customise… → Run** stages then starts the chosen Quantum action on **This molecule** through the Quantum Chemistry panel (`prepare_run`, LED cost, queue). **Apply to Properties** still stages only.
- The panel combo is synced to the wizard molecule before staging, so Properties A vs panel B cannot start B. A busy panel is refused before staging. All/chosen still refuse; **Run recommended** still does not request Quantum.
- Charge, solvent, and conformer stay panel settings of that molecule. Fill, ticks, and a global Method combo stay out of this PR.

## Cross-links

Follows wizard Quantum staging #639 and family compare #640. Design §2 and §12 in `docs/RESULTS_PROPERTIES_QUANTUM_DESIGN.md`.

## Verified

On `D:\_scratch\OpenChem-Studio-e8537480` with `uv run pytest`: `tests/test_goal_wizard.py tests/test_goal_run.py tests/test_quantum_chemistry_panel.py tests/test_quantum_run_button.py tests/test_quantum_start_assistant_run.py` 240 passed.
