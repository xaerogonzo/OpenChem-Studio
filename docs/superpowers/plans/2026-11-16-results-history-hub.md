# Results history hub Implementation Plan

> Cites `docs/RESULTS_PROPERTIES_QUANTUM_DESIGN.md` (Option B). Do not expand `SessionResultStore.put()` to include `parameters_key`.

**Goal:** Durable, deletable property-execution history plus Quantum runs in Results, wizard staging from the wizard's own scope, and explicit compare refusals.

**Architecture:** New `PropertyExecutionStore` (Quantum-run-shaped, not a cache). Results aggregates cache + executions + QC runs. Cache contract unchanged.

**Tech Stack:** Python 3.11+, existing project JSON envelopes, PySide6 Results reader.

## Global Constraints

- No Quantum on Fill table or Properties ticks.
- Identical repeats mint a new execution id.
- History delete does not edit automatic bundle manifests.
- Quantum delete is history-only; landed geometries stay.
- Staging still refuses `all` / `chosen`; it reads the **wizard** scope, not Properties.
