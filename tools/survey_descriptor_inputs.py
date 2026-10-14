"""Which always-on results depend on the structure's COORDINATES, and which only on how its hydrogens are written.

**WHY IT EXISTS.** Drawing aspirin and generating a conformer changed the Results reader's Synthetic
Accessibility from 1.58 to 6.445, Bertz CT from 343 to 609, H-bond acceptors from 3 to 4. A conformer
carries explicit hydrogen atoms and the drawing's are implicit, so every descriptor computed on the
conformer answers a slightly different question; the service re-ran ALL of them on it. Deciding which
ones may be computed on a geometry needs a measurement, not a reading of the names, and this is it.

**IT ASKS THE PROVIDER, NOT THE SERVICE.** What a descriptor varies with is a fact about the provider and
the structure, and it is the reason the service's policy is what it is. Measuring it through the service's
own geometry run would stop showing the artefact the day the service stopped producing it (the first
version of this tool did, and read `moved 0/0` for everything once the service was fixed). The service's
behaviour is guarded separately, in `tests/test_descriptor_input.py`.

**THE TEST OF "LEGITIMATELY 3D" IS WHAT A DESCRIPTOR VARIES WITH.** Three structures per molecule:

    drawing   the implicit-hydrogen 2D molblock
    A, B      two DIFFERENT embeddings of the same molecule (same atoms, same hydrogens, other coordinates)

and a result is exactly one of

    needs 3D       refused on the drawing (a flat structure has no moments of inertia), and it differs between A
                   and B: it is a function of the coordinates
    graph-only     the same on the drawing, A and B: a function of the structure graph
    H-artefact     the same on A and B, DIFFERENT on the drawing: a function of the graph that depends on whether
                   the hydrogens are atoms. Nothing about it is geometric, and computing it on a conformer returns a
                   different answer to the same question -- the defect
    MIXED          differs on both counts; none has been seen

The alert catalogues and the per-atom datasets are classified the same way. A per-atom dataset also records
`reindexed`: on the conformer it describes the hydrogens as atoms too (21 for aspirin's 13), whatever its values
on the shared atoms.

Measured on 2026-10-14 over `tests/fixtures/census_panel.toml` (29 molecules): the ten shape descriptors need 3D;
nine descriptors (`bertz_ct`, `esol_logs`, `labute_asa`, `np_likeness`, `np_likeness_confidence`, `num_hba`,
`num_rotatable_bonds`, `rule_of_three_pass`, `sa_score`) and two alert catalogues (`brenk`, `fragment_counts`) are
H-artefacts; the other 22 descriptors, three alert catalogues and all three per-atom datasets are graph-only.

Run it:

    python tools/survey_descriptor_inputs.py --report
    python tools/survey_descriptor_inputs.py --report --json out.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
for _path in (ROOT / "src", ROOT / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

#: Two numbers closer than this are the same descriptor value. Looser than float noise, tighter than any
#: figure a person would call different (a Bertz CT is quoted to a tenth).
TOLERANCE = 1e-6

#: The number of embeddings asked for when looking for two that differ.
EMBEDDINGS = 6


@dataclass
class Observation:
    """What one result id did across the panel."""

    result_id: str
    kind: str
    #: Rows on which the drawing and a conformer disagreed: `(row, drawing, conformer)`.
    moved: list[tuple[str, Any, Any]] = field(default_factory=list)
    #: Rows on which both structures produced the result.
    compared: int = 0
    #: Rows the drawing refused while a conformer gave a value.
    needed_geometry: int = 0
    #: Per-atom datasets only: rows on which the two structures described a different SET of atoms.
    reindexed: int = 0
    #: Rows on which two embeddings of one molecule gave different values, out of `pairs`.
    varied_between_conformers: int = 0
    pairs: int = 0

    @property
    def classification(self) -> str:
        if self.needed_geometry and not self.moved:
            return "needs 3D" if self.varied_between_conformers else "needs a conformer, but constant across them"
        if self.moved and not self.varied_between_conformers:
            return "H-artefact"
        if self.moved:
            return "MIXED (moves with the representation AND the coordinates)"
        if self.varied_between_conformers:
            return "MIXED (moves with the coordinates)"
        return "graph-only"


def _same(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool) or left is None or right is None:
        return left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        if math.isnan(left) and math.isnan(right):
            return True
        return abs(left - right) <= TOLERANCE * max(1.0, abs(left), abs(right))
    return left == right


def _outputs(provider, mol, molecule_uuid: str) -> dict[str, tuple[str, Any]]:
    """`result id -> (kind, comparable)` for everything the provider emits for `mol`."""
    from openchem.domain.common import CacheState

    out: dict[str, tuple[str, Any]] = {}
    for value in provider.compute(mol, molecule_uuid):
        out[f"descriptor:{provider.provider_id}:{value.descriptor_id}"] = (
            "descriptor", None if value.cache_state is CacheState.FAILED else value.value
        )
    for alert in provider.compute_alerts(mol, molecule_uuid):
        out[alert.alert_id] = ("alert", tuple(sorted(alert.matched)))
    for dataset in provider.compute_per_atom(mol, molecule_uuid):
        out[dataset.property_id] = ("per_atom", dict(dataset.values))
    return out


def _per_atom_same(left: dict, right: dict) -> bool:
    """Equal on the atoms both describe. The conformer has more atoms (its hydrogens); the drawing's atoms keep their indices."""
    shared = set(left) & set(right)
    return bool(shared) and all(_same(left[i], right[i]) for i in shared)


def _equal(kind: str, left: Any, right: Any) -> bool:
    return _per_atom_same(left, right) if kind == "per_atom" else _same(left, right)


def survey(rows=None, provider=None) -> dict[str, Observation]:
    """Every result id the provider emits, over the census panel (or `rows`), by what it varies with."""
    import calculator_census as census_tool
    from openchem.chem.conformer_providers import RDKitConformerProvider
    from openchem.chem.descriptor_providers import RDKitDescriptorProvider
    from openchem.chem.engine import ChemistryEngine
    from openchem.domain.molecule import MoleculeModel

    rows = rows if rows is not None else census_tool.load_corpus()
    provider = provider if provider is not None else RDKitDescriptorProvider()
    engine = ChemistryEngine()
    conformers = RDKitConformerProvider()
    found: dict[str, Observation] = {}
    for row in rows:
        model = MoleculeModel()
        engine.set_structure_from_smiles(model, row.smiles)
        drawing = engine.mol_from_model(model)
        try:
            embeddings = conformers.generate_conformers(drawing, num_conformers=EMBEDDINGS, optimize=False)
        except Exception:  # noqa: BLE001 - a molecule that will not embed has nothing to add here
            continue
        if not embeddings:
            continue
        on_drawing = _outputs(provider, drawing, model.uuid)
        on_first = _outputs(provider, embeddings[0][0], model.uuid)
        on_second = _outputs(provider, embeddings[1][0], model.uuid) if len(embeddings) > 1 else None
        for result_id, (kind, geometry_value) in on_first.items():
            seen = found.setdefault(result_id, Observation(result_id, kind))
            drawing_value = on_drawing.get(result_id, (kind, None))[1]
            if drawing_value is None and geometry_value is not None:
                seen.needed_geometry += 1
            else:
                seen.compared += 1
                if kind == "per_atom" and set(drawing_value) != set(geometry_value):
                    seen.reindexed += 1
                if not _equal(kind, drawing_value, geometry_value):
                    seen.moved.append((row.id, drawing_value, geometry_value))
            if on_second is not None:
                seen.pairs += 1
                if not _equal(kind, geometry_value, on_second[result_id][1]):
                    seen.varied_between_conformers += 1
    return found


def _report(found: dict[str, Observation], json_path: str | None) -> None:
    for kind in ("descriptor", "alert", "per_atom"):
        print(f"\n== {kind}")
        for result_id, seen in sorted(found.items(), key=lambda kv: (kv[1].classification, kv[0])):
            if seen.kind != kind:
                continue
            worst = ""
            if seen.moved:
                row, was, now = seen.moved[0]
                worst = f"  e.g. {row}: drawing {was!r:.40} -> conformer {now!r:.40}"
            print(
                f"  {seen.classification:<44} {result_id:<48} moved {len(seen.moved):>2}/{seen.compared:<2} "
                f"needed-3D {seen.needed_geometry:>2}  varies-between-conformers {seen.varied_between_conformers:>2}/{seen.pairs:<2}"
                f"{'  different atoms on ' + str(seen.reindexed) + ' rows' if seen.reindexed else ''}{worst}"
            )
    if json_path:
        payload = {
            result_id: {
                "kind": s.kind, "classification": s.classification, "moved_rows": [r for r, _a, _b in s.moved],
                "compared": s.compared, "needed_geometry": s.needed_geometry, "reindexed": s.reindexed,
                "varied_between_conformers": s.varied_between_conformers, "pairs": s.pairs,
            }
            for result_id, s in sorted(found.items())
        }
        Path(json_path).write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        print(f"\nwrote {json_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", action="store_true", required=True)
    parser.add_argument("--json")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    _report(survey(), args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
