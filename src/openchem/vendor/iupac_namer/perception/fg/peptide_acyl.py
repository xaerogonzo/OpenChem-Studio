"""
iupac_namer/perception/fg/peptide_acyl.py
==========================================

Naming round 9, item "peptide-acyl-naming" (admissions ledger slot 9,
target_source = "book:p.1048", P-103.2.5 / P-103.3.2).

**THE GAP.** Every one of B2's 20 rule-built dipeptides (20/20) named with
fully systematic substitutive nomenclature: glycylalanine came out
"2-[(2-amino-1-oxoethyl)amino]propanoic acid". The Blue Book retains the
"-yl" acyl form for the 20 proteinogenic amino acids when one acylates
another via the peptide bond -- P-103.3.2's own worked example is
"glycine + alanine -> glycylalanine (PIN)" (pdf p. 1048). Neither side of
that convention existed: no amino acid besides glycine had a retained
PARENT name (measured: alanine -> "2-aminopropanoic acid", not "alanine"),
and no amino-acid ACYL prefix existed at all.

**WHY A CLOSED TABLE, NOT A GENERAL RULE.** Unlike the linker-seniority
patches elsewhere in this round (_linker_has_imine, _linker_has_carbonyl,
_linker_has_phosphine_oxide -- structural checks that generalise to any
molecule with that shape), amino-acid retained names are a NAMED LIST: the
book retains exactly these 20 side chains, by exact structure, not by any
computable rule ("has an alpha-amino acid backbone" is not sufficient --
countless unnatural alpha-amino acids get no retained name at all). So this
module matches EXACT canonical structure, stereo included, against a table
of 20, the same closed-list shape as P-25.3.3's traditional ring numbering
tables in ring_naming/fusion_general.py's ``_TRADITIONAL``.

**STEREO IS PART OF THE MATCH, DELIBERATELY.** "Glycyl", "alanyl", etc.
denote the natural (L) series; the book's retained convention is for L-amino
acids specifically (P-103's own scope). Matching only by constitution (no
stereo check) would call a D-residue or an unspecified/racemic input
"alanyl" when it is not verifiably alanine at all -- exactly the kind of
unverified claim this project's convention (CLAUDE.md's "claims are
measured, not asserted") exists to prevent. A residue with under-specified
stereochemistry (measured: B2's own threonine and isoleucine dipeptide rows,
which carry stereo on the alpha carbon only, not the side-chain
stereocentre) is a KNOWN, DOCUMENTED miss, not a bug: this module correctly
declines rather than guess which diastereomer was meant.

**SCOPE.** Only a SINGLE peptide bond (a dipeptide) is handled: the base
residue's alpha-carboxyl must be free (a plain -C(=O)OH), matching every row
B2's battery actually tested. Tripeptides and longer chains, N-terminal or
C-terminal modification, and any residue outside the 20 natural ones all
fall through untouched -- this module is additive only, never declines an
otherwise-successful native plan.
"""

from __future__ import annotations

from rdkit import Chem

from openchem.vendor.iupac_namer.types import (
    Choice,
    DecisionContext,
    FreeValenceInfo,
    LeafTree,
    OutputForm,
)

# Retained PARENT names (P-103.2, Table 26.1-ish -- the free amino acid),
# keyed by canonical SMILES (with the natural, L-series stereochemistry OPSIN
# itself assigns to the bare retained name -- verified 2026-09-22 via
# py2opsin against each of the 20 names below).
_PARENT_BY_CANONICAL_SMILES: dict[str, str] = {
    "NCC(=O)O": "glycine",
    "C[C@H](N)C(=O)O": "alanine",
    "CC(C)[C@H](N)C(=O)O": "valine",
    "CC(C)C[C@H](N)C(=O)O": "leucine",
    "CC[C@H](C)[C@H](N)C(=O)O": "isoleucine",
    "O=C(O)[C@@H]1CCCN1": "proline",
    "N[C@@H](Cc1ccccc1)C(=O)O": "phenylalanine",
    "CSCC[C@H](N)C(=O)O": "methionine",
    "N[C@@H](CO)C(=O)O": "serine",
    "C[C@@H](O)[C@H](N)C(=O)O": "threonine",
    "N[C@@H](CS)C(=O)O": "cysteine",
    "N[C@@H](Cc1ccc(O)cc1)C(=O)O": "tyrosine",
    "NC(=O)C[C@H](N)C(=O)O": "asparagine",
    "NC(=O)CC[C@H](N)C(=O)O": "glutamine",
    "N[C@@H](CC(=O)O)C(=O)O": "aspartic acid",
    "N[C@@H](CCC(=O)O)C(=O)O": "glutamic acid",
    "NCCCC[C@H](N)C(=O)O": "lysine",
    "N=C(N)NCCC[C@H](N)C(=O)O": "arginine",
    "N[C@@H](Cc1c[nH]cn1)C(=O)O": "histidine",
    "N[C@@H](Cc1c[nH]c2ccccc12)C(=O)O": "tryptophan",
}

# The same 20, as the ACYL residue (the alpha -OH replaced by a dummy atom
# marking the free valence where the amide bond forms) -- built from the
# table above by replacing the alpha carboxyl's -OH with "*", never
# hand-typed twice, so the two tables cannot silently drift apart.
_ACYL_BY_CANONICAL_SMILES: dict[str, str] = {
    "*C(=O)CN": "glycyl",
    "*C(=O)[C@H](C)N": "alanyl",
    "*C(=O)[C@@H](N)C(C)C": "valyl",
    "*C(=O)[C@@H](N)CC(C)C": "leucyl",
    "*C(=O)[C@@H](N)[C@@H](C)CC": "isoleucyl",
    "*C(=O)[C@@H]1CCCN1": "prolyl",
    "*C(=O)[C@@H](N)Cc1ccccc1": "phenylalanyl",
    "*C(=O)[C@@H](N)CCSC": "methionyl",
    "*C(=O)[C@@H](N)CO": "seryl",
    "*C(=O)[C@@H](N)[C@@H](C)O": "threonyl",
    "*C(=O)[C@@H](N)CS": "cysteinyl",
    "*C(=O)[C@@H](N)Cc1ccc(O)cc1": "tyrosyl",
    "*C(=O)[C@@H](N)CC(N)=O": "asparaginyl",
    "*C(=O)[C@@H](N)CCC(N)=O": "glutaminyl",
    "*C(=O)[C@@H](N)CC(=O)O": "aspartyl",
    "*C(=O)[C@@H](N)CCC(=O)O": "glutamyl",
    "*C(=O)[C@@H](N)CCCCN": "lysyl",
    "*C(=O)[C@@H](N)CCCNC(=N)N": "arginyl",
    "*C(=O)[C@@H](N)Cc1c[nH]cn1": "histidyl",
    "*C(=O)[C@@H](N)Cc1c[nH]c2ccccc12": "tryptophyl",
}

# An amide nitrogen bonded to an sp3 alpha carbon: [N, alpha-C, acyl-C, =O,
# acyl-R]. `H0,H1` covers both base shapes this module handles -- an
# open-chain base residue's amine has exactly 1 H left after acylation
# (secondary amide, degree 2), while proline as the BASE (C-terminal)
# residue has 0: its ring nitrogen was already a secondary amine (2 ring
# bonds) before acylation, so acylating it makes a TERTIARY amide with no H
# at all (measured: histidylproline's own amide N is degree=3, H=0,
# in-ring). `_match_dipeptide` tells the two shapes apart and restores each
# correctly when cutting the bond. A free -NH2 (H2) or an already
# N,N-disubstituted amine base (not one of the 20) match neither and are
# correctly excluded here.
_AMIDE_PATTERN = Chem.MolFromSmarts("[NX3;H0,H1]([#6;X4])[CX3](=[OX1])[#6]")


def try_peptide_acyl_name(
    mol,
    output_form: OutputForm,
    free_valence: FreeValenceInfo | None,
    decision_ctx: DecisionContext | None,
) -> LeafTree | None:
    """Return a pre-composed "glycylalanine"-style LeafTree for a dipeptide
    between two of the 20 proteinogenic amino acids, or None to fall through
    to the regular plan search. Only fires for OutputForm.STANDALONE with no
    free valence -- like acid_infix_composition and cyclic_suffixes, a
    top-level structure decision, not a substituent one."""
    if output_form != OutputForm.STANDALONE or free_valence is not None:
        return None
    for match in mol.GetSubstructMatches(_AMIDE_PATTERN):
        n_idx, _alpha_c_idx, acyl_c_idx, _o_idx, _acyl_r_idx = match
        n_atom = mol.GetAtomWithIdx(n_idx)
        open_chain_base = n_atom.GetDegree() == 2 and n_atom.GetTotalNumHs() == 1
        proline_like_base = (
            n_atom.GetDegree() == 3 and n_atom.GetTotalNumHs() == 0 and n_atom.IsInRing()
        )
        if not (open_chain_base or proline_like_base):
            continue
        names = _match_dipeptide(mol, n_idx, acyl_c_idx)
        if names is not None:
            acyl_prefix, parent_name = names
            text = acyl_prefix + parent_name
            return LeafTree(
                output_form=output_form,
                free_valence=free_valence,
                choices_made=(Choice(
                    type="peptide_acyl_composition",
                    detail=f"{acyl_prefix} + {parent_name} (P-103.3.2)",
                ),),
                decision_ctx=decision_ctx,
                validity_warnings=None,
                text=text,
            )
    return None


def _match_dipeptide(mol, n_idx: int, acyl_c_idx: int) -> tuple[str, str] | None:
    """Cut the amide bond between *n_idx* and *acyl_c_idx*; if the resulting
    base fragment (N restored to -NH2) and acyl fragment (carbonyl carbon
    marked with a dummy free-valence atom) both match one of the 20 entries
    above, return (acyl_prefix, parent_name)."""
    rw = Chem.RWMol(mol)
    rw.RemoveBond(n_idx, acyl_c_idx)
    rw.GetAtomWithIdx(n_idx).SetNoImplicit(False)
    dummy_idx = rw.AddAtom(Chem.Atom(0))
    rw.AddBond(acyl_c_idx, dummy_idx, Chem.BondType.SINGLE)
    try:
        frags = Chem.GetMolFrags(rw, asMols=True, sanitizeFrags=False)
    except Exception:
        return None
    frag_atom_ids = Chem.GetMolFrags(rw, asMols=False)
    base_frag = acyl_frag = None
    for frag_mol, atom_ids in zip(frags, frag_atom_ids):
        if n_idx in atom_ids:
            base_frag = frag_mol
        if acyl_c_idx in atom_ids:
            acyl_frag = frag_mol
    if base_frag is None or acyl_frag is None or base_frag is acyl_frag:
        # The amide bond was not the sole connection between the two halves
        # (e.g. it sits in a ring) -- not the dipeptide shape this covers.
        return None
    try:
        Chem.SanitizeMol(base_frag)
        Chem.SanitizeMol(acyl_frag)
    except Exception:
        return None
    base_canonical = Chem.MolToSmiles(base_frag)
    acyl_canonical = Chem.MolToSmiles(acyl_frag)
    try:
        base_canonical = Chem.CanonSmiles(base_canonical)
        acyl_canonical = Chem.CanonSmiles(acyl_canonical)
    except Exception:
        return None
    parent_name = _PARENT_BY_CANONICAL_SMILES.get(base_canonical)
    acyl_prefix = _ACYL_BY_CANONICAL_SMILES.get(acyl_canonical)
    if parent_name is None or acyl_prefix is None:
        return None
    return acyl_prefix, parent_name
