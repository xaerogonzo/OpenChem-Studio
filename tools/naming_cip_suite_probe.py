"""Read the local CIP Validation Suite and spot-check rows the programme already pins.

    uv run --no-sync python tools/naming_cip_suite_probe.py list
    uv run --no-sync python tools/naming_cip_suite_probe.py pinned
    uv run --no-sync python tools/naming_cip_suite_probe.py bridgehead-candidates
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SUITE_DIR = Path(
    r"E:\My Area\Documents\OpenChem Studio literature\CIPValidationSuite"
)

# (suite id, smiles, expected name) — kept in sync with naming tests
PINNED = {
    "VS207": (
        "C[C@H]1CC[C@@H]([C@@]2([C@@H]3CC[C@@H](C)CC3)CC[C@@H](C)CC2)CC1",
        "(1r,4r)-4-methyl-1-[(1r,4r)-4-methylcyclohexyl]-1-[(1s,4s)-4-methylcyclohexyl]cyclohexane",
    ),
    "VS214": (
        "CC[C@@H]1CC/C(/CC1)=C\\2/CC[C@H](CC2)CC",
        "(1s,4E)-1-ethyl-4-[(4s)-4-ethylcyclohexan-1-ylidene]cyclohexane",
    ),
    "VS279": (
        "O[C@@H](C[C@H]1CC[C@@H](CC1)C)C[C@@H]2CC[C@@H](CC2)C",
        "(2R)-1-[(1r,4S)-4-methylcyclohexyl]-3-[(1s,4S)-4-methylcyclohexyl]propan-2-ol",
    ),
    "VS231": (
        "CC=[C@]=C1CC[C@H](CC1)CC",
        "(1s)-1-ethyl-4-[(1p)-prop-1-en-1-ylidene]cyclohexane",
    ),
}

BRIDGEHEAD_GREP = re.compile(
    r"bicyclo\[[0-9.]*\]|norborn|adamant|bridgehead",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SuiteRow:
    smiles: str
    suite_id: str
    labels: str
    rule: str
    stereo_units: str
    cip_rules: str


def suite_smi_path() -> Path:
    raw = os.environ.get("OPENCHEM_CIP_SUITE")
    if raw:
        p = Path(raw)
        return p if p.suffix.lower() == ".smi" else p / "compounds.smi"
    return DEFAULT_SUITE_DIR / "compounds.smi"


def load_rows(path: Path) -> list[SuiteRow]:
    if not path.is_file():
        raise FileNotFoundError(
            f"CIP suite SMILES not found at {path} "
            f"(set OPENCHEM_CIP_SUITE or clone to {DEFAULT_SUITE_DIR})"
        )
    rows: list[SuiteRow] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 6:
            continue
        rows.append(
            SuiteRow(
                smiles=parts[0],
                suite_id=parts[1],
                labels=parts[2],
                rule=parts[3],
                stereo_units=parts[4],
                cip_rules=parts[5],
            )
        )
    return rows


def cmd_list(rows: list[SuiteRow]) -> int:
    print(f"{len(rows)} entries in {suite_smi_path()}")
    for r in rows[:5]:
        print(f"  {r.suite_id}\t{r.labels}\t{r.stereo_units}\t{r.smiles[:50]}")
    if len(rows) > 5:
        print(f"  ... ({len(rows) - 5} more)")
    return 0


def cmd_bridgehead(rows: list[SuiteRow]) -> int:
    hits = [r for r in rows if BRIDGEHEAD_GREP.search(r.smiles)]
    print(f"{len(hits)} entries match bridgehead / polycyclic grep")
    for r in hits:
        print(f"  {r.suite_id}\t{r.labels}\t{r.smiles}")
    return 0


def cmd_pinned(rows: list[SuiteRow]) -> int:
    by_id = {r.suite_id: r for r in rows}
    sys.path.insert(0, str(ROOT / "src"))
    from openchem.vendor.iupac_namer import name_smiles

    failed = 0
    for sid, (smiles, expected) in PINNED.items():
        row = by_id.get(sid)
        if row is None:
            print(f"{sid}: MISSING from suite file")
            failed += 1
            continue
        if row.smiles != smiles:
            print(f"{sid}: SMILES drift (file differs from test pin)")
            failed += 1
        got = name_smiles(smiles)
        if got != expected:
            print(f"{sid}: FAIL")
            print(f"  expected: {expected}")
            print(f"  got:      {got}")
            failed += 1
        else:
            print(f"{sid}: ok  ({row.labels})")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("list", "pinned", "bridgehead-candidates"),
    )
    args = parser.parse_args()
    rows = load_rows(suite_smi_path())
    if args.command == "list":
        return cmd_list(rows)
    if args.command == "bridgehead-candidates":
        return cmd_bridgehead(rows)
    return cmd_pinned(rows)


if __name__ == "__main__":
    raise SystemExit(main())