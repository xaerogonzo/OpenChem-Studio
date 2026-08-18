"""What a periodic-table cell's colour is allowed to mean.

The palettes are pure functions, so almost everything here needs no
window. The two tests that do build one are the ones asking whether the
grid really shows what the palette computed -- which is a different claim
from the palette computing it.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, QEvent

from openchem.chem import element_palettes as palettes
from openchem.chem.element_reference import all_symbols, facts_for
from openchem.ui.dialogs.periodic_table_dialog import PeriodicTableDialog


@pytest.fixture
def dialog(qapp):
    built = PeriodicTableDialog()
    yield built
    built.setParent(None)
    built.deleteLater()
    QCoreApplication.sendPostedEvents(built, QEvent.Type.DeferredDelete)


# --- the scale is a value, and the mapping is a pure function ---------------


@pytest.mark.parametrize("key", sorted(palettes.CONTINUOUS))
def test_the_declared_endpoints_map_to_the_ends_of_the_ramp(key):
    spec = palettes.CONTINUOUS[key]

    assert palettes.position_for(spec, spec.minimum) == 0.0
    assert palettes.position_for(spec, spec.maximum) == 1.0


@pytest.mark.parametrize("key", sorted(palettes.CONTINUOUS))
def test_a_value_outside_the_declared_range_clamps_rather_than_running_off(key):
    """**Asserted as clamping rather than left to chance.**

    The alternative -- widening the range to fit -- is the derived-range
    behaviour this module exists to avoid: it would change every other
    element's colour, so two screenshots of the same table would stop
    being comparable.
    """
    spec = palettes.CONTINUOUS[key]
    below = spec.minimum - abs(spec.minimum) - 1000.0
    above = spec.maximum + abs(spec.maximum) + 1000.0

    assert palettes.position_for(spec, below) == 0.0
    assert palettes.position_for(spec, above) == 1.0


@pytest.mark.parametrize("key", sorted(palettes.CONTINUOUS))
def test_an_absent_value_is_never_an_endpoint(key):
    """"Not established" must not read as "very low".

    Several elements have no accepted electronegativity and fifteen have
    no measured melting point. Colouring those at the bottom of the scale
    would be the table inventing data.
    """
    spec = palettes.CONTINUOUS[key]

    assert palettes.position_for(spec, None) is None


def test_every_declared_range_actually_covers_the_shipped_data():
    """A declared range that clipped real elements would be hiding the
    very differences the heatmap exists to show."""
    for key, spec in palettes.CONTINUOUS.items():
        values = [
            value
            for symbol in all_symbols()
            if (value := palettes.value_for(key, symbol)) is not None
        ]
        assert values, f"{key} reads nothing at all"
        assert min(values) >= spec.minimum, f"{key}: {min(values)} below the declared floor"
        assert max(values) <= spec.maximum, f"{key}: {max(values)} above the declared ceiling"


def test_the_atomic_weight_transform_is_declared_and_does_something():
    """**THE CASE THAT FORCED `transform` TO EXIST.** Linear over 1..295
    puts hydrogen through krypton in the bottom sixth of the ramp, so four
    whole periods come out one colour."""
    spec = palettes.CONTINUOUS["atomic_weight"]
    carbon = palettes.value_for("atomic_weight", "C")

    linear = (carbon - spec.minimum) / (spec.maximum - spec.minimum)

    assert spec.transform != "linear"
    assert palettes.position_for(spec, carbon) > linear * 4
    assert spec.transform in spec.legend()


def test_the_legend_is_self_contained():
    """Property, range, transform, units and the unknown swatch, so a
    screenshot is readable without remembering the combo selection."""
    legend = palettes.CONTINUOUS["electronegativity"].legend()

    assert "Pauling electronegativity" in legend
    assert "0.7" in legend and "4" in legend
    assert "linear" in legend
    assert "dimensionless" in legend
    assert "not established" in legend


def test_the_legend_reports_the_same_spec_the_colours_come_from():
    """Otherwise the two can drift and only a screenshot would say so."""
    for key, spec in palettes.CONTINUOUS.items():
        legend = palettes.legend_for(key)
        assert spec.label in legend
        assert palettes.label_for(key) == spec.label


# --- state at room temperature ---------------------------------------------


def test_the_reference_conditions_are_written_down():
    """"Room temperature" is a convention, and a reader arriving with a
    boiling point that disagrees deserves to know which one was used."""
    assert palettes.REFERENCE_TEMPERATURE_C == 25.0
    assert "25" in palettes.DISCRETE["state"].label
    assert palettes.REFERENCE_PRESSURE in palettes.DISCRETE["state"].label


def test_the_two_liquid_elements_are_the_two_liquid_elements():
    liquids = {s for s in all_symbols() if palettes.class_for("state", s) == "liquid"}

    assert liquids == {"Br", "Hg"}


def test_the_eleven_gases_are_the_eleven_gases():
    gases = {s for s in all_symbols() if palettes.class_for("state", s) == "gas"}

    assert gases == {"H", "He", "N", "O", "F", "Ne", "Cl", "Ar", "Kr", "Xe", "Rn"}


def test_helium_is_a_gas_despite_having_no_melting_point():
    """Each branch needs only the number that decides it. Helium does not
    solidify at 1 atm at all, so the CRC gives it no melting point -- and
    a rule demanding both numbers called it "not established"."""
    assert facts_for("He").melting_point_c is None
    assert palettes.class_for("state", "He") == "gas"


def test_radium_is_a_solid_despite_having_no_boiling_point():
    """The mirror case, and the other half of the same lesson."""
    assert facts_for("Ra").boiling_point_c is None
    assert palettes.class_for("state", "Ra") == "solid"


def test_sublimation_is_read_from_the_source_and_never_inferred():
    """**THE INCONSISTENCY THIS PALETTE WAS SENT BACK TO FIX.**

    Melting and boiling points alone cannot derive "sublimes" -- that is a
    fact about the phase diagram. Inferring it from a MISSING boiling
    point would put every superheavy in the class, which is why oganesson
    is the control here.
    """
    subliming = {s for s in all_symbols() if palettes.class_for("state", s) == "sublimes"}

    assert subliming == {"C", "As"}
    assert facts_for("Og").boiling_point_c is None
    assert palettes.class_for("state", "Og") == "not established"


def test_an_element_with_nothing_measured_says_so():
    for symbol in ("Og", "Ts", "Fl"):
        assert palettes.class_for("state", symbol) == "not established"


# --- what the grid does with all that --------------------------------------


def test_a_heatmap_cell_prints_its_value_as_well_as_its_colour(dialog):
    """This table's own rule: colour never carries a fact alone. A grid
    distinguishing ten hues is unreadable to a fair number of people."""
    dialog._palette_combo.setCurrentIndex(palettes.PALETTE_ORDER.index("electronegativity"))

    assert "3.98" in dialog._buttons["F"].text()
    assert "0.79" in dialog._buttons["Cs"].text()


def test_an_element_with_no_value_is_marked_rather_than_coloured_low(dialog):
    dialog._palette_combo.setCurrentIndex(palettes.PALETTE_ORDER.index("electronegativity"))

    assert "not established" in dialog._buttons["He"].toolTip()
    assert dialog._buttons["He"].styleSheet() != dialog._buttons["Cs"].styleSheet()


def test_a_discrete_mode_prints_no_value_line(dialog):
    """The control for the two above: a cell that always showed a third
    line would satisfy them without any of this being mode-dependent."""
    dialog._palette_combo.setCurrentIndex(palettes.PALETTE_ORDER.index("category"))

    assert dialog._buttons["F"].text() == "9\nF"


def test_changing_the_colour_mode_changes_nothing_else(dialog):
    """Modes and tabs are where accidental state coupling appears."""
    dialog.select("Po")
    dialog._tabs.setCurrentIndex(1)
    detail = dialog._detail.text()

    for index in range(dialog._palette_combo.count()):
        dialog._palette_combo.setCurrentIndex(index)

    assert dialog.selected_symbol() == "Po"
    assert dialog._tabs.currentIndex() == 1
    assert dialog._detail.text() == detail


def test_every_declared_mode_can_colour_every_element(dialog):
    """The whole grid, in every mode -- an element the palette has no
    answer for must produce a swatch, not an exception."""
    for index, key in enumerate(palettes.PALETTE_ORDER):
        dialog._palette_combo.setCurrentIndex(index)
        for symbol in all_symbols():
            fill, note, _extra = dialog._fill_and_note(symbol)
            assert fill.startswith("#") and len(fill) == 7, f"{key}/{symbol}: {fill}"
            assert note
