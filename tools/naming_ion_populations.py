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
}

MODES = ("anion", "cation", "quaternary")

_ANION_WORD = re.compile(r"(?:(?<!am)(?<!im)(?<!sulfam)ide|ate|ite)(?![a-z])|ato|(?<!am)(?<!im)(?<!ure)(?<!sulfam)ido|\(\d*-\)")
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
                atom.SetFormalCharge(1)
                atom.SetNumExplicitHs(hydrogens + 1)
                atom.SetNoImplicit(True)
            else:
                atom.SetFormalCharge(1)
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


def _inchikey(smiles_or_mol, neutral: bool = False) -> str:
    from rdkit import Chem
    from rdkit.Chem.MolStandardize import rdMolStandardize

    mol = Chem.MolFromSmiles(smiles_or_mol) if isinstance(smiles_or_mol, str) else smiles_or_mol
    if mol is None:
        return ""
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
    if mode == "anion" and not _ANION_WORD.search(name):
        return "no_anion_word"
    if mode != "anion" and not _CATION_WORD.search(name):
        return "no_cation_word"
    if back is None:
        return "ok"           # names-only: nothing to compare
    if not back:
        return "unparsable"
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
