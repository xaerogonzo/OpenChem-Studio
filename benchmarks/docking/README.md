# Docking benchmarks

Two scripts, answering two different questions about the receptor
catalogue (`src/openchem/chem/receptor_library.py`). Both need network
access on a first run and both cache structures, so a second run is fast.

## `verify_catalog.py` — does every entry still work?

Downloads all 49 catalogued structures and confirms each one's
`ligand_code` resolves to a real binding site. **An entry whose code
matches nothing is dead**: the user picks a target and the box derivation
raises. Run this after editing the catalogue.

```bash
uv run --no-sync python benchmarks/docking/verify_catalog.py
```

Expect `49/49 entries produced a box`.

It also prints each site's atom count, which is the cheap sanity check:
the counts match the ligands' known formulas exactly — indinavir 45,
donepezil 28, diazepam 20, ergotamine 43, GABA 7, fentanyl 25. A count
that suddenly disagrees with the formula means either the wrong component
was named or copies are being merged.

**This is how two real bugs were found.** Estradiol came back as 120
atoms rather than 20, because 1ERE holds six copies all numbered 600 and
distinguished only by chain — merging them produced a box centred in
solvent between them. Astemizole came back as 68 rather than 34, because
8ZYO models it in two alternate conformations and only the docking path
was filtering altlocs.

## `redock.py` — do the boxes actually produce right answers?

The real test. Takes each ligand's own SMILES from RCSB, discards the
crystal coordinates, docks it back through the derived box with real
Vina, and reports how far the pose lands from where crystallography put
it. Needs a configured Vina executable (edit `VINA` at the top).

```bash
uv run --no-sync python benchmarks/docking/redock.py
```

Measured against Vina 1.2.7:

| PDB | ligand | affinity | centroid shift | target |
|---|---|---|---|---|
| 1HSG | MK1 | −10.5 | **0.18 Å** | indinavir / HIV-1 protease |
| 2RH1 | CAU | −10.1 | **0.35 Å** | carazolol / β2-adrenergic |
| 1ERE | EST | −10.8 | **0.49 Å** | estradiol / estrogen receptor α |
| 8ZYO | XB7 | −12.3 | **0.53 Å** | astemizole / hERG |
| 4DKL | BF0 | −8.4 | **0.71 Å** | β-FNA / μ-opioid |
| 4EY7 | E20 | −11.1 | **0.73 Å** | donepezil / acetylcholinesterase |
| 3EML | ZMA | −8.9 | 3.90 Å | ZM241385 / adenosine A2A |

Six of seven inside 0.75 Å. The A2A row is reported rather than averaged
away: ZM241385 is long and roughly linear, so a pose flipped end-for-end
within the same pocket moves the centroid several Å while still scoring
well. That is Vina's pose ranking, not the box — the box put the ligand
in the right place.

Centroid displacement rather than a symmetry-corrected RMSD, deliberately:
RMSD needs an atom correspondence this does not have, and the question
being asked is "did it find the right pocket", which a centroid answers
and a good score cannot flatter.

**Both scripts must use the same single-copy selection the box uses.**
An earlier version of `redock.py` compared each pose against the combined
centroid of every copy and reported estradiol as 47 Å wrong when it was
0.49 Å right — the script's bug, not the code's, and a good illustration
of why the multi-copy handling needed its own tests.

## What this does not measure

Redocking checks that a setup finds a pocket it was aimed at. It does not
establish that Vina's affinities rank unrelated compounds correctly, and
nothing here claims otherwise. A separate spot-check against the μ-opioid
receptor did show the expected separation — naloxone −8.6, morphine −7.9,
fentanyl −9.1 against caffeine −5.4 as a negative control, with the
opioid poses contacting Asp147, His297, Trp293 and Tyr326 — but four
compounds against one target is an anecdote, not a benchmark.

## `dock_herg.py` / `herg_compare.py` / `herg_sizematched.py` — hERG

Three scripts around one question, and the order matters because each
undercuts the one before it.

`dock_herg.py` docks a blocker/non-blocker panel into 8ZYO. Astemizole —
the structure's own ligand — redocks to **0.53 Å** and contacts **Tyr652
in all four subunits**, the recognised structural signature of a pore
blocker. Blockers averaged −9.8 kcal/mol against −6.2 for non-blockers.

`herg_compare.py` then checks whether that separation means anything.
**It largely does not**: `r(heavy atoms, Vina affinity) = −0.91`, and
ligand efficiency reverses the ranking (0.335 for blockers, 0.569 for
non-blockers). The panel put every blocker among the large drugs. Vina
cannot rank these compounds on hERG liability, and this run is not
evidence that it can.

The same script found the ADMET model separating them almost perfectly —
and correlating with size at **r = +0.98**, which is worse, not better.
A model that had learnt only "big lipophilic molecules block hERG" scores
identically on such a panel.

`herg_sizematched.py` is the panel built to break that: 19 compounds,
large ones with no liability and small ones with real liability.

    accuracy at 0.5      15/19
    r(prediction, size)  +0.82      r(prediction, logP)  +0.75
    false alarms  atorvastatin 0.766  fexofenadine 0.698  cetirizine 0.552
    missed        sotalol      0.215

**The errors are the confound.** Every false alarm is large and
lipophilic without blocking; the one miss is small and hydrophilic and
does block — sotalol, whose therapeutic mechanism *is* hERG block.

The pair that settles whether there is any signal beyond size:

| | heavy | MW | logP | prediction |
|---|---|---|---|---|
| terfenadine (withdrawn) | 35 | 471.7 | 6.45 | **0.970** |
| fexofenadine (its safe metabolite) | 37 | 501.7 | 5.51 | **0.698** |

Fexofenadine is terfenadine's own carboxylic-acid metabolite, slightly
larger, same scaffold, and marketed precisely because terfenadine's hERG
block was fatal. A pure size model must score them alike; this one
separates them by 0.27 — real signal — while still putting fexofenadine
on the wrong side of 0.5.

These numbers are **not** comparable to ADMET-AI's published performance,
which is measured on TDC's held-out test set. This is a small,
deliberately adversarial probe for one failure mode.

## Configuring the tools

Nothing here hardcodes a path any more. `_config.py` reads Vina and the
ADMET interpreter from the **same Settings the application uses**, so a
benchmark measures what the app actually runs and anyone who set the
tools up through the UI can reproduce these tables without editing
source. A script exits with a clear message naming the UI page to visit
if a tool it needs is unconfigured.

## Reproducibility

The 19-compound panel was re-run against the configured sidecar and
returned all 19 probabilities identical to three decimals, so the model
is deterministic and these numbers are stable to compare against.

## `cyp_panel.py` — CYP450, and the test hERG could not offer

22 drugs, five inhibition isoforms each. CYP allows a sharper version of
the hERG question, because five predictions per molecule make it possible
to ask *which enzyme* rather than only *how strong*.

**The headline test needs no ground truth.** If the five isoform
predictions rose and fell together, the model would have learned "this
molecule interacts with CYPs" rather than which one — measurable purely
from its own outputs. They don't:

```
        1A2   2C19    2C9    2D6    3A4
1A2    1.00   0.37  -0.10   0.53   0.18
2C19   0.37   1.00   0.85   0.33   0.80
2C9   -0.10   0.85   1.00   0.06   0.77
2D6    0.53   0.33   0.06   1.00   0.25
3A4    0.18   0.80   0.77   0.25   1.00
```

Mean off-diagonal **+0.40**, range −0.10 to +0.85. Genuinely
isoform-specific. The three that do move together (2C19/2C9/3A4) are the
ones with overlapping substrate preferences, which is chemistry rather
than a defect.

**The confound that ruins hERG is largely absent:**

| | CYP | hERG |
|---|---|---|
| r(prediction, heavy atoms) | **+0.24** | +0.82 |
| r(prediction, logP) | **+0.54** | +0.75 |

The residual logP term is expected — lipophilicity really does drive CYP
binding.

**Selectivity: 8/11 ranked correctly** against ~2.2 by chance. Every azole
and macrolide → 3A4; quinidine, paroxetine, fluoxetine → 2D6;
fluvoxamine → 1A2. Inhibitors average 0.696 on their peak isoform against
0.071 for renally-cleared drugs.

**The real failure is detection, not ranking.** Two known inhibitors are
scored inactive on every isoform — clarithromycin **0.05**, ciprofloxacin
**0.03**. Clarithromycin is a textbook strong 3A4 inhibitor, and a
peak-isoform metric flatters it because 3A4 is still the highest of five
near-zero numbers. The script reports ranking and detection separately
for exactly this reason.

**So: distrust a low CYP score; a high one is well supported here.** That
is the opposite shape of failure from hERG, where high scores on large
lipophilic molecules are the weak ones.

One leak: quinidine's *substrate* prediction peaks on 2D6 (0.62) when it
is a 3A4 substrate that merely *inhibits* 2D6 — the inhibition and
substrate endpoints are not perfectly disentangled.

## `ames_panel.py` — the endpoint with a free alternative

hERG and CYP have no honest rule-based substitute, which is what justifies
a sidecar for them. **Ames is different.** Mutagenicity is where
structural alerts genuinely work — a mutagen usually is or becomes an
electrophile, and electrophiles have recognisable substructures. So the
question is not "is the model good" but "does it beat what the app
already has offline and instantly".

26 compounds (15 standard reference mutagens and Ames-positive drugs, 11
with clean records) against eight textbook alert classes plus a
fused-ring rule for PAHs.

| | TP | TN | FP | FN | accuracy |
|---|---|---|---|---|---|
| ADMET-AI model | 14 | 10 | 1 | 1 | **92%** |
| structural alerts | 14 | 10 | 1 | 1 | **92%** |

An exact tie — **but they fail on different compounds**, which is the
useful part. All four disagreements are instructive:

| compound | known | outcome |
|---|---|---|
| aflatoxin B1 | POS | **model right** — its electrophile is an epoxide formed *metabolically*, so no static alert can express it |
| procarbazine | POS | **alerts right** (hydrazine); model scored 0.40 |
| paracetamol | neg | **model right** — the N-aryl amide alert over-fires |
| sucrose | neg | **alerts right**; model scored 0.53 |

Complementary, not redundant. Combining them buys what neither has alone:

```
either flags it    sensitivity 100%   specificity  82%
both must agree    sensitivity  87%   specificity 100%
```

For a genotoxicity screen sensitivity is what matters — a missed mutagen
costs more than a compound needlessly re-tested — so **treat a hit from
either source as the screen**. The model earns its place by catching
metabolically-activated mutagens no substructure can express, not by
being better across the board.

**The alert patterns are verified, not asserted.** Ten match/no-match
checks run before the table and abort the script if any pattern
misbehaves — a plausible-looking SMARTS that quietly matches nothing
would make the model look good for the wrong reason.

Ames is also the cleanest of the three endpoints on the size confound:

| endpoint | r(prediction, heavy atoms) | r(prediction, logP) |
|---|---|---|
| hERG | +0.82 | +0.75 |
| CYP | +0.24 | +0.54 |
| **Ames** | **−0.14** | **+0.32** |

## `rescore_power.py` — what does the rescore column actually do?

The Route 2 companion to `redock.py`. Two arms, and the most important
thing about it is what it does **not** measure.

```bash
uv run --no-sync python benchmarks/docking/rescore_power.py --exhaustiveness 25
```

### Ranking power is NOT measured, and that is a data finding

Route 2's acceptance criterion is rank correlation against **measured
affinities**. Measured 2026-09-03, every route to such a set is closed from
this machine — the PDBbind hosts, the old plain-`wget` CASF-2016 tarball URL
that published evaluations still use, Binding MOAD (whose domain now serves a
commercial antibody catalogue), and Zenodo/figshare, which carry only other
people's preprocessed derivatives. RCSB's own `rcsb_binding_affinity` exists
but is sparse and assay-heterogeneous: **zero** records for 1HSG, 3EML and
2RH1, and **104** for 4EY7 spanning Kd 8 nM to IC50 7120 nM for one ligand.

A 4000-fold spread across assays is not a ranking oracle. The gap stays open
in `docs/ROADMAP.md` rather than this script carrying a proxy for it.

### What it does measure: docking power, with free ground truth

Every catalogued receptor is deposited *with* its ligand, so the crystal pose
costs nothing. That is CASF's docking-power protocol — score a set of
generated poses, ask whether the best-scored one is right — run through the
shipped `rescore_with` path, so it measures what a user actually gets.

Measured at exhaustiveness 25, seed 4712, 9 poses, rescoring with Vinardo:

    PDB   lig   poses  best possible  vina picks  rescore picks    rho
    1HSG  MK1       9         0.44 A      0.44 A         0.44 A   0.12
    4DKL  BF0       9         0.72 A      1.17 A         0.94 A   0.90
    3EML  ZMA       9         2.50 A      3.77 A         4.22 A   0.07
    2RH1  CAU       9         0.37 A      0.37 A         0.37 A   0.92
    1ERE  EST       4         0.31 A      0.48 A         0.48 A   1.00
    4EY7  E20       9         0.46 A      0.46 A         0.46 A   0.83
    8EF5  7V7       9         0.52 A      4.45 A         4.31 A   0.82
    5C1M  VF1       2         0.43 A      0.43 A         0.43 A   1.00

    vina      6/8 within 3.0 A   mean displacement 1.45 A
    rescore   6/8 within 3.0 A   mean displacement 1.46 A
    ceiling   8/8

**A NULL RESULT, AND IT SHIPS.** [source:quiroga2016] reports Vinardo
improving docking on the authors' datasets; on these eight receptors it
changes nothing detectable — 6/8 either way, means 1.45 against 1.46 Å. That
is not evidence the two are equivalent, and the script says so: eight targets
cannot separate functions differing by less than about one target.

**THE CEILING ROW IS WHERE THE INFORMATION IS.** The search found a pose
within 3 Å on **8 of 8**, so both of the misses are *scoring* failures rather
than search failures — 3EML's search reached 2.50 Å while the scores picked
3.77 and 4.22, and 8EF5's reached 0.52 Å while both picked ~4.4. Without that
column a bad row is unattributable, which is exactly the distinction CASF's
own decomposition exists to draw. (8EF5 is a 3.30 Å cryo-EM structure, so its
reference ligand position carries real uncertainty of its own.)

### The reordering arm needs no oracle

Spearman between the two orderings of the *same* poses: mean **+0.71**, range
**+0.07 to +1.00**, none negative. On 3EML and 1HSG the two functions order
the poses almost independently. That is the measurement the shipped UI's
refusal to re-rank rests on — it says the orderings differ, and deliberately
says nothing about which is better.

### Leakage: `TRAINING_PROVENANCE_UNRESOLVED`

Three-valued rather than clean/contaminated. [source:quiroga2016] §3.1 names
Vinardo's selection set exactly — 122 of the 195 PDBbind Core 2013 structures
— and Vina was trained on PDBbind 2007. Both are checkable in principle by
intersecting PDB codes, and neither list is obtainable from here for the same
reason CASF-2016 is not. So the overlap is **unknown, not absent**.

### Caveats that are not optional

- **Centroid displacement, not symmetry-corrected RMSD.** There is no atom
  correspondence to the deposited ligand here, so this is coarser than CASF's
  2 Å RMSD criterion and its numbers are not comparable to a published
  docking-power figure.
- **Self-docking.** Each ligand is redocked into its own co-crystal
  structure, which is the easy case; cross-docking is harder and not covered.
- **Pose counts vary.** Vina merges similar modes, so 5C1M returned 2 poses
  and 1ERE 4. A rho over two points is not a measurement.
