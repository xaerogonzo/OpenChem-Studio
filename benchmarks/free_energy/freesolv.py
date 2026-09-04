"""The FreeSolv hydration free energy database, as an acceptance oracle.

642 small molecules with EXPERIMENTAL hydration free energies and, beside
each one, the value the Mobley group CALCULATED with GAFF/AM1-BCC at an
uncertainty of about 0.03 kcal/mol.

**THE CALCULATED COLUMN IS WHY THIS SET WAS CHOSEN, and it is a stronger
oracle than experiment.** Comparing our answer to experiment conflates two
different errors -- a wrong protocol and a right protocol on an imperfect
force field -- and cannot tell them apart. Comparing it to a published
GAFF/AM1-BCC number, computed with the same force field, isolates the
protocol. If ours reproduces theirs, the machinery is right whatever GAFF's
own limitations are; if it does not, something in our setup differs and the
experimental agreement would have hidden it.

That is the roadmap's Route 3 acceptance criterion -- "a published
congeneric series reproduced before any answer of ours is believed" -- at a
scale that runs in minutes rather than days, and with no protein, no atom
mapping and no missing-residue repair in the way.

NOTHING IS COMMITTED. The database is fetched and cached outside the tree,
the same pattern `benchmarks/solubility/fetch.py` uses.

    uv run --no-sync python benchmarks/free_energy/freesolv.py --summary
    uv run --no-sync python benchmarks/free_energy/freesolv.py --pick 6
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

#: **STDLIB ONLY, DELIBERATELY.** This module is imported by the validation
#: driver, which runs inside the WSL conda environment where `openchem` is
#: not installed -- AmberTools has no win-64 build, so the reference
#: protocol cannot run in the project's own venv. Reaching for
#: `openchem.net.open_url` here would make the oracle unimportable exactly
#: where the calculation happens.
from urllib.request import urlopen

#: The database's own master copy. Version 0.52, the latest the repository
#: publishes; its header line carries that version and the guard below
#: reads it rather than assuming, so a silently updated file is visible.
DATABASE_URL = "https://raw.githubusercontent.com/MobleyLab/FreeSolv/master/database.txt"

#: Semicolon-delimited, and the columns are named in the file's own header:
#: id; SMILES; iupac; experimental; experimental uncertainty; calculated
#: (GAFF); calculated uncertainty; experimental reference; calculated
#: reference; notes.
_EXPECTED_COLUMNS = 10


@dataclass(frozen=True, slots=True)
class Compound:
    identifier: str
    smiles: str
    name: str
    experimental_kcal_mol: float
    experimental_uncertainty: float
    calculated_kcal_mol: float
    calculated_uncertainty: float


def _cache_path() -> Path:
    """Cached beside this script rather than in the app's data root, for the
    same reason the import above is stdlib: the data root is an `openchem`
    concept and this file has to work where `openchem` is absent. Kept out
    of git by `.gitignore`, like `benchmarks/visual/artifacts`."""
    directory = Path(__file__).resolve().parent / "cache"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "database.txt"


def fetch(refresh: bool = False) -> str:
    path = _cache_path()
    if path.is_file() and not refresh:
        return path.read_text(encoding="utf-8")
    with urlopen(DATABASE_URL, timeout=60) as response:  # noqa: S310 - fixed https URL
        text = response.read().decode("utf-8")
    path.write_text(text, encoding="utf-8")
    return text


def parse(text: str) -> list[Compound]:
    """Every row, or a refusal.

    **FAIL-CLOSED ON THE COLUMN COUNT.** A silently reshaped file would put
    the calculated value in the uncertainty's place and produce a benchmark
    that reads plausibly and compares the wrong numbers. Ten columns are what
    the file's own header documents; anything else raises rather than being
    parsed as far as it goes.
    """
    compounds: list[Compound] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = [f.strip() for f in line.split(";")]
        if len(fields) != _EXPECTED_COLUMNS:
            raise ValueError(
                f"FreeSolv line {line_number} has {len(fields)} fields, "
                f"expected {_EXPECTED_COLUMNS}. The file's format has changed; "
                f"do not trust a partial parse of it."
            )
        compounds.append(
            Compound(
                identifier=fields[0],
                smiles=fields[1],
                name=fields[2],
                experimental_kcal_mol=float(fields[3]),
                experimental_uncertainty=float(fields[4]),
                calculated_kcal_mol=float(fields[5]),
                calculated_uncertainty=float(fields[6]),
            )
        )
    return compounds


def load(refresh: bool = False) -> list[Compound]:
    return parse(fetch(refresh))


def easy_subset(compounds: list[Compound], count: int) -> list[Compound]:
    """A small, deliberately EASY set to prove the pipeline on.

    Chosen by heavy-atom count and neutrality rather than by how well
    anything scores on them -- picking molecules because a method does well
    on them is how a benchmark becomes a description of its own result.

    Small and rigid keeps the sampling problem out of the way: the first
    question is whether the machinery is right, and a flexible solute
    answers a different one (whether the sampling converged) at the same
    time.
    """
    def heavy_atoms(smiles: str) -> int:
        # Cheap and adequate for ORDERING: every upper-case element letter
        # plus lower-case aromatic atoms, minus nothing. Not a formula
        # parser, and it does not need to be -- it is a sort key.
        return sum(1 for ch in smiles if ch.isalpha() and ch not in "lrHn") or len(smiles)

    neutral = [c for c in compounds if "+" not in c.smiles and "-" not in c.smiles]
    return sorted(neutral, key=lambda c: (heavy_atoms(c.smiles), c.identifier))[:count]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--pick", type=int, default=0)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    compounds = load(args.refresh)
    print(f"FreeSolv: {len(compounds)} compounds, cached at {_cache_path()}")

    if args.summary:
        gaff_error = [c.calculated_kcal_mol - c.experimental_kcal_mol for c in compounds]
        mae = sum(abs(e) for e in gaff_error) / len(gaff_error)
        rmse = (sum(e * e for e in gaff_error) / len(gaff_error)) ** 0.5
        print("\nThe published GAFF column against experiment -- the FORCE FIELD's")
        print("own error, which is the floor our protocol cannot beat:")
        print(f"  n {len(gaff_error)}   MAE {mae:.2f}   RMSE {rmse:.2f} kcal/mol")
        print("\n  So an agreement with EXPERIMENT better than ~1 kcal/mol would be")
        print("  luck rather than skill, while an agreement with the CALCULATED")
        print("  column is a statement about our machinery. That is the whole")
        print("  reason both columns are carried.")

    if args.pick:
        print(f"\n{'id':<18}{'name':<28}{'exp':>7}{'+/-':>6}{'GAFF':>8}{'+/-':>6}  SMILES")
        for c in easy_subset(compounds, args.pick):
            print(f"{c.identifier:<18}{c.name[:27]:<28}"
                  f"{c.experimental_kcal_mol:>7.2f}{c.experimental_uncertainty:>6.2f}"
                  f"{c.calculated_kcal_mol:>8.2f}{c.calculated_uncertainty:>6.2f}  {c.smiles}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
