"""Reaction templates contributed by plugins.

`RDKitTemplateProvider` has always read a bundled JSON file plus an
optional one in the user's data directory, and `ARCHITECTURE.md` recorded
the missing third source honestly: "an extensibility point with nothing
built on them yet ... a real gap, not silently dropped". This is that
third source.

**It lives in core rather than in the reaction_prediction plugin**, for
the same reason every other `PluginContext` namespace points at a core
service: a plugin must not have to import another plugin to extend it.
The bundled provider consumes this service; it does not own it.

**A template is data, not code.** It carries a name, a reaction SMARTS
and the id of whatever supplied it -- no callable, no RDKit. That keeps
this module free of the chemistry layer (`tests/test_layering.py`
enforces it for `services/`) and means a template can be logged,
exported or shown in a table without executing anything.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReactionTemplate:
    """One named reaction, as a SMARTS, and where it came from."""

    name: str
    smarts: str
    #: The plugin that registered it. **Carried, not derived**: a
    #: prediction has to be able to say which rule produced it, and two
    #: plugins may reasonably ship a template of the same name.
    source_id: str = ""

    @property
    def source_label(self) -> str:
        """What a prediction shows. ASCII, like every other label that
        reaches a result line -- see `Component.label` in
        `chem/substance.py` for why."""
        return f"{self.name} ({self.source_id})" if self.source_id else self.name


class ReactionTemplateService:
    """Holds the templates plugins have registered.

    Registration is per plugin so `unregister_source` can remove exactly
    what one plugin added when it unloads -- the same transactional
    unwind every other registrar gets.
    """

    def __init__(self) -> None:
        self._by_source: dict[str, list[ReactionTemplate]] = {}

    def register(self, source_id: str, templates: list[ReactionTemplate]) -> None:
        """Add templates for one plugin, replacing anything it registered
        before. Re-registering is how a plugin updates its set."""
        self._by_source[source_id] = [
            ReactionTemplate(name=t.name, smarts=t.smarts, source_id=source_id)
            for t in templates
        ]

    def unregister_source(self, source_id: str) -> None:
        self._by_source.pop(source_id, None)

    def all_templates(self) -> list[ReactionTemplate]:
        """Every registered template, in registration order.

        **Duplicate names are kept, not collapsed.** Two plugins may ship
        a template called "Esterification" with different SMARTS, and
        dropping one would silently lose a rule somebody installed. The
        provider already de-duplicates by PRODUCT, which is the level at
        which a duplicate actually matters to a reader.
        """
        return [t for templates in self._by_source.values() for t in templates]
