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
from openchem.ui.panels.property_panel import PropertyPanel
from openchem.ui.result_adapters import summarise
from openchem.ui.result_clipboard import result_to_text
from openchem.ui.widgets.results_view import ResultsView
from openchem.ui.visualization import build_atom_color_layer, data_range

import conftest
from conftest import dispose

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
    conftest.dispose(widget)


def _row_caption(panel: PropertyPanel, key: tuple[str, str]) -> str:
    """The caption's FULL text, not the string currently painted.

    A row caption is an `_ElidingLabel`, so `.text()` is whatever
    fits the panel's present width -- at the narrow widths these fixtures
    use, `'Molecular Weight (g/mol)'` paints as `'Molecul…'`. Reading it
    would make this file assert the fixture's geometry instead of the thing
    it exists for.

    **The guard is not weakened by this.** What it catches is a row
    captioned with its raw id, and a row captioned `mol_wt` has `mol_wt` as
    its full text too -- `_unelided_text` returns the id just as plainly as
    it returns the display name. Only the width-dependent truncation is
    removed from the comparison.
    """
    from openchem.ui.panels.property_panel import _unelided_text

    form = panel._row_sections[key].content_layout()
    row, _role = form.getWidgetPosition(panel._value_labels[key])
    return _unelided_text(form.itemAt(row, QFormLayout.ItemRole.LabelRole).widget())


def _projected(result) -> str:
    """The per-atom result AS THE READER RENDERS IT, flattened to one line.

    **THIS WAS `property_panel._summarise`**, the one-line summary the
    panel drew in the result's row. 2c removes that row, and the reader's
    own projection is the surface that carries the same four things -- the
    declared total leading, the atom count, the value range and the atom
    basis -- at the producer's declared precision. Flattened here so the
    assertions below stay about CONTENT and precision rather than about
    which fact carries which half.
    """
    view = summarise(
        result,
        result_id=getattr(result, "property_id", "r"),
        name=getattr(result, "name", "R"),
        category="physicochemical",
        structure_version=0,
    )
    return " ".join(f"{f.label} {f.display_value}" for f in view.facts)


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


def test_every_descriptor_reaches_the_reader_under_its_display_name_and_units(qapp):
    """DERIVED FROM `_DESCRIPTOR_SPECS`, so a descriptor added later is
    covered without touching this test.

    The sequence matters and is exactly what `DescriptorService` does: a
    RUNNING placeholder for every id FIRST (published before `compute()`
    runs, so it can only carry `name=descriptor_id, units=""`), then the
    real values. The panel row was captioned from the placeholder and never
    corrected, which is why the nice names in `_DESCRIPTOR_SPECS` were
    computed on every run and thrown away -- 26 of 26 showing `mol_logp`,
    `mol_wt`, `tpsa`.

    **THE ROW IS GONE AND THE SEQUENCE IS NOT.** 2c makes Properties a
    launcher, so these are read in the reader's aggregate entry. The
    aggregate is re-projected from the LATEST value per id every time,
    which is structurally why it cannot repeat the defect -- there is no
    first render to be stuck with. Driven through the panel rather than by
    building the aggregate directly, because the placeholder-then-value
    ordering is the thing under test and only the panel sees both.
    """
    bus = EventBus()
    panel = PropertyPanel(bus, CalculatorRegistry(), _FakeDescriptorService(), ChemistryEngine())
    reader = ResultsView()
    panel.attach_reader(reader)
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

    aggregate = reader.merged().report_for("molecular_properties")
    assert aggregate is not None, "the descriptors reached the reader not at all"
    facts = {fact.label: fact for fact in aggregate.facts}

    wrong = []
    for descriptor_id, name, units, _category in _DESCRIPTOR_SPECS:
        fact = facts.get(name)
        if fact is None:
            wrong.append((descriptor_id, "missing", name))
        elif fact.units != units:
            wrong.append((descriptor_id, fact.units, units))

    assert not wrong, f"descriptors still carrying the wrong name or units: {wrong}"
    # **THE UNITS STAY IN THEIR OWN FIELD.** The panel composed them into the
    # caption because a form row has one string; a `Fact` has `units` beside
    # `value` and `value_with_units` composes them, which is what stopped
    # `report_adapter`'s facts exporting "C: 60.00 % %".
    raw_ids = {did for did, _n, _u, _c in _DESCRIPTOR_SPECS}
    assert not (set(facts) & raw_ids), (
        f"facts still labelled with a raw id: {sorted(set(facts) & raw_ids)}"
    )
    dispose(reader)
    _dispose(panel)


def test_the_reported_descriptor_reads_logp_rather_than_mol_logp(qapp):
    """The specific value from the screenshot, named so a regression is
    recognisable as the thing that was reported."""
    bus = EventBus()
    panel = PropertyPanel(bus, CalculatorRegistry(), _FakeDescriptorService(), ChemistryEngine())
    reader = ResultsView()
    panel.attach_reader(reader)
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

    aggregate = reader.merged().report_for("molecular_properties")
    labels = {fact.label for fact in aggregate.facts}
    assert "LogP" in labels
    assert "mol_logp" not in labels
    dispose(reader)
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

    It is the TOTAL they must agree on. The panel row that used to be the
    second surface carried no range, because the section it sat in had no
    room for both; 2c removed the row, and the reader's projection carries
    the total AND the range AND the atom basis, so the constraint that
    shaped the old assertion is gone with it.
    """
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="Aspirin")
    engine.set_structure_from_smiles(molecule, ASPIRIN)
    result = compute_crippen_logp_contrib_calculator(Chem.MolFromMolBlock(molecule.molblock), "u", {})

    dialog = CalculatorInspectorDialog(engine, molecule, result, conformer_molblock=None)
    headline = f"{Crippen.MolLogP(Chem.MolFromSmiles(ASPIRIN)):.2f}"

    texts = [label.text() for label in dialog.findChildren(QLabel)]
    assert f"LogP (Crippen): {headline}" in texts, texts
    assert f"LogP (Crippen) {headline}" in _projected(result)
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


def test_the_reader_keeps_everything_the_row_showed_and_adds_the_total(qapp):
    """The projection is strictly richer than the row it replaced.

    An earlier version of this guard asserted the row must not GROW,
    because carrying the total and the range together overflowed a
    starved section. That starvation was a separate bug -- a
    height-for-width flag re-armed by a style change -- and it was fixed
    on master while this branch was in flight. Re-measured on the merge
    with the `dump` drive step: row 63/63, section 208/208, `ok`.

    So the constraint is gone, and asserting it now would pin a
    workaround in place for a bug that no longer exists. What is asserted
    instead is the CONTENT contract: the total leads, and nothing the old
    row carried was lost. The layout itself is guarded far better by
    `test_property_panel_long_values.py`, which measures actual clipping
    and carries a control proving its probe can see one.
    """
    result = compute_crippen_logp_contrib_calculator(Chem.MolFromSmiles(ASPIRIN), "u", {})
    summary = _projected(result)
    low, high = data_range(result)

    assert "LogP (Crippen) 1.31" in summary  # the declared total
    assert f"Atoms {len(result.values)}" in summary  # the count, as before
    assert f"{low:.2f} to {high:.2f}" in summary  # the range, as before
    # And the one the row never had room for: what the values are keyed to.
    assert "heavy atoms" in summary, summary


# --- 3. one precision -----------------------------------------------------


@pytest.mark.parametrize("places", [0, 2, 4])
def test_one_dataset_renders_at_one_precision_everywhere(qapp, places):
    """Headline, balance, legend, panel row and clipboard all go through
    `label_decimals`. Four of them used to disagree.

    Each surface is asserted at whatever it SHOWS, so this stays a
    precision test rather than quietly becoming a content one. The fourth
    surface was the Properties row until 2c removed it; the reader's
    projection replaced it and carries both the total and the range, which
    is more of the contract under one assertion rather than less.
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
    projected = _projected(result)
    assert f"LogP (Crippen) {total}" in projected  # reader: the total
    assert span in projected  # reader: range, at the same precision
    assert f"LogP (Crippen)\t{total}" in result_to_text(result)  # clipboard
    _dispose(dialog)


@pytest.mark.parametrize("value", [1.004, 1.005, 1.006, -0.004, -0.005, -0.006])
def test_rounding_boundaries_render_identically_in_every_place(qapp, value):
    """"One precision" can still secretly mean several rounding
    implementations. These are the values where they would differ."""
    result = _dataset({0: value}, parameters={"decimal_places": 2, "total": declare_total(value, "T")})

    expected = f"{value:.2f}"
    assert expected in _projected(result)
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
