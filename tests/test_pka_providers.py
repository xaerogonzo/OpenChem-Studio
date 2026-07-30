from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.pka_providers import compute_pka, pka_predictor_available, protonate_at_ph


def test_acetic_acid_is_neutral_at_low_ph():
    mol = Chem.MolFromSmiles("CC(=O)O")
    protonated = protonate_at_ph(mol, 2.0)
    assert Chem.MolToSmiles(protonated) == Chem.CanonSmiles("CC(=O)O")


def test_acetic_acid_is_deprotonated_at_physiological_ph():
    """Acetic acid's real pKa is ~4.76 -- deprotonated well above that,
    confirmed live against the actual Dimorphite-DL install."""
    mol = Chem.MolFromSmiles("CC(=O)O")
    protonated = protonate_at_ph(mol, 7.4)
    assert Chem.MolToSmiles(protonated) == Chem.CanonSmiles("CC(=O)[O-]")


def test_acetic_acid_stays_deprotonated_at_high_ph():
    mol = Chem.MolFromSmiles("CC(=O)O")
    protonated = protonate_at_ph(mol, 12.0)
    assert Chem.MolToSmiles(protonated) == Chem.CanonSmiles("CC(=O)[O-]")


def test_pka_predictor_available_reflects_the_real_install_state():
    """pkasolver's own dependency chain (torch-geometric -> torch-scatter/
    torch-sparse) has no pre-built wheel on this machine and needs an
    MSVC compiler to build from source, which isn't present (confirmed
    live during the Phase 18 install spike) -- False is the honest,
    current answer, not a hardcoded stub."""
    assert pka_predictor_available() is False


def test_compute_pka_returns_none_when_predictor_unavailable():
    mol = Chem.MolFromSmiles("CC(=O)O")
    assert compute_pka(mol) is None


def test_compute_pka_raises_clearly_if_predictor_becomes_available_but_unimplemented(monkeypatch):
    """If a future pkasolver install spike succeeds, compute_pka must fail
    loudly (NotImplementedError) rather than silently pretend to work --
    this pins that contract so it can't regress into a silent no-op."""
    import openchem.chem.pka_providers as pka_providers

    monkeypatch.setattr(pka_providers, "pka_predictor_available", lambda: True)
    mol = Chem.MolFromSmiles("CC(=O)O")

    with pytest.raises(NotImplementedError):
        compute_pka(mol)
