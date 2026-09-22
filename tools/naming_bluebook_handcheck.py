"""The Blue Book harvest's HAND CHECK: is OPSIN's structure for a printed name the structure the book DRAWS?

    python tools/naming_bluebook_handcheck.py sample                            # draw the stratified sample -> WORK/sample.json
    uvx --with pymupdf python tools/naming_bluebook_handcheck.py crops --pdf ... # render each row's page region -> WORK/crops/<label>.png
    python tools/naming_bluebook_handcheck.py sheets                            # crop + OPSIN's depiction, side by side -> WORK/sheets/<label>.png
    #  ... a person (or Claude) looks at each sheet and writes WORK/verdicts.json ...
    python tools/naming_bluebook_handcheck.py record                            # verdicts -> statuses, stop rules, the committed record

**THIS VALIDATES THE ORACLE, NOT THE ENGINE.** OPSIN reading a printed name is a claim about that name, and in round 8 it read every misspelling
(`docs/LESSONS.md`). The only independent check available is the structure the book DRAWS beside the name, so a sample of rows is compared by eye and the
result decides which rows may count (`benchmarks/naming/bluebook_protocol.toml`). This module reads BOTH halves, including the evaluation-only one, because
a sample that skipped the frozen half could not say whether the frozen half's oracle is sound; it never names a structure with the engine, prints a frozen
row's name into a committed file, or records a frozen row's verdict anywhere but the sealed sidecar. It reaches the frozen half through the harvest tool's
own constants, which is also why `tests/test_naming_heldout_lock.py` does not need to allow it.

**THE SAMPLE IS STRATIFIED AND SEEDED, never picked by eye.** Every chapter and every geometric or textual feature in the protocol is sampled, so "one-line
examples work and column-boundary names are broken" can be discovered; the seed is the protocol's. A row belongs to its chapter's stratum and to a stratum for
each feature it has, whatever it was drawn for.

**WHAT A VERDICT MEANS.** `SAME` and `DIFFERENT_TAUTOMER` agree (the round-trip gate already treats tautomers as one compound); `DIFFERENT_CHARGE_OR_H` and
`DIFFERENT_STRUCTURE` disagree; `UNREADABLE_DRAWING` is not checked and does not enter a rate. `join_ok = false` means the extracted name is not the printed name,
which is an extraction error and counts against the name-join stop rule; it also rejects the row.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "benchmarks" / "naming"
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))

import naming_bluebook_harvest as harvest  # noqa: E402

PROTOCOL = harvest.PROTOCOL
AGREE = {"SAME", "DIFFERENT_TAUTOMER"}
DISAGREE = {"DIFFERENT_CHARGE_OR_H", "DIFFERENT_STRUCTURE"}
CLASSES = AGREE | DISAGREE | {"UNREADABLE_DRAWING"}
VALIDATED, ACCEPTED, UNCERTAIN, REJECTED = "ORACLE_VALIDATED", "ORACLE_STRATUM_ACCEPTED", "ORACLE_UNCERTAIN", "ORACLE_REJECTED"
ORACLE_FILE = "bluebook_oracle.json"
HANDCHECK_FILE = "bluebook_handcheck.toml"
SEALED_FILE = ROOT / "benchmarks" / "naming" / "stages" / "sealed" / "bluebook_frozen.handcheck.json"


def protocol() -> dict:
    return tomllib.loads(PROTOCOL.read_bytes().replace(b"\r\n", b"\n").decode("utf-8"))


def strata_of(row: dict) -> list[str]:
    """The strata a row belongs to: its chapter and every feature it has."""
    return [f"chapter:{row['chapter']}"] + [f"feature:{name}" for name, on in sorted(row["features"].items()) if on]


def draw_sample(rows: list[dict], spec: dict) -> list[str]:
    """Labels of the hand sample. For each chapter, `per_chapter` rows; for each feature, `per_feature` rows; a row already drawn is not drawn again, so
    the total is at most 10 * per_chapter + features * per_feature. Seeded, order-independent (the rows are sorted by label first)."""
    rng = random.Random(spec["seed"])
    ordered = sorted(rows, key=lambda r: r["label"])
    chosen: list[str] = []
    for chapter in sorted({r["chapter"] for r in ordered}):
        pool = [r["label"] for r in ordered if r["chapter"] == chapter and r["label"] not in chosen]
        rng.shuffle(pool)
        chosen += pool[: spec["per_chapter"]]
    for feature in spec["features"]:
        pool = [r["label"] for r in ordered if r["features"].get(feature) and r["label"] not in chosen]
        rng.shuffle(pool)
        chosen += pool[: spec["per_feature"]]
    return chosen


def evaluate(rows: list[dict], verdicts: dict[str, dict], rules: dict) -> dict:
    """Statuses for every row, the per-stratum table, and the stop-rule verdict. Pure: rows are population rows, verdicts are `{label: {class, join_ok}}`."""
    stop, failure = rules["stop"], rules["stratum_failure"]
    by_label = {r["label"]: r for r in rows}
    checked = {label: v for label, v in verdicts.items() if label in by_label and v["class"] != "UNREADABLE_DRAWING"}
    strata: dict[str, dict] = {}
    for label, verdict in checked.items():
        for stratum in strata_of(by_label[label]):
            cell = strata.setdefault(stratum, {"checked": 0, "disagreements": 0})
            cell["checked"] += 1
            cell["disagreements"] += (verdict["class"] in DISAGREE) or (not verdict["join_ok"])
    for stratum, cell in strata.items():
        n, d = cell["checked"], cell["disagreements"]
        cell["failed"] = bool(n >= failure["min_checked"] and d >= failure["min_disagreements"] and d / n >= failure["min_rate"])
        cell["accepted"] = bool(n >= failure["min_checked"] and not cell["failed"])

    statuses: dict[str, str] = {}
    for row in rows:
        label = row["label"]
        own = strata_of(row)
        verdict = checked.get(label)
        if verdict is not None:
            statuses[label] = VALIDATED if (verdict["class"] in AGREE and verdict["join_ok"]) else REJECTED
        elif any(strata.get(s, {}).get("failed") for s in own):
            statuses[label] = REJECTED
        elif row["oracle_risk"]:
            statuses[label] = UNCERTAIN
        elif all(strata.get(s, {}).get("accepted") for s in own):
            statuses[label] = ACCEPTED
        else:
            statuses[label] = UNCERTAIN  # a stratum with too few checked rows can neither be called accepted nor failed

    n_checked = len(checked)
    join_errors = sum(1 for v in checked.values() if not v["join_ok"])
    disagreements = sum(1 for v in checked.values() if v["class"] in DISAGREE)
    eligible = len(rows)
    rejected_share = sum(1 for s in statuses.values() if s == REJECTED) / eligible if eligible else 0.0
    verdict = {
        "checked": n_checked,
        "unreadable_drawings": sum(1 for v in verdicts.values() if v["class"] == "UNREADABLE_DRAWING"),
        "join_errors": join_errors,
        "join_error_rate": join_errors / n_checked if n_checked else None,
        "disagreements": disagreements,
        "disagreement_rate": disagreements / n_checked if n_checked else None,
        "rejected_share_of_eligible": rejected_share,
        "usable_rows": len(rows),
    }
    reasons = []
    if len(rows) < stop["min_usable_rows"]:
        reasons.append(f"fewer than {stop['min_usable_rows']} usable rows")
    if n_checked and join_errors / n_checked > stop["max_name_join_error"]:
        reasons.append("name-join error over the stop rule")
    if n_checked and disagreements / n_checked > stop["max_overall_structure_disagreement"]:
        reasons.append("OPSIN-vs-drawn disagreement over the stop rule")
    if rejected_share > stop["max_rejected_stratum_share"]:
        reasons.append("failed strata hold more than the allowed share of rows")
    verdict["abandon_reasons"] = reasons
    verdict["b1_trusted"] = not reasons
    return {"statuses": statuses, "strata": dict(sorted(strata.items())), "summary": verdict}


# --- the commands ---------------------------------------------------------------------------------------------------------------------------------------


def _load_halves() -> list[dict]:
    rows = []
    for half, file_name in (("tuning", harvest.TUNING_FILE), ("frozen", harvest.FROZEN_FILE)):
        for row in json.loads((BENCH / file_name).read_text(encoding="utf-8")):
            rows.append({**row, "half": half})
    return rows


def cmd_sample(work: Path) -> None:
    rows = _load_halves()
    labels = draw_sample(rows, protocol()["sample"])
    by_label = {r["label"]: r for r in rows}
    work.mkdir(parents=True, exist_ok=True)
    payload = [
        {"label": label, "half": by_label[label]["half"], "chapter": by_label[label]["chapter"], "printed": by_label[label]["accepted_printed_targets"][0],
         "smiles": by_label[label]["smiles"], "locations": by_label[label]["locations"], "features": by_label[label]["features"]}
        for label in labels
    ]
    (work / "sample.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    counts = {half: sum(1 for p in payload if p["half"] == half) for half in ("tuning", "frozen")}
    print(f"sample of {len(payload)} rows ({counts}) -> {work / 'sample.json'}")


def cmd_crops(work: Path, pdf: Path) -> None:
    """Render, for each sampled row, the page region around its printed name (the drawn structure sits just above or beside it)."""
    import pymupdf

    doc = pymupdf.open(str(pdf))
    out = work / "crops"
    out.mkdir(parents=True, exist_ok=True)
    for item in json.loads((work / "sample.json").read_text(encoding="utf-8")):
        location = item["locations"][0]
        page = doc[location["page"] - 1]
        x0, y0, x1, y1 = location["bbox"]
        width, height = location["page_size"]
        clip = pymupdf.Rect(max(0, x0 - 60), max(0, y0 - 175), min(width, max(x1 + 60, x0 + 380)), min(height, y1 + 25))
        page.get_pixmap(matrix=pymupdf.Matrix(2, 2), clip=clip).save(str(out / f"{item['label']}.png"))
    print(f"rendered {len(list(out.glob('*.png')))} crops -> {out}")


def cmd_sheets(work: Path) -> None:
    """One image per row: the book's page region on the left, OPSIN's structure for the printed name on the right, and the printed name as text."""
    from PIL import Image, ImageDraw
    from rdkit import Chem
    from rdkit.Chem import Draw

    out = work / "sheets"
    out.mkdir(parents=True, exist_ok=True)
    for item in json.loads((work / "sample.json").read_text(encoding="utf-8")):
        crop = Image.open(work / "crops" / f"{item['label']}.png").convert("RGB")
        depiction = Draw.MolToImage(Chem.MolFromSmiles(item["smiles"]), size=(420, 300)).convert("RGB")
        sheet = Image.new("RGB", (crop.width + depiction.width + 30, max(crop.height, depiction.height + 60) + 40), "white")
        sheet.paste(crop, (0, 40))
        sheet.paste(depiction, (crop.width + 30, 40))
        mol = Chem.MolFromSmiles(item["smiles"])
        from rdkit.Chem.rdMolDescriptors import CalcMolFormula

        rings = sorted(len(r) for r in mol.GetRingInfo().AtomRings())
        # Formula and ring sizes are the checks a person can make against a drawing that a depiction of a bridged or fused system hides.
        facts = f"formula {CalcMolFormula(mol)}   rings {rings}   smiles {item['smiles'][:90]}"
        draw = ImageDraw.Draw(sheet)
        draw.text((6, 6), f"{item['label']}  printed: {item['printed']}", fill="black")
        draw.text((crop.width + 36, 26), "OPSIN's structure for the printed name", fill="black")
        draw.text((crop.width + 36, 345), facts, fill="black")
        sheet.save(out / f"{item['label']}.png")
    print(f"composed {len(list(out.glob('*.png')))} sheets -> {out}")


def cmd_record(work: Path) -> None:
    verdicts = json.loads((work / "verdicts.json").read_text(encoding="utf-8"))
    bad = {label: v for label, v in verdicts.items() if v.get("class") not in CLASSES or not isinstance(v.get("join_ok"), bool)}
    if bad:
        raise SystemExit(f"verdicts with an unknown class or no join_ok: {sorted(bad)}")
    rows = _load_halves()
    sample_labels = {item["label"] for item in json.loads((work / "sample.json").read_text(encoding="utf-8"))}
    missing = sample_labels - set(verdicts)
    if missing:
        raise SystemExit(f"{len(missing)} sampled rows have no verdict")
    result = evaluate(rows, verdicts, protocol())
    half = {r["label"]: r["half"] for r in rows}
    statuses = result["statuses"]
    oracle = {
        "protocol_sha256": harvest.protocol_sha256(),
        "summary": result["summary"],
        "strata": result["strata"],
        "status_counts": {h: {s: sum(1 for label, st in statuses.items() if half[label] == h and st == s)
                              for s in (VALIDATED, ACCEPTED, UNCERTAIN, REJECTED)} for h in ("tuning", "frozen")},
        # label -> status for EVERY row. Labels are opaque hashes of a structure, so this reveals a frozen row's status and nothing about the row.
        "status": dict(sorted(statuses.items())),
    }
    (BENCH / ORACLE_FILE).write_text(json.dumps(oracle, indent=1), encoding="utf-8")

    by_label = {r["label"]: r for r in rows}
    lines = ["# The Blue Book hand check: for each sampled TUNING row, is OPSIN's structure the structure the book draws?",
             "# Frozen rows' verdicts are in the sealed sidecar (stages/sealed/), never here. Written by tools/naming_bluebook_handcheck.py record.\n"]
    sealed = {}
    for label in sorted(sample_labels):
        v = verdicts[label]
        if half[label] == "frozen":
            sealed[label] = v
            continue
        row = by_label[label]
        lines.append(f'[[check]]\nlabel = "{label}"\npage = {row["locations"][0]["page"]}\nchapter = {row["chapter"]}\nclass = "{v["class"]}"\njoin_ok = {str(v["join_ok"]).lower()}')
        if v.get("note"):
            lines.append("note = " + json.dumps(v["note"]))
        lines.append("")
    (BENCH / HANDCHECK_FILE).write_text("\n".join(lines), encoding="utf-8")
    SEALED_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEALED_FILE.write_text(json.dumps(sealed, indent=1), encoding="utf-8")
    print(json.dumps({"summary": result["summary"], "status_counts": oracle["status_counts"]}, indent=1))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("sample", "crops", "sheets", "record"):
        p = sub.add_parser(name)
        p.add_argument("--work", type=Path, required=True, help="a scratch directory OUTSIDE the repository")
        if name == "crops":
            p.add_argument("--pdf", type=Path, required=True)
    args = parser.parse_args()
    if ROOT in args.work.resolve().parents:
        parser.error("the hand-check work directory holds frozen rows' crops and must be outside the repository")
    {"sample": lambda: cmd_sample(args.work), "crops": lambda: cmd_crops(args.work, args.pdf), "sheets": lambda: cmd_sheets(args.work),
     "record": lambda: cmd_record(args.work)}[args.command]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
