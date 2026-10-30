# How Model N types a nitro group or a carboxylate — design (PROPOSED, 2026-10-30)

**Status: a proposal. Nothing here is built and no check below has run.** It continues
`eem_second_models_preregistration.md` (section 5-R found the problem, 5-L.3 collected the literature, section 9 item 4 left
the direction open). Model J is paused and is not touched here.

## 1. The problem, in one paragraph

The EEM atom type is an element plus the highest bond order of any bond to the atom. In `[N+](=O)[O-]` and `C(=O)[O-]`
the two oxygens are the same atom chemically, but the drawing makes one of them double-bonded: that one is typed O2 and the
other O1, and O1 and O2 have different parameters (Model N: O1 A 3.1503, B 1.0577; O2 A 3.0486, B 0.8410). Which oxygen is
double-bonded follows **the order the atoms were written** (measured with RDKit: `CN(=O)=O` and `C[N+](=O)[O-]` give the
double bond to different oxygens of one molecule). So one structure written two ways gets two answers, and the two oxygens
of one group get different charges for no chemical reason.

## 2. What was measured before designing (exploratory, disclosed as such)

`eem_resonance_exploration.py`, Model N, the 77-molecule panel. Twelve molecules have such a pair (nitro groups, nitrate
esters, a nitramine, nitroguanidine, acetate, glycine zwitterion).

- **As drawn**, the difference in charge between the two oxygens of one group is **0.015 to 0.120 e (median 0.069 e)**, taking
  the worst of the ways the group can be drawn.
- **With each atom's A and B averaged over the resonance forms**, the same difference is **0.000 to 0.079 e (median 0.031 e)**
  and is never larger than as drawn. What is left is the geometry: the conformers are not symmetric, so two oxygens with
  identical parameters still sit in different surroundings. Acetate and nitrobenzene, whose groups are nearly symmetric, drop to
  0.0007 e and 0.0000 e.
- Averaging moves the atoms that are **not** in a group by at most **0.013 e**.
- RDKit's default enumeration gives up to **81 forms** for a molecule with four nitro groups, and in 6 of the 77 molecules the
  forms do not all have the same number of formal charges.

## 3. The options (from section 5-R and the literature)

| | What it does | For | Against |
|---|---|---|---|
| **as_drawn** | the published model on whatever bond list the drawing gives | exactly what the NEEMP solver does; no extension | the answer depends on atom order; the two oxygens differ by up to 0.12 e |
| **averaged** | each atom's A and B are the mean over the low-charge resonance forms | published precedent: Gilson, Gilson and Potter 2003 average the electronegativities and hardnesses over the lowest-energy forms; the answer is a function of the structure | an extension of Model N, not what its authors computed |
| **refuse** | decline any molecule whose types vary | no claim beyond the published model | loses every nitro group and carboxylate |

(MMFF94's single symmetric type for each, and averaging the charges instead of the parameters, are the same idea as `averaged`
for this purpose; Gilson et al. mention the second as an alternative.)

## 4. Proposed design — each item is a decision for Alex

**D1. The default is `averaged`; `as_drawn` and `refuse` are the other two values of one option.** Reason: it is the only
choice that makes the result depend on the structure alone, which is what every other result here is held to, and it has a
published precedent. The option is stored as a code (`averaged`, `as_drawn`, `refuse`), never as the words on the screen.

**D2. Where it lives.** A declared option of the Model N calculator (so it is part of the result's identity and its cache
fingerprint, and a change recomputes), with its default taken from one setting on the Settings page. A drive script and the
assistant read and set it the same way as any other option. A result always says which value it was computed with.

**D3. What a person is told.**
- `averaged`: the result's evidence names the atoms whose types were averaged and over how many forms, and the claim line reads
  "the charges NEEMP's model gives, with atom types averaged over resonance forms (after Gilson et al. 2003), which is an
  extension of the published model".
- `as_drawn`: a caveat on the result and on each affected atom: "the charges on these atoms depend on how the structure was
  drawn; the same structure drawn another way gives different charges", with the size measured here (up to about 0.1 e).
- `refuse`: the refusal names the group and says the other two values exist.

**D4. Which forms.** RDKit's default resonance enumeration (it creates no charge separation and allows no incomplete octet),
keeping only the forms with the **smallest sum of absolute formal charges**, all weighted equally. That approximates Gilson's
"lowest-energy forms" rule (both forms of a carboxylate, only the neutral form of an amide) without his donor-acceptor energy
table, which is a choice to report, not a measurement.

**D5. What counts as variable.** Any atom whose type differs between the kept forms, found by the enumeration and not by a
list of groups, so phosphate, sulfonate, nitrate and guanidinium are included without being named. Only nitro and carboxylate
are checked here; the others are reported, not claimed.

**D6. A cap.** If the enumeration reaches 1000 forms (RDKit's own default limit, which it applies silently) it is treated as
incomplete: `averaged` refuses with that reason and does not guess; `as_drawn` is unaffected.

**D7. Atoms that do not vary keep their own type's parameters,** so a molecule with no variable atom gives bit-identical
charges under all three values.

## 5. Checks, registered before anything is built

- **R1 invariance.** Under `averaged`, the charges of every panel molecule are the same (max difference 1e-8 e) for 20 random
  atom orders and 20 random SMILES spellings of it. Under `as_drawn` the same test is run and is EXPECTED to fail on the twelve
  molecules; that failure is recorded as the demonstration, not as a defect.
- **R2 equal parameters.** Under `averaged`, the two atoms of one group get the same A and the same B exactly.
- **R3 never worse.** For every group on the panel the averaged charge difference is not larger than the drawn one (true of all
  twelve in the exploration; held as a test so a change cannot break it quietly).
- **R4 nothing else moves.** A molecule with no variable atom has bit-identical charges under all three values; for the others
  the largest change on an atom outside a group is reported (0.013 e in the exploration) with no threshold.
- **R5 geometry residual.** The averaged difference that remains is reported per molecule with no threshold; it is geometry, not
  typing, and a symmetric geometry of acetate and nitrobenzene should show it near zero.
- **R6 cap.** A constructed molecule whose enumeration reaches the cap is refused by `averaged` with the reason and solved by
  `as_drawn`.
- **R7 independent solve.** The oracle of check C2 is extended with its own averaging (types from RDKit's forms directly,
  its own algebra) and agrees with the shipped code to 1e-6 e on the panel.

Stop rule: any R1 failure under `averaged`, or R3 failing for any group, stops the work and comes back for a decision.

## 6. What is NOT being claimed

That averaged charges are closer to a quantum-chemical reference (NPA cannot be computed here, and the reference's own two
oxygens are equal only by symmetry); that the averaging is what NEEMP's authors did (it is not); that the method is validated for
groups other than nitro and carboxylate; or that 0.1 e is large for the application's use.

## 7. How it would be built (no code yet)

`chem/typed_eem.py` gains an argument `bond_forms` (a sequence of bond lists, the first being the drawing's own) and a
`resonance` code; the solver stays pure and averages parameters over the forms it is given. The RDKit part (enumerate, select by
formal-charge sum, apply the cap) is one new function in `chem/` that returns the forms or a refusal. Neither is reachable
from a calculator until the option, its setting and its evidence lines exist, which is the later wiring step for Model N.
