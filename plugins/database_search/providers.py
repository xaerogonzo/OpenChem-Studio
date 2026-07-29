from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

REQUEST_TIMEOUT_SECONDS = 15


@dataclass(slots=True)
class SearchResult:
    source: str
    external_id: str
    name: str
    smiles: str
    molecular_formula: str | None
    molecular_weight: float | None


class DatabaseSearchError(Exception):
    """Raised when a search can't be completed — a network/HTTP failure, a
    timeout, or a rate-limit response. Always caught by the panel and shown
    as an inline message, never allowed to propagate into a crash.
    """


class DatabaseSearchProvider(ABC):
    """Plugin-local provider abstraction, deliberately generic over "a
    chemical database with a REST API" — a future PDB/DrugBank/BindingDB/
    local-database provider slots in the same way `PubChemProvider`/
    `ChEMBLProvider` do.
    """

    source: str

    @abstractmethod
    def search(self, query: str, query_type: str) -> list[SearchResult]:
        """`query_type` is one of "name", "smiles", "inchikey"."""


class PubChemProvider(DatabaseSearchProvider):
    source = "PubChem"

    _QUERY_TYPE_TO_NAMESPACE = {"name": "name", "smiles": "smiles", "inchikey": "inchikey"}
    # PubChem's PUG REST silently renamed this property: requesting
    # "CanonicalSMILES" still works, but as of the current API the response
    # key comes back as "ConnectivitySMILES" instead (confirmed against the
    # live API, not documentation) — MolecularWeight also comes back as a
    # numeric string ("180.16"), not a JSON number.
    _PROPERTIES = "MolecularFormula,MolecularWeight,CanonicalSMILES,IUPACName"

    def search(self, query: str, query_type: str) -> list[SearchResult]:
        namespace = self._QUERY_TYPE_TO_NAMESPACE.get(query_type)
        if namespace is None:
            raise DatabaseSearchError(f"PubChem does not support query type: {query_type}")

        try:
            import requests
        except ImportError as exc:
            raise DatabaseSearchError(
                "The 'requests' package is not installed. Run: uv sync --extra network"
            ) from exc

        url = (
            f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/{namespace}/{query}/"
            f"property/{self._PROPERTIES}/JSON"
        )
        try:
            response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            if response.status_code == 429:
                raise DatabaseSearchError("PubChem rate limit reached — try again shortly.")
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.Timeout as exc:
            raise DatabaseSearchError("PubChem request timed out.") from exc
        except requests.exceptions.RequestException as exc:
            raise DatabaseSearchError(f"PubChem request failed: {exc}") from exc

        properties = data.get("PropertyTable", {}).get("Properties", [])
        results = []
        for prop in properties:
            smiles = prop.get("ConnectivitySMILES") or prop.get("CanonicalSMILES")
            if not smiles:
                continue
            mw = prop.get("MolecularWeight")
            results.append(
                SearchResult(
                    source=self.source,
                    external_id=str(prop.get("CID", "")),
                    name=prop.get("IUPACName") or f"CID {prop.get('CID')}",
                    smiles=smiles,
                    molecular_formula=prop.get("MolecularFormula"),
                    molecular_weight=float(mw) if mw not in (None, "") else None,
                )
            )
        return results


class ChEMBLProvider(DatabaseSearchProvider):
    source = "ChEMBL"

    def search(self, query: str, query_type: str) -> list[SearchResult]:
        try:
            import requests
        except ImportError as exc:
            raise DatabaseSearchError(
                "The 'requests' package is not installed. Run: uv sync --extra network"
            ) from exc

        params = self._build_params(query, query_type)
        url = "https://www.ebi.ac.uk/chembl/api/data/molecule.json"
        try:
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
            if response.status_code == 429:
                raise DatabaseSearchError("ChEMBL rate limit reached — try again shortly.")
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.Timeout as exc:
            raise DatabaseSearchError("ChEMBL request timed out.") from exc
        except requests.exceptions.RequestException as exc:
            raise DatabaseSearchError(f"ChEMBL request failed: {exc}") from exc

        results = []
        for molecule in data.get("molecules", []):
            structures = molecule.get("molecule_structures") or {}
            smiles = structures.get("canonical_smiles")
            if not smiles:
                continue
            properties = molecule.get("molecule_properties") or {}
            mw = properties.get("full_mwt")
            results.append(
                SearchResult(
                    source=self.source,
                    external_id=molecule.get("molecule_chembl_id", ""),
                    name=molecule.get("pref_name") or molecule.get("molecule_chembl_id", ""),
                    smiles=smiles,
                    molecular_formula=properties.get("full_molformula"),
                    molecular_weight=float(mw) if mw not in (None, "") else None,
                )
            )
        return results

    def _build_params(self, query: str, query_type: str) -> dict[str, str]:
        if query_type == "name":
            return {"pref_name__icontains": query, "format": "json"}
        if query_type == "smiles":
            return {"molecule_structures__canonical_smiles__flexmatch": query, "format": "json"}
        if query_type == "inchikey":
            return {"molecule_structures__standard_inchi_key": query, "format": "json"}
        raise DatabaseSearchError(f"ChEMBL does not support query type: {query_type}")


def build_default_providers() -> dict[str, DatabaseSearchProvider]:
    return {
        "PubChem": PubChemProvider(),
        "ChEMBL": ChEMBLProvider(),
    }
