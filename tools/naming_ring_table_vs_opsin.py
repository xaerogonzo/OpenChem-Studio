"""Check every curated ring's `atom_locants` against OPSIN's own numbering, two chlorines at a time, with no use of the namer.

    python tools/naming_ring_table_vs_opsin.py                 # every neutral entry, up to 120 pairs each
    python tools/naming_ring_table_vs_opsin.py --cap 40 --rings indole

**WHY IT EXISTS.** Rounds 82 and 85 each found a curated entry whose labels were wrong, and a chlorine at ONE position cannot see a swap of two
symmetric atoms: both orders name the same molecule. Two chlorines can. For every pair of labelled hydrogen-bearing atoms (i, j) the table says
which atoms carry `i,j-dichloro-<ring name>`; OPSIN reads that name with ITS numbering; the two must be the same skeleton. The namer is not
involved, so a disagreement is the table against the book as OPSIN implements it, and cannot be the engine's fault.

**WHAT IT COMPARES.** The connectivity layer of the InChIKey (the first 14 characters), because OPSIN defaults the stereo of a morphinan, a cephem, a
penam, a cepham and a carbapenem and the full key then differs for a reason that is not the table's. A charged entry (the pyridinium forms) is skipped:
its neutral twin is probed under its own name.

**WHAT IT CANNOT SEE.** A label on an atom that carries no hydrogen (a ring nitrogen with no N-H), since nothing can be substituted there: the
round 85 nitrogens were swapped in a way only a test on the adjacency saw (`tests/test_namer_round85_*`). A name OPSIN cannot read is counted as
"unread" and never as agreement. Needs `java` on PATH.
"""

from __future__ import annotations

import argparse
import itertools
import random
import sys
from collections import Counter, defaultdict

from rdkit import Chem, RDLogger

RDLogger.DisableLog("rdApp.*")


def _sort_key(label: str) -> tuple[int, str]:
    digits = "".join(c for c in label if c.isdigit())
    return (int(digits) if digits else 0, label)


def connectivity_key(smiles: str) -> str | None:
    """The first block of the InChIKey: skeleton and hydrogens, no stereo."""
    from rdkit.Chem import inchi

    mol = Chem.MolFromSmiles(smiles)
    return inchi.MolToInchiKey(mol)[:14] if mol is not None else None


def build_probes(table: dict, cap: int = 120, seed: int = 86, only: str = "") -> list[tuple[str, str, str, str]]:
    """(entry name, SMILES with two chlorines, the name OPSIN is asked to read, the locant pair) for every probed pair.

    A pair is two ring atoms that the entry labels, that carry a hydrogen, and are carbon or nitrogen; an entry with no labels or with any formal
    charge is skipped; an entry with more than `cap` pairs is sampled (`seed` fixes it).
    """
    rng = random.Random(seed)
    probes = []
    for smiles, entry in table.items():
        labels = entry.get("atom_locants")
        if not labels or (only and only not in entry["name"]):
            continue
        mol = Chem.MolFromSmiles(smiles)
        if mol is None or any(a.GetFormalCharge() for a in mol.GetAtoms()):
            continue
        atoms = [a for a in labels if a < mol.GetNumAtoms()
                 and mol.GetAtomWithIdx(a).GetTotalNumHs() >= 1 and mol.GetAtomWithIdx(a).GetAtomicNum() in (6, 7)]
        pairs = list(itertools.combinations(atoms, 2))
        if len(pairs) > cap:
            pairs = rng.sample(pairs, cap)
        for a, b in pairs:
            rw = Chem.RWMol(mol)
            for x in (a, b):
                rw.AddBond(x, rw.AddAtom(Chem.Atom(17)), Chem.BondType.SINGLE)
            for x in rw.GetAtoms():
                x.SetNoImplicit(False)
            try:
                Chem.SanitizeMol(rw)
            except Exception:  # noqa: BLE001
                continue
            la, lb = sorted((str(labels[a]), str(labels[b])), key=_sort_key)
            probes.append((entry["name"], Chem.MolToSmiles(rw), f"{la},{lb}-dichloro-{entry['name']}", f"{la},{lb}"))
    return probes


def run(table: dict, cap: int = 120, only: str = "") -> tuple[dict, Counter, Counter]:
    """(disagreements by entry, probes by entry, unread by entry)."""
    from py2opsin import py2opsin

    probes = build_probes(table, cap=cap, only=only)
    bad: dict[str, list] = defaultdict(list)
    total: Counter = Counter()
    unread: Counter = Counter()
    for i in range(0, len(probes), 1500):
        chunk = probes[i:i + 1500]
        outs = py2opsin([p[2] for p in chunk])
        outs = [outs] if isinstance(outs, str) else outs
        for (name, smiles, _, pair), read in zip(chunk, outs):
            total[name] += 1
            if not read:
                unread[name] += 1
            elif connectivity_key(read) != connectivity_key(smiles):
                bad[name].append((pair, smiles, read))
    return dict(bad), total, unread


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cap", type=int, default=120)
    ap.add_argument("--rings", default="", help="only entries whose name contains this")
    args = ap.parse_args()
    from openchem.vendor.iupac_namer.data_loader import _RING_CURATED_SMILES

    bad, total, unread = run(_RING_CURATED_SMILES, cap=args.cap, only=args.rings)
    print(f"{sum(total.values())} probes over {len(total)} entries; {sum(unread.values())} unread")
    for name, found in sorted(bad.items(), key=lambda kv: -len(kv[1])):
        print(f"DISAGREES {len(found)}/{total[name]} {name}: e.g. {found[0][0]} -> {found[0][2]} (table: {found[0][1]})")
    mostly_unread = [n for n in total if unread[n] * 2 > total[n]]
    if mostly_unread:
        print(f"{len(mostly_unread)} entries with more than half their probes unread (not evidence either way): {mostly_unread[:5]}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
