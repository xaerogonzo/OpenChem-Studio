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
