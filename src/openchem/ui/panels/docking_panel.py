from __future__ import annotations

from PySide6.QtCore import QRect, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QPushButton,
    QSpinBox,
    QStyle,
    QStyleOptionSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import logging

from openchem.chem.calculation_input import canonical_conformer
from openchem.app.settings import Settings
from openchem.chem.docking_providers import DEFAULT_EXHAUSTIVENESS
from openchem.chem.engine import ChemistryEngine
from openchem.domain.common import describe_failure
from openchem.domain.docking import DockingBox, pose_score_of
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import DockingJobStateChanged, DockingResultReady, MoleculeSelected
from openchem.services.docking_service import DEFAULT_REPLICATES, DockingService
from openchem.ui.dialogs.external_tools_dialog import ExternalToolsDialog
from openchem.ui.molecule_combo import repopulate, select
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip
from openchem.ui.widgets.search_options import (
    CONTROL_HELP as SEARCH_CONTROL_HELP,
    SearchOptionsControls,
)

logger = logging.getLogger("openchem.ui")

_POSE_COLUMNS = (
    "Pose",
    "Binding Affinity (kcal/mol)",
    "RMSD l.b.",
    "RMSD u.b.",
    "Rescore",
)

#: The rescore column, named rather than indexed for the reason
#: `_AFFINITY_COLUMN` is. It is HIDDEN unless a rescore was requested, and
#: its header text is replaced at populate time with the function that
#: produced the number plus "(separate scale)".
_RESCORE_COLUMN = "Rescore"

def coordinate_spin_width(spin: QDoubleSpinBox) -> int:
    """Wide enough for the widest value the spin's RANGE permits, and no wider.

    **THE PANEL DID NOT FIT THE DOCK IT OPENS IN.** Its minimum was 466 px
    against a dock that opens at `main_window._INITIAL_RIGHT_DOCK_WIDTH` = 420,
    so ~26 px of every widget sat past the right edge behind the scroll area:
    the Dock button rendered as "Doc", "RMSD u.b." as "RMSI", and the replicate
    spread label was cut mid-word on every line. Pre-existing -- an artifact
    taken before that label existed shows the box status clipped identically as
    `box 16x18x16 A (size cl`.

    The cause is the six coordinate spins. Qt sizes a `QDoubleSpinBox` to the
    widest value its RANGE permits and then adds slack, so these ask 109 px for
    a number that in practice reads "-58.78". Three of them plus a form label
    column is a 444 px group in a 420 px dock.

    **DERIVED FROM THE FONT AND THE STYLE, NEVER A PIXEL CONSTANT**, and the
    first version of this was a flat 100 px that measured beautifully and was
    wrong in kind. Under a larger UI font that cap gives the line edit 80 px
    for a value needing 96 -- so it would clip the NUMBER, which is strictly
    worse than clipping a label. Measured both ways:

        platform    text   chrome   Qt's hint   this
        windows       44       52         109     96 + a digit
        offscreen     96       20         132    116 + a digit

    The chrome comes from the style's own `SC_SpinBoxEditField` rather than an
    allowance: a first attempt guessed 30 px for the buttons and frame, which
    is why 90 px looked fine and clipped. Asked of the LINE EDIT -- where the
    text is painted -- it is 52 on this platform and 20 on the other.

    One digit of margin, also font-derived, because the exact fit leaves a
    rounding error nowhere to go. **NO TEST DISTINGUISHES IT**, and that is
    recorded rather than papered over: without the margin the line edit comes
    out exactly as wide as the text, which still satisfies the fits-the-value
    guard. Asserting a specific slack would only restate this line.

    **`flow_row` IS NOT THE CURE**, for the reason this file already records
    about the strip-checkbox row: it wraps, so an `x, y, z` triple would split
    across lines -- worse to read than the clip -- and it would cost ~42 px of
    height in a panel whose 3D sibling was once 63 px tall.
    """
    metrics = QFontMetrics(spin.font())
    widest = max(
        metrics.horizontalAdvance(spin.textFromValue(spin.minimum())),
        metrics.horizontalAdvance(spin.textFromValue(spin.maximum())),
    )
    option = QStyleOptionSpinBox()
    spin.initStyleOption(option)
    hint = spin.sizeHint()
    option.rect = QRect(0, 0, hint.width(), hint.height())
    field = spin.style().subControlRect(
        QStyle.ComplexControl.CC_SpinBox,
        option,
        QStyle.SubControl.SC_SpinBoxEditField,
        spin,
    )
    return widest + (hint.width() - field.width()) + metrics.horizontalAdvance("0")


#: The pose column that takes whatever width the other three do not need.
#:
#: NAMED RATHER THAN INDEXED, so reordering `_POSE_COLUMNS` cannot silently
#: stretch a different column -- an index would still be a valid column and
#: nothing would look wrong until somebody magnified the header.
_AFFINITY_COLUMN = "Binding Affinity (kcal/mol)"

#: What each column MEANS, which the headers alone do not say -- reported
#: as confusing by a user who read the RMSD columns as accuracy against an
#: experimental structure. They are not: both are measured against pose 1.
#:
#: THE SCORING ERROR IS QUOTED WITH ITS SOURCE, AND ONLY BECAUSE IT HAS
#: ONE. It was first written in from memory, removed because nothing in
#: this tree supported it, and restored only after the paper was read:
#: `[source:trott_olson2010]`, "Vina achieves a comparatively low standard
#: error of 2.85 kcal/mol". The remembered figure turned out to be right,
#: which is not a reprieve -- it was unverifiable at the time, and a
#: tooltip is exactly where an unsourced number acquires false authority.
#:
#: ATTRIBUTED, NOT STATED FLATLY. It is the authors' standard error of
#: predicted against experimental binding free energies on THEIR
#: 190-complex set; it is not a universal error bar for any given run.
#: THE FIRST CONTRACTS IN THE APPLICATION, and the reason they are these
#: four: the question that started all of this was "what are RMSD l.b. and
#: u.b.?", and nothing answered it. They are also the worked example that
#: the whole chain carries real data -- contract, inventory, guard, CLI.
_POSE_COLUMN_HELP = {
    "Pose": HelpTooltip(
        text="",  # filled from _POSE_COLUMN_TOOLTIPS below
        tier=2,
        help_id="docking.pose_rank",
        topic="docking",
        help_anchor="docking",
    ),
    "Binding Affinity (kcal/mol)": HelpTooltip(
        text="",
        tier=3,
        help_id="docking.binding_affinity",
        topic="docking",
        help_anchor="docking",
        # The one external claim of the four: the standard error quoted in
        # the text is the authors' own, for their own 190-complex set.
        source_key="trott_olson2010",
    ),
    "RMSD l.b.": HelpTooltip(
        text="", tier=3, help_id="docking.rmsd_lower_bound", topic="docking",
        help_anchor="docking",
    ),
    "RMSD u.b.": HelpTooltip(
        text="", tier=3, help_id="docking.rmsd_upper_bound", topic="docking",
        help_anchor="docking",
    ),
    "Rescore": HelpTooltip(
        text="",
        tier=3,
        help_id="docking.rescore",
        topic="docking",
        help_anchor="docking",
        # Vinardo is the function offered, and the paper is what says it is
        # a real alternative rather than a re-scaling of Vina.
        source_key="quiroga2016",
    ),
}

#: The panel's own controls.
#:
#: The three box-centre spin boxes share ONE contract and the three sizes
#: share another: "a coordinate of the search box centre" is one concept
#: rendered once per axis, and which axis is on the label beside it.
_CONTROL_HELP = {
    "receptor": HelpTooltip(
        text=(
            "Which macromolecule in the project to dock against.\n\n"
            "Changing it resets the search box, the kept-chain list and the "
            "assembly choice: a chain id and a box position mean different "
            "things in a different structure, and carrying them across would "
            "silently dock against the wrong place."
        ),
        tier=2, help_id="docking.receptor", topic="docking", help_anchor="docking",
    ),
    "receptor_contents": HelpTooltip(
        text=(
            "Lists the chains, ligands and waters in the selected receptor, and "
            "lets you choose which to keep and whether to build the biological "
            "assembly.\n\n"
            "Read on demand rather than on every selection, because parsing a "
            "receptor means reading the whole file."
        ),
        tier=2, help_id="docking.receptor_contents", topic="docking",
        help_anchor="docking",
    ),
    "derive_box": HelpTooltip(
        text=(
            "Sets the search box to the site defined by a ligand already bound "
            "in the receptor -- the most reliable way to place it, because the "
            "crystallographer has already found the site for you.\n\n"
            "Where several copies of the ligand are present, the most buried "
            "one is boxed. That is a choice between equivalent copies, not a "
            "claim that the others are wrong.\n\n"
            "It boxes the site, which is not the same as reproducing the pose: "
            "the ligand that defined the box is stripped before docking."
        ),
        tier=3, help_id="docking.derive_box_from_ligand", topic="docking",
        help_anchor="docking",
    ),
    "ligand": HelpTooltip(
        text=(
            "Which molecule from the project to dock. It needs a 3D conformer; "
            "one is generated from the drawing if none exists."
        ),
        tier=2, help_id="docking.ligand", topic="docking", help_anchor="docking",
    ),
    "box_centre": HelpTooltip(
        text=(
            "One coordinate of the search box centre, in Angstrom, in the "
            "receptor's own frame.\n\n"
            "THE DEFAULT OF ZERO IS NOT A SITE. It is the origin of the "
            "coordinate system, which for a deposited structure is usually "
            "nowhere near the protein -- use \"Derive from ligand\" or set it "
            "from a site you already know.\n\n"
            "Vina searches only inside this box, so a pose outside it is never "
            "considered and its absence says nothing about whether it binds."
        ),
        tier=3, help_id="docking.search_box_centre", topic="docking",
        help_anchor="docking",
    ),
    "box_size": HelpTooltip(
        text=(
            "One edge length of the search box, in Angstrom. Range 1 to 200, "
            "default 20.\n\n"
            "It must be large enough for the ligand to rotate inside, and every "
            "extra Angstrom costs search time and admits more places for a pose "
            "to be found. A box drawn around a whole protein is not a thorough "
            "search, it is a worse one."
        ),
        tier=3, help_id="docking.search_box_size", topic="docking",
        help_anchor="docking",
    ),
    "num_poses": HelpTooltip(
        text=(
            "How many distinct poses to report, best score first. Range 1 to 50, "
            "default 9.\n\n"
            "It asks for more ANSWERS, not a harder search: the poses beyond the "
            "first are alternatives the same search already found."
        ),
        tier=2, help_id="docking.num_poses", topic="docking", help_anchor="docking",
    ),
    "replicates": HelpTooltip(
        text=(
            "How many independent Vina searches to run for this ligand. Range 1 "
            "to 25, default 1.\n\n"
            "Vina's search is stochastic, so a single run is one draw. Running N "
            "of them measures how far the score moves when nothing but the seed "
            "changes, and the panel then reports that range rather than one "
            "number that looks like a measurement.\n\n"
            "It multiplies the wall clock by N. And below 4 runs each, no "
            "ordering between two ligands can be supported however far apart "
            "their scores look: with 3 runs each, two sets of scores separate "
            "completely by chance one time in ten."
        ),
        tier=2, help_id="docking.replicates", topic="docking",
        help_anchor="docking", source_key="mann1947",
    ),
    "affinity_spread": HelpTooltip(
        text=(
            "The lowest and highest Vina score across this result's replicate "
            "runs, in kcal/mol, with the median and the number of runs.\n\n"
            "It is the SAMPLE RANGE of the runs performed -- how reproducible "
            "the search is for this ligand, in this box, at these settings. It "
            "is not an uncertainty on the binding affinity, and it neither "
            "widens nor narrows with how well the score predicts reality.\n\n"
            "It licenses one direction only. Two ligands whose ranges OVERLAP "
            "are indistinguishable by this method. Two whose ranges are "
            "disjoint were separated by the SCORING FUNCTION -- which CASF-2016 "
            "places at a ranking correlation of around 0.6 even for its best "
            "performers -- so a separation is not evidence that the two "
            "molecules bind differently.\n\n"
            "The range GROWS with the number of runs, in expectation, so two "
            "ranges measured over different counts are not comparable."
        ),
        tier=3, help_id="docking.affinity_spread", topic="docking",
        help_anchor="limits-docking", source_key="su2019",
    ),
    "protonation_ph": HelpTooltip(
        text=(
            "The pH BOTH the receptor and the ligand are prepared at. Range 0 "
            "to 14, default 7.4.\n\n"
            "It decides which groups carry a hydrogen, which decides which can "
            "DONATE a hydrogen bond -- so it reaches the score rather than only "
            "the picture. A basic amine prepared as neutral is typed as an "
            "acceptor rather than a donor, which is the opposite of what it "
            "does in the pocket.\n\n"
            "One value because the two are in the same solution. It is a "
            "declared preparation pH, not a claim that a single number fixes "
            "every protonation state: buried residues and histidine tautomers "
            "are beyond what any one pH determines."
        ),
        tier=3, help_id="docking.protonation_ph", topic="docking",
        help_anchor="docking",
    ),
    "strip_waters": HelpTooltip(
        text=(
            "Removes crystallographic waters from the receptor before docking. "
            "On by default.\n\n"
            "Docking treats the receptor as rigid, so a retained water is a "
            "permanent obstacle rather than something a ligand can displace -- "
            "which is why removing them is the usual choice. A water that "
            "genuinely bridges the ligand and the protein is lost with the rest."
        ),
        tier=3, help_id="docking.strip_waters", topic="docking",
        help_anchor="limits-docking",
    ),
    "strip_cofactors": HelpTooltip(
        text=(
            "Removes bound cofactors, metals and other non-water heteroatoms "
            "from the receptor. OFF by default.\n\n"
            "Off because a cofactor is often part of the site rather than "
            "clutter: strip the catalytic zinc from a metalloenzyme and the "
            "pocket it was holding open is no longer the pocket."
        ),
        tier=3, help_id="docking.strip_cofactors", topic="docking",
        help_anchor="limits-docking",
    ),
    "configure_vina": HelpTooltip(
        text=(
            "Opens the external-tools settings at the AutoDock Vina entry, where "
            "the path to the executable is set. Vina is installed by you and is "
            "not bundled; docking cannot run until that path is set."
        ),
        tier=1, help_id="docking.configure_vina", topic="docking",
        help_anchor="external-tools",
    ),
    "run": HelpTooltip(
        text=(
            "Prepares the receptor and the ligand and runs AutoDock Vina inside "
            "the search box above.\n\n"
            "The search is STOCHASTIC. Two runs of the same input give "
            "slightly different poses and scores, and a difference smaller than "
            "that spread is not a result.\n\n"
            "Seed pins one run so it can be repeated; Replicates MEASURES the "
            "spread instead of leaving it to be guessed at."
        ),
        tier=3, help_id="docking.run", topic="docking", help_anchor="limits-docking",
    ),
}


_POSE_COLUMN_TOOLTIPS = {
    "Pose": "Rank within this run, best score first. Not an identity: pose 1 of one "
    "run is unrelated to pose 1 of another.",
    "Binding Affinity (kcal/mol)": (
        "AutoDock Vina's empirical score, in kcal/mol. Always negative; more negative "
        "is predicted-tighter binding.\n\n"
        "It is NOT a measured binding free energy, and scores are generally not "
        "directly comparable across different receptors, targets or docking protocols "
        "-- the search box, receptor preparation and protonation pH all move the scale.\n\n"
        "For scale: Trott & Olson (2010), who wrote the scoring function, report a "
        "standard error of 2.85 kcal/mol against experimental binding free energies "
        "on their own 190-complex test set. Treat differences smaller than that as "
        "not meaningfully distinguishable."
    ),
    "RMSD l.b.": (
        "Root-mean-square deviation in Angstrom RELATIVE TO POSE 1 of this run -- not "
        "to any experimental structure. Pose 1 is therefore always 0.000.\n\n"
        "The lower bound allows symmetry-equivalent atoms to be matched to each other, "
        "so it is always less than or equal to the upper bound.\n\n"
        "A large value means this pose is geometrically different from pose 1. It does "
        "not establish whether either pose is correct."
    ),
    "Rescore": (
        "The same pose scored again by a DIFFERENT function, after the search.\n\n"
        "It is NOT on the affinity column's scale and the two must never be "
        "compared, subtracted or averaged. Vinardo and Vina differ by about 3 "
        "kcal/mol on the same atoms in the same place, because they weight "
        "their terms differently rather than because one binds better.\n\n"
        "Rescoring with Vina itself does not reproduce the affinity either, "
        "except for pose 1: a docking run uses one shared unbound reference "
        "for every pose it reports, while a rescore uses each pose's own.\n\n"
        "The poses are still ordered by the docking affinity. Nothing here "
        "re-ranks them, because whether this function ranks better on this "
        "receptor has not been measured."
    ),
    "RMSD u.b.": (
        "Root-mean-square deviation in Angstrom RELATIVE TO POSE 1 of this run -- not "
        "to any experimental structure. Pose 1 is therefore always 0.000.\n\n"
        "The upper bound matches each atom to itself, ignoring symmetry, so it is "
        "always greater than or equal to the lower bound.\n\n"
        "A large value means this pose is geometrically different from pose 1. It does "
        "not establish whether either pose is correct."
    ),
}

#: What the box resets to when nothing can be derived. Also the value it
#: has always had on a fresh panel -- but it is only defensible as a
#: STARTING point, never as a box to dock with, which is why every path
#: that writes it also says so on the status line.
_DEFAULT_BOX = DockingBox(center=(0.0, 0.0, 0.0), size=(20.0, 20.0, 20.0))

#: "STILL NOT HANDLED" READ AS AN OVERSIGHT AND THE TRUTH IS A DECISION.
#: `docs/ARCHITECTURE.md` records missing-residue repair as assessed and
#: deliberately left out, with numbers: zero of 49 curated receptors have a
#: chain break within 10 A of their site, only 3 of 48 have incomplete side
#: chains there, and the repair is a template prediction landing a median
#: 2.3 A from atoms actually observed in sister chains. So the two said
#: different KINDS of thing about the same fact -- one "unfinished, may
#: arrive", the other "measured, declined" -- and a panel note that implies
#: a pending feature is the more misleading of the two.
_LIMITATION_NOTE = (
    "Note: receptor preparation handles pH-correct protonation and "
    "water/cofactor stripping (below), via Open Babel. Missing-residue repair "
    "is deliberately not attempted — it was assessed and declined, because "
    "predicted atoms would be indistinguishable from observed ones in the "
    "result (see ARCHITECTURE.md). Treat results as a starting point, not "
    "production-grade docking prep."
)


def _rescore_note(function: str) -> str:
    """The sentence under the table when a rescore column is shown.

    **ON SCREEN, NOT ONLY IN THE TOOLTIP** -- the same reason the replicate
    spread's note is a label rather than hover text, and the same failure
    this project has twice recorded (the isotope table's spin/parity marks,
    `Fact.limitations`): a meaning that lives only in a hover is absent from
    every screenshot.

    It sits here rather than in the column header because the header has no
    room. The affinity column takes the table's remainder, so every pixel a
    fifth header claims comes off the number a reader is here for.
    """
    return (
        f"{function.title()} scored these poses again after the search. It is a "
        f"SEPARATE SCALE from the affinity column — the two must not be compared, "
        f"subtracted or averaged, and the poses are still ordered by the affinity. "
        f"Whether {function.title()} ranks better on this receptor has not been "
        f"measured here."
    )


#: The one conclusion a reader must not draw from a replicate range.
#:
#: ON SCREEN, NOT ONLY IN THE TOOLTIP. This project has twice recorded a
#: meaning that lived only in a hover and was therefore absent from every
#: screenshot -- the isotope table's spin/parity marks, and `Fact.limitations`,
#: which reaches a row tooltip and nothing else. A range printed beside two
#: affinities reads as an error bar unless something on the same surface says
#: it is not one.
#:
#: IT NAMES NEITHER "CONFIDENCE" NOR "INTERVAL", deliberately, where the plan
#: for this feature listed both in a denial. Saying "this is not a confidence
#: interval" teaches a reader the exact frame the sentence exists to prevent,
#: and it makes any guard on the rendered string unable to tell a denial from a
#: claim. Saying what the number IS, plus the one direction it licenses, is
#: shorter and leaves the guard a clean word ban.
_SPREAD_LIMIT_NOTE = (
    "That range is how much these runs disagreed with each other -- not an "
    "uncertainty on the affinity. A gap between two ligands means the search "
    "separated them, not that they bind differently."
)


def _representative_seed_phrase(replicates) -> str:
    """" (seed 1990277, protocol seed 4712)", or "" when neither is known.

    BOTH, WHEN BOTH EXIST, because they differ and the difference is the whole
    seed hierarchy this branch introduced: what the user pinned is not what
    Vina ran. Printing only the pinned number would tell a reader the run used
    4712; printing only the derived one would leave them unable to reproduce
    it.
    """
    rows = replicates.replicates
    index = replicates.representative_index
    seed = rows[index].seed if 0 <= index < len(rows) else None
    parts = []
    if seed is not None:
        parts.append(f"seed {seed}")
    if replicates.protocol_seed is not None:
        parts.append(f"protocol seed {replicates.protocol_seed}")
    return f" ({', '.join(parts)})" if parts else ""


def describe_replicate_spread(replicates) -> str:
    """What the panel says under the pose table about how this result was run.

    THREE STATES, NOT TWO, and each renders differently -- `n/a is not 0` with
    a third case:

        replicates is None   the count was never recorded, which is every
                             result saved before replicate runs existed
        n == 1               one run, no spread MEASURED -- which is the
                             default path, and the whole behavioural fix at
                             N = 1: the number stops presenting itself as a
                             measurement
        n >= 2               the measured range, its median, and the count

    A width of 0.0 from five runs that genuinely agree is a MEASUREMENT and
    stays distinguishable from all three, which is why `AffinityRange.width`
    is None at n = 1 rather than 0.0.

    A pure function over the domain type, so the three states are testable
    without building a panel -- and so the wording cannot drift between the
    live render and `sync_with_project`'s.
    """
    if replicates is None:
        return (
            "Replicates were not recorded for this result, which is every "
            "result saved before replicate runs existed."
        )
    spread = replicates.affinity_range()
    if spread is None:
        return "No run of this set produced a score."
    seeds = _representative_seed_phrase(replicates)
    if spread.n < 2:
        return f"1 run{seeds} — no spread measured."
    return (
        f"Score range over {spread.n} runs: {spread.low:.2f} to "
        f"{spread.high:.2f} (median {spread.median:.2f}). Poses are from the "
        f"median run{seeds}. {_SPREAD_LIMIT_NOTE}"
    )


# `box_defining_ligand_codes` used to live here, private. It moved to
# `chem/binding_site.py` because it turned out to have TWO callers and one of
# them was missing it: `VirtualScreeningDialog` sent no `receptor_prep_options`
# at all, so every virtual screen against a catalogued receptor docked into a
# pocket the crystal ligand was still sitting in. Copying it into the dialog
# would have been the drift this project has already paid for four times, so
# there is one implementation and both callers import it -- deferred, like
# every other `binding_site` import in this file.


class DockingPanel(QWidget):
    """Pick a receptor (macromolecule) + ligand (molecule) from the current
    project, define a search box, and run AutoDock Vina via whichever
    `VinaEngine` is available (chem/vina_engine.py) — the panel itself
    doesn't know or care which one.
    """

    #: The displayed search box changed -- derived, reset or typed over.
    #: `MainWindow` redraws the 3D overlay from it. A signal rather than a
    #: direct call because the panel has no reference to the viewer, which
    #: is the same reason docking RESULTS travel through the window.
    box_changed = Signal()

    def __init__(
        self,
        docking_service: DockingService,
        chemistry_engine: ChemistryEngine,
        settings: Settings,
        event_bus: EventBus,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._docking_service = docking_service
        self._chemistry_engine = chemistry_engine
        self._settings = settings
        self._event_bus = event_bus
        self._project: ProjectModel | None = None
        self._pending_ligand_uuid: str | None = None
        self._pending_receptor_uuid: str | None = None
        #: Which docking result the pose table is showing, so an undo
        #: that removes it can be told apart from a redo that restores it.
        self._displayed_result_uuid: str | None = None
        self._displayed_result = None

        self._receptor_combo = QComboBox(self)
        apply_help_tooltip(self._receptor_combo, _CONTROL_HELP["receptor"])
        # Parsing a receptor is not free (Open Babel reads the whole file),
        # so the summary is computed on demand from the button rather than
        # on every combo change.
        self._contents_button = QPushButton("Contents...", self)
        apply_help_tooltip(self._contents_button, _CONTROL_HELP["receptor_contents"])
        self._contents_button.clicked.connect(self._on_contents_clicked)
        # Empty means "no restriction", never "no chains" -- see
        # StructureContentsDialog.keep_chains. Reset whenever the receptor
        # changes, because a chain id names a different thing in a
        # different structure and carrying "keep A" across would silently
        # dock against the wrong subunit.
        self._keep_chains: list[str] = []
        #: Reset with the receptor for the same reason `_keep_chains`
        #: is: an assembly annotation belongs to one deposit, and
        #: carrying "build it" across would apply another structure's
        #: answer to this one.
        self._build_assembly = False
        self._derive_button = QPushButton("Derive from ligand...", self)
        self._derive_button.clicked.connect(self._on_derive_clicked)
        # Enabled by `_place_box_for_receptor` once a receptor with bound
        # ligands is chosen. Disabled is the honest starting state -- there
        # is nothing to derive from yet.
        self._derive_button.setEnabled(False)
        # The CONTRACT is attached once and is the stable meaning; the
        # rendered tooltip below it is state-dependent, because naming the
        # ligands actually present is the useful half. A later
        # `setToolTip` replaces the rendered string and leaves the contract
        # in place, which is what "a tooltip is one RENDERING" buys here.
        apply_help_tooltip(self._derive_button, _CONTROL_HELP["derive_box"])
        self._describe_derivable_ligands(())
        self._ligand_combo = QComboBox(self)
        apply_help_tooltip(self._ligand_combo, _CONTROL_HELP["ligand"])

        #: Where the displayed box came from -- "derived", "manual" or
        #: "none". PROVENANCE ONLY: `displayed_box()` reads the spinboxes,
        #: and nothing may dock from anything else.
        self._box_source = "none"
        #: True while `_write_box` is setting the spinboxes, so its own
        #: `valueChanged` emissions are not mistaken for a user edit.
        self._writing_box = False
        #: Which receptor the displayed box was placed for.
        #:
        #: The box CANNOT be driven by `currentIndexChanged` alone.
        #: `molecule_combo.repopulate` blocks signals deliberately -- a
        #: rebuild must not look like a user changing the selection -- so
        #: the first receptor ever added to a project arrives selected with
        #: no signal at all, and a signal-only implementation leaves its
        #: box at the default. Comparing the uuid catches that, and it is
        #: also what lets a repopulate for an unrelated reason leave a
        #: hand-positioned box alone.
        self._box_receptor_uuid: str | None = None

        self._center_x = self._make_spin(-1000, 1000, 0.0)
        self._center_y = self._make_spin(-1000, 1000, 0.0)
        self._center_z = self._make_spin(-1000, 1000, 0.0)
        self._size_x = self._make_spin(1, 200, 20.0)
        self._size_y = self._make_spin(1, 200, 20.0)
        self._size_z = self._make_spin(1, 200, 20.0)
        for spin in (self._center_x, self._center_y, self._center_z):
            apply_help_tooltip(spin, _CONTROL_HELP["box_centre"])
        for spin in (self._size_x, self._size_y, self._size_z):
            apply_help_tooltip(spin, _CONTROL_HELP["box_size"])
        for spin in (
            self._center_x, self._center_y, self._center_z,
            self._size_x, self._size_y, self._size_z,
        ):
            spin.valueChanged.connect(self._on_box_edited)
        # Connected only now that the spinboxes exist: the handler writes
        # the box, so a combo signal arriving earlier would reach them
        # before they had been built.
        self._receptor_combo.currentIndexChanged.connect(self._on_receptor_changed)

        self._num_poses_spin = QSpinBox(self)
        self._num_poses_spin.setRange(1, 50)
        self._num_poses_spin.setValue(9)
        apply_help_tooltip(self._num_poses_spin, _CONTROL_HELP["num_poses"])

        # THE FOUR SEARCH CONTROLS ARE SHARED WITH THE SCREENING DIALOG.
        # They were built here as four literals until that dialog needed
        # them too; a second copy would have shredded four help_ids into
        # eight, which is the one-concept-one-id rule's own forbidden
        # mutation. `ui/widgets/search_options.py` carries the reasoning.
        self._search_controls = SearchOptionsControls(self)
        self._exhaustiveness_combo = self._search_controls.exhaustiveness
        self._scoring_combo = self._search_controls.scoring_function
        self._rescore_combo = self._search_controls.rescore_with
        self._seed_spin = self._search_controls.seed

        # 1..25, default 1. ONE, because anything above it would multiply
        # every existing user's docking wall clock with no announcement -- and
        # because at 1 the panel's whole render is byte-identical to what it
        # was before replicates existed, so a surprise here is this feature's
        # fault rather than a re-baselining.
        self._replicates_spin = QSpinBox(self)
        self._replicates_spin.setRange(1, 25)
        self._replicates_spin.setValue(DEFAULT_REPLICATES)
        apply_help_tooltip(self._replicates_spin, _CONTROL_HELP["replicates"])

        self._ph_spin = QDoubleSpinBox(self)
        self._ph_spin.setRange(0.0, 14.0)
        self._ph_spin.setSingleStep(0.1)
        self._ph_spin.setValue(7.4)
        apply_help_tooltip(self._ph_spin, _CONTROL_HELP["protonation_ph"])
        self._strip_waters_check = QCheckBox("Strip waters", self)
        self._strip_waters_check.setChecked(True)
        apply_help_tooltip(self._strip_waters_check, _CONTROL_HELP["strip_waters"])
        self._strip_cofactors_check = QCheckBox("Strip cofactors", self)
        self._strip_cofactors_check.setChecked(False)
        apply_help_tooltip(self._strip_cofactors_check, _CONTROL_HELP["strip_cofactors"])

        self._configure_button = QPushButton("Configure Vina...", self)
        apply_help_tooltip(self._configure_button, _CONTROL_HELP["configure_vina"])
        self._configure_button.clicked.connect(self._on_configure_clicked)

        self._dock_button = QPushButton("Dock", self)
        apply_help_tooltip(self._dock_button, _CONTROL_HELP["run"])
        self._dock_button.clicked.connect(self._on_dock_clicked)

        self._status_label = QLabel("", self)
        #: Where the search box is, and whether that is where the receptor
        #: says its site is. SEPARATE from `_status_label` on purpose: that
        #: one carries job state and is rewritten on every
        #: `DockingJobStateChanged`, so a box warning put there is wiped by
        #: the "Queued..." that follows it microseconds later. Caught by
        #: `test_a_far_box_warns_without_blocking_the_run`, which asserted
        #: the message survived the click and found that it did not.
        self._box_status_label = QLabel("", self)
        self._box_status_label.setWordWrap(True)
        #: How this result was run, under the pose table. ITS OWN LABEL and
        #: not `_status_label`, for the reason `_box_status_label` above is
        #: separate: that one carries job state and is rewritten on every
        #: `DockingJobStateChanged`, so a spread put there is wiped by the
        #: "completed" that arrives after the result.
        self._spread_label = QLabel("", self)
        self._spread_label.setWordWrap(True)
        apply_help_tooltip(self._spread_label, _CONTROL_HELP["affinity_spread"])
        self._spread_label.setVisible(False)

        # Hidden until a rescore column is shown, exactly as the spread
        # label is hidden until replicates are measured.
        self._rescore_label = QLabel("", self)
        self._rescore_label.setWordWrap(True)
        # THE SHARED CONTRACT, not a copy. This label and the combo are
        # two renderings of ONE concept -- what a second score means and
        # why it must not be compared with the first -- so they carry one
        # help_id and `instance_path` tells the renderings apart.
        apply_help_tooltip(self._rescore_label, SEARCH_CONTROL_HELP["rescore_with"])
        self._rescore_label.setVisible(False)

        self._limitation_label = QLabel(_LIMITATION_NOTE, self)
        self._limitation_label.setWordWrap(True)

        self._table = QTableWidget(0, len(_POSE_COLUMNS), self)
        self._table.setHorizontalHeaderLabels(_POSE_COLUMNS)
        # On the header ITEMS, which are QTableWidgetItems rather than
        # widgets -- so a tooltip audit that walks QWidgets alone cannot
        # see these, and would report the table fully documented. An item
        # is not a QObject either, so `apply_help_tooltip` stores its
        # contract as item data rather than as a Qt property.
        for column, name in enumerate(_POSE_COLUMNS):
            item = self._table.horizontalHeaderItem(column)
            if item is not None:
                from dataclasses import replace

                apply_help_tooltip(
                    item, replace(_POSE_COLUMN_HELP[name], text=_POSE_COLUMN_TOOLTIPS[name])
                )
        # THE AFFINITY COLUMN TAKES THE SLACK; THE OTHER THREE SIZE TO THEIR
        # OWN TEXT. Stretch on all four divided the table's 440 px into four
        # equal 110 px sections, and "Binding Affinity (kcal/mol)" needs 141 --
        # so it rendered clipped at BOTH ends as "ling Affinity (kcal/r", which
        # is the identical defect `virtual_screening_dialog.py` records fixing
        # in its own table ("est score (kcal/mo").
        #
        # `ResizeToContents` sizes a section to the WIDER of its header and its
        # cells, so those three cannot clip at any font or DPI -- the property
        # a hand-tuned pixel width would not have. Measured at 440 px:
        #
        #     Stretch on all four   [110, 110, 110, 110]   affinity CLIPPED
        #     this                  [ 34, 278,  62,  66]   nothing clipped
        #
        # The affinity column is the one that takes the remainder because it is
        # the quantity a reader is here for. Letting the LAST column take it
        # instead -- `setStretchLastSection` -- gives RMSD u.b. 190 px for a
        # five-character number while leaving affinity at 154, five pixels off
        # clipping again.
        header = self._table.horizontalHeader()
        for column, name in enumerate(_POSE_COLUMNS):
            header.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.Stretch
                if name == _AFFINITY_COLUMN
                else QHeaderView.ResizeMode.ResizeToContents,
            )
        # HIDDEN FROM CONSTRUCTION, because "no rescore was requested" is the
        # starting state and an empty fifth column is not a neutral default:
        # `ResizeToContents` gives it its header's width, which took the
        # affinity column 10 px past clipping and reddened
        # `test_no_pose_table_header_is_clipped` the moment it was added.
        # `_apply_rescore_column` is the only thing that shows it.
        self._table.setColumnHidden(_POSE_COLUMNS.index(_RESCORE_COLUMN), True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        receptor_row = QHBoxLayout()
        receptor_row.addWidget(self._receptor_combo, 1)
        receptor_row.addWidget(self._contents_button)
        receptor_row.addWidget(self._derive_button)

        selection_form = QFormLayout()
        selection_form.addRow("Receptor:", receptor_row)
        selection_form.addRow("Ligand:", self._ligand_combo)

        box_group = QGroupBox("Search box (Å)", self)
        box_form = QFormLayout(box_group)
        center_row = QHBoxLayout()
        center_row.addWidget(self._center_x)
        center_row.addWidget(self._center_y)
        center_row.addWidget(self._center_z)
        size_row = QHBoxLayout()
        size_row.addWidget(self._size_x)
        size_row.addWidget(self._size_y)
        size_row.addWidget(self._size_z)
        # "Center:" rather than "Center (x, y, z):", which cost 39 px of the
        # 46 the panel had to save. The ordering is not lost: the two controls
        # carry `docking.box_centre` and `docking.box_size`, and the status
        # line under the group prints "centre (2.0, 15.9, -58.8)" in full.
        box_form.addRow("Center:", center_row)
        box_form.addRow("Size:", size_row)

        # "Preparation", not "Receptor preparation": the pH governs the LIGAND
        # too now, and a heading naming only the receptor would say the panel
        # does something narrower than it does.
        prep_group = QGroupBox("Preparation", self)
        prep_form = QFormLayout(prep_group)
        prep_form.addRow("pH (ligand + receptor):", self._ph_spin)
        # DELIBERATELY a QHBoxLayout, having tried the alternative. `flow_row`
        # is this project's cure for a horizontal row whose minimum width is
        # the SUM of its children, and it was substituted here on that rule
        # alone -- then measured, at the dock's 420 px default:
        #
        #     QHBoxLayout   row 17 px   group hint  85   group min width 828
        #     flow_row      row 38 px   group hint 106   group min width 654
        #
        # The two checkboxes need 372 px, so the flow row WRAPS at this width
        # and costs 21 px of visible dead space under them. The width it buys
        # back never mattered: `test_right_dock_width.py` passes either way,
        # because two checkboxes are not the many-children case that rule is
        # about. Reverted on the screenshot, which is the only thing that
        # showed the cost.
        strip_row = QHBoxLayout()
        strip_row.addWidget(self._strip_waters_check)
        strip_row.addWidget(self._strip_cofactors_check)
        prep_form.addRow("", strip_row)

        search_group = QGroupBox("Search", self)
        search_form = QFormLayout(search_group)
        search_form.addRow("Exhaustiveness:", self._exhaustiveness_combo)
        search_form.addRow("Scoring function:", self._scoring_combo)
        search_form.addRow("Rescore with:", self._rescore_combo)
        # DIRECTLY ABOVE SEED, because it changes what Seed means: a pinned
        # seed is the root of a DERIVED set of per-run seeds rather than the
        # number Vina receives. A reader who meets Seed first forms the older
        # meaning and has no reason to revisit it.
        search_form.addRow("Replicates:", self._replicates_spin)
        search_form.addRow("Seed:", self._seed_spin)

        run_row = QHBoxLayout()
        run_row.addWidget(QLabel("Poses:"))
        run_row.addWidget(self._num_poses_spin)
        run_row.addWidget(self._configure_button)
        run_row.addWidget(self._dock_button)

        layout = QVBoxLayout(self)
        layout.addLayout(selection_form)
        layout.addWidget(box_group)
        layout.addWidget(self._box_status_label)
        layout.addWidget(prep_group)
        layout.addWidget(search_group)
        layout.addLayout(run_row)
        layout.addWidget(self._status_label)
        layout.addWidget(self._spread_label)
        layout.addWidget(self._rescore_label)
        layout.addWidget(self._table)
        layout.addWidget(self._limitation_label)

        event_bus.subscribe(DockingJobStateChanged, self._on_job_state_changed)
        event_bus.subscribe(DockingResultReady, self._on_result_ready)
        event_bus.subscribe(MoleculeSelected, self._on_molecule_selected)

    def _make_spin(self, minimum: float, maximum: float, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox(self)
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        # Capped rather than left at Qt's own hint, which adds slack on top of
        # the widest value the RANGE permits. See `coordinate_spin_width`.
        spin.setMaximumWidth(coordinate_spin_width(spin))
        return spin

    def set_project(self, project: ProjectModel | None) -> None:
        self._project = project
        self._refresh_combos()

    def _refresh_combos(self) -> None:
        macromolecules = self._project.macromolecules if self._project is not None else []
        molecules = self._project.molecules if self._project is not None else []
        repopulate(self._receptor_combo, [(m.display_name, m.uuid) for m in macromolecules])
        repopulate(self._ligand_combo, [(m.display_name, m.uuid) for m in molecules])
        # `repopulate` is deliberately silent, so the box has to be asked
        # for here. It no-ops unless the selected receptor actually moved.
        self._sync_box_with_receptor()

    def _on_molecule_selected(self, event: MoleculeSelected) -> None:
        """Follow the project tree for the LIGAND only.

        The receptor combo lists macromolecules and is deliberately left
        alone: a `MoleculeSelected` uuid is never in it, and blanking a
        chosen receptor because the user clicked a small molecule would
        throw away the search box that goes with it.
        """
        select(self._ligand_combo, event.molecule_uuid)

    def _on_contents_clicked(self) -> None:
        """Summarise the selected receptor and show its chains.

        Parsed here rather than cached on the model: the summary is a view
        of the structure text, and caching it would give the model a
        second copy of the truth that could go stale the moment the text
        was replaced.
        """
        from openchem.chem.structure_assembly import parse_assembly
        from openchem.chem.structure_summary import summarize_structure
        from openchem.ui.dialogs.structure_contents_dialog import StructureContentsDialog

        if self._project is None:
            return
        receptor_uuid = self._receptor_combo.currentData()
        receptor = (
            self._project.find_macromolecule(receptor_uuid) if receptor_uuid else None
        )
        if receptor is None:
            self._status_label.setText("Select a receptor first.")
            return
        try:
            summary = summarize_structure(receptor.structure_text, receptor.source_format)
        except Exception as exc:  # noqa: BLE001 - surfaced, never a crash
            logger.exception("Failed to summarise receptor")
            self._status_label.setText(f"Could not read that receptor: {exc}")
            return
        dialog = StructureContentsDialog(
            receptor.display_name,
            summary,
            self,
            keep_chains=self._keep_chains or None,
            # Parsed from the SAME text the chains came from -- mmCIF
            # assembly records name label_asym_ids and PDB REMARK 350
            # names author ids, so crossing the two formats would annotate
            # chains that do not exist under those names.
            assembly=parse_assembly(receptor.structure_text, receptor.source_format),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._keep_chains = dialog.keep_chains()
        self._build_assembly = dialog.build_assembly()
        self._update_chain_status()

    def _on_receptor_changed(self, _index: int) -> None:
        self._keep_chains = []
        self._build_assembly = False
        self._update_chain_status()
        self._sync_box_with_receptor()

    def _sync_box_with_receptor(self) -> None:
        """Re-place the box iff the receptor it belongs to has changed.

        Reached from the combo's signal AND from `_refresh_combos`,
        because neither alone is sufficient: `repopulate` blocks signals,
        so the signal misses the first receptor; and a repopulate happens
        on every project mutation, so acting on it unconditionally would
        overwrite a hand-positioned box every time an unrelated molecule
        was renamed.
        """
        current = self._receptor_combo.currentData()
        if current == self._box_receptor_uuid:
            return
        self._box_receptor_uuid = current
        self._place_box_for_receptor()

    # --- the search box ------------------------------------------------------

    def selected_receptor_uuid(self) -> str | None:
        """Which receptor the box belongs to, or None.

        Public because `MainWindow._sync_docking_box_overlay` has to know
        whether there is anything to draw a box ON, and reaching into the
        combo from outside would put a second reader on that state.
        """
        return self._receptor_combo.currentData()

    def _selected_receptor(self):
        if self._project is None:
            return None
        receptor_uuid = self._receptor_combo.currentData()
        return self._project.find_macromolecule(receptor_uuid) if receptor_uuid else None

    def displayed_search_options(self) -> dict[str, object]:
        """The search settings as the four controls currently read them.

        Delegates to the shared control object, which is the ONE thing
        entitled to read those widgets. Kept as a method on the panel
        because it is this panel's public surface -- the drive step and
        several tests call it -- and because a caller should not have to
        know which widgets the panel happens to own.
        """
        return self._search_controls.options()

    def displayed_replicates(self) -> int:
        """How many searches the next run performs.

        A SIBLING OF `num_poses` AND DELIBERATELY NOT A `search_options` KEY.
        `search_options` is the dict handed straight to the provider, and a
        provider never sees more than one run at a time -- a replicate count in
        it would name something it cannot act on. It is also asserted as an
        exact dict by `tests/test_ligand_extent_warning.py`, which this
        placement leaves valid unedited.

        Its own accessor rather than a bare `.value()` at the call site, for
        the reason `displayed_search_options` is: one place reads the control,
        so the panel cannot start displaying one count and docking another.
        """
        return self._replicates_spin.value()

    def displayed_box(self) -> DockingBox:
        """The box as the six spinboxes currently read it.

        The ONE accessor, used by `_on_dock_clicked` and by the tests that
        check what was sent. `_box_source` records where these numbers came
        from and never substitutes for them: reading the box from anywhere
        else is how the panel would start displaying one thing and docking
        another.
        """
        return DockingBox(
            center=(self._center_x.value(), self._center_y.value(), self._center_z.value()),
            size=(self._size_x.value(), self._size_y.value(), self._size_z.value()),
        )

    def _write_box(self, box: DockingBox, source: str) -> None:
        """Set the six spinboxes without the write counting as a user edit.

        `setValue` emits `valueChanged` exactly as a keystroke does, so
        without this guard every derived box would be marked `manual` the
        instant it was written -- and the panel would then refuse to
        re-derive it. Scoped around the writes rather than inferred from
        whether the values changed, because a value that happens to match
        is still a programmatic write.
        """
        self._writing_box = True
        try:
            for spin, value in zip(
                (self._center_x, self._center_y, self._center_z,
                 self._size_x, self._size_y, self._size_z),
                (*box.center, *box.size),
                strict=True,
            ):
                spin.setValue(value)
        finally:
            self._writing_box = False
        self._box_source = source
        self.box_changed.emit()

    def _on_box_edited(self, _value: float) -> None:
        if self._writing_box:
            return
        self._box_source = "manual"
        self._box_status_label.setText("Search box: manually positioned.")
        self.box_changed.emit()

    def _place_box_for_receptor(self) -> None:
        """Box the receptor's own annotated site, or reset to defaults.

        **A RECEPTOR CHANGE ALWAYS REWRITES THE BOX, and resetting is the
        load-bearing half.** Leaving the previous receptor's coordinates in
        place would present one structure's site as though it belonged to
        another -- the same silently-plausible-wrong-box failure this
        method exists to fix, just moved one step along. `_keep_chains` and
        `_build_assembly` are reset directly above for exactly this reason;
        the box simply never was.

        A hand-tuned box survives everything else: this is reached from the
        receptor combo and from the Derive button, and from nothing that
        merely refreshes the panel.
        """
        receptor = self._selected_receptor()
        if receptor is None:
            self._write_box(_DEFAULT_BOX, "none")
            self._update_derive_button(())
            return

        codes = self._ligand_codes_for(receptor)
        self._update_derive_button(codes)
        preferred = str((getattr(receptor, "metadata", None) or {}).get("ligand_code", "") or "")
        if not preferred:
            self._write_box(_DEFAULT_BOX, "none")
            self._box_status_label.setText(
                "No annotated binding site for this receptor, so the search box was reset "
                "to defaults. Use Derive from ligand... to box a bound ligand."
                if codes
                else "No annotated binding site for this receptor, and no bound ligand to "
                "derive one from. Position the search box manually."
            )
            return
        self._derive_box_from(receptor, preferred)

    def _derive_box_from(self, receptor, ligand_code: str) -> None:
        """Place the box on `ligand_code`, or reset and say why.

        Idempotent: the derivation is a pure function of the structure text
        and the code, so pressing Derive twice writes the same six values
        and reports the same thing.
        """
        from openchem.chem.binding_site import BindingSiteError, box_from_ligand

        try:
            site = box_from_ligand(receptor.structure_text, receptor.source_format, ligand_code)
        except (BindingSiteError, Exception) as exc:  # noqa: BLE001 - reported, never crashes
            logger.exception("Could not derive a search box for %s", receptor.display_name)
            self._write_box(_DEFAULT_BOX, "none")
            # Distinguished from "there is no site" deliberately: the
            # metadata said this receptor HAS one, so silence would read as
            # "nothing to box here" when the truth is that something is
            # wrong and the user can act on it.
            self._box_status_label.setText(
                f"This receptor should have a {ligand_code} site, but it could not be "
                f"located: {exc} The search box was reset to defaults."
            )
            return
        self._write_box(site.box, "derived")
        self._box_status_label.setText(f"Binding site: {site.describe()}")

    def _ligand_codes_for(self, receptor) -> tuple[str, ...]:
        from openchem.chem.binding_site import ligand_codes_in

        try:
            return tuple(ligand_codes_in(receptor.structure_text, receptor.source_format))
        except Exception:  # noqa: BLE001 - a listing failure must not block docking
            logger.exception("Could not list ligand codes for %s", receptor.display_name)
            return ()

    def _update_derive_button(self, codes: tuple[str, ...]) -> None:
        """Say whether a box can be derived BEFORE the button is pressed.

        A failed automatic derivation must not make the manual route look
        permanently unavailable -- an imported structure, or a deposit
        revision whose catalogue code has moved, still has ligands in it
        that can define a site.
        """
        self._derive_button.setEnabled(bool(codes))
        self._describe_derivable_ligands(codes)

    def _describe_derivable_ligands(self, codes) -> None:
        """Render the contract PLUS what this receptor actually offers.

        The stable half is the contract attached in `__init__`; the live
        half names the ligand codes, which is the part that answers "will
        this button do anything for me". Composed rather than substituted,
        so pressing the button is explained even while the live half says
        there is nothing to derive from.
        """
        if codes:
            live = (
                "Ligands in this receptor: "
                + ", ".join(codes[:6])
                + ("..." if len(codes) > 6 else "")
            )
        else:
            live = "No bound ligand in this receptor to derive a search box from."
        self._derive_button.setToolTip(
            f"{_CONTROL_HELP['derive_box'].text}\n\n{live}"
        )

    def _on_derive_clicked(self) -> None:
        receptor = self._selected_receptor()
        if receptor is None:
            self._status_label.setText("Select a receptor first.")
            return
        codes = self._ligand_codes_for(receptor)
        if not codes:
            return
        preferred = str((getattr(receptor, "metadata", None) or {}).get("ligand_code", "") or "")
        if preferred and preferred.upper() in codes:
            self._derive_box_from(receptor, preferred)
            return
        code, accepted = QInputDialog.getItem(
            self, "Derive search box", "Box the site defined by:", list(codes), 0, False
        )
        if accepted and code:
            self._derive_box_from(receptor, code)

    def _update_chain_status(self) -> None:
        """Say so on the panel when the receptor is being cut down.

        A restriction chosen in a dialog that is then closed is invisible,
        and this one changes what Vina sees -- the user should not have to
        reopen the dialog to find out whether it is in effect.
        """
        if self._keep_chains:
            self._status_label.setText(
                f"Docking against chain(s) {', '.join(self._keep_chains)} only."
            )
        elif self._status_label.text().startswith("Docking against chain"):
            self._status_label.setText("")

    def _on_configure_clicked(self) -> None:
        dialog = ExternalToolsDialog(self._settings, self, focus="vina")
        dialog.exec()

    def _on_dock_clicked(self) -> None:
        if self._project is None:
            return
        receptor_uuid = self._receptor_combo.currentData()
        ligand_uuid = self._ligand_combo.currentData()
        if receptor_uuid is None or ligand_uuid is None:
            self._status_label.setText("Select both a receptor and a ligand first.")
            return
        receptor = self._project.find_macromolecule(receptor_uuid)
        ligand = self._project.find_molecule(ligand_uuid)
        if receptor is None or ligand is None:
            return
        if not ligand.conformers and not ligand.molblock:
            self._status_label.setText("Selected ligand has no structure yet.")
            return

        # The displayed box, always. `_box_source` says where it came from
        # and never decides what is sent -- a user who typed six numbers
        # over a derived box means the numbers.
        box = self.displayed_box()
        self._report_box_placement(receptor, box)
        # Prefer a real 3D conformer over the molecule's own molblock, which
        # for anything drawn in the 2D editor has all-zero z-coordinates --
        # docking a flat structure against a 3D receptor is meaningless, not
        # just lower quality. Mirrors QuantumChemistryPanel._on_run_clicked's
        # identical preference.
        best = canonical_conformer(ligand)
        ligand_molblock = best.molblock if best is not None else ligand.molblock
        ligand_mol = self._chemistry_engine.mol_from_molblock(ligand_molblock)
        # After the mol exists, because the warning is about the DOCKED
        # ligand's own geometry -- the box report above knows only the
        # receptor.
        self._report_ligand_extent(ligand_mol, box)

        from openchem.chem.binding_site import box_defining_ligand_codes

        self._pending_ligand_uuid = ligand_uuid
        self._pending_receptor_uuid = receptor_uuid
        self._dock_button.setEnabled(False)
        self._table.setRowCount(0)
        self._status_label.setText("Queued...")

        self._docking_service.request_docking(
            ligand_molecule_uuid=ligand_uuid,
            ligand_mol=ligand_mol,
            receptor_macromolecule_uuid=receptor_uuid,
            receptor_structure_text=receptor.structure_text,
            receptor_source_format=receptor.source_format,
            box=box,
            num_poses=self._num_poses_spin.value(),
            receptor_prep_options={
                "ph": self._ph_spin.value(),
                "strip_waters": self._strip_waters_check.isChecked(),
                "strip_cofactors": self._strip_cofactors_check.isChecked(),
                # Travels in the SAME dict the service hands to both the
                # receptor preparation and the interaction analysis, so
                # they cannot be given different receptors.
                "keep_chains": list(self._keep_chains),
                # Same dict, same reason: the service builds the
                # assembly ONCE from this and hands the identical text
                # to both the docking and the interaction analysis.
                "build_assembly": self._build_assembly,
                "strip_ligand_codes": box_defining_ligand_codes(receptor),
            },
            search_options=self.displayed_search_options(),
            replicates=self.displayed_replicates(),
        )

    def _report_box_placement(self, receptor, box: DockingBox) -> None:
        """Say where the box sits before the run, and never block it.

        Warn-never-block is deliberate. `far_from_reference_site` is
        evidence that the run will not sample the annotated site, not a
        verdict that the user is wrong: blind docking and allosteric sites
        are real uses and a distant box is the intended experiment for
        both. The zero-atom case IS refused, but further down, by
        `docking_providers._require_atoms_in_box` against the prepared
        receptor -- see `binding_site.BoxPlacement.atom_count` for why the
        two counts differ and why both exist.
        """
        from openchem.chem.binding_site import describe_box_placement

        code = str((getattr(receptor, "metadata", None) or {}).get("ligand_code", "") or "")
        try:
            placement = describe_box_placement(
                receptor.structure_text, receptor.source_format, box, code or None
            )
        except Exception:  # noqa: BLE001 - a diagnostic must never stop a run
            logger.exception("Could not judge box placement for %s", receptor.display_name)
            return
        self._box_status_label.setText(placement.describe())

    def _report_ligand_extent(self, ligand_mol, box: DockingBox) -> None:
        """Append a warning when the LIGAND is longer than the box's shortest
        side, on the same warn-never-block terms as the placement above.

        The box is derived from whatever ligand the crystallographer put in the
        receptor, and a docked ligand is routinely larger. Vina confines the
        ligand to the box, so whole orientations are then excluded from the
        search -- silently, because the run completes and returns poses.

        Reported, never resized. And worded as EXTENT rather than fit: a ligand
        longer than the shortest side can still dock, it just cannot lie along
        that axis.
        """
        from openchem.chem.binding_site import ligand_extent_exceeds_box, max_heavy_atom_extent

        try:
            extent = max_heavy_atom_extent(ligand_mol)
            if not ligand_extent_exceeds_box(extent, box):
                return
        except Exception:  # noqa: BLE001 - a diagnostic must never stop a run
            logger.exception("Could not measure the ligand's extent")
            return
        existing = self._box_status_label.text()
        warning = (
            f"Ligand extent {extent:.1f} A exceeds the shortest box dimension "
            f"({min(box.size):.1f} A), so some orientations cannot be searched. "
            "Widen the box if the pose looks constrained."
        )
        self._box_status_label.setText(f"{existing} {warning}" if existing else warning)

    def _is_pending(self, ligand_molecule_uuid: str, receptor_macromolecule_uuid: str) -> bool:
        return (
            ligand_molecule_uuid == self._pending_ligand_uuid
            and receptor_macromolecule_uuid == self._pending_receptor_uuid
        )

    def _on_job_state_changed(self, event: DockingJobStateChanged) -> None:
        if not self._is_pending(event.ligand_molecule_uuid, event.receptor_macromolecule_uuid):
            return
        self._status_label.setText(f"{event.state.value}{': ' + event.message if event.message else ''}")
        if event.state.value in ("completed", "failed"):
            self._dock_button.setEnabled(True)

    def sync_with_project(self, project: ProjectModel | None) -> None:
        """Make the pose table agree with the project's docking results.

        The table was filled from the `DockingResultReady` event and never
        read back from the project, so it only ever reflected what had just
        finished. Undoing a dock removed the result and left the poses on
        screen -- binding affinities, to two decimal places, for a run the
        project no longer contains. Measured: two rows still listed after
        the undo that emptied `project.docking_results`.

        Symmetric on purpose. Clearing on undo without restoring on redo
        would trade one wrong state for another, so this resolves the table
        from the project every time: the newest result for the currently
        selected receptor/ligand pair, or nothing.
        """
        self._table.setRowCount(0)
        self._displayed_result_uuid = None
        self._displayed_result = None
        # The rescore column and its note go with the poses, for the same
        # reason the spread label does: a column headed "Vinardo" over an
        # empty table states that a rescore was performed for a run the
        # project no longer contains.
        self._apply_rescore_column([])
        # Cleared HERE and not only in `_show_result`, so undoing a dock takes
        # the spread label with the poses. Leaving it would state a measured
        # range for a run the project no longer contains -- the same defect
        # this method exists to fix for the table.
        self._set_spread_text("")
        result = self._latest_result_for_selection(project)
        if result is not None:
            self._show_result(result)

    def _latest_result_for_selection(self, project: ProjectModel | None):
        if project is None:
            return None
        receptor_uuid = self._receptor_combo.currentData()
        ligand_uuid = self._ligand_combo.currentData()
        matching = [
            result
            for result in project.docking_results
            if result.receptor_macromolecule_uuid == receptor_uuid
            and result.ligand_molecule_uuid == ligand_uuid
        ]
        # Newest wins: re-docking the same pair should show the run just
        # made, not the first one ever made.
        return max(matching, key=lambda r: r.timestamp) if matching else None

    def _set_spread_text(self, text: str) -> None:
        """Show the label only when it has something to say.

        An empty word-wrapped QLabel still claims a line of font height, and
        this panel is height-constrained enough that its 3D sibling was once
        63 px tall. Hidden rather than blank, so the default path costs the
        table nothing.
        """
        self._spread_label.setText(text)
        self._spread_label.setVisible(bool(text))

    def _show_result(self, result) -> None:
        self._displayed_result_uuid = result.uuid
        # Kept so a diagnostic can read the STORED PoseScore rather than the
        # table's rendered strings: `inapplicable`, the protocol and the two
        # hashes never reach a cell, and they are what tell the four rescore
        # states apart. The project owns this object either way.
        self._displayed_result = result
        self._set_spread_text(describe_replicate_spread(result.replicates))
        self._table.setRowCount(len(result.poses))
        scores = [pose_score_of(pose) for pose in result.poses]
        self._apply_rescore_column(scores)
        for row, pose in enumerate(result.poses):
            values = (
                str(row + 1),
                f"{pose.binding_affinity_kcal_mol:.2f}",
                f"{pose.rmsd_lb:.3f}",
                f"{pose.rmsd_ub:.3f}",
            )
            for col, value in enumerate(values):
                self._table.setItem(row, col, QTableWidgetItem(value))
            self._set_rescore_cell(row, scores[row])

    def _apply_rescore_column(self, scores: list) -> None:
        """Show or hide the rescore column, and name it after the function.

        **THE HEADER CARRIES THE WARNING, NOT THE TOOLTIP.** A reader who
        sees `-8.78` beside `-5.47` will conclude the second says the
        ligand binds worse, and they are simply not on one scale -- 3.3
        kcal/mol apart for the same atoms in the same place. This project
        has twice recorded a meaning that lived only in hover text being
        absent from every screenshot (the isotope spin marks,
        `Fact.limitations`), so "(separate scale)" is printed.

        Hidden when NOTHING was requested, and shown whenever anything was
        -- including when every pose failed. "Not requested" and "requested
        and broken" are different answers and a missing column collapses
        them, which is this codebase's own *n/a is not 0* rule.
        """
        present = [score for score in scores if score is not None]
        column = _POSE_COLUMNS.index(_RESCORE_COLUMN)
        self._table.setColumnHidden(column, not present)
        self._rescore_label.setVisible(bool(present))

        # **THE AFFINITY COLUMN STOPS TAKING THE REMAINDER ONCE THERE IS A
        # FIFTH.** Stretch is right for four columns -- it hands affinity the
        # slack so it cannot clip -- and becomes the opposite once a fifth
        # column claims width: measured, affinity fell to 98 px against the
        # 328 its own header needs, then to 170 with a shorter fifth header.
        # No header text is short enough to fix that, because the squeeze is
        # the stretch column absorbing every other column's growth.
        #
        # `ResizeToContents` sizes a section to the WIDER of its header and
        # its cells, so with it on all five NOTHING can clip at any font or
        # DPI -- the same property `test_three_pose_columns_can_never_clip_
        # whatever_the_font` already pins for the other three. The table
        # scrolls horizontally instead when it must, which is a visible and
        # recoverable state where a clipped header is neither.
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(
            _POSE_COLUMNS.index(_AFFINITY_COLUMN),
            QHeaderView.ResizeMode.ResizeToContents
            if present
            else QHeaderView.ResizeMode.Stretch,
        )
        if not present:
            return
        function = present[0].function
        item = self._table.horizontalHeaderItem(column)
        if item is not None:
            # setText only. The help contract lives in the item's DATA and
            # is left untouched, so the column stays documented -- the
            # failure `docking.derive_box_from_ligand` records, where a
            # recomputed live string replaced a contract and the coverage
            # guard went on reporting the control documented.
            #
            # COMPACT, and the scale warning goes in the label below rather
            # than in here. "Vinardo (separate scale)" is ~150 px, and the
            # affinity column takes the table's remainder -- so a long fifth
            # header squeezed it to 98 px against the 328 its own text needs
            # and reddened `test_no_pose_table_header_is_clipped`. The note
            # under the table has room for a whole sentence, which is more
            # than a header could carry anyway.
            item.setText(function.title())
        self._rescore_label.setText(_rescore_note(function))

    def _set_rescore_cell(self, row: int, score) -> None:
        if score is None:
            return
        column = _POSE_COLUMNS.index(_RESCORE_COLUMN)
        if score.succeeded:
            item = QTableWidgetItem(f"{score.value:.2f}")
        else:
            cell, hover = describe_failure(score.error, score.error_summary)
            item = QTableWidgetItem(cell)
            item.setToolTip(hover)
        self._table.setItem(row, column, item)

    def _on_result_ready(self, event: DockingResultReady) -> None:
        result = event.result
        if not self._is_pending(result.ligand_molecule_uuid, result.receptor_macromolecule_uuid):
            return
        self._show_result(result)
