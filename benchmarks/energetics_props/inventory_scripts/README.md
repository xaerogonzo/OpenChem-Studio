# Inventory scripts

What produced the counts in `../inventory.json`, kept so that a count is a procedure and not a memory. **None of this runs in CI** (the sources are copyrighted books in the maintainer's library) and **none of it writes a label into the repository**: the scripts print counts and locators.

| script | source | how |
|---|---|---|
| `acree_census.py` | Acree 2010 (`acree2010.pdf`) | `uvx --with pymupdf python -I acree_census.py out.json`: splits the table text on formula + CAS-number pairs, counts entries whose name matches a polynitro / nitrate / nitramine / azide / azole / peroxide keyword and which print a fusion temperature or a sublimation enthalpy. The keyword is a name filter, not a structure test (it also matches a hydrazide), so the figure is an upper bound |
| `v2_extract.py`, `fieldlib.py`, `analyse.py` | Klapoetke's Encyclopedia, vol 2 (PDF) | entry headings are 12-pt bold lines at the top of a page; the property block is parsed by field label (`Tm.p.`, `Tdec.`, density items, heat of formation items) |
| `epub_extract.py`, `fieldlib.py`, `analyse.py` | Klapoetke's Encyclopedia, vols 1 and 3 (EPUB) | one chapter file per entry; the property table is an image in most entries and was read with RapidOCR (`uvx --with rapidocr-onnxruntime --with "numpy<2"`) and rebuilt into rows from the coordinates; **the OCR step, its job list and its image cache are not committed** |

The monograph counts (Meyer, Agrawal, Klapoetke 2017, Boddu, Viswanath, Akhavan, Cooper) were made by regex over the dumped text layer and by reading named tables; those exploratory scripts are not committed, and `inventory.json` labels each such count `regex_text_layer` or `table_read_by_hand` with the hand-check result.

The scripts have paths of the scratch layout they were written in; read them as procedures. The counts are what `inventory.json` holds, and `inventory_report.py` refuses a count without a locator.
