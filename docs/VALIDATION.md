# Validation

Every number this application reports has a measurement behind it. This page
collects them in one place, each with the method and the sample size that
produced it, and links out to the benchmark that owns it — so there is one
source of truth per number, not a copy here that quietly goes stale.

If you only read one thing: the results that mattered most were the ones
that said *no*. Four features were built far enough to be measured and then
dropped. Those are in the last section.

---

## Naming — 181/181

**Method.** 181 molecules across 22 categories, ground truth from PubChem.
Scored by **structural round-trip**, not string equality: the predicted name
is parsed back with OPSIN and the resulting structure compared to the input.
A name that is correct but phrased differently passes; a name that is
plausible and wrong does not.

Re-run for this release against the 181-molecule corpus:

| outcome | n |
|---|---|
| `exact` — the expected name, character for character | 82 |
| `equivalent` — a different but correct name, confirmed by round-trip | 98 |
| `tautomer` — round-trips to a different tautomer of the same compound | 1 |
| **correct** | **181/181 (100%)** |
| stereochemistry | **11/11, 0 silently flattened** |

For comparison, the same engine as originally vendored scored 148/165 (90%)
on the revision that existed then.

The `tautomer` class is metformin, and it is deliberately kept visible
rather than folded into `equivalent`. It is awarded only when a canonical
tautomer match **and** an InChIKey match both agree — a deliberately strict
pair, verified not to collapse on the charge defects the gate exists for
(guanidine vs guanidinium and benzyl cation vs toluene both still fail, as
they must).

**Against the ML alternatives**, scored on the earlier 124-molecule revision
— the only one all four engines were run on:

| engine | correct | stereochemistry | dependencies | speed |
|---|---|---|---|---|
| **deterministic (shipped)** | **120/124 (97%)** | **11/11** | rdkit only | 12 ms |
| `SMILES2IUPAC-canonical-base` | 88/124 (71%) | 0/11 — crashes | torch + transformers, 1.1 GB | 190 ms |
| `SMILES2IUPAC-isomeric-small` | 75/124 (60%) | 5/11, **3 silently flattened** | torch + transformers | 97 ms |
| `SMILES2IUPAC-canonical-small` | 71/124 (57%) | 0/11 | torch + transformers | 97 ms |

Silent stereochemistry flattening is separated out deliberately: an engine
that drops a stereocentre without saying so is more dangerous than one that
fails loudly.

→ [`benchmarks/naming/`](../benchmarks/naming/)

---

## NMR shift prediction

### The HOSE-code lookup — per-band error, measured

**Method.** The index was rebuilt with every twentieth molecule excluded,
then those molecules predicted. This is a genuine novel-compound test: the
environments being matched came from other molecules entirely.

| band | n | MAE | median |
|---|---|---|---|
| `good` | 11,390 | **1.12 ppm** | 0.50 |
| `medium` | 10,933 | **3.36 ppm** | 2.31 |
| `rough` | 1,957 | **10.00 ppm** | 7.17 |
| all | **24,280** | 2.85 ppm | 1.23 |

These per-band figures are not decoration — they are what the hybrid selects
on. An atom is assigned to a band by how well its environment is
represented, and the band's measured error is that prediction's expected
error.

**Corpus-specific, and known to be.** Re-measured on DELTA50 the bands do not
transfer exactly. The constants carry the corpus they were measured on.

### The hybrid — judged on its decisions, not just its output

**Method.** DELTA50 (*Molecules* 2023, 28, 2449, CC-BY) — 46 compounds, 207
assigned ¹³C shifts, B3LYP/def2-SVP. Paired bootstrap resampled over
**molecules**, not atoms, because atoms of one molecule share a structure
and an assignment.

| strategy | MAE | selection accuracy | worst regret | vs shipped gate |
|---|---|---|---|---|
| `hard_gate` (was shipped) | 1.46 | 77.8% | 10.94 | — (refused 13/46) |
| **`warn_only`** (now shipped) | **1.33** | **80.2%** | **6.39** | −0.131 [−0.308, −0.017] |
| `per_molecule_error` | 1.34 | 74.9% | 6.39 | not distinguishable |
| `lookup_only` | 2.33 | 72.0% | 30.95 | worse |
| `orca_only` | 2.68 | 28.0% | 7.85 | worse |

**Selection accuracy and regret judge the rule rather than the predictors.**
For every atom both predictions *and* the truth are known, so it is knowable
whether the rule picked the closer source. A rule can lower MAE purely
because the calculation happened to be good while still choosing badly —
regret catches that and MAE does not.

Confirmed on 14 held-out molecules the strategies never influenced, and
repeated at wB97X-D3/def2-SVP, where the gate fires only 3 times in 42 and
removing it is *not distinguishable* rather than better — never worse.

→ [`benchmarks/nmr/`](../benchmarks/nmr/)

---

## Docking — redocking the crystallographic ligand

**Method.** Each curated receptor's own bound ligand is extracted, re-docked
into the box derived from it, and the **centroid displacement** measured.
Centroid rather than symmetry-corrected RMSD deliberately: RMSD needs an
atom correspondence this does not have, and the question being asked is
"did it find the right pocket", which a centroid answers.

| PDB | ligand | affinity | centroid shift | target |
|---|---|---|---|---|
| 1HSG | MK1 | −10.5 | **0.18 Å** | indinavir / HIV-1 protease |
| 2RH1 | CAU | −10.1 | **0.35 Å** | carazolol / β2-adrenergic |
| 1ERE | EST | −10.8 | **0.49 Å** | estradiol / estrogen receptor α |
| 8ZYO | XB7 | −12.3 | **0.53 Å** | astemizole / hERG |
| 4DKL | BF0 | −8.4 | **0.71 Å** | β-FNA / μ-opioid |
| 4EY7 | E20 | −11.1 | **0.73 Å** | donepezil / acetylcholinesterase |
| 3EML | ZMA | −8.9 | 3.90 Å | ZM241385 / adenosine A2A |

The 3EML row is reported rather than hidden: a ligand can move several Å
within the same pocket and still score well, and the number is more useful
visible than tidied away.

**What this does not measure:** whether Vina's affinities correspond to real
binding free energies. They do not, and no redocking experiment can show
that.

→ [`benchmarks/docking/`](../benchmarks/docking/)

---

## ADMET — and the confound that had to be found first

The ADMET panels were checked for whether their apparent discrimination
means anything. For hERG, it largely did not: the model's separation
**correlated with molecular size at r = +0.98**, which is worse than no
finding, because it looks like a result.

A size-matched panel of 19 compounds was built specifically to break that.
Even there, r(prediction, size) = +0.82 and r(prediction, logP) = +0.75.

This is why the rule-based **hERG risk-factor checklist ships alongside the
model and is labelled "not a prediction"** — it is honest about being a list
of structural correlates, which is what the evidence supports.

→ [`benchmarks/docking/README.md`](../benchmarks/docking/README.md)

---

## Measured, and deliberately not shipped

The most load-bearing results here.

**A trained NMR shift model.** Boosted trees over HOSE codes plus RDKit atom
features, aimed squarely at the 10.00 ppm `rough` band. Held-out MAE moved
2.98 → 2.91 with a confidence interval spanning zero: **not
distinguishable**. It did not ship. What *did* come out of that work was a
real improvement found along the way — splitting the index on explicit
hydrogens — which shipped instead.

**Miller polarizability.** The parameters are unpublished. A reconstruction
missed benzene by +27% and CCl₄ by −50%, so there was nothing to validate
against.

**HLB.** No formulas published, no worked example, and the reference
implementation's default is a proprietary consensus method. Nothing to check
a result against.

**The TSEI steric index.** Several incompatible definitions in the
literature and no reference value to gate against. Shipped omitted rather
than guessed. The Szeged index, from the same batch, *did* ship — because it
could be validated against a theorem.

**Missing-residue repair.** Spiked with PDBFixer, measured, and rejected:
the rebuilt geometry is not trustworthy near a binding site, which is
precisely where docking would use it.

**The quinine conformer hypothesis** — that a single MMFF conformer was
responsible for the hybrid's refusal — was tested with Boltzmann averaging
and **refuted**: MAE moved 4.30 → 4.27 ppm. Recorded so it is not
re-proposed.

---

## Reproducing any of this

Each benchmark directory has its own README with the exact commands. Nothing
here depends on data that is not either in the repository or downloadable by
the scripts.
