from pathlib import Path

p = Path("docs/ARCHITECTURE.md")
t = p.read_text(encoding="utf-8")
t = t.replace("**167 modules, counted 2026-11-11**", "**168 modules, counted 2026-11-11**")
old = "`salt_mode_a.py`"
# Insert salt_mode_c immediately after the Mode A parenthetical.
marker = "; no UI), `salt_ionization.py`"
# That marker may appear only after salt_mode_a. Find salt_mode_a then first marker after it.
i = t.find("`salt_mode_a.py`")
if i < 0:
    raise SystemExit("no salt_mode_a")
j = t.find(marker, i)
if j < 0:
    raise SystemExit("no marker after salt_mode_a")
insert = "; no UI), `salt_mode_c.py` (Mode C: cartesian product of candidate states of one two-component pair, cap 50, pKa not used to rank; no UI), `salt_ionization.py`"
t = t[:j] + insert + t[j + len(marker) :]
p.write_text(t, encoding="utf-8")
print("patched", t[i : i + 220])
