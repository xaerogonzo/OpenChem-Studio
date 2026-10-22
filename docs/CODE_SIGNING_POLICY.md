# Code signing policy and privacy

## Status

**OpenChem Studio's releases are not code-signed yet.** The project is applying to
[SignPath Foundation](https://signpath.org/) for free code signing for open-source
projects. Until that is approved and in use, Windows SmartScreen may show "unknown
publisher" the first time you run the installer or the program: choose **More info**, then
**Run anyway**. When signing starts, this page will say so and the credit below will apply.

This page is the project's code signing policy and its privacy statement. Both are written
for the SignPath Foundation's terms, and both are true of the program today.

## Code signing policy

*In force once signing is approved. Until then no release is signed, and nothing below
means a file is.*

- **What is signed:** the files a release publishes, built from this repository's source:
  `OpenChemStudio.exe` and the installer `OpenChemStudio-v<version>-windows-x64-setup.exe`.
  Nothing built anywhere else, and no third-party binary, is signed under this project's name.
- **How they are built:** by the public GitHub Actions workflow
  [`release.yml`](../.github/workflows/release.yml), on a clean GitHub-hosted Windows
  machine, from a version tag. The workflow is part of the source and is reviewed like any
  other change. How a release is cut is in [RELEASING.md](RELEASING.md).
- **Metadata:** the product name is `OpenChem Studio` and the product and file version
  are the version in `pyproject.toml`, in the program and in the installer. The build
  fails if the built program says otherwise.
- **Every release is approved by a person** before it is signed or published. The build
  creates a draft; nothing is published, and nothing would be signed, without that step.
- **Roles:**

  | Role | What it means | Who |
  |---|---|---|
  | Author | commits code to the repository | Alexander L Corthell ([@xaerogonzo](https://github.com/xaerogonzo)) |
  | Reviewer | reviews changes from people who are not authors | Alexander L Corthell ([@xaerogonzo](https://github.com/xaerogonzo)) |
  | Approver | approves each release before it is signed and published | Alexander L Corthell ([@xaerogonzo](https://github.com/xaerogonzo)) |

  The project currently has one maintainer, who holds all three roles. Anyone else's
  change reaches a release only through a pull request the maintainer reviews.
- **Account security:** the maintainer uses multi-factor authentication on GitHub and,
  once approved, on SignPath.
- **What signing does and does not mean:** a signature says the file came from this
  project's build and has not been changed since. It does not say the program is free of
  mistakes, and it does not vouch for the data the program is given.
- **Reporting a problem** with a release, including a suspected false positive from an
  antivirus program or a file you believe was not built by this project:
  [open an issue](https://github.com/xaerogonzo/OpenChem-Studio/issues).

Code signing is provided free of charge by [SignPath.io](https://signpath.io/), with the
certificate from the [SignPath Foundation](https://signpath.org/). *(This credit applies
from the day signing is approved, not before.)*

## Checking a download today

Each release lists a `SHA256SUMS.txt`. Checking a file against it
(`certutil -hashfile <file> SHA256`) detects a damaged download. Releases built by the
workflow also carry a build provenance attestation:

```bash
gh attestation verify <file> --repo xaerogonzo/OpenChem-Studio
```

proves the file was produced by that workflow from this repository. Neither is a code
signature.

## Privacy

**OpenChem Studio collects nothing about you.** It has no accounts, no telemetry, no
usage statistics, no crash reporting, and it does not check for updates to itself. Your
structures, projects and settings stay on your computer, in your own files and in the
program's data folder.

The program contacts other services **only when you use a feature that needs one**, and
only the service that feature names. Nothing is sent in the background.

| When you | It contacts | What is sent |
|---|---|---|
| Look a structure up by name, or search compounds (naming, Database Search) | PubChem (`pubchem.ncbi.nlm.nih.gov`) | the name, formula or structure you searched for |
| Search ChEMBL (Database Search) | ChEMBL at EMBL-EBI (`www.ebi.ac.uk`) | what you searched for |
| Fetch a protein structure by its PDB id (Receptor Library) | RCSB (`files.rcsb.org`, `www.rcsb.org`) | the PDB id |
| Predict a reaction (Reaction Prediction plugin) | IBM RXN (`rxn.res.ibm.com`) | the reaction SMILES you entered, with **your own** API key |
| Ask the AI assistant (AI Assistant plugin) | the provider you choose and configure: Anthropic (`api.anthropic.com`), OpenAI (`api.openai.com`), a local Ollama on your own machine (`localhost`), or the **Claude Code** command-line program if it is installed on your computer, which the assistant runs and which sends the conversation to Anthropic under your own login | your messages and any calculation results you ask it to read, with **your own** API key (or your own Claude Code login); a key is stored only on your computer |
| Set up Java for name-to-structure conversion | Adoptium (`api.adoptium.net`) | a download request for the Temurin runtime |
| Set up AutoDock Vina | GitHub (`api.github.com`, `github.com`) | a download request for the release |
| Build the NMR database | SourceForge (`sourceforge.net`) | a download request for nmrshiftdb2 |
| Set up the pKa predictor | PyTorch (`download.pytorch.org`) and PyG (`data.pyg.org`) wheel indexes, the Python Package Index (PyPI, `pypi.org`) for the other packages, GitHub (`github.com`) for the predictor's source and trained models, and, if no suitable Python is installed, a standalone Python build that `uv` downloads from GitHub | download requests for the packages, the source and the models |
| Set up the ADMET predictor | the Python Package Index (PyPI, `pypi.org`) and, if no suitable Python is installed, a standalone Python from GitHub through `uv` | a download request for the `admet-ai` package, whose trained weights are inside it |
| Use synthesis route planning (Synthesis Planner plugin) | nothing, from OpenChem | it runs the AiZynthFinder program you installed yourself, on your computer. That program's own downloads (its models and stock) are made by that program when you set it up, not by OpenChem |

Some buttons only open a web page in **your browser** (the ChemSpider search, the
vendor pages for ORCA and Psi4, which you install yourself). The program sends nothing
to those sites; your browser does, as you choose.

Each service has its own privacy policy, which applies to what it receives. If you do not
want a service to see a query, do not use the feature that sends it. The AI assistant and
reaction prediction are plugins that stay idle until you configure a key, and **you can
turn any plugin off from the Plugins menu**. The installer shows a short version of this
statement before it installs anything.

## Changing this page

`tests/test_code_signing_policy.py` fails if a module that makes network requests or runs an
installer is not accounted for here, or names a host this page does not, so the privacy
statement cannot quietly fall behind the code. It cannot see a service reached through a
library or a program the code starts (the AI providers, `pip`, `uv`, `git`): those rows are
kept by hand and the test only checks that the page still names them.
