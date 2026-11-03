"""Stage 1 of the COD census for Phase B (crystal density): one streaming pass over the COD archive.

Reads `cod-cifs-mysql.txz` as a stream (nothing is written to disk but the index; unpacking half a million small files
measured 15 files/s on this machine, streaming 13,000/s) and records, for every CIF, the few header fields the census
needs: the COD code, the formula, the measurement temperature (and which tag it came from), pressure, the diffraction
density, the R factors, the journal year, the space group, Z and COD's own error flag. Nothing about structure is read here.

    python -I cod_index.py --archive "E:/.../cod-cifs-mysql.txz" --out "E:/.../index/cod_index.sqlite"

COD data is dedicated to the public domain (CC0); the archive and the index live OUTSIDE the repository.
This script reads values; it scores nothing and decides nothing about which entries count (that is the census, stage 2).
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import tarfile
import time
from pathlib import Path

#: tag -> column. The first tag listed for a column that is present wins (`temperature` prefers the diffraction tag).
SIMPLE = {
    "formula": ("_chemical_formula_sum",),
    "temperature_raw": ("_diffrn_ambient_temperature", "_cell_measurement_temperature"),
    "temperature_tag": (),
    "pressure_raw": ("_diffrn_ambient_pressure", "_cell_measurement_pressure"),
    "density_diffrn_raw": ("_exptl_crystal_density_diffrn",),
    "density_meas_raw": ("_exptl_crystal_density_meas",),
    "r_gt_raw": ("_refine_ls_R_factor_gt",),
    "r_all_raw": ("_refine_ls_R_factor_all",),
    "wr_raw": ("_refine_ls_wR_factor_ref", "_refine_ls_wR_factor_all"),
    "year": ("_journal_year",),
    "space_group": ("_symmetry_space_group_name_H-M", "_space_group_name_H-M_alt"),
    "z_raw": ("_cell_formula_units_Z",),
    "error_flag": ("_cod_error_flag",),
}
_TAGS = {tag: col for col, tags in SIMPLE.items() for tag in tags}
_LINE = re.compile(r"^(_[A-Za-z0-9_.\-\[\]]+)\s+(.*?)\s*$")
_NUMBER = re.compile(r"^[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def number(raw: str | None) -> float | None:
    """`293(2)` -> 293.0; `?`, `.` and anything else -> None. The uncertainty in brackets is dropped, never read as a value."""
    if not raw:
        return None
    m = _NUMBER.match(raw.strip().strip("'\""))
    return float(m.group(0)) if m else None


def parse(text: str) -> dict:
    """The header fields of one CIF, as printed (numbers parsed separately by `number`)."""
    out: dict = {}
    seen_tag_for: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("data_") and "code" not in out:
            out["code"] = line[5:].strip()
            continue
        if not line.startswith("_"):
            continue
        m = _LINE.match(line)
        if not m:
            continue
        tag, value = m.group(1), m.group(2)
        col = _TAGS.get(tag)
        if col is None or not value or value in ("?", "."):
            continue
        # the first listed tag for a column wins; a later, lower-priority tag does not overwrite it
        priority = SIMPLE[col].index(tag)
        if col in seen_tag_for and SIMPLE[col].index(seen_tag_for[col]) <= priority:
            continue
        seen_tag_for[col] = tag
        out[col] = value.strip("'\" ")
        if col == "temperature_raw":
            out["temperature_tag"] = tag
    return out


SCHEMA = """
CREATE TABLE IF NOT EXISTS cod (
  code TEXT PRIMARY KEY, path TEXT, formula TEXT, temperature_k REAL, temperature_tag TEXT, temperature_raw TEXT,
  pressure_raw TEXT, density_diffrn REAL, density_diffrn_raw TEXT, density_meas REAL, r_gt REAL, r_all REAL, wr REAL,
  year INTEGER, space_group TEXT, z REAL, error_flag TEXT
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


def run(archive: Path, out: Path, limit: int | None) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    db = sqlite3.connect(out)
    db.executescript(SCHEMA)
    t0 = time.time()
    n = 0
    batch = []
    with tarfile.open(archive, mode="r|xz") as tar:
        for member in tar:
            if not (member.isfile() and member.name.endswith(".cif")):
                continue
            text = tar.extractfile(member).read().decode("utf-8", errors="replace")
            f = parse(text)
            code = f.get("code") or Path(member.name).stem
            batch.append((
                code, member.name, f.get("formula"), number(f.get("temperature_raw")), f.get("temperature_tag"),
                f.get("temperature_raw"), f.get("pressure_raw"), number(f.get("density_diffrn_raw")), f.get("density_diffrn_raw"),
                number(f.get("density_meas_raw")), number(f.get("r_gt_raw")), number(f.get("r_all_raw")), number(f.get("wr_raw")),
                int(number(f.get("year")) or 0) or None, f.get("space_group"), number(f.get("z_raw")), f.get("error_flag")))
            n += 1
            if len(batch) >= 5000:
                db.executemany("INSERT OR REPLACE INTO cod VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", batch)
                db.commit()
                batch.clear()
                print(f"{n} entries, {time.time() - t0:.0f}s", file=sys.stderr, flush=True)
            if limit and n >= limit:
                break
    if batch:
        db.executemany("INSERT OR REPLACE INTO cod VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", batch)
    db.execute("INSERT OR REPLACE INTO meta VALUES ('archive', ?)", (archive.name,))
    db.execute("INSERT OR REPLACE INTO meta VALUES ('entries', ?)", (str(n),))
    db.commit()
    db.close()
    return {"entries": n, "seconds": round(time.time() - t0, 1)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--archive", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=None, help="stop after this many entries (a probe)")
    args = ap.parse_args(argv)
    print(run(args.archive, args.out, args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
