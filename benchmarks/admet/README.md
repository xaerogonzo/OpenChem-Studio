# ADMET endpoint benchmark

Which of the 104 columns ADMET-AI emits are good enough to show, and which
are not. `chem/admet_providers.py` reports 10 of them; this is the evidence
behind promoting seven more and refusing six.

Measured 2026-08-05 against the installed sidecar
(`admet-ai 2.0.1`, `chemprop 2.3.0`, `torch 2.13.0+cpu`) and TDC's ADMET
Benchmark Group v0.4.1. Three steps:

```bash
# 1. TDC splits, in a throwaway env (see fetch_tdc.py for why)
uv venv tdcenv --python 3.11
uv pip install --python tdcenv/Scripts/python.exe "PyTDC==0.4.1" "setuptools<81"
tdcenv/Scripts/python.exe fetch_tdc.py

# 2. predictions, from the sidecar's own interpreter (~2 min per split)
"<admet interpreter>" predict.py test
"<admet interpreter>" predict.py train

# 3. scores, from this project's environment
uv run --no-sync python score.py
```

## Read this before quoting any accuracy number

**The TDC test split is not held out from the weights this app runs.**
ADMET-AI's reproduction docs describe two training scripts:
`train_tdc_admet_group.py` builds scaffold-split models for leaderboard
comparison, and `train_tdc_admet_all.py` trains on all the data and
produces the models that ship inside the wheel. The app runs the shipped
ones, so **every TDC molecule is a training molecule**.

Two independent measurements agree with that reading.

Measured AUROC against the vendor's own published scaffold-split AUROC, on
the same test molecules:

    higher on 13 of 13 endpoints        mean delta  +0.059
    largest   cyp2c9_substrate  +0.152      bioavailability_ma  +0.124
    smallest  hia_hou           +0.005      pgp_broccatelli     +0.018

Train-split skill against test-split skill, which under real held-out
evaluation would favour train:

    mean gap  +0.003        max  +0.051        22 endpoints

Near zero because both splits trained these weights. Note that this second
check ALONE would have been misread as healthy generalisation — it is only
decisive next to the first.

**So no accuracy figure below is a held-out measurement, and no amount of
compute here can make one**: there is no TDC molecule the shipped model has
not seen. Held-out accuracy is quoted from the vendor's published
scaffold-split figures (`admet_ai/resources/data/admet.csv`), which are a
third party's measurement of equivalently-trained models, not of these
weights.

## What survives the leakage, and does the real work

The confound comparison. Leakage inflates the model's column but leaves the
molecular-weight and logP baselines untouched, so the measured gain is an
**upper bound** on the model's real advantage over a ruler. That supports
one sound inference:

> An endpoint that cannot beat a ruler even with the answers memorised is a
> ruler.

This is the hERG check generalised. hERG looked excellent on a ten-compound
panel while correlating with heavy-atom count at r = +0.98; the model had
learnt "big lipophilic molecules block hERG". `skill` below is AUROC for
classification and |Spearman| for regression, so the model, a molecular
weight and a logP are scored on one scale, and each baseline is given its
best orientation.

The second sound inference needs no baseline at all: **a model that cannot
beat the mean on data it trained on has learnt nothing usable.** Two
endpoints fail exactly that.

## Results

| endpoint | n | model | size | logP | gain | published | verdict |
|---|---|---|---|---|---|---|---|
| caco2_wang | 182 | 0.901 | 0.294 | 0.474 | +0.427 | R² 0.707 | **Advanced** |
| solubility_aqsoldb | 1995 | 0.939 | 0.427 | 0.765 | +0.175 | R² 0.817 | **Advanced** |
| bbb_martins | 406 | 0.950 | 0.780 | 0.569 | +0.171 | AUROC 0.900 | **Advanced** |
| ppbr_az | 559 | 0.764 | 0.021 | 0.353 | +0.411 | R² 0.589 | **Advanced** |
| hia_hou | 117 | 0.999 | 0.612 | 0.843 | +0.156 | AUROC 0.994 | **Advanced** |
| dili | 96 | 0.956 | 0.507 | 0.511 | +0.444 | AUROC 0.881 | **Advanced** |
| ld50_zhu | 1478 | 0.877 | 0.332 | 0.213 | +0.545 | R² 0.596 | **Advanced** |
| pgp_broccatelli | 245 | 0.965 | 0.782 | 0.888 | +0.077 | AUROC 0.948 | Research |
| bioavailability_ma | 128 | 0.841 | 0.695 | 0.515 | +0.145 | AUROC 0.716 | Research |
| vdss_lombardo | 226 | 0.478 | 0.079 | 0.358 | +0.119 | R² −1.211 | Research |
| half_life_obach | 135 | 0.449 | 0.006 | 0.275 | +0.174 | R² −2.386 | Research |
| clearance_hepatocyte_az | 243 | 0.673 | 0.047 | 0.032 | +0.626 | R² 0.264 | Research |
| clearance_microsome_az | 221 | 0.758 | 0.005 | 0.008 | +0.750 | R² 0.277 | Research |
| lipophilicity_astrazeneca | 840 | 0.940 | 0.147 | 0.325 | +0.615 | R² 0.771 | excluded |

The ten already-shipped endpoints re-scored consistently with the panels
that justified them (`herg` AUROC 0.911, `ames` 0.930, CYP inhibition
0.935–0.945, CYP substrate 0.751–0.881) — leaky, but no surprises.

## The six that did not ship, and why

**Pgp_Broccatelli — the hERG confound, repeating.** AUROC 0.965 looks like
the best classifier in the table. But logP alone scores **0.888** on the
same molecules, so the entire measured advantage is +0.077 *with the test
set memorised*. This is precisely what `herg_sizematched.py` was written to
catch, and the plan predicted it would recur. It did.

**Bioavailability_Ma.** Published held-out AUROC **0.716**, against a
size-only baseline of **0.695** on the same molecules. Whatever it knows
beyond molecular weight is within noise of nothing.

**VDss_Lombardo — R² −0.302 on its own training data.** Published R²
**−1.211**. Negative means worse than answering with the mean every time.
Volume of distribution spans four orders of magnitude and depends on tissue
binding that a 2D structure does not carry.

**Half_Life_Obach — R² −0.091 on its own training data.** Published
**−2.386**, the worst figure in the whole ADMET-AI table. Half-life is a
composite of clearance and volume of distribution, so it inherits the
failure above and adds to it.

**Clearance_Hepatocyte_AZ and Clearance_Microsome_AZ.** Published R²
**0.264** and **0.277**. Both beat a ruler comfortably — the ruler is
useless here (size skill 0.047 and 0.005) — but beating a useless baseline
is not the same as being useful. A quarter of the variance, on an endpoint
whose measured values span two orders of magnitude, is not a number to put
next to a molecule without a caveat larger than the number.

**So the entire Excretion block fails.** All three of its endpoints —
half-life, hepatocyte clearance, microsome clearance — are refused. That is
worth stating plainly rather than leaving as an absence: this app cannot
tell you how fast a compound is cleared, and the sidecar's willingness to
print a number for it does not change that.

**Lipophilicity_AstraZeneca** is excluded by an older curation decision
rather than by this benchmark: it is experimental logD7.4, and the app
computes logP and pH-dependent logD itself (`chem/logd.py`). It scores well
(R² 0.771 published) and could be revisited; it is listed here so that its
absence reads as a decision rather than an oversight.

## Where the tiers live

`REPORTED_ENDPOINTS` in `chem/admet_providers.py`, as three tiers with the
numbers above attached to each entry. `EndpointTier.RESEARCH` carries the
unbenchmarked remainder and says so in the UI.
