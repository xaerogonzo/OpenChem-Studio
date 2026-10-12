"""Which calculators match a phrase -- one rule, for the launcher's Find box and the assistant.

The launcher's Find box matched a calculator on its name, description, heading and tags
(`PropertyPanel._find_matches`). A second search for the AI assistant would have started as a copy
of that and drifted from it the first time one was reworded, so the rule lives here and both call
it: what the assistant can find is what a person typing the same words finds.

**SUBSTRING, CASE-FOLDED, ALL WORDS.** A query of two words matches a calculator whose text holds
both, in any order, so "lewis adduct" and "adduct lewis" agree. (The Find box used the whole query
as one substring, which finds "lewis adduct" and misses "adduct lewis"; the single-phrase case is
unchanged.) An empty query matches everything, and a query nothing matches returns an empty list --
never a near miss, because a wrong calculator offered to a model is a wrong run.

**ORDER IS THE BROWSE ORDER**, `calculator_browse_sort_key`, so two calls give the same list and
it reads the way Properties is laid out.
"""

from __future__ import annotations

from collections.abc import Iterable

from openchem.domain.calculator_taxonomy import calculator_browse_sort_key, category_label


def search_text(definition) -> str:
    """The casefolded text a query is matched against."""
    return " ".join(
        [
            str(getattr(definition, "display_name", "") or ""),
            str(getattr(definition, "description", "") or ""),
            category_label(str(getattr(definition, "category", "") or "")),
            *(str(tag) for tag in (getattr(definition, "tags", None) or [])),
        ]
    ).casefold()


def matches(definition, query: str) -> bool:
    """True when every word of `query` is in the calculator's text. Empty matches all."""
    words = query.casefold().split()
    if not words:
        return True
    haystack = search_text(definition)
    return all(word in haystack for word in words)


def search(definitions: Iterable, query: str, limit: int | None = None) -> list:
    """The definitions matching `query`, in browse order, at most `limit`."""
    found = sorted((d for d in definitions if matches(d, query)), key=calculator_browse_sort_key)
    return found if limit is None else found[: max(0, limit)]
