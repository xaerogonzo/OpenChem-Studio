"""A screen can be configured, and the settings reach the real operation.

The defect this file exists for: `ScreeningService.request_screen` took no
`search_options` and passed none to `request_docking`, so a virtual screen ran
at whatever `VinaDockingProvider` happened to default to and **could not pin a
seed even in principle** -- while a single dock could. A screen is the one
operation this application offers for RANKING, and it was the one that was not
reproducible.

The sentinel test below is the shape this project's history most demands: it
is what catches "the dialog visibly has the setting and the real operation
ignores it", which is `BatchRequest.molecule_uuids` -- a field written by every
caller and read by nothing.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QWidget

from openchem.chem.docking_providers import (
    DEFAULT_EXHAUSTIVENESS,
    SUPPORTED_SCORING_FUNCTIONS,
)
from openchem.chem.rescoring import SUPPORTED_RESCORE_FUNCTIONS
from openchem.domain.docking import DockingBox
from openchem.domain.macromolecule import MacromoleculeModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.services.screening_service import ScreeningProtocol, ScreeningService
from openchem.ui.widgets.search_options import (
    EXHAUSTIVENESS_CHOICES,
    NO_RESCORE,
    UNPINNED_SEED,
    SearchOptionsControls,
)

_RECEPTOR_WITH_A_LIGAND = """ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00  0.00           N
ATOM      2  CA  ALA A   1       1.500   0.000   0.000  1.00  0.00           C
HETATM    3  C1  LIG A 900       5.000   5.000   5.000  1.00  0.00           C
HETATM    4  C2  LIG A 900       6.000   5.000   5.000  1.00  0.00           C
HETATM    5  C3  LIG A 900       5.000   6.000   5.000  1.00  0.00           C
END
"""

_METHANE = """
  Mrv

  1  0  0  0  0  0            999 V2000
    0.0000    0.0000    0.0000 C   0  0
M  END
"""


class _SpyDockingService:
    """Records what `request_docking` was called with, and answers nothing.

    Answering nothing is deliberate: the queue advances on a docking EVENT,
    so a spy that publishes none leaves exactly one request in flight, which
    is the one under inspection.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def request_docking(self, **kwargs) -> None:
        self.calls.append(kwargs)


class _Engine:
    def mol_from_model(self, molecule):  # noqa: ANN001 - a stand-in
        return object()


@pytest.fixture
def service_and_spy(qapp):  # noqa: ARG001 - a QApplication for the event bus
    spy = _SpyDockingService()
    service = ScreeningService(EventBus(), spy, _Engine())
    return service, spy


@pytest.fixture
def controls(qapp):  # noqa: ARG001 - a QApplication must exist
    """A real, HELD parent.

    `SearchOptionsControls(QComboBox())` reads correctly and does not work:
    the parent is a temporary, so Qt destroys it and every child with it, and
    the next line raises "Internal C++ object already deleted". This project
    records the same trap reaching a QMenu through `bar.actions()`.
    """
    parent = QWidget()
    yield SearchOptionsControls(parent)
    parent.deleteLater()


def _receptor() -> MacromoleculeModel:
    return MacromoleculeModel(
        display_name="A receptor",
        structure_text="ATOM      1  N   ALA A   1       0.000   0.000   0.000\n",
        source_format="pdb",
    )


def _ligands(n: int = 1) -> list[MoleculeModel]:
    return [
        MoleculeModel(display_name=f"ligand {i}", molblock=_METHANE)
        for i in range(n)
    ]


# -- the sentinel -----------------------------------------------------------


def test_every_search_setting_reaches_request_docking_unchanged(service_and_spy):
    """THE SENTINEL. One request, a DISTINCT value for every option.

    Distinct on purpose: with two settings sharing a value, a wiring that
    sends one where the other belongs is invisible. `exhaustiveness=37` is
    not an offered choice and `seed=123456` is not a default, so neither can
    arrive by coincidence.
    """
    service, spy = service_and_spy
    search = {
        "exhaustiveness": 37,
        "scoring_function": "vinardo",
        "seed": 123456,
        "rescore_with": "vina",
    }
    prep = {
        "ph": 6.37,
        "strip_waters": False,
        "strip_cofactors": True,
        "strip_ligand_codes": ("ABC",),
        "keep_chains": ("B",),
        "build_assembly": False,
    }
    service.request_screen(
        _ligands(),
        _receptor(),
        DockingBox(center=(1.0, 2.0, 3.0), size=(20.0, 20.0, 20.0)),
        num_poses=7,
        receptor_prep_options=prep,
        search_options=search,
        replicates=3,
    )

    assert len(spy.calls) == 1
    call = spy.calls[0]
    assert call["search_options"] == search
    assert call["receptor_prep_options"] == prep
    assert call["num_poses"] == 7
    assert call["replicates"] == 3


def test_a_screen_that_sets_nothing_sends_an_empty_dict_not_a_default(service_and_spy):
    """The narrow half, and it is the load-bearing one.

    "Always send the panel's defaults" satisfies the sentinel and silently
    re-baselines every caller that asked for nothing -- which is the
    behaviour change an opt-in feature must not make. An empty dict lets the
    provider apply its OWN defaults, which is what happened before this
    parameter existed.
    """
    service, spy = service_and_spy
    service.request_screen(
        _ligands(),
        _receptor(),
        DockingBox(center=(0.0, 0.0, 0.0), size=(20.0, 20.0, 20.0)),
    )
    assert spy.calls[0]["search_options"] == {}


# -- the protocol record ----------------------------------------------------


def test_the_protocol_records_what_was_asked_and_not_what_was_assumed(service_and_spy):
    """None means NOT ASKED. It must never mean "asked for the default".

    `_DockingTask` once filled `scoring_function="vina"` and
    `exhaustiveness=8` with literals that were true only by coincidence, and
    a stored result naming settings it did not use is worse than one naming
    none -- nothing distinguishes it from a measurement.
    """
    service, spy = service_and_spy
    events: list = []
    service._event_bus.subscribe(type(None), lambda e: None)  # no-op, keeps the bus alive

    service.request_screen(
        _ligands(),
        _receptor(),
        DockingBox(center=(0.0, 0.0, 0.0), size=(20.0, 20.0, 20.0)),
    )
    protocol = service._protocol
    assert isinstance(protocol, ScreeningProtocol)
    assert protocol.requested_exhaustiveness is None
    assert protocol.requested_scoring_function is None
    assert protocol.protocol_seed is None
    assert protocol.rescore_with is None
    # And nothing has told us what really ran yet.
    assert protocol.resolved is False
    assert protocol.engine == ""
    assert protocol.exhaustiveness is None


def test_the_protocol_carries_a_requested_setting_verbatim(service_and_spy):
    service, spy = service_and_spy
    service.request_screen(
        _ligands(),
        _receptor(),
        DockingBox(center=(0.0, 0.0, 0.0), size=(20.0, 20.0, 20.0)),
        search_options={"exhaustiveness": 32, "scoring_function": "vinardo", "seed": 99},
    )
    protocol = service._protocol
    assert protocol.requested_exhaustiveness == 32
    assert protocol.requested_scoring_function == "vinardo"
    assert protocol.protocol_seed == 99


def test_an_explicit_off_rescore_is_not_the_same_as_never_mentioning_it(service_and_spy):
    """"" is a CHOICE and None is silence, and the record keeps them apart.

    Collapsing them loses the difference between a screen whose author
    decided against a second opinion and one that predates the control.
    """
    service, spy = service_and_spy
    box = DockingBox(center=(0.0, 0.0, 0.0), size=(20.0, 20.0, 20.0))
    service.request_screen(_ligands(), _receptor(), box, search_options={"rescore_with": ""})
    assert service._protocol.rescore_with == ""
    service.cancel()
    service._finish()
    service.request_screen(_ligands(), _receptor(), box, search_options={})
    assert service._protocol.rescore_with is None


def test_the_protocol_resolves_from_the_run_rather_than_from_the_request():
    """The provider is the authority on what actually ran.

    Asserted on the transformation directly: driving a real result through
    the service needs a provider, and what is under test is the RULE that
    engine, version, scoring function and exhaustiveness come from the
    result -- not the plumbing that delivers one.
    """
    from openchem.domain.docking import DockingResultModel
    from openchem.domain.common import Provenance

    protocol = ScreeningProtocol(
        requested_exhaustiveness=None,
        requested_scoring_function=None,
    )
    result = DockingResultModel(
        ligand_molecule_uuid="l",
        receptor_macromolecule_uuid="r",
        box=DockingBox(center=(0.0, 0.0, 0.0), size=(1.0, 1.0, 1.0)),
        poses=[],
        provenance=Provenance(method="vina", created_by="test"),
        engine="vina-executable",
        engine_version="1.2.7",
        scoring_function="vinardo",
        exhaustiveness=25,
        seed=4712,
    )
    resolved = protocol.resolved_against(result)

    assert resolved.resolved is True
    assert resolved.engine == "vina-executable"
    assert resolved.engine_version == "1.2.7"
    assert resolved.scoring_function == "vinardo"
    assert resolved.exhaustiveness == 25
    # The REQUEST is unchanged: it records that nothing was asked for, which
    # stays true however the run answered.
    assert resolved.requested_exhaustiveness is None
    assert resolved.requested_scoring_function is None
    # Idempotent -- a screen runs one protocol, so the second result writes
    # what the first did.
    assert resolved.resolved_against(result) == resolved


def test_the_protocol_reaches_the_progress_event(service_and_spy):
    """A reader of a partial table needs to know which protocol produced it."""
    service, spy = service_and_spy
    seen: list = []
    from openchem.services.screening_service import ScreeningProgress

    service._event_bus.subscribe(ScreeningProgress, seen.append)
    service.request_screen(
        _ligands(),
        _receptor(),
        DockingBox(center=(0.0, 0.0, 0.0), size=(20.0, 20.0, 20.0)),
        search_options={"exhaustiveness": 16},
    )
    assert seen, "the service publishes progress on request"
    assert seen[0].protocol is not None
    assert seen[0].protocol.requested_exhaustiveness == 16


# -- the dialog's own wiring ------------------------------------------------
#
# THE SENTINEL ABOVE TESTS THE SERVICE, NOT THE DIALOG, and a mutation proved
# the difference: replacing `self._search.options()` in `_start` with a dict
# the dialog assembles itself SURVIVED every test in this file and in four
# others. Testing a helper is not testing the wiring -- the fifth time this
# project has recorded that -- so the guard below drives the real button.


class _RecordingScreeningService:
    """Stands in for the service and records the request verbatim."""

    def __init__(self) -> None:
        self.requests: list[dict] = []

    def request_screen(self, ligands, receptor, box, **kwargs) -> None:
        self.requests.append(dict(kwargs, ligands=list(ligands), receptor=receptor, box=box))

    def cancel(self) -> None:  # the Cancel button connects to it at build time
        pass


@pytest.fixture
def wired_dialog(qapp):  # noqa: ARG001
    """A real dialog against a recording service.

    Built by hand rather than through the inventory, deliberately: the
    inventory hands it the REAL service, and what is under test is what the
    dialog sends -- which needs the receiving end to be readable.
    """
    from openchem.domain.macromolecule import MacromoleculeModel
    from openchem.events.base import EventBus
    from openchem.ui.dialogs.virtual_screening_dialog import VirtualScreeningDialog

    receptor = MacromoleculeModel(
        display_name="A receptor",
        structure_text=_RECEPTOR_WITH_A_LIGAND,
        source_format="pdb",
        metadata={"ligand_code": "LIG"},
    )
    molecule = MoleculeModel(display_name="ligand", molblock=_METHANE)
    project = ProjectModel(name="p", molecules=[molecule], macromolecules=[receptor])
    service = _RecordingScreeningService()
    dialog = VirtualScreeningDialog(service, EventBus(), project)
    yield dialog, service
    dialog.setParent(None)
    dialog.deleteLater()


def test_the_dialogs_four_controls_reach_the_service(wired_dialog):
    """Set every control to a DISTINCT non-default value, press Run, and read
    what the service was handed.

    This is the arm M5 exposed. Distinct values on purpose: with two settings
    sharing one, a wiring that sends one where the other belongs is invisible.
    """
    dialog, service = wired_dialog
    dialog._search.exhaustiveness.setCurrentIndex(
        dialog._search.exhaustiveness.findData(32)
    )
    dialog._search.scoring_function.setCurrentIndex(
        dialog._search.scoring_function.findData("vinardo")
    )
    dialog._search.rescore_with.setCurrentIndex(
        dialog._search.rescore_with.findData("vina")
    )
    dialog._search.seed.setValue(123456)

    dialog._start()

    assert service.requests, "the Run button reached the service"
    options = service.requests[0]["search_options"]
    assert options == {
        "exhaustiveness": 32,
        "scoring_function": "vinardo",
        "seed": 123456,
        "rescore_with": "vina",
    }


def test_the_dialog_sends_its_defaults_when_nothing_is_touched(wired_dialog):
    """The narrow half. "Send everything the controls hold" satisfies the
    test above AND a dialog that reads one widget and hardcodes the rest, so
    the untouched case has to be asserted too -- it is the one every user
    who never opens the controls actually runs."""
    dialog, service = wired_dialog
    dialog._start()
    options = service.requests[0]["search_options"]
    assert options == {
        "exhaustiveness": DEFAULT_EXHAUSTIVENESS,
        "scoring_function": SUPPORTED_SCORING_FUNCTIONS[0],
        "seed": None,
    }
    assert "rescore_with" not in options, "Off sends no key at all"


def test_the_dialog_presses_the_real_button(wired_dialog):
    """`_start` is what the Run button is connected to.

    Asserted rather than assumed, for the reason `jobs_cancel` presses the
    button instead of calling the handler: a test that calls a method proves
    the method works and says nothing about whether anything invokes it.
    """
    dialog, service = wired_dialog
    dialog._run.click()
    assert service.requests, "clicking Run requests a screen"


# -- the shared controls ----------------------------------------------------


def test_the_two_surfaces_share_one_control_object(controls):
    """Not two implementations. Asserted on the SOURCE, because the two
    surfaces agreeing today is what a copy would also look like."""
    import ast
    import pathlib

    for rel in (
        "src/openchem/ui/panels/docking_panel.py",
        "src/openchem/ui/dialogs/virtual_screening_dialog.py",
    ):
        text = pathlib.Path(rel).read_text(encoding="utf-8")
        assert "SearchOptionsControls" in text, rel
        tree = ast.parse(text)
        # Neither surface may build its own exhaustiveness/scoring/seed
        # widgets: the object owns them.
        constructed = [
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        assert constructed.count("SearchOptionsControls") == 1, rel


def test_the_scoring_combo_is_built_from_the_registered_vocabulary(controls):
    """`"vinardo"` must not be a magic string in a UI file.

    The provider VALIDATES against `SUPPORTED_SCORING_FUNCTIONS`, so a combo
    built from it offers only functions the provider accepts -- by
    construction rather than by two lists being edited together.
    """
    offered = [
        controls.scoring_function.itemData(i)
        for i in range(controls.scoring_function.count())
    ]
    assert tuple(offered) == tuple(SUPPORTED_SCORING_FUNCTIONS)

    rescore = [
        controls.rescore_with.itemData(i)
        for i in range(controls.rescore_with.count())
    ]
    assert rescore[0] == NO_RESCORE, "Off is first and is the default"
    assert set(rescore[1:]) == set(SUPPORTED_RESCORE_FUNCTIONS)


def test_no_ui_file_hardcodes_a_scoring_function_name(controls):
    """The narrow half. A combo built from the registry satisfies the test
    above while a `if rescore_with == "vinardo":` fossil elsewhere in the
    same file does not, and that fossil is what the plan named."""
    import pathlib
    import re

    offenders = []
    for path in pathlib.Path("src/openchem/ui").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r'"(vinardo)"', text):
            line_no = text[: match.start()].count("\n") + 1
            line = text.split("\n")[line_no - 1]
            # A mention inside a help contract or a comment is prose about
            # the function, not a branch on its id.
            if line.lstrip().startswith("#") or line.lstrip().startswith('"'):
                continue
            offenders.append(f"{path.as_posix()}:{line_no}")
    assert not offenders, "a scoring-function id is branched on as a literal:\n  " + "\n  ".join(
        offenders
    )


def test_an_unpinned_seed_is_sent_as_none_rather_than_zero(controls):
    """0 is the spinbox's "Random", and sending it as a seed would make every
    unpinned run share one."""
    controls.seed.setValue(UNPINNED_SEED)
    assert controls.options()["seed"] is None
    controls.seed.setValue(4712)
    assert controls.options()["seed"] == 4712


def test_off_sends_no_rescore_key_at_all(controls):
    """ABSENT rather than empty, so a run that asked for no rescore sends the
    byte-identical dict it sent before this control existed."""
    assert "rescore_with" not in controls.options()
    controls.rescore_with.setCurrentIndex(1)
    assert controls.options()["rescore_with"] in SUPPORTED_RESCORE_FUNCTIONS


def test_the_defaults_are_the_shipped_ones(controls):
    options = controls.options()
    assert options["exhaustiveness"] == DEFAULT_EXHAUSTIVENESS
    assert DEFAULT_EXHAUSTIVENESS in EXHAUSTIVENESS_CHOICES
    assert options["scoring_function"] == SUPPORTED_SCORING_FUNCTIONS[0]
    assert options["seed"] is None


def test_four_more_rows_still_fit_a_small_laptop(wired_dialog):
    """HEIGHT ONLY, and that asymmetry is deliberate.

    This branch added four rows to a dialog that had five. The periodic
    table's own history is what makes that worth asserting: one tab's
    comfortable floor became the whole dialog's, its action row ended up
    105 px below the bottom of the screen, and a `QDialog` has no maximise
    button and no size grip by default -- so a minimum larger than the
    screen cannot be rescued by resizing, because `resize()` is clamped to
    it.

    A WIDTH bound would be a claim about the font: `offscreen`'s default is
    far wider than a user's, and this project has already had a geometry
    test fail by 40 px on a panel measurably clean in the app. Height is
    driven by ROW COUNTS, which is the thing this branch changed and the
    thing a reader can reason about.

    728 is 768 less ordinary window chrome -- the smallest screen this
    product supports.
    """
    dialog, _ = wired_dialog
    assert dialog.minimumSizeHint().height() <= 728
