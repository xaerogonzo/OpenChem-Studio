"""What the planner's configuration offers, for the synthesis panel's three lists (`SetupProvider.options` and `is_warm`): read once per file, off the GUI thread, and never a silent fallback when a chosen name is not there.

Uses the stand-ins of `test_synthesis_planner_setup.py`."""

from __future__ import annotations

import os
from pathlib import Path

from test_synthesis_planner_setup import FakeSettings, configured, good_inspector, inspection

from openchem.chem import aizynth_planner as host
from openchem.services import synthesis_planner_setup as setup


def never_called(*args):
    raise AssertionError("the planner's Python must not be started for this")


def test_options_before_both_paths_are_set_says_what_to_set_and_starts_nothing(tmp_path):
    provider = setup.SetupProvider(FakeSettings(), inspector=never_called)
    options = provider.options()
    assert options.ok is False and options.problem.startswith("Not configured") and options.expansion == () and options.chosen_expansion is None
    assert provider.is_warm() is False

    settings, _, _ = configured(tmp_path)
    settings.set(setup.CONFIG_KEY, str(tmp_path / "gone.yml"))
    assert setup.SetupProvider(settings, inspector=never_called).options().problem == f"Configuration file not found at {tmp_path / 'gone.yml'}"


def test_options_lists_what_the_configuration_offers_and_what_is_chosen(tmp_path):
    settings, _, config = configured(tmp_path)
    provider = setup.SetupProvider(settings, inspector=lambda p, c: inspection(expansion=("ring", "uspto"), stock=("zinc", "mine"), filters=("uspto",), config=config))

    options = provider.options()

    assert options.ok is True and options.problem == "" and options.version == "4.4.1"
    assert (options.expansion, options.stock, options.filters) == (("ring", "uspto"), ("zinc", "mine"), ("uspto",))
    assert (options.chosen_expansion, options.chosen_stock, options.chosen_filter) == ("uspto", "zinc", None)  # no filter unless one is chosen


def test_options_follows_the_settings_the_panel_writes(tmp_path):
    settings, _, config = configured(tmp_path)
    provider = setup.SetupProvider(settings, inspector=lambda p, c: inspection(expansion=("ring", "uspto"), stock=("zinc", "mine"), filters=("uspto",), config=config))
    provider.options()
    settings.set(setup.EXPANSION_KEY, "ring")
    settings.set(setup.FILTER_KEY, "uspto")
    options = provider.options()
    assert (options.chosen_expansion, options.chosen_filter) == ("ring", "uspto")
    settings.set(setup.FILTER_KEY, "none")
    assert provider.options().chosen_filter is None


def test_a_chosen_name_the_configuration_lacks_is_a_problem_and_the_lists_are_still_given(tmp_path):
    settings, _, config = configured(tmp_path, aizynthfinder__stock="nope")
    options = setup.SetupProvider(settings, inspector=good_inspector(config)).options()
    assert options.ok is False and options.problem.startswith("The configuration has no stock named 'nope'") and options.problem.endswith(".")
    assert options.stock == ("zinc",) and options.expansion == ("uspto",)  # so the person can pick one that is there


def test_a_named_file_that_is_not_there_is_the_problem(tmp_path):
    settings, paths, config = configured(tmp_path)
    paths["stock.txt"].unlink()
    options = setup.SetupProvider(settings, inspector=good_inspector(config)).options()
    assert options.ok is False and "The stock file is not there" in options.problem and str(paths["stock.txt"]) in options.problem


def test_an_environment_that_does_not_answer_is_explained_the_way_the_test_button_does(tmp_path):
    settings, _, _ = configured(tmp_path)
    failing = lambda p, c: host.PlannerInspection(ok=False, kind="planner", reason="x")  # noqa: E731
    options = setup.SetupProvider(settings, inspector=failing).options()
    assert options.ok is False and "AiZynthFinder is not installed in" in options.problem and options.expansion == ()


def test_is_warm_says_whether_a_request_would_wait(tmp_path):
    settings, _, config = configured(tmp_path)
    calls = []

    def counting(python, config_path):
        calls.append(config_path)
        return inspection(config=config)

    provider = setup.SetupProvider(settings, inspector=counting)
    assert provider.is_warm() is False and calls == []  # asking starts nothing
    provider.options()
    assert provider.is_warm() is True and len(calls) == 1
    provider()  # a request now reads the cached reading
    provider.options()
    assert len(calls) == 1

    config_path = Path(settings.get(setup.CONFIG_KEY))
    stat = config_path.stat()
    os.utime(config_path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    assert provider.is_warm() is False  # the file changed, so the next request would read it again
    settings.set(setup.PYTHON_KEY, str(tmp_path / "gone.exe"))
    assert provider.is_warm() is False


def test_a_failed_reading_leaves_it_cold(tmp_path):
    settings, _, _ = configured(tmp_path)
    provider = setup.SetupProvider(settings, inspector=lambda p, c: host.PlannerInspection(ok=False, kind="planner", reason="x"))
    provider.options()
    assert provider.is_warm() is False


def test_the_container_hands_the_panel_the_provider_the_service_reads(qapp):
    from openchem.bootstrap import build_service_container

    services = build_service_container()
    assert services.synthesis_setup is not None and services.synthesis_setup is services.synthesis_planning_service._setup_provider
