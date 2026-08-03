"""Split nmrshiftdb2 into train / held-out by record position.

Every twentieth RECORD (not every twentieth parseable molecule) is held
out, matching the protocol recorded in nmr_database.py: iter_assigned_spectra
numbers records with enumerate() over the raw supplier, so records RDKit
cannot sanitize still consume an index. Splitting the file positionally
therefore reproduces the same partition.
"""
from pathlib import Path

WORK = Path("D:/Random Programs/OpenChemStudio_Data/nmr_train_work")
src = WORK / "nmrshiftdb2withsignals.sd"

train = (WORK / "train.sd").open("w", encoding="utf-8", newline="")
held = (WORK / "heldout.sd").open("w", encoding="utf-8", newline="")

buf: list[str] = []
n = 0
with src.open("r", encoding="utf-8", errors="replace", newline="") as fh:
    for line in fh:
        buf.append(line)
        if line.rstrip("\r\n") == "$$$$":
            (held if n % 20 == 0 else train).write("".join(buf))
            buf = []
            n += 1

if buf and any(s.strip() for s in buf):
    print("WARNING: trailing partial record,", len(buf), "lines")

train.close()
held.close()
print("records", n, "-> heldout", (n + 19) // 20, "train", n - (n + 19) // 20)
for name in ("train.sd", "heldout.sd"):
    print(name, f"{(WORK / name).stat().st_size:,}")
