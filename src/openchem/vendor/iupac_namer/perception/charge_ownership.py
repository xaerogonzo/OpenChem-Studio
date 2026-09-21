"""Who owns each formally charged atom: exactly one route, or a declared hole.

Naming round 7 found a defect that lived in NO corpus: a carboxylate that also
carries a neutral OH was named as if the OH were the principal group. The cause
was not a wrong rule but a missing owner. ``_classify_acidic_anion`` deferred
that case to plan search ("mixed charged + neutral cases ... are deferred to the
standard plan-search path, which already handles them"), and plan search's
``_carved_acid_anion_sites`` excluded carboxylate ("handled by the dedicated
``_classify_acidic_anion`` path"). Each guard was right about its own half and
assumed the other guard covered the rest, so nothing did, and the charge fell to
an "oxido" prefix on the wrong parent.

This module makes ownership a MEASURED property instead of a comment:

* **structural class**, from the site itself (``_acidic_anion_site_kind``), not
  from any route: a carboxylate or sulfonate oxygen is an ``ACID_ANION`` site, an
  alkoxide or thiolate an ``OLATE_ANION`` site;
* **claimants**, from the real route predicates, never a copy of them: every
  classifier that yields a classification covering the atom (before the
  first-claimer-wins de-duplication, via ``classify_charges(claims_out=...)``),
  plus the plan search's two promotions: ``carved_anion`` when
  ``_carved_acid_anion_sites`` contains the atom, and ``fg_anion`` when FG
  perception detects an anion-variant group on it (the route that owns a
  zwitterion's carboxylate and a sulfinate, and is gated on net charge <= 0 as
  ``_name_bound`` gates it);
* **observed route**, from the real engine under ``diagnostics.capture()``: which
  classifier rendered, whether charge perception handed the molecule back to
  plan search and why, and which plan-search promotion (``carved_anion`` /
  ``fg_anion``) took it.

For a structural anion site the verdict is:

    OWNED         exactly one claimant, and the observed route agrees with it
    HOLE          no claimant -- the defect this module exists to see
    UNSUPPORTED   no claimant, and the class is in DECLARED_UNSUPPORTED with its reason
    OVERLAP       two claimants where no cascade is declared (an acid anion has
                  none), or two of the same tier; ordering, not design, picks
                  the winner. A declared cascade (a pure alkoxide is claimed by
                  the classifier first and the carved route second) is OWNED
    INCONSISTENT  one claimant, but the engine did not take that route

``semantic_owner`` is separate from the implementation route on purpose: it says
WHAT the class is (``ACID_ANION``), so a refactor that moves the logic to another
function cannot change ownership without changing the model.

Nothing here alters a name. It is read-only over the molecule, and the two hooks
it needed elsewhere (``classify_charges(claims_out=...)`` and
``diagnostics.record_route``) change no result.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

ACID_ANION = "ACID_ANION"    # a deprotonated ACID: carboxylate, sulfonate
OLATE_ANION = "OLATE_ANION"  # a deprotonated alcohol or thiol: -olate, -thiolate

#: The classifier hints that name an acid-derived or olate anion, mapped to the
#: semantic class they are the owner of. Everything else the dispatcher knows
#: (carbon ions, nitrogen cations, boranuides, ...) is out of this module's
#: verdict: it reports their claimants but does not call a hole for them.
_ANION_HINT_CLASS = {
    "acidic_anion_carboxylate": ACID_ANION,
    "acidic_anion_olate": OLATE_ANION,
}

_ANION_CLASSIFIER = "_classify_acidic_anion"
_CARVED = "carved_anion"
_FG_ANION = "fg_anion"
#: A WHOLE-MOLECULE route that answers before any classifier runs: ``detect`` looks the
#: canonical SMILES up in the curated inorganic table (carbamate, thiocyanate, ...) and
#: returns the retained name. It is a declared cascade, not an overlap: it is asked first, on
#: purpose, so that a retained name beats a classifier's constructed one. The diagnostic did
#: not know it until the dynamic cross-check found 'carbamate' owned by NOTHING the static
#: claims named (naming round 7, R3).
_CURATED = "curated_inorganic"

#: Classes for which BOTH the classifier and the plan search's carved route may
#: claim the same site, in that order: a pure alkoxide or thiolate is claimed by
#: both, the classifier answers first, and the carved route exists for what the
#: classifier defers (a thiolate beside a neutral -SH). That is a cascade, and it
#: is declared here so it is not mistaken for a double claim. ACID_ANION has NO
#: cascade: the carved route excludes carboxylate on purpose ("the dedicated path
#: handles it"), so a carved claim on a carboxylate is a conflict.
_CASCADE_ALLOWED = frozenset({OLATE_ANION})


class Verdict(str, Enum):
    OWNED = "OWNED"
    HOLE = "HOLE"
    OVERLAP = "OVERLAP"
    INCONSISTENT = "INCONSISTENT"
    #: No route names it AND the scope says so on purpose. Not a defect; a declared edge.
    UNSUPPORTED = "UNSUPPORTED"


#: Structural classes the engine deliberately does not name as an ANION, each with its reason. A site
#: in one of these with no owner is UNSUPPORTED rather than a HOLE, so the invariant reads "exactly one
#: owner, or a declared UNSUPPORTED" and never "or nobody noticed". Extending this dict is a scope
#: decision and needs the reason in words.
DECLARED_UNSUPPORTED: dict[str, str] = {
    "phosphorus_oxoacid": (
        "a deprotonated phosphonic or phosphoric acid is named by the book's 'hydrogen' method for acid "
        "esters of inorganic acids ('hydrogen phenylphosphonate', 'phenyl hydrogen phosphate', pdf p. 808), "
        "a construction of its own that is not built; the engine names the neutralised skeleton with oxido "
        "prefixes, which round-trips and is not preferred (naming round 7, adjudicated HOLE_PHOSPHORUS_ACID)"
    ),
}


@dataclass(frozen=True)
class SiteOwnership:
    atom: int
    element: str
    charge: int
    #: ACID_ANION / OLATE_ANION, or None for a charged atom of another class.
    structural_class: str | None
    #: Implementation routes that would claim the atom, in dispatch order.
    claimants: tuple[str, ...]
    verdict: Verdict | None  # None: not an anion site, so no verdict is called


@dataclass(frozen=True)
class Observed:
    """What the real engine did, as recorded by ``diagnostics.capture()``."""

    name: str | None
    classifier_rendered: tuple[str, ...]   # suffix hints that succeeded
    handed_back: tuple[str, ...]           # decline reasons from charge perception
    plan_search_routes: tuple[str, ...]    # "carved_anion" / "fg_anion" / "curated_inorganic"

    @property
    def route(self) -> str:
        if _CURATED in self.plan_search_routes:
            return _CURATED
        if self.classifier_rendered:
            return "classifier:" + "+".join(self.classifier_rendered)
        if self.plan_search_routes:
            return "plan_search:" + "+".join(self.plan_search_routes)
        if self.handed_back:
            return "plan_search:unpromoted(" + "+".join(self.handed_back) + ")"
        return "none_recorded"


@dataclass(frozen=True)
class OwnershipReport:
    smiles: str
    sites: tuple[SiteOwnership, ...]
    observed: Observed | None

    @property
    def anion_sites(self) -> tuple[SiteOwnership, ...]:
        return tuple(s for s in self.sites if s.structural_class is not None)

    @property
    def verdict(self) -> Verdict | None:
        """The worst verdict over the structural anion sites, or None if there are
        none. Order: HOLE, OVERLAP, INCONSISTENT, UNSUPPORTED, OWNED."""
        verdicts = {s.verdict for s in self.anion_sites}
        for worst in (Verdict.HOLE, Verdict.OVERLAP, Verdict.INCONSISTENT, Verdict.UNSUPPORTED, Verdict.OWNED):
            if worst in verdicts:
                return worst
        return None

    @property
    def owners(self) -> tuple[str, ...]:
        """Distinct implementation routes claiming any structural anion site."""
        return tuple(sorted({c for s in self.anion_sites for c in s.claimants}))


def unsupported_class(mol, atom_idx: int) -> str | None:
    """The DECLARED_UNSUPPORTED class this charged atom belongs to, or None."""
    atom = mol.GetAtomWithIdx(atom_idx)
    if atom.GetSymbol() == "O" and _is_oxoacid_anion_oxygen(mol, atom):
        centre = next(n for n in atom.GetNeighbors() if n.GetAtomicNum() != 1)
        if centre.GetSymbol() == "P":
            return "phosphorus_oxoacid"
    return None


def structural_sites(mol) -> dict[int, str]:
    """Atom index -> ACID_ANION / OLATE_ANION, from the site alone.

    Uses the same helper the classifier gates on, so "is this a carboxylate
    oxygen" has one definition; nothing about WHICH ROUTE handles it is read.
    """
    from openchem.vendor.iupac_namer.perception.charge_perception import (
        _acidic_anion_site_kind,
    )

    out: dict[int, str] = {}
    for atom in mol.GetAtoms():
        if atom.GetFormalCharge() != -1:
            continue
        kind = _acidic_anion_site_kind(mol, atom)
        if kind in ("carboxylate", "sulfonate") or _is_oxoacid_anion_oxygen(mol, atom):
            out[atom.GetIdx()] = ACID_ANION
        elif kind == "olate":
            out[atom.GetIdx()] = OLATE_ANION
    return out


def _is_oxoacid_anion_oxygen(mol, atom) -> bool:
    """O(-) on a sulfur or phosphorus that also carries a double-bonded oxygen: a
    deprotonated sulfinic / sulfonic / sulfuric / phosphonic / phosphoric acid.

    Defined from the site alone, NOT from what any route accepts. The classifier
    gate knows only carboxylate and C-sulfonate, so a route-derived definition
    would have called a phosphonate "not an anion site" and hidden exactly the
    kind of gap this module is for.
    """
    if atom.GetSymbol() != "O" or atom.GetTotalNumHs() != 0:
        return False
    heavy = [n for n in atom.GetNeighbors() if n.GetAtomicNum() != 1]
    if len(heavy) != 1 or heavy[0].GetSymbol() not in ("S", "P"):
        return False
    centre = heavy[0]
    bond = mol.GetBondBetweenAtoms(atom.GetIdx(), centre.GetIdx())
    if bond is None or bond.GetBondTypeAsDouble() != 1.0:
        return False
    for other in centre.GetNeighbors():
        if other.GetIdx() == atom.GetIdx() or other.GetSymbol() != "O":
            continue
        b = mol.GetBondBetweenAtoms(centre.GetIdx(), other.GetIdx())
        if b is not None and b.GetBondTypeAsDouble() == 2.0:
            return True
    return False


def claimants(mol) -> dict[int, tuple[str, ...]]:
    """Charged atom -> every route that would claim it, in dispatch order.

    Classifier claims are taken BEFORE the first-claimer-wins de-duplication, so
    an atom two classifiers would both claim shows both. The plan search's carved
    route is asked directly (``_carved_acid_anion_sites``): it is a pure function
    of the molecule.
    """
    from openchem.vendor.iupac_namer.engine import _carved_acid_anion_sites
    from openchem.vendor.iupac_namer.perception.charge_perception import (
        classify_charges,
    )

    raw: list = []
    classify_charges(mol, claims_out=raw)
    claims: dict[int, list[str]] = {
        a.GetIdx(): [] for a in mol.GetAtoms() if a.GetFormalCharge() != 0
    }
    for name, cls in raw:
        for idx in cls.site_atom_indices:
            if idx in claims:
                claims[idx].append(f"classifier:{name}:{cls.suffix_hint}")
    for idx in _carved_acid_anion_sites(mol):
        claims.setdefault(idx, []).append(_CARVED)
    for idx in _fg_anion_sites(mol):
        claims.setdefault(idx, []).append(_FG_ANION)
    if _curated_name(mol) is not None:
        for idx in claims:
            claims[idx].insert(0, _CURATED)
    return {idx: tuple(v) for idx, v in claims.items()}


def _curated_name(mol) -> str | None:
    """The retained name the curated inorganic table gives this whole molecule, if any."""
    from rdkit import Chem

    from openchem.vendor.iupac_namer.data_loader import _lookup_curated_inorganic

    try:
        record = _lookup_curated_inorganic(Chem.MolToSmiles(mol))
    except Exception:  # noqa: BLE001 - a lookup failure is "no curated name"
        return None
    return record.get("name") if record else None


def _fg_anion_sites(mol) -> frozenset[int]:
    """Charged atoms the plan search's FG-anion promotion would take.

    A mirror of the promotion in ``engine._name_bound`` (net charge <= 0, then a
    suffix-eligible FG of an anion-variant type anchored on, or claiming, a
    negatively charged atom). It IS a mirror, unlike the other two claimants, so
    ``charged_owners(measure=True)`` checks it against the route the engine
    actually recorded: a drift shows as INCONSISTENT, not as a silent wrong answer.
    """
    from openchem.vendor.iupac_namer.engine import _FG_TYPES_WITH_ANION_VARIANT
    from openchem.vendor.iupac_namer.perception import Perception

    if sum(a.GetFormalCharge() for a in mol.GetAtoms()) > 0:
        return frozenset()
    neg = {a.GetIdx() for a in mol.GetAtoms() if a.GetFormalCharge() < 0}
    if not neg:
        return frozenset()
    try:
        fgs = Perception(mol).fgs.detected_fgs
    except Exception:  # noqa: BLE001 - perception failing is "no claim"
        return frozenset()
    sites: set[int] = set()
    for fg in fgs:
        if not fg.suffix_eligible or fg.type not in _FG_TYPES_WITH_ANION_VARIANT:
            continue
        if fg.anchor in neg or any(i in neg for i in fg.atoms):
            sites.update(neg & ({fg.anchor} | set(fg.atoms)))
    return frozenset(sites)


def observe(smiles: str) -> Observed:
    """Run the real engine once and record which route named the charge."""
    from openchem.vendor.iupac_namer import diagnostics, name_smiles

    with diagnostics.capture() as rec:
        try:
            name = name_smiles(smiles)
        except Exception:  # noqa: BLE001 - an engine refusal is an observation
            name = None
    return Observed(
        name=name,
        classifier_rendered=tuple(
            hint for hint, c in sorted(rec.stats.items()) if c.get("succeeded")
        ),
        handed_back=tuple(sorted({g.reason for g in rec.gaps})),
        plan_search_routes=tuple(sorted({route for route, _smi in rec.routes})),
    )


def _verdict(structural_class: str, site_claims: tuple[str, ...], observed: Observed | None):
    """HOLE / OVERLAP / INCONSISTENT / OWNED for one structural anion site."""
    # Only the routes that OWN this class count: an unrelated classifier that
    # happens to cover the atom (a nitro group's O-, say) is not an owner.
    classifier_owners = [
        c for c in site_claims
        if c.startswith("classifier:" + _ANION_CLASSIFIER)
        and _ANION_HINT_CLASS.get(c.rsplit(":", 1)[-1]) == structural_class
    ]
    carved_owners = [c for c in site_claims if c == _CARVED]
    fg_owners = [c for c in site_claims if c == _FG_ANION]
    if _CURATED in site_claims:
        # A retained whole-molecule name answers first, by design: not an overlap.
        if observed is not None and _CURATED not in observed.plan_search_routes:
            return Verdict.INCONSISTENT
        return Verdict.OWNED
    owners = classifier_owners + carved_owners + fg_owners
    if not owners:
        return Verdict.HOLE
    if len(owners) > 1 and not _is_declared_cascade(
        structural_class, bool(classifier_owners), bool(carved_owners), bool(fg_owners)
    ):
        return Verdict.OVERLAP
    if observed is not None:
        # The EFFECTIVE owner is the first that claims, in precedence order:
        # classifier, then the plan search's carved route, then its FG route.
        if classifier_owners:
            expected_route_seen = bool(observed.classifier_rendered)
        elif carved_owners:
            expected_route_seen = _CARVED in observed.plan_search_routes
        else:
            expected_route_seen = _FG_ANION in observed.plan_search_routes
        if not expected_route_seen:
            return Verdict.INCONSISTENT
    return Verdict.OWNED


def _is_declared_cascade(structural_class: str, classifier: bool, carved: bool, fg: bool) -> bool:
    """Is this SET of claimants one the design declares? Only the olate cascade
    (classifier first, carved second) is. Any other pair of routes claiming one
    site is ordering picking a winner, which is what OVERLAP reports."""
    if structural_class not in _CASCADE_ALLOWED:
        return False
    return not fg and classifier and carved


def _site_verdict(mol, idx: int, klass: str, site_claims, observed):
    verdict = _verdict(klass, site_claims, observed)
    if verdict is Verdict.HOLE and unsupported_class(mol, idx) is not None:
        return Verdict.UNSUPPORTED
    return verdict


def charged_owners(mol, smiles: str | None = None, *, measure: bool = True) -> OwnershipReport:
    """The ownership of every formally charged atom of ``mol``.

    ``measure=True`` also runs the real engine to observe the route, which is what
    turns a static claim into a checked one; ``measure=False`` is the pure static
    view (no engine call), used by the mutation tests where the observation is
    beside the point.

    A multi-component structure is reported per atom over the whole molecule, but
    its OBSERVED route is the whole-salt run, so per-component conclusions belong
    to the caller's component-by-component use of this function.
    """
    from rdkit import Chem

    smi = smiles if smiles is not None else Chem.MolToSmiles(mol)
    classes = structural_sites(mol)
    claims = claimants(mol)
    observed = observe(smi) if measure else None
    sites = []
    for atom in mol.GetAtoms():
        if atom.GetFormalCharge() == 0:
            continue
        idx = atom.GetIdx()
        klass = classes.get(idx)
        site_claims = claims.get(idx, ())
        sites.append(SiteOwnership(
            atom=idx,
            element=atom.GetSymbol(),
            charge=atom.GetFormalCharge(),
            structural_class=klass,
            claimants=site_claims,
            verdict=_site_verdict(mol, idx, klass, site_claims, observed) if klass else None,
        ))
    return OwnershipReport(smiles=smi, sites=tuple(sites), observed=observed)
