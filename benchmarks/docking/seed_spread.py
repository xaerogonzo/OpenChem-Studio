"""How far a Vina score moves when NOTHING changes but the seed.

This characterises the rule `domain/affinity_range.py` ships. It measures, per
(receptor, ligand):

    the WIDTH of the score range at n = 3, 5 and 10 runs, and how it grows
    the GAP between two ligands of the same receptor, at matched n
    the shipped `compare()` verdict for that pair, at each n

WHAT THIS BENCHMARK IS NOT FOR
------------------------------

**It does not supply a threshold, and the obvious next move after reading it
is the one thing that must not happen.** A reader who sees "the width is about
0.1 kcal/mol" will want to compile that in as a noise floor and call two
ligands different when they differ by more. That is the fitted constant the
whole design refuses: the shipped gate takes two replicate COUNTS and nothing
else, so there is no threshold in the units of the data for anybody to tune,
and `test_no_kcal_literal_lives_in_the_module` fails if one appears.

Equally: if the spread measured here differs from what somebody else reports,
that is a DOCS finding. It is not a reason to move `DEFAULT_REPLICATES` or
`SEPARATION_ALPHA`, which come from `2/comb(n_a+n_b, n_a)` and never from a
measurement.

**A WIDTH GROWS WITH n IN EXPECTATION**, which is why every figure below is
labelled with its count and why widths at different n must never be compared.
That growth is the most important table this script prints.

WHERE THE MOLECULES COME FROM, AND WHY NOT ONE SMILES IS TYPED
--------------------------------------------------------------

Every ligand is a DEPOSITED one, fetched by its PDB chemical-component code.
This project has already recorded a benchmark whose story changed when two
from-memory SMILES were replaced by the corpus's own -- an ibuprofen that
"showed Loose over-counting" and an ethylmorphine that did not parse. So each
receptor is paired with its OWN deposited ligand and with the deposited ligand
of a SIBLING ENTRY IN THE SAME FAMILY, both real ligands of that receptor:

    5C1M  mu-opioid       BU72 (own)         vs  fentanyl (from 8EF5)
    6WGT  5-HT2A          LSD (own)          vs  ergotamine (from 4IAR)
    2RH1  beta-2          carazolol (own)    vs  BI-167107 (from 3SN6)
    3PBL  dopamine D3     eticlopride (own)  vs  nemonapride (from 5WIU)

5C1M with fentanyl is the case this whole feature was reported from: three
fentanyl analogues at -8.88 / -8.79 / -8.75, a spread of 0.13 across three
different molecules against a same-molecule seed spread of 0.06.

**ALL FOUR ARE GPCRs, AND THAT IS A LIMIT RATHER THAN A CHOICE.** The
family-sibling rule is what removes typed SMILES, and the receptor library's
only multi-deposit families are GPCRs -- there is no second acetylcholinesterase
or HIV-protease entry to take a second ligand from. So this says nothing about
how the spread behaves on a soluble enzyme with a buried pocket. Fixing that
means either a second deposit per family or accepting a typed SMILES, and the
second is what this docstring exists to avoid.

WHAT IS HELD IDENTICAL
----------------------

    receptor PDBQT   built ONCE per target and reused by both ligands and by
                     every seed -- byte-identical, not merely equivalent, and
                     its sha256 is printed as a setup assertion.
                     **THAT SHA IS EVIDENCE ABOUT ONE RUN AND IS NOT A
                     REPRODUCIBILITY FINGERPRINT.** Measured while writing
                     this: three preparations of 5C1M in ONE process give
                     three different sha256 at identical byte length --
                     80 of 3794 lines differ and every one is an added
                     polar HYDROGEN on a rotatable group (Arg guanidinium,
                     and friends). Open Babel places those at a rotamer it
                     does not fix, so the receptor handed to Vina is not
                     reproducible even though the heavy atoms are
    ligand PDBQT     embedded ONCE per ligand and reused by every seed, so the
                     3D input does not vary between replicates. A fresh embed
                     per run would measure the embedder and the search at once
    box              derived from the receptor's own deposited ligand
    exhaustiveness   identical
    seed             the ONLY thing that varies

RECEPTORS COME FROM THE CACHE, NEVER THE NETWORK, for the reason
`OPENCHEM_DRIVE`'s receptor step gives: a measurement that depends on RCSB
being up is not a measurement. Populate it once through File > Receptor
Library. The ligand SMILES are fetched by component code and then CACHED to
the data root, so only the first run needs the network at all.

    uv run --no-sync python benchmarks/docking/seed_spread.py
    uv run --no-sync python benchmarks/docking/seed_spread.py --targets 5C1M --seeds 3

MEASURED 2026-08-31, real Vina 1.2.7, exhaustiveness 25, 80 runs, ~26 min
========================================================================

**THE WIDTH GREW IN 8 OF 8 LIGANDS AND SHRANK IN NONE**, which is the effect
the count exists to make visible:

    ligand                        n=3     n=5    n=10    median at n=10
    5C1M  BU72                   0.00    0.00    0.02         -12.44
    5C1M  fentanyl               0.04    0.04    0.04          -8.73
    6WGT  LSD                    0.01    0.02    0.03          -9.82
    6WGT  ergotamine             0.04    0.04    0.08          -9.43
    2RH1  carazolol             0.01    0.03    0.05         -10.07
    2RH1  BI-167107              0.04    0.05    0.06         -10.15
    3PBL  eticlopride            0.04    0.04    0.05          -8.12
    3PBL  nemonapride            0.14    0.14    0.18          -7.46

The MEDIAN moved by at most 0.01 across the same range, which is the other
half of why the median is the representative: it is stable in n where the
width and the minimum are not.

**A FITTED NOISE FLOOR WOULD HAVE TO BE WRONG SOMEWHERE.** At n = 10 the
widths span 0.02 to 0.18 -- a factor of NINE across eight ligands of one
method on four receptors. A constant chosen from the middle of that is
too tight for nemonapride and far too loose for BU72. This is the
no-fitted-constant design measured rather than argued.

**THE COUNT DECIDES, NOT THE SIZE -- AND 5C1M IS THE PROOF.** BU72 and
fentanyl are 3.70 kcal/mol apart, roughly 90x the wider of their two widths,
and at 3 runs each the shipped `compare()` still returns NOT_ASSESSED:

    target   n   A median   B median    gap   widest   verdict
    5C1M     3    -12.44      -8.73    3.70     0.04   not_assessed
    5C1M     5    -12.44      -8.74    3.70     0.04   separated
    6WGT     3     -9.82      -9.44    0.39     0.04   not_assessed
    6WGT     5     -9.82      -9.44    0.39     0.04   separated
    2RH1     3    -10.08     -10.16    0.09     0.04   not_assessed
    2RH1     5    -10.08     -10.16    0.08     0.05   separated
    3PBL     3     -8.12      -7.46    0.65     0.14   not_assessed
    3PBL     5     -8.12      -7.46    0.66     0.14   separated

Four pairs, all four flipping at exactly n = 5 -- the first count above the
derived minimum of 4. Nothing about the gap enters that decision.

**2RH1 IS THE ROW TO READ TWICE, AND IT IS WHY THE RULE IS ONE-DIRECTIONAL.**
Carazolol and BI-167107 are 0.08 kcal/mol apart with widths of 0.05 and 0.06,
and the method calls them SEPARATED. That is a true statement about the
search: it told them apart more consistently than it disagreed with itself.
It is not a claim that they bind differently -- 0.08 kcal/mol is far below
anything a scoring function with a ~0.6 ranking correlation resolves. A
reader who takes "separated" as chemical evidence has made exactly the error
the panel's own wording is written against.

**AND THE MOTIVATING CASE IS SHARPER THAN THE ORIGINAL ESTIMATE.** Fentanyl
in 5C1M has a width of 0.04 over ten runs, where the report's three different
analogues spanned 0.13. So those three were about THREE times the
single-molecule width, not the "roughly twice" recorded from a three-seed
sample -- which is the sample-size effect this file is about, seen in the
figure that motivated it.

**PREP IS NOT WORTH CACHING.** Receptor preparation is 0.2-1.0 s and is paid
ONCE per receptor; a search is 6.1-37.8 s and is paid per run. Over a
ten-replicate sweep of two ligands the prep is under 2% of the total. The
cost that matters is ligand FLEXIBILITY: ergotamine at 43 heavy atoms takes
37.8 s per run against LSD's 6.1 s on the same receptor, so ten replicates of
a large ligand is six minutes rather than one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import statistics
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _config import vina_executable  # noqa: E402
from openbabel import pybel  # noqa: E402
from openchem import paths  # noqa: E402
from openchem.chem.binding_site import box_from_ligand  # noqa: E402
from openchem.chem.docking_providers import VinaDockingProvider  # noqa: E402
from openchem.chem.receptor_library import find  # noqa: E402
from openchem.chem.vina_engine import ExecutableVinaEngine, parse_vina_output_pdbqt  # noqa: E402
from openchem.domain.affinity_range import (  # noqa: E402
    MIN_REPLICATES_FOR_SEPARATION,
    AffinityRange,
    compare,
    separation_p_value,
)
from openchem.services.progress import ProgressHandle  # noqa: E402
from rdkit import Chem  # noqa: E402
from rdkit.Chem import AllChem  # noqa: E402

CACHE = paths.data_root() / "receptors"
SMILES_CACHE = paths.data_root() / "benchmark_component_smiles.json"
EXHAUSTIVENESS = 25
PREP = {"strip_waters": True, "strip_cofactors": True}
PH = 7.4

#: Ten distinct seeds, read as NESTED PREFIXES at n = 3, 5 and 10.
#:
#: Nested rather than three separate sweeps: 80 runs instead of 144, and the
#: three figures are then subsets of ONE sample rather than three independent
#: ones -- so "the width grew" is a statement about the same runs seen further,
#: which is what the growth question means.
SEEDS = [11, 22, 33, 44, 55, 66, 77, 88, 99, 111]
COUNTS = (3, 5, 10)

#: (receptor, its own ligand, a sibling's ligand, where the sibling came from).
#: The fourth column is recorded so the provenance of every molecule is on the
#: page rather than in a lookup.
TARGETS = [
    ("5C1M", "VF1", "7V7", "8EF5"),
    ("6WGT", "7LD", "ERM", "4IAR"),
    ("2RH1", "CAU", "P0G", "3SN6"),
    ("3PBL", "ETQ", "AQD", "5WIU"),
]


def component_smiles(code: str) -> str:
    """The deposited SMILES for a PDB chemical component, cached to disk.

    The receptors already come from a local cache; caching these too is what
    makes a re-run fully offline, so a figure can be reproduced without RCSB.
    """
    cached = json.loads(SMILES_CACHE.read_text()) if SMILES_CACHE.exists() else {}
    if code in cached:
        return cached[code]

    from openchem.net import open_url

    data = json.loads(
        open_url(f"https://data.rcsb.org/rest/v1/core/chemcomp/{code}", timeout=45).read()
    )
    smiles = None
    for row in data.get("pdbx_chem_comp_descriptor", []) or []:
        if row.get("type") == "SMILES_CANONICAL":
            smiles = row.get("descriptor")
            break
    if not smiles:
        raise RuntimeError(f"RCSB returned no canonical SMILES for component {code}")
    cached[code] = smiles
    SMILES_CACHE.write_text(json.dumps(cached, indent=1), encoding="utf-8")
    return smiles


def embed(smiles: str):
    """One conformer, one fixed embedding seed.

    The SAME molecule object feeds every replicate, so the only thing varying
    across a sweep is Vina's own seed. Re-embedding per run would fold the
    embedder's randomness into a number reported as the search's.
    """
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    if AllChem.EmbedMolecule(mol, randomSeed=0xC0FFEE) != 0:
        raise RuntimeError("would not embed")
    AllChem.MMFFOptimizeMolecule(mol)
    return mol


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed-to-seed spread of a Vina score.")
    parser.add_argument("--targets", nargs="+", default=None)
    parser.add_argument("--seeds", type=int, default=len(SEEDS))
    args = parser.parse_args()

    seeds = SEEDS[: args.seeds]
    counts = tuple(n for n in COUNTS if n <= len(seeds)) or (len(seeds),)
    targets = [t for t in TARGETS if args.targets is None or t[0] in args.targets]

    # SETUP ASSERTIONS BEFORE ANY DOCKING. `ligand_ph_ab.py` is the precedent:
    # two arms that turned out identical would produce a perfect null and read
    # as evidence. Seeds that accidentally coincided would give a zero spread
    # that reads as a finding about the molecule.
    assert len(set(seeds)) == len(seeds), "the seeds are not distinct"
    print(f"setup: {len(set(seeds))} distinct seeds, exhaustiveness {EXHAUSTIVENESS}, pH {PH}")
    print(f"setup: separation needs {MIN_REPLICATES_FOR_SEPARATION} runs each; "
          f"p at n=3 is {separation_p_value(3, 3):.3f}, at n=10 {separation_p_value(10, 10):.2g}")

    engine = ExecutableVinaEngine(vina_executable())
    provider = VinaDockingProvider(engine=engine)
    rows: dict[tuple[str, str], list[float]] = {}
    timings: dict[str, tuple[float, float]] = {}

    for pdb_id, own_code, sibling_code, sibling_from in targets:
        entry = find(pdb_id)
        structure = (CACHE / f"{pdb_id}.pdb").read_text(encoding="utf-8")
        site = box_from_ligand(structure, "pdb", entry.ligand_code)

        with tempfile.TemporaryDirectory() as scratch:
            s = pathlib.Path(scratch)
            receptor = s / "receptor.pdbqt"
            started = time.monotonic()
            provider._convert_receptor_to_pdbqt(
                pybel, structure, "pdb", receptor,
                {**PREP, "strip_ligand_codes": (entry.ligand_code,)}, PH,
            )
            prep_seconds = time.monotonic() - started
            digest = hashlib.sha256(receptor.read_bytes()).hexdigest()[:16]
            # ONE receptor file for both ligands: the between-ligand gap must
            # not carry any receptor-preparation difference.
            print(f"\n[{pdb_id}] receptor pdbqt sha {digest}  prep {prep_seconds:.1f}s  "
                  f"box {tuple(round(v, 2) for v in site.box.center)}")

            ligands = {}
            for label, code, source in (
                (f"{own_code} (own)", own_code, pdb_id),
                (f"{sibling_code} (from {sibling_from})", sibling_code, sibling_from),
            ):
                mol = embed(component_smiles(code))
                path = s / f"{code}.pdbqt"
                provider._convert_ligand_to_pdbqt(pybel, mol, path, PH)
                ligands[label] = path
                heavy = mol.GetNumHeavyAtoms()
                print(f"[{pdb_id}] {label:<28} {heavy:>3} heavy atoms, "
                      f"deposited in {source}")

            # SETUP ASSERTION: the two ligands really are different molecules.
            # Two arms that turned out to be one would give a gap of zero and
            # read as "indistinguishable" rather than as a broken fixture.
            texts = [p.read_bytes() for p in ligands.values()]
            assert texts[0] != texts[1], f"{pdb_id}: the two ligands are the same file"

            for label, path in ligands.items():
                values = []
                search_seconds = 0.0
                for seed in seeds:
                    started = time.monotonic()
                    out = engine.dock(
                        receptor_pdbqt=receptor, ligand_pdbqt=path, box=site.box,
                        num_poses=9, exhaustiveness=EXHAUSTIVENESS, seed=seed,
                        progress=ProgressHandle(),
                    )
                    search_seconds += time.monotonic() - started
                    values.append(parse_vina_output_pdbqt(out)[0].binding_affinity_kcal_mol)
                rows[(pdb_id, label)] = values
                timings[f"{pdb_id} {label}"] = (prep_seconds, search_seconds / len(seeds))
                print(f"[{pdb_id}] {label:<28} " + " ".join(f"{v:6.2f}" for v in values))

    # -- how a width grows with n ------------------------------------------
    print("\n\nWIDTH BY REPLICATE COUNT -- the table nobody may read across")
    print("A width measured over more runs is larger IN EXPECTATION, so two")
    print("widths at different n are not comparable. This is that effect.\n")
    header = "".join(f"{'n=%d w' % n:>9}{'med':>8}" for n in counts)
    print(f"{'target / ligand':<44}{header}")
    print("-" * (44 + len(header)))
    for (pdb_id, label), values in rows.items():
        cells = []
        for n in counts:
            spread = AffinityRange(tuple(values[:n]))
            cells.append(f"{spread.width:9.2f}{spread.median:8.2f}")
        print(f"{pdb_id + ' ' + label:<44} " + "".join(cells))

    # -- the gap against the width -----------------------------------------
    print("\n\nBETWEEN-LIGAND GAP AGAINST WITHIN-LIGAND WIDTH, at matched n")
    print("And the SHIPPED verdict, so the rule is exercised on real Vina")
    print("output rather than on fixtures.\n")
    print(f"{'target':<8} {'n':>3} {'A median':>9} {'B median':>9} {'gap':>7} "
          f"{'widest':>7}   verdict")
    print("-" * 72)
    for pdb_id, *_rest in targets:
        pair = [(label, values) for (p, label), values in rows.items() if p == pdb_id]
        if len(pair) != 2:
            continue
        (_a_label, a_values), (_b_label, b_values) = pair
        for n in counts:
            a = AffinityRange(tuple(a_values[:n]))
            b = AffinityRange(tuple(b_values[:n]))
            gap = abs(a.median - b.median)
            widest = max(a.width, b.width)
            print(f"{pdb_id:<8} {n:>3} {a.median:>9.2f} {b.median:>9.2f} {gap:>7.2f} "
                  f"{widest:>7.2f}   {compare(a, b).value}")

    # -- what it cost -------------------------------------------------------
    print("\n\nPREP AGAINST SEARCH -- what a cached receptor would be worth\n")
    print(f"{'target / ligand':<44} {'prep':>8} {'search/run':>12}")
    print("-" * 66)
    for name, (prep_seconds, per_run) in timings.items():
        print(f"{name:<44} {prep_seconds:>7.1f}s {per_run:>11.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
