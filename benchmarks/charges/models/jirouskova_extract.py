"""Read Jiroušková et al. 2009's Table 2 from the PDF's TEXT LAYER (the first of the two independent readings; the second is
`tests/fixtures/charges/jirouskova2009/table2.csv`, typed from the page rendered at 300 dpi).

Run through a throwaway environment (the repository does not depend on pymupdf):

    uvx --with pymupdf python benchmarks/charges/models/jirouskova_extract.py "<path to the PDF>" tests/fixtures/charges/jirouskova2009/table2_textlayer.json

The two readings are compared, exactly, by `tests/test_jirouskova_eem_table.py`; a disagreement means one of them is a typo.
"""

from __future__ import annotations

import json
import re
import sys

import pymupdf

#: One printed number with its 95% interval: "2.659 ± 0.026".
_PLUS_MINUS = re.compile(r"^(\d+\.\d+)\s*±\s*(\d+\.\d+)$")
_PLAIN = re.compile(r"^\d+\.\d+$")
_ELEMENT = re.compile(r"^[A-Z][a-z]?$")


def read_table(pdf_path: str) -> dict:
    document = pymupdf.open(pdf_path)
    tokens: list[str] = []
    for page in document:
        text = page.get_text()
        if "EEM parameters obtained using" not in text:
            continue
        tokens = [line.strip() for line in text.splitlines() if line.strip()]
        break
    if not tokens:
        raise SystemExit("Table 2 was not found in the text layer")
    start = tokens.index("Element and bond order")
    kappas = [float(m.group(1)) for t in tokens for m in [re.search(r"κ = (\d\.\d+)", t)] if m]
    rows = []
    i = start + 1
    while i < len(tokens):
        if not _ELEMENT.match(tokens[i]) or not tokens[i + 1].isdigit():
            i += 1
            continue
        element, order = tokens[i], int(tokens[i + 1])
        cells = tokens[i + 2 : i + 8]
        pairs = [_PLUS_MINUS.match(cells[k]) for k in (0, 1, 3, 4)]
        plains = [_PLAIN.match(cells[k]) for k in (2, 5)]
        if not all(pairs) or not all(plains):
            break
        rows.append(
            {
                "element": element,
                "bond_order": order,
                "b3lyp": {"A": float(pairs[0].group(1)), "A_pm": float(pairs[0].group(2)), "B": float(pairs[1].group(1)), "B_pm": float(pairs[1].group(2)), "s": float(plains[0].group(0))},
                "hf": {"A": float(pairs[2].group(1)), "A_pm": float(pairs[2].group(2)), "B": float(pairs[3].group(1)), "B_pm": float(pairs[3].group(2)), "s": float(plains[1].group(0))},
            }
        )
        i += 8
    ravg = [float(t) for t in tokens if t in ("0.941", "0.940")]
    return {"kappa_b3lyp": kappas[0], "kappa_hf": kappas[1], "rows": rows, "ravg_mol": ravg}


if __name__ == "__main__":
    table = read_table(sys.argv[1])
    with open(sys.argv[2], "w", encoding="utf-8", newline="\n") as handle:
        json.dump(table, handle, indent=1, ensure_ascii=False)
        handle.write("\n")
    print(len(table["rows"]), "rows", table["kappa_b3lyp"], table["kappa_hf"], table["ravg_mol"])
