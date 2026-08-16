"""Build `chem/data/abraham_solvents.json` and `abraham_solutes.json`.

    uv run --no-sync python tools/build_abraham_tables.py

Two CC-BY 4.0 sources, both free and both fetched rather than typed:

  * **Solvent coefficients** -- Bradley, Abraham & Acree, "Predicting
    Abraham model solvent coefficients", BMC Chemistry 2015, doi
    10.1186/s13065-015-0085-4, Table 1. 91 MEASURED solvents. The paper
    also predicts coefficients for 293 solvents and says of those "not as
    gospel", so only the measured table is taken.

  * **Solute descriptors** -- Bradley, Acree & Lang, "Compounds with known
    Abraham descriptors", figshare 2014, doi 10.6084/m9.figshare.1176994.
    Experimental E, S, A, B, V, L per compound, with the literature source
    on every row.

**THE DESCRIPTORS ARE MEASURED, NOT PREDICTED, AND THAT IS THE WHOLE
POINT.** The alternative route was the Platts group-contribution scheme --
roughly 480 coefficients and 132 hand-written SMARTS patterns to
transcribe, adding 0.7-1.0 log of its own error. Looking up an
experimental descriptor costs neither.

TWO QUALITY GATES IN THE SOURCE DATA, BOTH HONOURED:

  * a `donotuse` column with a written reason -- 6 rows carry it;
  * `-123` as a missing-value sentinel, which a naive float() reads as a
    perfectly ordinary number and which would poison every prediction
    made from that row. 513 rows carry at least one.

The lookup key is the InChIKey computed from the source SMILES by RDKit,
so a user's drawn structure matches on constitution and stereochemistry
rather than on how somebody wrote the SMILES.
"""

from __future__ import annotations

import html
import json
import re
import ssl
import statistics
import urllib.request
from pathlib import Path

import certifi
from rdkit import Chem, RDLogger
from rdkit.Chem import inchi

RDLogger.DisableLog("rdApp.*")

OUT = Path(__file__).resolve().parents[1] / "src" / "openchem" / "chem" / "data"

_SOLVENT_URL = "https://pmc.ncbi.nlm.nih.gov/articles/PMC4369285/"
_SOLUTE_URL = "https://ndownloader.figshare.com/files/1684722"

_ATTRIBUTION_SOLVENTS = (
    "Bradley J-C, Abraham MH, Acree WE Jr, Lang ASID. Predicting Abraham model solvent "
    "coefficients. Chemistry Central Journal / BMC Chemistry 2015;9:12. "
    "doi:10.1186/s13065-015-0085-4. Table 1, measured solvents only. CC BY 4.0."
)
_ATTRIBUTION_SOLUTES = (
    "Bradley J-C, Acree WE Jr, Lang ASID. Compounds with known Abraham descriptors. "
    "figshare 2014. doi:10.6084/m9.figshare.1176994. CC BY 4.0."
)

#: The source's missing-value sentinel. Reads as a number and is not one.
_MISSING = -123.0


def _get(url: str) -> str:
    context = ssl.create_default_context(cafile=certifi.where())
    request = urllib.request.Request(url, headers={"User-Agent": "openchem-abraham-build"})
    with urllib.request.urlopen(request, timeout=180, context=context) as response:
        return response.read().decode("utf-8", "replace")


def _cells(row: str) -> list[str]:
    return [
        html.unescape(re.sub(r"<[^>]+>", " ", cell)).replace("−", "-").strip()
        for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)
    ]


def build_solvents() -> dict:
    """Table 1's measured coefficients, keyed by the paper's own name.

    The table interleaves two coefficient sets -- the ordinary
    `c e s a b v` and a `c = 0` refit -- with the solvent NAME between
    them. Only the first set is taken: the c=0 form exists in the paper to
    make solvents comparable with each other, not to be used for
    prediction.
    """
    tables = re.findall(r"<table.*?</table>", _get(_SOLVENT_URL), re.S)
    coefficients: dict[str, dict] = {}
    for table in tables:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S)
        if not rows or _cells(rows[0])[:2] != ["c", "e"]:
            continue
        for row in rows[1:]:
            cells = _cells(row)
            if len(cells) < 12:
                continue
            try:
                numbers = [float(value) for value in cells[:6]]
            except ValueError:
                continue
            name = " ".join(cells[6].split())
            if name:
                coefficients[name] = dict(zip("cesabv", numbers))
    return coefficients


def build_solutes() -> tuple[dict, dict]:
    """Experimental descriptors keyed by InChIKey, plus a rejection tally.

    **A COMPOUND MEASURED TWICE GETS THE MEDIAN AND ITS SPREAD, NOT THE
    FIRST ROW.** 432 InChIKeys appear more than once and only 51 of those
    groups agree exactly; the widest disagreement in a single descriptor
    is 2.24. Acetanilide is the case that settles the design -- three rows
    give S = 3.61, 1.54 and 1.37 and A = 1.908, 0.417 and 0.400, and the
    FIRST of them is the outlier. "Take the first" would have shipped it.

    The spread is kept PER DESCRIPTOR rather than averaged away, because a
    solvent coefficient of -4.9 turns a 0.3 disagreement in B into 1.5 log
    units on the answer. `chem/abraham.py` propagates it into a stated
    uncertainty instead of presenting a median as though it were agreed.

    Per descriptor and not one worst-case number: the first version stored
    only the widest spread and multiplied it by the SUM of the coefficient
    magnitudes, which assumes every descriptor is wrong by the worst
    amount and all in the same direction. That refused aspirin, caffeine
    and ibuprofen -- three of the first four drugs tried.
    """
    text = _get(_SOLUTE_URL)
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S)
    header = _cells(rows[0])
    index = {name: position for position, name in enumerate(header)}
    keys = ("E", "S", "A", "B", "V")

    groups: dict[str, list] = {}
    names: dict[str, str] = {}
    rejected = {"donotuse": 0, "missing sentinel": 0, "unparseable smiles": 0}
    for row in rows[1:]:
        cells = _cells(row)
        if len(cells) < len(header):
            continue
        if cells[index["donotuse"]].strip():
            rejected["donotuse"] += 1
            continue
        try:
            values = [float(cells[index[key]]) for key in keys]
        except ValueError:
            rejected["missing sentinel"] += 1
            continue
        if any(value == _MISSING for value in values):
            rejected["missing sentinel"] += 1
            continue
        mol = Chem.MolFromSmiles(cells[index["smiles"]].strip())
        if mol is None:
            rejected["unparseable smiles"] += 1
            continue
        key = inchi.MolToInchiKey(mol)
        groups.setdefault(key, []).append(values)
        names.setdefault(key, cells[index["name"]].strip())

    solutes: dict[str, dict] = {}
    for key, measurements in groups.items():
        entry = {"name": names[key], "n": len(measurements)}
        spreads = {}
        for position, label in enumerate(keys):
            column = [row[position] for row in measurements]
            entry[label.lower()] = round(statistics.median(column), 4)
            spread = round(max(column) - min(column), 4)
            if spread:
                spreads[label.lower()] = spread
        # Omitted entirely when every row agreed, which is the common case
        # and keeps the shipped file small.
        if spreads:
            entry["spread"] = spreads
        solutes[key] = entry
    rejected["duplicate rows merged"] = sum(len(g) for g in groups.values()) - len(groups)
    return solutes, rejected


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    solvents = build_solvents()
    (OUT / "abraham_solvents.json").write_text(
        json.dumps({"attribution": _ATTRIBUTION_SOLVENTS, "solvents": solvents}, indent=1),
        encoding="utf-8",
    )
    print(f"solvents: {len(solvents)} measured")

    solutes, rejected = build_solutes()
    (OUT / "abraham_solutes.json").write_text(
        json.dumps({"attribution": _ATTRIBUTION_SOLUTES, "solutes": solutes}, indent=0),
        encoding="utf-8",
    )
    print(f"solutes:  {len(solutes)} usable, rejected {rejected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
