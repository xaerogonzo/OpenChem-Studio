"""Probe: do connected coordination drawings survive Ketcher addFragment and getMolfile?

PubChem stores ferrocene and cisplatin as disconnected ions; these fixtures
are connected drawings (cis- and trans-PtCl2(NH3)2 with dative N->Pt;
carboplatin and oxaliplatin with dative N/O->Pt; cis-PtCl2(en); ferrocene
as Fe bound to both Cp rings). Template insert uses
``addFragment``; load uses ``setMolecule``. The first run filled
``FINDING_ADD_FRAGMENT`` and ``FINDING_LOAD``; the assertions hold that
measurement so a Ketcher upgrade cannot silently change it.
"""

from __future__ import annotations

import math
from pathlib import Path

from rdkit import Chem

from openchem.chem.engine import ChemistryEngine
from openchem.chem.structure_templates import molblock_for
from openchem.domain.structure_template import TemplateEntry

from tests.test_ketcher_editor_backend import (
    _get_molblock_sync,
    _ready_backend,
    _run_js,
    _wait_until,
)
from tests.test_template_insert import _wait_callback

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ketcher"

METALS = frozenset({"Fe", "Pt"})

# (n_fragments, metal_symbols, bonds_to_metal, dative_bonds_to_metal, cl_pt_cl)
# cl_pt_cl is "cis" | "trans" | "unknown" | None (not cisplatin).
Fact = tuple[int, tuple[str, ...], int, int, str | None]

FIXTURE_FACTS: dict[str, Fact] = {
    "cisplatin_cis.mol": (1, ("Pt",), 4, 2, "cis"),
    "transplatin.mol": (1, ("Pt",), 4, 2, "trans"),
    "carboplatin.mol": (1, ("Pt",), 4, 4, None),
    "oxaliplatin.mol": (1, ("Pt",), 4, 4, None),
    "cis_ptcl2_en.mol": (1, ("Pt",), 4, 2, "cis"),
    "ferrocene.mol": (1, ("Fe",), 10, 0, None),
}

# Measured 2026-11-15 (cisplatin, transplatin, ferrocene) and 2026-11-21
# (carboplatin, oxaliplatin, cis-PtCl2(en)) on the vendored Ketcher bundle
# (Indigo writer). addFragment keeps the five square-planar Pt drawings
# and returns an empty molfile for ferrocene, with no error.
# setMolecule keeps all six drawings, including ferrocene's ten Fe-C bonds.
FINDING_ADD_FRAGMENT: dict[str, Fact | tuple[str, ...] | None] = {
    "cisplatin_cis.mol": (1, ("Pt",), 4, 2, "cis"),
    "transplatin.mol": (1, ("Pt",), 4, 2, "trans"),
    "carboplatin.mol": (1, ("Pt",), 4, 4, None),
    "oxaliplatin.mol": (1, ("Pt",), 4, 4, None),
    "cis_ptcl2_en.mol": (1, ("Pt",), 4, 2, "cis"),
    "ferrocene.mol": (0, (), 0, 0, None),
}
FINDING_LOAD: dict[str, Fact | tuple[str, ...] | None] = {
    "cisplatin_cis.mol": (1, ("Pt",), 4, 2, "cis"),
    "transplatin.mol": (1, ("Pt",), 4, 2, "trans"),
    "carboplatin.mol": (1, ("Pt",), 4, 4, None),
    "oxaliplatin.mol": (1, ("Pt",), 4, 4, None),
    "cis_ptcl2_en.mol": (1, ("Pt",), 4, 2, "cis"),
    "ferrocene.mol": (1, ("Fe",), 10, 0, None),
}


def _angle_deg(mol: Chem.Mol, centre: int, a: int, b: int) -> float | None:
    if mol.GetNumConformers() == 0:
        return None
    conf = mol.GetConformer()
    c = conf.GetAtomPosition(centre)
    pa = conf.GetAtomPosition(a)
    pb = conf.GetAtomPosition(b)
    va = (pa.x - c.x, pa.y - c.y)
    vb = (pb.x - c.x, pb.y - c.y)
    na = math.hypot(*va)
    nb = math.hypot(*vb)
    if na < 1e-6 or nb < 1e-6:
        return None
    cosine = max(-1.0, min(1.0, (va[0] * vb[0] + va[1] * vb[1]) / (na * nb)))
    return math.degrees(math.acos(cosine))


def _cl_pt_cl(mol: Chem.Mol) -> str | None:
    pts = [a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "Pt"]
    cls = [a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "Cl"]
    if len(pts) != 1 or len(cls) != 2:
        return None
    angle = _angle_deg(mol, pts[0], cls[0], cls[1])
    if angle is None:
        return "unknown"
    if 50.0 <= angle <= 130.0:
        return "cis"
    if angle >= 150.0:
        return "trans"
    return "unknown"


def _facts(molblock: str) -> Fact | tuple[str, ...] | None:
    if not molblock.strip():
        return None
    mol = Chem.MolFromMolBlock(molblock, sanitize=False, removeHs=False)
    if mol is None:
        return ("unparsed",)
    mol.UpdatePropertyCache(strict=False)
    fragments = Chem.GetMolFrags(mol)
    metals = tuple(a.GetSymbol() for a in mol.GetAtoms() if a.GetSymbol() in METALS)
    metal_bonds = 0
    dative = 0
    for bond in mol.GetBonds():
        begin, end = bond.GetBeginAtom(), bond.GetEndAtom()
        if begin.GetSymbol() not in METALS and end.GetSymbol() not in METALS:
            continue
        metal_bonds += 1
        if bond.GetBondType() == Chem.BondType.DATIVE:
            dative += 1
    return (len(fragments), metals, metal_bonds, dative, _cl_pt_cl(mol))


def test_fixture_molfiles_are_connected_coordination_drawings():
    for name, expected in FIXTURE_FACTS.items():
        text = (FIXTURES / name).read_text(encoding="utf-8")
        assert _facts(text) == expected, (name, _facts(text))


def test_molblock_for_accepts_the_coordination_fixtures():
    engine = ChemistryEngine()
    for name in FIXTURE_FACTS:
        molblock = (FIXTURES / name).read_text(encoding="utf-8")
        entry = TemplateEntry(id=name, name=name, category_id="x", molblock=molblock)
        prepared = molblock_for(entry, engine)
        assert "V2000" in prepared or "V3000" in prepared
        facts = _facts(prepared)
        assert isinstance(facts, tuple) and facts[0] == 1
        assert facts[1] == FIXTURE_FACTS[name][1]


def test_add_fragment_then_get_molfile_keeps_or_drops_coordination_as_measured(qapp):
    backend = _ready_backend(qapp)
    assert _run_js(qapp, backend, "typeof window.ketcher.addFragment") == "function"
    measured: dict[str, Fact | tuple[str, ...] | None] = {}
    for name in FINDING_ADD_FRAGMENT:
        molblock = (FIXTURES / name).read_text(encoding="utf-8")
        backend.load_molblock("")
        error = _wait_callback(qapp, lambda cb, mb=molblock: backend.add_fragment(mb, cb))
        assert error is None, (name, error)
        returned = _get_molblock_sync(qapp, backend, timeout_seconds=10) or ""
        assert "V2000" in returned or "V3000" in returned, (name, returned[:200])
        measured[name] = _facts(returned)
    assert measured == FINDING_ADD_FRAGMENT, (
        "Ketcher addFragment coordination round-trip changed. Re-run this file on the "
        f"vendored bundle and update FINDING_ADD_FRAGMENT. got={measured!r}"
    )


def test_load_molblock_then_get_molfile_keeps_or_drops_coordination_as_measured(qapp):
    backend = _ready_backend(qapp)
    measured: dict[str, Fact | tuple[str, ...] | None] = {}
    for name in FINDING_LOAD:
        molblock = (FIXTURES / name).read_text(encoding="utf-8")
        backend.load_molblock(molblock)
        _wait_until(qapp, lambda: False, timeout_seconds=1.0)
        returned = _get_molblock_sync(qapp, backend, timeout_seconds=10) or ""
        measured[name] = _facts(returned)
    assert measured == FINDING_LOAD, (
        "Ketcher setMolecule coordination round-trip changed. Re-run this file on the "
        f"vendored bundle and update FINDING_LOAD. got={measured!r}"
    )
