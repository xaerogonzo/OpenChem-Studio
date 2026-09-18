"""P-58.2's indicated / added / hydro procedure, against the book's own names.

`ring_naming/indicated_hydrogen_p58.plan_hydrogens` decides, for a ring
C=O (or C=S ...) expressed as a suffix, which ring atoms carry indicated
hydrogen, which carry 'added indicated hydrogen', and which are hydro
positions. Its expectations here are the Blue Book's printed PINs (2013
recommendations, 2022 corrections; BlueBookV2.pdf, page given per case), not
the engine's output -- the function is new, and the engine's older answers
are what it corrects.

Each molecule carries its IUPAC locants as atom-map numbers, ten times the
locant, with a fusion letter as +5 (4a -> 45), so the expected sets can be
read straight off the name.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer.ring_naming.indicated_hydrogen_p58 import plan_hydrogens


def _plan(mapped_smiles: str):
    mol = Chem.MolFromSmiles(mapped_smiles)
    assert mol is not None, mapped_smiles
    locant_of = {a.GetIdx(): a.GetAtomMapNum() for a in mol.GetAtoms() if a.GetAtomMapNum()}
    ring = [a.GetIdx() for a in mol.GetAtoms() if a.IsInRing()]
    groups = [
        a.GetIdx() for a in mol.GetAtoms()
        if a.IsInRing() and any(
            b.GetBondType() == Chem.BondType.DOUBLE and not b.GetOtherAtom(a).IsInRing()
            for b in a.GetBonds()
        )
    ]
    plan = plan_hydrogens(mol, ring, groups, locant_of)
    assert plan is not None, mapped_smiles

    def locants(atoms):
        return sorted(locant_of[a] for a in atoms)

    return locants(plan.indicated), locants(plan.added), locants(plan.hydro)


@pytest.mark.parametrize("name,smiles,indicated,added,hydro", [
    # P-58.2.2.2 (p. 478): "naphthalen-1(2H)-one (PIN)"
    ("naphthalen-1(2H)-one",
     "O=[C:10]1[CH2:20][CH:30]=[CH:40][c:45]2[cH:50][cH:60][cH:70][cH:80][c:85]12",
     [], [20], []),
    # P-58.2.2.2 (p. 478): "pyrimidine-4,6(1H,5H)-dione (PIN)"
    ("pyrimidine-4,6(1H,5H)-dione",
     "O=[C:60]1[CH2:50][C:40](=O)[N:30]=[CH:20][NH:10]1",
     [], [10, 50], []),
    # P-58.2.5 (p. 484): "2,3-dihydronaphthalene-1,4-dione (PIN)" -- a quinone,
    # so the two groups need no added hydrogen and the saturation is hydro.
    ("2,3-dihydronaphthalene-1,4-dione",
     "O=[C:10]1[CH2:20][CH2:30][C:40](=O)[c:45]2[cH:50][cH:60][cH:70][cH:80][c:85]12",
     [], [], [20, 30]),
    # P-64.2 (p. 566): "quinolin-2(1H)-one (PIN) (not 1,2-dihydroquinolin-2-one)"
    ("quinolin-2(1H)-one",
     "O=[C:20]1[CH:30]=[CH:40][c:45]2[cH:50][cH:60][cH:70][cH:80][c:85]2[NH:10]1",
     [], [10], []),
    # P-64.2 (p. 566): "1,2-dihydro-3H-indol-3-one (PIN) (not 1H-indol-3(2H)-one)"
    ("1,2-dihydro-3H-indol-3-one",
     "O=[C:30]1[CH2:20][NH:10][c:75]2[cH:70][cH:60][cH:50][cH:40][c:35]12",
     [30], [], [10, 20]),
    # P-66.2.1 (p. 666): "1H-pyrrole-2,5-dione (PIN)"
    ("1H-pyrrole-2,5-dione",
     "O=[C:20]1[CH:30]=[CH:40][C:50](=O)[NH:10]1",
     [10], [], []),
    # P-58.2.3.1.3 (p. 482): "3,3a-dihydro-1H-indene-1,4(2H)-dione (PIN)"
    ("3,3a-dihydro-1H-indene-1,4(2H)-dione",
     "O=[C:10]1[CH2:20][CH2:30][CH:35]2[C:40](=O)[CH:50]=[CH:60][CH:70]=[C:75]12",
     [10], [20], [30, 35]),
])
def test_the_books_own_names(name, smiles, indicated, added, hydro):
    assert _plan(smiles) == (indicated, added, hydro), name


@pytest.mark.parametrize("name,smiles,indicated,added,hydro", [
    # Derived by the same procedure: tetralone.
    ("3,4-dihydronaphthalen-1(2H)-one",
     "O=[C:10]1[CH2:20][CH2:30][CH2:40][c:45]2[cH:50][cH:60][cH:70][cH:80][c:85]12",
     [], [20], [30, 40]),
    # uracil
    ("pyrimidine-2,4(1H,3H)-dione",
     "O=[C:20]1[NH:10][CH:60]=[CH:50][C:40](=O)[NH:30]1",
     [], [10, 30], []),
    # caffeine: one indicated H (purine), two groups -- P-58.2.3.1.3 (1) puts
    # it at N1; the groups are then accommodated, and N3/N7 are hydro.
    ("1,3,7-trimethyl-3,7-dihydro-1H-purine-2,6-dione",
     "C[N:10]1[C:20](=O)[N:30](C)[C:40]2=[C:50]([C:60]1=O)[N:70](C)[CH:80]=[N:90]2",
     [10], [], [30, 70]),
    # coumarin: as many indicated H as groups, so it sits on the group carbon.
    ("2H-1-benzopyran-2-one",
     "O=[C:20]1[CH:30]=[CH:40][c:45]2[cH:50][cH:60][cH:70][cH:80][c:85]2[O:10]1",
     [20], [], []),    # A neutral bridgehead N has three sigma bonds and no double bond to take
    # part in, like a divalent chalcogen. Counted as pi-capable it invented a
    # "4aH" in pyrido[1,2-a]pyrimidin-4-one; quinolizine's h0 is 1 only with
    # N5 left out.
    ("4H-quinolizin-4-one",
     "O=[C:40]1[CH:30]=[CH:20][CH:10]=[C:95]2[CH:90]=[CH:80][CH:70]=[CH:60][N:50]12",
     [40], [], []),
])
def test_the_same_procedure_on_the_cases_it_was_built_for(name, smiles, indicated, added, hydro):
    assert _plan(smiles) == (indicated, added, hydro), name


def test_a_charged_ring_atom_is_declined_rather_than_guessed():
    mol = Chem.MolFromSmiles("O=C1C=CC=C[NH+]1C")
    ring = [a.GetIdx() for a in mol.GetAtoms() if a.IsInRing()]
    assert plan_hydrogens(mol, ring, [1], {i: i for i in ring}) is None


# ---------------------------------------------------------------------------
# The ring table's precomposed ketone names, held to the same procedure
# ---------------------------------------------------------------------------

import re  # noqa: E402

from openchem.vendor.iupac_namer import data_loader  # noqa: E402
from openchem.vendor.iupac_namer.ring_naming import indicated_hydrogen_p58 as p58  # noqa: E402
from openchem.vendor.iupac_namer.types import Locant  # noqa: E402

_KETONE_NAME = re.compile(
    r"^(?P<parent>.+?)-(?P<locs>\d+[a-z]?(?:,\d+[a-z]?)*)"
    r"(?:\((?P<added>[^)]*)\))?-(?P<mult>di|tri|tetra)?one$"
)


def _locant(value) -> Locant:
    m = re.match(r"(\d+)([a-z]?)$", str(value))
    return Locant.numeric(int(m.group(1)), m.group(2))


def _table_disagreements():
    """(checked, [(key, recorded, by P-58.2)]) over the curated ring table.

    Entries whose name carries its ring C=O ("...-2-one") are emitted as
    written, so the engine's rewrite never sees them; before round 4 fifteen
    of them had hand-written hydrogens that P-58.2 does not give -- three
    of those described a DIFFERENT TAUTOMER from their own key.
    """
    checked, wrong = 0, []
    for smi, rec in data_loader._RING_CURATED_SMILES.items():
        name = rec.get("name") or ""
        m = _KETONE_NAME.match(name)
        if not m or "cyclo[" in name or not rec.get("atom_locants"):
            continue  # von Baeyer names carry no indicated hydrogen
        mol = Chem.MolFromSmiles(smi)
        ring = [a.GetIdx() for a in mol.GetAtoms() if a.IsInRing()]
        if any(i not in rec["atom_locants"] for i in ring):
            continue
        locant_of = {i: _locant(rec["atom_locants"][i]) for i in ring}
        groups = [
            a.GetIdx() for a in mol.GetAtoms()
            if a.IsInRing() and any(
                b.GetBondType() == Chem.BondType.DOUBLE
                and b.GetOtherAtom(a).GetSymbol() == "O"
                and not b.GetOtherAtom(a).IsInRing()
                for b in a.GetBonds()
            )
        ]
        plan = plan_hydrogens(mol, ring, groups, locant_of)
        split = p58._split_hydrogen_prefix(m.group("parent"))
        if plan is None or split is None:
            continue
        checked += 1

        def labels(atoms):
            return [str(x) for x in sorted(locant_of[a] for a in atoms)]

        base = split[0]
        expected = p58._hydrogen_prefix(labels(plan.indicated), labels(plan.hydro), base) + base
        expected += "-" + ",".join(str(x) for x in sorted(locant_of[g] for g in groups))
        added = labels(plan.added)
        if added:
            expected += "(" + ",".join(f"{a}H" for a in added) + ")"
        expected += "-" + (m.group("mult") or "") + "one"
        if expected != name:
            wrong.append((smi, name, expected))
    return checked, wrong


def test_every_precomposed_ring_ketone_name_places_its_hydrogens_by_p58():
    checked, wrong = _table_disagreements()
    # Measured 2026-09-18: 42 entries reach the comparison. A guard that
    # silently checks none passes for the wrong reason, so the floor is held.
    assert checked >= 40, checked
    assert not wrong, "\n".join(f"{k}: {n!r} -> {e!r}" for k, n, e in wrong)
