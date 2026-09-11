"""Mutagenicity alerts, checked against compounds with known answers.

A plausible-looking SMARTS that quietly matches nothing is
indistinguishable from a clean molecule, so every pattern is pinned by
something it MUST match and something it must NOT. That is the same
discipline the hERG basic-amine pattern was held to, and it matters more
here because these alerts are load-bearing: measured over 26 compounds
they match the trained ADMET model's accuracy, and the application offers
them as a screen whether or not the sidecar is installed.

The compounds are standard Ames reference mutagens and drugs with clean
genotoxicity records. SMILES are the canonical PubChem strings used by
`benchmarks/docking/ames_panel.py`.
"""

from __future__ import annotations

import pytest

from tests.conftest import dispose
from rdkit import Chem

from openchem.chem.descriptor_providers import (
    MUTAGENICITY_ALERT_NAME,
    RDKitDescriptorProvider,
    compute_mutagenicity_alerts,
    largest_fused_aromatic_carbocycle,
)

SMILES = {
    "2-nitrofluorene": "C1C2=CC=CC=C2C3=C1C=C(C=C3)[N+](=O)[O-]",
    "benzidine": "C1=CC(=CC=C1N)C2=CC=C(C=C2)N",
    "2-acetylaminofluorene": "CC(=O)NC1=CC2=C(C=C1)C3=CC=CC=C3C2",
    "N-nitrosodimethylamine": "CN(C)N=O",
    "procarbazine": "CC(C)NC(=O)C1=CC=C(C=C1)CNNC",
    "benzo[a]pyrene": "C1=CC=C2C3=C4C(=CC2=C1)C=CC5=C4C(=CC=C5)C=C3",
    "naphthalene": "c1ccc2ccccc2c1",
    "anthracene": "c1ccc2cc3ccccc3cc2c1",
    "paracetamol": "CC(=O)NC1=CC=C(C=C1)O",
    "aspirin": "CC(=O)OC1=CC=CC=C1C(=O)O",
    "ibuprofen": "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O",
    "metformin": "CN(C)C(=N)N=C(N)N",
    "D-glucose": "C(C1C(C(C(C(O1)O)O)O)O)O",
    "styrene oxide": "C1OC1c1ccccc1",
}


def _alerts(name: str) -> list[str]:
    return compute_mutagenicity_alerts(Chem.MolFromSmiles(SMILES[name]), "uuid").matched


@pytest.mark.parametrize(
    ("compound", "expected_alert"),
    [
        ("2-nitrofluorene", "Aromatic nitro"),
        ("benzidine", "Aromatic amine"),
        ("2-acetylaminofluorene", "N-aryl amide (aromatic amine precursor)"),
        ("N-nitrosodimethylamine", "N-nitroso"),
        ("procarbazine", "Hydrazine"),
        ("styrene oxide", "Epoxide"),
    ],
)
def test_each_alert_fires_on_a_compound_that_carries_it(compound, expected_alert):
    assert expected_alert in _alerts(compound)


@pytest.mark.parametrize(
    "compound", ["aspirin", "ibuprofen", "metformin", "D-glucose"]
)
def test_clean_compounds_raise_no_alert(compound):
    """These have clean genotoxicity records and no alerting substructure.
    A pattern that over-fires shows up here rather than in the field."""
    assert _alerts(compound) == []


def test_an_acylated_nitrogen_is_not_an_aromatic_amine():
    """The distinction the patterns turn on. Paracetamol's nitrogen is
    acylated, so 'Aromatic amine' must not fire -- only the weaker
    precursor alert, which is the one that (correctly, and as a known
    limitation) over-flags this drug."""
    matched = _alerts("paracetamol")

    assert "Aromatic amine" not in matched
    assert "N-aryl amide (aromatic amine precursor)" in matched


def test_a_polycyclic_aromatic_is_caught_with_no_functional_group():
    """Benzo[a]pyrene is carbon and hydrogen only, so every SMARTS misses
    it. Without the fused-ring rule a major mutagen class would be
    invisible to this screen."""
    matched = _alerts("benzo[a]pyrene")

    assert any(alert.startswith("Polycyclic aromatic") for alert in matched)


@pytest.mark.parametrize(
    ("compound", "rings"),
    [("naphthalene", 2), ("anthracene", 3), ("benzo[a]pyrene", 5)],
)
def test_fused_ring_counting_is_right(compound, rings):
    assert largest_fused_aromatic_carbocycle(Chem.MolFromSmiles(SMILES[compound])) == rings


def test_two_fused_rings_are_below_the_threshold():
    """Naphthalene is not an alert. Setting the bar at two would flag a
    large fraction of ordinary drug-like molecules and make the screen
    useless."""
    assert _alerts("naphthalene") == []


def test_a_molecule_can_carry_several_alerts():
    matched = _alerts("2-nitrofluorene")

    assert "Aromatic nitro" in matched
    assert len(matched) >= 1


# --- reaching the Properties panel ---------------------------------------


def test_the_alert_is_published_with_the_other_admet_alerts():
    """It has to arrive through `compute_alerts` to show up in the panel
    at all -- that is the only path `DescriptorService` publishes."""
    provider = RDKitDescriptorProvider()

    alerts = provider.compute_alerts(Chem.MolFromSmiles(SMILES["2-nitrofluorene"]), "uuid")

    mutagenicity = next(a for a in alerts if a.name == MUTAGENICITY_ALERT_NAME)
    assert mutagenicity.category == "admet", "must land in the ADMET section"
    assert mutagenicity.alert_id == "mutagenicity_alerts"
    assert "Aromatic nitro" in mutagenicity.matched


def test_existing_alert_families_are_untouched():
    """A regression guard: adding a fifth alert must not disturb the four
    already relied on."""
    provider = RDKitDescriptorProvider()

    names = {a.alert_id for a in provider.compute_alerts(Chem.MolFromSmiles("c1ccccc1"), "uuid")}

    assert {"pains", "brenk", "mutagenicity_alerts"} <= names


def test_the_alert_reaches_the_properties_panel(qapp):
    """End to end, through the real panel. The ADMET section already
    existed and alerts route by `category`, so this needed no panel
    change -- but "should route generically" and "does" are different
    claims, and only one of them is worth relying on.
    """
    from openchem.chem.engine import ChemistryEngine
    from openchem.events.base import EventBus
    from openchem.events.events import AlertComputed, MoleculeSelected
    from openchem.services.calculator_registry import CalculatorRegistry
    from openchem.ui.panels.property_panel import PropertyPanel

    class _StubService:
        def request_descriptors(self, *a, **k):
            pass

        def run_calculator(self, *a, **k):
            pass

    bus = EventBus()
    panel = PropertyPanel(bus, CalculatorRegistry(), _StubService(), ChemistryEngine())
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))

    alert = compute_mutagenicity_alerts(Chem.MolFromSmiles(SMILES["2-nitrofluorene"]), "mol-1")
    bus.publish(AlertComputed(alert=alert))

    # **THE READER, NOT A PANEL ROW.** Properties is the launcher now; what
    # "reaches the user" means is that the result is held and filed under
    # the section its producer names, which is what the reader groups by.
    report = panel._reports["mutagenicity_alerts"]
    assert report.category == "admet", "filed under ADMET / Toxicity"
    assert any("Aromatic nitro" in line for line in report.matched)


def test_a_clean_molecule_still_says_it_ran(qapp):
    """A screen that ran and found nothing must not look like one that
    never ran.

    **THE PANEL SAID "Clean" AND THE READER SAID NOTHING AT ALL.** Measured
    while emptying the launcher: a clean catalogue reaches the reader
    through `report_from_alert` with no facts, no matched lines and no
    limitations, so focusing it showed a title and blankness. Two things
    now separate it from a calculator nobody ran -- the entry EXISTS, and
    the reader says so above the (absent) facts.

    **AND IT GIVES THE VERDICT, WHICH IT COULD NOT WHEN THIS WAS WRITTEN.**
    The first version of this said the reader deliberately does not, on the
    ground that only a catalog is entitled to one. The entitlement was never
    the problem: `report_from_alert` was DROPPING `severity`, so the reader
    had no way to know it was holding a catalog at all. Carrying it is what
    makes the verdict sayable, and a report with nothing to say still gets
    the neutral sentence -- `tests/test_property_panel_reader.py` asserts
    both directions.
    """
    from openchem.chem.engine import ChemistryEngine
    from openchem.events.base import EventBus
    from openchem.events.events import AlertComputed, MoleculeSelected
    from openchem.services.calculator_registry import CalculatorRegistry
    from openchem.ui.panels.property_panel import PropertyPanel

    class _StubService:
        def request_descriptors(self, *a, **k):
            pass

        def run_calculator(self, *a, **k):
            pass

    bus = EventBus()
    panel = PropertyPanel(bus, CalculatorRegistry(), _StubService(), ChemistryEngine())
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))

    bus.publish(
        AlertComputed(alert=compute_mutagenicity_alerts(Chem.MolFromSmiles(SMILES["aspirin"]), "mol-1"))
    )

    from openchem.ui.widgets.results_view import ResultsView

    reader = ResultsView("mol-1")
    reader.set_reports(list(panel._reports.values()))
    reader.set_focus("mutagenicity_alerts")
    assert not reader.merged().report_for("mutagenicity_alerts").facts, (
        "setup: a clean catalogue really does arrive with nothing in it"
    )
    assert "Checked, nothing flagged." in reader._view._summary.text()
    dispose(reader)
