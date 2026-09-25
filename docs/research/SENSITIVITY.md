# How wrong inputs move the Kamlet-Jacobs estimate

The detonation calculator needs two numbers it cannot estimate: a **loading density** and a
**condensed-phase enthalpy of formation**. Every density and enthalpy method the survey will compare
predicts one of them with some error. This note records what those errors do to the estimate, so effort goes
to the input that matters, and it says what it does *not* show.

`tools/energetics_sensitivity.py` computes everything below through the calculator's own equations
(`chem/energetics.py`), so it cannot disagree with what the calculator would say. Three artefacts, kept
apart because they answer three different questions:

1. **Local sensitivity**: the analytic elasticity at the nominal point. A slope.
2. **A finite perturbation** through the real equation. A step; needed because pressure goes as the *square*
   of density, so a slope understates a step of realistic size.
3. **Realistic input uncertainty**: a method's measured validation error. **Not computed here.** A
   validation RMSE is never a per-molecule interval.

## The worked example (one compound)

RDX, Kamlet-Jacobs 1968 Table III as `tests/test_energetics.py` records it: loading density 1.712 g/cm3,
Q = 1496 cal/g, printed P = 311.9 kbar and D = 8.512 mm/us. The enthalpy is not printed; the paper's Q
implies 17.71 kcal/mol through Eq. (15b). From the formula the module gives P = 311.2 kbar and D = 8.505
mm/us, within the rounding of the paper's printed inputs.

```
python tools/energetics_sensitivity.py --preset rdx-table-iii
```

**Local sensitivity** (measured 2026-09-24):

| | value |
|---|---|
| d ln P / d ln rho | 2.00 (exactly: P is proportional to rho squared) |
| d ln D / d ln rho | 0.690 |
| d ln Q / dH | 0.301 % per kcal/mol |
| d ln P / dH | 0.151 % per kcal/mol |
| d ln D / dH | 0.075 % per kcal/mol |

**A finite step in each input alone**, at *illustrative* sigmas of 0.04 g/cm3 and 9.3 kcal/mol (round
numbers of the size the literature discusses; **not** any method's error):

| step | dQ % | dP % | dD % |
|---|---|---|---|
| rho -0.04 | 0.00 | -4.62 | -1.61 |
| rho +0.04 | 0.00 | +4.73 | +1.61 |
| H -9.3 | -2.80 | -1.41 | -0.71 |
| H +9.3 | +2.80 | +1.39 | +0.69 |

## What this shows, and what it does not

- For **this compound**, at these steps, the density step moves the pressure about **three times** as much
  as the enthalpy step, and moves the velocity about **twice** as much; only the heat of detonation Q itself
  is more sensitive to the enthalpy. That follows from the equations: P goes as rho squared and only as the
  square root of Q, and Q is a difference of large terms.
- It agrees in direction with the one source that says it from its own work. Kim et al. 2008 (held; see
  `literature.toml`) report, from their own preliminary results, that "a density change of 0.1 g/cc
  significantly impacted on the explosive performance, while a difference of 10 kcal/mol in heat of formation
  had little influence", and that performance needs the density "within an error of 0.03 g/cc, and the heat
  of formation within an error of 5 kcal/mol". Those are their statements about their own results, not
  something re-derived here.
- **It does not show that density dominates the error budget for explosives in general.** That is a claim
  about a *set*, and the set (a sourced known-explosives table) does not exist yet. The tool is written to
  be run over it when it does, and the survey should not lean on one worked example until then.
- **It says nothing about which method to prefer**: that needs each method's measured error on a
  leakage-checked common evaluation set, which is what artefact (3) is.
- The elasticities are at the nominal point; they change with the compound, and for a compound with a small
  Q (a low formation enthalpy relative to the large terms) the enthalpy elasticity is larger.
