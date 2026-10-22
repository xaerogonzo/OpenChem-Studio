# Displaced-restart diagnosis (exploratory, 2026-10-21; NOT a benchmark record)

After the proton-affinity run (PASS, water missing) and the bond-dissociation run (PARTIAL, three deciding bonds missing), this tried one repair on the four structures the preregistered rule dropped: take the structure's final geometry, compute its Hessian, **displace it by 0.15 Angstrom (largest atom component) along the most imaginary normal mode in each direction, and re-optimize** (`! M062X def2-TZVPD TightSCF TightOpt DefGrid3 Opt Freq`, `%geom Calc_Hess true`, 4 cores). `diag_displace.py` is the script (it reads the committed `runs.jsonl` of both benchmarks); `results/*.json` are its outputs. Nothing here changes either verdict; `benchmarks/restart_v2/PREREGISTRATION.md` is the protocol that would be tested properly.

| structure | v1 lowest mode (cm-1) | after displacement (+ / -) | H of the accepted structure (Eh) |
|---|---|---|---|
| H3O+ (water's ion) | -601.6 | 0.0 / 0.0 (both minima) | -76.66319626 (v1 dropped one: -76.66272409; the preregistration's smoke run: -76.66319385) |
| ethanol radical | -105.8 | 0.0 / -64.0 | -154.28373255 (v1 saddle: -154.28483662) |
| toluene (parent) | -49.4 | -31.3 / -12.7 | -271.40099483 for the -12.7 one (v1: -271.40099749) |
| CH3S radical | -1328.2 | -1743.5 / -1553.1 | none: worse, and the energy does not move |

The bond enthalpies these would give (`bde_core.bond_dissociation_enthalpy`, kcal/mol, reference in brackets): ethanol O-H 102.79 [104.7], toluene benzylic C-H 90.38 [89.8], methanethiol S-H 83.96 [87.4] (not repaired). **These numbers were computed after the verdict was seen and the protocol was designed after the verdict, so they are not evidence for the verdict and move none of it.**
