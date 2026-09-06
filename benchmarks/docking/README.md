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

### Ranking power is NOT measured HERE — and it is measurable now, next door

**SUPERSEDED IN ITS CONCLUSION, KEPT FOR ITS EVIDENCE.** Everything the
section below says about PDBbind, CASF-2016, Binding MOAD and
`rcsb_binding_affinity` is still true and still worth having: those routes are
closed and re-checking them is wasted time.

What was wrong was the inference drawn from it — that ranking power is
therefore unmeasurable here. `docs/ROADMAP.md` named the reopener in the same
breath ("a curated affinity set assembled from BindingDB/ChEMBL for targets
already in the library"), and **ChEMBL is reachable with no account**:
ChEMBL_37, 24.5M activities, and 21 of the 23 catalogued receptors sampled
reach a target carrying `=`-relation Ki values with a pChEMBL.

The decisive difference is that ChEMBL carries `assay_chembl_id`, so a series
can be confined to **one assay** — which is exactly what
`rcsb_binding_affinity` could not do, and exactly why its 4000-fold spread
made it useless. See `chembl_corpus.py` and the Within-Assay Docking Ranking
Benchmark below.

### The closed routes, as measured 2026-09-03

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

## The Within-Assay Docking Ranking Benchmark — route 2's acceptance

`chembl_corpus.py` → `rank_power.py` → `rank_report.py`. Three stages, each
leaving standalone evidence, and only the middle one costs Vina time.

```bash
uv run --no-sync python benchmarks/docking/chembl_corpus.py
uv run --no-sync python benchmarks/docking/chembl_corpus.py --presence
uv run --no-sync python benchmarks/docking/rank_power.py --all
uv run --no-sync python benchmarks/docking/rank_report.py
```

**IT IS NOT CASF, AND THE NAME IS LOAD-BEARING.** CASF-2016 decouples scoring
from docking over 285 complexes and 57 targets. This ranks compounds measured
in ONE assay against poses this application generated. Its rho is not
[source:su2019]'s pooled ~0.6 or [source:nguyen2020]'s 0.498 ± 0.026 — a
different quantity on a harder question, which `rank_report.py` prints rather
than trusting a reader to remember.

### What the corpus is

Measured 2026-09-05 against ChEMBL_37: **1586 single-assay series** over eight
catalogued receptors, **795 of them size-decoupled**, from 41,073 activities.

| target | family | activities | series |
| --- | --- | --- | --- |
| 3HS4 | carbonic anhydrase II | 11,050 | 408 |
| 3PBL | dopamine D3 | 8,253 | 286 |
| 3EML | adenosine A2A | 6,575 | 275 |
| 6WGT | 5-HT2A | 6,323 | 224 |
| 5TGZ | cannabinoid CB1 | 3,955 | 181 |
| 5I6X | serotonin transporter | 3,394 | 135 |
| 2RH1 | β2-adrenergic | 796 | 38 |
| 5C1M | μ-opioid (**mouse**) | 727 | 39 |

Eight targets across eight families, because eight from one family would
measure one pocket eight times. 5C1M earns its place on evidence: it is the
receptor the original ranking complaint was reported against.

### One assay is the whole point

`rcsb_binding_affinity` failed as an oracle because it mixes assays — 104
records for one 4EY7 ligand spanning Kd 8 nM to IC50 7120 nM. ChEMBL carries
`assay_chembl_id`, so a series can be confined to one assay, one endpoint and
one laboratory, and an ordering within it is a real ordering.

**Series size is DERIVED, not typed.** Under the null that the docking order is
unrelated to the measured one, all n! orderings are equally likely and two are
perfect — one per direction, since the benchmark does not fix the direction in
advance. So the two-sided rate of the extreme outcome is 2/n!, and the minimum
is the smallest n clearing `SEPARATION_ALPHA`: **n = 5**, where n = 4 gives
0.083. The alpha is imported from `domain/affinity_range.py` so the corpus and
the shipped separation rule cannot drift apart.

**The potency span is reported and never used to admit.** A minimum span would
be a constant somebody fitted. The only gate is that at least two potencies
differ, which is definedness — Spearman is undefined otherwise.

### The join is pinned; SIFTS is the verifier

A UniProt accession is not a construct. **Four of the eight deposits carry a
second accession for their crystallisation fusion** — T4 lysozyme (P00720) in
3PBL, 2RH1 and 3EML, cytochrome b562 (P0ABE7) in 6WGT, flavodoxin (P00323) in
5TGZ — and each has ChEMBL targets of its own, so "take the accession with the
most activities" can return a chaperone's affinity data as the receptor's.

So `JOIN` is a table with a reason per row, and `verify_join` **fails on
disagreement** rather than resolving anything. Three cases that otherwise fail
by returning silence rather than an error:

- **5C1M is mouse.** P42866 is mouse μ-opioid and so is CHEMBL2858, which
  carries 727 Ki values of its own — so the exact-organism rule is what the
  data supports, not a principle imposed on it. No ortholog fallback is
  implemented rather than written and left unreachable.
- **4M48 is *Drosophila*.** Q7K4Y6 reaches no ChEMBL target at all.
- **COX-2 has 27 Ki values**, because that endpoint is measured as IC50. A
  Ki-only rule silently refuses an enzyme class.

### The receptor preparation differs from every other benchmark here

    {"strip_waters": True, "strip_cofactors": False,
     "strip_ligand_codes": (entry.ligand_code,)}

`redock.py`, `rescore_power.py` and `seed_spread.py` all pass
`strip_cofactors: True`, which `is_stripped_residue` resolves to "delete every
non-standard residue" — taking **carbonic anhydrase II's catalytic zinc**, the
binding determinant for the sulfonamide series that is 3HS4's entire reason for
being here. Both halves are asserted before any search, because a blocked
pocket or a stripped cofactor compresses every score toward a constant and
still yields a plausible correlation.

**A PDBQT IS NOT A PDB**, and reading it as one made the metal check return 0
on a receptor whose zinc was present: the element is not at columns 77–78, the
AutoDock type is the last token. Measured on 3HS4, the distinct trailing tokens
across the file are exactly `A C HD N NA OA S Zn`.

### The receptor is prepared once per series

Receptor preparation is **not reproducible** — three preparations of 5C1M gave
three sha256s, 80 of 3794 lines differing on polar-hydrogen rotamers. Harmless
for one ligand; ruinous across a series, where two ligands would be scored
against two different receptor files in exactly the dimension being measured.

### Seeds are derived per ligand

`domain/affinity_range.py` makes it a precondition: two ligands sharing a
replicate seed make their values arrive as correlated pairs. Derived by
SHA-256, never `hash()`, which is randomised per process — this project shipped
that bug once already, in `protonate_at_ph`.

### Six replicates, and the split is fixed in advance

`_stats.REPLICATE_HALVES` is `((0,1,2), (3,4,5))`. Six rather than five so the
halves are **even**: two aggregates over different counts are not comparable.
Six also clears the derived minimum of four.

**`rho(half A, half B)` is SEARCH REPEATABILITY, not a noise ceiling.** It says
how consistently the search orders the same ligands under this protocol; it
does not bound the attainable correlation with experiment. The oracle's own
reproducibility is unmeasurable here — ChEMBL carries no per-row uncertainty —
so the docking's is measured and the oracle's is not.

### Baselines, computed free at corpus-build time

`rho(heavy_atoms, pChEMBL)`, MW, cLogP, TPSA, plus `rho(-vina, heavy_atoms)`
and the random floor `1/sqrt(n-1)`. This project has shipped an endpoint that
turned out to be molecular size (r = +0.98); a docking score that ranks no
better than heavy-atom count is not ranking.

**A series whose potency already tracks size cannot discriminate**, so the
control is present and can never fire there. `is_size_decoupled` selects the
ones where it can — and `None` counts as decoupled rather than as missing:
`5C1M_CHEMBL758126` is six compounds identical in heavy atoms, MW, cLogP *and*
TPSA across a 1.99-log potency span, an isomer series where only geometry can
be the answer.

### The selection is frozen before any docking

**Fifteen series, 194 ligands, 1164 searches** at six replicates, over all
eight targets. Chosen by a declared rule: size-decoupled, 5 ≤ n ≤ 14, **every
ligand fits the box**, the largest two per target, ties by id. **Sorted by
ligand count and not by potency span**: a wide span is easier to rank, so
selecting on it would flatter every number that follows, where the count
selects for statistical power.

This is a **curated benchmark, not a random sample**, and the manifest says so.

#### The fit requirement was added after v1 was frozen, and that is recorded

v1 required only size-decoupling and the size band, and Stage 1 was started on
it. Its own timings said the cost model was wrong by thirty-fold — **243 s mean
per search against the 7 s measured on the smoke test**, projecting 80 hours
rather than 2.6.

The cause was the ligands, not the receptor, and the comparison is controlled:
`5C1M_CHEMBL759051` and `5C1M_CHEMBL2209608` share a target, a box and a
protocol and differ **nineteen-fold in cost** — 379 s against 20 s — at 31
against 7 maximum rotatable bonds. The expensive series was also the one whose
ligands do not fit: 14 of 14 over the box, against 4 of 13.

So two problems coincide and only one is about money. **A ligand longer than
the box's shortest side has whole orientations excluded from the search**,
which is the monotone-in-size artefact the baselines exist to catch, so a
series where every ligand overflows ranks artefacts. Every box here clamps to
`MINIMUM_SIZE`, 16 Å, against ligand extents reaching 32.4 Å.

**The amendment is admissible because box fit is computed from ligand geometry
and the catalogue box alone** — no docking score exists for it, and none had
been looked at. Same discipline as `benchmarks/free_energy/AMMONIA.md`, which
amended a preregistration openly before any outcome existed. The manifest
carries the amendment and its reasoning in `docking_selection_rule_amendment`;
quietly re-freezing would have been the wrong move.

**32 of 47 candidate series examined were rejected on box fit** — so two thirds
of otherwise-eligible single-assay series contain a ligand the catalogue's own
box cannot hold. The survivors span 9.4–15.6 Å against 16.0–16.8 Å boxes, with
4–8 rotatable bonds. A target with no fully-fitting candidate is excluded and
named rather than represented by its least-bad series; 2RH1 yielded one series
rather than two.

### The leakage bound, worded narrowly

Every PDBbind entry is a co-crystallised complex, so a compound that is **no
PDB chemical component** cannot be in Vina's training set or Vinardo's
selection set. That is a sufficient exclusion under exact-InChIKey identity —
a **minimal** bound, not a leakage-free claim, since protonation, tautomer,
salt and stereo representation all break exact identity, and similarity leakage
is not addressed at all. One-way: absence is sufficient, **presence implies
nothing**, because a compound can be in the PDB bound to a protein PDBbind
never included.

**RCSB answers a zero-hit search with HTTP 204 and an empty body**, so
`json.loads` raises and a blanket except reads "not in the PDB" as a failure —
folding absence and inability together and biasing the split optimistic. Hence
three values, and three fixtures: a hit, a real absence, and a fault. A
two-fixture test is satisfied by both of the mutations it exists to catch.

**And the layer that SUMMARISES it made exactly that mistake.**
`rank_report.py` read a compound with no cache entry as one that had been
checked and found absent, and announced *"no compound in this corpus has an
exact PDB chemical-component match"* on 125 of 194 compounds it had never
looked up — the cache having been built for the v1 selection. `NOT_LOOKED_UP`
is its own counted verdict now. Being careful one layer down does not make the
layer above careful.

#### THE PRE-COMMITMENT FOR CLOSING IT, RECORDED BEFORE THE LOOKUP RAN

442 of the 638 compound-series entries were never looked up, so the three
verdicts **are not a split** and `rank_report.py` refuses to present them as
one. Closing that costs one cached HTTP call per InChIKey and no Vina time.

**The ABSENT-only median will be reported whatever it says.** It is currently
unchanged against the full set on the 191 entries that were checked, and 442
more can move it. This is written here, in a committed file, rather than in
`data/manifest.json` — which is gitignored, so a pre-commitment recorded there
is not a record of anything.

The reason is this benchmark's own worst methodological moment, one section
down: an interim p-value crossed 0.05 and came back, because the report was run
three times while the data accumulated. **A number decided after seeing it is
not a result**, and the leakage arm is the one remaining place in this
benchmark where that mistake is still available.

Nothing about the corpus, the selection or the docking changes — the lookup
reads the cached corpus and rewrites no manifest, deliberately, so it cannot
re-freeze a selection underneath a measurement.

### The result: 3828 searches, 14.5 hours, and it is a NULL

**The full record, with the per-series table for all 56 series, is
`docs/DOCKING_RANKING_BENCHMARK.md`.** The raw JSONL is gitignored, so that
table is the only committed form of the run.

Measured 2026-09-05/06 over the frozen 56-series selection. 624 distinct
ligands, six replicates each, exhaustiveness 25, mean 13.7 s per search.

| | |
| --- | --- |
| median ρ(−vina, pChEMBL) | **+0.082**, 95% series bootstrap **[−0.030, +0.245]** |
| series with ρ > 0 | 32/56, sign test **p = 0.350** two-sided |
| median ρ(Vinardo) − ρ(Vina) | **+0.000**, 95% **[−0.104, +0.082]** |
| series where Vinardo ranks higher | 27/56 |
| series beating every trivial baseline | **9/56** |
| series with ρ above **twice** its own random floor | **1/56** |
| search repeatability | median **+0.990**, 55/56 ≥ +0.95 |
| ligand pairs reordered between replicate halves | **60 of 3462 (1.7%)** |
| leakage | 191 ABSENT, 5 PRESENT, 442 NOT_LOOKED_UP |

**THIS IS N5 FROM THE ROADMAP'S OWN LIST — THE CLEANEST NEGATIVE THE DESIGN
ALLOWS.** The search is very nearly deterministic in its ordering: a median
repeatability of +0.990, and **1.7% of ligand pairs swap** between independent
replicate halves. So the disagreement with measured potency is **not sampling
noise**, and no amount of extra exhaustiveness addresses it. It is the scoring
function — which is what [source:su2019] says about ranking power, now measured
here on this application's own poses rather than cited.

**Vinardo does not improve on Vina** (N2). The delta's median is exactly
+0.000 and 27 of 56 is what a coin gives. The two disagree strongly on
individual series — `3HS4_CHEMBL2045715` +0.33 → +0.70, `5I6X_CHEMBL5042437`
−0.07 → −0.75 — so the second column buys ordering *diversity*, not accuracy.
That is the measured version of the rescoring axis's own no-re-ranking rule.

**Only 9 of 56 series beat every trivial physicochemical baseline**, so on 47
of them heavy-atom count, molecular weight or cLogP orders the compounds at
least as well as docking does. That is N1, the outcome the roadmap calls the
most valuable, at 84%.

#### THE P-VALUE MOVED WITH EVERY LOOK, AND THAT IS THE METHODOLOGICAL FINDING

Recorded because the interim numbers were nearly written up as a result:

    15 series (first frozen selection)   11/15   p = 0.118
    28 series (widening in flight)       19/28   p = 0.087
    37 series (widening in flight)       25/37   p = 0.047   <-- crossed 0.05
    56 series (PRE-COMMITTED ENDPOINT)   32/56   p = 0.350

**A p-value inspected repeatedly as data accumulates is not a p-value.** At 37
series this benchmark said "significant" on a dataset whose completed form says
nothing of the kind. Nothing in the arithmetic was wrong at any step; the
inspection schedule was. `rank_report.py` prints a PARTIAL banner whenever the
complete count is short of the frozen selection, because the script cannot know
who is running it or for the how-many-th time, and the interim value that
happens to sit across a conventional threshold is exactly the one that gets
quoted.

#### THE FIRST FIFTEEN AGAINST THE OTHER FORTY-ONE, AND WHY THEY ARE NOT COMPARABLE

    first selection      median rho +0.245  (n = 15)  95% [-0.030, +0.398]
                         ligands/series 13, span 2.26, floor SD 0.289
    added by widening    median rho +0.006  (n = 41)  95% [-0.071, +0.200]
                         ligands/series 12, span 1.95, floor SD 0.302

The selection walk takes the largest series first, so **the added series are
smaller and lower-span by construction** — noisier instruments with a higher
random floor. A lower median among them is partly an artefact of that, not
necessarily a weaker effect, and the two groups are **not exchangeable**. The
split is printed anyway, with that caveat attached, because it is the only way
to see whether widening changed the answer or merely sharpened it.

**It changed it.** The first fifteen sat at +0.245 with an interval that
*almost* excluded zero; the full set sits at +0.082 with one that comfortably
includes it. Widening a corpus after seeing a marginal result is the right
response to a marginal result, and this is what it is for.

#### WHAT THIS DOES NOT SAY

Not "docking cannot rank". One series reaches ρ = +0.79
(`5I6X_CHEMBL1645847`) and another +0.75 (`5I6X_CHEMBL808864`); 22 of 56 exceed
their own random floor in absolute value, which is about what 56 draws from a
null would give. The claim is **no ranking ability detectable across
within-assay congeneric series at this n**, on eight targets, with Vina at
exhaustiveness 25.

The oracle's own reproducibility is unmeasurable here — ChEMBL carries no
per-row uncertainty — so ρ is bounded above by a quantity nobody can measure,
while the docking's own repeatability is measured and is essentially 1. That
asymmetry is in `docs/SCIENTIFIC_LIMITATIONS.md`.

**442 of 638 compound-series entries were never looked up** against the PDB, so
the leakage arms are not a split. Run `chembl_corpus.py --presence-only` to
close that; it costs one cached HTTP call per InChIKey and no Vina time. On the
191 that were checked, the ABSENT-only median is unchanged.

The corpus holds 1586 series; 56 were docked, which is 3.5%.
