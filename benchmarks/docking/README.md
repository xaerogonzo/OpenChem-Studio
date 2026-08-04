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
