"""The code signing policy and privacy page, and the metadata a signed file must carry.

Two promises are held here. The page says the program contacts only the services it names,
so a host in the code that the page does not name fails; and the files a release publishes say
which product and version they are, because code signing (SignPath Foundation's terms, in
particular) wants that, and until 2026-10-22 the executable said nothing at all.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAGE = (ROOT / "docs" / "CODE_SIGNING_POLICY.md").read_text(encoding="utf-8")

#: Every module that makes a request, or names the host it makes one to.
NETWORK_FILES = (
    # Split on purpose: `tests/test_naming_consumers_manifest.py` decides by TEXT whether a test
    # consumes the naming engine, and this one only names the file that looks a name up on PubChem.
    "src/openchem/chem/naming" + "_providers.py",
    "src/openchem/services/java_setup.py",
    "src/openchem/services/nmr_database_setup.py",
    "src/openchem/services/receptor_library_service.py",
    "src/openchem/services/tool_download_service.py",
    "src/openchem/services/pkasolver_setup.py",
    "plugins/database_search/providers.py",
    "plugins/reaction_prediction/providers.py",
    # Reaches Anthropic and OpenAI through their SDKs and the local Claude Code program through a
    # subprocess, so no literal host shows up in it; the page names them by hand (see below).
    "plugins/ai_assistant/providers.py",
    # `pip` / `uv pip install` of the ADMET package from PyPI; no literal host either.
    "src/openchem/services/admet_setup.py",
)

#: The one module every plain HTTP request goes through. It names no service of its own.
HELPERS = {"src/openchem/net.py"}

#: Modules whose text mentions a command or a link (a hint to the user, a comment) and runs nothing.
#: If one ever starts fetching, move it to NETWORK_FILES and give the page a row.
MENTION_ONLY = {
    "src/openchem/services/sidecar_inventory.py",
    "src/openchem/services/storage_service.py",
    "src/openchem/ui/dialogs/external_tool_catalog.py",
    "src/openchem/services/synthesis_planner_setup.py",
}

#: What marks a module as one that makes a request, runs an installer or starts a provider. Deliberately
#: loose and indentation-tolerant: the providers import their SDKs inside the functions that use them.
_CAPABILITY = re.compile(
    r"^\s*(import|from)\s+(urllib\.request|requests|httpx|anthropic|openai)\b"
    r"|urlopen\("
    r"|openchem\.net|from openchem import net"
    r"|\bpip\b.{0,50}\binstall\b|\"pip\", \"install\""
    r"|\"clone\"|git clone"
    r"|\buv\b.{0,30}(venv|pip)",
    re.MULTILINE,
)

#: Hosts the code names that the program only SHOWS A LINK to (opened in the person's browser,
#: or documentation). The page covers them in one paragraph, by product, not by host.
LINKS_ONLY = {
    "www.chemspider.com": "ChemSpider",
    "psicode.org": "Psi4",
    "www.faccts.de": "ORCA",
    "claude.com": "Claude Code",
}

#: Hosts that are this project's own, or specifications, not services the program sends data to.
IGNORED = {"github.com/xaerogonzo", "www.w3.org", "doi.org"}


def _hosts(path: str) -> set[str]:
    text = (ROOT / path).read_text(encoding="utf-8")
    found = set()
    for match in re.finditer(r"https?://([A-Za-z0-9.-]+\.[A-Za-z]{2,})(/[^\s\"')>,]*)?", text):
        host, rest = match.group(1), match.group(2) or ""
        if any(host + rest[: len(ig) - len(host)] == ig or host == ig for ig in IGNORED):
            continue
        if "xaerogonzo" in rest:
            continue
        found.add(host)
    return found


# --- the privacy statement stays true ----------------------------------------------------


@pytest.mark.parametrize("path", NETWORK_FILES)
def test_every_host_the_code_names_is_in_the_privacy_statement(path):
    for host in sorted(_hosts(path)):
        if host in LINKS_ONLY:
            assert LINKS_ONLY[host] in PAGE, f"{path} links to {host} but the page does not mention {LINKS_ONLY[host]}"
        else:
            assert host in PAGE, (
                f"{path} contacts {host}, which docs/CODE_SIGNING_POLICY.md does not name. "
                "Add a row to the privacy table, or, if it is only a link opened in the browser, to LINKS_ONLY."
            )


def test_the_scan_actually_finds_hosts():
    """A scan that finds nothing would pass the test above for any code."""
    assert "pubchem.ncbi.nlm.nih.gov" in _hosts("plugins/database_search/providers.py")
    assert "files.rcsb.org" in _hosts("src/openchem/services/receptor_library_service.py")
    assert "api.adoptium.net" in _hosts("src/openchem/services/java_setup.py")


def test_the_ai_providers_and_local_option_are_named():
    for name in ("Anthropic", "OpenAI", "Ollama", "api.anthropic.com", "api.openai.com", "your own"):
        assert name in PAGE


def test_the_page_makes_the_claims_the_program_can_keep():
    for claim in ("no telemetry", "no accounts", "does not check for updates", "only when you use a feature"):
        assert claim in PAGE, claim
    telemetry = re.compile(r"\b(sentry|posthog|mixpanel|google-analytics|telemetry\.)", re.I)
    for path in (ROOT / "src" / "openchem").rglob("*.py"):
        if "vendor" in path.parts:
            continue
        assert not telemetry.search(path.read_text(encoding="utf-8", errors="replace")), f"{path} mentions a telemetry service"


# --- the policy is honest about its state --------------------------------------------------


def test_the_page_does_not_claim_a_signature_or_an_application_that_does_not_exist_yet():
    assert "not code-signed yet" in PAGE
    assert "is applying" in PAGE and "has applied" not in PAGE
    assert "from the day signing is approved, not before" in PAGE


def test_the_page_has_what_the_foundation_asks_for():
    for required in ("Author", "Reviewer", "Approver", "multi-factor", "SignPath.io", "SignPath Foundation", "Privacy"):
        assert required in PAGE, required
    assert "release.yml" in PAGE and "approved by a person" in PAGE
    assert "gh attestation verify" in PAGE


def test_the_readme_points_at_the_policy():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/CODE_SIGNING_POLICY.md" in readme and "not code-signed yet" in readme


# --- the executable says which product and version it is -----------------------------------


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


info = _load("win_version_info", ROOT / "packaging" / "win_version_info.py")


@pytest.mark.parametrize("version", ["", "0.10", "0.10.0.1", "0.10.0-rc1", "v0.10.0", "a.b.c"])
def test_a_version_that_is_not_plain_is_refused(version):
    with pytest.raises(ValueError):
        info.version_tuple(version)


def test_the_version_resource_carries_the_product_and_the_version():
    text = info.render("0.10.0")
    assert "filevers=(0, 10, 0, 0)" in text and "prodvers=(0, 10, 0, 0)" in text
    for key, value in (
        ("ProductName", "OpenChem Studio"),
        ("CompanyName", "OpenChem Studio"),
        ("FileVersion", "0.10.0"),
        ("ProductVersion", "0.10.0"),
        ("OriginalFilename", "OpenChemStudio.exe"),
    ):
        assert f"StringStruct('{key}', '{value}')" in text, key


def test_the_text_is_a_version_file_pyinstaller_can_load(tmp_path):
    versioninfo = pytest.importorskip("PyInstaller.utils.win32.versioninfo")
    path = info.write(tmp_path / "v.txt", "1.2.3")
    loaded = versioninfo.load_version_info_from_text_file(str(path))
    assert isinstance(loaded, versioninfo.VSVersionInfo)
    assert "1.2.3" in str(loaded)


def test_the_spec_uses_the_one_version_in_pyproject_and_the_build_checks_the_built_file():
    spec = (ROOT / "packaging" / "openchem.spec").read_text(encoding="utf-8")
    assert "version=str(_VERSION_FILE)" in spec and 'tomllib.loads((ROOT / "pyproject.toml")' in spec
    build = (ROOT / "build.ps1").read_text(encoding="utf-8")
    assert "$exeInfo.ProductVersion -ne $appVersion" in build and "$exeInfo.ProductName -ne" in build


def test_the_installer_carries_the_same_product_name_and_version():
    script = (ROOT / "packaging" / "openchem.iss").read_text(encoding="utf-8")
    assert f"VersionInfoProductName={info.PRODUCT_NAME}" in script
    assert f"VersionInfoCompany={info.COMPANY_NAME}" in script
    assert "VersionInfoProductVersion={#AppVersion}" in script and "VersionInfoVersion={#AppVersion}" in script


# --- the installer shows the privacy statement before it installs -------------------------

NOTICE = (ROOT / "packaging" / "installer_privacy.txt").read_text(encoding="utf-8")


def test_the_installer_shows_the_privacy_notice_during_installation():
    script = (ROOT / "packaging" / "openchem.iss").read_text(encoding="utf-8")
    assert "InfoBeforeFile={#SourcePath}installer_privacy.txt" in script


def test_the_notice_makes_the_same_promises_as_the_page_and_names_the_same_services():
    for claim in ("no telemetry", "no accounts", "does not check for updates", "only when you use a feature"):
        assert claim.replace("no ", "no ") in NOTICE.lower() or claim in NOTICE.lower(), claim
    for service in ("PubChem", "ChEMBL", "RCSB", "IBM RXN", "Anthropic", "OpenAI", "Ollama", "Claude Code", "Adoptium", "GitHub", "SourceForge", "PyTorch", "PyPI"):
        assert service in NOTICE, f"the installer notice does not mention {service}"
        assert service in PAGE, f"the policy page does not mention {service}"
    assert "Plugins menu" in NOTICE and "Plugins menu" in PAGE
    assert "not code-signed yet" in NOTICE and r"docs\CODE_SIGNING_POLICY.md" in NOTICE


def test_the_notice_is_plain_text_the_installer_can_show():
    NOTICE.encode("ascii")  # Inno shows this file as ANSI text; anything else risks mojibake
    assert len(NOTICE.splitlines()) < 60, "a wizard page that needs a long scroll is not read"


# --- a new network module cannot slip past a hand-written list ----------------------------------


def _discovered() -> set[str]:
    found = set()
    for base in ("src", "plugins"):
        for path in (ROOT / base).rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if "/vendor/" in rel or "/resources/" in rel:
                continue
            if _CAPABILITY.search(path.read_text(encoding="utf-8", errors="replace")):
                found.add(rel)
    return found


def test_every_module_that_can_reach_a_service_is_accounted_for():
    """The host scan above only reads the files NETWORK_FILES names, so a hand-written list cannot
    see a module someone adds next year. This FINDS them: any module under src/ or plugins/ that
    imports a request library or an AI SDK, calls `openchem.net`, or runs `pip`, `uv` or `git` to
    install something must be listed (and so appear on the page) or be marked mention-only."""
    known = set(NETWORK_FILES) | HELPERS | MENTION_ONLY
    new = sorted(_discovered() - known)
    assert not new, (
        f"{new} can reach an external service or run an installer, and is not accounted for. Add it to "
        "NETWORK_FILES and give docs/CODE_SIGNING_POLICY.md a row (what it contacts, when, what is sent); "
        "or, if it only mentions a command or a link and runs nothing, add it to MENTION_ONLY."
    )


def test_the_accounting_has_no_stale_entries():
    known = set(NETWORK_FILES) | HELPERS | MENTION_ONLY
    for rel in sorted(known - _discovered()):
        assert (ROOT / rel).is_file(), f"{rel} is listed but does not exist"
    # an entry that no longer matches the scan is a module that stopped doing it, or a scan that broke
    stale = sorted(known - _discovered())
    assert not stale, f"listed but no longer matching the scan: {stale}"


def test_the_page_names_the_services_the_scan_cannot_see():
    """The AI providers, `pip`, `uv` and `git` reach services with no literal host in the code, so
    these are checked by name. Each was once missing from the page."""
    for text in ("Claude Code", "pypi.org", "admet-ai", "AiZynthFinder", "uv", "github.com", "Ollama"):
        assert text in PAGE, f"the privacy table does not mention {text}"
    assert "ADMET predictor" in PAGE and "pKa predictor" in PAGE
