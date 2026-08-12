"""Worked example: contributing reaction templates from a plugin.

`context.reactions.register([...])` is the one plugin namespace that had no
worked example -- it was covered by tests including an end-to-end one, but
nothing a third party could read and copy, which ARCHITECTURE.md recorded as
an open gap. This is that example.

THREE THINGS THIS DEMONSTRATES, and the third is the one that is easy to get
wrong:

1. **Register a LIST, once.** `register` takes a list rather than one
   template at a time because a reaction-SMARTS library is data that grows;
   thirty rules should be one call and one rollback, not thirty of each.

2. **The templates go into the SAME pool the bundled provider draws from.**
   `RDKitTemplateProvider` reads `all_templates()` on every prediction, so a
   registered template is applied by the shipped reaction plugin without
   either one knowing about the other. Read access to the namespace is
   deliberate for exactly this reason -- a write-only registration namespace
   would be unusable by the one plugin that needs it.

3. **Deactivation removes them.** Nothing here does that by hand:
   `_ReactionTemplateRegistrar` records a rollback at registration time and
   the plugin loader runs it, so `deactivate` staying empty is the point
   rather than an omission.

THE SMARTS ARE DELIBERATELY SMALL AND ORDINARY. This is an example of the
API, not a reaction-chemistry library -- three textbook transformations,
each with a substrate small enough to check by eye. `tests/
test_reaction_templates_example_plugin.py` applies every one of them and
asserts the product, because a template that parses and matches nothing
would demonstrate nothing while looking correct.
"""

from __future__ import annotations

from openchem.plugins.context import PluginContext
from openchem.plugins.interfaces import Plugin
from openchem.services.reaction_template_service import ReactionTemplate

#: Reaction SMARTS, `reactants>>products`, with mapped atoms carrying
#: identity across the arrow.
#:
#: **NONE OF THESE DUPLICATES A BUNDLED TEMPLATE, and that is a deliberate
#: choice rather than a coincidence.** `reaction_templates.json` already
#: ships Fischer esterification and amide coupling, which were the obvious
#: first picks for an example and are the wrong ones twice over: a plugin
#: re-registering chemistry the app already has demonstrates nothing a
#: reader wants to copy, and `RDKitTemplateProvider` de-duplicates products
#: across templates in file-then-registered order, so the bundled rule
#: reaches the answer first and the example's own template is invisible in
#: the output. An example whose contribution cannot be seen is not one.
#:
#: One two-reactant rule is included on purpose: reactant roles in a SMARTS
#: template are positional, and the provider tries every ordering so a
#: caller need not know which.
TEMPLATES: list[ReactionTemplate] = [
    ReactionTemplate(
        name="Primary alcohol oxidation",
        smarts="[CX4;H2:1][OX2H1:2]>>[CX3:1]=[O:2]",
    ),
    ReactionTemplate(
        name="Nitro reduction",
        smarts="[#6:1][N+](=[O])[O-]>>[#6:1][NX3H2]",
    ),
    ReactionTemplate(
        name="Williamson ether synthesis",
        smarts="[CX4:1][Cl,Br,I].[OX2H1:2][CX4:3]>>[CX4:1][O:2][CX4:3]",
    ),
]


class ReactionTemplatesPlugin(Plugin):
    def activate(self, context: PluginContext) -> None:
        context.reactions.register(TEMPLATES)
        context.logger.info(
            "reaction_templates_plugin registered %d templates", len(TEMPLATES)
        )

    def deactivate(self) -> None:
        """Deliberately empty -- see point 3 in the module docstring.

        The registrar recorded a rollback when `register` was called and the
        loader runs it on unload. Unregistering here as well would be a
        second, divergent copy of that logic.
        """


def create_plugin() -> Plugin:
    return ReactionTemplatesPlugin()
