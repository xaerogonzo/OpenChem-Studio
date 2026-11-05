"""Build maintainer-side training-index manifests for the engine preregistration test.

Reads PDB-code lists from Alex's off-repo folders (see PREREGISTRATION_ENGINE.md),
intersects them with the catalogued receptor PDB ids, and writes a small JSON report.
Nothing bulk-copyrighted is committed except the intersection sets used by tests.

    uv run --no-sync python tools/build_engine_training_overlap.py
    uv run --no-sync python tools/build_engine_training_overlap.py --write-core
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from openchem.chem.receptor_library import RECEPTOR_LIBRARY  # noqa: E402

DEFAULT_MAINTAINER_ROOT = Path(r"E:/My Area/Claude/OpenChem Studio")
TRAINING_DIR = DEFAULT_MAINTAINER_ROOT / "docking/training_indexes"
PDBBIND_DEMO = DEFAULT_MAINTAINER_ROOT / "Pdbind-plus_demo"
CORE_CSV = TRAINING_DIR / "pdbbind_extract/v2013-core/pdbbind_v2013_core.csv"
CSAR_TSV = TRAINING_DIR / "BindingDB_CSAR.tsv"
DKOES_PROXY_MANIFEST = TRAINING_DIR / "dkoes_csar_bindingdb_proxy.json"
PDBBIND_PL_INDEX = PDBBIND_DEMO / "index/INDEX_general_PL.2020R1.lst"
PDBBIND_2007_REFINED_INDEX = (
    TRAINING_DIR
    / "pdbbind_v2007_indexes/home/ubuntu/v2007/INDEX.2007.refined.data"
)
PDBBIND_2007_GENERAL_INDEX = (
    TRAINING_DIR
    / "pdbbind_v2007_indexes/home/ubuntu/v2007/INDEX.2007.general.data"
)
#: Nature Protocols 2018 Table S3 vs DeepChem's 193: the two missing Core 2013 codes.
CORE2013_DEEPCHEM_GAP = frozenset({"3zso", "3zsx"})
CORE2013_OFFICIAL_COUNT = 195
VINA_PDBBIND_2007_REFINED_COUNT = 1300

DKOES_PROXY_META = {
    "arm": "smina-dkoes_fast",
    "intended_training_set": "CSAR-NRC HiQ 2010 (343 complexes per ci200082t)",
    "locked_to": "bindingdb_csar_202611_tsv",
    "source_url": "https://www.bindingdb.org/rwd/bind/downloads/BindingDB_CSAR_202611_tsv.zip",
    "reason": (
        "CSAR_NRC_HiQ_Set tar and csardock.org are gone; koes2013 PMC SI "
        "(NIHMS443682-supplement-1_si_001.zip) is RapidMiner workflows only — "
        "no set1.csv or KEEP_LIST.txt. BindingDB CSAR export is the held PDB index."
    ),
    "caveat": (
        "818 CSAR-curated rows yield 746 unique PDB codes. HiQ 343 as a named file "
        "was not recovered; freeze uses this CSAR index. Unconfirmed HiQ-era catalog "
        "ids are not written into TRAINING_OVERLAP."
    ),
}

PDB_RE = re.compile(r"\b([0-9][a-z0-9]{3})\b", re.I)


def catalog_pdbs() -> frozenset[str]:
    return frozenset(e.pdb_id.lower() for e in RECEPTOR_LIBRARY)


def read_pdbbind_core2013(path: Path) -> frozenset[str]:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    return frozenset(r["pdb_id"].lower() for r in rows)


def read_pdbbind_pl_index(path: Path) -> frozenset[str]:
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        ids.add(line.split()[0].lower())
    return frozenset(ids)


def read_bindingdb_csar_pdbs(path: Path) -> frozenset[str]:
    """PDB codes from BindingDB's CSAR export (PDB columns only — not sequences)."""
    found: set[str] = set()
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        pdb_cols = [
            c
            for c in (reader.fieldnames or [])
            if c == "PDB ID(s) for Ligand-Target Complex"
            or c.startswith("PDB ID(s) of Target Chain ")
        ]
        for row in reader:
            for col in pdb_cols:
                cell = (row.get(col) or "").strip()
                if not cell:
                    continue
                for match in PDB_RE.finditer(cell):
                    found.add(match.group(1).lower())
    return frozenset(found)


def audit_pl_extraction(demo_root: Path, index_ids: frozenset[str]) -> dict[str, int | bool]:
    pl_root = demo_root / "P-L/P-L"
    if not pl_root.is_dir():
        return {"present": False}
    on_disk: set[str] = set()
    for bucket in pl_root.iterdir():
        if not bucket.is_dir():
            continue
        for pdb_dir in bucket.iterdir():
            if pdb_dir.is_dir() and re.fullmatch(r"[0-9a-z]{4}", pdb_dir.name, re.I):
                on_disk.add(pdb_dir.name.lower())
    missing = len(index_ids - on_disk)
    return {
        "present": True,
        "index_count": len(index_ids),
        "extracted_pdb_dirs": len(on_disk),
        "missing_from_index": missing,
        "complete": missing == 0,
    }


def overlap_block(name: str, training: frozenset[str], catalog: frozenset[str]) -> dict:
    hit = sorted(catalog & training)
    return {
        "source": name,
        "training_count": len(training),
        "catalog_overlap": hit,
        "catalog_overlap_count": len(hit),
    }


def write_dkoes_proxy_manifest(
    pdbs: frozenset[str],
    catalog: frozenset[str],
    path: Path = DKOES_PROXY_MANIFEST,
) -> dict:
    """Write maintainer-side dkoes training proxy (746 PDB codes from BindingDB)."""
    overlap = sorted(catalog & pdbs)
    payload = {
        **DKOES_PROXY_META,
        "pdb_count": len(pdbs),
        "pdb_ids": sorted(pdbs),
        "catalog_overlap": overlap,
        "catalog_overlap_count": len(overlap),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def build_report() -> dict:
    catalog = catalog_pdbs()
    blocks: list[dict] = []

    if CORE_CSV.is_file():
        core = read_pdbbind_core2013(CORE_CSV)
        blocks.append(overlap_block("pdbbind_core2013_deepchem", core, catalog))
        official = core | CORE2013_DEEPCHEM_GAP
        if len(official) != CORE2013_OFFICIAL_COUNT:
            raise SystemExit(
                f"Core 2013 official reconstruction is {len(official)}, "
                f"not {CORE2013_OFFICIAL_COUNT}"
            )
        blocks.append(overlap_block("pdbbind_core2013_official_195", official, catalog))
    else:
        blocks.append({"source": "pdbbind_core2013_deepchem", "missing": str(CORE_CSV)})

    if PDBBIND_2007_REFINED_INDEX.is_file():
        refined = read_pdbbind_pl_index(PDBBIND_2007_REFINED_INDEX)
        if len(refined) != VINA_PDBBIND_2007_REFINED_COUNT:
            raise SystemExit(
                f"PDBbind 2007 refined is {len(refined)}, "
                f"not {VINA_PDBBIND_2007_REFINED_COUNT}"
            )
        blocks.append(overlap_block("pdbbind_v2007_refined", refined, catalog))
    else:
        blocks.append(
            {"source": "pdbbind_v2007_refined", "missing": str(PDBBIND_2007_REFINED_INDEX)}
        )

    if PDBBIND_2007_GENERAL_INDEX.is_file():
        general = read_pdbbind_pl_index(PDBBIND_2007_GENERAL_INDEX)
        blocks.append(overlap_block("pdbbind_v2007_general", general, catalog))

    dkoes_proxy: dict | None = None
    if CSAR_TSV.is_file():
        csar = read_bindingdb_csar_pdbs(CSAR_TSV)
        blocks.append(overlap_block("bindingdb_csar_202611", csar, catalog))
        blocks.append(
            overlap_block("dkoes_training_proxy_bindingdb746", csar, catalog)
        )
        dkoes_proxy = write_dkoes_proxy_manifest(csar, catalog)
    else:
        blocks.append({"source": "bindingdb_csar_202611", "missing": str(CSAR_TSV)})

    pl_audit: dict | None = None
    if PDBBIND_PL_INDEX.is_file():
        pl_ids = read_pdbbind_pl_index(PDBBIND_PL_INDEX)
        pl_audit = audit_pl_extraction(PDBBIND_DEMO, pl_ids)
        blocks.append(overlap_block("pdbbind_plus_demo_pl_index", pl_ids, catalog))

    #: Only lists that belong to a candidate's training set (not PDBbind 2020 PL,
    #: not 2007 general — Vina's paper names the refined set).
    stratum_sources = {
        "pdbbind_core2013_official_195",
        "pdbbind_v2007_refined",
        "dkoes_training_proxy_bindingdb746",
    }
    union = frozenset().union(
        *(
            set(b["catalog_overlap"])
            for b in blocks
            if b.get("source") in stratum_sources and "catalog_overlap" in b
        )
    )
    return {
        "catalog_count": len(catalog),
        "blocks": blocks,
        "training_overlap_stratum": sorted(union),
        "notes": {
            "koes2013_si": (
                "PMC3726561 supplement-1 (NIHMS443682-supplement-1_si_001.zip) matches "
                "D:/Xaero Stuff/Documents/Sci Downloads/koes2013_si — RapidMiner only, "
                "no HiQ PDB list. dkoes arm uses BindingDB CSAR as the surviving CSAR "
                "PDB index; HiQ 343 as a named file was not recovered and does not "
                "populate TRAINING_OVERLAP."
            ),
            "vina_training": (
                "Trott & Olson: training set for Vina is the PDBbind refined set. "
                "Index: DGL pdbbind_v2007 INDEX.2007.refined.data, n=1300."
            ),
            "vinardo_training": (
                "Quiroga 122 ⊂ PDBbind Core 2013 (195). Official 195 = DeepChem 193 "
                "plus 3zso and 3zsx from Nature Protocols 2018 Table S3."
            ),
            "dkoes_proxy_manifest": str(DKOES_PROXY_MANIFEST) if dkoes_proxy else None,
            "pdbbind_pl_structures": pl_audit,
        },
    }


def write_engine_core_training_overlap(union: frozenset[str]) -> None:
    path = ROOT / "benchmarks/docking/engine_core.py"
    text = path.read_text(encoding="utf-8")
    body = ", ".join(f'"{p.upper()}"' for p in sorted(union))
    new_line = f"TRAINING_OVERLAP: frozenset[str] = frozenset({{{body}}})"
    if "TRAINING_OVERLAP: frozenset[str] = frozenset()" in text:
        text = text.replace(
            "TRAINING_OVERLAP: frozenset[str] = frozenset()",
            new_line,
        )
        path.write_text(text, encoding="utf-8")
        print(f"Updated {path} TRAINING_OVERLAP ({len(union)} receptors)")
    else:
        print("engine_core.py TRAINING_OVERLAP already set; not overwriting", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        type=Path,
        default=TRAINING_DIR / "training_overlap_report.json",
    )
    parser.add_argument(
        "--write-core",
        action="store_true",
        help="Write union overlap into benchmarks/docking/engine_core.py (only if still empty).",
    )
    args = parser.parse_args()
    report = build_report()
    payload = json.dumps(report, indent=2) + "\n"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(payload, encoding="utf-8")
    artifact = ROOT / "benchmarks/docking/artifacts_engine_gates/training_overlap_report.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(payload, encoding="utf-8")
    print(json.dumps(report, indent=2))
    if args.write_core:
        union = frozenset(report["training_overlap_stratum"])
        write_engine_core_training_overlap(union)


if __name__ == "__main__":
    main()
