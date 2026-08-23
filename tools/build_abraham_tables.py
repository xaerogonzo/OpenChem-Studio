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
    "doi:10.1186/s13065-015-0085-4. Table 1, measured solvents only. CC BY 4.0. "
    "Acetic acid is NOT from this table -- see `solvent_sources`: Stovall DM, "
    "Schmidt A, Dai C, Zhang S, Acree WE Jr, Abraham MH. Abraham model correlations "
    "for estimating solute transfer of neutral molecules into anhydrous acetic acid "
    "from water and from the gas phase. J Mol Liq 2015;212:16-22. "
    "doi:10.1016/j.molliq.2015.08.042, Eq. (6)."
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


#: Acetic acid, MEASURED -- the one solvent here that does not come from
#: Bradley's Table 1.
#:
#: **THIS IS A DEFERRAL WHOSE REASON ROTTED, NOT A NEW FEATURE.** Alex
#: asked for acetic acid by name during the solubility work and it was
#: refused, with the reason recorded in `docs/VALIDATION.md`: only
#: PREDICTED coefficients existed, they failed this module's own 1.0-log
#: uncertainty ceiling, and the predicted table is the `c = 0` refit and
#: so carries no intercept at all. Both halves of that are now false.
#:
#: Stovall, Schmidt, Dai, Zhang, Acree & Abraham, "Abraham model
#: correlations for estimating solute transfer of neutral molecules into
#: anhydrous acetic acid from water and from the gas phase", J. Mol. Liq.
#: 212 (2015) 16-22, doi 10.1016/j.molliq.2015.08.042, Eq. (6):
#:
#:     log P = 0.175 + 0.174 E - 0.454 S - 1.073 A - 2.789 B + 3.725 V
#:     N = 68, SD = 0.182, R2 = 0.980, F = 612.4
#:
#: TYPED FROM THE PAPER, not fetched, because it is not open access --
#: which is why the standard errors are carried beside the values below
#: rather than left in a comment. They are the paper's own, printed in
#: parentheses after each coefficient.
#:
#: **THE INTERCEPT IS THE HALF THAT IS EASY TO MISS.** `c = 0.175` is
#: what the predicted table has no column for, and the solubility
#: equation needs it -- see `chem/abraham.py` on why the `c = 0` refit is
#: the wrong parameterisation for anything but comparing solvents.
_MEASURED_ELSEWHERE = {
    "acetic acid": {
        "coefficients": {
            "c": 0.175,
            "e": 0.174,
            "s": -0.454,
            "a": -1.073,
            "b": -2.789,
            "v": 3.725,
        },
        #: The paper's printed standard error on each coefficient. Kept
        #: because the refusal this replaces was decided by propagating
        #: the PREDICTED set's much larger out-of-bag errors, and the
        #: comparison only means anything if both are recorded.
        "standard_errors": {
            "c": 0.049,
            "e": 0.086,
            "s": 0.115,
            "a": 0.123,
            "b": 0.163,
            "v": 0.081,
        },
        "source_key": "stovall2015",
        "fit": {"n": 68, "sd": 0.182, "r2": 0.980},
    }
}


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


def build_predicted_only_names() -> list[str]:
    """Names from the paper's PREDICTED table, which are deliberately NOT shipped.

    Captured so a user asking for one gets the real reason rather than
    "not in the table" -- which reads as an oversight when the truth is
    that the numbers exist and the paper's own held-out error makes them
    unusable. Acetic acid is the case that motivated this; it was asked
    for by name.

    That table is the `c = 0` refit only (`e0 s0 a0 b0 v0`), the paper's
    equation 3 for log P. The solubility equation needs the intercept, so
    even a solvent whose predicted error were acceptable could not be used
    from this table without the measured `c`.
    """
    tables = re.findall(r"<table.*?</table>", _get(_SOLVENT_URL), re.S)
    names: list[str] = []
    for table in tables:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S)
        if not rows:
            continue
        header = [" ".join(c.split()) for c in _cells(rows[0])]
        # The predicted table leads with Solvent and carries ONLY the
        # c=0 columns; the measured one leads with `c`.
        if not header or header[0].lower() != "solvent":
            continue
        for row in rows[1:]:
            cells = _cells(row)
            if cells and cells[0]:
                names.append(" ".join(cells[0].split()).lower())
    return sorted(set(names))


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
    # The measured coefficients that are NOT in Bradley's Table 1, added
    # after their own source was read. `solvent_sources` names them, so a
    # reader can tell which paper any one solvent came from rather than
    # inferring it from the file-level `_source_key`.
    solvent_sources = {}
    for name, entry in _MEASURED_ELSEWHERE.items():
        solvents[name] = dict(entry["coefficients"])
        solvent_sources[name] = entry["source_key"]
    standard_errors = {
        name: entry["standard_errors"] for name, entry in _MEASURED_ELSEWHERE.items()
    }
    predicted_only = [n for n in build_predicted_only_names() if n not in
                      {k.lower() for k in solvents}]
    (OUT / "abraham_solvents.json").write_text(
        json.dumps(
            {
                # EMITTED HERE rather than hand-added afterwards. It was
                # hand-added before, so regenerating this file silently
                # dropped it and `test_every_shipped_data_table_declares_
                # its_source` would have gone red on the next rebuild.
                "_source_key": "bradley2015",
                "_supplementary_source_keys": sorted(set(solvent_sources.values())),
                "attribution": _ATTRIBUTION_SOLVENTS,
                "solvents": solvents,
                # Which solvents did NOT come from `_source_key`.
                "solvent_sources": solvent_sources,
                # The paper's own standard error per coefficient, for the
                # solvents whose source prints them.
                "solvent_standard_errors": standard_errors,
                # Named so a request for one can be refused with its real
                # reason. NOT coefficients -- deliberately no numbers here,
                # so nothing downstream can start using them.
                "predicted_only": predicted_only,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    print(
        f"solvents: {len(solvents)} measured "
        f"({len(solvent_sources)} from a source other than {_ATTRIBUTION_SOLVENTS[:24]!r}...), "
        f"{len(predicted_only)} predicted-only named"
    )

    solutes, rejected = build_solutes()
    (OUT / "abraham_solutes.json").write_text(
        json.dumps({"attribution": _ATTRIBUTION_SOLUTES, "solutes": solutes}, indent=0),
        encoding="utf-8",
    )
    print(f"solutes:  {len(solutes)} usable, rejected {rejected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
