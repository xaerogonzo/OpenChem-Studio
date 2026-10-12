# Calculator cost

What each registry-run calculator costs, and which of them a parameter changes. It is the evidence
behind `src/openchem/domain/builtin_execution_policies.py`: every class (instant, short) and every
ceiling there is read back against `results.json` by `tests/test_execution_policy.py`, so a bound
cannot be loosened without these figures loosening it.

```bash
uv run --no-sync python benchmarks/calculator_cost/measure.py
```

About ten minutes, mostly the slow cases the policy exists to catch. It writes `results.json`.

## What it measures

Through `openchem.cli.calculation`, the Qt-free twin of the application's task, on three fixed
molecules with one seeded, unoptimised conformer each: ethanol (3 heavy atoms), aspirin (13) and
atorvastatin (41, the largest the policy's figures stand for).

1. **`defaults`**: every registry calculator at default settings, on all three.
2. **`with_inputs`**: the calculators that only *refused* at their defaults (`lewis_adduct`,
   `detonation`, `alignment_3d`, `markush_enumeration`, and `griffin_hlb`, which is defined for
   surfactants and refused all three panel molecules), re-run with real inputs. A refusal is
   fast; timing one measures nothing about the calculator.
3. **`scaling`**: the calculators whose cost depends on a parameter, at the values a model could
   choose.

## What it found (2026-10-12)

* Every registry calculator ran in under 1.3 s at its defaults.
* **Four scale measurably with a parameter**, and the defaults hide it. `hbond_vs_ph`: 0.6 s at a 0.5 pH step,
  16.7 s at 0.01. Molecular dynamics: 0.17 s at 1,000 steps, 16.6 s at 100,000. Geometry (3D) under
  `conformer_policy=always`: 4.0 s at 20 conformers, 29.7 s at 200 (1.1 s under `never`). The stereoisomer
  enumerator: 1.1 s at a 2,000-structure cap, 2.9 s at 10,000. The tautomer and resonance enumerators did not
  scale on the molecules tried (0.8 s and 0.00 s at 10,000) and carry the same cap as a precaution; the
  three sidecar-driven pH sweeps carry the pH-step floor by analogy, unmeasured.
* **Alignment is slow on realistic molecules**: a 41-heavy-atom molecule took 0.6 s aligned to a
  13-heavy-atom reference and 31 s aligned to a 28-heavy-atom one, which then took 46 s with MCS, and
  74 to 104 s on `Accurate` and 109 to 163 s with both across four runs (the `Accurate` runs differ more
  between runs than anything else here; `results.json` holds the latest).
* A choice parameter is **not validated by the calculator**: `geometry_analysis` accepted
  `conformer_policy="lowest_energy"` (not one of its choices) and ran. The assistant bridge validates
  parameters itself.

## What it does not measure

The pkasolver and ADMET-AI sidecars are unconfigured on a command line, so those calculators report
`needs_setup` and their cost is cited from the roadmap (pkasolver, a cold call of 2.9 to 3.1 s) or filed
as not measured (ADMET-AI). `iupac_name` starts Java and reaches the network, which the command line
declines to do (`cli/calculation.EXTERNAL_EFFECT_CALCULATORS`). Service-run calculators (Docking, ORCA)
are not registry runs. Absolute seconds are this machine's; the *ratios* and the classes are what
transfer.
