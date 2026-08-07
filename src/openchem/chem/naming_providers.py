"""IUPAC naming, in both directions, from several sources.

Provider-shaped rather than a single answer, because the sources differ in
kind and that difference matters more than the string they return:

    PubChem   exact      a database record for a compound someone curated
    engine    derived     the vendored Blue Book namer, from the structure
    OPSIN     parsed      a deterministic grammar, name -> structure only

Every result carries `source` and `kind` so a UI can show which is which.
There is deliberately NO numeric confidence field: no engine here emits a
calibrated confidence, and manufacturing one would be the same fabricated
precision this project refused for NMR RMSE and hERG probabilities. The
field can be added the day one actually does.

STOUT WAS REMOVED, not merely disabled. It was a sequence-to-sequence
neural namer run as a sidecar; its published weights were withdrawn (the
download 404s, checked repeatedly) and the vendored nomenclature engine
supersedes it anyway -- 181/181 on `benchmarks/naming`, deterministic,
offline, and unable to invent a fluent wrong name the way STOUT could.
A leftover-cleanup entry survives in `services/sidecar_inventory.py` so
anyone who installed the old environment can reclaim the disk.

NETWORK AND PRIVACY: the PubChem providers send the structure or name to
NCBI's public servers. That is a third party receiving whatever molecule
is being looked up, which matters for unpublished work -- so lookups are
only ever performed on an explicit user action, never automatically when a
molecule is opened or edited, and `PUBCHEM_PRIVACY_NOTE` is shown wherever
they are offered.

TWO FAILURE MODES CONFIRMED LIVE, both of which look like success:
  * A structure PubChem does not know returns HTTP 200 with
    `{"PropertyTable": {"Properties": [{"CID": 0}]}}` -- no error, no name.
    CID 0 is the sentinel and is checked for explicitly.
  * `CanonicalSMILES` and `IsomericSMILES` still resolve but now return
    `null`; the live property name is `SMILES`.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import urllib.error
import urllib.parse
from contextlib import contextmanager
from dataclasses import dataclass

from rdkit import Chem

from openchem.net import open_url
from openchem.chem.report_adapter import report_fields
from openchem.domain.report import ReportResult

logger = logging.getLogger("openchem.chemistry")

_PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
_TIMEOUT_SECONDS = 25

PUBCHEM_PRIVACY_NOTE = (
    "Looks the structure up on PubChem, which means sending it to NCBI's public "
    "servers. Avoid for unpublished or confidential structures."
)

# Result kinds. Not an enum for the same reason CalculatorDefinition.category
# isn't: a new source needs no code change here.
EXACT = "exact"
PREDICTED = "predicted"
PARSED = "parsed"


@dataclass(frozen=True)
class NameResult:
    """One name from one source."""

    name: str
    source: str
    kind: str
    note: str = ""


@dataclass(frozen=True)
class StructureResult:
    """One structure parsed or looked up from a name."""

    smiles: str
    source: str
    kind: str
    note: str = ""


class NamingError(RuntimeError):
    """A lookup failed for a reason the user should see verbatim."""


def _pubchem(path: str) -> dict:
    url = f"{_PUBCHEM_BASE}/{path}"
    try:
        # NCBI's usage policy asks callers to identify themselves so they
        # can reach whoever is generating load -- open_url does that.
        with open_url(url, timeout=_TIMEOUT_SECONDS) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise NamingError("PubChem has no record matching this input.") from exc
        raise NamingError(f"PubChem returned HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise NamingError(f"Could not reach PubChem: {exc.reason}") from exc
    except (TimeoutError, OSError) as exc:
        raise NamingError(f"Could not reach PubChem: {exc}") from exc


def _first_property_record(payload: dict) -> dict:
    records = payload.get("PropertyTable", {}).get("Properties", [])
    if not records:
        raise NamingError("PubChem returned no records.")
    record = records[0]
    # CID 0 is PubChem's "I have nothing for this" answer, returned with a
    # perfectly normal HTTP 200. Without this check an unknown structure
    # reads as a successful lookup that happened to return no name.
    if record.get("CID") == 0:
        raise NamingError("PubChem has no record for this structure.")
    return record


def pubchem_name_for_structure(mol: Chem.Mol) -> NameResult:
    """The curated IUPAC name PubChem holds for this exact structure."""
    smiles = Chem.MolToSmiles(mol)
    quoted = urllib.parse.quote(smiles, safe="")
    record = _first_property_record(_pubchem(f"compound/smiles/{quoted}/property/IUPACName/JSON"))
    name = record.get("IUPACName")
    if not name:
        raise NamingError("PubChem has a record for this structure but no IUPAC name for it.")
    return NameResult(name=name, source="PubChem", kind=EXACT, note=PUBCHEM_PRIVACY_NOTE)


def pubchem_structure_for_name(name: str) -> StructureResult:
    """Look a name up as a structure.

    `SMILES` is the live property; `CanonicalSMILES` and `IsomericSMILES`
    still resolve but return null, which would otherwise surface as a
    successful lookup with an empty structure.
    """
    quoted = urllib.parse.quote(name.strip(), safe="")
    if not quoted:
        raise NamingError("Enter a name to look up.")
    record = _first_property_record(_pubchem(f"compound/name/{quoted}/property/SMILES/JSON"))
    smiles = record.get("SMILES")
    if not smiles:
        raise NamingError("PubChem matched a record but returned no structure for it.")
    return StructureResult(smiles=smiles, source="PubChem", kind=EXACT, note=PUBCHEM_PRIVACY_NOTE)


@dataclass(frozen=True)
class StructureIdentification:
    """What PubChem holds for a structure, or the fact that it holds nothing."""

    cid: int
    iupac_name: str
    molecular_formula: str
    molecular_weight: float | None
    synonyms: tuple[str, ...]

    @property
    def url(self) -> str:
        return f"https://pubchem.ncbi.nlm.nih.gov/compound/{self.cid}"


def chemspider_search_url(inchikey: str) -> str:
    """A ChemSpider search page for this structure.

    A LINK RATHER THAN AN API CALL, deliberately. ChemSpider's web service
    requires a per-user registered API key, so there is nothing this
    application can ship that queries it on the user's behalf. Handing
    them a working search URL costs nothing, needs no key, and is honest
    about being a browser hand-off rather than an integration.
    """
    return f"https://www.chemspider.com/Search.aspx?q={urllib.parse.quote(inchikey, safe='')}"


def pubchem_identify_smiles(smiles: str) -> StructureIdentification:
    """`pubchem_identify` for callers that hold a SMILES rather than a Mol.

    Exists so the UI never has to touch RDKit: `ui/` and `app/` must not
    import a chemistry engine directly (enforced by
    tests/test_layering.py), and the lookup dialog carries a SMILES string
    across to a worker thread precisely because handing an RDKit Mol
    between threads is not something to do casually.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise NamingError("This structure could not be prepared for lookup.")
    return pubchem_identify(mol)


def pubchem_identify(mol: Chem.Mol) -> StructureIdentification:
    """Find this exact structure on PubChem and report what is known about it.

    EXACT STRUCTURE MATCH, not a similarity search. PubChem's `smiles`
    namespace resolves the structure as given, so a different tautomer or
    a missing stereocentre is a different query and can legitimately come
    back "not found". That is the right behaviour for "is this the
    compound I think it is" and worth stating in the UI, because a
    no-match is easily misread as "this molecule is unknown to science"
    when it means "not this exact connectivity and stereochemistry".

    Two requests: the property table, then synonyms for the CID it
    returns. Synonyms are the part users actually want -- a CID is not an
    answer to "what is this called" -- and PubChem does not return them
    from the property endpoint.
    """
    smiles = Chem.MolToSmiles(mol)
    quoted = urllib.parse.quote(smiles, safe="")
    record = _first_property_record(
        _pubchem(f"compound/smiles/{quoted}/property/IUPACName,MolecularFormula,MolecularWeight/JSON")
    )
    cid = int(record.get("CID") or 0)
    weight = record.get("MolecularWeight")
    return StructureIdentification(
        cid=cid,
        iupac_name=str(record.get("IUPACName") or ""),
        molecular_formula=str(record.get("MolecularFormula") or ""),
        # Confirmed live: MolecularWeight comes back as a STRING ("180.16"),
        # not a JSON number, so it needs converting rather than using.
        molecular_weight=float(weight) if weight not in (None, "") else None,
        synonyms=_pubchem_synonyms(cid),
    )


def _pubchem_synonyms(cid: int, limit: int = 8) -> tuple[str, ...]:
    """Common names for a CID. Never raises -- this is the optional half.

    A failed synonym lookup must not turn a successful identification into
    an error: the CID, formula and IUPAC name are already in hand, and
    they are the part that matters.
    """
    if cid <= 0:
        return ()
    try:
        payload = _pubchem(f"compound/cid/{cid}/synonyms/JSON")
    except NamingError:
        logger.debug("PubChem returned no synonyms for CID %d", cid)
        return ()
    entries = payload.get("InformationList", {}).get("Information", [])
    if not entries:
        return ()
    return tuple(str(s) for s in entries[0].get("Synonym", [])[:limit])


@contextmanager
def _java_on_path():
    """Puts a managed Java runtime on PATH for the duration of the block.

    py2opsin shells out to a bare `java` and finds it on PATH, so a
    runtime this app installed into its own data directory -- on neither
    PATH nor JAVA_HOME -- is invisible to it. Scoped to the block rather
    than exported, and restored afterwards, so nothing else in the
    process sees a mutated PATH.

    This has to wrap the IMPORT as well as the call: py2opsin runs
    `java -version` at module scope and warns "Java may not be
    installed/accessible" when it fails. That warning is wrong here (the
    calls work, because they were already wrapped) but it reaches the
    console, and a scary-but-false warning is worth the two lines it
    costs to not emit.
    """
    from openchem.services.java_setup import java_home

    home = java_home()
    original = os.environ.get("PATH", "")
    if home is not None:
        os.environ["PATH"] = str(home / "bin") + os.pathsep + original
    try:
        yield home
    finally:
        os.environ["PATH"] = original


def opsin_available() -> bool:
    """OPSIN is a Java library. `py2opsin` bundles its jar but still shells
    out to a JRE, so the package being importable is NOT enough -- a
    machine without Java gets an import that works and a call that fails.
    Both conditions are checked.
    """
    from openchem.services.java_setup import java_home

    if java_home() is None:
        return False
    with _java_on_path():
        try:
            import py2opsin  # noqa: F401
        except ImportError:
            return False
    return True


def describe_opsin_status() -> str:
    if opsin_available():
        return "Ready: OPSIN can parse IUPAC names into structures offline."
    from openchem.services.java_setup import java_home

    if java_home() is None:
        return (
            "OPSIN needs Java, which was not found. Tools > External Tools > Java can install "
            "a portable Temurin runtime for you; PubChem name lookup works without it (but "
            "only covers known compounds and sends the name over the network)."
        )
    return "OPSIN needs the py2opsin package, which is not installed."


#: A name this engine generated and that OPSIN parsed back to the same
#: structure. Stronger than PREDICTED and weaker than EXACT: derived from
#: the molecular graph by rule rather than looked up, and checked.
DERIVED = "derived"


def derived_name_for_structure(mol: Chem.Mol) -> NameResult:
    """A systematic name generated from the molecular graph by rule.

    Deterministic, offline, and about 10 ms -- no model, no weights, no
    network. It reaches structures no database has ever seen, which is
    exactly where PubChem stops.

    VERIFIED BEFORE IT IS RETURNED, when a parser is available: the name
    is fed back through OPSIN and must yield the structure it came from.
    A rule engine cannot be fluently wrong the way a language model can,
    but it can still be wrong, and this is a cheap independent check --
    the engine's own author uses the same one. Without OPSIN the name is
    still returned, flagged as unverified rather than silently trusted.

    See src/openchem/vendor/VENDORING.md for provenance and
    benchmarks/naming for the measured accuracy (120/124, stereochemistry
    11/11).
    """
    from openchem.vendor.iupac_namer import name_smiles

    smiles = Chem.MolToSmiles(mol)
    try:
        name = name_smiles(smiles)
    except Exception as exc:  # the engine raises a wide variety on odd input
        raise NamingError(f"Could not derive a name for this structure: {exc}") from exc
    if not name:
        raise NamingError("The nomenclature engine produced no name for this structure.")

    verified = verify_name_round_trip(str(name), mol)
    if verified is False:
        raise NamingError(
            "A name was derived but did not parse back to this structure, so it is "
            "being withheld rather than shown."
        )
    note = "" if verified else "Not verified: no offline parser available to check it."
    return NameResult(name=str(name), source="Nomenclature engine", kind=DERIVED, note=note)


def opsin_structure_for_name(name: str) -> StructureResult:
    """Parse an IUPAC name into a structure, offline and deterministically.

    Unlike PubChem this is a grammar, not a lookup: it handles names for
    compounds nobody has ever registered, and it fails cleanly on names it
    cannot parse rather than guessing.
    """
    if not opsin_available():
        raise NamingError(describe_opsin_status())
    with _java_on_path():
        from py2opsin import py2opsin as run_opsin

        result = run_opsin(name.strip())
    # py2opsin returns an empty string for an unparseable name.
    if not result:
        raise NamingError(f"OPSIN could not parse {name.strip()!r} as an IUPAC name.")
    smiles = result[0] if isinstance(result, list) else str(result)
    if not smiles:
        raise NamingError(f"OPSIN could not parse {name.strip()!r} as an IUPAC name.")
    return StructureResult(smiles=smiles, source="OPSIN", kind=PARSED)


def verify_name_round_trip(name: str, original: Chem.Mol) -> bool | None:
    """Does parsing the name back give the structure we started from?

    The only real check available on a predicted name, and worth having
    precisely because a wrong generated name looks exactly as
    authoritative as a right one. Returns `None` when no parser is available to check with
    -- which is honestly different from "checked and failed".
    """
    if not opsin_available():
        return None
    try:
        parsed = opsin_structure_for_name(name)
    except NamingError:
        return False
    candidate = Chem.MolFromSmiles(parsed.smiles)
    if candidate is None:
        return False
    return Chem.MolToSmiles(candidate) == Chem.MolToSmiles(original)


def compute_iupac_name(
    mol: Chem.Mol,
    molecule_uuid: str,
    parameters: dict | None = None,
    interpreter_path: str | None = None,
):
    """The "naming" category's calculator.

    Queries every available source and reports them ALL, each labelled with
    where it came from and what kind of answer it is. Sources are not
    merged into one "the name", because they genuinely differ in
    authority: a PubChem record is a curated fact, a derived name is
    generated from the structure, and showing them as one string would
    erase that.

    Network use is opt-in per run via the `use_pubchem` parameter, since a
    lookup sends the structure to NCBI.
    """
    from openchem.domain.common import CacheState, Provenance

    parameters = parameters or {}
    lines: list[str] = []
    results: list[NameResult] = []

    if parameters.get("use_pubchem", True):
        try:
            results.append(pubchem_name_for_structure(mol))
        except NamingError as exc:
            lines.append(f"PubChem: {exc}")

    # After PubChem, because a curated record beats a generated name even
    # when the generator is very good.
    try:
        results.append(derived_name_for_structure(mol))
    except NamingError as exc:
        lines.append(f"Nomenclature engine: {exc}")

    for result in results:
        line = f"{result.name}  [{result.source}, {result.kind}]"
        if result.kind == PREDICTED:
            verified = verify_name_round_trip(result.name, mol)
            if verified is True:
                line += "  -- round-trips back to this structure"
            elif verified is False:
                line += "  -- WARNING: does not round-trip back to this structure"
            # `None` means no parser was available to check with, which is
            # not the same as a failed check and is not claimed as one.
        lines.append(line)

    if not results and not any(line for line in lines if not line.startswith("PubChem:")):
        return _report(
            alert_id="iupac_name",
            name="IUPAC Name",
            molecule_uuid=molecule_uuid,
            matched=lines,
            category="naming",
            cache_state=CacheState.FAILED,
            error="No naming source returned a name. See the details for why.",
            provenance=Provenance(created_by="core", method="naming"),
        )

    return _report(
        alert_id="iupac_name",
        name="IUPAC Name",
        molecule_uuid=molecule_uuid,
        matched=lines,
        category="naming",
        provenance=Provenance(
            created_by="core",
            method="+".join(sorted({r.source for r in results})) or "naming",
            parameters={"sources": [{"source": r.source, "kind": r.kind} for r in results]},
        ),
    )


def _report(**fields) -> ReportResult:
    """One `AlertResult(...)` call site, as a `ReportResult`.

    The keyword names are unchanged -- `alert_id`, `name`, `matched`,
    `category` -- so the call sites above read as they always did and the
    diff stays small. `report_fields` does the translation and turns each
    line into a `Fact`; see `chem/report_adapter.py` for what a string can
    and cannot carry.

    A calculator that wants real units, evidence or limitations on a fact
    builds `Fact`s directly instead, as `geometry_analysis` now does.
    """
    return ReportResult(**report_fields(**fields))
