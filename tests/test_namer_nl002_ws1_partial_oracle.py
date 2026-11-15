"""NL-002 partial oracle (WS1, 2026-11-15).

The representative ``9-chlorobicyclo[3.3.1]nonan-1-ol`` is still a **validator limit**: OPSIN cannot anchor
bridgehead R/S and the emitted name is flat. There is no book PIN or CIP-suite row on that exact skeleton
(``benchmarks/naming/BLUEBOOK_V3.md``, ``CIP_VALIDATION_SUITE.md``).

This file pins the evidence chain:

1. **Validator limit** — four embeddable isomers, one flat name (see also
   ``tests/test_namer_nl001_nl005_ws1_validator_evidence.py``).
2. **Engine descriptors on NL-002** — before OPSIN strips them, each isomer gets a distinct name; those
   descriptors agree with RDKit's whole-molecule CIP labeller on every cited centre.
3. **Same code path, independent oracles** — five CIP Validation Suite entries under P-93.5.2 (norbornane /
   tropane; Hanson *et al.*, *J. Chem. Inf. Model.* **2018**, 58, 1755) agree with the engine's pre-validation
   descriptors by multiset (same approach as NL-001 / NL-109 suite pins).
4. **Book analogue** — Blue Book V3 P-93.5.2.1 p. 929 cites full R/S on a substituted adamantan-1-ol with a
   remote halogen. Round 89 already pins ``5-methylbicyclo[2.2.2]octan-2-ol`` (bridgehead alcohol + remote methyl
   on a cage); here we check pre-validation R/S against RDKit on that skeleton — analogue chemistry, not NL-002.

Residual risk: no worked example on plain bicyclo[3.3.1]nonane with 1-ol and 9-Cl.
"""

from __future__ import annotations

import re
from collections import Counter

import pytest
from rdkit import Chem, RDLogger
from rdkit.Chem import rdCIPLabeler
from rdkit.Chem.EnumerateStereoisomers import EnumerateStereoisomers, StereoEnumerationOptions

import openchem.vendor.iupac_namer.engine as engine
from openchem.vendor.iupac_namer import name_smiles
from openchem.vendor.iupac_namer.assembly import assemble
from openchem.vendor.iupac_namer.strategy import default_strategy

RDLogger.DisableLog("rdApp.*")

NL002_FLAT = "9-chlorobicyclo[3.3.1]nonan-1-ol"
NL002_UNCHIRAL = "OC12CCCC(CCC1)C2Cl"

# CIP Validation Suite SMILES + author labels (commit pinned in CIP_VALIDATION_SUITE.md).
BRIDGEHEAD_SUITE = [
    ("VS111", "F[C@H]1[C@@H]2C[C@H]([C@H]1CC2)Br", "2S 3S 5R 6S"),
    ("VS159", "C[C@@H]1[C@@H]2C[C@]([C@H]1C=C2)(C)Br", "2R 3R 5S 6S"),
    ("VS235", "CN1[C@@H]2C[C@H](C[C@H]1CC2)OC([C@H](CO)C=3C=CC=CC3)=O", "3S 5r 7R 12S"),
    ("VS238", "C[C@H]1[C@H]2CCC[C@@H]1CC2", "2s 3S 7R"),
    ("VS241", "O[C@H]1C[C@H]2N[C@@H](C1)CC2", "2s 4S 6R"),
]

# Cage bridgehead alcohol + remote substituent (round 89 pin; book analogue — Blue Book V3 p. 929).
CAGE_BRIDGEHEAD_ALCOHOL = (
    "(1R,2R,4R,5S)-5-methylbicyclo[2.2.2]octan-2-ol",
    "C[C@H]1C[C@H]2CC[C@@H]1C[C@H]2O",
)


def _descriptor_counter(name: str) -> Counter[str]:
    found: Counter[str] = Counter()
    for group in re.findall(r"\(([^()]*)\)", name):
        for token in group.split(","):
            match = re.fullmatch(r"\d+[a-z]?'*([RSrsEZ])", token.strip())
            if match:
                found[match.group(1)] += 1
    return found


def _suite_want(labels: str) -> Counter[str]:
    want: Counter[str] = Counter()
    for token in labels.split():
        match = re.fullmatch(r"(\d+)([RSrsEZ])", token)
        assert match, token
        want[match.group(2)] += 1
    return want


def _pre_validation_name(smiles: str) -> str:
    tree = engine.name(Chem.MolFromSmiles(smiles), default_strategy())
    return assemble(tree)


def _embeddable_nl002_isomers() -> list[str]:
    opts = StereoEnumerationOptions(tryEmbedding=True, unique=True, onlyUnassigned=True, maxIsomers=16)
    mol = Chem.MolFromSmiles(NL002_UNCHIRAL)
    return [Chem.MolToSmiles(m) for m in EnumerateStereoisomers(mol, options=opts)]


def _disagreements_with_rdkit(smiles: str, pre_name: str) -> list[str]:
    """Every descriptor in the pre-validation name must match RDKit CIP on that atom."""
    mol = Chem.MolFromSmiles(smiles)
    rdCIPLabeler.AssignCIPLabels(mol)
    label = {atom.GetIdx(): atom.GetProp("_CIPCode") for atom in mol.GetAtoms() if atom.HasProp("_CIPCode")}
    tree = engine.name(mol, default_strategy())
    assert assemble(tree) == pre_name
    problems: list[str] = []
    described: list[int] = []
    for descriptor in tree.stereo_descriptors or ():
        atom = descriptor.stereo_center.atom_idx
        described.append(atom)
        if label.get(atom) != descriptor.descriptor:
            problems.append(
                f"atom {atom}: name says {descriptor.locant}{descriptor.descriptor}, RDKit says {label.get(atom)}"
            )
    if sorted(described) != sorted(label):
        problems.append(f"name cites atoms {sorted(described)}; RDKit labels {sorted(label)}")
    return problems


@pytest.mark.parametrize("sid,smiles,labels", BRIDGEHEAD_SUITE, ids=[row[0] for row in BRIDGEHEAD_SUITE])
def test_cip_suite_bridgehead_pre_validation_descriptors_match_suite_labels(sid, smiles, labels):
    del sid
    pre = _pre_validation_name(smiles)
    assert _descriptor_counter(pre) == _suite_want(labels), (pre, labels)


def test_nl002_four_embeddable_isomers_share_one_flat_name_but_distinct_pre_validation_names():
    isomers = _embeddable_nl002_isomers()
    assert len(isomers) == 4
    finals = {name_smiles(s) for s in isomers}
    pres = {_pre_validation_name(s) for s in isomers}
    assert finals == {NL002_FLAT}
    assert len(pres) == 4


@pytest.mark.parametrize("smiles", _embeddable_nl002_isomers(), ids=[f"iso{i}" for i in range(4)])
def test_nl002_pre_validation_descriptors_agree_with_rdkit_per_atom(smiles):
    pre = _pre_validation_name(smiles)
    assert _disagreements_with_rdkit(smiles, pre) == []


def test_cage_bridgehead_alcohol_analogue_pre_validation_agrees_with_rdkit():
    expected, smiles = CAGE_BRIDGEHEAD_ALCOHOL
    pre = _pre_validation_name(smiles)
    assert pre == expected
    assert _disagreements_with_rdkit(smiles, pre) == []