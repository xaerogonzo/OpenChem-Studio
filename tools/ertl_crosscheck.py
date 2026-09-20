"""Cross-check the v2 structural-feature vocabulary against Ertl's algorithm.

Ertl 2017 [source:ertl2017] identifies functional groups WITHOUT a curated
list: mark every heteroatom plus four kinds of carbon, merge connected marked
atoms. It is an independent oracle -- never a definition here -- so the check
runs both ways:

  Ertl -> v2   every Ertl group is covered by v2 instances (mapped), or its
               uncovered atoms carry a written justification.
  v2 -> Ertl   every v2 instance lies inside some Ertl group, or its feature
               carries a written justification for being OpenChem-only.

**THE IMPLEMENTATION IS RDKIT'S, AND IT IS NOT THE PAPER'S.** Ertl's own code
is Novartis-internal; RDKit ships Richard Hall's reimplementation as
`Contrib/IFG/ifg.py`, pinned below by sha256. Read against the paper, it
differs in two ways that matter here, both stated in its own source:

  * it marks carbons with `A=,#[!#6]` -- ALIPHATIC atoms only -- so an
    aromatic C=O carbon (a pyridone, a coumarin) is not marked, where the
    paper's table lists "O=[Car]" at 13.64% of ChEMBL. Its comment says so
    ("c=O should not match (see fig1, box 15)").
  * it merges ALL connected marked atoms, aromatic heteroatoms included, where
    the paper collects aromatic heteroatoms "as single atoms".

**CATEGORIES.** `ifg.py` returns atom sets, not the paper's generalised
categories, so `generalize` applies the paper's three rules (p. 4) itself,
producing a canonical key; `si_key` parses the paper's Additional file 1
pseudo-SMILES into the same key, so an observed category joins its ChEMBL
prevalence.

Run as a script for the report; `tests/test_ertl_crosscheck.py` imports it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tomllib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from rdkit import Chem, RDConfig, RDLogger

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from openchem.chem.structural_features import detect_features  # noqa: E402

#: The implementation this check is pinned to (RDKit 2025.09.6's copy).
IFG_PATH = Path(RDConfig.RDContribDir) / "IFG" / "ifg.py"
IFG_SHA256 = "92b97a341b5b0ca3a774ed89d7d2ee3b1d06f23ec30055bccb849f4cfde9ba60"

#: The committed mapping this check regenerates and compares against.
MAPPING_PATH = ROOT / "tests" / "fixtures" / "structural_features" / "ertl_mapping.toml"

#: The naming corpora, which are also the functional-group population the
#: v1 baseline was measured on. The naming round's second held-out set is
#: deliberately NOT here: it is locked, and only its final evaluation reads it.
CORPORA = [ROOT / "benchmarks" / "naming" / n for n in ("corpus.json", "heldout.json")]

#: Ertl 2017's Fig. 1 molecules, as ifg.py's own `main()` carries them (its
#: comment on #10 notes a discrepancy with the paper; kept as it is).
ERTL_FIGURE_1 = (
    "Cc1nc(NS(=O)(=O)c2ccc(N)cc2)nc(C)c1",
    "NC(=N)c1ccc(C=Cc2ccc(cc2O)C(=N)N)cc1",
    "CC(=O)Nc1nnc(s1)S(=O)(=O)N",
    "NS(=O)(=O)c1cc2c(NCNS2(=O)=O)cc1Cl",
    "CNC1=Nc2ccc(Cl)cc2C(=N(=O)C1)c3ccccc3",
    "Cc1onc(c1C(=O)NC2C3SC(C)(C)C(N3C2=O)C(=O)O)c4ccccc4",
    "Clc1ccccc1C2=NCC(=O)Nc3ccc(cc23)N(=O)=O",
    "COc1cc(cc(C(=O)NCC2CCCN2CC=C)c1OC)S(=O)(=O)N",
    "Cc1ccc(Cl)c(Nc2ccccc2C(=O)O)c1Cl",
    "Clc1ccc2Oc3ccccc3N=C(N4CCNCC4)c2c1",
    "FC(F)(F)CN1C(=O)CN=C(c2ccccc2)c3cc(Cl)ccc13",
    "OCC1OC(CC1O)n2cnc3C(O)CNC=Nc32",
    "CCNC1CC(C)S(=O)(=O)c2sc(cc12)S(=O)(=O)N",
    "CC(O)C1C2C(C)C(=C(N2C1=O)C(=O)O)SC3CNC(C3)C(=O)N(C)C",
    "CC1CN(CC(C)N1)c2c(F)c(N)c3c(=O)c(cn(C4CC4)c3c2F)C(=O)O",
    "CC(=CCC1C(=O)N(N(C1=O)c2ccccc2)c3ccccc3)C",
    "Clc1ccc2N=C3NC(=O)CN3Cc2c1Cl",
    "CC(=O)NC1C(NC(=N)N)C=C(OC1C(O)C(O)CO)C(=O)O",
    "CC(O)C(O)C1CNc2nc(N)nc(O)c2N1",
    "NC1CCCCN(C1)c2c(Cl)cc3c(=O)c(cn(C4CC4)c3c2Cl)C(=O)O",
)


def ifg_module():
    """RDKit's IFG implementation, refusing any copy but the pinned one."""
    digest = hashlib.sha256(IFG_PATH.read_bytes()).hexdigest()
    if digest != IFG_SHA256:
        raise RuntimeError(
            f"{IFG_PATH} has sha256 {digest}, not the pinned {IFG_SHA256}: the "
            f"oracle changed, so re-read it against the paper before re-pinning"
        )
    from rdkit.Contrib.IFG import ifg

    return ifg


def ertl_groups(mol: Chem.Mol) -> list[frozenset[int]]:
    return [frozenset(g.atomIds) for g in ifg_module().identify_functional_groups(mol)]


# --- the paper's generalisation (p. 4) ------------------------------------------

#: Dummy-atom isotopes standing for the paper's pseudo-atoms in a canonical key.
_R, _CAL, _CAR = 1, 2, 3
#: An aromatic heteroatom is written with its element and this isotope, so
#: [Nar] and an aliphatic N never share a key.
_AROMATIC = 100


def _is_carbonyl(atom: Chem.Atom) -> bool:
    return atom.GetAtomicNum() == 6 and any(
        b.GetBondType() == Chem.BondType.DOUBLE and b.GetOtherAtom(atom).GetAtomicNum() in (8, 16)
        for b in atom.GetBonds()
    )


def generalize(mol: Chem.Mol, group: frozenset[int]) -> str:
    """The paper's generalised category of one group, as a canonical key.

    1. Environments on carbon atoms are deleted, except substituents on a
       carbonyl, which are kept (aldehyde vs ketone).
    2. Free valences on heteroatoms become R -- except the H of an -OH, and
       the H of a simple amine or thiol (a group that is a single N or S).
    3. Remaining environment carbons become R -- except the one carbon of a
       single-atom N or O group, which keeps its type (Cal/Car): amine vs
       aniline, alcohol vs phenol.
    """
    single = len(group) == 1
    rw = Chem.RWMol()
    index: dict[int, int] = {}
    for i in sorted(group):
        a = mol.GetAtomWithIdx(i)
        new = Chem.Atom(a.GetAtomicNum())
        new.SetFormalCharge(a.GetFormalCharge())
        new.SetNoImplicit(True)
        if a.GetIsAromatic() and a.GetAtomicNum() != 6:
            new.SetIsotope(_AROMATIC)
        index[i] = rw.AddAtom(new)
    for bond in mol.GetBonds():
        a, b = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        if a in group and b in group:
            order = bond.GetBondType()
            if order == Chem.BondType.AROMATIC:
                order = Chem.BondType.SINGLE
            rw.AddBond(index[a], index[b], order)

    def add_pseudo(to: int, isotope: int, order=Chem.BondType.SINGLE):
        dummy = Chem.Atom(0)
        dummy.SetIsotope(isotope)
        rw.AddBond(index[to], rw.AddAtom(dummy), order)

    for i in sorted(group):
        atom = mol.GetAtomWithIdx(i)
        if atom.GetIsAromatic() and atom.GetAtomicNum() != 6:
            continue  # an aromatic heteroatom is written bare: [Nar], [Oar], [Sar]
        # An explicit hydrogen atom ([2H] in heavy water) is a hydrogen, not an
        # environment: counting it as R filed D2O under the ETHER category.
        outside = [n for n in atom.GetNeighbors()
                   if n.GetIdx() not in group and n.GetAtomicNum() != 1]
        if atom.GetAtomicNum() == 6:
            if _is_carbonyl(atom):
                for n in outside:
                    add_pseudo(i, _R)  # rule 1's exception, then rule 3
            continue  # rule 1: other carbon environments deleted
        carbons = [n for n in outside if n.GetAtomicNum() == 6]
        for n in outside:
            if n.GetAtomicNum() != 6:
                add_pseudo(i, _R)
            elif single and atom.GetAtomicNum() in (7, 8) and len(carbons) == 1:
                order = mol.GetBondBetweenAtoms(i, n.GetIdx()).GetBondType()
                add_pseudo(i, _CAR if n.GetIsAromatic() else _CAL,
                           Chem.BondType.DOUBLE if order == Chem.BondType.DOUBLE else Chem.BondType.SINGLE)
            else:
                add_pseudo(i, _R)
        # Rule 2: an -OH keeps its H; so does the N or S of a single-atom
        # group (amine, thiol). Every other H on a heteroatom becomes R.
        keep_h = atom.GetAtomicNum() == 8 or (single and atom.GetAtomicNum() in (7, 16))
        if not keep_h:
            for _ in range(atom.GetTotalNumHs()):
                add_pseudo(i, _R)
    return Chem.MolToSmiles(rw.GetMol(), canonical=True)


_SI_TOKENS = {
    "[R]": f"[{_R}*]", "[Cal]": f"[{_CAL}*]", "[Car]": f"[{_CAR}*]",
    "[Nar]": f"[{_AROMATIC}N]", "[Nar+]": f"[{_AROMATIC}N+]",
    "[Oar]": f"[{_AROMATIC}O]", "[Oar+]": f"[{_AROMATIC}O+]",
    "[Sar]": f"[{_AROMATIC}S]", "[Sar+]": f"[{_AROMATIC}S+]",
}


def si_key(pseudo: str) -> str | None:
    """A pseudo-SMILES from Ertl's Additional file 1, as the same canonical
    key `generalize` produces. None when RDKit cannot read it."""
    text = pseudo
    for token, replacement in _SI_TOKENS.items():
        text = text.replace(token, replacement)
    mol = Chem.MolFromSmiles(text, sanitize=False)
    if mol is None:
        return None
    # The table was built on NEUTRALISED structures (the paper, p. 5), so it
    # writes nitro and azide pentavalent -- "[R]N(=O)=O" -- where RDKit holds
    # them charge-separated. RDKit's own standard cleanup maps the one onto
    # the other; without it nitro, present in the corpus, never joined its row.
    mol.UpdatePropertyCache(strict=False)
    Chem.rdmolops.Cleanup(mol)
    for atom in mol.GetAtoms():
        atom.SetNoImplicit(True)
        atom.SetNumExplicitHs(0)
    return Chem.MolToSmiles(mol, canonical=True)


def load_si(path: Path) -> list[tuple[str, float, int]]:
    """(pseudo-SMILES, % of ChEMBL molecules, molecule count), file order."""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and re.fullmatch(r"[\d.]+", parts[1]):
            rows.append((parts[0], float(parts[1]), int(parts[2])))
    return rows


# --- the two-way comparison -----------------------------------------------------


@dataclass
class CategoryObservation:
    count: int = 0
    features: set[str] = field(default_factory=set)
    #: Element symbols of Ertl-marked atoms no v2 instance covers.
    uncovered: set[str] = field(default_factory=set)
    #: v2 instances touching the group that reach OUTSIDE it.
    wider: set[str] = field(default_factory=set)
    example: str = ""


def population() -> list[tuple[str, str]]:
    """(source, SMILES) for every molecule the check runs over."""
    out = []
    for path in CORPORA:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else data.get("molecules", data.get("entries", []))
        out.extend((path.stem, item["smiles"]) for item in items)
    out.extend(("ertl2017-fig1", s) for s in ERTL_FIGURE_1)
    out.extend(("ertl2017-si", r["smiles"]) for r in si_representatives())
    return out


#: One molecule per prevalent category of the paper's Additional file 1,
#: kept only where it regenerates that category (see the file's comment).
SI_REPRESENTATIVES = ROOT / "tests" / "fixtures" / "structural_features" / "ertl_si_representatives.json"


def si_representatives() -> list[dict]:
    return json.loads(SI_REPRESENTATIVES.read_text(encoding="utf-8"))["representatives"]


def observe() -> tuple[dict[str, CategoryObservation], dict[str, Counter]]:
    """Every Ertl category seen, and every v2 feature found outside any group."""
    RDLogger.DisableLog("rdApp.*")
    categories: dict[str, CategoryObservation] = defaultdict(CategoryObservation)
    outside: dict[str, Counter] = defaultdict(Counter)
    for source, smiles in population():
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            continue
        features = detect_features(mol)
        groups = ertl_groups(mol)
        for group in groups:
            key = generalize(mol, group)
            obs = categories[key]
            obs.count += 1
            obs.example = obs.example or smiles
            touching = [f for f in features if f.atoms & group]
            covered = set().union(*(f.atoms for f in touching)) if touching else set()
            obs.features |= {f.feature_id for f in touching}
            obs.uncovered |= {mol.GetAtomWithIdx(i).GetSymbol() for i in group - covered}
            obs.wider |= {f.feature_id for f in touching if not f.atoms <= group}
        for f in features:
            if not any(f.atoms <= g for g in groups):
                outside[f.feature_id][smiles] += 1
    return dict(categories), dict(outside)


def as_mapping(categories, outside) -> dict:
    """The observations in the committed file's shape (justifications excluded)."""
    return {
        "category": {
            key: {
                "features": sorted(obs.features),
                "uncovered": sorted(obs.uncovered),
                "wider": sorted(obs.wider),
            }
            for key, obs in sorted(categories.items())
        },
        "outside": {fid: sorted(c) for fid, c in sorted(outside.items())},
    }


def committed() -> dict:
    return tomllib.loads(MAPPING_PATH.read_text(encoding="utf-8"))


def _toml_str(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


def write_mapping(categories, outside, previous: dict | None) -> str:
    """Render the mapping file, CARRYING OVER every justification already
    written, so regenerating never discards a reason someone wrote."""
    previous = previous or {"category": {}, "outside": {}}
    lines = [
        "# Ertl 2017 <-> vocabulary v3. GENERATED by `tools/ertl_crosscheck.py --write`,",
        "# then justified by hand: every `why` is written by a person and carried",
        "# over on regeneration. tests/test_ertl_crosscheck.py regenerates the",
        "# observations and fails on any difference, and on any category with",
        "# uncovered atoms (or any OpenChem-only feature) that has no `why`.",
        "#",
        "# category key: Ertl's generalised category (paper p. 4) as a canonical",
        "# SMILES; [1*] = R, [2*] = Cal, [3*] = Car, [100N] = Nar (etc.).",
        "#   features   v2 features touching the group",
        "#   uncovered  elements of Ertl-marked atoms no v2 instance covers",
        "#   wider      v2 features touching the group that reach outside it",
        "",
    ]
    for key, obs in sorted(categories.items()):
        lines.append(f"[category.{_toml_str(key)}]")
        lines.append(f"example = {_toml_str(obs.example)}")
        lines.append(f"count = {obs.count}")
        lines.append(f"features = {json.dumps(sorted(obs.features))}")
        lines.append(f"uncovered = {json.dumps(sorted(obs.uncovered))}")
        lines.append(f"wider = {json.dumps(sorted(obs.wider))}")
        why = previous["category"].get(key, {}).get("why")
        if why:
            lines.append(f"why = {_toml_str(why)}")
        lines.append("")
    for fid, counter in sorted(outside.items()):
        lines.append(f"[outside.{_toml_str(fid)}]")
        lines.append(f"examples = {json.dumps(sorted(counter)[:3])}")
        why = previous["outside"].get(fid, {}).get("why")
        if why:
            lines.append(f"why = {_toml_str(why)}")
        lines.append("")
    return "\n".join(lines)


def prevalence_report(categories, si_path: Path, top: int) -> str:
    """How much of ChEMBL's functional-group occurrence, by Ertl's own table,
    falls in categories this population observed and v2 covers fully."""
    si = load_si(si_path)[:top]
    lines, covered_pct, seen_pct, total_pct = [], 0.0, 0.0, 0.0
    for pseudo, pct, n in si:
        key = si_key(pseudo)
        total_pct += pct
        obs = categories.get(key)
        state = "not observed" if obs is None else ("MAPPED" if not obs.uncovered else f"uncovered {obs.uncovered}")
        if obs is not None:
            seen_pct += pct
            if not obs.uncovered:
                covered_pct += pct
        lines.append(f"{pct:6.2f}%  {pseudo:42s} {state}  {sorted(obs.features) if obs else ''}")
    head = (f"Top {len(si)} Ertl categories: {total_pct:.1f} summed %; observed in this "
            f"population {seen_pct:.1f}; observed AND fully covered {covered_pct:.1f}")
    return head + "\n" + "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="regenerate the mapping file")
    parser.add_argument("--si", type=Path, help="Ertl's Additional file 1 (ERTL2017_si.md)")
    parser.add_argument("--top", type=int, default=100)
    args = parser.parse_args(argv)
    categories, outside = observe()
    if args.write:
        previous = committed() if MAPPING_PATH.exists() else None
        MAPPING_PATH.write_text(write_mapping(categories, outside, previous), encoding="utf-8")
        print(f"wrote {MAPPING_PATH} ({len(categories)} categories, {len(outside)} outside)")
    unjustified = [k for k, o in categories.items() if o.uncovered]
    print(f"{len(categories)} categories; {len(unjustified)} with uncovered atoms; "
          f"{len(outside)} v2 features outside every Ertl group")
    if args.si:
        print(prevalence_report(categories, args.si, args.top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
