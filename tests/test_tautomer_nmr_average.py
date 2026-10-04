"""The population-weighted fast-exchange average of tautomer NMR (P5, step 3): the rule and when there is none.

Real tautomers of cyclohexanone (keto and enol) give real heavy-atom correspondence and real hydrogen counts; the
shifts are synthetic and known, so every expected value is hand-computable.
"""

from __future__ import annotations

import dataclasses

import pytest
from rdkit import Chem

from openchem.chem.tautomer_distribution import MODEL_POLICY_SINGLE, generate_tautomer_candidates
from openchem.chem.tautomer_nmr import average_tautomer_nmr
from openchem.domain.common import Provenance
from openchem.domain.scientific_result import (
    NMRSpectrumResult,
    StructureEntry,
    StructureSetResult,
    TautomerNmrEntry,
    TautomerNmrResult,
)

PARENT = "dist-run-1"
POPULATIONS = (0.8, 0.2)


def _tautomers():
    candidates, failures = generate_tautomer_candidates(
        Chem.MolFromSmiles("O=C1CCCCC1"), policy=MODEL_POLICY_SINGLE
    )
    assert failures == 0 and len(candidates) == 2
    return candidates


def _shift(mol, atom, tautomer_index):
    symbol = mol.GetAtomWithIdx(atom).GetSymbol()
    base = {"C": 100.0 + atom, "H": 1.0 + 0.01 * atom, "O": 0.0}[symbol]
    return base + 5.0 * tautomer_index  # tautomers differ, so an average is not a copy


def _build(*, branch="validated", complete=True, parent=PARENT, populations=POPULATIONS, units="ppm",
           spectrum_type="nmr_shifts", fail=None, store_geometry=True):
    candidates = _tautomers()
    entries, nmr_entries = [], []
    for index, candidate in enumerate(candidates):
        metadata = {
            "fingerprint": candidate.fingerprint, "tautomer_fingerprint": candidate.tautomer_fingerprint,
            "status": "succeeded", "is_lowest_calculated_for_tautomer": True,
        }
        if store_geometry:
            metadata["optimized_molblock"] = Chem.MolToMolBlock(candidate.mol)
        entries.append(StructureEntry(molblock="2D", label=f"T{index}", score=populations[index], metadata=metadata))
        mol = Chem.MolFromMolBlock(Chem.MolToMolBlock(candidate.mol), removeHs=False)
        values = {a.GetIdx(): _shift(mol, a.GetIdx(), index) for a in mol.GetAtoms() if a.GetSymbol() in "CH"}
        spectrum = NMRSpectrumResult(
            spectrum_type=spectrum_type, name="n", units=units, method="orca", molecule_uuid="m", values=values,
            elements={i: mol.GetAtomWithIdx(i).GetSymbol() for i in values},
        )
        nmr_entries.append(TautomerNmrEntry(
            candidate.tautomer_fingerprint, f"T{index}", "2D", (candidate.fingerprint,), (1.0,),
            None if fail == index else spectrum, "failed" if fail == index else "",
        ))
    distribution = StructureSetResult(
        set_id="orca.tautomer_distribution", name="d", method="orca", molecule_uuid="m", entries=entries,
        provenance=Provenance(created_by="core", method="orca", parameters={
            "validation_branch": branch, "complete": complete, "parent_run_id": PARENT,
        }),
    )
    nmr = TautomerNmrResult(molecule_uuid="m", run_id="nmr-run", parent_run_id=parent, method_basis="x",
                            per_conformer=False, entries=tuple(nmr_entries))
    return nmr, distribution, candidates


def _mol(candidate):
    return Chem.MolFromMolBlock(Chem.MolToMolBlock(candidate.mol), removeHs=False)


def _hcount(mol, heavy):
    return sum(1 for n in mol.GetAtomWithIdx(heavy).GetNeighbors() if n.GetAtomicNum() == 1)


def test_every_carbon_gets_the_weighted_mean_of_its_13c_shift():
    nmr, distribution, candidates = _build()
    average = average_tautomer_nmr(nmr, distribution)
    assert average.available and average.weights == tuple(
        (c.tautomer_fingerprint, w) for c, w in zip(candidates, POPULATIONS, strict=True)
    )
    mol = _mol(candidates[0])
    carbons = [a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "C"]
    by_atom = {p.heavy_atom: p for p in average.peaks if p.nucleus == "13C"}
    assert sorted(by_atom) == sorted(carbons)
    for carbon in carbons:
        expected = 0.8 * (100.0 + carbon) + 0.2 * (105.0 + carbon)
        assert by_atom[carbon].shift_ppm == pytest.approx(expected)
        assert [fp for fp, _ in by_atom[carbon].per_tautomer] == [c.tautomer_fingerprint for c in candidates]


def test_a_carbons_protons_are_averaged_only_when_its_hydrogen_count_is_the_same_in_every_tautomer():
    nmr, distribution, candidates = _build()
    mols = [_mol(c) for c in candidates]
    average = average_tautomer_nmr(nmr, distribution)
    stable = [h for h in range(mols[0].GetNumAtoms())
              if mols[0].GetAtomWithIdx(h).GetSymbol() == "C" and 0 < _hcount(mols[0], h) == _hcount(mols[1], h)]
    changing = [h for h in range(mols[0].GetNumAtoms())
                if mols[0].GetAtomWithIdx(h).GetSymbol() == "C" and _hcount(mols[0], h) != _hcount(mols[1], h)]
    assert stable and changing  # the enol's alpha carbon is the changing one
    peaks = {p.heavy_atom: p for p in average.peaks if p.nucleus == "1H"}
    assert sorted(peaks) == sorted(stable)
    for carbon in stable:
        per = []
        for index, mol in enumerate(mols):
            hs = [n.GetIdx() for n in mol.GetAtomWithIdx(carbon).GetNeighbors() if n.GetAtomicNum() == 1]
            per.append(sum(_shift(mol, h, index) for h in hs) / len(hs))
        assert peaks[carbon].shift_ppm == pytest.approx(0.8 * per[0] + 0.2 * per[1])
        assert peaks[carbon].hydrogen_count == _hcount(mols[0], carbon)
    reported = {n.heavy_atom: n for n in average.not_averaged if n.nucleus == "1H" and n.element == "C"}
    assert sorted(reported) == sorted(changing)
    assert all("changes between tautomers" in n.reason for n in reported.values())


def test_hydrogens_on_oxygen_are_never_averaged_and_are_named():
    nmr, distribution, candidates = _build()
    average = average_tautomer_nmr(nmr, distribution)
    oxygens = [n for n in average.not_averaged if n.element == "O"]
    assert len(oxygens) == 1 and "exchanges with solvent" in oxygens[0].reason
    assert all(p.element == "C" for p in average.peaks)  # nothing on a heteroatom is a peak


def test_it_uses_the_validated_populations_and_nothing_else():
    nmr, distribution, _ = _build(populations=(0.5, 0.5))
    average = average_tautomer_nmr(nmr, distribution)
    peak = next(p for p in average.peaks if p.nucleus == "13C")
    assert peak.shift_ppm == pytest.approx(0.5 * peak.per_tautomer[0][1] + 0.5 * peak.per_tautomer[1][1])


@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        ({"branch": "unvalidated"}, "not validated"),
        ({"branch": "ranking_only"}, "not validated"),
        ({"complete": False}, "incomplete"),
        ({"parent": "some-other-run"}, "not computed from this tautomer distribution"),
        ({"parent": ""}, "not computed from this tautomer distribution"),
        ({"fail": 1}, "not every tautomer"),
        ({"spectrum_type": "nmr_raw_shielding"}, "not referenced"),
        ({"units": "ppm (isotropic shielding)"}, "not referenced"),
        ({"populations": (0.7, 0.2)}, "do not sum to one"),
        ({"store_geometry": False}, "not stored"),
    ],
)
def test_there_is_no_average_unless_every_ingredient_is_in_place(kwargs, fragment):
    nmr, distribution, _ = _build(**kwargs)
    average = average_tautomer_nmr(nmr, distribution)
    assert average.available is False and fragment in average.reason
    assert average.peaks == () and average.not_averaged == ()  # never a partial average


def test_an_incomplete_nmr_result_with_skipped_tautomers_is_refused():
    nmr, distribution, _ = _build()
    skipped = dataclasses.replace(nmr, skipped=("T3: not stored",))
    assert "not every tautomer" in average_tautomer_nmr(skipped, distribution).reason


def test_tautomers_whose_heavy_atoms_do_not_correspond_cannot_be_paired():
    nmr, distribution, candidates = _build()
    other = Chem.AddHs(Chem.MolFromSmiles("CCCCCC=O"))  # same atom count class, different skeleton
    from rdkit.Chem import AllChem

    AllChem.EmbedMolecule(other, randomSeed=3)
    entries = list(distribution.entries)
    metadata = dict(entries[1].metadata, optimized_molblock=Chem.MolToMolBlock(other))
    entries[1] = dataclasses.replace(entries[1], metadata=metadata)
    swapped = dataclasses.replace(distribution, entries=entries)
    assert "heavy atoms do not correspond" in average_tautomer_nmr(nmr, swapped).reason
