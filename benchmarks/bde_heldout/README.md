# The held-out X-H bonds of the bond-dissociation benchmark

The reference data for Arm B of `benchmarks/restart_v2/PREREGISTRATION.md` (a DRAFT, not frozen; nothing here has been calculated with ORCA).

* `extract_atct.py` -- reads the saved ATcT 1.228 table (the HTML page, from Alex's paper library; **not committed**, 4.5 MB), checks every pair by formula and structure, computes each bond enthalpy as `dfH(R.) + dfH(H.) - dfH(RH)` with its uncertainty, and writes the two files below. It stops if the table is not the 3,455-row version this was built from.
* `candidates.json` -- the 30 bonds that met the rule (27 deciding, 3 excluded with their reasons and what would lift them), each with the table's numbers it was built from. The list was written before any of these enthalpies was computed.
* `crosscheck_v1.json` -- the same arithmetic on the first run's bonds that Blanksby and Ellison also give, so the converter is held to references already held (mean difference -0.11 kcal/mol; one bond beyond three combined uncertainties, propene's allylic C-H).
* `tests/test_bde_heldout_data.py` -- recomputes every bond from the stored numbers, checks the structures, the overlap with the first run and the exclusions.

To rebuild: `uv run --no-sync python benchmarks/bde_heldout/extract_atct.py "<path to ATcT Thermochemical Values ver. 1.228.htm>"`.
