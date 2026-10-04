# Method-screen selection rule (written 2026-10-03, BEFORE any single-point number from M062X / wB97M-V / revDSD exists)

Candidates (all def2-TZVP; revDSD with def2-TZVP/C): `M062X`, `wB97M-V`, `revDSD-PBEP86-D4/2021`.
Baseline already known: PBE0 def2-TZVP (v3 preset).

Data: development systems ONLY (cytosine, acetylacetone, acetaldimine/vinylamine, 2-pyridone), single points on the
PBE0/def2-TZVP optimized pool geometries (a disclosed cost shortcut). A tautomer's energy = min over its pool conformers.
References and gate arithmetic are exactly the frozen v1 criteria (tie 1.0, MAE <= 1.0, max <= 2.0, one error per
reference-listed tautomer after rebaselining each vector to its own lowest reference-listed tautomer).
The held-out manifest systems are NOT touched.

Rule:
1. A candidate is ELIGIBLE only if it passes the ranking check in every one of the four systems.
2. Among eligible candidates, score = the largest per-system max|error| (kcal/mol). Lowest score wins.
3. Scores within 0.25 kcal/mol of each other are a tie; a tie goes to the cheaper functional
   (cost order: M062X < wB97M-V < revDSD-PBEP86-D4).
4. If no candidate is eligible, NO method is chosen from this screen: report that, and decide with Alex.
5. Passing the screen is NOT a validation claim. It selects which method gets the preregistered held-out run.
6. The result is reported as it falls; the rule is not edited after the numbers are seen.
