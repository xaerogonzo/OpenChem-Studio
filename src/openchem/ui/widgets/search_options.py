"""The four Vina search controls, built ONCE for both surfaces that offer them.

The Docking panel has offered exhaustiveness, scoring function, rescore and
seed since the rescoring axis landed. The Virtual Screening dialog offered
NONE of them, so a screen ran at whatever the provider happened to default to
and **could not be reproduced even in principle** while a single dock could --
`services/screening_service.py` did not pass `search_options` at all, so a
pinned seed had nowhere to go.

**THIS IS A SHARED WIDGET RATHER THAN A SECOND IMPLEMENTATION, AND THE HELP
CONTRACT IS WHY IT HAD TO BE.** `help_id` names a DEFINITION, not an instance:
"exhaustiveness" means exactly the same thing in a panel and in a dialog, so
it is ONE id with two renderings that `instance_path` tells apart. Writing the
dialog its own contracts would be one concept shredded across two ids -- the
mutation `test_one_concept_is_not_split_across_many_help_ids` exists to
refuse, shipped on purpose.

The drift argument is the ordinary one and applies as well: this project has
paid four times for two implementations of one rule, and here the divergence
would be silent AND meaningful. A dialog offering exhaustiveness 10/20/50
against the panel's 8/16/25/32, or reading a seed of 0 as zero rather than as
"Random", produces perfectly plausible runs that are not the runs the other
surface would have produced.

**IT OWNS THE WIDGETS AND NOT THE LAYOUT.** The panel puts Replicates between
Rescore and Seed, deliberately -- a pinned seed is the root of a DERIVED set
of per-run seeds rather than the number Vina receives, and a reader who meets
Seed first forms the older meaning. The dialog's Replicates lives elsewhere
and means something different again, since N multiplies by the ligand count.
So each surface adds its own rows and neither has to accept the other's
ordering.
"""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QSpinBox, QWidget

from openchem.chem.docking_providers import DEFAULT_EXHAUSTIVENESS, SUPPORTED_SCORING_FUNCTIONS
from openchem.chem.rescoring import SUPPORTED_RESCORE_FUNCTIONS
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip

#: The exhaustiveness values offered. 8 is Vina's own default and 25 the
#: shipped one; both are offered so a run can be compared against either.
#: NOT derived from anything -- there is no registry of sensible search
#: efforts, and inventing one to avoid a literal would be worse than the
#: literal.
EXHAUSTIVENESS_CHOICES = (8, 16, 25, 32)

#: The value a seed spinbox holds when nothing is pinned. Qt's
#: `setSpecialValueText` renders it as "Random", which is Qt's own idiom for
#: an out-of-band value -- rather than a second checkbox whose state could
#: disagree with the number beside it.
UNPINNED_SEED = 0

#: The rescore combo's "not requested" value. It is the EMPTY STRING and not
#: None, because `QComboBox.currentData()` answers None for an item carrying
#: no data at all -- so None would make "Off" and "this combo is broken"
#: indistinguishable to the accessor.
NO_RESCORE = ""


def _label_for(function_id: str) -> str:
    """"vinardo" -> "Vinardo". Derived, so a new registered function needs no
    edit here and cannot appear in the list under its raw id."""
    return function_id[:1].upper() + function_id[1:]


#: The help contracts for the four controls. They live BESIDE the widgets
#: they document rather than in either surface, which is what makes "one
#: concept, one help_id" true by construction instead of by both authors
#: remembering.
CONTROL_HELP = {
    "exhaustiveness": HelpTooltip(
        text=(
            "How hard Vina searches: the number of independent runs, each "
            "starting from a random ligand conformation. Default 25.\n\n"
            "Higher costs proportionally more time. Vina's own default is 8; a "
            "published study of 1, 8, 25, 50, 75 and 100 found 8 performs well "
            "and that median pose error changes little above 25, so 25 is this "
            "application's documented choice rather than a claimed optimum.\n\n"
            "It does not rescue a search box the ligand does not fit in -- more "
            "sampling of the wrong space is still the wrong space."
        ),
        tier=3, help_id="docking.exhaustiveness", topic="docking",
        help_anchor="docking",
    ),
    "scoring_function": HelpTooltip(
        text=(
            "Which of Vina's scoring functions ranks the poses. Default Vina.\n\n"
            "Vinardo is a re-parameterised alternative its authors report as "
            "better at predicting poses. Its scores are NOT on the same scale "
            "as Vina's, so numbers from the two must never be compared or put "
            "in one ranking; the function used is recorded with every result."
        ),
        tier=3, help_id="docking.scoring_function", topic="docking",
        help_anchor="docking",
    ),
    "rescore_with": HelpTooltip(
        text=(
            "Score every pose a SECOND time with a different function, after "
            "the search. Off by default, and it costs one extra Vina call per "
            "pose.\n\n"
            "The pose is not changed and neither is the affinity beside it: "
            "AutoDock Vina is documented as strong at finding the right pose "
            "and weaker at ranking one ligand against another, so this "
            "replaces the number and keeps the geometry.\n\n"
            "The two numbers are on DIFFERENT SCALES and must never be "
            "compared, averaged or put in one ranking. On one fentanyl pose "
            "Vina reports -8.78 and Vinardo -5.47 for the same atoms in the "
            "same place. Even choosing Vina here does not reproduce the "
            "affinity for any pose but the first, because a docking run uses "
            "one shared unbound reference for all its poses and a rescore "
            "uses each pose's own.\n\n"
            "Measured over 56 single-assay series on eight receptors, Vinardo "
            "did NOT rank better than Vina: the median difference in rank "
            "correlation was +0.000. It reorders poses without improving the "
            "ordering, so it is offered as a second opinion and not as an "
            "improvement."
        ),
        tier=3, help_id="docking.rescore_with", topic="docking",
        help_anchor="docking",
        source_key="quiroga2016",
    ),
    "random_seed": HelpTooltip(
        text=(
            "The random seed for Vina's search. 'Random' picks a fresh one for "
            "each run.\n\n"
            "Vina's search is stochastic, so two runs of identical inputs give "
            "slightly different answers. The seed used is always recorded with "
            "the result, so any run can be repeated afterwards even when it was "
            "not pinned in advance. Pin one to compare two settings without the "
            "search itself moving between them.\n\n"
            "This reproduces a run under the same Vina version and settings; it "
            "is not a guarantee of identical output across versions or machines."
        ),
        tier=3, help_id="docking.random_seed", topic="docking",
        help_anchor="docking",
    ),
}


class SearchOptionsControls:
    """The four widgets, and the ONE thing entitled to read them.

    Not a `QWidget`: it owns four controls and no layout, so a surface can
    interleave its own rows between them. Every widget is parented to
    `parent` on construction, so the ordinary Qt ownership cascade applies
    and nothing here has to be disposed of separately.
    """

    def __init__(self, parent: QWidget) -> None:
        self.exhaustiveness = QComboBox(parent)
        for value in EXHAUSTIVENESS_CHOICES:
            # Read back from the item DATA rather than parsed out of the
            # label, so translating or reformatting the text cannot change
            # what is sent.
            self.exhaustiveness.addItem(str(value), value)
        self.exhaustiveness.setCurrentIndex(
            self.exhaustiveness.findData(DEFAULT_EXHAUSTIVENESS)
        )
        apply_help_tooltip(self.exhaustiveness, CONTROL_HELP["exhaustiveness"])

        # BUILT FROM THE REGISTERED VOCABULARY, never from two string
        # literals. `SUPPORTED_SCORING_FUNCTIONS` is what
        # `VinaDockingProvider` validates against, so a function this combo
        # offers is a function the provider accepts, by construction rather
        # than by both lists being edited together.
        self.scoring_function = QComboBox(parent)
        for function_id in SUPPORTED_SCORING_FUNCTIONS:
            self.scoring_function.addItem(_label_for(function_id), function_id)
        apply_help_tooltip(self.scoring_function, CONTROL_HELP["scoring_function"])

        # "Off" FIRST AND DEFAULT. A rescore costs one extra Vina call per
        # pose, and the benefit on any given receptor is measured as absent
        # rather than merely unknown -- see the contract. So it is opt-in,
        # and at Off a request carries no `rescore_with` key at all.
        #
        # A combo rather than a checkbox: there are two functions to choose
        # between, and "Off" as a first item makes not-requested an explicit
        # state rather than something inferred from a cleared box.
        #
        # VINARDO IS LISTED FIRST AMONG THE FUNCTIONS, reversing the
        # registered order, because rescoring a Vina search with Vina is the
        # degenerate case -- offered, since it is the only way to see the
        # shared-unbound-reference effect the contract describes, but not the
        # one anybody reaches for.
        self.rescore_with = QComboBox(parent)
        self.rescore_with.addItem("Off", NO_RESCORE)
        for function_id in reversed(SUPPORTED_RESCORE_FUNCTIONS):
            self.rescore_with.addItem(_label_for(function_id), function_id)
        apply_help_tooltip(self.rescore_with, CONTROL_HELP["rescore_with"])

        self.seed = QSpinBox(parent)
        self.seed.setRange(UNPINNED_SEED, 2**31 - 1)
        self.seed.setValue(UNPINNED_SEED)
        self.seed.setSpecialValueText("Random")
        apply_help_tooltip(self.seed, CONTROL_HELP["random_seed"])

    def options(self) -> dict[str, object]:
        """The search settings as the four controls currently read them.

        The ONE accessor. Reading these anywhere else is how a surface starts
        displaying one thing and docking another, which is the defect this
        whole module exists to make unrepeatable across two surfaces rather
        than merely unlikely within one.

        A seed of 0 is the spinbox's special "Random" value and is sent as
        `None`, which the provider turns into a CHOSEN seed rather than
        leaving to Vina -- so an unpinned run is still reproducible after the
        fact.
        """
        seed = self.seed.value()
        options: dict[str, object] = {
            "exhaustiveness": self.exhaustiveness.currentData(),
            "scoring_function": self.scoring_function.currentData(),
            "seed": None if seed == UNPINNED_SEED else seed,
        }
        # ABSENT rather than empty when Off, so a run that asked for no
        # rescore sends the byte-identical dict it sent before this control
        # existed. `tests/test_ligand_extent_warning.py` asserts this as an
        # exact dict, and that assertion stays valid unedited -- which is
        # the point: an opt-in feature must not re-baseline everyone else's
        # request.
        rescore = self.rescore_with.currentData()
        if rescore:
            options["rescore_with"] = rescore
        return options


__all__ = [
    "CONTROL_HELP",
    "EXHAUSTIVENESS_CHOICES",
    "NO_RESCORE",
    "UNPINNED_SEED",
    "SearchOptionsControls",
]
