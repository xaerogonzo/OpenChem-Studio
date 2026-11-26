"""Replace a shipped template's bad RDKit depiction with a better 2D molblock.

Run (from the repo root)::

    uv run --no-sync python tools/curate_template_layouts.py            # dry run: what would change
    uv run --no-sync python tools/curate_template_layouts.py --write    # store the winners
    uv run --no-sync python tools/curate_template_layouts.py --ids a.b c.d

For every template the layout screen flags (``tools/template_layout_check.py``)
and that is still SMILES-only, several candidate drawings are generated (RDKit
with different flip samplings, CoordGen, and orthographic projections of an
embedded 3D structure from many viewpoints), each is scaled to one bond length,
given wedge bonds for its stereo, and kept only when it parses back to the SAME
molecule (InChIKey with stereo). The best one by the screen's own rank wins and
is stored as the entry's ``molblock``; the SMILES moves to
``tests/fixtures/curated_template_smiles.json``, which the identity test reads.
A template whose best candidate still flags is left alone and reported: some
cages cannot be drawn flat without a crossing.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
DATA = ROOT / "src/openchem/chem/data/structure_templates"
FIXTURE = ROOT / "tests/fixtures/curated_template_smiles.json"
BOND = 1.5
VIEWS = 400
#: How many substituent placements to try per planar core (the core is fixed).
PLANAR_SEEDS = 4


def _load_checker():
    spec = importlib.util.spec_from_file_location("template_layout_check", ROOT / "tools/template_layout_check.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["template_layout_check"] = module
    spec.loader.exec_module(module)
    return module


chk = _load_checker()


def _rescale(mol, conf_id=-1):
    """Centre and scale so the median bond is BOND; flat z."""
    import statistics

    from rdkit.Geometry import Point3D

    conf = mol.GetConformer(conf_id)
    pts = [(conf.GetAtomPosition(i).x, conf.GetAtomPosition(i).y) for i in range(mol.GetNumAtoms())]
    lengths = [
        ((pts[b.GetBeginAtomIdx()][0] - pts[b.GetEndAtomIdx()][0]) ** 2 + (pts[b.GetBeginAtomIdx()][1] - pts[b.GetEndAtomIdx()][1]) ** 2) ** 0.5
        for b in mol.GetBonds()
    ]
    scale = BOND / statistics.median(lengths)
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    for i, (x, y) in enumerate(pts):
        conf.SetAtomPosition(i, Point3D((x - cx) * scale, (y - cy) * scale, 0.0))
    conf.Set3D(False)


def _flat(mol):
    from rdkit import Chem

    out = Chem.Mol(mol)
    out.RemoveAllConformers()
    return out


def candidates(smiles: str):
    """Yield (label, mol-with-2D-conformer) drawings of the molecule."""
    from rdkit import Chem
    from rdkit.Chem import AllChem, rdCoordGen, rdDepictor

    base = Chem.MolFromSmiles(smiles)
    for seed in range(12):
        m = _flat(base)
        rdDepictor.Compute2DCoords(m, nFlipsPerSample=3, nSample=60, sampleSeed=seed, permuteDeg4Nodes=bool(seed % 2))
        yield f"rdkit{seed}", m
    for label, precision in (("coordgen", None), ("coordgen_best", "best")):
        m = _flat(base)
        params = rdCoordGen.CoordGenParams()
        if precision:
            params.minimizerPrecision = params.sketcherBestPrecision
        rdCoordGen.AddCoords(m, params)
        yield label, m
    yield from planar_candidates(base)
    # Orthographic projections of an embedded structure: for bridged cages a
    # good viewpoint is a drawing a person would make.
    heavy = Chem.AddHs(base)
    if AllChem.EmbedMolecule(heavy, randomSeed=7) != 0:
        return
    heavy = Chem.RemoveHs(heavy)
    xyz = heavy.GetConformer().GetPositions()
    rng = random.Random(11)
    import numpy as np

    for view in range(VIEWS):
        q = np.array([rng.gauss(0, 1) for _ in range(4)])
        q /= np.linalg.norm(q)
        w, x, y, z = q
        rot = np.array(
            [
                [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
            ]
        )
        pts = xyz @ rot.T
        m = _flat(base)
        from rdkit.Chem import rdchem
        from rdkit.Geometry import Point3D

        conf = rdchem.Conformer(m.GetNumAtoms())
        for i, p in enumerate(pts):
            conf.SetAtomPosition(i, Point3D(float(p[0]), float(p[1]), 0.0))
        conf.Set3D(False)
        m.AddConformer(conf)
        yield f"view{view}", m


def planar_candidates(base):
    """Crossing-free drawings of the largest ring block (Tutte embedding).

    The biggest two-connected block of the ring system is embedded as a planar
    graph with one face pinned to a regular polygon (every face, three sizes);
    weights are fitted so bonds come out near one length. Everything else is
    laid out around it by RDKit. Needs networkx (``uv run --with networkx``);
    a non-planar block yields nothing.
    """
    try:
        import networkx as nx
    except ImportError as exc:  # pragma: no cover - maintainer tool
        raise SystemExit("planar candidates need networkx: uv run --no-sync --with networkx python ...") from exc
    import math

    import numpy as np
    from rdkit import Chem
    from rdkit.Chem import rdDepictor
    from rdkit.Geometry import Point2D
    from scipy.optimize import minimize

    graph = nx.Graph([(b.GetBeginAtomIdx(), b.GetEndAtomIdx()) for b in base.GetBonds()])
    core = nx.k_core(graph, 2) if graph.number_of_edges() else graph
    blocks = [c for c in nx.biconnected_components(core) if len(c) >= 3]
    if not blocks:
        return
    block = max(blocks, key=len)
    sub = core.subgraph(block).copy()
    planar, embedding = nx.check_planarity(sub)
    if not planar:
        return
    nodes = sorted(sub.nodes)
    index = {a: i for i, a in enumerate(nodes)}
    edges = np.array([(index[a], index[b]) for a, b in sub.edges])
    seen, faces = set(), []
    for a, b in embedding.edges():
        if (a, b) in seen:
            continue
        face = embedding.traverse_face(a, b, mark_half_edges=seen)
        if len(set(face)) == len(face) and len(face) >= 3:
            faces.append(face)
    n = len(nodes)
    for fnum, face in enumerate(faces):
        outer = [index[a] for a in face]
        free = np.setdiff1d(np.arange(n), outer)
        for factor in (1.0, 1.6, 2.4):
            radius = factor / (2 * math.sin(math.pi / len(outer)))
            angles = 2 * math.pi * np.arange(len(outer)) / len(outer)
            fixed = np.zeros((n, 2))
            fixed[outer] = radius * np.stack([np.cos(angles), np.sin(angles)], axis=1)
            outer_edge = np.isin(edges[:, 0], outer) & np.isin(edges[:, 1], outer)

            def embed(log_w, fixed=fixed, outer=outer, free=free):
                w = np.zeros((n, n))
                w[edges[:, 0], edges[:, 1]] = w[edges[:, 1], edges[:, 0]] = np.exp(log_w)
                lap = np.diag(w.sum(axis=1)) - w
                pos = fixed.copy()
                if len(free):
                    pos[free] = np.linalg.solve(lap[np.ix_(free, free)], -lap[np.ix_(free, outer)] @ fixed[outer])
                return pos

            def energy(log_w, embed=embed, outer_edge=outer_edge):
                pos = embed(log_w)
                d = np.linalg.norm(pos[edges[:, 0]] - pos[edges[:, 1]], axis=1)
                gaps = np.linalg.norm(pos[:, None] - pos[None], axis=2) + np.eye(n) * 99
                return float(np.sum((d[~outer_edge] - 1.0) ** 2) + 5.0 * np.sum(np.maximum(0.0, 0.85 - gaps) ** 2))

            try:
                fit = minimize(energy, np.zeros(len(edges)), method="L-BFGS-B", bounds=[(-6, 6)] * len(edges), options={"maxiter": 400})
                pos = embed(fit.x)
            except np.linalg.LinAlgError:
                continue
            coord_map = {nodes[i]: Point2D(float(pos[i][0]), float(pos[i][1])) for i in range(n)}
            for seed in range(PLANAR_SEEDS):
                m = _flat(base)
                try:
                    rdDepictor.Compute2DCoords(m, coordMap=coord_map, nFlipsPerSample=3, nSample=60, sampleSeed=seed)
                except Exception:  # noqa: BLE001 - RDKit refusing a map just drops the candidate
                    continue
                yield f"planar{fnum}x{factor}s{seed}", m


def molblock_with_wedges(mol) -> str:
    from rdkit import Chem

    Chem.WedgeMolBonds(mol, mol.GetConformer())
    return Chem.MolToMolBlock(mol)


def best_drawing(smiles: str):
    """(label, molblock, Layout) of the best identity-preserving candidate, or None."""
    from rdkit import Chem
    from rdkit.Chem.inchi import MolToInchiKey

    from openchem.chem.engine import ChemistryEngine

    engine = ChemistryEngine()
    target = MolToInchiKey(Chem.MolFromSmiles(smiles))
    ranked = []
    for label, mol in candidates(smiles):
        try:
            _rescale(mol)
            layout = chk.layout_of_molblock(Chem.MolToMolBlock(mol))
        except (ValueError, ZeroDivisionError):
            continue
        ranked.append((layout.score, label, mol, layout))
    ranked.sort(key=lambda row: row[0])
    for _score, label, mol, layout in ranked[:25]:
        block = molblock_with_wedges(Chem.Mol(mol))
        try:
            parsed = engine.mol_from_molblock(block)
        except Exception:  # noqa: BLE001 - a candidate the engine refuses is just skipped
            continue
        if MolToInchiKey(parsed) != target:
            continue
        final = chk.layout_of_molblock(block)
        return label, block, final
    return None


def _entry_smiles(entry: dict, pinned: dict[str, str]) -> str | None:
    return entry.get("smiles") or pinned.get(entry["id"])


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--ids", nargs="*", help="only these template ids")
    args = parser.parse_args(argv)

    # A drawing flagged only for its aspect ratio (a long chain) reads fine: leave it.
    flagged = {tid for tid, lay in chk.screen_shipped() if set(lay.flags) - {"aspect"}}
    wanted = set(args.ids) if args.ids else flagged
    pinned = json.loads(FIXTURE.read_text(encoding="utf-8")) if FIXTURE.exists() else {}
    changed, left = [], []
    for path in sorted(DATA.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        dirty = False
        for entry in raw["entries"]:
            if entry["id"] not in wanted or "smiles" not in entry:
                continue
            smiles = entry["smiles"]
            before = chk.layout_of_molblock(_rdkit_block(smiles))
            result = best_drawing(smiles)
            if result is None or result[2].score >= before.score:
                left.append((entry["id"], before, None))
                continue
            label, block, after = result
            line = (entry["id"], before, after, label)
            # Accept a drawing with no overlap and no crossing that scores better; a
            # remaining stretched bond (cages) is reported, not a reason to keep the tangle.
            clean = not ({"overlap", "crossing"} & set(after.flags))
            (changed if clean else left).append(line if clean else (entry["id"], before, after))
            if clean:
                pinned[entry["id"]] = smiles
                entry.pop("smiles")
                entry["molblock"] = block
                dirty = True
        if dirty and args.write:
            path.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.write:
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(json.dumps(dict(sorted(pinned.items())), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"curated {len(changed)}, left alone {len(left)}")
    for tid, before, after, label in changed:
        rest = f"  still flags {','.join(after.flags)}" if after.flags else ""
        print(f"  OK   {tid:52} score {before.score:8.1f} -> {after.score:5.1f}  ({label}){rest}")
    for row in left:
        tid, before, after = row[0], row[1], row[2]
        tail = f"best candidate still flags: {','.join(after.flags)} (score {after.score:.1f})" if after else "no better candidate"
        print(f"  LEFT {tid:52} score {before.score:8.1f}; {tail}")
    return 0


def _rdkit_block(smiles: str) -> str:
    from rdkit import Chem
    from rdkit.Chem import rdDepictor

    mol = Chem.MolFromSmiles(smiles)
    rdDepictor.Compute2DCoords(mol)
    Chem.WedgeMolBonds(mol, mol.GetConformer())
    return Chem.MolToMolBlock(mol)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
