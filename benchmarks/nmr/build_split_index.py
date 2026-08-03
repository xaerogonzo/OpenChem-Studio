"""Build the shift index from the training split only, with the real code.

The SHIPPING build_index, unmodified -- the baseline has to be what the
application actually does, not a re-implementation that resembles it.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from openchem.chem.nmr_database import build_index  # noqa: E402
from openchem.services.nmr_database_setup import INDEX_SPHERES  # noqa: E402

WORK = Path("D:/Random Programs/OpenChemStudio_Data/nmr_train_work")


def progress(spectra, measurements, environments):
    print(f"  {spectra:,} spectra  {measurements:,} shifts  {environments:,} env", flush=True)


start = time.time()
stats = build_index(
    WORK / "train.sd",
    WORK / "split_index.sqlite",
    max_spheres=INDEX_SPHERES,
    on_progress=progress,
)
print(stats)
print(f"{time.time() - start:.0f}s")
print("index bytes", f"{(WORK / 'split_index.sqlite').stat().st_size:,}")
