from __future__ import annotations

import dataclasses
import os
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from openchem.chem.calculation_input import (
    canonical_conformer,
    resolve_calculation_input,
    resolve_ensemble,
)
from openchem.domain.calculator import ENSEMBLE, GEOMETRY
from openchem.app.settings import Settings
from openchem.chem.engine import ChemistryEngine
from openchem.chem.nmr_correlation import compute_cosy_pairs, compute_hmbc_pairs, compute_hsqc_pairs
from openchem.chem.orca_engine import (
    CALC_TYPE_LABELS,
    METHOD_BASIS_PRESETS,
    NMR_METHOD_BASIS,
    SOLVENTS,
    default_cores,
    find_mpi_bin,
)
from openchem.domain.compare import ComparedResult, CompareRefusal, compare
from openchem.domain.project import ProjectModel
from openchem.domain.scientific_result import (
    CrossPeak,
    PerAtomDataset,
    SpectrumResult,
    VibrationalSpectrumResult,
)
from openchem.events.base import EventBus
from openchem.events.events import (
    MoleculeSelected,
    NmrReferenceCalibrated,
    NmrScalingCalibrated,
    QmSurfaceComputed,
    QuantumChemistryJobStateChanged,
    QuantumChemistryResultReady,
    SpectrumComputed,
)
from openchem.services.quantum_chemistry_service import QuantumChemistryService
from openchem.ui.dialogs.compare_results_dialog import CompareResultsDialog
from openchem.ui.dialogs.settings_dialog import EXTERNAL_TOOLS, SettingsDialog
from openchem.ui.molecule_combo import repopulate, select
from openchem.ui.widgets.empty_state import empty_state, empty_state_text, is_empty_state
from openchem.ui.widgets.flow_layout import flow_row
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip
from openchem.ui.widgets.esp_compare_widget import EspCompareWidget
from openchem.ui.widgets.ir_view_widget import IrViewWidget
from openchem.ui.widgets.pop_out_host import PopOutHost
from openchem.ui.widgets.nmr_correlation_plot_widget import NmrCorrelationPlotWidget, Peak
from openchem.ui.widgets.nmr_view_widget import NmrViewWidget
from openchem.ui.widgets.sortable_item import SortableItem
from openchem.ui.widgets.scroll_safe import make_scroll_safe

_NMR_SPECTRUM_COLUMNS = ("Atom", "Element", "Value (ppm)")
_CORRELATION_COLUMNS = ("Atom A", "Atom B", "Shift A", "Shift B", "J (Hz)")
# "Source" is a first-class column, not something to dig out of provenance:
# a spectrum drawn from two methods that does not say which value came from
# where is harder to trust than either method alone.
_HYBRID_COLUMNS = (
    "Atom",
    "Element",
    "Shift (ppm)",
    "Source",
    "Expected error",
    "Methods differ by",
)
_HYBRID_UNAVAILABLE_NOTE = (
    "The hybrid view merges this calculation with the experimental-shift database, "
    "per atom. It needs an empirically scaled spectrum — calibrate this method/basis "
    "first (Calibrate Reference), since TMS referencing alone leaves the computed "
    "values on a different scale from measured ones."
)
_RAW_SHIELDING_NOTE = (
    "Note: isotropic shielding constants, not yet referenced to a standard (e.g. TMS) "
    "as a chemical shift — treat as raw ORCA output, not a directly comparable δ (ppm) value."
)
_CALIBRATED_NOTE = "Calibrated to TMS — values are real δ (ppm) chemical shifts."
_SCALED_NOTE = (
    "Empirically scaled — real δ (ppm), fitted against known compounds at this exact "
    "method/basis. More accurate than TMS referencing alone, which assumes a slope of −1."
)
#: Distinct from a bare "—" in a J (Hz) cell, which a user cannot tell apart
#: from "ORCA reported no coupling for this pair" -- see
#: NMRSpectrumResult.coupling_error's docstring for the four states this
#: collapses without it.
_COUPLING_FAILED_NOTE = (
    "Spin-spin coupling data unavailable — ORCA's coupling output could not be parsed. "
    "The chemical shifts above are unaffected."
)
# (correlation_type, compute_fn, x_axis_label, y_axis_label) -- HSQC/HMBC
# always put H first/C second (see chem/nmr_correlation.py), COSY is H-H.
_CORRELATION_SPECS = (
    ("hsqc", compute_hsqc_pairs, "1H shift (ppm)", "13C shift (ppm)"),
    ("hmbc", compute_hmbc_pairs, "1H shift (ppm)", "13C shift (ppm)"),
    ("cosy", compute_cosy_pairs, "1H shift (ppm)", "1H shift (ppm)"),
)


# THE HELP CONTRACTS FOR THIS PANEL.
#
# One dict rather than a `setToolTip` at each construction site, because a
# help_id is a stable semantic identifier and scattering the declarations
# makes "does this concept already have an id" unanswerable without
# reading the whole file.
#
# ONE CONCEPT, ONE `help_id`, AND THE UNIQUENESS RUNS BOTH WAYS. The three
# correlation tabs (HSQC/HMBC/COSY) are built from ONE column tuple by ONE
# loop and populated by ONE method, so their five columns mean the same
# five things in each -- they share five ids across fifteen renderings,
# and `instance_path` is what tells the renderings apart. What differs
# between those tabs is WHICH atom pairs appear, which is a property of
# the tab rather than of its columns. `Atom` and `Element` are likewise
# one concept each across the spectrum and hybrid tables.
_HELP: dict[str, HelpTooltip] = {
    "molecule": HelpTooltip(
        text=(
            "Which molecule in the current project the calculation runs on.\n\n"
            "The calculation is submitted as a 3D geometry, so the molecule needs a "
            "conformer; one is generated from the drawing if none exists."
        ),
        tier=1,
        help_id="quantum.molecule",
        topic="quantum-chemistry",
        help_anchor="quantum-chemistry",
    ),
    "calculation_type": HelpTooltip(
        text=(
            "What ORCA is asked to do. This decides which result tabs fill in: an NMR "
            "type populates the signal, correlation and Hybrid tabs, "
            "\"Optimization + Frequency\" produces the IR modes, and any type that "
            "keeps a wavefunction lets Surfaces be computed.\n\n"
            "A single point cannot produce vibrational modes, and a type this panel "
            "did not run leaves its tabs untouched rather than blank-because-broken."
        ),
        tier=2,
        help_id="quantum.calculation_type",
        topic="quantum-chemistry",
        help_anchor="quantum-chemistry",
    ),
    "total_charge": HelpTooltip(
        text=(
            "Total charge of the species, in units of the elementary charge. "
            "Range -10 to +10.\n\n"
            "Set for you from the drawn structure's formal charge whenever you pick a "
            "molecule, and free to override afterwards. It declares WHICH species is "
            "being calculated: ORCA will converge a wrong charge perfectly happily "
            "and report it as an ordinary result."
        ),
        tier=2,
        help_id="quantum.total_charge",
        topic="quantum-chemistry",
        help_anchor="quantum-chemistry",
    ),
    "spin_multiplicity": HelpTooltip(
        text=(
            "Spin multiplicity, 2S+1: 1 for a closed-shell singlet, 2 for a doublet "
            "radical, 3 for a triplet. Range 1 to 10, default 1.\n\n"
            "UNLIKE CHARGE, THIS IS NOT DERIVED FROM THE STRUCTURE -- it stays at 1 "
            "whatever you select, so a radical or a triplet has to be set by hand. A "
            "singlet calculation on an open-shell species converges to a state the "
            "molecule does not have."
        ),
        tier=2,
        help_id="quantum.spin_multiplicity",
        topic="quantum-chemistry",
        help_anchor="quantum-chemistry",
    ),
    "method_basis": HelpTooltip(
        text=(
            "The functional and basis set, written as ORCA's own keyword line -- this "
            "text becomes the `!` header of the input file verbatim, so anything ORCA "
            "accepts there can be typed here rather than picked from the list.\n\n"
            "Choosing an NMR calculation moves this to a basis set with the core "
            "flexibility shielding needs, unless you have edited it yourself, in "
            "which case your text is left alone."
        ),
        tier=2,
        help_id="quantum.method_basis",
        topic="quantum-chemistry",
        help_anchor="quantum-chemistry",
    ),
    "cpu_cores": HelpTooltip(
        text=(
            "How many CPU cores ORCA uses for the calculation.\n\n"
            "Measured on a 59-atom NMR job: 1 core 743 s, 8 cores 97 s, 16 cores 111 s. "
            "Gains stop at about eight, so the automatic choice is capped there. "
            "Needs Microsoft MPI."
        ),
        tier=2,
        help_id="quantum.cpu_cores",
    ),
    "solvent_model": HelpTooltip(
        text=(
            "Adds an implicit solvent to the calculation as a CPCM keyword on the "
            "method line. \"None (gas phase)\" adds nothing.\n\n"
            "CPCM is a continuum: it models the bulk polarisation of the solvent "
            "rather than individual solvent molecules, so it does not represent a "
            "specific hydrogen bond to solvent.\n\n"
            "Because the solvent travels as part of the method string, a solvated and "
            "a gas-phase setup are separate TMS reference entries and cannot be "
            "calibrated against each other by accident."
        ),
        tier=2,
        help_id="quantum.solvent_model",
        topic="quantum-chemistry",
        help_anchor="quantum-chemistry",
    ),
    "configure_orca": HelpTooltip(
        text=(
            "Opens the external-tools settings at the ORCA entry, where the path to "
            "the executable is set. ORCA is installed by you and is not bundled with "
            "this application; nothing in this panel can run until that path is set."
        ),
        tier=1,
        help_id="quantum.configure_orca",
        topic="quantum-chemistry",
        help_anchor="external-tools",
    ),
    "tms_reference_calibration": HelpTooltip(
        text=(
            "Runs TMS at the method and basis currently selected and uses its "
            "shielding to convert this method's raw shielding constants into chemical "
            "shifts. The result is cached per method/basis, so it is not re-run for "
            "every molecule.\n\n"
            "Referencing against TMS alone assumes the relationship between shielding "
            "and shift has a slope of exactly -1. That fixes where the scale starts, "
            "not how it is stretched. \"Calibrate Scaling\" fits the slope from real "
            "compounds and is the more accurate route."
        ),
        tier=3,
        help_id="quantum.tms_reference_calibration",
        topic="quantum-chemistry",
        help_anchor="limits-nmr",
    ),
    "empirical_shift_scaling": HelpTooltip(
        text=(
            "Fits an empirical shift-scaling line from ORCA runs on eleven known "
            "compounds at this exact method and basis, correcting both the offset and "
            "the slope that TMS referencing alone leaves at -1. Once it has run, its "
            "factors take priority over the TMS reference.\n\n"
            "It costs one ORCA run per standard, against the single run TMS "
            "referencing needs -- which is why it is a separate button rather than an "
            "upgrade of that one.\n\n"
            "The fit belongs to the method and basis it was calibrated at, and says "
            "nothing about any other."
        ),
        tier=3,
        help_id="quantum.empirical_shift_scaling",
        topic="quantum-chemistry",
        help_anchor="limits-nmr",
    ),
    "tab_help": HelpTooltip(
        text=(
            "Opens the documentation for whichever tab is currently active -- "
            "what HSQC/HMBC/COSY correlate, the difference between raw "
            "shielding/TMS-referenced/empirically scaled shifts, what the "
            "Hybrid tab merges, and so on. One button for the whole strip "
            "rather than one per tab, because it always follows the tab "
            "you are already looking at."
        ),
        tier=1,
        help_id="quantum.tab_help",
        topic="quantum-chemistry",
        help_anchor="quantum-chemistry",
    ),
    "more_menu": HelpTooltip(
        text=(
            "Configure ORCA, Calibrate Reference and Calibrate Scaling -- set up "
            "once per method/basis rather than pressed for every run, so they sit "
            "behind this disclosure instead of crowding Run and Cancel."
        ),
        tier=1,
        help_id="quantum.more_menu",
        topic="quantum-chemistry",
        help_anchor="quantum-chemistry",
    ),
    "run_calculation": HelpTooltip(
        text=(
            "Submits the calculation to ORCA and streams its output into the Log tab "
            "as it works. Results land in the tabs relevant to the calculation type "
            "once the job finishes."
        ),
        tier=1,
        help_id="quantum.run_calculation",
        topic="quantum-chemistry",
        help_anchor="quantum-chemistry",
    ),
    "cancel_calculation": HelpTooltip(
        text=(
            "Stops the running ORCA process and removes its scratch directory. "
            "Whatever it had computed so far is lost: a cancelled job produces no "
            "partial result."
        ),
        tier=1,
        help_id="quantum.cancel_calculation",
        topic="quantum-chemistry",
        help_anchor="quantum-chemistry",
    ),
    "boltzmann_averaging": HelpTooltip(
        text=(
            "Runs the calculation on every conformer and averages the shifts by their "
            "Boltzmann populations, using each run's own SCF energy.\n\n"
            "A flexible molecule in solution interconverts fast on the NMR timescale, "
            "so the measured shift is a population average -- not the lowest-energy "
            "geometry's.\n\n"
            "Costs one full ORCA run per conformer. The average is only as good as "
            "the conformer set it is taken over: a conformer that was never generated "
            "contributes nothing and is not accounted for."
        ),
        tier=3,
        help_id="quantum.boltzmann_averaging",
        topic="quantum-chemistry",
        help_anchor="limits-nmr",
    ),
    "correlation_contours": HelpTooltip(
        text=(
            "Draw cross peaks as contour rings rather than dots.\n\n"
            "The rings show POSITION only. Predicted correlations carry no intensity, "
            "so every peak is drawn the same height and width -- unlike a measured "
            "spectrum, where contour height is peak volume.\n\n"
            "Set per tab, because a sparse HSQC and a crowded HMBC of the same "
            "molecule genuinely want different answers."
        ),
        tier=3,
        help_id="quantum.correlation_contours",
        topic="quantum-chemistry",
        help_anchor="2d-correlation",
    ),
    # --- the 1D spectrum table, whose first two columns the Hybrid tab shares
    "nmr_atom_index": HelpTooltip(
        text=(
            "The atom this row reports, numbered from 0 in the geometry that was sent "
            "to ORCA -- that is, the structure WITH EXPLICIT HYDROGENS.\n\n"
            "It is not the numbering of the 2D drawing, where hydrogens are implicit "
            "and carry no index of their own."
        ),
        tier=2,
        help_id="quantum.nmr_atom_index",
        topic="quantum-chemistry",
        help_anchor="quantum-chemistry",
    ),
    "nmr_element": HelpTooltip(
        text="Chemical element of this atom, as ORCA reported it for that nucleus.",
        tier=1,
        help_id="quantum.nmr_element",
        topic="quantum-chemistry",
        help_anchor="quantum-chemistry",
    ),
    "nmr_value": HelpTooltip(
        text=(
            "THIS COLUMN HOLDS ONE OF TWO DIFFERENT QUANTITIES, which is why it is "
            "named \"Value\" rather than \"Shift\". The note directly above the "
            "table says which one is on screen.\n\n"
            "Uncalibrated, it is the raw isotropic shielding constant in ppm, straight "
            "from ORCA and referenced to nothing. Shielding runs the OPPOSITE way to a "
            "chemical shift: a more shielded nucleus has a LARGER shielding constant "
            "and a SMALLER shift, so these numbers must not be compared against "
            "literature shifts.\n\n"
            "Once a reference or a scaling has been calibrated, it is a real chemical "
            "shift in ppm and is comparable with measured spectra."
        ),
        tier=3,
        help_id="quantum.nmr_value",
        topic="quantum-chemistry",
        help_anchor="limits-nmr",
    ),
    # --- the correlation tables: five ids across fifteen renderings
    "correlation_atom_a": HelpTooltip(
        text=(
            "First atom of this cross peak -- the 1H in all three experiments -- "
            "numbered from 0 in the structure with explicit hydrogens rather than in "
            "the 2D drawing."
        ),
        tier=2,
        help_id="quantum.correlation_atom_a",
        topic="quantum-chemistry",
        help_anchor="quantum-chemistry",
    ),
    "correlation_atom_b": HelpTooltip(
        text=(
            "Second atom of this cross peak -- the 13C in HSQC and HMBC, the partner "
            "1H in COSY -- numbered from 0 in the structure with explicit hydrogens "
            "rather than in the 2D drawing."
        ),
        tier=2,
        help_id="quantum.correlation_atom_b",
        topic="quantum-chemistry",
        help_anchor="quantum-chemistry",
    ),
    "correlation_shift_a": HelpTooltip(
        text=(
            "This calculation's value for the first atom, in ppm, which is the peak's "
            "horizontal position. It carries whatever referencing the run has: "
            "uncalibrated, it is a raw shielding constant rather than a shift."
        ),
        tier=2,
        help_id="quantum.correlation_shift_a",
        topic="quantum-chemistry",
        help_anchor="limits-nmr",
    ),
    "correlation_shift_b": HelpTooltip(
        text=(
            "This calculation's value for the second atom, in ppm, which is the "
            "peak's vertical position. It carries whatever referencing the run has: "
            "uncalibrated, it is a raw shielding constant rather than a shift."
        ),
        tier=2,
        help_id="quantum.correlation_shift_b",
        topic="quantum-chemistry",
        help_anchor="limits-nmr",
    ),
    "correlation_coupling": HelpTooltip(
        text=(
            "The computed spin-spin coupling constant for this pair, in Hz. Only the "
            "\"NMR + Spin-Spin Coupling\" calculation produces one.\n\n"
            "A dash means NO COUPLING WAS COMPUTED for this pair -- it does not mean "
            "the coupling is zero. The cross peaks themselves are derived from bonding "
            "connectivity, so a peak is listed whether or not there is a coupling "
            "constant to put beside it."
        ),
        tier=3,
        help_id="quantum.correlation_coupling",
        topic="quantum-chemistry",
        help_anchor="limits-nmr",
    ),
    # --- the Hybrid tab
    "hybrid_shift": HelpTooltip(
        text=(
            "The chemical shift kept for this atom, in ppm, after merging this "
            "calculation with the experimental-shift database.\n\n"
            "Always a real shift rather than a raw shielding constant: the merge needs "
            "an empirically scaled spectrum, so an uncalibrated run produces no rows "
            "here at all."
        ),
        tier=3,
        help_id="quantum.hybrid_shift",
        topic="quantum-chemistry",
        help_anchor="limits-nmr",
    ),
    "hybrid_source": HelpTooltip(
        text=(
            "Which predictor supplied the value kept for this atom -- the experimental "
            "database lookup, or this ORCA run after empirical scaling.\n\n"
            "Chosen per atom by whichever expects to be less wrong, so one spectrum "
            "routinely mixes both. A method that cannot state an expected error never "
            "beats one that can."
        ),
        tier=2,
        help_id="quantum.hybrid_source",
        topic="quantum-chemistry",
        help_anchor="limits-nmr",
        # The lookup half of this column names an external database.
        source_key="nmrshiftdb2",
    ),
    "hybrid_expected_error": HelpTooltip(
        text=(
            "How wrong the winning method expects to be for this atom, in ppm.\n\n"
            "It is a property of the METHOD, not a measurement against experiment for "
            "this molecule -- nothing here has been compared with a real spectrum of "
            "the compound on screen. It is the quantity the per-atom choice is made "
            "on.\n\n"
            "\"unknown\" means the winning method cannot state one."
        ),
        tier=3,
        help_id="quantum.hybrid_expected_error",
        topic="quantum-chemistry",
        help_anchor="limits-nmr",
    ),
    "hybrid_disagreement": HelpTooltip(
        text=(
            "The spread, in ppm, between the values the two methods offered for this "
            "atom. A dash means only one method offered a value, so there was nothing "
            "to disagree with.\n\n"
            "AGREEMENT IS NOT ACCURACY. A small spread says the database and the "
            "calculation landed in the same place; both can be in the same place and "
            "both wrong. A large spread is the useful signal -- it marks an atom worth "
            "checking by hand."
        ),
        tier=3,
        help_id="quantum.hybrid_disagreement",
        topic="quantum-chemistry",
        help_anchor="limits-nmr",
    ),
    "runs_combo": HelpTooltip(
        text=(
            "Every retained calculation for this molecule, newest first. Selecting "
            "one repaints every tab from THAT run -- its spectrum, descriptors, IR "
            "and surfaces, none of another run's.\n\n"
            "This only changes what is displayed. It does not change what the next "
            "press of Run will submit."
        ),
        tier=1,
        help_id="quantum.runs_combo",
        topic="quantum-chemistry",
        help_anchor="quantum-chemistry",
    ),
    "delete_run": HelpTooltip(
        text=(
            "Removes the selected run from this project's history. Only the "
            "project record is deleted -- a reusable wavefunction it left in the "
            "quantum-chemistry cache is untouched, and a later identical "
            "calculation can still reuse it."
        ),
        tier=2,
        help_id="quantum.delete_run",
        topic="quantum-chemistry",
        help_anchor="quantum-chemistry",
    ),
    "compare_runs": HelpTooltip(
        text=(
            "Compares this molecule's retained NMR shifts across two runs, atom "
            "by atom -- the same dialog the Atom Inspector's \"Compare with...\" "
            "opens. Refuses when the two runs' atom numbering cannot be safely "
            "matched (for instance after a structural edit between them), rather "
            "than silently lining up the wrong atoms."
        ),
        tier=2,
        help_id="quantum.compare_runs",
        topic="quantum-chemistry",
        help_anchor="quantum-chemistry",
    ),
}

#: Column position -> key in `_HELP`, per table. The correlation tuple is
#: ONE mapping used by all three correlation tabs, which is the
#: shared-concept claim above made executable rather than merely written
#: down: there is no place for the three to drift apart.
_SPECTRUM_COLUMN_HELP = ("nmr_atom_index", "nmr_element", "nmr_value")
_CORRELATION_COLUMN_HELP = (
    "correlation_atom_a",
    "correlation_atom_b",
    "correlation_shift_a",
    "correlation_shift_b",
    "correlation_coupling",
)
_HYBRID_COLUMN_HELP = (
    "nmr_atom_index",
    "nmr_element",
    "hybrid_shift",
    "hybrid_source",
    "hybrid_expected_error",
    "hybrid_disagreement",
)


def _document_header(table: QTableWidget, keys: tuple[str, ...]) -> None:
    """Attach the contracts to a table's HEADER ITEMS.

    A `QTableWidgetItem` is not a `QObject`, so its contract is stored as
    item data rather than as a Qt property -- `apply_help_tooltip` handles
    that. A tooltip audit walking `QWidget`s alone would report these
    tables fully documented while covering none of their columns, which is
    the hole the header surface exists to close.
    """
    for column, key in enumerate(keys):
        item = table.horizontalHeaderItem(column)
        if item is not None:
            apply_help_tooltip(item, _HELP[key])


class QuantumChemistryPanel(QWidget):
    """Pick a molecule from the current project, configure a calculation,
    and run it via whichever `QuantumEngineProvider` is registered
    (`OrcaQuantumEngineProvider` is the only one today). Streams ORCA's
    stdout live and shows a summary once results arrive.
    """

    def __init__(
        self,
        quantum_chemistry_service: QuantumChemistryService,
        chemistry_engine: ChemistryEngine,
        settings: Settings,
        event_bus: EventBus,
        parent: QWidget | None = None,
        qm_surface_service=None,
        result_store_service=None,
        open_help=None,
    ) -> None:
        """Built in five steps, in the order they must happen.

        Split from a single 334-line constructor -- the longest of the
        four. Each step's lines are verbatim at the indent they already
        had, so every comment still sits against what it explains: why
        solvent is not a separate parameter threaded through the service,
        why Boltzmann averaging is opt-in, and why the 1D view's
        `QWebEngineView` is built lazily.

        **THE ORDER IS THE CONTRACT.** Controls exist before the tabs that
        hold them and the form that lays them out, and the events are
        subscribed last so no handler can fire against a half-built panel.
        Checked before cutting: no local is assigned in one step and read
        in another, so this is a move rather than a behaviour change.
        """
        super().__init__(parent)
        self._init_state(
            quantum_chemistry_service, chemistry_engine, settings, qm_surface_service,
            result_store_service, open_help,
        )
        self._build_controls()
        self._build_tabs()
        self._build_form_and_layout()
        self._subscribe_to_events(event_bus)

    def _init_state(
        self,
        quantum_chemistry_service: QuantumChemistryService,
        chemistry_engine: ChemistryEngine,
        settings: Settings,
        qm_surface_service,
        result_store_service=None,
        open_help=None,
    ) -> None:
        """The services and the state fields, before any widget exists."""
        self._quantum_chemistry_service = quantum_chemistry_service
        self._chemistry_engine = chemistry_engine
        self._settings = settings
        # `open_help(topic_key)` opens it elsewhere (the app-wide, F1-bound
        # window); left None, the panel opens a private one of its own --
        # `CalculatorVisibilityPage`'s exact contract, for the exact same
        # reason: nothing here requires a MainWindow to exist, which every
        # test that builds this panel standalone depends on.
        self._open_help = open_help
        self._help_window = None
        # Optional, and after `parent` so every existing positional call
        # site keeps working. Without it the Surfaces tab says why it is
        # empty rather than not existing -- a missing tab reads as a
        # version difference, an explained one reads as configuration.
        self._qm_surface_service = qm_surface_service
        # Optional for the same reason. Without it the panel behaves
        # exactly as it always did (live results only, nothing survives a
        # molecule switch or a reload) -- the QC run history it owns
        # (`.qc_runs`) is what `_refresh_active_run` reads from.
        self._result_store_service = result_store_service
        self._project: ProjectModel | None = None
        self._pending_molecule_uuid: str | None = None
        self._pending_mol = None  # rdkit.Chem.Mol, set in _on_run_clicked -- needed
        # by _on_spectrum_computed to compute connectivity-derived HSQC/
        # HMBC/COSY correlations against whichever shift values arrive.
        # The molecule's own 2D structure and its conformer, kept for the 1D
        # NMR view: the depiction must come from the 2D molblock (drawing
        # the conformer's flattened 3D coordinates gives an unreadable
        # tangle), the 3D pane from the conformer.
        self._pending_molblock: str = ""
        self._pending_conformer_molblock: str = ""
        #: The geometry ORCA optimised, once it arrives. Kept separate from
        #: the submitted one because the normal modes describe motion about
        #: THIS structure, not the one that was sent.
        self._optimized_conformer_molblock: str = ""
        #: The RDKit Mol `_update_correlation_tabs`/`_update_hybrid_tab`
        #: compute connectivity against -- separate from `_pending_mol`,
        #: which means "the job currently in flight this session" and must
        #: not double as "what is currently displayed" (that conflation is
        #: exactly why history couldn't be shown before this field existed:
        #: `_pending_mol` is `None` whenever no job has been submitted this
        #: session, including right after a project loads). Set from a live
        #: job's own `_pending_mol` when its result arrives, or from a
        #: historical run's `input_molblock` by `_render_run`.
        self._display_mol = None
        #: The run currently being displayed -- `None` until
        #: `_refresh_active_run` finds one, or once Phase 2 adds a history
        #: picker, whichever run the user selected there.
        self._active_run = None

    def _build_controls(self) -> None:
        """Every control above the tabs, in the order it is laid out."""
        # `make_scroll_safe` on every combo/spin box built in this method:
        # confirmed live (OPENCHEM_DRIVE's wheel_trace/wheel steps) that a
        # `QComboBox` accepts a wheel event directly and a `QSpinBox` does
        # too via its internal line edit's ignore propagating up to it --
        # neither checks focus, so scrolling PAST one of these on the way
        # down the panel silently changes it. The returned guards are kept
        # (not just relied on via Qt's own parent/child lifetime) so a test
        # can find them.
        self._scroll_safe_guards: list = []

        self._molecule_combo = QComboBox(self)
        apply_help_tooltip(self._molecule_combo, _HELP["molecule"])
        self._molecule_combo.currentIndexChanged.connect(self._on_molecule_changed)
        self._scroll_safe_guards.append(make_scroll_safe(self._molecule_combo))

        self._calc_type_combo = QComboBox(self)
        apply_help_tooltip(self._calc_type_combo, _HELP["calculation_type"])
        self._calc_type_combo.addItems(list(CALC_TYPE_LABELS.keys()))
        self._calc_type_combo.currentTextChanged.connect(self._on_calc_type_changed)
        self._scroll_safe_guards.append(make_scroll_safe(self._calc_type_combo))

        self._charge_spin = QSpinBox(self)
        self._charge_spin.setRange(-10, 10)
        apply_help_tooltip(self._charge_spin, _HELP["total_charge"])
        self._scroll_safe_guards.append(make_scroll_safe(self._charge_spin))

        self._multiplicity_spin = QSpinBox(self)
        self._multiplicity_spin.setRange(1, 10)
        self._multiplicity_spin.setValue(1)
        apply_help_tooltip(self._multiplicity_spin, _HELP["spin_multiplicity"])
        self._scroll_safe_guards.append(make_scroll_safe(self._multiplicity_spin))

        self._method_combo = QComboBox(self)
        self._method_combo.setEditable(True)
        self._method_combo.addItems(METHOD_BASIS_PRESETS)
        apply_help_tooltip(self._method_combo, _HELP["method_basis"])
        self._scroll_safe_guards.append(make_scroll_safe(self._method_combo))

        # Solvent is NOT a separate parameter threaded through the service --
        # it is appended to the method/basis string as a CPCM keyword, which
        # is what ORCA itself wants (`! B3LYP pcSseg-1 CPCM(Chloroform)`) and
        # what `method_basis` already is here: the whole free-text `!` header.
        #
        # That is not just convenience. The TMS reference cache is keyed on
        # the method_basis string verbatim, so appending the solvent makes a
        # chloroform reference and a gas-phase reference distinct cache
        # entries automatically. A separate `solvent` parameter would have
        # left them sharing one key and silently calibrated solvated shifts
        # against a gas-phase TMS.
        self._solvent_combo = QComboBox(self)
        apply_help_tooltip(self._solvent_combo, _HELP["solvent_model"])
        for solvent in SOLVENTS:
            self._solvent_combo.addItem(solvent or "None (gas phase)", solvent)
        self._scroll_safe_guards.append(make_scroll_safe(self._solvent_combo))

        # Stored under `orca/cores`, which the service reads at launch. Without
        # MPI a parallel job aborts, so the box is pinned to 1 and says why.
        self._cores_spin = QSpinBox(self)
        self._cores_spin.setRange(1, max(1, os.cpu_count() or 1))
        apply_help_tooltip(self._cores_spin, _HELP["cpu_cores"])
        self._scroll_safe_guards.append(make_scroll_safe(self._cores_spin))
        if find_mpi_bin() is None:
            self._cores_spin.setValue(1)
            self._cores_spin.setEnabled(False)
            self._cores_spin.setToolTip(
                "Running on more than one core needs Microsoft MPI (mpiexec), which is not installed."
            )
        else:
            stored = self._settings.get("orca/cores", 0)
            self._cores_spin.setValue(int(stored) if stored and int(stored) >= 1 else default_cores())
            self._cores_spin.valueChanged.connect(self._on_cores_changed)

        # Opt-in, because it costs one full ORCA run per conformer. Off by
        # default so nobody accidentally turns a 5-minute job into an hour.
        self._boltzmann_check = QCheckBox("Average over all conformers (Boltzmann)", self)
        apply_help_tooltip(self._boltzmann_check, _HELP["boltzmann_averaging"])

        self._configure_button = QPushButton("Configure ORCA...", self)
        apply_help_tooltip(self._configure_button, _HELP["configure_orca"])
        self._configure_button.clicked.connect(self._on_configure_clicked)

        self._calibrate_button = QPushButton("Calibrate Reference (TMS)...", self)
        apply_help_tooltip(self._calibrate_button, _HELP["tms_reference_calibration"])
        self._calibrate_button.clicked.connect(self._on_calibrate_clicked)
        # A second, more thorough calibration. Costs N ORCA runs against
        # the TMS button's one, which is why it is its own button rather
        # than an upgrade of that one -- the user should choose to spend
        # that time. Once it has run, its factors take priority.
        self._scaling_button = QPushButton("Calibrate Scaling (11 standards)...", self)
        apply_help_tooltip(self._scaling_button, _HELP["empirical_shift_scaling"])
        self._scaling_button.clicked.connect(self._on_scaling_calibrate_clicked)

        # Three buttons that are set-up-once-and-forget, not part of the
        # per-run workflow -- collapsed behind one disclosure rather than
        # sitting in the row every Run/Cancel press has to share space
        # with. Real `QPushButton`s, not `QAction`s: every test and every
        # help tooltip above already targets these exact widgets, and a
        # `QWidgetAction` embeds a widget in a menu unchanged rather than
        # replacing it with a new control that would need its own wiring.
        self._more_menu = QMenu(self)
        for button in (self._configure_button, self._calibrate_button, self._scaling_button):
            action = QWidgetAction(self._more_menu)
            action.setDefaultWidget(button)
            self._more_menu.addAction(action)
        self._more_button = QToolButton(self)
        self._more_button.setText("More")
        self._more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._more_button.setMenu(self._more_menu)
        apply_help_tooltip(self._more_button, _HELP["more_menu"])
        self._more_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)

        self._run_button = QPushButton("Run", self)
        apply_help_tooltip(self._run_button, _HELP["run_calculation"])
        self._run_button.clicked.connect(self._on_run_clicked)
        self._cancel_button = QPushButton("Cancel", self)
        self._cancel_button.setEnabled(False)
        apply_help_tooltip(self._cancel_button, _HELP["cancel_calculation"])
        self._cancel_button.clicked.connect(self._on_cancel_clicked)

        # One history control for the WHOLE panel, not one per tab -- every
        # tab repaints from whichever run is selected here. Disabled/empty
        # until `_refresh_active_run` has something to show (no project, no
        # molecule, or no QC history for it yet).
        self._runs_combo = QComboBox(self)
        apply_help_tooltip(self._runs_combo, _HELP["runs_combo"])
        self._runs_combo.currentIndexChanged.connect(self._on_runs_combo_changed)
        self._delete_run_button = QPushButton("Delete Run", self)
        apply_help_tooltip(self._delete_run_button, _HELP["delete_run"])
        self._delete_run_button.clicked.connect(self._on_delete_run_clicked)
        self._compare_runs_button = QPushButton("Compare NMR Shifts...", self)
        apply_help_tooltip(self._compare_runs_button, _HELP["compare_runs"])
        self._compare_runs_button.clicked.connect(self._on_compare_runs_clicked)
        self._set_runs_controls_enabled(False)

        # ONE affordance for the whole tab strip, not one per tab -- it
        # follows whichever tab is active (`_tab_help_topics`, resolved at
        # click time) rather than cluttering eight already-cramped tab
        # headers with their own help buttons.
        self._tab_help_button = QPushButton("Help for this tab", self)
        self._tab_help_button.setAutoDefault(False)
        apply_help_tooltip(self._tab_help_button, _HELP["tab_help"])
        self._tab_help_button.clicked.connect(self._on_tab_help_clicked)

        self._status_label = QLabel("", self)
        self._output_log = QPlainTextEdit(self)
        self._output_log.setReadOnly(True)
        # `QPlainTextEdit` has placeholder text natively, so the Log tab
        # explains itself without adding a widget to a panel that cannot
        # afford one -- see the `addTab` comment below.
        self._output_log.setPlaceholderText(
            "Nothing has run yet. Press Run above and ORCA's output streams "
            "here as it works."
        )
        self._results_label = QLabel("", self)
        self._results_label.setWordWrap(True)

        self._spectrum_note_label = QLabel(_RAW_SHIELDING_NOTE, self)
        self._spectrum_note_label.setWordWrap(True)
        self._spectrum_note_label.setVisible(False)
        self._spectrum_table = QTableWidget(0, len(_NMR_SPECTRUM_COLUMNS), self)
        self._spectrum_table.setHorizontalHeaderLabels(_NMR_SPECTRUM_COLUMNS)
        _document_header(self._spectrum_table, _SPECTRUM_COLUMN_HELP)
        self._spectrum_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._spectrum_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._spectrum_table.setVisible(False)

    def _build_tabs(self) -> None:
        """The tab widget: 1D signals, IR, surfaces, hybrid, the three
        correlation tabs and the log.
        """
        # NMR tabs: the Phase 23c 1D signal view first, then the Phase 22 2D
        # correlation tabs (HSQC/HMBC/COSY) -- one table + scatter plot per
        # correlation type, built from connectivity alone
        # (chem/nmr_correlation.py), so they populate regardless of
        # whether the shift values are raw shielding or TMS-calibrated.
        self._correlation_tabs = QTabWidget(self)
        self._correlation_tabs.setVisible(False)
        # Per-tab status glyph: base title (set once, below) -> the active
        # run's `output_status` key it reflects. Populated per-tab as each
        # is built rather than with a generic wrapper, because several
        # tabs (Hybrid, Surfaces, the Log) have no `output_status` entry
        # of their own and are deliberately left out of this dict -- no
        # entry means no glyph, not a guessed one.
        self._tab_status_titles: dict[int, str] = {}
        self._tab_status_keys: dict[int, str] = {}
        #: Tab index -> help topic key, read by the one contextual help
        #: affordance above the tab strip -- it follows whichever tab is
        #: active rather than needing one help button per tab.
        self._tab_help_topics: dict[int, str] = {}
        # The 1D view owns a QWebEngineView for its 3D pane, which is
        # expensive enough not to build for every user who never runs an NMR
        # calculation -- the tab exists from the start (so tab order never
        # shifts under the user), the widget lands in it on first result.
        # Every tab below carries a placeholder saying why it is blank and
        # what would fill it. A job populates the tabs relevant to ITS
        # calculation type and leaves the rest untouched, so most of these
        # are empty most of the time -- an ESP single point lights up
        # Surfaces and nothing else. With nothing on screen to say so, all
        # six other tabs read as broken.
        #
        # They are deliberately NOT collected into a dict here; see
        # `_content_of` for the heap corruption that caused.

        self._nmr_view: NmrViewWidget | None = None
        self._nmr_view_tab = QWidget(self._correlation_tabs)
        self._nmr_view_layout = QVBoxLayout(self._nmr_view_tab)
        # THE LOG IS A TAB.
        #
        # `_output_log` is a `QPlainTextEdit` whose default Expanding
        # policy took the largest share of the panel, so a finished
        # calculation showed a wall of SCF iterations above a cramped band
        # of the numbers it was run for. Alex: "completed calculations
        # should emphasize results rather than console output".
        #
        # A tab rather than a collapsible section, which is the shape Alex
        # offered -- "or a separate Log tab" -- and which reparents the
        # widget that already exists rather than wrapping it in a new one.
        #
        # (Wrapping it DID crash the suite when this was written, and the
        # comment here used to explain that at length. The cause was the
        # test harness collecting MainWindows, not this panel; see
        # CLAUDE.md, "SOLVED: the teardown collect was DESTROYING
        # MainWindows". A section would be safe now. A tab is still the
        # better answer, so it stays.)
        self._correlation_tabs.addTab(self._nmr_view_tab, "1D Signals")
        self._tab_status_titles[self._correlation_tabs.indexOf(self._nmr_view_tab)] = "1D Signals"
        self._tab_status_keys[self._correlation_tabs.indexOf(self._nmr_view_tab)] = "spectrum"
        self._tab_help_topics[self._correlation_tabs.indexOf(self._nmr_view_tab)] = "nmr-referencing"
        self._add_empty_state(
            self._nmr_view_tab,
            self._nmr_view_layout,
            "No NMR signals for this molecule yet.",
            'Choose an NMR calculation in "Calculation" above and press Run. '
            "Grouped signals, integrations and multiplicities appear here.",
        )

        # IR, on the same deferred-construction pattern and for the same
        # reason (a QWebEngineView for its 3D pane). Added AFTER the NMR
        # tab rather than before it so existing tab positions do not move.
        self._ir_view: IrViewWidget | None = None
        self._ir_view_tab = QWidget(self._correlation_tabs)
        self._ir_view_layout = QVBoxLayout(self._ir_view_tab)
        self._correlation_tabs.addTab(self._ir_view_tab, "IR")
        self._tab_status_titles[self._correlation_tabs.indexOf(self._ir_view_tab)] = "IR"
        self._tab_status_keys[self._correlation_tabs.indexOf(self._ir_view_tab)] = "vibrational_spectrum"
        self._tab_help_topics[self._correlation_tabs.indexOf(self._ir_view_tab)] = "ir-spectra"
        self._add_empty_state(
            self._ir_view_tab,
            self._ir_view_layout,
            "No vibrational spectrum yet.",
            'Run an "Optimisation + Frequencies" calculation. The modes come '
            "from the frequency step, so a single point cannot produce them.",
        )

        # Surfaces: the point-charge ESP beside the ab initio one. Same
        # deferred construction -- it owns TWO QWebEngineViews, which is
        # the most expensive tab here and the least often opened.
        self._surfaces_view: EspCompareWidget | None = None
        self._surfaces_tab = QWidget(self._correlation_tabs)
        self._surfaces_layout = QVBoxLayout(self._surfaces_tab)
        self._correlation_tabs.addTab(self._surfaces_tab, "Surfaces")
        self._tab_status_titles[self._correlation_tabs.indexOf(self._surfaces_tab)] = "Surfaces"
        # Surfaces has no `output_status` entry of its own -- a run either
        # retained a wavefunction to compute one from, or it didn't. This
        # sentinel key tells `_update_tab_status_indicators` to read
        # `run.surface_cache_key` instead of `run.output_status`.
        self._tab_status_keys[self._correlation_tabs.indexOf(self._surfaces_tab)] = "__surface_cache_key"
        self._tab_help_topics[self._correlation_tabs.indexOf(self._surfaces_tab)] = "surfaces"
        self._add_empty_state(
            self._surfaces_tab,
            self._surfaces_layout,
            "No surface computed yet.",
            "Run any calculation that keeps its wavefunction, then pick a "
            "surface type above and press Compute QM surface. The instant "
            "point-charge map needs no calculation at all.",
        )

        # Hybrid: this calculation merged with the experimental-shift
        # lookup, per atom, choosing whichever expects to be less wrong.
        # Built here rather than on first result because it is a plain
        # label and table -- nothing expensive to defer.
        hybrid_tab = QWidget(self._correlation_tabs)
        hybrid_layout = QVBoxLayout(hybrid_tab)
        self._hybrid_summary_label = QLabel("", hybrid_tab)
        self._hybrid_summary_label.setWordWrap(True)
        self._hybrid_table = QTableWidget(0, len(_HYBRID_COLUMNS), hybrid_tab)
        self._hybrid_table.setHorizontalHeaderLabels(_HYBRID_COLUMNS)
        _document_header(self._hybrid_table, _HYBRID_COLUMN_HELP)
        self._hybrid_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._hybrid_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        hybrid_layout.addWidget(self._hybrid_summary_label)
        hybrid_layout.addWidget(self._hybrid_table)
        self._correlation_tabs.addTab(hybrid_tab, "Hybrid")
        self._tab_status_titles[self._correlation_tabs.indexOf(hybrid_tab)] = "Hybrid"
        self._tab_status_keys[self._correlation_tabs.indexOf(hybrid_tab)] = "spectrum"
        self._tab_help_topics[self._correlation_tabs.indexOf(hybrid_tab)] = "hybrid-shifts"
        # The hybrid tab needs no placeholder WIDGET: `_hybrid_summary_label`
        # already exists to carry exactly this kind of note, and already
        # shows `_HYBRID_UNAVAILABLE_NOTE` when a run produces no rows. It
        # only ever started blank, so it is given its message up front.
        self._hybrid_summary_label.setText(
            "No hybrid shifts yet. Run an NMR calculation -- this tab merges "
            "it with the experimental-shift lookup, per atom, choosing "
            "whichever expects to be less wrong."
        )

        self._correlation_tables: dict[str, QTableWidget] = {}
        self._correlation_plots: dict[str, NmrCorrelationPlotWidget] = {}
        for correlation_type, _compute_fn, _x_label, _y_label in _CORRELATION_SPECS:
            tab = QWidget(self._correlation_tabs)
            tab_layout = QVBoxLayout(tab)
            table = QTableWidget(0, len(_CORRELATION_COLUMNS), tab)
            # Read back via `sender()` in the two handlers below, instead
            # of a lambda closing over `correlation_type` (and, with it,
            # `self` -- a lambda connected to a child widget's signal is
            # not disconnected when the panel itself would otherwise be
            # collected, unlike a bound method, which Qt tracks and
            # disconnects on its own). `test_qt_object_disposal.py`'s
            # self-capturing-lambda guard is what caught this.
            table.setProperty("correlation_type", correlation_type)
            table.setHorizontalHeaderLabels(_CORRELATION_COLUMNS)
            _document_header(table, _CORRELATION_COLUMN_HELP)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            plot = NmrCorrelationPlotWidget(parent=tab)
            plot.setProperty("correlation_type", correlation_type)
            # One checkbox per tab rather than one for the panel: HSQC is
            # sparse enough to read as dots while HMBC on the same molecule
            # is crowded enough to want contours, so the useful setting
            # genuinely differs between them.
            contour_toggle = QCheckBox("Contours", tab)
            contour_toggle.setChecked(True)
            # All three tabs share ONE contract: same concept, three
            # renderings, told apart by `instance_path`.
            apply_help_tooltip(contour_toggle, _HELP["correlation_contours"])
            contour_toggle.toggled.connect(plot.set_show_contours)
            host = PopOutHost(
                plot,
                title=f"{correlation_type.upper()} correlations",
                settings_id=f"quantum.correlation_{correlation_type}",
                settings=self._settings,
                parent=tab,
            )
            # Stretch, not a real QSplitter: `table`, `contour_toggle` and
            # `host` all stay tab's own DIRECT children, which is what
            # `_content_of` requires (see its docstring -- a dict keyed by
            # a QWidget corrupted the heap once already; nesting an
            # extra container here would just be a different way of
            # breaking the same invariant, since `host` would no longer
            # be discoverable at `tab.children()`). The table is the
            # lookup reference; the plot is what the zoom/pan work above
            # exists for -- roughly a quarter/three-quarters split, not
            # equal halves. A user-draggable split was the plan's first
            # idea, but it costs exactly this invariant for a panel that
            # already crashed once over it.
            tab_layout.addWidget(table, 1)
            tab_layout.addWidget(contour_toggle, 0)
            tab_layout.addWidget(host, 3)
            self._correlation_tabs.addTab(tab, correlation_type.upper())
            tab_index = self._correlation_tabs.indexOf(tab)
            self._tab_status_titles[tab_index] = correlation_type.upper()
            self._tab_status_keys[tab_index] = "spectrum"
            self._tab_help_topics[tab_index] = "2d-correlation"
            self._correlation_tables[correlation_type] = table
            self._correlation_plots[correlation_type] = plot
            # Bidirectional, the same shape `NmrViewWidget` already uses
            # for the 1D spectrum: a table row selects its peak, a peak
            # click selects its row -- both through the (atom_a, atom_b)
            # pair, never coordinates or row position.
            table.itemSelectionChanged.connect(self._on_correlation_row_selected)
            plot.peak_selected.connect(self._on_correlation_peak_selected)
            # Painted into the plot rather than added as a placeholder
            # widget -- see `ui/widgets/empty_state.py` for the heap
            # corruption that a placeholder in a content-bearing tab
            # caused, measured 5/5. The message also lands exactly where
            # the peaks would be, which is where somebody is looking.
            plot.set_empty_message(
                f"No {correlation_type.upper()} cross peaks yet.\n"
                "Run an NMR calculation."
            )

        # LAST, deliberately -- "results outrank the log" is an ordering
        # claim as much as a layout one, and every existing tab keeps its
        # index so nothing shifts under somebody who has learned where
        # things are.
        # "ORCA Log," not "Log" -- the application's own bottom Console is
        # also a log, and a tab reading just "Log" inside a QC results dock
        # reads as a duplicate of it rather than what it actually is: this
        # one job's raw ORCA stdout.
        self._correlation_tabs.addTab(self._output_log, "ORCA Log")
        self._tab_help_topics[self._correlation_tabs.indexOf(self._output_log)] = "quantum-chemistry"

    def _build_form_and_layout(self) -> None:
        """The run form and the vertical layout under it.

        `form` is built HERE rather than in its own step because it
        is a local read by `layout.addLayout(form)`.
        """
        # Two distinct sections, not one form that happens to have a
        # history control at the bottom: selecting an old run in "Currently
        # viewing" must never read as having changed what "Calculation to
        # run" is about to submit -- the exact ambiguity a single unlabelled
        # block would invite.
        calculation_heading = QLabel("Calculation to run", self)
        calculation_heading.setStyleSheet("font-weight: bold;")

        form = QFormLayout()
        form.addRow("Molecule:", self._molecule_combo)
        form.addRow("Calculation:", self._calc_type_combo)
        form.addRow("Charge:", self._charge_spin)
        form.addRow("Multiplicity:", self._multiplicity_spin)
        form.addRow("Method/basis:", self._method_combo)
        form.addRow("Solvent (CPCM):", self._solvent_combo)
        form.addRow("CPU cores:", self._cores_spin)
        form.addRow("", self._boltzmann_check)

        # Used to be five buttons in this row -- measured under `offscreen`:
        # 218 + 350 + 434 + 80 + 86 = 1168 px, more than the whole panel is
        # ever given, which is why this was a `flow_row` in the first
        # place (see git history for the measurement). The three setup-
        # once buttons are now behind `_more_button`'s menu, so this row is
        # just "More", Run, Cancel -- narrow enough for a plain
        # `QHBoxLayout`, but left as `flow_row` anyway: a docked panel can
        # still be narrower than these three at some DPI, and `flow_row`
        # costs nothing extra when a row already fits on one line.
        run_row = flow_row(self)
        run_row.layout().addWidget(self._more_button)
        run_row.layout().addWidget(self._run_button)
        run_row.layout().addWidget(self._cancel_button)

        # "Currently viewing," separate from the form above it ("calculation
        # to run"): selecting a run here must never look like it changed
        # what the next Run press will submit, and it does not.
        viewing_heading = QLabel("Currently viewing", self)
        viewing_heading.setStyleSheet("font-weight: bold;")

        runs_row = flow_row(self)
        runs_row.layout().addWidget(QLabel("Runs:", self))
        runs_row.layout().addWidget(self._runs_combo)
        runs_row.layout().addWidget(self._delete_run_button)
        runs_row.layout().addWidget(self._compare_runs_button)

        # THE RESULTS COME FIRST, AND THE LOG IS COLLAPSED UNDERNEATH.
        #
        # `_output_log` is a `QPlainTextEdit`, whose default Expanding
        # policy took the largest share of the panel -- so a finished
        # calculation showed a wall of scrolling SCF iterations above a
        # cramped band of the numbers somebody actually ran it for. Alex,
        # reading a completed job: "completed calculations should
        # emphasize results rather than console output".
        #
        # It expands by itself while a job runs, because then the log IS
        # the interesting thing -- there is nothing else yet, and a silent
        # panel during a ten-minute ORCA run reads as a hang.

        layout = QVBoxLayout(self)
        layout.addWidget(calculation_heading)
        layout.addLayout(form)
        layout.addWidget(run_row)
        layout.addWidget(viewing_heading)
        layout.addWidget(runs_row)
        layout.addWidget(self._status_label)
        layout.addWidget(self._results_label)
        layout.addWidget(self._spectrum_note_label)
        layout.addWidget(self._spectrum_table)
        # Above the tab strip, not inside any one tab -- see
        # `_tab_help_button`'s own comment for why one affordance rather
        # than eight.
        help_row = flow_row(self)
        help_row.layout().addWidget(self._tab_help_button)
        layout.addWidget(help_row)
        layout.addWidget(self._correlation_tabs)

        self._reset_empty_states()

    def _subscribe_to_events(self, event_bus: EventBus) -> None:
        """The seven events this panel listens for."""
        event_bus.subscribe(QuantumChemistryJobStateChanged, self._on_job_state_changed)
        event_bus.subscribe(QuantumChemistryResultReady, self._on_result_ready)
        event_bus.subscribe(SpectrumComputed, self._on_spectrum_computed)
        event_bus.subscribe(QmSurfaceComputed, self._on_qm_surface_computed)
        event_bus.subscribe(NmrReferenceCalibrated, self._on_reference_calibrated)
        event_bus.subscribe(NmrScalingCalibrated, self._on_scaling_calibrated)
        event_bus.subscribe(MoleculeSelected, self._on_molecule_selected)

    def set_project(self, project: ProjectModel | None) -> None:
        self._project = project
        self._refresh_molecule_combo()
        self._refresh_active_run()

    def _refresh_molecule_combo(self) -> None:
        molecules = self._project.molecules if self._project is not None else []
        repopulate(self._molecule_combo, [(m.display_name, m.uuid) for m in molecules])

    def _on_molecule_selected(self, event: MoleculeSelected) -> None:
        """Follow the project tree, like the editor, the 3D viewer and the
        Property panel already do.

        Without this the panel silently computed on whichever molecule the
        combo happened to land on, which is how a project with two
        identically-named molecules turned into "ORCA refuses to run even
        though the 3D viewer is showing ten conformers".
        """
        select(self._molecule_combo, event.molecule_uuid)

    def _current_molecule(self):
        if self._project is None:
            return None
        molecule_uuid = self._molecule_combo.currentData()
        if molecule_uuid is None:
            return None
        return self._project.find_molecule(molecule_uuid)

    def _on_molecule_changed(self, _index: int) -> None:
        molecule = self._current_molecule()
        if molecule is not None and molecule.molblock:
            self._charge_spin.setValue(self._chemistry_engine.formal_charge(molecule))
        self._refresh_active_run()

    def _refresh_active_run(self) -> None:
        """Populate the Runs combo for the selected molecule and show its
        newest entry, if this session's `ResultStoreService` has history
        for it.

        This is the panel's only route to "what was already calculated
        here" outside a live job: `_pending_molecule_uuid` is `None` right
        after a molecule selection or a project load, which is exactly
        when a user expects to see a prior result reappear rather than a
        blank panel.
        """
        self._active_run = None
        molecule = self._current_molecule()
        runs = (
            self._result_store_service.qc_runs.runs_for(molecule.uuid)
            if molecule is not None and self._result_store_service is not None
            else []
        )
        self._runs_combo.blockSignals(True)
        self._runs_combo.clear()
        for run in runs:
            self._runs_combo.addItem(self._run_label(run), run.run_id)
        self._runs_combo.blockSignals(False)
        self._set_runs_controls_enabled(bool(runs))
        if not runs:
            self._clear_run_display()
            return
        self._runs_combo.setCurrentIndex(0)
        self._render_run(runs[0])

    def _run_label(self, run) -> str:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(run.started_at))
        calc_label = next(
            (label for label, key in CALC_TYPE_LABELS.items() if key == run.calc_type), run.calc_type
        )
        return f"{calc_label} · {run.method_basis} · {when}"

    def _set_runs_controls_enabled(self, enabled: bool) -> None:
        self._runs_combo.setEnabled(enabled)
        self._delete_run_button.setEnabled(enabled)
        self._compare_runs_button.setEnabled(enabled)

    def _on_runs_combo_changed(self, index: int) -> None:
        if index < 0 or self._result_store_service is None:
            return
        run_id = self._runs_combo.itemData(index)
        if run_id is None:
            return
        run = self._result_store_service.qc_runs.get(run_id)
        if run is not None:
            self._render_run(run)

    def _on_delete_run_clicked(self) -> None:
        if self._active_run is None or self._result_store_service is None:
            return
        # A project-history delete only -- the underlying `result_cache`
        # wavefunction this run's `surface_cache_key` points at is
        # independently managed and NOT purged: it may still be reusable
        # by a later identical calculation, and this button has no way to
        # know that and should not guess.
        choice = QMessageBox.question(
            self,
            "Delete run",
            f"Delete \"{self._run_label(self._active_run)}\" from this project's history?\n\n"
            "This only removes the project record -- a reusable wavefunction it left "
            "in the quantum-chemistry cache is not affected.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        self._result_store_service.qc_runs.delete(self._active_run.run_id)
        self._refresh_active_run()

    def _on_compare_runs_clicked(self) -> None:
        if self._active_run is None or self._result_store_service is None:
            return
        if self._active_run.results.get("spectrum") is None:
            QMessageBox.information(
                self, "Cannot compare", "The active run has no NMR spectrum to compare."
            )
            return
        molecule = self._current_molecule()
        if molecule is None:
            return
        candidates = [
            run
            for run in self._result_store_service.qc_runs.runs_for(molecule.uuid)
            if run.run_id != self._active_run.run_id and run.results.get("spectrum") is not None
        ]
        if not candidates:
            QMessageBox.information(
                self,
                "Cannot compare",
                "No other retained run for this molecule has an NMR spectrum to compare against.",
            )
            return
        labels = [self._run_label(run) for run in candidates]
        choice, ok = QInputDialog.getItem(
            self, "Compare NMR Shifts", "Compare the active run against:", labels, 0, False
        )
        if not ok:
            return
        self._open_run_comparison(self._active_run, candidates[labels.index(choice)])

    def _open_run_comparison(self, run_a, run_b) -> None:
        """Compares two runs' NMR shifts, atom by atom, through the exact
        same `domain.compare`/`CompareResultsDialog` the Atom Inspector's
        "Compare with..." already uses -- rather than a QC-specific
        comparison widget. `compare()` itself refuses (with a reason shown
        to the user) when the two runs' atom numbering cannot be safely
        lined up, e.g. a structural edit between them changed the
        fingerprint; this method does not re-implement that check.
        """
        molecule = self._current_molecule()
        if molecule is None:
            return
        compared = []
        for run in (run_a, run_b):
            spectrum = run.results["spectrum"]
            dataset = PerAtomDataset(
                property_id="nmr_shift",
                name=f"NMR shift ({run.method_basis}, {self._run_label(run)})",
                units=spectrum.units,
                # The method/basis, not `run.provider` ("orca" for every
                # ORCA run regardless of method) -- `compare()`'s
                # same_result_as() uses this plus `property_id` to refuse
                # "the same result twice", and two runs at different
                # method/basis are NOT the same result. Confirmed live: two
                # NMR runs both labelled method="orca" were refused as
                # duplicates even though they were B3LYP and PBE0.
                method=run.method_basis,
                molecule_uuid=run.molecule_uuid,
                values=dict(spectrum.values),
            )
            compared.append(ComparedResult(dataset, run.input_fingerprint, run.calculation_input))
        outcome = compare(compared)
        if isinstance(outcome, CompareRefusal):
            QMessageBox.information(self, "Cannot compare", outcome.message)
            return
        symbols = dict(run_a.results["spectrum"].elements)
        dialog = CompareResultsDialog(outcome, symbols, molecule.display_name, parent=self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.show()

    def _clear_run_display(self) -> None:
        self._reset_empty_states()
        self._results_label.setText("")
        self._display_mol = None
        self._clear_tab_status_indicators()

    def _clear_tab_status_indicators(self) -> None:
        for index, title in self._tab_status_titles.items():
            self._correlation_tabs.setTabText(index, title)

    def _update_tab_status_indicators(self, run) -> None:
        """A cheap per-tab glyph for the active run's `output_status`, so
        checking why one of eight tabs is empty does not need clicking
        through all eight -- AVAILABLE/NOT_PRODUCED/FAILED, read off the
        run record itself rather than from "whatever this tab's widget
        still happens to contain" (which is exactly the kind of leftover
        content `_reset_empty_states` exists to prevent)."""
        glyph = {"available": "✓", "not_produced": "–", "failed": "✗", "inapplicable": "–"}
        for index, title in self._tab_status_titles.items():
            key = self._tab_status_keys.get(index)
            if key == "__surface_cache_key":
                mark = glyph["available"] if run.surface_cache_key else glyph["not_produced"]
            else:
                status = run.output_status.get(key)
                mark = glyph.get(status.value) if status is not None else None
            self._correlation_tabs.setTabText(index, f"{title} {mark}" if mark else title)

    def _render_run(self, run) -> None:
        """Repaint the panel from a stored `QuantumChemistryRun`, entirely
        locally.

        **MUST NEVER PUBLISH ONTO THE SHARED EVENT BUS.** PropertyPanel
        treats `DescriptorComputed` as "the current/latest value" --
        broadcasting an older run's numbers that way would make Results
        silently show stale values while this panel displays history. The
        live/newest-result path (`main_window._on_quantum_chemistry_result_ready`
        republishing `DescriptorComputed`) is unaffected and keeps working
        exactly as it always has.

        Reuses the exact rendering `_on_result_ready`/`_on_spectrum_computed`
        already do for a live job (`_render_nmr_spectrum`, `_update_ir_view`,
        `_update_surfaces_view`) rather than a second implementation of the
        same tables/plots, which is what let the NMR/IR tabs drift out of
        sync with each other in the first place.
        """
        self._active_run = run
        self._reset_empty_states()
        self._update_tab_status_indicators(run)
        self._display_mol = (
            self._chemistry_engine.mol_from_molblock(run.input_molblock)
            if run.input_molblock
            else None
        )
        # `input_molblock` is the 3D structure actually sent to ORCA (see
        # `QuantumChemistryService.request_calculation`), the same thing
        # `_pending_conformer_molblock` holds for a live job -- so the 3D
        # panes (NMR, IR animation, Surfaces) that already read it work
        # unchanged. There is no separate 2D depiction recorded for a
        # historical run, so `_pending_molblock` (the flat drawing) is left
        # empty; `NmrViewWidget` falls back to deriving one from the 3D
        # structure when it has no 2D molblock to draw instead.
        self._pending_molblock = ""
        self._pending_conformer_molblock = run.input_molblock
        # THIS run's own optimized geometry, not "whatever the molecule's
        # latest optimization happens to be" -- a later run at a different
        # method could have added another conformer since. Resolved by id
        # rather than trusting conformer LIST POSITION, which is exactly
        # the trap `canonical_conformer()` exists to avoid for a live job.
        self._optimized_conformer_molblock = ""
        molecule = self._current_molecule()
        if molecule is not None and run.output_conformer_id:
            for conformer in molecule.conformers:
                if conformer.conformer_id == run.output_conformer_id:
                    self._optimized_conformer_molblock = conformer.molblock
                    break

        descriptors = run.results.get("descriptors") or []
        lines = [f"{d.name}: {d.value:.6f} {d.units}" for d in descriptors]
        self._results_label.setText("\n".join(lines))

        spectrum = run.results.get("spectrum")
        if spectrum is not None:
            self._render_nmr_spectrum(spectrum)

        vibrational = run.results.get("vibrational_spectrum")
        if vibrational is not None:
            self._update_ir_view(vibrational)

        self._update_surfaces_view()

    def _on_configure_clicked(self) -> None:
        dialog = SettingsDialog(self._settings, self, section=EXTERNAL_TOOLS, tool="orca")
        dialog.exec()

    def _on_tab_help_clicked(self) -> None:
        topic = self._tab_help_topics.get(self._correlation_tabs.currentIndex(), "quantum-chemistry")
        self._open_help_topic(topic)

    def _open_help_topic(self, topic: str) -> None:
        """`open_help`'s contract, `CalculatorVisibilityPage.show_help_for`'s
        exact shape: a caller may supply a callback that opens the app-wide
        help window (so this panel's button and F1 land on the same
        window); without one, a private `HelpDialog` is opened instead, so
        nothing here depends on living inside a `MainWindow`."""
        if self._open_help is not None:
            self._open_help(topic)
            return
        from openchem.ui.dialogs.help_dialog import HelpDialog

        if self._help_window is None:
            self._help_window = HelpDialog(self, topic)
        self._help_window.show_topic(topic)
        self._help_window.show()
        self._help_window.raise_()
        self._help_window.activateWindow()

    def _on_run_clicked(self) -> None:
        molecule = self._current_molecule()
        if molecule is None or not molecule.molblock:
            self._status_label.setText("Select a molecule with a structure first.")
            return
        if not molecule.conformers:
            # Confirmed live against a real ORCA install: molecule.molblock
            # alone (from SMILES import or the 2D editor) carries only
            # heavy atoms -- hydrogens stay implicit, same as virtually
            # every MOL/SDF representation -- so building an ORCA input
            # straight from it silently sends an incomplete structure (a
            # bare oxygen atom for water, not H2O) rather than failing
            # loudly. RDKitConformerProvider._embed_one already calls
            # Chem.AddHs() before embedding, so requiring a real conformer
            # here guarantees explicit hydrogens with real 3D positions,
            # not just a flatter/lower-quality geometry.
            self._status_label.setText(
                "Generate one with Structure ▸ Generate Conformers... first -- "
                "quantum chemistry needs explicit hydrogens with real 3D positions, which "
                "the 2D editor's structure alone doesn't have."
            )
            return

        # THROUGH THE RESOLVER, so the molecule ORCA is handed and the identity
        # stamped on its spectra come from one resolution (the canonical
        # conformer, not `conformers[0]`, which agrees only while the list
        # happens to be energy-sorted).
        resolved = resolve_calculation_input(self._chemistry_engine, molecule, GEOMETRY)
        if resolved.used != GEOMETRY:
            # The resolver fell back to the DRAWING -- the conformer would not
            # parse or is flat. Refused, never run: the drawing carries no
            # hydrogens, and ORCA would compute a plausible-looking answer for
            # a different molecule (see the conformer check above).
            self._status_label.setText(
                "The selected molecule's conformer has no usable 3D coordinates. Regenerate "
                "it with Structure ▸ Generate Conformers... first."
            )
            return
        mol = resolved.mol
        molblock = canonical_conformer(molecule).molblock

        calc_type = CALC_TYPE_LABELS[self._calc_type_combo.currentText()]
        method_basis = self._effective_method_basis()
        if not method_basis:
            self._status_label.setText("Enter a method/basis (e.g. 'B3LYP def2-SVP').")
            return

        boltzmann = self._boltzmann_check.isChecked() and len(molecule.conformers) > 1
        ensemble = None
        if boltzmann:
            # Resolved BEFORE the panel commits to a run, so a refusal leaves
            # the controls as they were rather than disabled with no job.
            try:
                ensemble = resolve_ensemble(self._chemistry_engine, molecule)
            except ValueError as exc:
                self._status_label.setText(f"Cannot average over the conformers: {exc}")
                return

        if calc_type == "led" and not self._confirm_led_cost(self, mol):
            return

        self._pending_molecule_uuid = molecule.uuid
        self._pending_mol = mol
        self._pending_molblock = molecule.molblock
        self._pending_conformer_molblock = molblock
        self._optimized_conformer_molblock = ""
        self._run_button.setEnabled(False)
        self._cancel_button.setEnabled(True)
        self._output_log.clear()
        self._results_label.setText("")
        self._spectrum_table.setRowCount(0)
        self._spectrum_table.setVisible(False)
        self._spectrum_note_label.setVisible(False)
        self._correlation_tabs.setVisible(False)
        # Back to placeholders. A second job of a different type must not
        # leave the first job's tables sitting under the new job's heading,
        # which would be worse than a blank tab -- it would be wrong.
        self._reset_empty_states()
        self._status_label.setText("queued")

        if ensemble is not None:
            self._quantum_chemistry_service.request_boltzmann_nmr(
                mols=list(ensemble.mols),
                molecule_uuid=molecule.uuid,
                calc_type=calc_type,
                charge=self._charge_spin.value(),
                multiplicity=self._multiplicity_spin.value(),
                method_basis=method_basis,
                input_fingerprint=ensemble.fingerprint,
                calculation_input=ENSEMBLE,
            )
            return

        self._quantum_chemistry_service.request_calculation(
            mol=mol,
            molecule_uuid=molecule.uuid,
            calc_type=calc_type,
            charge=self._charge_spin.value(),
            multiplicity=self._multiplicity_spin.value(),
            method_basis=method_basis,
            input_fingerprint=resolved.fingerprint,
            calculation_input=GEOMETRY,
        )

    def _on_cancel_clicked(self) -> None:
        if self._pending_molecule_uuid is not None:
            self._quantum_chemistry_service.cancel(self._pending_molecule_uuid)

    def _effective_method_basis(self) -> str:
        """The full ORCA `!` header body -- method/basis plus the CPCM
        solvent keyword when one is selected.

        Both Run and Calibrate go through here, and they must: the TMS
        reference is cached against this exact string, so a reference
        calibrated in chloroform would never be found by a job that built
        its header differently.
        """
        method_basis = self._method_combo.currentText().strip()
        if not method_basis:
            return ""
        solvent = self._solvent_combo.currentData()
        return f"{method_basis} CPCM({solvent})" if solvent else method_basis

    @staticmethod
    def _confirm_led_cost(parent, mol) -> bool:
        """Show what an LED job will cost BEFORE it starts. True to proceed.

        Before, not after, because the two ways this job goes wrong are both
        unrecoverable once it is running: it takes days, or it fills the
        scratch disk. Measured, benzene-water is the case that makes the
        second one real -- ten minutes and 1.9 GB, so a time-only warning
        would wave through the job most likely to fill a laptop.

        A structure that is not two species is refused here rather than at
        input-building time, so the message arrives as a dialog instead of a
        failed job in the log.

        A staticmethod taking `parent` explicitly, because the decision it
        makes is worth testing on its own and a Qt widget cannot be
        instantiated without its whole service container.

        The fragment count comes from the chem layer rather than from a
        local `Chem.GetMolFrags` call: `tests/test_layering.py` forbids a UI
        module importing RDKit, and caught the first version of this doing
        exactly that.
        """
        from openchem.chem.orca_led import estimate_led_cost_for

        estimate = estimate_led_cost_for(mol)
        if estimate.fragment_count != 2:
            QMessageBox.information(
                parent,
                "Two partners needed",
                "An interaction breakdown needs exactly two separate species — "
                "they are the fragments it decomposes the interaction between.\n\n"
                "Draw the two partners as separate molecules (a Lewis acid and "
                "its base, a hydrogen-bonded pair) rather than joined by a bond.",
            )
            return False
        if estimate.geometry_problem:
            # Refused, not warned. A live run of an overlapping pair produced
            # +40619 kcal/mol -- arithmetically correct, physically
            # meaningless, and indistinguishable from a real result once it
            # is just a number on the panel.
            QMessageBox.warning(
                parent, "This geometry cannot be decomposed", estimate.geometry_problem
            )
            return False

        if not estimate.should_warn:
            return True
        answer = QMessageBox.question(
            parent,
            "This calculation is expensive",
            f"{estimate.advice}\n\n"
            f"{estimate.atoms} atoms, {estimate.basis_functions} basis functions, "
            f"DLPNO-CCSD(T).\n\n"
            "The estimate is scaled from two measured jobs and is a guide to the "
            "order of the cost, not a prediction.\n\nStart it anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def select_calculation_type(self, calc_type: str) -> bool:
        """Choose a calculation by its type code ("nmr", "sp", ...), as a click on its
        Properties row does. Returns whether there was such a calculation, so the caller
        can say so instead of leaving the combo wherever it was.

        Selects only. Nothing runs: the person still presses Run here, with the charge,
        multiplicity and method they want.
        """
        for label, code in CALC_TYPE_LABELS.items():
            if code == calc_type:
                index = self._calc_type_combo.findText(label)
                if index >= 0:
                    self._calc_type_combo.setCurrentIndex(index)
                    return True
        return False

    def _on_cores_changed(self, value: int) -> None:
        self._settings.set("orca/cores", value)

    def _on_calc_type_changed(self, label: str) -> None:
        """Steers NMR runs onto an NMR-appropriate basis.

        Shielding depends on core electron density, which the general-purpose
        valence bases don't describe -- so the default preset is a poor choice
        for exactly the calculation whose point is shielding accuracy. Only
        moves off a preset the user hasn't customised: an edited or
        hand-typed method string is left alone.
        """
        if CALC_TYPE_LABELS.get(label) not in ("nmr", "nmr_coupling"):
            return
        if self._method_combo.currentText().strip() in METHOD_BASIS_PRESETS:
            self._method_combo.setCurrentText(NMR_METHOD_BASIS)

    def _on_calibrate_clicked(self) -> None:
        method_basis = self._effective_method_basis()
        if not method_basis:
            self._status_label.setText("Enter a method/basis before calibrating.")
            return
        self._calibrate_button.setEnabled(False)
        self._status_label.setText(f"Calibrating reference (TMS) for {method_basis!r} — this may take a while.")
        self._quantum_chemistry_service.request_reference_calibration(method_basis)

    def _on_scaling_calibrate_clicked(self) -> None:
        method_basis = self._effective_method_basis()
        if not method_basis:
            self._status_label.setText("Enter a method/basis before calibrating.")
            return
        self._scaling_button.setEnabled(False)
        self._status_label.setText(
            f"Calibrating scaling factors for {method_basis!r} across 11 reference compounds — "
            "this runs 11 ORCA jobs and will take a while."
        )
        self._quantum_chemistry_service.request_scaling_calibration(method_basis)

    def _on_scaling_calibrated(self, event: NmrScalingCalibrated) -> None:
        self._scaling_button.setEnabled(True)
        if not event.factors:
            self._status_label.setText(f"Scaling calibration failed: {event.error}")
            return
        # R^2 is shown, not hidden: a slope is only as good as the fit it
        # came from, and the user is about to trust every shift to it.
        summary = ", ".join(
            f"{element} R²={factors.r_squared:.4f} (n={factors.sample_count})"
            for element, factors in sorted(event.factors.items())
        )
        message = f"Scaling calibrated for {event.method_basis!r}: {summary}."
        if event.error:
            message += f" Not calibrated — {event.error}"
        self._status_label.setText(message)

    def _on_reference_calibrated(self, event: NmrReferenceCalibrated) -> None:
        self._calibrate_button.setEnabled(True)
        if event.error:
            self._status_label.setText(f"Reference calibration failed: {event.error}")
        else:
            elements = ", ".join(sorted(event.values))
            self._status_label.setText(f"Reference calibrated for {event.method_basis!r} ({elements}).")

    def _on_job_state_changed(self, event: QuantumChemistryJobStateChanged) -> None:
        if event.molecule_uuid != self._pending_molecule_uuid:
            return
        self._status_label.setText(event.state.value)
        if event.message:
            self._output_log.appendPlainText(event.message)
        if event.state.value == "running":
            # Shown and selected while there is nothing else yet: a panel
            # that sits silent through a ten-minute ORCA run reads as a
            # hang, and the log is the only evidence anything is happening.
            self._correlation_tabs.setVisible(True)
            self._correlation_tabs.setCurrentWidget(self._output_log)
        if event.state.value in ("completed", "failed"):
            self._run_button.setEnabled(True)
            self._cancel_button.setEnabled(False)
            if event.state.value == "failed":
                # Stay on the log: it is where the reason is, and every
                # other tab is empty for a job that produced nothing.
                #
                # On SUCCESS nothing is forced. The numbers land in
                # `_results_label`, which sits above the tabs and is always
                # visible, and each `_update_*` selects its own tab when it
                # has something to show -- yanking the user to a tab that
                # says "no NMR signals yet" after an ESP run would be worse
                # than leaving them where they were.
                self._correlation_tabs.setCurrentWidget(self._output_log)
            # Failed keeps it OPEN: the log is where the reason is, and
            # collapsing it would hide the one thing worth reading.

    def _on_result_ready(self, event: QuantumChemistryResultReady) -> None:
        if event.molecule_uuid != self._pending_molecule_uuid:
            return
        lines = [f"{d.name}: {d.value:.6f} {d.units}" for d in event.descriptors]
        if event.conformer is not None:
            lines.append("Optimized geometry added as a new conformer.")
            # Held for the IR view, which must animate about the optimised
            # geometry. `QuantumChemistryResultReady` is published before
            # the vibrational `SpectrumComputed` from the same job
            # (`_finish_calculation_job` parses descriptors first), so by
            # the time the spectrum arrives this is already set.
            self._optimized_conformer_molblock = event.conformer.molblock
        self._results_label.setText("\n".join(lines))
        # After the conformer is recorded, so the surfaces are drawn on the
        # optimised geometry when there is one.
        self._update_surfaces_view()

    def _on_spectrum_computed(self, event: SpectrumComputed) -> None:
        spectrum = event.spectrum
        if spectrum.molecule_uuid != self._pending_molecule_uuid:
            return
        # A VIBRATIONAL SPECTRUM MUST NOT REACH THE NMR PATH BELOW, and
        # this branch is the whole reason the method dispatches at all.
        # `SpectrumComputed` carries every spectrum type, and everything
        # after this point reads `spectrum.values` -- which
        # `VibrationalSpectrumResult` documents as DELIBERATELY EMPTY,
        # because an IR peak belongs to a normal mode rather than to an
        # atom. Falling through produced no error and no empty state: an
        # NMR table with zero rows, a "1D Signals" view built from no
        # signals, and three correlation tabs computed over nothing, all
        # presented as a successful result.
        if isinstance(spectrum, VibrationalSpectrumResult):
            self._update_ir_view(spectrum)
            return
        # This IS the live job's own mol -- `_update_correlation_tabs`/
        # `_update_hybrid_tab` read `_display_mol`, never `_pending_mol`
        # directly, so the same assignment covers both a live result and
        # (in `_render_run`) a historical one. Set only on the NMR path:
        # IR has no use for it.
        self._display_mol = self._pending_mol
        self._render_nmr_spectrum(spectrum)

    def _render_nmr_spectrum(self, spectrum: SpectrumResult) -> None:
        """The NMR side of `_on_spectrum_computed` -- factored out so
        `_render_run` can repaint a HISTORICAL spectrum through the exact
        same code, rather than a second implementation that could drift
        from what a live result does. Reads `self._display_mol` (via
        `_update_correlation_tabs`/`_update_hybrid_tab`), never
        `self._pending_mol` -- the caller is responsible for setting it
        first, live or historical.
        """
        referencing = (
            spectrum.provenance.parameters.get("referencing") if spectrum.provenance else None
        )
        if spectrum.spectrum_type == "nmr_raw_shielding":
            note = _RAW_SHIELDING_NOTE
        elif referencing == "empirical_linear_scaling":
            note = _SCALED_NOTE
        else:
            note = _CALIBRATED_NOTE
        coupling_error = getattr(spectrum, "coupling_error", None)
        if coupling_error:
            note = f"{note}\n{_COUPLING_FAILED_NOTE}"
        self._spectrum_note_label.setText(note)
        self._spectrum_note_label.setVisible(True)
        self._spectrum_table.setVisible(True)
        atom_indices = sorted(spectrum.values)
        self._spectrum_table.setRowCount(len(atom_indices))
        for row, atom_index in enumerate(atom_indices):
            values = (
                str(atom_index),
                spectrum.elements.get(atom_index, ""),
                f"{spectrum.values[atom_index]:.3f}",
            )
            for col, text in enumerate(values):
                self._spectrum_table.setItem(row, col, QTableWidgetItem(text))

        self._update_nmr_view(spectrum)
        self._update_correlation_tabs(spectrum)
        self._update_hybrid_tab(spectrum)

    def _update_surfaces_view(self) -> None:
        """Shows the point-charge ESP beside the ab initio one.

        Populated on any completed calculation, not only a frequency job:
        the wavefunction a single-point leaves behind is enough to plot
        every surface, so requiring an `opt_freq` would withhold the
        cheapest path to the most expensive picture.
        """
        molblock = self._optimized_conformer_molblock or self._pending_conformer_molblock
        if not molblock or self._qm_surface_service is None:
            return
        if self._surfaces_view is None:
            self._surfaces_view = EspCompareWidget(
                self._chemistry_engine,
                self._qm_surface_service,
                parent=self._surfaces_tab,
            )
            self._surfaces_layout.addWidget(
                PopOutHost(
                    self._surfaces_view,
                    title="Surfaces",
                    settings_id="quantum.surfaces",
                    settings=self._settings,
                    parent=self._surfaces_tab,
                )
            )
        self._surfaces_view.set_molecule(self._pending_molecule_uuid or "", molblock)
        self._fill_tab(self._surfaces_tab)
        self._correlation_tabs.setVisible(True)

    # --- empty states --------------------------------------------------------

    def _add_empty_state(
        self,
        tab: QWidget,
        layout: QVBoxLayout,
        headline: str,
        action: str,
    ) -> None:
        """Give `tab` a placeholder standing in for its content.

        **NOTHING IS STORED.** The placeholder and the content it replaces
        are both found through Qt's own parent/child tree whenever they
        are needed -- see `_content_of` for why, which is a heap
        corruption this cost three full suite runs to pin down.

        The content is "every direct child of the tab that is not the
        placeholder", which is exactly right here and needs no list: an
        empty `QTableWidget` still draws its header strip, so a populated
        header sitting above the words "nothing here yet" is the failure
        this hides. The three deferred tabs (1D Signals, IR, Surfaces)
        simply have no content yet, and the same rule gives an empty list.
        """
        layout.addWidget(empty_state(headline, action, tab))

    def empty_message_for_tab(self, index: int) -> str:
        """What this tab tells a reader when it has nothing to show.

        **Derived from the widgets, never from a list kept alongside
        them.** A tab that displays nothing must be able to fail the guard
        in `tests/test_empty_states.py`, and it cannot if the guard reads a
        registry of messages somebody remembered to update -- the same
        direction that let two panels ship with no help topic.

        Three mechanisms, because one size did not fit:

        - a placeholder label, for the three deferred tabs whose content
          does not exist until a result arrives;
        - `_hybrid_summary_label`, which already existed to carry notes;
        - text painted inside `NmrCorrelationPlotWidget`, for the
          correlation tabs.

        The split is not stylistic. A placeholder WIDGET added to a tab
        that already holds content widgets corrupted the heap during the
        teardown collect, 5 runs out of 5 -- see
        `ui/widgets/empty_state.py`. So only the genuinely-empty tabs get
        one, and the rest say it through a widget that is already there.
        """
        tab = self._correlation_tabs.widget(index)
        if tab is None:
            return ""
        for child in tab.findChildren(QWidget):
            if is_empty_state(child):
                return empty_state_text(child)
        for plot in tab.findChildren(NmrCorrelationPlotWidget):
            if plot.empty_message():
                return plot.empty_message()
        if self._hybrid_summary_label in tab.findChildren(QLabel):
            return self._hybrid_summary_label.text()
        if tab is self._output_log:
            return self._output_log.placeholderText()
        return ""

    @staticmethod
    def _content_of(tab: QWidget) -> tuple[QWidget | None, list[QWidget]]:
        """This tab's placeholder, and the widgets it stands in for.

        DISCOVERED, never remembered, and that distinction is load-bearing.

        The first version kept `dict[QWidget, tuple[EmptyState, ...]]` on
        the panel. **That crashed the suite with a Windows heap corruption
        (0xc0000374), deterministically, 3 runs out of 3**, inside the
        teardown `gc.collect()` -- and NOT in a test of this panel, but in
        `test_main_window_conformers.py`, five hundred tests after the
        window that built it went away.

        A dict keyed by a QWidget has to HASH that widget, and PySide
        hashes on the underlying C++ pointer. Qt deletes a parent's
        children C++-side, so by collection time those keys address freed
        memory. Reading it to hash or to decref is the corruption.

        The rule for anything holding Qt objects in this codebase: keep
        them where Qt already keeps them. The parent/child tree is valid
        for exactly as long as the widgets are, which a Python container
        cannot promise.
        """
        state: QWidget | None = None
        content: list[QWidget] = []
        for child in tab.children():
            if not isinstance(child, QWidget):
                continue  # the layout itself is a QObject, not a QWidget
            if is_empty_state(child):
                state = child
            else:
                content.append(child)
        return state, content

    def _fill_tab(self, tab: QWidget) -> None:
        """This tab now has real content: retire its placeholder."""
        state, content = self._content_of(tab)
        if state is None:
            return
        state.setVisible(False)
        for widget in content:
            widget.setVisible(True)

    def _reset_empty_states(self) -> None:
        """Back to placeholders, for a fresh job.

        Walks the tab widget rather than a stored collection, for the
        reason in `_content_of`.

        **A DETACHED VIEW IS BROUGHT HOME FIRST, and this is the only
        place that does it.** Hiding a `PopOutHost` does not close the
        window its content is sitting in, so without this a new job would
        blank the tab while a window on another monitor went on showing
        the PREVIOUS run's surface, with nothing anywhere saying it was
        stale.

        A new job is a SEMANTIC reset, which is what distinguishes it from
        the four ways of merely looking away -- switching dock, switching
        tab, hiding the dock, floating it. Those must NOT return anything,
        which is why `PopOutHost` has no `hideEvent` hook: a tab page
        receives hide events on every tab switch.
        """
        for index in range(self._correlation_tabs.count()):
            tab = self._correlation_tabs.widget(index)
            for host in tab.findChildren(PopOutHost):
                host.return_home()
            state, content = self._content_of(tab)
            if state is None:
                continue
            state.setVisible(True)
            for widget in content:
                widget.setVisible(False)
        # HSQC/HMBC/COSY and Hybrid are NOT covered by the walk above --
        # each paints its own "no data yet" message directly into its
        # content widgets rather than using a placeholder `_content_of`
        # can discover (`_build_tabs`'s comment on why: a placeholder
        # WIDGET in a content-bearing tab caused a heap corruption,
        # measured 5/5). Left unhandled, a job of a different calc_type --
        # e.g. IR after NMR -- reached `_on_spectrum_computed`'s
        # `VibrationalSpectrumResult` branch, which returns before ever
        # touching these tabs, so the PREVIOUS run's HSQC/HMBC/COSY rows
        # and cross peaks (and the Hybrid table) went on sitting there
        # under the new run's heading. Confirmed live and by a targeted
        # test before this fix.
        for correlation_type in self._correlation_tables:
            self._correlation_tables[correlation_type].setRowCount(0)
            self._correlation_plots[correlation_type].set_peaks([])
            # A zoom window -- or a peak selection -- from whatever was on
            # screen before must not carry over onto a different run's or
            # molecule's data range.
            self._correlation_plots[correlation_type].reset_view()
            self._correlation_plots[correlation_type].set_highlighted_pair(None, None)
        self._hybrid_table.setRowCount(0)
        self._hybrid_summary_label.setText(_HYBRID_UNAVAILABLE_NOTE)

    def _on_qm_surface_computed(self, event) -> None:
        if self._surfaces_view is None:
            return
        self._surfaces_view.on_surface_computed(
            event.molecule_uuid, event.field, event.error
        )

    def _update_ir_view(self, spectrum: VibrationalSpectrumResult) -> None:
        """Populates the IR tab, built on first result for the same reason
        the 1D NMR view is: it owns a `QWebEngineView` for its 3D pane,
        which is expensive to build for a user who never runs a frequency
        job. The tab itself exists from the start so tab order never
        shifts under the user."""
        if self._ir_view is None:
            self._ir_view = IrViewWidget(self._chemistry_engine, parent=self._ir_view_tab)
            self._ir_view_layout.addWidget(
                PopOutHost(
                    self._ir_view,
                    title="IR spectrum",
                    settings_id="quantum.ir_spectrum",
                    settings=self._settings,
                    parent=self._ir_view_tab,
                )
            )
        # The OPTIMISED conformer, not the submitted structure: an
        # `opt_freq` optimises first and the modes describe motion about
        # the result. `_pending_conformer_molblock` is what was sent, so
        # the optimised geometry published by the same job is preferred
        # when it arrived.
        self._ir_view.set_spectrum(
            spectrum, self._optimized_conformer_molblock or self._pending_conformer_molblock or ""
        )
        self._fill_tab(self._ir_view_tab)
        self._correlation_tabs.setVisible(True)
        self._correlation_tabs.setCurrentWidget(self._ir_view_tab)

    def _update_nmr_view(self, spectrum: SpectrumResult) -> None:
        """Populates the 1D signal view -- the same `NmrViewWidget` the
        Property Panel opens for the empirical estimator, so a real ORCA
        result and a SMARTS estimate are read the same way."""
        if not self._pending_molblock:
            return
        if self._nmr_view is None:
            self._nmr_view = NmrViewWidget(self._chemistry_engine, parent=self._nmr_view_tab)
            self._nmr_view_layout.addWidget(
                PopOutHost(
                    self._nmr_view,
                    title="NMR signals",
                    settings_id="quantum.nmr_signals",
                    settings=self._settings,
                    parent=self._nmr_view_tab,
                )
            )
        self._nmr_view.set_spectrum(
            self._pending_molblock, spectrum, self._pending_conformer_molblock or None
        )
        self._fill_tab(self._nmr_view_tab)
        self._correlation_tabs.setVisible(True)

    def _update_correlation_tabs(self, spectrum: SpectrumResult) -> None:
        mol = self._display_mol
        if mol is None:
            return
        # NMRSpectrumResult.couplings (Phase 22, "NMR + Spin-Spin Coupling"
        # calc_type only) -- getattr since the base SpectrumResult type
        # this method is annotated with doesn't have the field.
        real_couplings: dict[tuple[int, int], float] = getattr(spectrum, "couplings", None) or {}
        for correlation_type, compute_fn, x_label, y_label in _CORRELATION_SPECS:
            cross_peaks = compute_fn(mol, spectrum.values)
            if real_couplings:
                cross_peaks = [
                    dataclasses.replace(
                        cp, coupling_hz=real_couplings.get((min(cp.atom_a, cp.atom_b), max(cp.atom_a, cp.atom_b)))
                    )
                    for cp in cross_peaks
                ]
            self._populate_correlation_tab(correlation_type, cross_peaks, spectrum, x_label, y_label)
        self._correlation_tabs.setVisible(True)

    def _update_hybrid_tab(self, spectrum: SpectrumResult) -> None:
        """Merges this calculation with the database lookup, per atom.

        Runs only against an empirically scaled spectrum. A raw or
        TMS-only one is refused rather than merged: the database's values
        are measured ppm, and TMS referencing removes an offset without
        removing the scale error, so splicing the two would produce a
        step in the spectrum that reads as chemistry.
        """
        from openchem.chem import nmr_database, nmr_hybrid
        from openchem.domain.nmr import ScalingFactors

        mol = self._display_mol
        parameters = (spectrum.provenance.parameters if spectrum.provenance else {}) or {}
        if mol is None or parameters.get("referencing") != "empirical_linear_scaling":
            self._hybrid_summary_label.setText(_HYBRID_UNAVAILABLE_NOTE)
            self._hybrid_table.setRowCount(0)
            return

        rows: list[tuple[str, ...]] = []
        # One sort value per column, parallel to `rows` -- `None` for a
        # text column (Element, Source), which leaves `SORT_ROLE` unset
        # and falls back to text comparison.
        row_sort_values: list[tuple[object, ...]] = []
        counts: dict[str, int] = {}
        errors: list[float] = []
        notes: list[str] = []
        # Carbon only -- the lookup's per-band accuracy was measured on
        # carbons, and selecting protons on a number nobody measured is
        # exactly what this module refuses to do.
        for element in sorted(
            {e for e in spectrum.elements.values() if e in nmr_hybrid.MERGEABLE_ELEMENTS}
        ):
            computed = {
                index: value
                for index, value in spectrum.values.items()
                if spectrum.elements.get(index) == element
            }
            scaling = parameters.get(f"scaling_{element}")
            factors = ScalingFactors(**scaling) if isinstance(scaling, dict) else None

            lookup = nmr_database.predict_spectrum(mol, spectrum.molecule_uuid, element=element)
            if not lookup.values:
                notes.append(
                    f"{element}: no database values to merge with"
                    + (f" — {lookup.error}" if lookup.error else "")
                )
                continue

            check = nmr_hybrid.check_calibration(
                nmr_hybrid.trusted_values(lookup),
                computed,
                element,
                getattr(factors, "residual_rms", None),
            )
            lookups = nmr_hybrid.lookup_candidates(lookup)
            computed_candidates = nmr_hybrid.computed_candidates(computed, factors)
            candidates = {
                index: [c for c in (lookups.get(index), computed_candidates.get(index)) if c]
                for index in set(lookups) | set(computed_candidates)
            }
            merged = nmr_hybrid.fuse(
                candidates, spectrum.elements, spectrum.molecule_uuid, element, check
            )
            if merged.error:
                notes.append(f"{element}: {merged.error}")
                continue

            details = merged.provenance.parameters
            notes.append(self._hybrid_summary(element, details, check))
            for source, count in details["sources"].items():
                counts[source] = counts.get(source, 0) + count
            for index in sorted(merged.values):
                detail = details["per_atom"][str(index)]
                expected = detail["expected_error"]
                if expected is not None:
                    errors.append(expected)
                rows.append(
                    (
                        str(index),
                        element,
                        f"{merged.values[index]:.3f}",
                        str(detail["source"]),
                        f"{expected:.2f}" if expected is not None else "unknown",
                        f"{detail['disagreement_ppm']:.2f}"
                        if detail["disagreement_ppm"]
                        else "—",
                    )
                )
                # "unknown"/"—" both sort BELOW every real value here --
                # same "no data groups at one end" convention as every
                # other sortable column in this phase.
                row_sort_values.append(
                    (
                        index,
                        None,
                        merged.values[index],
                        None,
                        expected if expected is not None else float("-inf"),
                        detail["disagreement_ppm"] if detail["disagreement_ppm"] else float("-inf"),
                    )
                )

        if rows:
            totals = "   ".join(f"{count} {source}" for source, count in sorted(counts.items()))
            average = f"{sum(errors) / len(errors):.2f} ppm" if errors else "unknown"
            notes.insert(0, f"{len(rows)} atoms      {totals}\nexpected average error   {average}")
        self._hybrid_summary_label.setText("\n".join(notes) or _HYBRID_UNAVAILABLE_NOTE)
        # No `_fill_tab` here: this tab has no placeholder WIDGET to
        # retire. `_hybrid_summary_label` IS the placeholder, and the line
        # above has just overwritten it -- with the real summary when
        # there are rows, or `_HYBRID_UNAVAILABLE_NOTE` when a run
        # produced none, which is a more specific answer than the opening
        # message for somebody who has already run something.
        self._hybrid_table.setSortingEnabled(False)
        self._hybrid_table.setRowCount(len(rows))
        for row, (values, sort_values) in enumerate(zip(rows, row_sort_values)):
            for col, text in enumerate(values):
                sort_value = sort_values[col]
                item = (
                    SortableItem(text, sort_value) if sort_value is not None else QTableWidgetItem(text)
                )
                self._hybrid_table.setItem(row, col, item)
        self._hybrid_table.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self._hybrid_table.setSortingEnabled(True)

    @staticmethod
    def _hybrid_summary(element: str, details: dict, check) -> str:
        """The calibration check, reported either way.

        A failing check no longer blocks the merge -- measured on DELTA50,
        refusing cost accuracy and prevented no harm. It is still worth
        showing: it says how far this calculation sits from values the
        database is confident about, which is real information about the
        run even when the merged spectrum is the better answer.
        """
        if check is None:
            return (
                f"{element}: no database values confident enough to check this "
                "calculation against — the merge could not verify itself."
            )
        verdict = "passed" if check.passed else "DISAGREES"
        note = (
            f"{element}: calibration check {verdict} against {check.compared} trusted "
            f"values (offset {check.mean_offset:+.2f}, RMS {check.rms:.2f}, "
            f"max {check.max_deviation:.2f} ppm)"
        )
        if not check.passed:
            note += (
                "\n   Merged anyway: each atom is still chosen by whichever method "
                "expects to be less wrong, and refusing the whole spectrum was "
                "measured to lose more than it saved."
            )
        return note

    def _populate_correlation_tab(
        self,
        correlation_type: str,
        cross_peaks: list[CrossPeak],
        spectrum: SpectrumResult,
        x_label: str,
        y_label: str,
    ) -> None:
        table = self._correlation_tables[correlation_type]
        # No `_fill_tab` here either -- the plot paints its own empty
        # message and stops as soon as it has peaks.
        #
        # OFF during population, like every other sortable table here --
        # a never-before-sorted `QTableWidget` already has a (section 0,
        # DESCENDING) sort indicator by Qt's own default, so re-enabling
        # without resetting it first would sort this table on its very
        # first population. See docs/gotchas/qt-table-sort-indicator-default.md.
        table.setSortingEnabled(False)
        table.setRowCount(len(cross_peaks))
        peaks: list[Peak] = []
        for row, cross_peak in enumerate(cross_peaks):
            shift_a = spectrum.values.get(cross_peak.atom_a)
            shift_b = spectrum.values.get(cross_peak.atom_b)
            atom_a_item = SortableItem(str(cross_peak.atom_a), cross_peak.atom_a)
            atom_b_item = SortableItem(str(cross_peak.atom_b), cross_peak.atom_b)
            shift_a_item = SortableItem(
                f"{shift_a:.3f}" if shift_a is not None else "", shift_a if shift_a is not None else float("-inf")
            )
            shift_b_item = SortableItem(
                f"{shift_b:.3f}" if shift_b is not None else "", shift_b if shift_b is not None else float("-inf")
            )
            # An em dash, not "0": no coupling value reported means no
            # coupling value reported. Sorts below every real value, the
            # same convention `NmrViewWidget`'s own coupling column uses.
            coupling_item = SortableItem(
                f"{cross_peak.coupling_hz:.2f}" if cross_peak.coupling_hz is not None else "—",
                cross_peak.coupling_hz if cross_peak.coupling_hz is not None else float("-inf"),
            )
            for col, item in enumerate(
                (atom_a_item, atom_b_item, shift_a_item, shift_b_item, coupling_item)
            ):
                table.setItem(row, col, item)
            if shift_a is not None and shift_b is not None:
                peaks.append(Peak(x=shift_a, y=shift_b, atom_a=cross_peak.atom_a, atom_b=cross_peak.atom_b))
        table.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        table.setSortingEnabled(True)
        self._correlation_plots[correlation_type].set_peaks(peaks, x_label=x_label, y_label=y_label)

    def _on_correlation_peak_selected(self, atom_a: int, atom_b: int) -> None:
        """A plot click -> the matching table row, by (atom_a, atom_b) --
        never by nearby coordinates, which two legitimately co-located
        cross peaks (a symmetric molecule) would resolve to the wrong
        row for. `correlation_type` comes off the plot that emitted this,
        not a captured closure -- see where this is connected."""
        correlation_type = self.sender().property("correlation_type")
        table = self._correlation_tables[correlation_type]
        table.blockSignals(True)
        for row in range(table.rowCount()):
            item_a, item_b = table.item(row, 0), table.item(row, 1)
            if item_a is not None and item_b is not None and (
                item_a.text(), item_b.text()
            ) == (str(atom_a), str(atom_b)):
                table.selectRow(row)
                break
        table.blockSignals(False)

    def _on_correlation_row_selected(self) -> None:
        """The inbound half: selecting a table row highlights its peak.
        `correlation_type` comes off the table that emitted this (see
        where this is connected), not a captured closure."""
        table = self.sender()
        correlation_type = table.property("correlation_type")
        rows = {index.row() for index in table.selectedIndexes()}
        if len(rows) != 1:
            return
        row = rows.pop()
        item_a, item_b = table.item(row, 0), table.item(row, 1)
        if item_a is None or item_b is None:
            return
        try:
            atom_a, atom_b = int(item_a.text()), int(item_b.text())
        except ValueError:
            return
        self._correlation_plots[correlation_type].set_highlighted_pair(atom_a, atom_b)
