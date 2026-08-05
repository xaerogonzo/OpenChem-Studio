"""Step 1 of 3: download the TDC ADMET Benchmark Group splits.

Needs PyTDC, which does NOT belong in either this project or the ADMET
sidecar environment -- it pins `rdkit-pypi` and would drag the sidecar's
working torch/rdkit stack around with it. Build a throwaway environment
instead (PyTDC 0.4.1 is the last release without the `tiledbsoma`
dependency, which has no Windows wheel and fails to build from source):

    uv venv tdcenv --python 3.11
    uv pip install --python tdcenv/Scripts/python.exe "PyTDC==0.4.1" "setuptools<81"
    tdcenv/Scripts/python.exe fetch_tdc.py

`setuptools` is explicit because PyTDC 0.4.1 imports `pkg_resources`,
which Python 3.12+ environments no longer provide by default.

Writes tdc_data/, which is NOT committed: it is TDC's data, ~10 MB, and
regenerating it is one command.
"""

from __future__ import annotations

import json
from pathlib import Path

from tdc.benchmark_group import admet_group

OUT = Path("tdc_data")


def main() -> int:
    OUT.mkdir(exist_ok=True)
    group = admet_group(path=str(OUT / "raw"))
    print(f"{len(group.dataset_names)} benchmark datasets")

    manifest = {}
    for name in group.dataset_names:
        benchmark = group.get(name)
        # The `test` split is FIXED across seeds -- the seed only re-splits
        # train_val into train/valid -- which is what makes it usable as a
        # reference set at all. Both halves are written because score.py
        # compares performance on them (see its `_leakage`).
        benchmark["test"].to_csv(OUT / f"{name}__test.csv", index=False)
        benchmark["train_val"].to_csv(OUT / f"{name}__trainval.csv", index=False)
        manifest[name] = {
            "test": int(len(benchmark["test"])),
            "train_val": int(len(benchmark["train_val"])),
        }
        print(f"  {name:36} test {len(benchmark['test']):>5}"
              f"   train_val {len(benchmark['train_val']):>6}")

    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
