"""Builds each corpus assembly and records what came out.

Separate from scoring so a build is produced once and compared many
times, following `benchmarks/conformers`. The built structures go to
`cache/built_<label>/`; the manifest carries the identity of every
placement, which is what scoring matches on.

`--mutate` is the gate's own check on itself. A benchmark that has never
been shown to FAIL is not evidence, and the mutation that matters here is
`transpose`: every operator matrix in the bundled receptor catalogue is
axis-aligned, so transposing one changes nothing and a transposed
implementation passes all 49. 2OMF's 3-fold is in the corpus precisely so
that this mutation has something to break.

Usage:
    python build.py --label shipped
    python build.py --label transpose --mutate transpose
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"

sys.path.insert(0, str(HERE.parents[1] / "src"))

from openchem.chem import structure_assembly  # noqa: E402
from openchem.chem.structure_assembly import Transform, build_assembly  # noqa: E402

_MUTATIONS = ("transpose", "swap-translation")


def _apply_mutation(kind: str) -> None:
    """Corrupt the operators on purpose, in one visible place.

    Patching `operator_transforms` rather than editing the module means
    the mutation cannot be left behind in the source, which this project
    has already been bitten by twice -- once by an edit that never landed
    and once by a restored file still running from stale bytecode.
    """
    original = structure_assembly.operator_transforms

    def mutated(text, fmt, assembly_id=None):
        transforms = original(text, fmt, assembly_id)
        out = {}
        for key, transform in transforms.items():
            matrix, vector = transform.matrix, transform.vector
            if kind == "transpose":
                matrix = tuple(
                    tuple(matrix[column][row] for column in range(3))
                    for row in range(3)
                )
            elif kind == "swap-translation":
                vector = (vector[1], vector[0], vector[2])
            out[key] = Transform(
                operator_id=transform.operator_id, matrix=matrix, vector=vector
            )
        return out

    structure_assembly.operator_transforms = mutated
    # `build_assembly` resolved the name at import time in this module's
    # namespace only; the builder itself calls it through the module.
    print(f"MUTATED: {kind}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, help="names the output files")
    parser.add_argument("--mutate", choices=_MUTATIONS, default=None)
    parser.add_argument(
        "--format",
        choices=("pdb", "mmcif"),
        default="pdb",
        help="which deposited form to build FROM; the reference is mmCIF either way",
    )
    args = parser.parse_args()

    corpus = json.loads((HERE / "corpus.json").read_text(encoding="utf-8"))
    if args.mutate:
        _apply_mutation(args.mutate)

    out_dir = CACHE / f"built_{args.label}"
    out_dir.mkdir(parents=True, exist_ok=True)

    predictions = {}
    for entry in corpus["structures"]:
        pdb_id, assembly_id = entry["pdb_id"], entry["assembly_id"]
        suffix = "pdb" if args.format == "pdb" else "cif"
        source = CACHE / f"{pdb_id}.{suffix}"
        if not source.exists():
            print(f"  MISSING {source.name} -- run fetch.py first", file=sys.stderr)
            return 2
        result = build_assembly(
            source.read_text(errors="ignore"), args.format, assembly_id=assembly_id
        )
        record = {
            "ok": result.ok,
            "failure_reason": result.failure_reason,
            "warnings": list(result.warnings),
            "instances": [
                [i.source_chain, i.operator_id, i.generated_chain_id]
                for i in result.instances
            ],
        }
        if result.ok:
            path = out_dir / f"{pdb_id}.{suffix}"
            path.write_text(result.output_text, encoding="utf-8")
            record["atom_count"] = sum(
                1
                for line in result.output_text.splitlines()
                if line.startswith(("ATOM ", "HETATM"))
            )
            record["sha256"] = hashlib.sha256(
                result.output_text.encode("utf-8")
            ).hexdigest()
            print(f"  {pdb_id}: built {record['atom_count']:,} atoms")
        else:
            print(f"  {pdb_id}: refused -- {result.failure_reason}")
        predictions[pdb_id] = record

    payload = {
        "label": args.label,
        "source_format": args.format,
        "mutation": args.mutate,
        "corpus_version": corpus["corpus_version"],
        "environment": {
            "built": date.today().isoformat(),
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "predictions": predictions,
    }
    destination = HERE / f"predictions_{args.label}.json"
    destination.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"\nWrote {destination.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
