"""Holds the plugin-supplied `AtomFactProvider`s.

Deliberately tiny. It exists so the Atom Inspector does not have to know
which plugins are loaded, and so plugin registration goes through the
same `register_provider`/`unregister_provider` pair every other provider
type already uses -- `PluginContext`'s registrars are all the same three
lines, and a service with a different shape would need a special one.

There is no compute here on purpose. Facts are gathered by
`chem.atom_report.build_atom_report`, which is a pure function of the
molecule and whatever results were handed to it; this class only answers
"who else has something to say".
"""

from __future__ import annotations

from openchem.plugins.interfaces import AtomFactProvider


class AtomFactService:
    def __init__(self, providers: list[AtomFactProvider] | None = None) -> None:
        self._providers: list[AtomFactProvider] = list(providers or [])

    def register_provider(self, provider: AtomFactProvider) -> None:
        self._providers.append(provider)

    def unregister_provider(self, provider_id: str) -> None:
        self._providers = [p for p in self._providers if p.provider_id != provider_id]

    def providers(self) -> tuple[AtomFactProvider, ...]:
        """A snapshot, so a provider registering while a report is being
        built cannot mutate the list mid-iteration."""
        return tuple(self._providers)
