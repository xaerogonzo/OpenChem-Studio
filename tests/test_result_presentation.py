"""How a per-atom result READS -- captions, ranges, precision, clipboard.

Four defects were measured in the running app, all presentation and none
chemistry. Each has a guard here.

  1. Every scalar descriptor row was captioned with its raw internal id
     and lost its units: `mol_logp` for "LogP", `mol_wt` for "Molecular
     Weight (g/mol)". All 26 of them, in every section.
  2. The Calculator Inspector's legend printed the symmetric COLOUR
     DOMAIN as if it were the data range -- "-1.019 to 1.019" beside a
     panel row saying "-1.019 to 0.5437" for the same numbers.
  3. One dataset rendered at four precisions on one screen: 2 dp atom
     labels, a `.3f` legend, a `.4g` headline and a `.4g` panel row.
  4. Copying a per-atom result carried no molecular total at all.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QFormLayout, QLabel
from rdkit import Chem, RDLogger
from rdkit.Chem import Crippen

from openchem.chem.calculator_options import EXPLICIT_HYDROGENS
from openchem.chem.descriptor_providers import (
    _DESCRIPTOR_SPECS,
    compute_crippen_logp_contrib_calculator,
)
from openchem.chem.engine import ChemistryEngine
from openchem.domain.common import CacheState, Provenance, declare_total
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.molecule import MoleculeModel
from openchem.domain.scientific_result import PerAtomDataset
from openchem.events.base import EventBus
from openchem.events.events import DescriptorComputed, MoleculeSelected
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.ui.dialogs.calculator_inspector_dialog import CalculatorInspectorDialog
from openchem.ui.panels.property_panel import PropertyPanel, _summarise
from openchem.ui.result_clipboard import result_to_text
from openchem.ui.visualization import build_atom_color_layer, data_range
from openchem.ui.widgets.collapsible_section import ExplicitHeightLabel

RDLogger.DisableLog("rdApp.*")

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"


class _FakeDescriptorService:
    def run_calculator(self, *args, **kwargs) -> None:
        pass


def _dispose(widget) -> None:
    """Per widget, and never the global `sendPostedEvents(None, ...)`.

    The global form drains every pending deferred delete in the process,
    including ones other test files left queued -- which is a double-free
    this repo has already recorded twice.
    """
    widget.setParent(None)
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)


def _row_caption(panel: PropertyPanel, key: tuple[str, str]) -> str:
    form = panel._row_sections[key].content_layout()
    row, _role = form.getWidgetPosition(panel._value_labels[key])
    return form.itemAt(row, QFormLayout.ItemRole.LabelRole).widget().text()


def _dataset(values, parameters=None, units="") -> PerAtomDataset:
    return PerAtomDataset(
        property_id="test_calc",
        name="Test Calculator",
        units=units,
        method="rdkit",
        molecule_uuid="mol-1",
        values=values,
        provenance=Provenance(created_by="core", method="rdkit", parameters=parameters or {}),
    )


# --- 1. descriptor row captions -------------------------------------------


def test_every_descriptor_row_shows_its_display_name_and_units(qapp):
    """DERIVED FROM `_DESCRIPTOR_SPECS`, so a descriptor added later is
    covered without touching this test.

    The sequence matters and is exactly what `DescriptorService` does:
    a RUNNING placeholder for every id FIRST (published before
    `compute()` runs, so it can only carry `name=descriptor_id, units=""`),
    then the real values. The row was captioned from the placeholder and
    never corrected, which is why the nice names in `_DESCRIPTOR_SPECS`
    were computed on every run and thrown away.
    """
    bus = EventBus()
    panel = PropertyPanel(bus, CalculatorRegistry(), _FakeDescriptorService(), ChemistryEngine())
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))

    def publish(descriptor_id, name, units, category, state, value=None):
        bus.publish(
            DescriptorComputed(
                descriptor=DescriptorValue(
                    descriptor_id=descriptor_id,
                    name=name,
                    units=units,
                    category=category,
                    provider="rdkit",
                    molecule_uuid="mol-1",
                    value=value,
                    cache_state=state,
                )
            )
        )

    for descriptor_id, _name, _units, category in _DESCRIPTOR_SPECS:
        publish(descriptor_id, descriptor_id, "", category, CacheState.RUNNING)
    for descriptor_id, name, units, category in _DESCRIPTOR_SPECS:
        publish(descriptor_id, name, units, category, CacheState.COMPLETED, 1.0)

    wrong = []
    for descriptor_id, name, units, _category in _DESCRIPTOR_SPECS:
        expected = f"{name} ({units})" if units else name
        actual = _row_caption(panel, ("rdkit", descriptor_id))
        if actual != expected:
            wrong.append((descriptor_id, actual, expected))

    assert not wrong, f"rows still captioned with their raw ids: {wrong}"
    _dispose(panel)


def test_the_reported_row_reads_logp_rather_than_mol_logp(qapp):
    """The specific row from the screenshot, named so a regression is
    recognisable as the thing that was reported."""
    bus = EventBus()
    panel = PropertyPanel(bus, CalculatorRegistry(), _FakeDescriptorService(), ChemistryEngine())
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))

    for name, units, state, value in (
        ("mol_logp", "", CacheState.RUNNING, None),
        ("LogP", "", CacheState.COMPLETED, 3.624),
    ):
        bus.publish(
            DescriptorComputed(
                descriptor=DescriptorValue(
                    descriptor_id="mol_logp",
                    name=name,
                    units=units,
                    category="lipophilicity",
                    provider="rdkit",
                    molecule_uuid="mol-1",
                    value=value,
                    cache_state=state,
                )
            )
        )

    assert _row_caption(panel, ("rdkit", "mol_logp")) == "LogP"
    _dispose(panel)


# --- 2. the legend --------------------------------------------------------


def test_the_legend_quotes_the_data_range_not_the_colour_domain(qapp):
    """These are two different quantities and the bug was that they shared
    a name. For signed data the colour scale is deliberately symmetric
    about zero, so its domain names a value no atom need have."""
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    result = _dataset({0: -1.019, 1: 0.5437, 2: 0.1})

    scale = build_atom_color_layer(result).color_scale
    assert (scale.domain_min, scale.domain_max) == pytest.approx((-1.019, 1.019)), (
        "the colour domain stopped being symmetric, so this test no longer discriminates"
    )
    assert data_range(result) == pytest.approx((-1.019, 0.5437))

    dialog = CalculatorInspectorDialog(engine, molecule, result, conformer_molblock=None)
    texts = [label.text() for label in dialog.findChildren(QLabel)]

    assert any("-1.02 to 0.54" in t for t in texts), texts
    assert not any("1.02 to 1.02" in t for t in texts), "the colour domain is being shown as data"
    _dispose(dialog)


def test_the_dialog_and_the_panel_row_quote_the_same_total(qapp):
    """They disagreed on screen, three inches apart -- `mol_logp 3.624`
    against `Overall: 0.8585`. Both read the one declaration now.

    It is the TOTAL they must agree on rather than the range: the row no
    longer carries a range at all, because the section it sits in has no
    room for both (see `_summarise`, which has the measurements).
    """
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Aspirin")
    engine.set_structure_from_smiles(molecule, ASPIRIN)
    result = compute_crippen_logp_contrib_calculator(Chem.MolFromMolBlock(molecule.molblock), "u", {})

    dialog = CalculatorInspectorDialog(engine, molecule, result, conformer_molblock=None)
    headline = f"{Crippen.MolLogP(Chem.MolFromSmiles(ASPIRIN)):.2f}"

    texts = [label.text() for label in dialog.findChildren(QLabel)]
    assert f"LogP (Crippen): {headline}" in texts, texts
    assert _summarise(result).startswith(f"LogP (Crippen) {headline}")
    _dispose(dialog)


def test_the_dialog_legend_still_carries_the_range(qapp):
    """Because the panel row gave it up, the dialog is now the ONLY place
    it appears -- so losing it there would lose it entirely."""
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Aspirin")
    engine.set_structure_from_smiles(molecule, ASPIRIN)
    result = compute_crippen_logp_contrib_calculator(Chem.MolFromMolBlock(molecule.molblock), "u", {})

    dialog = CalculatorInspectorDialog(engine, molecule, result, conformer_molblock=None)
    low, high = data_range(result)

    # Matched EXACTLY rather than by substring: the balance sentence also
    # contains " to " ("...contributions sum to 0.15..."), and a loose
    # selector picked that instead when this was first written.
    texts = [label.text() for label in dialog.findChildren(QLabel)]
    assert f"{low:.2f} to {high:.2f}" in texts, texts
    _dispose(dialog)


def test_the_panel_row_does_not_outgrow_the_space_it_had(qapp):
    """A STARVED section clips whatever does not fit, so a longer summary
    is not free.

    Measured in the running app with `OPENCHEM_INSTRUMENT_PANEL=1`:
    Lipophilicity is starved on master already (145 px against a 192 px
    minimum) and the result row is given 34 px. A first version of this
    summary carried the total AND the range and needed 79 px, taking the
    shortfall from 13 px to 45 -- an existing clip made visibly worse.

    Pinned against the wording it replaced rather than against a magic
    number, so this stays meaningful if the font or the panel width
    changes.
    """
    result = compute_crippen_logp_contrib_calculator(Chem.MolFromSmiles(ASPIRIN), "u", {})
    values = result.values
    previous = f"{len(values)} atoms, {min(values.values()):.4g} to {max(values.values()):.4g}"

    label = ExplicitHeightLabel("")
    label.resize(205, 16)
    label.setText(previous)
    before = label.heightForWidth(205)
    label.setText(_summarise(result))
    after = label.heightForWidth(205)

    assert after <= before, (
        f"the summary row grew from {before} px to {after} px in a section that is "
        f"already starved: {_summarise(result)!r}"
    )


# --- 3. one precision -----------------------------------------------------


@pytest.mark.parametrize("places", [0, 2, 4])
def test_one_dataset_renders_at_one_precision_everywhere(qapp, places):
    """Headline, balance, legend, panel row and clipboard all go through
    `label_decimals`. Four of them used to disagree.

    Each surface is asserted at whatever it SHOWS -- the panel row carries
    the total but no longer a range, the dialog carries both -- so this
    stays a precision test rather than quietly becoming a content one.
    """
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Aspirin")
    engine.set_structure_from_smiles(molecule, ASPIRIN)
    result = compute_crippen_logp_contrib_calculator(
        Chem.MolFromMolBlock(molecule.molblock), "u", {"decimal_places": places}
    )

    total = f"{Crippen.MolLogP(Chem.MolFromSmiles(ASPIRIN)):.{places}f}"
    low, high = data_range(result)
    span = f"{low:.{places}f} to {high:.{places}f}"

    dialog = CalculatorInspectorDialog(engine, molecule, result, conformer_molblock=None)
    texts = [label.text() for label in dialog.findChildren(QLabel)]

    visible_sum = f"{sum(result.values.values()):.{places}f}"

    assert f"LogP (Crippen): {total}" in texts  # dialog headline
    assert span in texts  # dialog legend
    balance = next(t for t in texts if "balance" in t)  # dialog balance sentence
    assert f"sum to {visible_sum}" in balance, balance
    assert _summarise(result).startswith(f"LogP (Crippen) {total}")  # panel row
    assert f"LogP (Crippen)\t{total}" in result_to_text(result)  # clipboard
    _dispose(dialog)


@pytest.mark.parametrize("value", [1.004, 1.005, 1.006, -0.004, -0.005, -0.006])
def test_rounding_boundaries_render_identically_in_every_place(qapp, value):
    """"One precision" can still secretly mean several rounding
    implementations. These are the values where they would differ."""
    result = _dataset({0: value}, parameters={"decimal_places": 2, "total": declare_total(value, "T")})

    expected = f"{value:.2f}"
    assert expected in _summarise(result)
    assert f"T\t{expected}" in result_to_text(result)


# --- 4. the clipboard -----------------------------------------------------


def test_a_declared_total_is_copied_exactly_once():
    result = _dataset({0: 0.5, 1: 0.25}, parameters={"total": declare_total(1.0, "LogP (Crippen)")})
    text = result_to_text(result)
    assert text.count("LogP (Crippen)\t1.00") == 1


def test_an_undeclared_dataset_gains_no_total_on_the_clipboard():
    """The summing bug must not reappear on the paste path."""
    result = _dataset({0: 0.5, 1: 0.25})
    lines = result_to_text(result).splitlines()
    assert lines[1].startswith("Atom\t"), lines
    assert not any("0.75" in line for line in lines)


def test_the_copied_total_carries_its_units():
    result = _dataset(
        {0: 100.0}, units="Å²", parameters={"total": declare_total(220.7, "Total SASA", units="Å²")}
    )
    assert "Total SASA\t220.70 Å²" in result_to_text(result)


# --- the explicit-hydrogen depiction is a VIEW ----------------------------


def test_explicit_hydrogens_draws_more_than_the_heavy_atom_skeleton(qapp):
    """Measured by INK, not by searching the SVG for an "H".

    `render_2d_svg`'s own docstring records why: RDKit draws text as
    bezier paths rather than `<text>` nodes, so `svg.count('>H<')` returns
    0 on a depiction that did draw the hydrogens. That exact false signal
    cost a measurement during this work.
    """
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Aspirin")
    engine.set_structure_from_smiles(molecule, ASPIRIN)
    mol = Chem.MolFromMolBlock(molecule.molblock)

    def ink(mode: str) -> int:
        result = compute_crippen_logp_contrib_calculator(mol, "u", {"hydrogens": mode})
        dialog = CalculatorInspectorDialog(engine, molecule, result, conformer_molblock=None)
        image = dialog._view._svg_widget.grab().toImage()
        pixels = [
            image.pixel(x, y) for x in range(0, image.width(), 2) for y in range(0, image.height(), 2)
        ]
        background = max(set(pixels), key=pixels.count)
        drawn = sum(1 for pixel in pixels if pixel != background)
        _dispose(dialog)
        return drawn

    assert ink(EXPLICIT_HYDROGENS) > ink("Heavy atoms only")


def test_opening_the_dialog_never_writes_back_to_the_model(qapp):
    """`Explicit hydrogens` builds a hydrogenated structure INSIDE the
    dialog. This app distinguishes retained, display-aligned and adopted
    conformers, and a dialog quietly writing its working copy into any of
    them would corrupt all three."""
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Aspirin")
    engine.set_structure_from_smiles(molecule, ASPIRIN)
    before_molblock = molecule.molblock
    before_smiles = molecule.canonical_smiles
    before_conformers = list(molecule.conformers)

    result = compute_crippen_logp_contrib_calculator(
        Chem.MolFromMolBlock(molecule.molblock), "u", {"hydrogens": EXPLICIT_HYDROGENS}
    )
    dialog = CalculatorInspectorDialog(engine, molecule, result, conformer_molblock=None)
    _dispose(dialog)

    assert molecule.molblock == before_molblock
    assert molecule.canonical_smiles == before_smiles
    assert list(molecule.conformers) == before_conformers


def test_the_skeleton_is_in_the_same_place_in_every_hydrogen_mode(qapp):
    """A COORDINATE invariant, not a screenshot judgement.

    "The molecule looks like it is in the same place" is an argument
    waiting to happen the first time an RDKit drawing option moves
    something two pixels. Corresponding heavy atoms are compared directly
    instead, so a mode that silently re-laid-out the structure fails here
    naming the atom.
    """
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Aspirin")
    engine.set_structure_from_smiles(molecule, ASPIRIN)
    mol = Chem.MolFromMolBlock(molecule.molblock)
    heavy_atom_count = mol.GetNumAtoms()

    positions = {}
    for mode in ("Heavy atoms only", "Increment of Hs", EXPLICIT_HYDROGENS):
        result = compute_crippen_logp_contrib_calculator(mol, "u", {"hydrogens": mode})
        dialog = CalculatorInspectorDialog(engine, molecule, result, conformer_molblock=None)
        drawn = Chem.MolFromMolBlock(dialog._view._depiction_molblock, removeHs=False)
        conformer = drawn.GetConformer()
        positions[mode] = [conformer.GetAtomPosition(i) for i in range(heavy_atom_count)]
        _dispose(dialog)

    reference = positions["Heavy atoms only"]
    for mode, coordinates in positions.items():
        for index in range(heavy_atom_count):
            assert (reference[index] - coordinates[index]).Length() == pytest.approx(
                0.0, abs=1e-9
            ), f"heavy atom {index} moved in {mode}"


def test_adding_hydrogens_for_the_depiction_moves_no_heavy_atom(qapp):
    """Asserted so a future RDKit that starts re-laying-out fails HERE,
    naming the reason, rather than in a screenshot somebody has to
    interpret. Measured at 0.00e+00 displacement when this was written.
    """
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Aspirin")
    engine.set_structure_from_smiles(molecule, ASPIRIN)

    drawn = Chem.MolFromMolBlock(molecule.molblock)
    with_h = Chem.MolFromMolBlock(
        engine.molblock_with_explicit_hydrogens(molecule.molblock), removeHs=False
    )

    assert with_h.GetNumAtoms() > drawn.GetNumAtoms(), "no hydrogens were added"
    before = drawn.GetConformer()
    after = with_h.GetConformer()
    for index in range(drawn.GetNumAtoms()):
        assert (before.GetAtomPosition(index) - after.GetAtomPosition(index)).Length() == pytest.approx(
            0.0, abs=1e-9
        ), f"heavy atom {index} moved"
