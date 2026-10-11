"""`HeightStatingHost`: a workflow in the Properties list must not be squeezed.

The defect was measured in the running app: the alignment section asked for 1102 px
and was given 551, and its rows were squeezed to a few pixels. These tests pin the
contract that ends it: the host states the child's real height at its real width as a
plain size hint, offers no height-for-width to the layout above, and restates when the
child's content changes.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import conftest
from openchem.ui.widgets.height_stating_host import HeightStatingHost


def _wrapping_child() -> QWidget:
    child = QWidget()
    layout = QVBoxLayout(child)
    label = QLabel("word " * 200)
    label.setWordWrap(True)
    layout.addWidget(label)
    child.label = label
    return child


def _host(qapp, width=300):
    host = HeightStatingHost(_wrapping_child())
    host.resize(width, 50)
    host.show()
    qapp.processEvents()
    return host


def test_it_states_a_height_and_offers_no_height_for_width(qapp):
    host = _host(qapp)
    try:
        assert host.hasHeightForWidth() is False
        assert host.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Fixed
        assert host.stated_height() > 0
        assert host.sizeHint().height() == host.stated_height()
        assert host.minimumSizeHint().height() == host.stated_height()
    finally:
        conftest.dispose(host)


def test_the_stated_height_is_the_height_the_child_needs_at_this_width(qapp):
    host = _host(qapp, width=300)
    try:
        needed = host.child.layout().heightForWidth(host.width())
        assert host.stated_height() >= needed
    finally:
        conftest.dispose(host)


def test_a_narrower_host_states_a_taller_height(qapp):
    """Wrapped text needs more lines in less width; the host must follow it."""
    host = _host(qapp, width=400)
    try:
        wide = host.stated_height()
        host.resize(180, host.height())
        qapp.processEvents()
        assert host.stated_height() > wide
    finally:
        conftest.dispose(host)


def test_it_restates_when_the_childs_content_changes(qapp):
    host = _host(qapp)
    try:
        before = host.stated_height()
        host.child.label.setText("word " * 600)
        qapp.processEvents()
        assert host.stated_height() > before
    finally:
        conftest.dispose(host)


def test_showing_a_hidden_child_widget_grows_the_stated_height(qapp):
    """The alignment section's case: a table and a picture that appear after a run."""
    child = QWidget()
    layout = QVBoxLayout(child)
    layout.addWidget(QLabel("settings"))
    later = QWidget()
    later.setMinimumHeight(300)
    layout.addWidget(later)
    later.setVisible(False)
    host = HeightStatingHost(child)
    host.resize(300, 50)
    host.show()
    qapp.processEvents()
    try:
        before = host.stated_height()
        later.setVisible(True)
        qapp.processEvents()
        assert host.stated_height() >= before + 300
    finally:
        conftest.dispose(host)


def test_a_list_of_hosts_is_never_given_less_than_each_one_states(qapp):
    """The measured failure, reproduced small: a scroll area holding a few hosts whose
    children wrap text. Every host must be at least as tall as it states."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    holder = QWidget()
    layout = QVBoxLayout(holder)
    hosts = [HeightStatingHost(_wrapping_child()) for _ in range(3)]
    for host in hosts:
        layout.addWidget(host)
    layout.addStretch()
    area.setWidget(holder)
    area.resize(320, 400)
    area.show()
    qapp.processEvents()
    qapp.processEvents()
    try:
        for host in hosts:
            assert host.height() >= host.stated_height() > 0
    finally:
        conftest.dispose(area)
