"""How the Properties panel's sections are shaped, derived from the registry.

**26 SECTIONS HELD 49 BUTTONS AND ELEVEN HELD EXACTLY ONE**, so finding a
calculator meant scrolling twenty-six headings, most concealing a single
item. Counted in `docs/NAVIGATION_AUDIT.md` and the strongest single
number behind the report that this had become difficult software to use.

Every guard here reads the LIVE REGISTRY rather than a list kept beside
it. `CalculatorDefinition.category` is deliberately a free string -- its
own docstring says a new category needs no code change -- so a
hand-written list is a blocklist by another name, and this codebase has
already watched one rot (`inapplicable_calculators`, 22 of 49 correct).
"""

from __future__ import annotations

from collections import Counter

import pytest


from openchem.bootstrap import build_service_container
from openchem.domain.calculator import RegistryExecution
from openchem.domain.common import CacheState
from openchem.ui.panels.property_panel import _CATEGORY_LABELS, _CATEGORY_ORDER

import conftest

#: The one category that may hold a single calculator, and why.
#:
#: A DECLARED exception, not a threshold. `nmr_database` has no registry
#: sibling -- the ORCA NMR jobs are ServiceExecution and live in their own
#: panel -- and filing a spectroscopic measurement under a structural
#: heading purely to flatten a count would be worse than the count. The
#: entry is by NAME so a second singleton cannot arrive quietly.
#: `thermophysical` is the second, for the same reason rather than a new
#: one: Joback's eleven properties are critical constants, phase-change
#: points and a heat capacity, and not one of the seventeen existing
#: headings takes them. Filing a critical volume under "Electronic" or
#: "Solubility" to flatten a count is exactly the trade the nmr entry
#: above refuses.
#: `energetic` WAS the third, for exactly one commit. The detonation
#: properties landed beside oxygen balance and
#: `test_the_declared_singleton_really_is_one` went red until this name
#: was removed -- which is the guard working, and the reason that narrow
#: half exists at all.
#: `aromaticity` WAS the third, for exactly one commit. Bird's index landed
#: beside HOMA and `test_the_declared_singleton_really_is_one` went red until
#: this name was removed -- which is the guard working, and the second time
#: that has happened here after `energetic`.
_ALLOWED_SINGLETONS = {"nmr", "thermophysical"}


def _real_registry():
    """The live registry, for a test that needs one outside the fixture."""
    return build_service_container().calculator_registry


@pytest.fixture(scope="module")
def registry():
    return _real_registry()


@pytest.fixture(scope="module")
def button_counts(registry) -> Counter:
    """Calculators that actually put a BUTTON in a section.

    ServiceExecution entries (Docking, Quantum Chemistry) are registered
    for discovery and run from their own panels, so they are excluded
    exactly as `_section_for` excludes them.
    """
    counts: Counter = Counter()
    for category in registry.categories():
        counts[category] = sum(
            1
            for definition in registry.by_category(category)
            if isinstance(definition.execution, RegistryExecution)
        )
    return counts


def _every_reachable_category() -> set[str]:
    """Every category that can reach `_section_for`.

    **IT WAS FOUR SOURCES AND IT IS ONE.** The registry, the two descriptor
    spec tables and a provider's alert literals could each put a category in
    front of `_section_for`, because a descriptor built a row and an alert
    built a row, and a row needs a section to live in. 2c removes both: the
    always-on values are read in the results panel, so the ONLY thing that
    creates a section now is a registered calculator this panel can run.

    Measured at the change: the four-source enumeration gives 23 and the
    built panel gives 20. Three categories -- physicochemical, shape and
    one more -- are declared by descriptors alone and no longer appear in
    Properties at all, correctly: a launcher has nothing to offer where
    there is nothing to launch.

    **THE CATEGORIES THAT LEFT ARE NOT UNGUARDED**, which is the only
    reason narrowing this is safe. A descriptor's category still decides
    where its value is GROUPED in the reader, and
    `test_calculator_taxonomy.py::test_every_category_a_DESCRIPTOR_declares_is_mapped_explicitly`
    is what holds that -- written at the same change, because two of them
    were silently taking a default.

    A calculator's RESULT category is deliberately not read here:
    `test_a_calculators_result_lands_in_its_own_section` already forbids it
    differing from its definition's, so it adds nothing new.
    """
    registry = _real_registry()
    return {
        d.category
        for c in registry.categories()
        for d in registry.by_category(c)
        if isinstance(d.execution, RegistryExecution)
    }


def test_no_category_holds_a_single_calculator(button_counts):
    singletons = {c for c, n in button_counts.items() if n == 1}

    assert singletons <= _ALLOWED_SINGLETONS, (
        f"{sorted(singletons - _ALLOWED_SINGLETONS)} hold exactly one calculator. "
        "A section per calculator is the shape this panel was measured in and "
        "moved away from -- merge it, or declare it in _ALLOWED_SINGLETONS "
        "with the reason."
    )


def test_the_declared_singleton_really_is_one(button_counts):
    """The other half, so the allowlist cannot outlive its reason.

    An entry that has quietly gained a sibling is a stale exception, and a
    stale exception is how a guard starts lying -- the same failure as a
    corpus entry claiming coverage it no longer provides.
    """
    for category in _ALLOWED_SINGLETONS:
        assert button_counts.get(category) == 1, (
            f"{category!r} is allowed to be a singleton but now holds "
            f"{button_counts.get(category)}. Remove it from _ALLOWED_SINGLETONS."
        )


def test_every_section_has_a_heading_somebody_chose(button_counts):
    """`_CATEGORY_LABELS` falls back to `category.title()`, which shipped
    the NMR section as "Nmr" until a documentation sweep caught it. The
    fallback stays -- a plugin category must not crash the panel -- but
    nothing WE ship may rely on it.

    **FOUR SOURCES FEED `_section_for` AND EARLY VERSIONS READ ONE OR
    TWO.** The first checked only the calculator registry, passed, and
    the running app showed a section headed "Logp" -- because
    `_on_descriptor_computed` files a `DescriptorValue` by ITS category
    and the descriptor table is a separate list. The second added that
    table and still missed the alerts a PROVIDER publishes (PAINS ->
    medicinal_chemistry, BRENK -> admet), which are literals scattered
    through `descriptor_providers.py` that no list enumerates. Those were
    covered by coincidence until this read them too.
    """
    missing = sorted(c for c in _every_reachable_category() if c not in _CATEGORY_LABELS)

    assert not missing, (
        f"{missing} would be title-cased into a heading nobody chose. "
        "Add them to _CATEGORY_LABELS."
    )


def test_no_heading_contains_an_ampersand():
    """The section header is a `QToolButton`, which treats `&` as a
    MNEMONIC and swallows it: "Lipophilicity & Refractivity" rendered as
    "Lipophilicity  Refractivity", ampersand gone, with a stray gap where
    it had been. Seen in the running app after a merge every test passed.

    Escaping as `&&` would work and is not the rule, because the next
    person to add a heading will not know that. No ampersands at all.
    """
    offenders = {c: label for c, label in _CATEGORY_LABELS.items() if "&" in label}

    assert not offenders, f"{offenders} -- a QToolButton eats the ampersand"


def test_no_heading_is_long_enough_to_elide():
    """"Identity & Composition" rendered as "Identity ...mposition".

    21 characters is not a taste judgement: it is the longest heading
    MEASURED to fit at the panel's real width in the running app
    ("Electronic Properties" and "Structure Generators", both 20-21, need
    116-120 px against 121-125 available). The ceiling is stated here
    rather than recomputed, because computing it needs the real dock.
    """
    too_long = {c: label for c, label in _CATEGORY_LABELS.items() if len(label) > 21}

    assert not too_long, f"{too_long} will elide in the panel"


def test_every_ordered_category_still_has_a_heading():
    """A stale entry in `_CATEGORY_ORDER` is invisible -- the category is
    never seen, so it sorts nothing and nothing fails. After a merge that
    is exactly what gets left behind.

    **Checked against `_CATEGORY_LABELS`, NOT against the registry.** The
    first version of this test asserted every ordered category was
    registered and failed on `physicochemical`, `medicinal_chemistry` and
    `shape` -- which are real sections that no CALCULATOR registers: they
    come from the descriptor providers and from the alert catalogs. The
    two lists in this panel having the same membership is the invariant
    that actually holds.
    """
    stale = [c for c in _CATEGORY_ORDER if c not in _CATEGORY_LABELS]

    assert not stale, (
        f"{stale} are ordered but have no heading -- left behind by a merge?"
    )


@pytest.fixture(scope="module")
def computed_results(registry):
    """Every registry calculator run once, on a molecule with a conformer.

    **THIS IS THE SLOWEST TEST IN THE SUITE and the cost is deliberate.**
    Measured: ~35 s warm standalone, ~76 s inside a full run, against a
    next-slowest of 14 s. Roughly 12 s of it is spent on calculators
    whose result carries no category and is therefore discarded here --
    unavoidable, because the result TYPE is only knowable by running it.
    Most of the remainder is sidecars: the ADMET model (7.7 s), pkasolver
    (pka, logd, microspecies) and OPSIN's JVM.

    Module-scoped so the sweep happens once however many assertions are
    made over it. WITH A CONFORMER, or every 3D-dependent calculator
    comes back FAILED and is skipped -- `interaction_analysis` is one the
    section merge moved, so without geometry this would not cover the
    change it exists for.
    """
    from rdkit import Chem, RDLogger
    from rdkit.Chem import AllChem

    RDLogger.DisableLog("rdApp.*")
    mol = Chem.AddHs(Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O"))
    AllChem.EmbedMolecule(mol, randomSeed=0xF00D)
    AllChem.MMFFOptimizeMolecule(mol)

    results = []
    for category in registry.categories():
        for definition in registry.by_category(category):
            if not isinstance(definition.execution, RegistryExecution):
                continue
            try:
                result = registry.compute(
                    definition.calculator_id,
                    mol,
                    "uuid",
                    {p.name: p.default for p in definition.parameters},
                )
            except Exception:  # noqa: BLE001 - a calculator that raises is not the subject
                continue
            results.append((definition, result))
    return results


def test_a_calculators_result_lands_in_its_own_section(computed_results):
    """THE TRAP IN MERGING CATEGORIES, and the reason this file exists.

    A `ReportResult` and an `AlertResult` carry their OWN `category` --
    the panel files them with `report.category`, not with the
    definition's -- while everything else is filed by registry lookup. So
    moving a calculator to a new section without moving the category its
    result carries puts the BUTTON in one section and its ANSWER in
    another, with nothing failing anywhere.

    Checked by RUNNING each calculator, because the two values live in
    different files and only agree if somebody kept them in step.
    """
    from openchem.domain.common import CacheState

    mismatched = []
    compared: list[str] = []
    for definition, result in computed_results:
        # EMPTY IS NOT "CARRIES ONE". `PerAtomDataset.category` defaults
        # to `""` meaning "I am in the registry, ask it" -- so every
        # registered per-atom calculator now HAS the attribute and none
        # of them declares a value. Reading `is None` compared "" against
        # 16 real categories and failed on all of them the moment that
        # field was added. A NON-empty category that disagrees with its
        # definition is still exactly the bug this test is about.
        carried = getattr(result, "category", None) or None
        if carried is None or getattr(result, "cache_state", None) is CacheState.FAILED:
            continue
        compared.append(definition.calculator_id)
        if carried != definition.category:
            mismatched.append(
                f"{definition.calculator_id}: button in {definition.category!r}, "
                f"result in {carried!r}"
            )

    assert not mismatched, "; ".join(mismatched)
    # A FLOOR, because a guard that silently compares nothing passes.
    # Every result that fails or carries no category of its own is
    # skipped above, so a change that made them all fail would turn this
    # into an assertion about an empty list -- "an arm that does not run
    # is not an arm", one level up.
    assert len(compared) >= 10, f"only compared {compared}"


def test_no_calculator_name_is_wider_than_its_button(registry):
    """A name longer than anything measured to fit will elide.

    Elision is graceful -- `_ElidingPushButton` keeps the full name in the
    tooltip -- but a truncated label is still a label somebody has to
    hover to read, and SEVEN of them were truncated before the
    `Open {name}...` wrapper came off the buttons.

    The ceiling is a character count standing in for a pixel width, which
    is imprecise in a proportional font; see `_MAX_CALCULATOR_NAME` for
    why a pixel assertion would be worse. ServiceExecution entries are
    excluded because they have no button.
    """
    from openchem.ui.panels.property_panel import _MAX_CALCULATOR_NAME

    too_long = sorted(
        (len(d.display_name), d.display_name)
        for category in registry.categories()
        for d in registry.by_category(category)
        if isinstance(d.execution, RegistryExecution)
        and len(d.display_name) > _MAX_CALCULATOR_NAME
    )

    assert not too_long, f"these will elide on their button: {too_long}"


def test_every_calculator_button_really_does_open_a_dialog(registry):
    """The trailing ellipsis on every button promises one, so it had
    better be true.

    Written after the opposite was assumed: that some calculators run
    immediately and their ellipsis was a lie. `_open_calculator` shows a
    settings dialog `if definition.parameters`, and ALL 49 declare
    parameters -- so the promise holds and a conditional ellipsis would
    have been a branch that never runs. If a parameterless calculator is
    ever registered this fails, and the label needs to become
    conditional after all.
    """
    parameterless = sorted(
        d.calculator_id
        for category in registry.categories()
        for d in registry.by_category(category)
        if isinstance(d.execution, RegistryExecution) and not d.parameters
    )

    assert not parameterless, (
        f"{parameterless} run with no dialog, but their button ends in '...' -- "
        "make the ellipsis conditional on definition.parameters"
    )


def test_a_calculator_name_keeps_its_ampersand_on_the_button(qapp):
    """"Substance & Bonding" rendered as "Substance  Bonding".

    Qt reads `&` in a button label as a mnemonic marker and swallows it.

    **SHOWN, then resized.** The escape happens in two places -- the
    constructor and `resizeEvent` -- and `resizeEvent` NEVER FIRES on a
    widget that was never shown, so a test that only constructs covers
    half of it. That is the same trap as `repaint()` on an unshown widget
    calling no `paintEvent`, which this project already records.
    """
    from openchem.ui.panels.property_panel import _ElidingPushButton

    button = _ElidingPushButton("Substance & Bonding")
    button.show()
    button.resize(400, 24)
    qapp.processEvents()
    try:
        assert "&&" in button.text(), button.text()
        assert button._full_text == "Substance & Bonding"
        assert button._shown_text == "Substance & Bonding"
    finally:
        button.hide()
        button.setParent(None)
        button.deleteLater()


def test_a_resize_that_changes_nothing_does_not_call_setText(qapp, monkeypatch):
    """The guard compares against `_shown_text`, NOT `self.text()`.

    `text()` comes back ESCAPED, so comparing an unescaped elided string
    to it is never equal and every resize calls `setText` again -- a
    relayout on every layout pass, forever.

    **THREE EARLIER VERSIONS OF THIS TEST CAUGHT NOTHING**, each looking
    right:

    1. asserted the text was unchanged after two resizes -- true either
       way, since the loop wastes work rather than changing the answer;
    2. counted `setText` calls but resized to the SAME size twice, and Qt
       sends no `resizeEvent` when nothing moved;
    3. resized to two different sizes, on a widget that was NEVER SHOWN
       -- where `resize()` delivers no `resizeEvent` at all, so the code
       under test never ran. Measured: 0 events hidden, 2 events shown.

    Shown, then two different widths, both wide enough that the label
    does not elide: the rendered label is identical at both, so correct
    code sets nothing while the mutation sets it every time.
    """
    from PySide6.QtWidgets import QPushButton

    from openchem.ui.panels.property_panel import _ElidingPushButton

    button = _ElidingPushButton("Substance & Bonding")
    button.show()
    button.resize(400, 24)          # settle; nothing elides at this width
    qapp.processEvents()

    calls: list[str] = []
    original = QPushButton.setText
    monkeypatch.setattr(
        QPushButton, "setText", lambda self, text: (calls.append(text), original(self, text))[1]
    )
    try:
        button.resize(420, 24)      # real resizeEvents, same rendered label
        button.resize(440, 24)
        qapp.processEvents()

        assert calls == [], f"setText called {len(calls)}x for an unchanged label"
        assert button._shown_text == "Substance & Bonding"
    finally:
        button.hide()
        button.setParent(None)
        button.deleteLater()


def test_the_panels_button_label_is_the_calculator_name_and_nothing_else(qapp):
    """It used to read `Open {name}...`, and `Open ` alone was ~32 px of a
    192 px button -- spent identically 49 times, and enough on its own to
    elide seven names where none elide now.

    **Reads the button THE PANEL BUILT.** The first version of this test
    constructed its own `_ElidingPushButton` from a display name and
    asserted that string had no prefix -- which tested the test. Putting
    the wrapper back left it green.
    """
    from openchem.chem.engine import ChemistryEngine
    from openchem.events.base import EventBus
    from openchem.services.calculator_registry import CalculatorRegistry
    from openchem.ui.panels.property_panel import PropertyPanel, _ElidingPushButton

    class _Service:
        def run_calculator(self, model, request) -> None:
            pass

    panel = PropertyPanel(EventBus(), _real_registry(), _Service(), ChemistryEngine())
    try:
        panel._section_for("identity")
        labels = [b._full_text for b in panel.findChildren(_ElidingPushButton)]

        assert labels, "the panel built no calculator buttons"
        offenders = [label for label in labels if label.startswith("Open ")]
        assert not offenders, offenders
        assert "Elemental Analysis..." in labels
    finally:
        conftest.dispose(panel)


def test_the_heading_and_the_copied_text_agree(qapp):
    """One function decides what a section is called, because there were
    TWO and they disagreed.

    The heading fell back to `category.replace("_", " ").title()` and
    `as_text()` to `category.title()`, so an unlabelled
    `medicinal_chemistry` would read "Medicinal Chemistry" on screen and
    copy as "Medicinal_Chemistry" -- two names for one section, in one
    panel. Latent rather than shipped: every category in the app has a
    chosen label, so neither fallback runs today.

    **Exercised through the real panel and the real `as_text()`.** The
    first version of this test called `_category_label` directly, which
    is the shared helper -- so putting the old expression back in
    `as_text` left it green. It asserted that the two agreed by asking
    only one of them.

    A category NOBODY has named is the only way to reach the fallback at
    all, so the CALCULATOR carries an invented one -- it was a descriptor
    until 2c, which removed the value rows and with them the only thing a
    descriptor put in a section.
    """
    from openchem.chem.engine import ChemistryEngine
    from openchem.domain.calculator import CalculatorDefinition, RegistryExecution
    from openchem.events.base import EventBus
    from openchem.events.events import MoleculeSelected
    from openchem.services.calculator_registry import CalculatorRegistry
    from openchem.ui.panels.property_panel import (
        _CATEGORY_LABELS,
        PropertyPanel,
        _category_label,
    )

    category = "plugin_supplied_tools"
    assert category not in _CATEGORY_LABELS, "pick a category nobody has named"

    class _Service:
        def run_calculator(self, model, request) -> None:
            pass

    registry = CalculatorRegistry()
    registry.register(
        CalculatorDefinition(
            calculator_id="whatever",
            display_name="Whatever",
            category=category,
            description="a plugin's calculator, in a category nobody named",
            execution=RegistryExecution(compute=lambda mol, uuid, params: None),
        )
    )
    bus = EventBus()
    panel = PropertyPanel(bus, registry, _Service(), ChemistryEngine())
    try:
        bus.publish(MoleculeSelected(molecule_uuid="mol-1"))
        # Sections are built lazily, when one is first asked for.
        panel._section_for(category)
        heading = panel._sections[category]._toggle_button.text()
        copied = panel.as_text()

        assert heading == "Plugin Supplied Tools", heading
        assert heading in copied, copied
        assert "Plugin_Supplied_Tools" not in copied
        assert _category_label(category) == heading
    finally:
        conftest.dispose(panel)


def test_a_named_category_is_not_title_cased(qapp):
    """`nmr` becoming "Nmr" is how this finding was noticed. A chosen
    label must survive the fallback path untouched."""
    from openchem.ui.panels.property_panel import _category_label

    assert _category_label("nmr") == "NMR"
    assert _category_label("pka") == "pKa"
    assert _category_label("") == "Other"


def test_the_always_on_per_atom_batch_declares_every_category():
    """IT IS IN NO REGISTRY, SO IT CANNOT BE ASKED ONE.

    `compute_per_atom` is the always-on batch -- explicitly "not
    registry-driven" -- and the panel used to route it by looking its
    `property_id` up in the registry anyway. Two of the three resolved,
    BY COINCIDENCE: `crippen_logp_contrib` and `crippen_mr_contrib` are
    also registered calculator ids (the registered ones offer a hydrogen
    mode this batch is fixed on). `gasteiger_charge` has no twin -- the
    registered charge calculator is `gasteiger_charge_at_ph` -- so it
    fell through to a generic "Other" section it was the only occupant
    of.

    Asserting all THREE rather than the one that was broken: the point of
    the fix is that the two which worked stop being lucky.
    """
    from rdkit import Chem, RDLogger

    from openchem.chem.descriptor_providers import RDKitDescriptorProvider

    RDLogger.DisableLog("rdApp.*")
    mol = Chem.AddHs(Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O"))
    datasets = RDKitDescriptorProvider().compute_per_atom(mol, "uuid")
    assert datasets, "the always-on batch produced nothing, so this proves nothing"

    known = _every_reachable_category()
    for dataset in datasets:
        assert dataset.category, (
            f"{dataset.property_id} declares no category, so the panel must "
            "guess one from a registry this batch is not in"
        )
        assert dataset.category in known, (
            f"{dataset.property_id} declares {dataset.category!r}, which is "
            "not a category anything else produces -- it would open a "
            "section of its own"
        )

    # ... and the specific one that was wrong, by name, so a future
    # re-shuffle of the batch cannot quietly drop it back into "other".
    charge = next(d for d in datasets if d.property_id == "gasteiger_charge")
    assert charge.category == "charge"
    assert not _real_registry().get("gasteiger_charge"), (
        "gasteiger_charge is registered now, so the registry lookup would "
        "resolve it and this test no longer covers the case it names"
    )


def test_a_declared_category_routes_a_dataset_the_registry_cannot_place():
    """THE CONSUMER HALF, and it is the one a revert breaks silently.

    The producer declaring a category buys nothing if the consumer goes on
    asking the registry. Driven through the real `PerAtomDataComputed`
    path with an EMPTY registry, so there is nothing to resolve the id and
    the declaration is the only thing that can place the result anywhere.

    **THE CONSUMER MOVED IN 2c AND THE QUESTION DID NOT.** This asserted
    that the declared category created its SECTION in the Properties panel,
    because the row was filed there. There is no row now -- and a section
    heading created for a category with no calculator buttons in it would
    be an empty heading -- so the declaration is read where the result is
    read: the reader groups its selector by exactly this field. What must
    not happen is the same either way, the category being invented by the
    consumer instead of taken from the producer.
    """
    from openchem.chem.engine import ChemistryEngine
    from openchem.domain.common import Provenance
    from openchem.domain.scientific_result import PerAtomDataset
    from openchem.events.base import EventBus
    from openchem.events.events import MoleculeSelected, PerAtomDataComputed
    from openchem.services.calculator_registry import CalculatorRegistry
    from openchem.ui.panels.property_panel import PropertyPanel

    class _Service:
        def run_calculator(self, model, request) -> None:
            pass

    bus = EventBus()
    panel = PropertyPanel(bus, CalculatorRegistry(), _Service(), ChemistryEngine())
    try:
        bus.publish(MoleculeSelected(molecule_uuid="mol-1"))
        bus.publish(
            PerAtomDataComputed(
                dataset=PerAtomDataset(
                    property_id="nothing_registered_owns_this",
                    name="Declared Elsewhere",
                    units="e",
                    method="test",
                    molecule_uuid="mol-1",
                    values={0: 1.0},
                    category="charge",
                    provenance=Provenance(created_by="test", method="test"),
                )
            )
        )

        summary = panel._reports["nothing_registered_owns_this"]
        assert summary.category == "charge", (
            "the declared category did not survive the trip to the reader, so "
            "the consumer is still routing by the registry"
        )
        assert summary.category != "other", (
            "the dataset was filed under the generic category despite "
            "declaring where it belongs"
        )
    finally:
        conftest.dispose(panel)


def test_an_undeclared_dataset_still_asks_the_registry():
    """THE NARROW HALF. Without it, "prefer the declaration" is satisfied
    by ignoring the registry entirely -- which would break every dataset
    a REGISTERED calculator produces, since those carry no category and
    are placed by exactly that lookup.

    An empty `category` is not a missing value here; it is the producer
    saying "I am in the registry, ask it".
    """
    from openchem.chem.engine import ChemistryEngine
    from openchem.domain.common import Provenance
    from openchem.domain.scientific_result import PerAtomDataset
    from openchem.events.base import EventBus
    from openchem.events.events import MoleculeSelected, PerAtomDataComputed
    from openchem.services.calculator_registry import CalculatorRegistry
    from openchem.ui.panels.property_panel import PropertyPanel

    registry = _real_registry()
    definition = next(
        d
        for d in registry.by_category("charge")
        if isinstance(d.execution, RegistryExecution)
    )

    class _Service:
        def run_calculator(self, model, request) -> None:
            pass

    bus = EventBus()
    panel = PropertyPanel(bus, registry, _Service(), ChemistryEngine())
    try:
        bus.publish(MoleculeSelected(molecule_uuid="mol-1"))
        bus.publish(
            PerAtomDataComputed(
                dataset=PerAtomDataset(
                    property_id=definition.calculator_id,
                    name=definition.display_name,
                    units="e",
                    method="test",
                    molecule_uuid="mol-1",
                    values={0: 1.0},
                    provenance=Provenance(created_by="test", method="test"),
                )
            )
        )

        assert "other" not in panel._sections, (
            f"{definition.calculator_id} is registered under "
            f"{definition.category!r} and still went to the generic section, "
            "so the registry fallback has been removed"
        )
    finally:
        conftest.dispose(panel)


def test_the_guide_states_the_real_number_of_collapsible_categories():
    """The count in `docs/USER_GUIDE.md`, against the live enumeration.

    **IT LIVES HERE RATHER THAN IN `test_docs_are_current.py`** because
    this file already owns "which categories exist", and a second
    implementation of that is the drift this repository has paid for four
    times. The doc guards import from production for the same reason;
    importing another TEST module is the smell.

    **THE CLAIM IS ABOUT WHAT A USER SEES, so it was measured there** --
    driven in the real application, aspirin selected, the Properties
    panel dumped: 20 sections, matching this enumeration exactly. It said
    25 for as long as anybody can trace, and the run that settled it also
    turned up a 21st section holding one mis-routed result, which is the
    two tests above.
    """
    import re
    from pathlib import Path

    guide = (
        Path(__file__).resolve().parent.parent / "docs" / "USER_GUIDE.md"
    ).read_text(encoding="utf-8")

    # ANY whitespace between the two words, not only after the digits:
    # the sentence was reflowed at 2c and the line break landed between
    # "collapsible" and "categories", which this read as the count having
    # been removed altogether.
    stated = re.search(r"\*\*(\d+)\s+collapsible\s+categories\*\*", guide)
    assert stated, "the guide no longer states a collapsible-category count"
    assert int(stated.group(1)) == len(_every_reachable_category()), (
        f"the guide says {stated.group(1)} collapsible categories and there "
        f"are {len(_every_reachable_category())}"
    )


def test_the_readme_states_the_real_number_of_categories_too():
    """The same claim as the guide's, in the doc a new reader meets first.

    **IT LIVES HERE FOR THE REASON THE GUARD ABOVE GIVES**: this file owns
    "which categories exist", and a second implementation of that is the
    drift this repository has paid for four times.

    Measured during the docsweep that added it: the README said "58
    calculators across 18 categories" against a live 59 and 23. The guide was
    right on both because a guard held it; the README had nothing.
    """
    import re
    from pathlib import Path

    readme = (Path(__file__).resolve().parent.parent / "README.md").read_text(
        encoding="utf-8"
    )

    stated = re.search(r"\*\*(\d+) calculators across (\d+) categories\*\*", readme)
    assert stated, (
        "README.md no longer states calculators-across-categories in the shape "
        "this guard reads. If the sentence was reworded, reword the pattern "
        "too -- a count nothing checks is a count that rots."
    )
    assert int(stated.group(2)) == len(_every_reachable_category()), (
        f"the README says {stated.group(2)} categories and there are "
        f"{len(_every_reachable_category())}"
    )


def test_a_result_declares_the_same_section_its_calculator_does():
    """**ONE ID MUST NOT NAME TWO SECTIONS.**

    `test_a_calculators_result_lands_in_its_own_section` above walks the
    REGISTRY, so a result whose producer declares its own `category` --
    every `AlertResult`, and the always-on batch in particular -- was
    outside its population. Measured over every literal `(id, category)`
    pair in the tree: 41 declarations, and exactly ONE disagreed with the
    registered calculator of the same id. `functional_groups` said `admet`
    while its calculator said `substructure`, so the BUTTON sat under
    Substructure Search and the always-on RESULT ROW appeared under ADMET /
    Regulatory -- one name, two headings, and nothing could see it.

    It reads the SOURCE rather than running the producers because the two
    declarations are what disagree; a run would only show whichever one
    happened to answer.
    """
    import ast
    from pathlib import Path

    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

    registered = {d.calculator_id: d.category for d in CALCULATOR_DEFINITIONS}
    assert registered, "fixture is degenerate: no calculators registered"

    src = Path(__file__).resolve().parent.parent / "src" / "openchem"
    declared: list[tuple[str, str, str]] = []
    for path in src.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            if node.func.id not in ("AlertResult", "report_fields", "report_from_fields"):
                continue
            keywords = {k.arg: k.value for k in node.keywords}
            result_id = keywords.get("alert_id") or keywords.get("report_id")
            category = keywords.get("category")
            if not isinstance(result_id, ast.Constant):
                continue
            if not isinstance(category, ast.Constant):
                continue
            declared.append(
                (
                    result_id.value,
                    category.value,
                    f"{path.relative_to(src).as_posix()}:{node.lineno}",
                )
            )

    assert len(declared) >= 30, f"the walk found only {len(declared)} declarations"

    disagreeing = [
        f"{result_id} declares {category!r} and its calculator declares "
        f"{registered[result_id]!r} ({where})"
        for result_id, category, where in declared
        if result_id in registered and registered[result_id] != category
    ]
    assert not disagreeing, disagreeing


def test_the_four_catalogs_have_no_registered_calculator_and_that_is_fine():
    """The narrow half. The guard above only compares ids the registry
    knows, so "no id is ever checked" would satisfy it -- these four are
    genuinely producer-only (PAINS, BRENK, mutagenicity, hERG risk factors
    are always-on catalogs with nothing to run) and their presence is what
    says the comparison has a real population to be narrower than."""
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

    registered = {d.calculator_id for d in CALCULATOR_DEFINITIONS}
    catalogs = {"pains", "brenk", "mutagenicity_alerts", "herg_risk_factors"}
    assert not (catalogs & registered), sorted(catalogs & registered)


def test_every_default_expanded_category_is_one_the_panel_builds(qapp):
    """An entry naming a category that gets no section expands nothing.

    **MEASURED AT HALF THE SET.** `_DEFAULT_EXPANDED` held
    `{"physicochemical", "identity"}`; sections are built for the categories
    a RUNNABLE calculator declares, and `physicochemical` has none -- it had
    a section only because the 41 always-on descriptors built one, and 2c
    reads those in the results panel instead. So one of the two named
    nothing, silently: an unreachable entry expands nothing and complains
    about nothing.
    """
    from openchem.bootstrap import build_service_container
    from openchem.chem.engine import ChemistryEngine
    from openchem.ui.panels.property_panel import _DEFAULT_EXPANDED, PropertyPanel

    services = build_service_container()
    panel = PropertyPanel(
        services.event_bus,
        services.calculator_registry,
        services.descriptor_service,
        ChemistryEngine(),
    )
    try:
        unreachable = sorted(_DEFAULT_EXPANDED - set(panel._sections))
        assert not unreachable, (
            f"_DEFAULT_EXPANDED names categories the panel never builds: "
            f"{unreachable}. A section is built per category with a runnable "
            "calculator."
        )
    finally:
        conftest.dispose(panel)


