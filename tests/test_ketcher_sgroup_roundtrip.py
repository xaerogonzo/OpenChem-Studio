"""Probe: do molfile S-groups survive Ketcher addFragment and getMolfile?

Polymer templates are parked until this is measured. The fixture molfiles
carry ``M  STY`` lines; the editor's persistence path is ``getMolfile``.
The first run filled ``FINDING_ADD_FRAGMENT`` and ``FINDING_LOAD``; the
assertions hold that measurement so a Ketcher upgrade cannot silently change it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rdkit import Chem

from openchem.chem.structure_templates import molblock_for
from openchem.domain.structure_template import TemplateEntry, TemplateError

from tests.test_ketcher_editor_backend import (
    _get_molblock_sync,
    _ready_backend,
    _run_js,
    _wait_until,
)
from tests.test_template_insert import _wait_callback

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ketcher"

# Measured 2026-11-14 on the vendored Ketcher bundle.
# addFragment then getMolfile strips ``M  STY`` (the drawing remains).
# setMolecule then getMolfile keeps SRU and SUP.
FINDING_ADD_FRAGMENT: dict[str, tuple[str, ...] | None] = {
    "propane_sru.mol": (),
    "propane_sup.mol": (),
}
FINDING_LOAD: dict[str, tuple[str, ...] | None] = {
    "propane_sru.mol": ("SRU",),
    "propane_sup.mol": ("SUP",),
}


def _sty_kinds(molblock: str) -> tuple[str, ...]:
    kinds: list[str] = []
    for line in molblock.splitlines():
        if line.startswith("M  STY"):
            # M  STY  n  idx type [idx type ...]
            parts = line.split()
            for i in range(4, len(parts), 2):
                kinds.append(parts[i])
    return tuple(kinds)


def _read_kinds(molblock: str) -> tuple[str, ...] | None:
    if not molblock.strip():
        return None
    return _sty_kinds(molblock)


def _rdkit_sgroup_types(molblock: str) -> tuple[str, ...]:
    mol = Chem.MolFromMolBlock(molblock, sanitize=False, removeHs=False)
    if mol is None:
        return ()
    return tuple(sg.GetProp("TYPE") for sg in Chem.GetMolSubstanceGroups(mol) if sg.HasProp("TYPE"))


def test_fixture_molfiles_carry_the_s_groups_the_probe_names():
    for name, expected in (("propane_sru.mol", ("SRU",)), ("propane_sup.mol", ("SUP",))):
        text = (FIXTURES / name).read_text(encoding="utf-8")
        assert _sty_kinds(text) == expected
        assert _rdkit_sgroup_types(text) == expected


def test_molblock_for_still_refuses_an_s_group_fixture():
    molblock = (FIXTURES / "propane_sru.mol").read_text(encoding="utf-8")
    entry = TemplateEntry(id="x", name="x", category_id="x", molblock=molblock)
    with pytest.raises(TemplateError, match="S-groups"):
        molblock_for(entry)


def test_add_fragment_then_get_molfile_keeps_or_drops_s_groups_as_measured(qapp):
    backend = _ready_backend(qapp)
    assert _run_js(qapp, backend, "typeof window.ketcher.addFragment") == "function"
    measured: dict[str, tuple[str, ...] | None] = {}
    for name in FINDING_ADD_FRAGMENT:
        molblock = (FIXTURES / name).read_text(encoding="utf-8")
        backend.load_molblock("")
        error = _wait_callback(qapp, lambda cb, mb=molblock: backend.add_fragment(mb, cb))
        assert error is None, (name, error)
        returned = _get_molblock_sync(qapp, backend, timeout_seconds=10) or ""
        assert "V2000" in returned or "V3000" in returned, (name, returned[:200])
        measured[name] = _read_kinds(returned)
    assert measured == FINDING_ADD_FRAGMENT, (
        "Ketcher addFragment S-group round-trip changed. Re-run this file on the "
        f"vendored bundle and update FINDING_ADD_FRAGMENT. got={measured!r}"
    )


def test_load_molblock_then_get_molfile_keeps_or_drops_s_groups_as_measured(qapp):
    backend = _ready_backend(qapp)
    measured: dict[str, tuple[str, ...] | None] = {}
    for name in FINDING_LOAD:
        molblock = (FIXTURES / name).read_text(encoding="utf-8")
        backend.load_molblock(molblock)
        _wait_until(qapp, lambda: False, timeout_seconds=1.0)
        returned = _get_molblock_sync(qapp, backend, timeout_seconds=10) or ""
        measured[name] = _read_kinds(returned)
    assert measured == FINDING_LOAD, (
        "Ketcher setMolecule S-group round-trip changed. Re-run this file on the "
        f"vendored bundle and update FINDING_LOAD. got={measured!r}"
    )
