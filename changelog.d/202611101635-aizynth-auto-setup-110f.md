### AiZynthFinder can be set up from Settings
- **Set Up Automatically** on the AiZynthFinder External tools tab builds a separate Python 3.12 environment, installs `aizynthfinder==4.4.1` with `pyarrow<21`, and runs `download_public_data`, after showing the size (~1.7 GB) and sources (PyPI, Zenodo, Figshare) and asking first. Browse still accepts an environment you already have; do not point it at the GitHub source zip.
- Remove from Disk only deletes the copy this app built, not an environment you pointed it at yourself.
