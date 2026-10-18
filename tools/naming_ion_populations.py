"""Make ions out of the census molecules and check that each name still says its charge: where naming rounds 46 to 49 found their defects.

    python tools/naming_ion_populations.py anion                       # deprotonate ONE acidic site of each census molecule
    python tools/naming_ion_populations.py cation --limit 40           # protonate ONE basic site, at most 40 per kind
    python tools/naming_ion_populations.py quaternary --out quat.json  # N-methylate ONE basic nitrogen
    python tools/naming_ion_populations.py anion --names-only          # name them, skip the OPSIN read-back (no JRE needed)

**WHY IT EXISTS.** Round 45's census was saturated (seven rows, all OPSIN artifacts), so a census scan could not find anything. Rounds 46, 47, 48 and 49 each found
their defects the same way: change ONE site of every census molecule into an ion and read every name back. Round 46 deprotonated (21 of the first 169 anions had no charge
in the name); round 47 protonated (a ring cation with a ketone lost its hydro positions); round 48 N-methylated (a hydro azolium put the cation and the indicated hydrogen on
one nitrogen, a hypothesis that a quaternary N+ shared round 47's defect was measured and found false). The three scripts lived in scratch folders and memory notes, and each
round rebuilt one. This is the one place.

**WHAT IT SAYS.** For each candidate ion, one of: `ok`; `refused` (the engine raised, which for an ion is the charge guard working: a visible failure, listed, not a wrong
name); `naming_error` (an embedded `[NAMING ERROR: ...]`); `unparsable` (OPSIN cannot read the name); `charge_changed` (reads back to the same connectivity with a different net
charge, usually the neutral compound: the name lost its charge); `wrong` (a different molecule). An ANION is compared on NEUTRAL connectivity, because OPSIN reads `-sulfonamidate`
as the neutral sulfonamide; its name must also carry an anion word, which is the check the neutral comparison cannot make. A cation or a quaternary cation is compared with its
charge. A candidate is made only where a molecule has EXACTLY ONE site of the kind, so each ion is the same molecule with one change.

**WHAT IT DOES NOT DO.** It reads the census, which is not a frozen population (`engine_consulted: false`). It never touches a frozen set. The site patterns are the ones rounds
46 to 48 used, no broader: an acidic or basic site they do not match is not covered, and the summary says how many candidates each kind produced so a silent zero shows.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

#: Acidic sites, deprotonated (round 46). The pattern's FIRST atom is the one that loses its proton.
ANION_SITES = {
    "sulfonamide": "[NX3;H1;!R]S(=O)(=O)",
    "carboxylic": "[OX2H1]C(=O)",
    "phenol": "[OX2H1]c",
    "thiol": "[SX2H1]",
    "tetrazole": "[nH]1nnnc1",
    "imide": "[NX3;H1](C=O)C=O",
    "acylsulfonamide": "[NX3;H1](C=O)S(=O)=O",
    "sulfonic": "[OX2H1]S(=O)=O",
    # round 51: the sites rounds 46-50 never changed
    "lactam": "[NX3;H1;R]C(=O)",
    "hydrazide": "[NX3;H1](C=O)[NX3]",
    "azole_nh": "[nX3;H1;r5]",
    "hydroxamic": "[OX2H1][NX3]C=O",
    # round 52
    "amide_acyclic": "[NX3;H1;!R]C(=O)[#6]",
    "urea": "[NX3;H1;!R]C(=O)N",
    "thioamide": "[NX3;H1]C(=S)",
    "oxime": "[OX2H1]N=C",
    "phosphonic": "[OX2H1]P(=O)",
    "sulfinic": "[OX2H1]S(=O)[#6]",
    # round 58: the first CARBON acids and a few more
    "enol": "[OX2H1][CX3]=[CX3]",
    "hydroxylamine": "[OX2H1][NX3;!$(N=*);!$(NC=O)]",
    "sultam": "[NX3;H1;R]S(=O)(=O)",
    "carbamate": "[NX3;H1;!R]C(=O)O",
    "dicarbonyl_ch": "[CX4;H2,H1]([CX3]=O)[CX3]=O",
    "dinitrile_ch": "[CX4;H2,H1](C#N)C#N",
    # round 59: heavier acids
    "selenol": "[SeX2H1]",
    "boronic": "[OX2H1]B",
    "phosphinic": "[OX2H1][PX4](=O)([#6])[#6]",
    # round 60: an alkoxide and an anilide (the azanide prefix of round 56), never deprotonated before
    "alcohol": "[OX2H1][CX4]",
    "aniline_nh": "[NX3;H2,H1;$(N-[a]);!$(NC=[O,S,N]);!$(NS=O)]",
}

#: Basic sites, protonated or N-methylated (rounds 47 and 48). The first atom gains the proton or the methyl.
CATION_SITES = {
    "aromatic_n": "[nX2;r6]",
    "azole_n": "[nX2;r5]",
    "amine_primary": "[NX3;H2;!$(NC=[O,S,N]);!$(N-[a]);!$(NS=O)]",
    "amine_secondary": "[NX3;H1;!$(NC=[O,S,N]);!$(N-[a]);!$(NS=O);!$(N-N);!$(N-O)]",
    "amine_tertiary": "[NX3;H0;!$(NC=[O,S,N]);!$(N-[a]);!$(NS=O);!$(N-N);!$(N-O);!$(N=*)]",
    "aniline": "[NX3;H2,H1;$(N-[a]);!$(NC=[O,S,N]);!$(NS=O)]",
    "imine": "[NX2;!R]=C",
    "amidine": "[NX2]=C[NX3]",
    "amide_o": "[OX1;$(O=C[NX3])]",
    "carbonyl_o": "[OX1;$(O=[CX3]([#6])[#6])]",
    # round 52
    "thiocarbonyl_s": "[SX1]=C",
    "sulfoxide_o": "[OX1]=[SX3]",
    "phosphine_p": "[PX3;H0]",
    "nitrile_n": "[NX1]#C",
    # round 58
    "thioether_s": "[SX2;!R]([#6])[#6]",
    # round 59: N-oxide O (protonated), selenium, phosphine oxide
    "n_oxide_o": "[OX1-][#7+;!$([#7+](~[OX1])~[OX1])]",   # an N-oxide; a NITRO group is not one (its protonated form is another species)
    "selenoether_se": "[SeX2;!R]([#6])[#6]",
    "phosphine_oxide_o": "[OX1]=[PX4]",
    # round 60: the oxygens no earlier round protonated (an ester, an acid, an aldehyde, an ether, an alcohol)
    "ester_o": "[OX1;$(O=C([#6,#1])[OX2][#6])]",
    "acid_o": "[OX1;$(O=C[OX2H1])]",
    "aldehyde_o": "[OX1;$(O=[CX3H1])]",
    "ether_o": "[OX2;!R;!$(O[CX3]=[O,N,S])]([#6])[#6]",
    "alcohol_o": "[OX2H1][CX4]",
}

MODES = ("anion", "cation", "quaternary", "zwitterion", "dianion", "dication", "betaine", "quat_dication", "trianion", "trication")

#: The pairs rounds 55 onward make (the multi-charge modes): which kinds of site go together. A zwitterion deprotonates an acid AND protonates a base in one molecule (a net-neutral ion,
#: which the charge guard does not judge at all); a dianion deprotonates two different acid sites; a dication protonates two different base sites.
ZWITTERION_ACIDS = ("carboxylic", "phenol", "sulfonic", "tetrazole", "imide", "acylsulfonamide",
                    # round 59: the acid kinds the single-charge mode reached after round 55
                    "lactam", "azole_nh", "amide_acyclic", "urea", "hydroxamic", "enol", "dicarbonyl_ch", "thioamide", "hydrazide",
                    "alcohol", "aniline_nh")  # round 61: the acids round 60 added
ZWITTERION_BASES = ("amine_primary", "amine_secondary", "amine_tertiary", "aniline", "aromatic_n", "azole_n", "amidine",
                    "imine", "amide_o", "carbonyl_o", "thioether_s", "n_oxide_o",
                    "ester_o", "acid_o", "aldehyde_o", "ether_o", "alcohol_o")  # round 61
DIANION_KINDS = ("carboxylic", "phenol", "sulfonic", "tetrazole", "imide", "sulfonamide", "thiol",
                 "lactam", "azole_nh", "amide_acyclic", "urea", "hydroxamic", "enol", "dicarbonyl_ch", "thioamide", "hydrazide",
                 "alcohol", "aniline_nh")
DICATION_KINDS = ("amine_primary", "amine_secondary", "amine_tertiary", "aniline", "aromatic_n", "azole_n", "amidine",
                  "imine", "amide_o", "carbonyl_o", "thioether_s", "n_oxide_o",
                  "ester_o", "acid_o", "aldehyde_o", "ether_o", "alcohol_o")

_ANION_WORD = re.compile(r"(?:(?<!am)(?<!im)(?<!sulfam)ide|ate|ite)(?![a-z])|ato|(?<!am)(?<!im)(?<!ure)(?<!sulfam)ido|\(\d*-\)|\d'*-id-|azanidyl")
_CATION_WORD = re.compile(r"ium|onio|\(\d*\+\)")


@dataclass(frozen=True)
class Candidate:
    mode: str
    kind: str
    label: str
    smiles: str       # the ion
    parent: str       # the census molecule it came from


def _usable(mol, smiles: str) -> bool:
    """A single neutral fragment; a nitro group or an N-oxide is allowed, nothing else charged."""
    from rdkit import Chem

    if mol is None or "." in smiles or Chem.GetFormalCharge(mol) != 0:
        return False
    return all(
        a.GetFormalCharge() == 0 or (a.GetSymbol() == "N" and a.GetFormalCharge() == 1) or (a.GetSymbol() == "O" and a.GetFormalCharge() == -1)
        for a in mol.GetAtoms()
    )


def generate(mode: str, rows: list[dict], limit: int | None = None) -> list[Candidate]:
    """The ions: one per molecule per kind, only where the molecule has exactly one site of that kind."""
    from rdkit import Chem, RDLogger

    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; one of {MODES}")
    RDLogger.DisableLog("rdApp.*")
    if mode in ("zwitterion", "dianion", "dication", "betaine", "quat_dication", "trianion", "trication"):
        return _generate_pairs(mode, rows, limit)
    sites = ANION_SITES if mode == "anion" else CATION_SITES
    out: list[Candidate] = []
    for kind, smarts in sites.items():
        query = Chem.MolFromSmarts(smarts)
        count = 0
        for row in rows:
            mol = Chem.MolFromSmiles(row["smiles"])
            if not _usable(mol, row["smiles"]):
                continue
            hits = mol.GetSubstructMatches(query)
            if len(hits) != 1:
                continue
            rw = Chem.RWMol(mol)
            atom = rw.GetAtomWithIdx(hits[0][0])
            hydrogens = atom.GetTotalNumHs()
            if mode == "anion":
                atom.SetFormalCharge(-1)
                atom.SetNumExplicitHs(0)
                atom.SetNoImplicit(False)
            elif mode == "cation":
                atom.SetFormalCharge(atom.GetFormalCharge() + 1)
                atom.SetNumExplicitHs(hydrogens + 1)
                atom.SetNoImplicit(True)
            else:
                atom.SetFormalCharge(atom.GetFormalCharge() + 1)   # an N-oxide O- methylated is a neutral alkoxy on N+ (round 59)
                atom.SetNumExplicitHs(hydrogens)
                atom.SetNoImplicit(True)
                methyl = rw.AddAtom(Chem.Atom(6))
                rw.AddBond(atom.GetIdx(), methyl, Chem.BondType.SINGLE)
            try:
                Chem.SanitizeMol(rw)
            except Exception:  # noqa: BLE001 - a site that will not sanitise as an ion is not a candidate
                continue
            count += 1
            if limit is not None and count > limit:
                break
            out.append(Candidate(mode, kind, row.get("label", ""), Chem.MolToSmiles(rw), row["smiles"]))
    return out


def _apply_site(rw, idx: int, how: str) -> None:
    """Deprotonate (`minus`), protonate (`plus`) or N-methylate (`methyl`, a permanent cation) one atom of an editable molecule."""
    from rdkit import Chem

    atom = rw.GetAtomWithIdx(idx)
    hydrogens = atom.GetTotalNumHs()
    if how == "methyl":
        atom.SetFormalCharge(atom.GetFormalCharge() + 1)
        atom.SetNumExplicitHs(hydrogens)
        atom.SetNoImplicit(True)
        methyl = rw.AddAtom(Chem.Atom(6))
        rw.AddBond(idx, methyl, Chem.BondType.SINGLE)
    elif how == "minus":
        atom.SetFormalCharge(-1)
        atom.SetNumExplicitHs(0)
        atom.SetNoImplicit(False)
    else:
        atom.SetFormalCharge(atom.GetFormalCharge() + 1)   # an N-oxide O- becomes a neutral hydroxy (round 59)
        atom.SetNumExplicitHs(hydrogens + 1)
        atom.SetNoImplicit(True)


def _generate_pairs(mode: str, rows: list[dict], limit: int | None) -> list[Candidate]:
    """Two sites changed in ONE molecule (rounds 55 on): an acid and a base (`zwitterion`), two acids (`dianion`), two bases (`dication`).

    Each kind must occur exactly once in the molecule and the two sites must be different atoms, so the ion is the one a person would draw. One ion per molecule per pair of kinds."""
    from itertools import combinations, product

    from rdkit import Chem

    if mode in ("zwitterion", "betaine"):
        pairs = list(product(ZWITTERION_ACIDS, ZWITTERION_BASES))
    elif mode == "dianion":
        pairs = list(combinations(DIANION_KINDS, 2))
    elif mode == "trianion":
        pairs = list(combinations(DIANION_KINDS, 3))
    elif mode == "trication":
        pairs = list(combinations(DICATION_KINDS, 3))
    else:
        pairs = list(combinations(DICATION_KINDS, 2))
    queries = {k: Chem.MolFromSmarts(s) for k, s in {**ANION_SITES, **CATION_SITES}.items()}
    hows = {
        "zwitterion": ("minus", "plus"), "dianion": ("minus", "minus"), "dication": ("plus", "plus"),
        "betaine": ("minus", "methyl"), "quat_dication": ("methyl", "plus"),
        "trianion": ("minus", "minus", "minus"), "trication": ("plus", "plus", "plus"),
    }[mode]
    out: list[Candidate] = []
    for kinds in pairs:
        count = 0
        for row in rows:
            mol = Chem.MolFromSmiles(row["smiles"])
            if not _usable(mol, row["smiles"]):
                continue
            hits = [mol.GetSubstructMatches(queries[k]) for k in kinds]
            if any(len(h) != 1 for h in hits) or len({h[0][0] for h in hits}) != len(kinds):
                continue
            # Two sites within two bonds of each other are one group drawn as a charge-separated tautomer (an azole's [n-] beside its own [nH+], an amide's N- beside its O-protonated
            # oxygen): a neutral compound, not an ion anyone would draw (naming round 59).
            dm = Chem.GetDistanceMatrix(mol)
            if any(dm[a[0][0]][b[0][0]] <= 2 for i, a in enumerate(hits) for b in hits[i + 1:]):
                continue
            rw = Chem.RWMol(mol)
            for h, how in zip(hits, hows):
                _apply_site(rw, h[0][0], how)
            try:
                Chem.SanitizeMol(rw)
            except Exception:  # noqa: BLE001 - a pair that will not sanitise as an ion is not a candidate
                continue
            count += 1
            if limit is not None and count > limit:
                break
            out.append(Candidate(mode, "+".join(kinds), row.get("label", ""), Chem.MolToSmiles(rw), row["smiles"]))
    return out


def _sulfoxide_drawing(mol):
    """OPSIN draws an O-protonated sulfoxide as a sulfonium, `O[S+](C)C`; the ion population draws it `CS(C)=[OH+]`. They are one species, but InChI keeps them apart (round 53)."""
    from rdkit import Chem

    rw = Chem.RWMol(mol)
    changed = False
    for s in rw.GetAtoms():
        if s.GetSymbol() != "S" or s.GetFormalCharge() != 1:
            continue
        for bond in s.GetBonds():
            o = bond.GetOtherAtom(s)
            if o.GetSymbol() == "O" and o.GetFormalCharge() == 0 and bond.GetBondTypeAsDouble() == 1.0 and o.GetDegree() <= 2 and not o.IsInRing():
                hydrogens = o.GetTotalNumHs()
                bond.SetBondType(Chem.BondType.DOUBLE)
                s.SetFormalCharge(0)
                o.SetFormalCharge(1)
                o.SetNoImplicit(True)
                o.SetNumExplicitHs(hydrogens)
                changed = True
                break
    if not changed:
        return mol
    try:
        Chem.SanitizeMol(rw)
    except Exception:  # noqa: BLE001 - keep the original drawing
        return mol
    return rw.GetMol()


def _inchikey(smiles_or_mol, neutral: bool = False) -> str:
    from rdkit import Chem
    from rdkit.Chem.MolStandardize import rdMolStandardize

    mol = Chem.MolFromSmiles(smiles_or_mol) if isinstance(smiles_or_mol, str) else smiles_or_mol
    if mol is None:
        return ""
    mol = _sulfoxide_drawing(mol)
    if neutral:
        mol = rdMolStandardize.Uncharger().uncharge(Chem.Mol(mol))
        return Chem.MolToInchiKey(mol).split("-")[0]
    return Chem.MolToInchiKey(mol)


def verdict(mode: str, smiles: str, name: str | None, back: str | None, refusal: str | None = None) -> str:
    """One class for one ion. `name` is None when the engine raised (`refusal` says why); `back` is OPSIN's SMILES, "" when it could not read the name."""
    if name is None:
        return "refused"
    if "NAMING ERROR" in name:
        return "naming_error"
    if mode in ("anion", "dianion", "trianion", "zwitterion", "betaine") and not _ANION_WORD.search(name):
        return "no_anion_word"
    if mode in ("cation", "quaternary", "dication", "trication", "zwitterion", "betaine", "quat_dication") and not _CATION_WORD.search(name):
        return "no_cation_word"
    if back is None:
        return "ok"           # names-only: nothing to compare
    if not back:
        return "unparsable"
    if mode in ("zwitterion", "dianion", "dication", "betaine", "quat_dication", "trianion", "trication"):
        # Standard InChI normalises where a proton sits, so the same key is the same ion; a different charge count with the same skeleton is the compound with a charge lost.
        if _inchikey(back) == _inchikey(smiles):
            return "ok"
        if _inchikey(back, neutral=True) == _inchikey(smiles, neutral=True):
            # OPSIN reads `-sulfonamidate` as the NEUTRAL sulfonamide (the single-anion mode compares on neutral connectivity for the same reason), so each one in the name
            # accounts for one charge the read-back does not have.
            from rdkit import Chem

            lost = Chem.GetFormalCharge(Chem.MolFromSmiles(smiles)) - Chem.GetFormalCharge(Chem.MolFromSmiles(back))
            if lost and lost == -name.count("sulfonamidate") or (lost and abs(lost) == name.count("sulfonamidate")):
                return "ok"
            return "charge_changed"
        return "wrong"
    if mode == "anion":
        return "ok" if _inchikey(back, neutral=True) == _inchikey(smiles, neutral=True) else "wrong"
    if _inchikey(back) == _inchikey(smiles):
        return "ok"
    # Standard InChI normalises WHERE a proton sits, so a different protonation site gives the SAME key and is "ok" above; a key that differs while the neutral skeleton agrees is a
    # different net charge (the neutral compound read back from a cation's name).
    if _inchikey(back, neutral=True) == _inchikey(smiles, neutral=True):
        return "charge_changed"
    return "wrong"


def run(mode: str, rows: list[dict], limit: int | None, names_only: bool) -> list[dict]:
    from openchem.vendor.iupac_namer import name_smiles

    candidates = generate(mode, rows, limit)
    names: list[str | None] = []
    reasons: list[str | None] = []
    for c in candidates:
        try:
            names.append(name_smiles(c.smiles))
            reasons.append(None)
        except Exception as exc:  # noqa: BLE001 - a refusal is a result here
            names.append(None)
            reasons.append(str(exc)[:100])
    backs: list[str | None]
    if names_only:
        backs = [None] * len(candidates)
    else:
        import naming_census_scan as scan

        readable = [n for n in names if n is not None and "NAMING ERROR" not in n]
        reads = iter(scan.read_back(readable))
        backs = [next(reads) if (n is not None and "NAMING ERROR" not in n) else None for n in names]
    results = []
    for c, name, back, reason in zip(candidates, names, backs, reasons):
        results.append({
            "mode": c.mode, "kind": c.kind, "label": c.label, "smiles": c.smiles, "name": name, "read": back, "refusal": reason,
            "verdict": verdict(mode, c.smiles, name, back, reason),
        })
    return results


def summary(results: list[dict], examples: int = 4) -> str:
    by_kind = collections.Counter(r["kind"] for r in results)
    by_verdict = collections.Counter(r["verdict"] for r in results)
    lines = [f"{len(results)} ions"] + [f"  {k:<18} {n}" for k, n in sorted(by_kind.items())]
    lines.append("verdicts:")
    lines += [f"  {v:<16} {n}" for v, n in by_verdict.most_common()]
    shown = collections.Counter()
    for r in results:
        if r["verdict"] == "ok":
            continue
        shown[r["verdict"]] += 1
        if shown[r["verdict"]] <= examples:
            detail = r["refusal"] or (r["name"] or "")
            lines.append(f"  [{r['verdict']}] {r['kind']}: {r['smiles']}  ->  {detail[:150]}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Make ions out of the census molecules and check each name keeps its charge.")
    parser.add_argument("mode", choices=MODES)
    parser.add_argument("--limit", type=int, default=None, help="at most this many ions per kind")
    parser.add_argument("--out", type=Path, default=None, help="write every result as JSON")
    parser.add_argument("--names-only", action="store_true", help="skip the OPSIN read-back")
    args = parser.parse_args()

    from naming_census_scan import _engine_logging_silenced, load_sample

    rows = load_sample()
    with _engine_logging_silenced():
        results = run(args.mode, rows, args.limit, args.names_only)
    print(summary(results))
    if args.out:
        args.out.write_text(json.dumps(results, indent=1), encoding="utf-8")
        print(f"-> {args.out}")


if __name__ == "__main__":
    main()
