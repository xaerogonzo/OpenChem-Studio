"""Help contracts for the External Tools pages.

These pages carry one contract per control, built from the same descriptor
that built the control, so a tab's help cannot describe a different tool from
the one it sits on. The ids are per tool (`external_tools.vina_remove`) rather
than per concept, because the guard allows one id to carry exactly one text and
a Remove button that names what it deletes is more useful than one that says
"the tool".

Every contract here states what the action DOES and what it changes on disk or
in settings -- the things a user cannot tell from a label like "Re-check".
"""

from __future__ import annotations

from openchem.ui.widgets.help_tooltip import HelpTooltip

_TOPIC = "external_tools"
_ANCHOR = "settings"


def _tip(text: str, help_id: str, tier: int = 1) -> HelpTooltip:
    return HelpTooltip(
        text=text, tier=tier, help_id=help_id, topic=_TOPIC, help_anchor=_ANCHOR
    )


def setup_help(descriptor) -> HelpTooltip:
    """The button that fetches or builds the tool."""
    if not getattr(descriptor, "obtainable", True):
        return _tip(
            f"Not offered: {descriptor.title} cannot be downloaded by this app, so "
            "there is nothing to set up here. Use the vendor links instead.",
            f"external_tools.{descriptor.key}_setup",
        )
    return _tip(
        f"{descriptor.action_label.rstrip('.')}: asks you to confirm first, saying what "
        f"is fetched, from where and how big, then installs {descriptor.title} into "
        "OpenChem Studio's own tools folder and points the settings at it.",
        f"external_tools.{descriptor.key}_setup",
    )


def remove_help(descriptor) -> HelpTooltip:
    """The Remove from Disk button on a tool's own tab."""
    if not getattr(descriptor, "removable", True):
        return _tip(
            f"Not offered: {descriptor.title} was installed by you, not by this app, "
            "so this app does not delete it. Uninstall it the way you installed it.",
            f"external_tools.{descriptor.key}_remove",
        )
    return _tip(
        f"Deletes {descriptor.remove_label} and frees the space it uses. It asks you "
        "to confirm and lists the folders first; the tool can be set up again later.",
        f"external_tools.{descriptor.key}_remove",
    )


def recheck_help(descriptor) -> HelpTooltip:
    """Re-check on the tabs with no path field."""
    return _tip(
        f"Looks at the disk again and updates the status line for {descriptor.title}. "
        "Changes nothing; use it after installing or removing the tool by hand.",
        f"external_tools.{descriptor.key}_recheck",
    )


def path_help(descriptor, what: str) -> HelpTooltip:
    """The path field. `what` names what goes in it."""
    return _tip(
        f"The {what} for {descriptor.title}. It is saved when you leave the field, "
        "and the status line below it then reports whether it works. Clear it to "
        "stop using the tool.",
        f"external_tools.{descriptor.key}_path",
        tier=2,
    )


def browse_help(descriptor) -> HelpTooltip:
    """Browse next to the path field."""
    return _tip(
        f"Pick a folder; OpenChem Studio finds {descriptor.title} inside it and fills "
        "in the path. Pointing at the install or environment folder is enough.",
        f"external_tools.{descriptor.key}_browse",
    )


def locate_help(descriptor, hint: str) -> HelpTooltip:
    """Locate Installed."""
    return _tip(
        f"{hint} A found copy is written into the path field.",
        f"external_tools.{descriptor.key}_locate",
    )


def test_help(descriptor) -> HelpTooltip:
    """The Test button."""
    return _tip(
        f"Runs {descriptor.title} once to check that it really works, and reports the "
        "result on the status line. It changes no setting.",
        f"external_tools.{descriptor.key}_test",
    )


def vendor_link_help(descriptor, label: str, url: str) -> HelpTooltip:
    """A vendor page button on a tool this app cannot download."""
    slug = "download" if "get" in label.lower() else "docs"
    return _tip(
        f"Opens {url} in your browser. {descriptor.title} cannot be downloaded "
        "automatically, so this is the vendor's own page.",
        f"external_tools.{descriptor.key}_{slug}",
    )


STORAGE_MOVE = _tip(
    "Choose a new folder for everything OpenChem Studio installs; what is already "
    "there is moved and the settings follow. Across drives this copies then deletes, "
    "and can take a while.",
    "external_tools.storage_move",
)
STORAGE_RESET = _tip(
    "Moves the data back to the system default location (on Windows, the system "
    "drive) and clears the custom location from the settings. Disabled when the "
    "default is already in use.",
    "external_tools.storage_reset",
)
STORAGE_REFRESH = _tip(
    "Re-reads the location and re-measures every component's size on disk. Changes "
    "nothing.",
    "external_tools.storage_refresh",
)
STORAGE_REMOVE = _tip(
    "Deletes this component from disk after you confirm, freeing the size shown. "
    "Only components OpenChem Studio installed itself can be removed here.",
    "external_tools.storage_remove",
)
STORAGE_HEADERS = (
    _tip("The installed tool or environment this row describes.",
         "external_tools.storage_col_component"),
    _tip("How much disk space the component uses; measured after the tab opens, so "
         "it shows ... until then.", "external_tools.storage_col_size"),
    _tip("The Remove button for a component that is installed; empty when there is "
         "nothing to remove.", "external_tools.storage_col_remove"),
    _tip("What the component is, or why it cannot be removed here (for example it "
         "is yours rather than installed by this app).",
         "external_tools.storage_col_status"),
)
