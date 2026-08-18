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
    very differences the heatmap exists to show.

    **THE HYBRID'S SPEC IS IN HERE TOO.** This guard walked `CONTINUOUS`
    alone, so the half-life range shipped unchecked -- and it is the range
    most likely to be wrong, being read off a measurement rather than off
    a table of radii.
    """
    for key, spec in {
        **palettes.CONTINUOUS,
        **{k: h.spec for k, h in palettes.HYBRID.items()},
    }.items():
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


# --- N5: the two radioactivity modes ---------------------------------------


def test_stability_reads_evaluated_stability_and_not_natural_abundance():
    """**URANIUM IS THE WHOLE REASON THIS MODE WAS DEFERRED.**

    The obvious implementation -- an element carrying a natural abundance
    has a stable isotope -- gets carbon, technetium and every synthetic
    element right, and is wrong about uranium and thorium, which are
    naturally occurring and have no stable isotope at all. So a test built
    on carbon and technetium passes against the broken rule.
    """
    assert palettes.stability_class("U") == "radioactive only"
    assert palettes.stability_class("Th") == "radioactive only"

    # ... and the two classes it must still get right.
    assert palettes.stability_class("C") == palettes.STABLE_CLASS
    assert palettes.stability_class("Tc") == "radioactive only"


def test_every_stability_answer_is_one_of_the_declared_classes():
    """A class the legend does not name would render as a bare `#eeeeee`
    with the raw string as its tooltip -- which looks like a styling bug
    rather than like a palette that has outgrown its own vocabulary."""
    declared = set(palettes.DISCRETE["stability"].classes)

    assert {palettes.stability_class(s) for s in all_symbols()} <= declared


def test_a_stable_element_is_a_terminal_CLASS_and_not_a_point_on_the_ramp():
    """**THE TOP OF THE SCALE IS NOT WHERE STABILITY GOES.** Carbon's
    longest half-life is not a large number, it is not a number: C-12 does
    not decay. Encoding it as 10^30 years would make the ramp's ceiling a
    claim nobody made, and reduce "has a stable isotope" -- the single
    most useful thing this mode can say -- to a colour to be interpreted.
    """
    carbon = palettes.half_life_shading("C")

    assert carbon.terminal == palettes.STABLE_CLASS
    assert carbon.position is None
    assert carbon.display == "stable"


def test_exactly_one_of_position_and_terminal_is_set_for_every_element():
    """A cell on the ramp AND off it would let the dialog take whichever
    branch it happened to test first."""
    for symbol in all_symbols():
        shading = palettes.half_life_shading(symbol)
        on_ramp = shading.position is not None
        off_ramp = shading.terminal is not None

        assert on_ramp != off_ramp, f"{symbol}: {shading}"


def test_the_ramp_holds_the_thirty_eight_elements_with_no_stable_isotope():
    """Measured, and worth pinning: the ramp is not a fringe of the table.

    Eighty elements are terminal-stable and thirty-eight are plotted --
    and none is "not established", because every element without a stable
    isotope has at least one nuclide with a measured half-life. That last
    fact makes the third class UNREACHABLE from real data today, which is
    why it is asserted on the function directly below rather than through
    an element that would demonstrate it.
    """
    kinds = [palettes.half_life_shading(s) for s in all_symbols()]

    assert sum(1 for k in kinds if k.position is not None) == 38
    assert sum(1 for k in kinds if k.terminal == palettes.STABLE_CLASS) == 80
    assert sum(1 for k in kinds if k.terminal == palettes.UNESTABLISHED_CLASS) == 0


def test_an_element_whose_table_says_nothing_gets_the_third_class(monkeypatch):
    """No shipped element reaches this branch, so it is asserted here.

    An unreachable branch is a question about WHERE to assert, not
    automatically dead code: the contract is that a palette never invents
    a position, and answering "0.0" for an element nothing is known about
    would put it at the fast-decay end of the scale.
    """
    monkeypatch.setattr(palettes.nuclide_data, "has_stable_isotope", lambda s: False)
    monkeypatch.setattr(
        palettes.nuclide_data, "longest_radioactive_isotope", lambda s: None
    )

    shading = palettes.half_life_shading("C")

    assert shading.terminal == palettes.UNESTABLISHED_CLASS
    assert shading.position is None


def test_a_qualified_half_life_is_never_presented_as_an_exact_one():
    """**THE RAMP'S OWN BLIND SPOT.** A colour means a magnitude, so it
    cannot say "estimated" -- and five of the thirty-eight plotted values
    are. Without the mark, moscovium's systematics-derived 5 s renders
    exactly like uranium's measured 4.46 Gy.
    """
    estimated = [
        s for s in all_symbols() if palettes.half_life_shading(s).qualified
    ]

    assert set(estimated) == {"Mc", "Mt", "Nh", "No", "Rf"}
    for symbol in estimated:
        assert palettes.half_life_shading(symbol).display.endswith("#")

    # The control: a measured value carries no mark at all.
    assert not palettes.half_life_shading("U").qualified
    assert not palettes.half_life_shading("U").display.endswith("#")


def test_the_log10_transform_is_declared_and_is_load_bearing():
    """Linear over 0.01..1e28 seconds is not a worse scale, it is no scale.

    Every element below thorium lands in the bottom 0.05% of the ramp, so
    thirty-six of the thirty-eight would share one colour with each other
    and with the floor.
    """
    spec = palettes.HYBRID["longest_half_life"].spec

    assert spec.transform == "log10"

    linear = palettes.PaletteSpec(spec.key, spec.label, spec.units, spec.minimum, spec.maximum)
    uranium = 1.4e17

    assert palettes.position_for(linear, uranium) < 0.0001
    assert 0.6 < palettes.position_for(spec, uranium) < 0.7


def test_the_two_transforms_act_at_different_points():
    """Pinned because it reads like an inconsistency and is a decision.

    `square root` bends the FRACTION; `log10` is a change of variable on
    the value and both endpoints. Unifying them would silently recolour
    either the atomic-weight heatmap or the half-life one, so the
    difference is asserted rather than left to a comment.
    """
    root = palettes.PaletteSpec("k", "k", "", 1.0, 100.0, "square root")
    log = palettes.PaletteSpec("k", "k", "", 1.0, 100.0, "log10")

    # sqrt of the fraction: sqrt(49/99)
    assert palettes.position_for(root, 50.0) == pytest.approx(0.7036, abs=1e-4)
    # log10 of the value, normalised: log10(50)/log10(100)
    assert palettes.position_for(log, 50.0) == pytest.approx(0.8495, abs=1e-4)

    # Both still pin the declared endpoints, which is what callers rely on.
    for spec in (root, log):
        assert palettes.position_for(spec, 1.0) == 0.0
        assert palettes.position_for(spec, 100.0) == 1.0


def test_bismuth_sits_at_the_top_of_the_ramp_and_livermorium_at_the_bottom():
    """The two ends, named, so a future NUBASE that moves either fails
    here rather than quietly rescaling every cell between them.

    Bismuth is the interesting one: it was counted stable until its alpha
    decay was measured, and Bi-209's 2.01e19 y puts it a full nine orders
    of magnitude above thorium.
    """
    plotted = {
        s: shading.position
        for s in all_symbols()
        if (shading := palettes.half_life_shading(s)).position is not None
    }

    assert max(plotted, key=plotted.get) == "Bi"
    assert min(plotted, key=plotted.get) in {"Lv", "Ts"}


def test_the_legend_names_both_terminal_classes():
    """A swatch the legend does not explain is a colour with no meaning,
    and this palette has two of them beside the ramp."""
    legend = palettes.legend_for("longest_half_life")

    assert palettes.STABLE_CLASS in legend
    assert palettes.UNESTABLISHED_CLASS in legend
    assert "log10" in legend


def test_the_legend_explains_every_mark_any_cell_can_print():
    """**THE DEFECT A GREEN SUITE SHIPPED.** Five cells print a trailing
    `#` because a colour cannot say "estimated" -- and the legend never
    said what it meant, so the mark was decodable only from a tooltip.
    A screenshot carries the legend and not the tooltip, which is the
    reason this table's legend is required to be self-contained.

    Derived from what the cells ACTUALLY print, so a future NUBASE that
    puts a bound on one of these values fails here rather than printing a
    `>` nobody can read.
    """
    legend = palettes.legend_for("longest_half_life")
    marks = {
        character
        for symbol in all_symbols()
        for character in palettes.half_life_shading(symbol).display
        if character in "#<>~"
    }

    assert marks, "no cell carries a mark, so this guard proves nothing"
    for mark in marks:
        assert mark in legend, f"a cell prints {mark!r} and the legend never says so"


def test_the_legend_does_not_read_as_though_one_class_is_the_exception():
    """"has a stable isotope, not established shown separately" is what
    the rendered legend said, and it attaches "shown separately" to the
    second class alone."""
    legend = palettes.legend_for("longest_half_life")

    assert "shown separately: " in legend
    assert "shown separately" not in legend.split("shown separately: ", 1)[1]


# --- and what the grid does with them ---------------------------------------


def test_the_grid_gives_a_stable_element_a_colour_the_RAMP_NEVER_PRODUCES(dialog):
    """**"DIFFERENT FROM URANIUM" IS NOT THE CLAIM**, and asserting that
    let a mutation through: painting carbon with the ramp's top colour
    still differs from uranium's 0.638, so the test passed while the
    terminal class had been silently turned back into a very large number.

    The claim is that the swatch is off the ramp ENTIRELY -- not equal to
    any colour the ramp can produce, at either endpoint or at any plotted
    element's position.
    """
    from openchem.ui.dialogs.periodic_table_dialog import _ramp

    index = palettes.PALETTE_ORDER.index("longest_half_life")
    dialog._palette_combo.setCurrentIndex(index)

    carbon_fill, carbon_note, carbon_extra = dialog._fill_and_note("C")
    _uranium_fill, uranium_note, _extra = dialog._fill_and_note("U")

    reachable = {_ramp(0.0), _ramp(1.0)} | {
        _ramp(shading.position)
        for symbol in all_symbols()
        if (shading := palettes.half_life_shading(symbol)).position is not None
    }

    assert carbon_fill not in reachable
    assert carbon_extra == "stable"
    assert "U-238" in uranium_note
    assert palettes.STABLE_CLASS in carbon_note


def test_the_stable_swatch_is_the_same_colour_in_both_radioactivity_modes(dialog):
    """The two modes are one question asked twice, so switching between
    them must not repaint the eighty elements the question is not about.

    That is also what makes the terminal class visibly a CLASS: it carries
    the same meaning, and the same green, whether or not a ramp is on
    screen beside it.
    """
    fills = {}
    for key in ("stability", "longest_half_life"):
        dialog._palette_combo.setCurrentIndex(palettes.PALETTE_ORDER.index(key))
        fills[key] = {s: dialog._fill_and_note(s)[0] for s in all_symbols()}

    stable = [s for s in all_symbols() if palettes.stability_class(s) == palettes.STABLE_CLASS]

    assert len(stable) == 80
    for symbol in stable:
        assert fills["stability"][symbol] == fills["longest_half_life"][symbol], symbol


def test_the_grid_says_a_value_is_estimated_in_words_not_only_in_a_mark(dialog):
    """The cell has room for `#`; the tooltip has room for the sentence."""
    index = palettes.PALETTE_ORDER.index("longest_half_life")
    dialog._palette_combo.setCurrentIndex(index)

    _fill, note, extra = dialog._fill_and_note("Mc")

    assert extra.endswith("#")
    assert "not an exact measurement" in note
    assert "estimated" in note

    assert "not an exact measurement" not in dialog._fill_and_note("U")[1]


def test_uranium_is_not_coloured_as_stable_in_the_grid(dialog):
    """The end-to-end form of the deferral: whichever way the two modes
    are implemented, uranium may never share carbon's swatch."""
    for key in ("stability", "longest_half_life"):
        dialog._palette_combo.setCurrentIndex(palettes.PALETTE_ORDER.index(key))

        assert dialog._fill_and_note("U")[0] != dialog._fill_and_note("C")[0], key


def test_the_radioactivity_binary_is_readable_without_seeing_colour(dialog):
    """**RED AND GREEN, WHICH IS THE ONE PAIR THAT CANNOT CARRY A FACT
    ALONE.** Every other discrete mode spreads its classes over four or
    ten hues, so confusing two costs a reader one element; here it costs
    them the entire picture, and the picture is the point of the mode.

    Found by looking at the rendered grid. Every test was green, and
    nothing in the suite had an opinion about whether a cell said which
    class it was in.
    """
    dialog._palette_combo.setCurrentIndex(palettes.PALETTE_ORDER.index("stability"))

    assert dialog._buttons["C"].text() == "6\nC\nstable"
    assert dialog._buttons["U"].text() == "92\nU\ndecays"
    assert dialog._buttons["Tc"].text() == "43\nTc\ndecays"

    # Every element says something, and the two words are not near-twins.
    for symbol in all_symbols():
        assert dialog._fill_and_note(symbol)[2] in {"stable", "decays", "\u2014"}


def test_the_other_discrete_modes_are_left_alone(dialog):
    """The control. The cure for a red/green binary must not become "every
    cell gains a third line", which would crowd the ten-class category
    mode the table has always opened with.
    """
    for key in ("category", "block", "state"):
        dialog._palette_combo.setCurrentIndex(palettes.PALETTE_ORDER.index(key))

        assert dialog._fill_and_note("C")[2] == "", key
