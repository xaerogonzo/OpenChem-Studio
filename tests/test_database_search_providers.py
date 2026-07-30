from __future__ import annotations

from unittest.mock import MagicMock, patch

import database_search.providers as providers_mod
import pytest


def _fake_response(json_data, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data
    response.raise_for_status.return_value = None
    return response


def test_pubchem_provider_builds_request_and_parses_response():
    # Matches the real PUG REST response shape (verified live): even though
    # "CanonicalSMILES" is requested, the key comes back as
    # "ConnectivitySMILES", and MolecularWeight comes back as a numeric
    # string, not a JSON number.
    provider = providers_mod.PubChemProvider()
    payload = {
        "PropertyTable": {
            "Properties": [
                {
                    "CID": 2244,
                    "MolecularFormula": "C9H8O4",
                    "MolecularWeight": "180.16",
                    "ConnectivitySMILES": "CC(=O)OC1=CC=CC=C1C(=O)O",
                    "IUPACName": "2-acetyloxybenzoic acid",
                }
            ]
        }
    }
    with patch("requests.get", return_value=_fake_response(payload)) as mock_get:
        results = provider.search("aspirin", "name")

    assert len(results) == 1
    result = results[0]
    assert result.source == "PubChem"
    assert result.external_id == "2244"
    assert result.name == "2-acetyloxybenzoic acid"
    assert result.smiles == "CC(=O)OC1=CC=CC=C1C(=O)O"
    assert result.molecular_formula == "C9H8O4"
    assert result.molecular_weight == 180.16
    args, kwargs = mock_get.call_args
    assert "compound/name/aspirin/property" in args[0]
    assert kwargs["timeout"] == providers_mod.REQUEST_TIMEOUT_SECONDS


def test_pubchem_provider_falls_back_to_canonical_smiles_key():
    provider = providers_mod.PubChemProvider()
    payload = {
        "PropertyTable": {
            "Properties": [
                {"CID": 1, "CanonicalSMILES": "O", "MolecularFormula": "H2O", "MolecularWeight": "18.02"}
            ]
        }
    }
    with patch("requests.get", return_value=_fake_response(payload)):
        results = provider.search("water", "name")
    assert results[0].smiles == "O"


def test_pubchem_provider_unknown_query_type_raises():
    provider = providers_mod.PubChemProvider()
    with pytest.raises(providers_mod.DatabaseSearchError):
        provider.search("aspirin", "cas_number")


def test_pubchem_provider_rate_limit_raises_clear_error():
    provider = providers_mod.PubChemProvider()
    with patch("requests.get", return_value=_fake_response({}, status_code=429)):
        with pytest.raises(providers_mod.DatabaseSearchError, match="rate limit"):
            provider.search("aspirin", "name")


def test_pubchem_provider_wraps_request_exceptions():
    import requests

    provider = providers_mod.PubChemProvider()
    with patch("requests.get", side_effect=requests.exceptions.Timeout("slow")):
        with pytest.raises(providers_mod.DatabaseSearchError, match="timed out"):
            provider.search("aspirin", "name")


def test_chembl_provider_builds_request_and_parses_response():
    provider = providers_mod.ChEMBLProvider()
    payload = {
        "molecules": [
            {
                "molecule_chembl_id": "CHEMBL25",
                "pref_name": "ASPIRIN",
                "molecule_structures": {"canonical_smiles": "CC(=O)Oc1ccccc1C(=O)O"},
                "molecule_properties": {"full_molformula": "C9H8O4", "full_mwt": "180.16"},
            }
        ]
    }
    with patch("requests.get", return_value=_fake_response(payload)) as mock_get:
        results = provider.search("aspirin", "name")

    assert len(results) == 1
    result = results[0]
    assert result.source == "ChEMBL"
    assert result.external_id == "CHEMBL25"
    assert result.name == "ASPIRIN"
    assert result.smiles == "CC(=O)Oc1ccccc1C(=O)O"
    assert result.molecular_formula == "C9H8O4"
    assert result.molecular_weight == 180.16
    _, kwargs = mock_get.call_args
    assert kwargs["params"]["pref_name__icontains"] == "aspirin"


def test_chembl_provider_skips_molecules_without_smiles():
    provider = providers_mod.ChEMBLProvider()
    payload = {"molecules": [{"molecule_chembl_id": "CHEMBL1", "molecule_structures": {}}]}
    with patch("requests.get", return_value=_fake_response(payload)):
        results = provider.search("x", "name")
    assert results == []


def test_build_default_providers_has_two_sources():
    provider_map = providers_mod.build_default_providers()
    assert set(provider_map) == {"PubChem", "ChEMBL"}
