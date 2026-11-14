"""WP5 of docs/HYPERVALENT_COVERAGE_DESIGN.md: the three graph-theory calculators on a held hypervalent structure, held to a second implementation.

`topology_analysis`, `topology_eccentricity` and `topology_distance_degree` are arithmetic on the heavy-atom graph, so the oracle is this file's own breadth-first
search and the textbook definition of each index, written independently of RDKit and of `chem/topology_analysis.py`. They were refused on a held structure because
topology analysis counted one chiral centre for SF6 (WP2 fixed that); the panel includes held structures with a ring, an aromatic ring and a stereocentre, since a held
centre can carry an organic group on an oxygen.

NOT verified, and a test says so: geometry analysis (a Dreiding or force-field energy for a centre it has no parameters for), surface analysis, the dipole moment
(0.00 for a T-shaped ClF3, whose dipole is not zero), polarizability, logD and solubility (all read charges or logP that do not exist for these structures).
"""

from __future__ import annotations

import math
from collections import deque

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.bootstrap import build_service_container
from openchem.chem.calculation_input import HYPERVALENT_VERIFIED_CALCULATORS
from openchem.domain.molecule import MoleculeModel
from tests.test_chem_engine import _hypervalent_molblock

PANEL = {
    "ClF3": "FCl(F)F",
    "BrF3": "FBr(F)F",
    "ClF5": "FCl(F)(F)(F)F",
    "ClF3O": "FCl(F)(F)=O",
    "ClF2-O-cyclopropyl": "FCl(F)OC1CC1",
    "ClF2-O-phenyl": "FCl(F)Oc1ccccc1",
    "ClF2-O-chiral": "FCl(F)OC[C@H](F)Cl",
    "BrF2-O-cyclopentyl": "FBr(F)OC1CCCC1",
}


@pytest.fixture(scope="module")
def rig():
    return build_service_container()


def _held(rig, smiles: str) -> Chem.Mol:
    drawn = Chem.MolFromSmiles(smiles, sanitize=False)
    drawn.UpdatePropertyCache(strict=False)
    AllChem.Compute2DCoords(drawn)
    model = MoleculeModel(display_name=smiles)
    rig.chemistry_engine.set_structure_from_molblock(model, Chem.MolToMolBlock(drawn), allow_hypervalent=True)
    return rig.chemistry_engine.mol_from_model(model, allow_hypervalent=True)


def _compute(rig, calculator_id: str, mol: Chem.Mol):
    registry = rig.descriptor_service._calculator_registry
    definition = registry.get(calculator_id)
    params = {p.name: p.default for p in definition.parameters}
    return registry.compute(calculator_id, mol, "u", params)


# --- the oracle: the heavy-atom graph, breadth-first search, the textbook definitions --------------------------------------


def _graph(mol: Chem.Mol) -> dict[int, set[int]]:
    graph: dict[int, set[int]] = {a.GetIdx(): set() for a in mol.GetAtoms()}
    for b in mol.GetBonds():
        graph[b.GetBeginAtomIdx()].add(b.GetEndAtomIdx())
        graph[b.GetEndAtomIdx()].add(b.GetBeginAtomIdx())
    return graph


def _distances(graph: dict[int, set[int]]) -> dict[int, dict[int, int]]:
    out = {}
    for source in graph:
        seen, queue = {source: 0}, deque([source])
        while queue:
            node = queue.popleft()
            for nxt in graph[node]:
                if nxt not in seen:
                    seen[nxt] = seen[node] + 1
                    queue.append(nxt)
        out[source] = seen
    return out


def _weighted_sums(mol: Chem.Mol) -> dict[int, float]:
    """Balaban's distance sums: each bond is as long as 1 / its order (a double bond 1/2, an aromatic bond 1/1.5), shortest paths by Floyd-Warshall."""
    n = mol.GetNumAtoms()
    d = [[0.0 if i == j else math.inf for j in range(n)] for i in range(n)]
    for b in mol.GetBonds():
        i, j = b.GetBeginAtomIdx(), b.GetEndAtomIdx()
        d[i][j] = d[j][i] = 1.0 / b.GetBondTypeAsDouble()
    for k in range(n):
        for i in range(n):
            for j in range(n):
                if d[i][k] + d[k][j] < d[i][j]:
                    d[i][j] = d[i][k] + d[k][j]
    return {i: sum(x for x in d[i] if x != math.inf) for i in range(n)}


def _indices(graph: dict[int, set[int]], mol: Chem.Mol) -> dict[str, float]:
    w = _weighted_sums(mol)
    dist = _distances(graph)
    nodes = sorted(graph)
    pairs = [(a, b, dist[a][b]) for i, a in enumerate(nodes) for b in nodes[i + 1 :] if b in dist[a]]
    edges = [(a, b) for a in nodes for b in graph[a] if a < b]
    degree = {n: len(graph[n]) for n in nodes}
    s = {n: sum(dist[n].values()) for n in nodes}
    wiener = sum(d for _, _, d in pairs)
    components = len({frozenset(dist[n]) for n in nodes})
    cyclomatic = len(edges) - len(nodes) + components
    szeged = 0
    for u, v in edges:
        nu = sum(1 for w in nodes if w in dist[u] and w in dist[v] and dist[u][w] < dist[v][w])
        nv = sum(1 for w in nodes if w in dist[u] and w in dist[v] and dist[v][w] < dist[u][w])
        szeged += nu * nv
    balaban = len(edges) / (cyclomatic + 1) * sum(1.0 / math.sqrt(w[u] * w[v]) for u, v in edges) if edges else 0.0
    return {
        "Wiener index": wiener,
        "Hyper Wiener index": sum((d + d * d) / 2 for _, _, d in pairs),
        "Harary index": sum(1.0 / d for _, _, d in pairs),
        "Platt index": sum(degree[u] + degree[v] - 2 for u, v in edges),
        "Randic index": sum(1.0 / math.sqrt(degree[u] * degree[v]) for u, v in edges),
        "Wiener polarity": sum(1 for _, _, d in pairs if d == 3),
        "Szeged index": szeged,
        "Balaban index": balaban,
        "Cyclomatic number": cyclomatic,
        "Bond count": len(edges),
        "Atom count": len(nodes),
    }


@pytest.mark.parametrize("name", PANEL)
def test_topology_analysis_matches_a_second_implementation(rig, name):
    mol = _held(rig, PANEL[name])
    expected = _indices(_graph(mol), mol)
    facts = {f.label: f for f in _compute(rig, "topology_analysis", mol).facts}
    for label, value in expected.items():
        shown = facts[label].value if facts[label].value is not None else float(facts[label].display_value)
        assert float(shown) == pytest.approx(value, abs=0.006), (name, label)


@pytest.mark.parametrize("name", PANEL)
def test_per_atom_eccentricity_and_distance_degree_match(rig, name):
    mol = _held(rig, PANEL[name])
    dist = _distances(_graph(mol))
    eccentricity = _compute(rig, "topology_eccentricity", mol).values
    distance_degree = _compute(rig, "topology_distance_degree", mol).values
    for atom, row in dist.items():
        assert eccentricity[atom] == max(row.values()), (name, atom)
        assert distance_degree[atom] == sum(row.values()), (name, atom)


def test_no_centre_is_reported_chiral_except_the_one_that_is(rig):
    for name, smiles in PANEL.items():
        facts = {f.label: str(f.display_value) for f in _compute(rig, "topology_analysis", _held(rig, smiles)).facts}
        expected = "1" if name == "ClF2-O-chiral" else "0"
        assert facts["Chiral center count"] == expected, name


def test_the_ring_facts_follow_the_ring_the_drawing_has(rig):
    facts = {f.label: str(f.display_value) for f in _compute(rig, "topology_analysis", _held(rig, PANEL["ClF2-O-cyclopropyl"])).facts}
    assert (facts["Ring count"], facts["Ring atom count"], facts["Largest ring size"]) == ("1", "3", "3")
    facts = {f.label: str(f.display_value) for f in _compute(rig, "topology_analysis", _held(rig, PANEL["ClF2-O-phenyl"])).facts}
    assert (facts["Ring count"], facts["Aromatic ring count"], facts["Ring atom count"]) == ("1", "1", "6")
    facts = {f.label: str(f.display_value) for f in _compute(rig, "topology_analysis", _held(rig, PANEL["ClF3"])).facts}
    assert (facts["Ring count"], facts["Ring atom count"], facts["Cyclomatic number"]) == ("0", "0", "0")


def test_the_three_are_allowed_and_the_measured_wrong_ones_are_not():
    assert {"topology_analysis", "topology_eccentricity", "topology_distance_degree"} <= HYPERVALENT_VERIFIED_CALCULATORS
    for calculator_id in ("geometry_analysis", "surface_analysis", "dipole_moment", "polarizability", "logd", "solubility", "cns_mpo"):
        assert calculator_id not in HYPERVALENT_VERIFIED_CALCULATORS, calculator_id


def test_topology_analysis_now_runs_through_the_service_on_a_held_clf3(rig, qapp):
    from openchem.events.events import ReportComputed
    from tests.test_hypervalent_calculators import _held as _held_model
    from tests.test_hypervalent_calculators import _run_through_the_service

    molecule, _ = _held_model(rig, "ClF3")
    events = _run_through_the_service(rig, qapp, molecule, "topology_analysis")
    reports = [e.report for e in events if isinstance(e, ReportComputed) and e.report.report_id == "topology_analysis"]
    assert reports and {f.label: str(f.display_value) for f in reports[-1].facts}["Wiener index"] == "9"
