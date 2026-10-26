"""What the frozen smoke test asks of the running application (pure; no Qt).

`benchmarks/visual/frozen_smoke.json` is run against the BUILT exe by
`tools/frozen_smoke.py`. Two of its steps need facts only the live process has:
where the help text came from, and what the install self-check concluded. They
are read here from the running modules, never inferred from source text: a
release that quietly read loose files, or never finished its integrity check,
would pass every other step.

Every comparison fails closed. An expectation key this module does not know is a
failure (a typo must not silently assert nothing), a state field that could not
be read is a failure, and a check that is still `checking` when its time runs out
is a failure.
"""

from __future__ import annotations

from typing import Any

_HELP_KEYS = {"source", "documents", "topics_at_least", "panel_keys_resolve", "search"}
_INSTALL_KEYS = {"status", "checked_at_least"}


def panel_help_keys() -> list[str]:
    """Every help topic key a panel or centre tab points at (what F1 would open)."""
    from openchem.app import main_window

    keys: set[str] = set()
    for table in (
        main_window.HELP_TOPIC_BY_DOCK,
        main_window.HELP_TOPIC_BY_PLUGIN_DOCK,
        main_window.HELP_TOPIC_BY_CENTRE_TAB,
    ):
        keys.update(str(value) for value in table.values())
    return sorted(keys)


def help_state(query: str = "") -> dict[str, Any]:
    """The help system as the running process sees it. Never raises."""
    from openchem import help as help_docs

    state: dict[str, Any] = {}
    try:
        state["source"] = help_docs.content_source()
        loaded = 0
        for name in help_docs.HELP_DOCUMENTS:
            if help_docs.document_text(name).strip():
                loaded += 1
        state["documents"] = loaded
        state["topics"] = len(help_docs.topics())
        unresolved = []
        for key in panel_help_keys():
            try:
                if not help_docs.topic_markdown(key).strip():
                    unresolved.append(key)
            except help_docs.HelpUnavailable:
                unresolved.append(key)
        state["unresolved_keys"] = unresolved
        if query:
            state["search_query"] = query
            state["search_hits"] = len(help_docs.search(query))
    except Exception as exc:  # noqa: BLE001 - a broken help is the finding, not a crash of the driver
        state["error"] = f"{type(exc).__name__}: {exc}"
    return state


def evaluate_help(expect: dict[str, Any], state: dict[str, Any]) -> list[str]:
    """Why `state` does not meet `expect`; empty means it does."""
    failures = [f"unknown expectation {key!r}" for key in expect if key not in _HELP_KEYS]
    if "error" in state:
        return failures + [f"the help could not be read: {state['error']}"]
    if "source" in expect and state.get("source") != expect["source"]:
        failures.append(f"help source is {state.get('source')!r}, expected {expect['source']!r}")
    if "documents" in expect and state.get("documents") != expect["documents"]:
        failures.append(f"{state.get('documents')!r} help documents loaded, expected {expect['documents']}")
    if "topics_at_least" in expect and not state.get("topics", 0) >= expect["topics_at_least"]:
        failures.append(f"{state.get('topics')!r} topics, expected at least {expect['topics_at_least']}")
    if expect.get("panel_keys_resolve") and state.get("unresolved_keys") != []:
        failures.append(f"panel help keys that do not resolve: {state.get('unresolved_keys')!r}")
    search = expect.get("search")
    if search is not None:
        if state.get("search_query") != search.get("query"):
            failures.append("the search was not run for the expected query")
        elif not state.get("search_hits", 0) >= search.get("hits_at_least", 1):
            failures.append(f"search {search.get('query')!r} found {state.get('search_hits')!r} topics")
    return failures


def install_state() -> dict[str, Any]:
    """The install self-check's latest answer. Never raises."""
    from openchem import install_check

    try:
        result = install_check.current()
        return {
            "status": result.status.value,
            "checked": result.checked,
            "problems": result.problems,
            "detail": result.detail,
            "summary": result.summary(),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


def install_pending(state: dict[str, Any]) -> bool:
    """True while the check has not answered yet, so the step keeps waiting."""
    return state.get("status") == "checking"


def evaluate_install(expect: dict[str, Any], state: dict[str, Any]) -> list[str]:
    failures = [f"unknown expectation {key!r}" for key in expect if key not in _INSTALL_KEYS]
    if "error" in state:
        return failures + [f"the install check could not be read: {state['error']}"]
    if install_pending(state):
        failures.append("the install check had not finished")
    if "status" in expect and state.get("status") != expect["status"]:
        failures.append(f"install check is {state.get('status')!r} ({state.get('summary')}), expected {expect['status']!r}")
    if "checked_at_least" in expect and not state.get("checked", 0) >= expect["checked_at_least"]:
        failures.append(f"{state.get('checked')!r} files checked, expected at least {expect['checked_at_least']}")
    return failures
