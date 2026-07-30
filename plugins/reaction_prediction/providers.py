from __future__ import annotations

import itertools
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import platformdirs

REQUEST_TIMEOUT_SECONDS = 30

# Same appname/appauthor PluginManager already uses for its default user
# plugin directory (src/openchem/plugins/manager.py) — reused here so a
# user has one predictable "OpenChemStudio" app-data location, not a
# second, differently-named one just for reaction templates.
USER_TEMPLATES_PATH = (
    Path(platformdirs.user_data_dir("OpenChemStudio", appauthor=False)) / "reaction_templates.json"
)


@dataclass(slots=True)
class ReactionPrediction:
    product_smiles: str
    confidence: float | None
    source_label: str


@dataclass(slots=True)
class _ReactionTemplate:
    name: str
    smarts: str


class ReactionPredictionError(Exception):
    """Raised when a prediction can't be produced — bad reactant SMILES, a
    missing/bad API key, or a network/API failure for the remote provider.
    Always caught by the panel and shown as an inline message, never
    allowed to propagate into a crash.
    """


class ReactionPredictor(ABC):
    """Plugin-local provider abstraction (not part of `openchem.plugins.
    interfaces` — core never needs to know this exists, same reasoning as
    `ai_assistant`'s `AIProvider`)."""

    provider_id: str

    @abstractmethod
    def predict(self, reactant_smiles: list[str]) -> list[ReactionPrediction]:
        """Predict likely product(s) for the given reactants."""


def _load_templates_file(path: Path) -> list[_ReactionTemplate]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [_ReactionTemplate(name=entry["name"], smarts=entry["smarts"]) for entry in data]


class RDKitTemplateProvider(ReactionPredictor):
    """Always available, zero config: applies a small library of named
    reaction SMARTS via RDKit's reaction machinery. Deterministic, so
    `confidence` is always `None` — a template match isn't a scored
    prediction, and inventing a confidence number would be misleading.

    Loads templates from the bundled `reaction_templates.json` **and**, if
    present, an additional file under the user's app-data directory — so a
    user can add their own reactions without touching this plugin's code
    (reaction-SMARTS libraries tend to grow; see PLUGIN_SDK.md's convention
    of treating this kind of thing as data, not code).
    """

    provider_id = "rdkit_templates"

    def __init__(self, bundled_templates_path: Path) -> None:
        self._templates = _load_templates_file(bundled_templates_path) + _load_templates_file(
            USER_TEMPLATES_PATH
        )

    def predict(self, reactant_smiles: list[str]) -> list[ReactionPrediction]:
        from rdkit import Chem
        from rdkit.Chem import AllChem

        reactant_mols = []
        for smiles in reactant_smiles:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                raise ReactionPredictionError(f"Could not parse reactant SMILES: {smiles!r}")
            reactant_mols.append(mol)

        predictions: list[ReactionPrediction] = []
        seen_smiles: set[str] = set()
        for template in self._templates:
            rxn = AllChem.ReactionFromSmarts(template.smarts)
            if rxn.GetNumReactantTemplates() != len(reactant_mols):
                continue
            # Reactant roles in a SMARTS template are positional (e.g. "acid
            # then alcohol"), but callers may enter reactants in either
            # order — try every ordering rather than forcing the caller to
            # know each template's expected order.
            for ordering in itertools.permutations(reactant_mols):
                try:
                    product_sets = rxn.RunReactants(ordering)
                except Exception:  # noqa: BLE001 - a bad template/ordering combo, not a crash
                    continue
                for product_set in product_sets:
                    for product in product_set:
                        try:
                            Chem.SanitizeMol(product)
                            smiles = Chem.MolToSmiles(product)
                        except Exception:  # noqa: BLE001 - RDKit couldn't finalize this product
                            continue
                        if smiles in seen_smiles:
                            continue
                        seen_smiles.add(smiles)
                        predictions.append(
                            ReactionPrediction(
                                product_smiles=smiles, confidence=None, source_label=template.name
                            )
                        )
        return predictions


class RemoteReactionAPIProvider(ReactionPredictor):
    """Optional, configured (not subclassed) remote predictor — same shape
    as `ai_assistant`'s `OpenAICompatibleProvider`: `base_url`/`api_key`
    come from `context.settings`/`context.secrets`, so it's genuinely
    swappable, not hardcoded to one vendor.

    Documented default target: IBM RXN for Chemistry
    (https://rxn.res.ibm.com), a free-tier-signup, well-documented
    reaction-prediction API. IMPORTANT: this V1 implementation POSTs a
    generic `{"reactants": [...]}"` payload and expects a `{"products":
    [...]}"` JSON response — a simple synchronous request/response shape.
    IBM RXN's real API is actually an async submit-then-poll job flow,
    which was NOT verified against a live account in this session. Treat
    this provider as a genuinely generic "bring your own endpoint"
    integration point; wiring it to IBM RXN's true contract (or any other
    specific service) is follow-up work, not something to assume works
    out of the box.
    """

    provider_id = "remote_api"

    def __init__(self, base_url: str = "", api_key: str = "") -> None:
        # Public, mutable — unlike AnthropicProvider/OpenAICompatibleProvider
        # (which read credentials fresh off an AIRequest each call),
        # ReactionPredictor.predict() takes only `reactant_smiles`, so the
        # panel refreshes these two attributes from context.settings/
        # context.secrets right before every predict() call instead, rather
        # than risk a stale value baked in at construction time.
        self.base_url = base_url
        self.api_key = api_key

    def predict(self, reactant_smiles: list[str]) -> list[ReactionPrediction]:
        if not self.base_url:
            raise ReactionPredictionError("No remote reaction API base_url configured.")
        if not self.api_key:
            raise ReactionPredictionError("No remote reaction API key configured.")

        try:
            import requests
        except ImportError as exc:
            raise ReactionPredictionError(
                "The 'requests' package is not installed. Run: uv sync --extra network"
            ) from exc

        try:
            response = requests.post(
                self.base_url,
                json={"reactants": reactant_smiles},
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.Timeout as exc:
            raise ReactionPredictionError("Remote reaction API request timed out.") from exc
        except requests.exceptions.RequestException as exc:
            raise ReactionPredictionError(f"Remote reaction API request failed: {exc}") from exc

        return [
            ReactionPrediction(
                product_smiles=entry["smiles"],
                confidence=entry.get("confidence"),
                source_label="remote_api",
            )
            for entry in data.get("products", [])
        ]


def build_default_providers(bundled_templates_path: Path) -> dict[str, ReactionPredictor]:
    return {
        "Templates": RDKitTemplateProvider(bundled_templates_path),
        "Remote API": RemoteReactionAPIProvider(),
    }
