"""A curated catalogue of docking targets, with their binding sites named.

WHY THIS EXISTS. Finding a receptor on RCSB [source:rcsb_pdb] is not the hard part -- there
are dozens of mu-opioid entries and the search returns all of them. The
hard part is the next question: *which* one, and *where on it* does a
small molecule go. An entry with no bound ligand gives you a protein and
no site; an entry solved in lipidic cubic phase is full of monoolein and
cholesterol, so "the biggest non-protein thing in the file" is a lipid
rather than the pharmacology. Answering that per target, by hand, every
time, is the friction this replaces.

So each entry names three things a bare PDB ID does not: which structure
to use, what was bound to it, and the residue code of that ligand -- which
is what `chem/binding_site.py` turns into a search box. A catalogue entry
therefore arrives ready to dock, rather than ready to research.

WHAT IS SHIPPED HERE IS THE INDEX, NOT THE STRUCTURES. Coordinates are
fetched from RCSB on demand and cached (`services/receptor_library_service.py`).
PDB data is public domain and could be vendored, but ~50 structures is
tens to hundreds of megabytes of files that RCSB already serves, and a
vendored copy silently goes stale as entries are re-refined.

EVERY FIELD BELOW CAME FROM THE RCSB API, NOT FROM RECOLLECTION. The
PDB id, title, resolution, method, ligand code and ligand name of all 49
entries were read from `data.rcsb.org` and checked against the target each
was proposed for. That mattered: the first pass picked each entry's
heaviest non-solvent component as its ligand, and that rule chose
dodecaethylene glycol for the beta-2 adrenergic receptor, the haem for
COX-2, and FAD for MAO-B -- three cofactors and a cryoprotectant in place
of carazolol, rofecoxib and safinamide. The codes here are the corrected
ones.

Nine proposed entries were DROPPED rather than shipped with a guess,
because the deposit contains no ligand to place a box on: the 5-HT3
receptor (4PIR), two NMDA cryo-EM structures (6IRA), Cav1.1 (5GJV),
Cav3.1 (6KZO), two hERG entries (5VA1/5VA2), carbonic anhydrase at 0.9 A
(3KS3), the active delta-opioid receptor (6PT2, whose agonist is a
peptide and therefore part of the polymer, not a ligand), and cardiac
Nav1.5 (6UZ3). Where a replacement with a real bound drug existed it was
used instead -- 8ZYO for hERG, 6DG8 for 5-HT3, 3HS4 for carbonic
anhydrase, 6JP5 for Cav1.1, 6LQA for Nav1.5.

THIS IS A STARTING POINT, NOT AN ENDORSEMENT. A co-crystallised ligand
marks a site that is real and druggable, which is a far better starting
box than a guess, but it is still one conformational state of one
construct. Several GPCR entries here are thermostabilised or
BRIL/T4-lysozyme fusions -- standard practice for crystallising them, and
noted per entry where it applies, because it is the kind of thing that
matters and does not appear in the title.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class ReceptorEntry:
    """One catalogued structure, and where its binding site is.

    `ligand_code` is the load-bearing field -- the three-character PDB
    chemical component id of the co-crystallised ligand, which
    `binding_site.box_from_ligand` uses to find the site. Everything else
    is there so a chemist can tell entries apart without opening them.
    """

    pdb_id: str
    #: What a user is looking for ("mu-opioid receptor"), not the deposit
    #: title -- titles say things like "Crystal structure of the chimeric
    #: protein of 5-HT1B-BRIL in complex with ergotamine", which is
    #: accurate and unsearchable.
    target: str
    family: str
    #: PDB chemical component id of the ligand that defines the site.
    ligand_code: str
    #: Its common name where it has one, otherwise the systematic name.
    ligand_name: str
    resolution_angstrom: float
    method: str
    #: The receptor's functional state, where the structure captures one.
    #: Agonist- and antagonist-bound states of the same GPCR have
    #: genuinely different pockets, so docking an agonist into an inactive
    #: structure is a real (and easy) mistake.
    state: str = ""
    #: Anything that would change how a result should be read -- fusion
    #: partners, thermostabilising mutations, non-human source.
    caveat: str = ""

    @property
    def label(self) -> str:
        state = f" ({self.state})" if self.state else ""
        return f"{self.target}{state} - {self.pdb_id}"


# Ordered by family, then roughly by how commonly the target is docked.
# `state` is filled in only where the deposit genuinely establishes one.
RECEPTOR_LIBRARY: tuple[ReceptorEntry, ...] = (
    # --- Opioid receptors ---------------------------------------------
    ReceptorEntry(
        pdb_id="4DKL", target="mu-opioid receptor", family="Opioid",
        ligand_code="BF0", ligand_name="beta-funaltrexamine (beta-FNA)",
        resolution_angstrom=2.80, method="X-ray diffraction", state="inactive",
        caveat="T4-lysozyme fusion; beta-FNA is covalently bound to Lys233.",
    ),
    ReceptorEntry(
        pdb_id="5C1M", target="mu-opioid receptor", family="Opioid",
        ligand_code="VF1", ligand_name="BU72 (agonist)",
        resolution_angstrom=2.07, method="X-ray diffraction", state="active",
        caveat="Nanobody-stabilised active state.",
    ),
    ReceptorEntry(
        pdb_id="8EF5", target="mu-opioid receptor", family="Opioid",
        ligand_code="7V7", ligand_name="fentanyl",
        resolution_angstrom=3.30, method="Electron microscopy", state="active",
        caveat="Gi-protein complex.",
    ),
    ReceptorEntry(
        pdb_id="4DJH", target="kappa-opioid receptor", family="Opioid",
        ligand_code="JDC", ligand_name="JDTic (antagonist)",
        resolution_angstrom=2.90, method="X-ray diffraction", state="inactive",
    ),
    ReceptorEntry(
        pdb_id="6B73", target="kappa-opioid receptor", family="Opioid",
        ligand_code="CVV", ligand_name="MP1104 (agonist)",
        resolution_angstrom=3.10, method="X-ray diffraction", state="active",
        caveat="Nanobody-stabilised active state.",
    ),
    ReceptorEntry(
        pdb_id="4N6H", target="delta-opioid receptor", family="Opioid",
        ligand_code="EJ4", ligand_name="naltrindole (antagonist)",
        resolution_angstrom=1.80, method="X-ray diffraction", state="inactive",
        caveat="Highest-resolution opioid receptor structure here.",
    ),
    ReceptorEntry(
        pdb_id="4EA3", target="nociceptin/orphanin FQ receptor (NOP)",
        family="Opioid", ligand_code="0NN", ligand_name="C-24 (antagonist)",
        resolution_angstrom=3.01, method="X-ray diffraction", state="inactive",
    ),
    # --- Sigma receptors ----------------------------------------------
    ReceptorEntry(
        pdb_id="5HK1", target="sigma1 receptor", family="Sigma",
        ligand_code="61W", ligand_name="PD144418",
        resolution_angstrom=2.51, method="X-ray diffraction",
    ),
    ReceptorEntry(
        pdb_id="5HK2", target="sigma1 receptor", family="Sigma",
        ligand_code="61V", ligand_name="4-IBP",
        resolution_angstrom=3.20, method="X-ray diffraction",
    ),
    ReceptorEntry(
        pdb_id="7M93", target="sigma2 receptor (TMEM97)", family="Sigma",
        ligand_code="YT1", ligand_name="PB28",
        resolution_angstrom=2.94, method="X-ray diffraction",
        caveat="Bovine, not human.",
    ),
    # --- Serotonergic --------------------------------------------------
    ReceptorEntry(
        pdb_id="7E2Y", target="5-HT1A receptor", family="Serotonergic",
        ligand_code="SRO", ligand_name="serotonin",
        resolution_angstrom=3.00, method="Electron microscopy", state="active",
        caveat="Gi-protein complex.",
    ),
    ReceptorEntry(
        pdb_id="4IAR", target="5-HT1B receptor", family="Serotonergic",
        ligand_code="ERM", ligand_name="ergotamine",
        resolution_angstrom=2.70, method="X-ray diffraction",
        caveat="BRIL fusion construct.",
    ),
    ReceptorEntry(
        pdb_id="6A93", target="5-HT2A receptor", family="Serotonergic",
        ligand_code="8NU", ligand_name="risperidone",
        resolution_angstrom=3.00, method="X-ray diffraction", state="inactive",
    ),
    ReceptorEntry(
        pdb_id="6WGT", target="5-HT2A receptor", family="Serotonergic",
        ligand_code="7LD", ligand_name="LSD",
        resolution_angstrom=3.40, method="X-ray diffraction",
    ),
    ReceptorEntry(
        pdb_id="4IB4", target="5-HT2B receptor", family="Serotonergic",
        ligand_code="ERM", ligand_name="ergotamine",
        resolution_angstrom=2.70, method="X-ray diffraction",
        caveat="BRIL fusion construct.",
    ),
    ReceptorEntry(
        pdb_id="6BQG", target="5-HT2C receptor", family="Serotonergic",
        ligand_code="ERM", ligand_name="ergotamine",
        resolution_angstrom=3.00, method="X-ray diffraction",
    ),
    ReceptorEntry(
        pdb_id="6DG8", target="5-HT3A receptor (channel)", family="Serotonergic",
        ligand_code="SRO", ligand_name="serotonin",
        resolution_angstrom=3.89, method="Electron microscopy",
        caveat="Pentameric ligand-gated ion channel; the site is at a "
               "subunit interface, so which copy you box matters.",
    ),
    # --- Adrenergic ----------------------------------------------------
    ReceptorEntry(
        pdb_id="2VT4", target="beta1-adrenergic receptor", family="Adrenergic",
        ligand_code="P32", ligand_name="cyanopindolol",
        resolution_angstrom=2.70, method="X-ray diffraction", state="inactive",
        caveat="Turkey, with thermostabilising mutations.",
    ),
    ReceptorEntry(
        pdb_id="2RH1", target="beta2-adrenergic receptor", family="Adrenergic",
        ligand_code="CAU", ligand_name="carazolol (inverse agonist)",
        resolution_angstrom=2.40, method="X-ray diffraction", state="inactive",
        caveat="T4-lysozyme fusion. A long-standing docking benchmark.",
    ),
    ReceptorEntry(
        pdb_id="3SN6", target="beta2-adrenergic receptor", family="Adrenergic",
        ligand_code="P0G", ligand_name="BI-167107 (agonist)",
        resolution_angstrom=3.20, method="X-ray diffraction", state="active",
        caveat="Gs-protein complex -- the classic active-state GPCR structure.",
    ),
    ReceptorEntry(
        pdb_id="6KUX", target="alpha2A-adrenergic receptor", family="Adrenergic",
        ligand_code="E3F", ligand_name="RSC (antagonist)",
        resolution_angstrom=2.70, method="X-ray diffraction", state="inactive",
    ),
    ReceptorEntry(
        pdb_id="7B6W", target="alpha1B-adrenergic receptor", family="Adrenergic",
        ligand_code="T0B", ligand_name="(+)-cyclazosin",
        resolution_angstrom=2.87, method="X-ray diffraction", state="inactive",
    ),
    # --- Dopaminergic ---------------------------------------------------
    ReceptorEntry(
        pdb_id="6CM4", target="dopamine D2 receptor", family="Dopaminergic",
        ligand_code="8NU", ligand_name="risperidone",
        resolution_angstrom=2.87, method="X-ray diffraction", state="inactive",
    ),
    ReceptorEntry(
        pdb_id="3PBL", target="dopamine D3 receptor", family="Dopaminergic",
        ligand_code="ETQ", ligand_name="eticlopride",
        resolution_angstrom=2.89, method="X-ray diffraction", state="inactive",
    ),
    ReceptorEntry(
        pdb_id="5WIU", target="dopamine D4 receptor", family="Dopaminergic",
        ligand_code="AQD", ligand_name="nemonapride",
        resolution_angstrom=1.96, method="X-ray diffraction", state="inactive",
    ),
    # --- Cholinergic -----------------------------------------------------
    ReceptorEntry(
        pdb_id="5CXV", target="muscarinic M1 receptor", family="Cholinergic",
        ligand_code="0HK", ligand_name="tiotropium",
        resolution_angstrom=2.70, method="X-ray diffraction", state="inactive",
    ),
    ReceptorEntry(
        pdb_id="3UON", target="muscarinic M2 receptor", family="Cholinergic",
        ligand_code="QNB", ligand_name="QNB (3-quinuclidinyl benzilate)",
        resolution_angstrom=3.00, method="X-ray diffraction", state="inactive",
    ),
    ReceptorEntry(
        pdb_id="4DAJ", target="muscarinic M3 receptor", family="Cholinergic",
        ligand_code="0HK", ligand_name="tiotropium",
        resolution_angstrom=3.40, method="X-ray diffraction", state="inactive",
    ),
    ReceptorEntry(
        pdb_id="5KXI", target="nicotinic alpha4beta2 receptor", family="Cholinergic",
        ligand_code="NCT", ligand_name="nicotine",
        resolution_angstrom=3.94, method="X-ray diffraction",
        caveat="Low resolution; site sits at a subunit interface.",
    ),
    ReceptorEntry(
        pdb_id="4EY7", target="acetylcholinesterase", family="Cholinergic",
        ligand_code="E20", ligand_name="donepezil",
        resolution_angstrom=2.35, method="X-ray diffraction",
        caveat="Deep gorge site -- a larger box than usual is warranted.",
    ),
    # --- Histamine and cannabinoid ---------------------------------------
    ReceptorEntry(
        pdb_id="3RZE", target="histamine H1 receptor", family="Histamine",
        ligand_code="5EH", ligand_name="doxepin",
        resolution_angstrom=3.10, method="X-ray diffraction", state="inactive",
    ),
    ReceptorEntry(
        pdb_id="5TGZ", target="cannabinoid CB1 receptor", family="Cannabinoid",
        ligand_code="ZDG", ligand_name="AM6538 (antagonist)",
        resolution_angstrom=2.80, method="X-ray diffraction", state="inactive",
    ),
    ReceptorEntry(
        pdb_id="5ZTY", target="cannabinoid CB2 receptor", family="Cannabinoid",
        ligand_code="9JU", ligand_name="AM10257",
        resolution_angstrom=2.80, method="X-ray diffraction",
    ),
    # --- Ion channels -----------------------------------------------------
    ReceptorEntry(
        pdb_id="4PE5", target="NMDA receptor GluN1/GluN2B", family="Ion channel",
        ligand_code="QEL", ligand_name="ifenprodil",
        resolution_angstrom=3.96, method="X-ray diffraction",
        caveat="Ifenprodil binds the GluN1/GluN2B amino-terminal-domain "
               "interface -- an allosteric site, NOT the channel pore.",
    ),
    ReceptorEntry(
        pdb_id="6X3T", target="GABA-A receptor alpha1beta2gamma2", family="Ion channel",
        ligand_code="ABU", ligand_name="GABA (orthosteric agonist)",
        resolution_angstrom=2.55, method="Electron microscopy",
        caveat="The orthosteric GABA site, at a beta-alpha interface. GABA is "
               "small, so the derived box needs generous padding.",
    ),
    ReceptorEntry(
        pdb_id="6HUP", target="GABA-A receptor alpha1beta3gamma2L", family="Ion channel",
        ligand_code="DZP", ligand_name="diazepam",
        resolution_angstrom=3.58, method="Electron microscopy",
        caveat="The benzodiazepine site (alpha-gamma interface), distinct from the "
               "orthosteric GABA site in 6X3T.",
    ),
    ReceptorEntry(
        pdb_id="7C7Q", target="GABA-B receptor", family="Ion channel",
        ligand_code="2C0", ligand_name="baclofen",
        resolution_angstrom=3.00, method="Electron microscopy", state="active",
        caveat="Also holds the positive allosteric modulator BHFF (FN0) at "
               "a separate site.",
    ),
    ReceptorEntry(
        pdb_id="6J8G", target="voltage-gated sodium channel Nav1.7",
        family="Ion channel", ligand_code="9SL", ligand_name="saxitoxin",
        resolution_angstrom=3.20, method="Electron microscopy",
        caveat="Saxitoxin blocks at the extracellular selectivity filter -- "
               "NOT the intracellular local-anaesthetic site.",
    ),
    ReceptorEntry(
        pdb_id="6LQA", target="voltage-gated sodium channel Nav1.5",
        family="Ion channel", ligand_code="QDN", ligand_name="quinidine",
        resolution_angstrom=3.30, method="Electron microscopy",
        caveat="Quinidine occupies the central cavity -- the local-anaesthetic "
               "site, so a better antiarrhythmic starting point than 6J8G.",
    ),
    ReceptorEntry(
        pdb_id="6JP5", target="voltage-gated calcium channel Cav1.1",
        family="Ion channel", ligand_code="C5U", ligand_name="nifedipine",
        resolution_angstrom=2.90, method="Electron microscopy",
        caveat="Rabbit. The dihydropyridine site.",
    ),
    ReceptorEntry(
        pdb_id="8ZYO", target="hERG potassium channel (KCNH2)",
        family="Ion channel", ligand_code="XB7", ligand_name="astemizole",
        resolution_angstrom=3.29, method="Electron microscopy",
        caveat="Astemizole was withdrawn for QT prolongation -- this is the "
               "cardiotoxicity liability the ADMET hERG predictor screens for.",
    ),
    # --- Transporters -----------------------------------------------------
    ReceptorEntry(
        pdb_id="5I6X", target="serotonin transporter (SERT)", family="Transporter",
        ligand_code="8PR", ligand_name="paroxetine",
        resolution_angstrom=3.14, method="X-ray diffraction",
        caveat="Thermostabilised ts3 construct.",
    ),
    ReceptorEntry(
        pdb_id="4M48", target="dopamine transporter (DAT)", family="Transporter",
        ligand_code="21B", ligand_name="nortriptyline",
        resolution_angstrom=2.96, method="X-ray diffraction",
        caveat="Drosophila, not human -- the binding site differs enough that "
               "human DAT conclusions do not transfer directly.",
    ),
    # --- Other high-value targets ------------------------------------------
    ReceptorEntry(
        pdb_id="3EML", target="adenosine A2A receptor", family="Other",
        ligand_code="ZMA", ligand_name="ZM241385 (antagonist)",
        resolution_angstrom=2.60, method="X-ray diffraction", state="inactive",
        caveat="T4-lysozyme fusion. One of the most-used GPCR docking benchmarks.",
    ),
    ReceptorEntry(
        pdb_id="5KIR", target="cyclooxygenase-2 (COX-2)", family="Other",
        ligand_code="RCX", ligand_name="rofecoxib (Vioxx)",
        resolution_angstrom=2.70, method="X-ray diffraction",
        caveat="Also contains the catalytic haem (COH) -- a cofactor, not the "
               "drug site.",
    ),
    ReceptorEntry(
        pdb_id="2V5Z", target="monoamine oxidase B (MAO-B)", family="Other",
        ligand_code="SAG", ligand_name="safinamide",
        resolution_angstrom=1.60, method="X-ray diffraction",
        caveat="Also contains the FAD cofactor, adjacent to the inhibitor site.",
    ),
    ReceptorEntry(
        pdb_id="1ERE", target="estrogen receptor alpha", family="Other",
        ligand_code="EST", ligand_name="estradiol",
        resolution_angstrom=3.10, method="X-ray diffraction",
        caveat="Ligand-binding domain only. Fully enclosed pocket, so a "
               "docked pose has little room to be wrong.",
    ),
    ReceptorEntry(
        pdb_id="3HS4", target="carbonic anhydrase II", family="Other",
        ligand_code="AZM", ligand_name="acetazolamide",
        resolution_angstrom=1.10, method="X-ray diffraction",
        caveat="Binding requires coordination to the catalytic zinc, which "
               "Vina's scoring function models only crudely.",
    ),
    ReceptorEntry(
        pdb_id="1HSG", target="HIV-1 protease", family="Other",
        ligand_code="MK1", ligand_name="indinavir",
        resolution_angstrom=2.00, method="X-ray diffraction",
        caveat="The textbook docking tutorial system.",
    ),
)


def families() -> list[str]:
    """Catalogue families, in the order the library declares them."""
    seen: list[str] = []
    for entry in RECEPTOR_LIBRARY:
        if entry.family not in seen:
            seen.append(entry.family)
    return seen


def by_family(family: str) -> list[ReceptorEntry]:
    return [e for e in RECEPTOR_LIBRARY if e.family == family]


def find(pdb_id: str) -> ReceptorEntry | None:
    wanted = pdb_id.strip().upper()
    return next((e for e in RECEPTOR_LIBRARY if e.pdb_id == wanted), None)


def search(query: str) -> list[ReceptorEntry]:
    """Substring match over target, family, PDB id and ligand name.

    Searching the LIGAND matters as much as searching the target, and is
    the part a plain RCSB search handles badly: "what has fentanyl bound
    to it" and "what has a benzodiazepine site" are how someone actually
    arrives at a structure. Greek letters are folded to their spelled-out
    forms both ways, so "alpha-2A" and "α2A" both find the same entry --
    nobody types α at a search box.
    """
    text = _normalise(query)
    if not text:
        return list(RECEPTOR_LIBRARY)
    return [
        entry
        for entry in RECEPTOR_LIBRARY
        # Each field is matched SEPARATELY. Normalising one concatenated
        # string instead lets a match straddle a field boundary: the
        # 5-HT1A entry joins ligand "serotonin" to state "active", and
        # "serotoninactive" contains "inactive", so a search for inactive
        # structures returned an active one.
        if any(
            text in _normalise(field)
            for field in (entry.target, entry.family, entry.pdb_id,
                          entry.ligand_name, entry.state)
        )
    ]


_GREEK = {
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "κ": "kappa",
    "μ": "mu", "σ": "sigma", "ε": "epsilon", "θ": "theta", "ρ": "rho",
}


def _normalise(text: str) -> str:
    lowered = text.strip().lower()
    for symbol, name in _GREEK.items():
        lowered = lowered.replace(symbol, name)
    # So "5-HT2A", "5ht2a" and "5 HT 2A" all match each other.
    return "".join(ch for ch in lowered if ch.isalnum())
