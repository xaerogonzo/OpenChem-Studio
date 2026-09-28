"""A SMARTS-based first-order group counter, scoped to exactly the Marrero-Gani (2001) groups this
survey's energetics corpus needs -- NOT a general-purpose replacement for `compare_energetics.py`'s
hand decomposition, but the check that the hand decomposition is a property of the molecule's
structure and not of how one particular SMILES string happens to write it.

**Why this exists.** A group-contribution assignment must be invariant to SMILES atom order and ring
traversal direction -- `docs/research/literature.toml`'s marrero2001 entry records this as a real risk,
not a hypothetical one. `tests/test_energetics_groups.py` runs this counter over several differently
written SMILES for each corpus molecule and asserts identical counts; it also cross-checks every
already-published hand decomposition in `compare_energetics.py`'s `MOLECULES` table, so a mismatch here
is either a bug in this matcher or a bug in that hand decomposition -- never a shrug.

**Scope, deliberately narrow.** Ten group symbols, the ones this corpus actually uses:
`CH2 (cyclic)`, `N (cyclic)`, `NO2 except as above`, `aC-NO2`, `aC-CH3`, `aC-NH2`, `aC-N`, `aCH`, `C`,
`CH2`, `ONO2`. Extending this to the paper's full 182-row vocabulary is a different, much larger project
(a general Marrero-Gani calculator) that `docs/CALCULATOR_MATURITY.md` would need its own promotion case
for -- this module is not that.
"""

from __future__ import annotations

from rdkit import Chem

#: (group symbol, SMARTS, atoms-per-match to report as the group's occurrence count).
#: Order matters: a molecule's atoms are claimed by the FIRST pattern that matches them (mirrors the
#: paper's own "heavier/more specific group wins" assignment rule -- aC-NO2 must claim its nitro group
#: before the generic NO2 pattern gets a chance at it, same for aC-CH3 vs plain CH3, etc.).
#: Match order encodes the paper's own priority rule (Rule 2/"golden rule", `marrero2001.txt` p. 199):
#: a fragment shared between a possible aC-R group and a plainer group must use the aC-R form, and a
#: fragment's terminal atoms (here, a nitro or nitrate group's oxygens, which have nowhere else to be
#: claimed) bundle into whichever group first claims their attachment atom. So aromatic-attached and
#: nitrate-ester forms are listed BEFORE the generic, non-aromatic nitro pattern that would otherwise
#: also match their nitrogen; the `claimed`-atom check below then skips the generic pattern for atoms a
#: more specific one already took, which is what actually enforces the ordering -- getting the LIST
#: order wrong would silently misclassify a group, so `tests/test_energetics_groups.py` checks this
#: module's output against every hand decomposition already in `compare_energetics.py`, not just this
#: module's own logic.
_PATTERNS: list[tuple[str, str]] = [
    # aC-R groups bundle the ring attachment carbon with the FIRST atom of the substituent only (Rule 3,
    # p. 199: "aC-CO", "aC-COO", etc.) -- EXCEPT where the substituent's own atoms are all terminal (a
    # nitro group's two oxygens have no further group to belong to), in which case the whole substituent
    # bundles with the ring carbon because there is nowhere else for those atoms to go.
    ("aC-NO2", "[c;R]([NX3](=O)=O)"),
    ("aC-NO2", "[c;R]([N+](=O)[O-])"),
    ("aC-NH2", "[c;R]([NX3;H2])"),
    ("aC-CH3", "[c;R]([CH3;!R])"),
    # Tetryl's exocyclic nitramine N: a TERTIARY aromatic amine (0 H on N) bundles ring-C + N only, same
    # as aC-CH2 bundles ring-C + the first CH2 and leaves a further substituent (here: the N-methyl and
    # the N-nitro) to its own separate groups below.
    ("aC-N", "[c;R]([NX3;H0])"),
    # Plain aromatic CH: an aromatic carbon with an explicit H (unsubstituted ring position).
    ("aCH", "[cH1;R]"),
    # Nitrate ester -O-NO2 (whole fragment; the O has no further group to belong to either, same
    # terminal-atom reasoning as aC-NO2). Must be tried BEFORE the generic nitro pattern below, which
    # would otherwise also match this nitrogen.
    ("ONO2", "[OX2][NX3](=O)=O"),
    ("ONO2", "[OX2][N+](=O)[O-]"),
    # Ring nitramine/amine nitrogen: sp3, non-aromatic, in a ring -- generic, same as the paper's own
    # "N (cyclic)" definition (example N-methylpyrrolidine has no nitro on it at all). Its own
    # substituent (here, a nitro) is a separate group, matched next.
    ("N (cyclic)", "[NX3;R;!a]"),
    # A nitro group not already claimed by aC-NO2 or ONO2 above -- the nitramine's own N-NO2 substituent.
    ("NO2 except as above", "[NX3](=O)=O"),
    ("NO2 except as above", "[N+](=O)[O-]"),
    # Ring CH2 (the nitramine ring's own methylene).
    ("CH2 (cyclic)", "[CH2;R]"),
    # Quaternary carbon, all-carbon substitution, no H (PETN's central atom). The recursive $(...)
    # constraint checks the four-carbon-neighbor condition WITHOUT capturing those neighbors as match
    # atoms -- writing this as a plain branched SMARTS instead would (and initially did) also claim the
    # neighboring carbons as part of this one match, wrongly starving them of their own CH2 count.
    ("C", "[CX4H0;$([CX4](-[#6])(-[#6])(-[#6])-[#6])]"),
    # Plain acyclic CH2 (PETN's arm methylenes, once ONO2 above has already claimed the ester oxygen).
    ("CH2", "[CH2;!R]"),
    # Plain acyclic CH3 (tetryl's N-methyl) and CH (nitroglycerin's backbone carbon bonded to one
    # nitrate-ester O and two CH2 arms -- a plain "CH", NOT a "CH-O" ether-context group, for the same
    # reason PETN's arms are plain "CH2" and not "CH2O": ONO2 already bundles its own oxygen as a
    # complete terminal unit, per row 83's own worked example (n-butyl nitrate), so the carbon it
    # attaches to carries no ether-context group of its own).
    ("CH3", "[CH3;!R]"),
    ("CH", "[CH1;!R;!a;$([CH1](-[#6,#7,#8])(-[#6,#7,#8])-[#6,#7,#8])]"),
    # A generic NH2 not already claimed by a more specific aC-NH2/CH2NH2/etc. pattern above (row 65,
    # "NH2 except as above" -- example cyclobutylamine). Standalone, 1 atom: the group's own H's are not
    # separately counted, same convention as every other terminal amine group in this table.
    ("NH2 except as above", "[NX3;H2;!a]"),
]


def count_groups(smiles: str) -> dict[str, int]:
    """First-order group counts for `smiles`, by the scoped pattern list above.

    Raises `ValueError` for any heavy atom no pattern claims -- a silent gap here would defeat the
    point of this module, which is to catch exactly that kind of miscount.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"cannot read {smiles!r} as a structure")

    claimed: dict[int, str] = {}
    counts: dict[str, int] = {}
    for label, smarts in _PATTERNS:
        pattern = Chem.MolFromSmarts(smarts)
        if pattern is None:
            raise ValueError(f"bad SMARTS for {label!r}: {smarts!r}")
        for match in mol.GetSubstructMatches(pattern):
            if any(idx in claimed for idx in match):
                continue
            for idx in match:
                claimed[idx] = label
            counts[label] = counts.get(label, 0) + 1

    heavy_atoms = {a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() > 1}
    uncovered = heavy_atoms - claimed.keys()
    if uncovered:
        symbols = sorted(mol.GetAtomWithIdx(i).GetSymbol() for i in uncovered)
        raise ValueError(f"{smiles!r}: no group claimed atoms {sorted(uncovered)} ({symbols})")

    return counts
