"""The Setup guide is held to the tool catalogue, so a new tool cannot ship without guidance, and to the
links and Help topics that exist, so it cannot point somewhere dead."""

from __future__ import annotations

import re
from html import escape

import pytest

from openchem import help as help_content
from openchem.app.settings import Settings
from openchem.events.base import EventBus
from openchem.ui.dialogs import external_tool_guide as guide
from openchem.ui.dialogs.external_tools_pages import ExternalToolsPages

_HOST = re.compile(r"^https://[A-Za-z0-9.-]+/")


@pytest.fixture
def pages(qapp):
    return ExternalToolsPages(Settings(EventBus()))


def test_every_tool_tab_has_exactly_one_guide_row_and_no_row_is_orphaned(pages):
    tabs = sorted(tab.descriptor.key for tab in pages._tool_tabs)
    rows = sorted(entry.key for entry in guide.GUIDE)
    assert rows == tabs


def test_every_row_says_what_it_is_what_needs_it_and_what_to_do(pages):
    for entry in guide.GUIDE:
        assert entry.tier in (guide.RECOMMENDED, guide.OPTIONAL, guide.ADVANCED), entry.key
        for field in (entry.what, entry.needed_for, entry.next_step):
            assert len(field.strip()) > 20, entry.key


def test_every_help_link_names_a_topic_that_exists_and_every_other_link_is_https():
    topics = {topic.key for topic in help_content.topics()}
    for entry in guide.GUIDE:
        for link in entry.links:
            if link.target.startswith("help:"):
                assert link.target[5:] in topics, (entry.key, link.target)
            else:
                assert _HOST.match(link.target), (entry.key, link.target)


def test_the_footer_topics_exist():
    topics = {topic.key for topic in help_content.topics()}
    assert guide.HELP_TOOLS in topics and guide.HELP_INSTALLING in topics


def test_every_task_names_only_tools_that_have_a_row():
    rows = {entry.key for entry in guide.GUIDE}
    for label, keys in guide.TASKS:
        assert set(keys) <= rows, label


def test_a_row_shows_the_tool_tabs_own_status_not_a_recomputed_one(pages):
    statuses = pages._guide_statuses()
    for tab in pages._tool_tabs:
        title, status = statuses[tab.descriptor.key]
        assert title == tab.descriptor.title
        assert status == " ".join(tab.status_label.text().split())
        # The row is rendered from it, escaped (an apostrophe or ampersand in a status is data, not markup).
        assert escape(status) in pages._guide._rows[tab.descriptor.key].text()


def test_the_task_filter_shows_only_the_tools_that_task_needs(pages):
    combo = pages._guide.task_combo
    index = [label for label, _ in guide.TASKS].index("Dock a molecule into a protein")
    combo.setCurrentIndex(index)
    shown = {key for key, frame in pages._guide._frames.items() if not frame.isHidden()}
    assert shown == {"vina"}
    combo.setCurrentIndex(0)
    assert {key for key, frame in pages._guide._frames.items() if not frame.isHidden()} == {
        entry.key for entry in guide.GUIDE
    }


def test_a_row_cannot_inject_markup_through_its_text():
    entry = guide.GuideEntry(
        key="x", tier=guide.OPTIONAL, what="<script>1</script>", needed_for="a&b", next_step="c" * 30
    )
    html = guide.row_html(entry, "<b>T</b>", "<i>s</i>")
    assert "<script>" not in html and "<i>s</i>" not in html and "<b>T</b>" not in html


def test_the_links_in_a_row_reach_the_right_handler(qapp):
    seen: list[tuple[str, str]] = []
    tab = guide.GuideTab(
        None,
        statuses=lambda: {},
        open_tab=lambda key: seen.append(("tab", key)),
        open_help=lambda key: seen.append(("help", key)),
        open_url=lambda url: seen.append(("url", url)),
    )
    tab._on_link("tab:orca")
    tab._on_link("help:external-tools")
    tab._on_link("https://example.org/x")
    tab._on_link("javascript:alert(1)")
    tab._on_link("file:///C:/Windows")
    assert seen == [("tab", "orca"), ("help", "external-tools"), ("url", "https://example.org/x")]


def test_the_guide_can_be_reached_by_key_and_by_a_tool_link(pages):
    pages.show_tool("orca")
    assert pages.current_tool() == "orca"
    pages.show_tool(guide.GUIDE_KEY)
    assert pages._tabs.currentWidget() is pages._guide
    pages._guide._on_link("tab:xtb")
    assert pages.current_tool() == "xtb"
