"""A test must not leave a deferred delete queued for a later test to drain.

This guards the autouse `flush_deferred_deletes` fixture in `conftest.py`,
because what it prevents is invisible in normal output and goes off much
later: `processEvents()` does not deliver a `DeferredDelete`, so without
the fixture every `deleteLater()` in the suite accumulates in one
process-wide queue until something spins a nested event loop and drains
the whole backlog at once, thousands of allocations away from the code
that queued it.

The check is an ordered pair: one test deliberately abandons an object,
the next asserts it was destroyed in between. pytest runs tests in
definition order within a file, so the pair is deterministic.

There is deliberately no companion check that DESTROYS abandoned widgets.
A fixture that did was tried twice and reverted twice for crashing the
suite; `flush_deferred_deletes` documents that at length.

The second half of the problem -- widgets whose C++ destructor ran inside
an unrelated test -- is now solved by the `pytest_runtest_teardown` hook in
`conftest.py`, and the pair of tests at the bottom of this file guard the
mechanism it relies on.
"""

from __future__ import annotations

import weakref

import pytest

import shiboken6
from PySide6.QtCore import QObject

_deleted_later: list[weakref.ref] = []
_abandoned_subscribers: list[weakref.ref] = []


def test_a_test_may_call_delete_later_and_not_wait(qapp):
    # A plain QObject rather than a widget: nothing else in the suite
    # disposes of one, so this isolates `flush_deferred_deletes`.
    obj = QObject()
    obj.deleteLater()
    _deleted_later.append(weakref.ref(obj))


def test_that_deferred_delete_was_flushed_before_this_test_started(qapp):
    assert _deleted_later, "the test above must run first -- this pair is ordered"
    obj = _deleted_later[0]()
    assert obj is None or not shiboken6.isValid(obj), (
        "a deleteLater() was still queued after its test ended. processEvents() "
        "does not deliver DeferredDelete, so it would sit in the process-wide "
        "queue until some later test caused a nested event loop to drain the "
        "whole backlog at once. See flush_deferred_deletes in conftest.py."
    )


# --- why a panel outlives its test, and what the teardown collect fixes ----


def test_subscribing_does_not_keep_the_subscriber_alive(qapp):
    """The contract `EventBus` now holds itself to.

    It used to store the BOUND METHOD, so the bus held the subscriber and
    the subscriber held the bus: nothing could be freed by reference
    counting, and the pair waited for the cyclic collector, which runs at a
    moment nobody chooses -- including inside Qt's event dispatch during an
    unrelated test. Bound methods are held weakly now, so a subscriber dies
    with its last real reference.
    """
    import gc

    from openchem.events.base import EventBus
    from openchem.events.events import MoleculeChanged

    class Subscriber:
        def __init__(self, bus):
            self._bus = bus
            bus.subscribe(MoleculeChanged, self._on_changed)

        def _on_changed(self, event):
            pass

    gc.collect()
    bus = EventBus()
    ref = weakref.ref(Subscriber(bus))

    assert ref() is None, "refcounting alone must free a subscriber"


def test_a_lambda_handler_is_still_held_strongly(qapp):
    """The deliberate asymmetry, and the reason it is not a bug.

    A lambda usually has no other reference. Held weakly it would be
    collected the instant `subscribe` returned and the subscription would
    silently never fire -- which is far worse than a leak, because nothing
    would look wrong. Only bound methods are weak, because only they have
    an owner whose lifetime is the right answer.
    """
    from openchem.events.base import EventBus
    from openchem.events.events import MoleculeChanged

    bus = EventBus()
    seen = []
    bus.subscribe(MoleculeChanged, lambda event: seen.append(event))

    bus._dispatch(MoleculeChanged(molecule_uuid="u"))

    assert len(seen) == 1


def test_a_dead_subscriber_is_dropped_rather_than_raising(qapp):
    """Nothing has to unsubscribe on the way out."""
    from openchem.events.base import EventBus
    from openchem.events.events import MoleculeChanged

    class Subscriber:
        def __init__(self, bus, seen):
            self._seen = seen
            bus.subscribe(MoleculeChanged, self._on_changed)

        def _on_changed(self, event):
            self._seen.append(event)

    bus = EventBus()
    seen = []
    kept = Subscriber(bus, seen)
    Subscriber(bus, seen)  # dropped immediately

    bus._dispatch(MoleculeChanged(molecule_uuid="u"))

    assert len(seen) == 1, "the collected subscriber must not have been called"
    assert kept is not None
    # And the dead entry is REMOVED, not merely skipped. Skipping is
    # invisible to a behavioural test and would let `_handlers` grow for
    # the life of the process.
    assert len(bus._handlers[MoleculeChanged]) == 1


def test_unsubscribe_still_removes_exactly_one_subscription(qapp):
    """A bound method is a fresh object each time it is looked up, so
    `unsubscribe` has to compare by equality; an identity test would
    silently do nothing. One occurrence, matching the old behaviour --
    `PluginContext` records one rollback per subscribe."""
    from openchem.events.base import EventBus
    from openchem.events.events import MoleculeChanged

    class Subscriber:
        def __init__(self, seen):
            self._seen = seen

        def on_changed(self, event):
            self._seen.append(event)

    bus = EventBus()
    seen = []
    subscriber = Subscriber(seen)
    for _ in range(3):
        bus.subscribe(MoleculeChanged, subscriber.on_changed)

    bus.unsubscribe(MoleculeChanged, subscriber.on_changed)
    bus._dispatch(MoleculeChanged(molecule_uuid="u"))

    # THREE subscriptions, not two: with only two, a loop that deleted
    # every match still ended up removing one (it mutates the list it is
    # enumerating and falls off the end), so the test passed either way.
    assert len(seen) == 2


def test_a_subscriber_left_behind_is_gone_before_the_next_test(qapp):
    """The first half of an ordered pair, like the deferred-delete one
    above: this abandons a subscriber, and the next test asserts it was
    collected in between -- which is what the teardown hook exists to
    guarantee, and what stops the destructor landing in someone else's
    event dispatch."""
    from openchem.events.base import EventBus
    from openchem.events.events import MoleculeChanged

    class Abandoned:
        def __init__(self, bus):
            self._bus = bus
            bus.subscribe(MoleculeChanged, self._on_changed)

        def _on_changed(self, event):
            pass

    bus = EventBus()
    _abandoned_subscribers.append(weakref.ref(Abandoned(bus)))
    _abandoned_subscribers.append(weakref.ref(bus))


def test_the_abandoned_subscriber_was_collected_at_the_previous_teardown(qapp):
    assert _abandoned_subscribers, "the previous test did not run; the pair is broken"
    assert all(ref() is None for ref in _abandoned_subscribers), (
        "a subscriber survived into this test -- the teardown gc.collect() in "
        "conftest.py has regressed, and its destructor will now run at an "
        "arbitrary later moment"
    )


# --- the leak a self-capturing lambda creates -------------------------------


def _survives_collection(factory) -> bool:
    """True if the object is still alive after the cyclic collector has run.

    Built inside this helper so the caller keeps no local: an object the
    test itself still references is trivially alive, which is how two
    earlier attempts at this measurement fooled themselves.
    """
    import gc

    gc.collect()
    gc.collect()
    ref = weakref.ref(factory())
    for _ in range(3):
        gc.collect()
    return ref() is not None


def test_connecting_a_self_capturing_lambda_leaks_its_widget(qapp):
    """The mechanism, pinned so the fixes below have something to point at.

    PySide6 holds a connected plain callable STRONGLY and a QObject's bound
    method weakly. So a `lambda: self._handler(x)` connected to a signal
    roots its widget for the life of the process -- past refcounting and
    past the cyclic collector, which cannot see through the map the
    callable is kept in.

    This asserts the leak deliberately. If a future PySide6 stops leaking
    here, this test fails and the workarounds it justifies can go.
    """
    from PySide6.QtWidgets import QPushButton, QWidget

    class SelfCapturing(QWidget):
        def __init__(self):
            super().__init__()
            button = QPushButton(self)
            button.clicked.connect(lambda _checked=False: self._go())

        def _go(self):
            pass

    class BoundMethod(QWidget):
        def __init__(self):
            super().__init__()
            button = QPushButton(self)
            button.clicked.connect(self._go)

        def _go(self, _checked=False):
            pass

    assert _survives_collection(SelfCapturing), "PySide6 no longer leaks here"
    assert not _survives_collection(BoundMethod)


def test_the_property_panel_does_not_leak(qapp):
    """Measured before the fix: it survived refcounting AND three cycles of
    the collector, because `_section_for` connected one self-capturing
    lambda per registered calculator -- 22 of them on a default registry.
    Every panel ever built stayed in memory for the session."""
    from openchem.bootstrap import build_service_container
    from openchem.ui.panels.property_panel import PropertyPanel

    def build():
        services = build_service_container()
        return PropertyPanel(
            services.event_bus,
            services.calculator_registry,
            services.descriptor_service,
            services.chemistry_engine,
        )

    assert not _survives_collection(build)


def test_the_periodic_table_dialog_does_not_leak(qapp):
    """118 cells, each of which was connecting a self-capturing lambda."""
    from openchem.ui.dialogs.periodic_table_dialog import PeriodicTableDialog

    assert not _survives_collection(PeriodicTableDialog)


def test_the_jobs_panel_does_not_leak(qapp):
    """The one that was missed, and the worst place to miss it.

    `refresh` runs on a 500 ms timer that nothing stops, so the leaked
    lambda was not connected once -- it was connected TWICE A SECOND for
    the life of the process, on a panel that could never be collected.

    **THE FIXTURE MUST HAVE A JOB, or it cannot see the defect.** The
    lambda lived inside `for row, job in enumerate(jobs)`, so a panel with
    an empty `JobManager` never reached it and was collected perfectly
    happily. Measured on the shipped defect: with one active job
    `_survives_collection` is True, with none it is False. A fixture built
    from a bare `JobManager()` is the degenerate case this project keeps
    paying for -- it passes against the bug.
    """
    from openchem.services.job_manager import JobManager
    from openchem.ui.panels.jobs_panel import JobsPanel

    def build():
        job_manager = JobManager()
        job_manager.try_start("conformer", "mol-1")
        return JobsPanel(job_manager)

    assert not _survives_collection(build)


def test_a_jobs_panel_with_no_jobs_could_never_have_shown_the_leak(qapp):
    """The control for the fixture above, asserting its own setup.

    Without this, someone simplifying `build()` to `JobsPanel(JobManager())`
    leaves a green test that cannot fail. This states, in the suite rather
    than in a comment, that the empty panel is NOT evidence: it is collected
    with the fix and was collected without it.
    """
    from openchem.services.job_manager import JobManager
    from openchem.ui.panels.jobs_panel import JobsPanel

    assert not _survives_collection(lambda: JobsPanel(JobManager()))


def test_a_subscriber_collected_during_dispatch_is_not_called(qapp):
    """The narrow race the None check in `_dispatch` exists for.

    Pruning happens before any handler runs, so an entry can be alive at
    prune time and dead by the time the loop reaches it -- which is exactly
    what happens when one handler drops the last reference to another
    subscriber. Without the guard that is a call through a dead weakref.

    Written after mutation testing: removing the check failed nothing,
    because every other test prunes and dispatches with a stable set.
    """
    import gc

    from openchem.events.base import EventBus
    from openchem.events.events import MoleculeChanged

    bus = EventBus()
    seen = []
    holder = {}

    class Victim:
        def on_changed(self, event):
            seen.append("victim")

    class Killer:
        def on_changed(self, event):
            seen.append("killer")
            holder.clear()  # drops the only reference to the victim
            gc.collect()

    killer = Killer()
    victim = Victim()
    holder["victim"] = victim
    bus.subscribe(MoleculeChanged, killer.on_changed)
    bus.subscribe(MoleculeChanged, victim.on_changed)
    del victim

    bus._dispatch(MoleculeChanged(molecule_uuid="u"))

    assert seen == ["killer"], "the victim was collected mid-dispatch and must not be called"


def test_closing_a_main_window_empties_its_undo_stack(qapp, tmp_path):
    """Not tidiness -- destruction safety.

    A MainWindow whose stack still holds commands faults when it is
    destroyed. Measured against the real window: suppress `_new_molecule`
    so nothing is ever pushed and it destroys cleanly 3/3; clear the stack
    first and it destroys cleanly 5/5; drop it as-is and it segfaults 5/5.
    `close()` alone is not enough, so `closeEvent` does the clearing.

    The mechanism is not understood. A synthetic QUndoCommand on a
    QUndoStack destroys fine, and so does the real `AddMoleculeCommand` in
    a minimal harness -- it takes the whole window. Recorded in CLAUDE.md.
    """
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container

    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "no_plugins"))
    settings.set("plugins/user_directory", str(tmp_path / "no_user"))
    window = MainWindow(services, settings, SessionManager())
    # The auto-created molecule puts one command on the stack.
    assert window._undo_stack.count() > 0

    window.close()

    assert window._undo_stack.count() == 0


@pytest.fixture
def a_fixture_provided_panel(qapp):
    """Provided BY A FIXTURE on purpose.

    That is the case the collect's placement is about: pytest caches a
    fixture's value on its `SubRequest`/`TopRequest`/`Function` and holds
    it for the whole item protocol. An object built as a plain local
    inside a test is released when the function returns and would be
    collected either way -- so a test written that way cannot tell the
    right hook from the wrong one, which is exactly what happened on the
    first attempt at this.

    **A PANEL, NOT A MainWindow, and that is the point of this rewrite.**
    This pair used to use a MainWindow, and asserted that the collect
    destroyed it. Destroying one turns out to CORRUPT THE HEAP -- so
    MainWindows are now retained for the session (see `conftest.py`) and
    cannot be the probe. A panel is still collected, still fixture-held,
    and still proves what this pair is really about: that the collect runs
    after pytest finalises fixtures rather than before.
    """
    from openchem.events.base import EventBus
    from openchem.ui.panels.property_panel import PropertyPanel
    from openchem.services.calculator_registry import CalculatorRegistry
    from openchem.chem.engine import ChemistryEngine

    class _Service:
        def request_descriptors(self, *a, **k):
            pass

        def run_calculator(self, *a, **k):
            pass

    bus = EventBus()
    yield PropertyPanel(bus, CalculatorRegistry(), _Service(), ChemistryEngine())


def test_a_fixture_provided_object_is_gone_before_the_next_test(a_fixture_provided_panel):
    """First half of an ordered pair; the next test checks it was destroyed.

    This is what the collect's PLACEMENT buys. It used to run in
    `pytest_runtest_teardown` with no ordering, which puts it BEFORE
    pytest finalises fixtures -- and pytest still holds every fixture
    value at that moment, so the object could not possibly be collected
    there. Measured by listing the referrers of one still alive at
    teardown: `SubRequest`, `TopRequest`, `Function` and the fixture-name
    cache. All pytest machinery; nothing in the application held it.

    Moving the collect to after the protocol ends took late C++
    destructions from 135 to 0.
    """
    _abandoned_subscribers.append(weakref.ref(a_fixture_provided_panel))


def test_that_object_was_collected_between_the_tests(qapp):
    assert _abandoned_subscribers, "the previous test did not run; the pair is broken"
    assert all(ref() is None for ref in _abandoned_subscribers), (
        "a fixture-provided panel survived into the next test -- the gc.collect() in "
        "conftest.py has moved back to a hook that runs while pytest still holds the "
        "fixture values"
    )


def test_main_windows_are_deliberately_never_collected(qapp, tmp_path):
    """The opposite policy, for the one class where collecting is fatal.

    Collecting a MainWindow corrupts the heap -- 0xc0000374, raised inside
    the collect, in whichever test is unlucky. Measured on a two-file
    reproduction: retaining MainWindow made it clean, retaining the viewer
    backends or the web-engine objects did not, and `gc.DEBUG_SAVEALL`
    (free nothing at all) also made it clean.

    So `conftest.py` holds every one for the session. This asserts that,
    because the retainer is easy to remove while reading the file as
    scaffolding.
    """
    import gc

    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container

    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "no_plugins"))
    settings.set("plugins/user_directory", str(tmp_path / "no_user"))
    window = MainWindow(services, settings, SessionManager())
    reference = weakref.ref(window)
    window.close()
    del window, services, settings
    gc.collect()

    assert reference() is not None, (
        "a MainWindow was collected -- the retainer in conftest.py is gone, and "
        "the suite will start corrupting the heap at an unrelated test"
    )


def test_every_single_shot_timer_is_bound_to_a_context_object():
    """A pending `QTimer.singleShot` must not outlive its widget.

    `QTimer.singleShot(msec, callable)` is tied to nothing, so a widget
    destroyed before it fires leaves a live Python wrapper around a freed
    C++ object -- `RuntimeError: libshiboken: Internal C++ object ...
    already deleted`, raised from inside Qt's dispatch in whatever code
    happens to be pumping events, which is why it reads as a failure
    somewhere else entirely. The three-argument form takes a CONTEXT
    OBJECT that Qt disconnects on destruction, so the shot is cancelled
    rather than firing and then declining.

    **FIVE SITES SHIPPED WITH THIS, in four files, and they were not one
    bug.** One crashed the suite through an innocent bystander; one also
    replayed a superseded payload; one never fired at all because the
    two-argument form cannot cross a thread with no event loop; one could
    not have raised and was tidied anyway; one sat behind an env var with
    the widest window of the lot. A per-site fix would have been five
    separate arguments, so the invariant is asserted over the package.

    Deliberately NOT a ban on lambdas. `progress_reporter` legitimately
    passes one that captures a label and a plain value, never a `self` --
    which is the capture that leaks (see
    `test_connecting_a_self_capturing_lambda_leaks_its_widget` above).
    What every one of the five got wrong was the missing context object,
    and that is what this pins.

    A shot that genuinely must fire regardless of any object's lifetime
    would fail here, and should: it can pass `QCoreApplication.instance()`
    and say why in a comment, rather than being indistinguishable from the
    five accidents.
    """
    import ast
    from pathlib import Path

    package = Path(__file__).resolve().parents[1] / "src" / "openchem"
    offenders = []
    checked = 0
    for path in sorted(package.rglob("*.py")):
        if "vendor" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "singleShot"
            ):
                checked += 1
                if len(node.args) != 3:
                    rel = path.relative_to(package.parent.parent)
                    offenders.append(f"{rel}:{node.lineno}")

    assert checked >= 5, f"only {checked} singleShot calls found; this guard has lost its subject"
    assert not offenders, (
        "pass a context object as the second argument, or the shot outlives its widget: "
        + ", ".join(offenders)
    )


def test_no_signal_is_connected_to_a_self_capturing_lambda():
    """The invariant, over the package, rather than one widget at a time.

    PySide6 holds a connected plain callable STRONGLY and a QObject's bound
    method weakly, so `signal.connect(lambda ...: self._handler(x))` roots
    its owner for the life of the process -- past refcounting and past the
    cyclic collector, which cannot see through the map the callable is kept
    in. `test_connecting_a_self_capturing_lambda_leaks_its_widget` above
    pins that mechanism; this pins that nothing in the package does it.

    **FIVE SITES SHIPPED WITH THIS, in five files, and they were not one
    bug.** `PropertyPanel`, `PeriodicTableDialog` and `ExternalToolsDialog`
    had each been fixed individually, and a per-widget guard was written for
    two of them -- so the rule existed, the cure existed, and the population
    was still a hand-kept list that three widgets were on and five were not.
    The worst of the five was `JobsPanel`, whose `refresh` runs on a 500 ms
    timer, so it connected a fresh rooted lambda twice a second forever and
    was named in the Linux suite's segfault traceback.

    WHAT IT DOES NOT COVER, said here because a green structural guard is
    easily mistaken for a lifetime proof. It pins ONE SHAPE: a lambda passed
    directly to `connect` whose body mentions `self`. It says nothing about
    a lambda that reaches `self` through another name, a
    `functools.partial(self...)`, a strong reference held somewhere else
    entirely, or an object kept alive by its Qt parent.
    `test_the_property_panel_does_not_leak` and its siblings assert the
    OUTCOME and are not made redundant by this.

    If a site genuinely needs the capture it should fail here and say why in
    a comment, the same escape `test_every_single_shot_timer_is_bound_to_a_context_object`
    grants `QCoreApplication.instance()`.
    """
    import ast
    from pathlib import Path

    package = Path(__file__).resolve().parents[1] / "src" / "openchem"
    offenders = []
    checked = 0
    for path in sorted(package.rglob("*.py")):
        if "vendor" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "connect"
            ):
                continue
            checked += 1
            for argument in node.args:
                if isinstance(argument, ast.Lambda) and any(
                    isinstance(name, ast.Name) and name.id == "self"
                    for name in ast.walk(argument.body)
                ):
                    rel = path.relative_to(package.parent.parent)
                    offenders.append(f"{rel}:{node.lineno}")

    # REPORTED EVEN WHEN IT PASSES. `checked >= N` catches the walk
    # collapsing to nothing; the printed count is what makes a quieter drift
    # visible in a green run. Measured at 265 when this was written.
    print(f"\nchecked {checked} connect() calls; {len(offenders)} self-capturing lambdas")

    assert checked >= 200, (
        f"only {checked} connect() calls found; this guard has lost its subject"
    )
    assert not offenders, (
        "connect a bound method and carry the payload on the widget "
        "(setProperty/setData, read back through sender()) -- a lambda "
        "capturing `self` roots its owner forever: " + ", ".join(offenders)
    )


# ---------------------------------------------------------------------------
# The Qt object census: a re-import is not a second census
# ---------------------------------------------------------------------------
#
# `_start_census` in `conftest.py` refuses to be the second wrapper, because
# double-wrapping every widget constructor is a measured cause of
# instability. That refusal was written as a bare boolean flag, and a bare
# flag cannot tell two different situations apart:
#
#     a SECOND instrument stacking on the first     the real hazard
#     THIS SAME FILE executed twice by an import    harmless
#
# `tests/` has no `__init__.py`, so pytest loads the conftest under its own
# plugin name and `from tests.conftest import painted/ink` -- which four
# tests in three files do -- imports the SAME FILE again under a second
# module name and re-runs it at module level. Measured on the four:
#
#     census OFF   4 passed     `_CENSUS_PATH is None`, returns early
#     census ON    4 failed     RuntimeError from the guard
#
# So the instrument reddened the suite exactly when switched on, which is
# the hazard it exists to prevent, restated. It shipped in `68aa89e` and
# survived because nobody had run the full suite with the census enabled.
#
# BOTH HALVES ARE GUARDED AND THE NARROW ONE IS LOAD-BEARING. "Never raise"
# satisfies the first test and silently deletes the stacked-instrument
# protection, which is the thing the hazard is actually about.


def _census_stand_in(source):
    """A stand-in for an already-installed census, tagged with `source`."""

    def already_wrapped(self, *args, **kwargs):  # pragma: no cover - never called
        raise AssertionError("the stand-in constructor must not run")

    already_wrapped._openchem_census = source
    return already_wrapped


def _conftest_source():
    """The path `_start_census` compares against, spelled the same way."""
    import os
    import pathlib

    return os.path.realpath(pathlib.Path(__file__).with_name("conftest.py"))


def _reimport_conftest(monkeypatch, trail, installed_by):
    """Re-execute `conftest.py` with a census reported as already installed."""
    import importlib
    import sys

    from PySide6.QtWidgets import QWidget

    monkeypatch.setenv("OPENCHEM_CENSUS", str(trail))
    monkeypatch.setattr(QWidget, "__init__", _census_stand_in(installed_by))
    monkeypatch.delitem(sys.modules, "tests.conftest", raising=False)
    return importlib.import_module("tests.conftest")


def test_re_executing_this_conftest_does_not_raise(qapp, monkeypatch, tmp_path):
    """The wide half: importing `tests.conftest` again is not a second census.

    Exercised through a REAL re-import rather than by calling
    `_start_census` directly, because the import is the route the four
    failing tests take and a direct call would not prove that route is
    safe.
    """
    trail = tmp_path / "census.txt"

    module = _reimport_conftest(monkeypatch, trail, _conftest_source())

    # It returned early, so it neither installed a second wrapper nor
    # opened the trail. The `open()` is `"w"`, so reaching it would have
    # TRUNCATED a running census -- destroying the evidence the instrument
    # exists to preserve, in exactly the crash case where it is the only
    # evidence there is.
    assert module._census_handle == []
    assert not trail.exists()


def test_a_census_installed_by_another_file_still_raises(qapp, monkeypatch, tmp_path):
    """The narrow half, and the one a blanket "never raise" would delete.

    Asserted through the same import route as its sibling so the two
    differ in exactly one input: who installed the existing wrapper.
    """
    with pytest.raises(RuntimeError, match="already census-wrapped"):
        _reimport_conftest(
            monkeypatch,
            tmp_path / "census.txt",
            "/some/other/plugin/conftest.py",
        )


def test_the_stand_in_really_is_what_start_census_compares_against(qapp):
    """Assert the setup, so neither guard above can go vacuous.

    If `_CENSUS_SOURCE` is ever spelled differently from what
    `_conftest_source()` builds, the wide test would pass for the wrong
    reason -- it would be exercising the RAISE branch and asserting
    against a module that never loaded.
    """
    import sys

    loaded = [
        module
        for name, module in list(sys.modules.items())
        if name.rsplit(".", 1)[-1] == "conftest"
        and getattr(module, "_CENSUS_SOURCE", None) is not None
    ]
    assert loaded, "no loaded conftest exposes _CENSUS_SOURCE"
    assert all(module._CENSUS_SOURCE == _conftest_source() for module in loaded)


def test_no_test_file_derives_the_disposal_recipe_for_itself():
    """`setParent(None)` + `deleteLater()` + a flush lives in ONE place.

    Those three lines were copy-pasted across 46 test files under at
    least six names. `git show dba03eb:benchmarks/disposal/inventory.md`
    is what that looked like, measured before any of it was touched: 64
    sequences, 8 distinct. This repository has paid four times for two
    implementations of one idea drifting, and forty-six is worse than
    two.

    IT IS AN AST WALK AND NOT A TEXT SCAN, for the reason
    `test_no_test_file_derives_the_platform_gate_for_itself` already
    gives: the prose explaining this rule -- this docstring included --
    names the three calls, and a text search flags it.

    WHAT IT DELIBERATELY DOES NOT CATCH is a sequence that is not this
    recipe. `tests/test_pop_out_host.py` closes a window and forces Qt's
    own posted delete precisely to assert the CONTENT survived: that is
    the test's subject, not its cleanup, and consolidating it would
    destroy the thing under test. `benchmarks/disposal/inventory.md`
    lists every survivor, so "what is left" is a reviewable number rather
    than a hole.
    """
    import sys
    from pathlib import Path

    tools = Path(__file__).resolve().parent.parent / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    from disposal_inventory import CANONICAL, collect  # noqa: E402

    offenders = [
        f"{s['file']}:{s['line']}"
        for s in collect()
        if s["names"][-3:] == CANONICAL and not s["file"].endswith("conftest.py")
    ]
    assert not offenders, (
        "these re-derive the disposal recipe instead of calling "
        f"conftest.dispose(): {offenders}"
    )


def test_the_recipe_really_is_findable_and_this_guard_is_not_vacuous():
    """Assert the setup: the walker must SEE `conftest.dispose` itself.

    Without this, a walker that silently returned nothing -- a changed
    AST shape, a moved `tests/` -- would satisfy the guard above forever
    while the tree filled back up with copies. A green
    "no offenders" and "the walk found nothing to walk" read identically
    in an empty list, which is the population assertion `ui/visual_check`
    already records needing.
    """
    import sys
    from pathlib import Path

    tools = Path(__file__).resolve().parent.parent / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    from disposal_inventory import CANONICAL, collect  # noqa: E402

    from disposal_inventory import sequences_in_source  # noqa: E402

    assert collect(), "the walker found no disposal sequences in tests/ at all"

    # ON CONSTRUCTED SOURCE, not on whatever the tree happens to hold. An
    # earlier version of this located `conftest.dispose` and asserted the
    # walk found it -- and broke the moment that function grew an `if`
    # around its flush for the experiment, which is a refactor and not a
    # regression. What must never change is that the walk can recognise
    # the recipe when it is there.
    planted = sequences_in_source(
        """
def teardown(widget):
    widget.setParent(None)
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)
""",
        "<constructed>",
    )
    assert [s for s in planted if s["names"][-3:] == CANONICAL], (
        "the walker cannot recognise the recipe even when handed it, so the "
        "guard above would pass against a tree full of copies"
    )

    # ...and the CONTROL: a sequence that merely RESEMBLES it is not it.
    # Without this the guard above is satisfied by a walker that calls
    # everything canonical, which would make the offender test fire on
    # every file in the tree.
    near_miss = sequences_in_source(
        """
def teardown(widget):
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)
""",
        "<constructed>",
    )
    assert not [s for s in near_miss if s["names"][-3:] == CANONICAL]


def test_the_shipped_disposal_still_flushes_by_default():
    """The control arm is what the suite runs unless told otherwise.

    `OPENCHEM_DISPOSE_FLUSH` exists to A/B the one line both Linux frames
    of ours name. A switch whose default drifted would silently make
    every ordinary run the EXPERIMENTAL arm, and nothing else would say
    so -- the crash it changes is 50/50 either way, so no outcome could
    reveal it.
    """
    import conftest

    assert conftest.FLUSH_AT_DISPOSE is True


@pytest.mark.parametrize(
    "value, flushes",
    [
        (None, True),  # unset: the shipped behaviour
        ("1", True),
        ("0", False),  # the treatment arm, and the ONLY value that turns it off
        ("", True),
        ("false", True),  # NOT a synonym for "0" -- see the docstring
        ("nonsense", True),
    ],
)
def test_only_the_exact_string_zero_turns_the_flush_off(value, flushes):
    """Fail SAFE, onto the shipped behaviour.

    A truthy-string parse (`"false"` -> off) would let a typo in a
    workflow put an ordinary run into the treatment arm. Tested on the
    pure function so it needs no environment manipulation.
    """
    import conftest

    assert conftest.flush_at_dispose(value) is flushes
