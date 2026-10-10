"""Two substituents that print as the same SMILES are not the same substituent: the session cache's identity.

`CC[C@@H](C)c1cccc([C@@H](C)CC)c1` (the R,S di-sec-butylbenzene) was named `1,3-bis[(2R)-butan-2-yl]benzene` or
`1,3-bis[(2S)-butan-2-yl]benzene`, by the order its atoms were written in. OPSIN reads the first as the R,R compound and
the second as the S,S, so both were names for a different stereoisomer, and the name the Blue Book prints for it (P-14.4
(j), pdf p. 79) is `1-[(2R)-butan-2-yl]-3-[(2S)-butan-2-yl]benzene (PIN)`.

THE CAUSE WAS NOT THE PREFIX MERGER, which is where it first looked to be. Both prefixes reach `merge_identical_prefixes`
already named `(2R)-butan-2-yl`; it correctly merges two identical strings. They were identical because the naming
session's cache is keyed on the fragment's SMILES, and a carved fragment's stereo is not in its SMILES. Cut at either ring
bond, the two substituents are both `CCCC` with the attachment on atom 3: once the ring side is an H the centre is no longer
a stereocentre, so the inherited descriptor (`R`, `S`) lives only in an atom PROPERTY, which `MolToSmiles` cannot write. The
second lookup returned the first fragment's tree. Measured by disabling the lookup: the right name comes out.

What the tests pin, and why each is a separate test:

* the failing case, and its CONVERSE (R,R and S,S still merge into `bis[...]`), because "stop merging" would also pass the first;
* the same through `derived_name_for_structure`, since the app WITHHELD the wrong name and a fix is only visible there once
  the name is returned instead of refused;
* the premise (the two fragments print identically and the key tells them apart) and the WIRING (the session really holds
  one entry per distinct stamp), because a helper that is right but not used passes every other test;
* a miniature of the sweep that found the extent of the defect: every stereoisomer of seven substituent families on a
  1,3-phenylene, read back through OPSIN. Measured before the fix, over nine families and five parents: 56 of 2725 names read
  back as another stereoisomer, in exactly these seven families and all of them a same-family pair on a ring.

THE CITATION ORDER OF THE TWO PREFIXES IS PINNED ELSEWHERE. This file asserts what must hold in every spelling: the two
descriptors are both present and the name reads back to the structure. Which prefix is cited first when the two differ only
in their descriptors is P-45.6.3 (R precedes S, pdf p. 427), pinned by `test_namer_stereo_parents_and_citation.py`; when two
prefixes tie on their letters alone it is P-14.5.4 (the lowest locants at the first point of difference, pdf p. 82), which the
engine does not implement: the book's own `1-(pentan-2-yl)-4-(pentan-3-yl)benzene` comes out in the other order in 20 of 40
spellings.
"""
from __future__ import annotations

import re

import pytest
from rdkit import Chem, RDLogger
from rdkit.Chem import rdCIPLabeler
from rdkit.Chem.EnumerateStereoisomers import EnumerateStereoisomers

from openchem.chem.naming_providers import derived_name_for_structure, opsin_available
from openchem.vendor.iupac_namer import name_smiles
from openchem.vendor.iupac_namer.perception.extraction import carve_substituent, context_stereo_key
from openchem.vendor.iupac_namer.types import NamingSession, OutputForm
from tests.naming_spellings import checked_spellings

needs_opsin = pytest.mark.skipif(not opsin_available(), reason="needs the managed JRE and py2opsin")

RDLogger.DisableLog("rdApp.*")

# Each isomer's OWN SMILES (`MolToSmiles` of the enumerated molecule), and the CIP pair it is checked to have below.
R_S = "CC[C@@H](C)c1cccc([C@@H](C)CC)c1"
R_R = "CC[C@@H](C)c1cccc([C@H](C)CC)c1"
S_S = "CC[C@H](C)c1cccc([C@@H](C)CC)c1"

SEED = 20261006
N_SPELLINGS = 16


def _key(smiles: str) -> str:
    return Chem.MolToInchiKey(Chem.MolFromSmiles(smiles))


def _cip(smiles: str) -> list[str]:
    mol = Chem.MolFromSmiles(smiles)
    rdCIPLabeler.AssignCIPLabels(mol)
    return sorted(a.GetProp("_CIPCode") for a in mol.GetAtoms() if a.HasProp("_CIPCode"))


def _spellings(smiles: str, n: int = N_SPELLINGS) -> list[str]:
    """The structure written from other roots and in other atom orders, each CHECKED to be that structure.

    The check is the point: `MolToSmiles(doRandom=True)` on a molecule straight out of `EnumerateStereoisomers` writes a
    DIFFERENT stereoisomer, so a spelling must be parsed from the isomer's own SMILES and its InChIKey compared, or the
    test reports an instability that is the probe's and not the engine's. (`doRandom` is not used any more: it ignores the seed,
    so half of these were new on every run. See `tests/naming_spellings.py`.)
    """
    return checked_spellings(smiles, n, SEED)


def _read_back(names: list[str]) -> dict[str, str]:
    """`{name: InChIKey of what OPSIN reads it as}`; a name OPSIN cannot read maps to `""`."""
    from py2opsin import py2opsin

    unique = sorted(set(names))
    result = py2opsin(unique)
    result = result if isinstance(result, list) else [result]
    return {name: (_key(smiles) if smiles else "") for name, smiles in zip(unique, result)}


# ---------------------------------------------------------------------------
# The fixtures are the compounds they claim to be
# ---------------------------------------------------------------------------

def test_the_fixtures_are_the_stereoisomers_they_claim_to_be():
    assert _cip(R_S) == ["R", "S"]
    assert _cip(R_R) == ["R", "R"]
    assert _cip(S_S) == ["S", "S"]
    assert len({_key(R_S), _key(R_R), _key(S_S)}) == 3
    # each is the isomer's OWN SMILES, so a random spelling of it is still that isomer
    for smiles in (R_S, R_R, S_S):
        assert Chem.MolToSmiles(Chem.MolFromSmiles(smiles)) == smiles


# ---------------------------------------------------------------------------
# The failing case, and its converse
# ---------------------------------------------------------------------------

def test_the_r_s_compound_is_named_with_both_descriptors_in_every_spelling():
    """THE REPORTED DEFECT. Both prefixes must carry their own descriptor: one `(2R)` and one `(2S)`, never `bis`."""
    for spelling in _spellings(R_S):
        name = name_smiles(spelling)
        assert "bis[" not in name, f"{spelling}\n  {name}: two different substituents were merged into one"
        assert sorted(re.findall(r"\(2([RS])\)-butan-2-yl", name)) == ["R", "S"], f"{spelling}\n  {name}"


def test_the_canonical_spelling_gives_the_books_name():
    """The app names the CANONICAL SMILES (`derived_name_for_structure` canonicalises), so this is the name a user sees.

    The Blue Book's own example under P-14.4 (j). Since the prefixes are cited R before S (P-45.6.3) every spelling gives this name;
    `test_namer_stereo_parents_and_citation.py` pins that, and this one is the spelling the application names.
    """
    assert name_smiles(Chem.MolToSmiles(Chem.MolFromSmiles(R_S))) == "1-[(2R)-butan-2-yl]-3-[(2S)-butan-2-yl]benzene"


@pytest.mark.parametrize("smiles,expected", [
    (R_R, "1,3-bis[(2R)-butan-2-yl]benzene"),
    (S_S, "1,3-bis[(2S)-butan-2-yl]benzene"),
], ids=["R,R", "S,S"])
def test_two_substituents_with_the_same_descriptor_still_merge(smiles, expected):
    """THE CONVERSE. Identical substituents are still one `bis[...]`; the fix is not "never merge" and not "never cache"."""
    for spelling in _spellings(smiles):
        assert name_smiles(spelling) == expected, spelling


@needs_opsin
@pytest.mark.parametrize("smiles", [R_S, R_R, S_S], ids=["R,S", "R,R", "S,S"])
def test_every_name_reads_back_as_the_structure_it_was_made_from(smiles):
    """OPSIN is the arbiter: the old R,S names read back as the R,R and the S,S."""
    spellings = _spellings(smiles)
    names = [name_smiles(s) for s in spellings]
    back = _read_back(names)
    want = _key(smiles)
    wrong = sorted({f"{name!r} reads back as another structure" for name in names if back[name] != want})
    assert not wrong, "\n".join(wrong)


@needs_opsin
def test_the_app_returns_the_name_instead_of_withholding_it():
    """`derived_name_for_structure` raised "describes a different stereoisomer" for this compound; it must now answer, and
    the answer must have been VERIFIED (an empty note: no "not verified", no "does not express stereochemistry")."""
    result = derived_name_for_structure(Chem.MolFromSmiles(R_S))
    assert result.name == "1-[(2R)-butan-2-yl]-3-[(2S)-butan-2-yl]benzene"
    assert not result.note, result.note


# ---------------------------------------------------------------------------
# The mechanism: the premise, the key, and the wiring
# ---------------------------------------------------------------------------

def _carved_substituents(smiles: str):
    """The two sec-butyl fragments cut from the ring, as the engine carves them."""
    mol = Chem.MolFromSmiles(smiles)
    fragments = []
    for bond in mol.GetBonds():
        a, b = bond.GetBeginAtom(), bond.GetEndAtom()
        if a.GetIsAromatic() != b.GetIsAromatic():
            ring, side = (a, b) if a.GetIsAromatic() else (b, a)
            fragments.append(carve_substituent(mol, frozenset(), (ring.GetIdx(), side.GetIdx())))
    assert len(fragments) == 2
    return fragments


def test_the_two_fragments_print_identically_and_only_the_key_tells_them_apart():
    """THE PREMISE. If a SMILES ever starts carrying the stereo, this fails and says the cause has moved, instead of the
    other tests quietly passing for a different reason."""
    (frag_a, att_a, _), (frag_b, att_b, _) = _carved_substituents(R_S)
    assert Chem.MolToSmiles(frag_a) == Chem.MolToSmiles(frag_b) == "CCCC"
    assert att_a == att_b
    assert context_stereo_key(frag_a) != context_stereo_key(frag_b)


def test_equal_inherited_descriptors_share_a_key_so_the_cache_still_hits():
    (frag_a, _, _), (frag_b, _, _) = _carved_substituents(R_R)
    assert Chem.MolToSmiles(frag_a) == Chem.MolToSmiles(frag_b)
    # the two were carved from different atoms of the parent, so a key that included WHERE they came from would split them
    assert context_stereo_key(frag_a) == context_stereo_key(frag_b) != ""


def test_a_fragment_that_inherits_nothing_keeps_the_key_it_always_had():
    """No stamp, no suffix: every molecule that was never carved from a stereo parent is keyed exactly as before."""
    assert context_stereo_key(Chem.MolFromSmiles("CCCC")) == ""
    assert context_stereo_key(Chem.MolFromSmiles("C[C@H](O)CC")) == ""  # its own chirality is in its SMILES already


def test_atom_and_bond_stamps_are_both_in_the_key():
    """The namer reads both (`perception/stereo.py`). A bond stamp is not what the reported shape needed -- an alkene
    fragment keeps an explicit [H], so its SMILES already differs -- but a key that left it out would be the same defect
    waiting for a fragment that loses that [H]."""
    mol = Chem.MolFromSmiles("CC=CC")
    plain = context_stereo_key(mol)
    atom_r, atom_s, bond_e, bond_z = (Chem.Mol(mol) for _ in range(4))
    atom_r.GetAtomWithIdx(1).SetProp("_ParentCIPCode", "R")
    atom_s.GetAtomWithIdx(1).SetProp("_ParentCIPCode", "S")
    bond_e.GetBondWithIdx(1).SetProp("_ParentCIPCode", "E")
    bond_z.GetBondWithIdx(1).SetProp("_ParentCIPCode", "Z")
    keys = [context_stereo_key(m) for m in (atom_r, atom_s, bond_e, bond_z)]
    assert plain == "" and "" not in keys
    assert len(set(keys)) == 4


def _substituent_stores(monkeypatch, smiles: str) -> list[str]:
    """The cache keys the plain `CCCC` substituent is stored under while `smiles` is named."""
    stores: list[str] = []
    real = NamingSession.cache_store

    def spy(self, key, form, fv_bond_orders, tree, attachment_indices=None):
        if form is OutputForm.SUBSTITUENT and key.split("|")[0] == "CCCC":
            stores.append(key)
        return real(self, key, form, fv_bond_orders, tree, attachment_indices)

    # A CONTEXT, so the spy is undone before the next call: two spies on one test would stack, and the first call's list
    # would then collect the second structure's stores too.
    with monkeypatch.context() as patched:
        patched.setattr(NamingSession, "cache_store", spy)
        name_smiles(smiles)
    return stores


def test_the_session_holds_one_entry_per_distinct_stamp(monkeypatch):
    """THE WIRING, not the helper: `_name_bound` has 45 cache calls and every one has to use the key. R,S is two entries,
    R,R is one, and in both each entry is stored ONCE (a second store of the same key would be a lookup that missed)."""
    unlike = _substituent_stores(monkeypatch, R_S)
    like = _substituent_stores(monkeypatch, R_R)
    assert len(set(unlike)) == 2 and len(unlike) == 2, unlike
    assert len(set(like)) == 1 and len(like) == 1, like


def test_every_session_cache_call_in_the_engine_uses_that_key():
    """`_name_bound` has 45 cache calls and returns from 45 places; the test above reaches only the stores these molecules
    reach. One that still wrote under the bare SMILES would leave a stamped fragment's tree under the key an UNSTAMPED
    fragment of the same SMILES looks up, in the same session. So every call is read out of the syntax tree: a comment or a
    docstring that mentions `cache_store(smiles` can neither satisfy this nor fail it."""
    import ast

    from openchem.vendor.iupac_namer import engine

    with open(engine.__file__, encoding="utf-8") as fh:
        module = ast.parse(fh.read())
    calls = [
        node for node in ast.walk(module)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr in ("cache_store", "cache_lookup")
    ]
    assert calls, "no session cache call was found at all, so this guard would pass whatever the engine does"
    bare = [
        f"engine.py line {call.lineno}" for call in calls
        if not (call.args and isinstance(call.args[0], ast.Name) and call.args[0].id == "fragment_key")
    ]
    assert not bare, f"a session cache call that does not use `fragment_key`: {bare}"


# ---------------------------------------------------------------------------
# The extent: a miniature of the sweep that measured it
# ---------------------------------------------------------------------------

# Substituents written so the FIRST atom is the one bonded to the ring (ring digits kept clear of the parent's own).
FAMILIES = {
    "butan-2-yl": "C(C)CC",
    "1-chloroethyl": "C(C)Cl",
    "1-phenylethyl": "C(C)c7ccccc7",
    "2-methylbutyl": "CC(C)CC",
    "3-methylpentan-2-yl": "C(C)C(C)CC",
    "1-methoxyethyl": "C(C)OC",
    "1-fluoropropyl": "C(F)CC",
}


@needs_opsin
@pytest.mark.parametrize("family", FAMILIES, ids=list(FAMILIES))
def test_no_stereoisomer_of_a_like_pair_on_a_ring_is_named_as_another(family):
    """Every stereoisomer of the family on both sides of a 1,3-phenylene, three spellings each, read back through OPSIN.

    Measured on the tree before the fix, with nine families over five parents: 56 wrong-isomer names in 2725, every one a
    pair of the SAME family on the ring (a pair on an amine, ether or sulfide has one substituent that becomes the parent,
    so nothing is merged, and a pair of different families does not collide). The two families left out here, oxolan-2-yl
    and 2-methylcyclohexyl, had no wrong name; they only vary in which equivalent half is the parent.
    """
    sub = FAMILIES[family]
    flat = Chem.MolFromSmiles(f"c1({sub})cccc({sub})c1")
    assert flat is not None
    jobs: list[tuple[str, str]] = []  # (the isomer's own SMILES, a spelling of it)
    for iso in EnumerateStereoisomers(flat):
        own = Chem.MolToSmiles(iso)
        for spelling in _spellings(own, n=2):
            jobs.append((own, spelling))
    names = [name_smiles(spelling) for _own, spelling in jobs]
    back = _read_back(names)
    wrong = [
        f"{own}\n   {name}\n   reads back as another structure"
        for (own, _spelling), name in zip(jobs, names)
        if back[name] != _key(own)
    ]
    assert not wrong, "\n".join(sorted(set(wrong)))
