"""One place that opens an HTTP connection, so every request this app
makes says who it is.

WHY THIS EXISTS. Adoptium's API sits behind Cloudflare, which rejects
Python's default `Python-urllib/3.13` User-Agent outright: HTTP 403, body
`error code: 1010`, and nothing anywhere in that response contains the
word "agent". The Java installer failed on exactly this, and it failed
after the download button was pressed, so it read as "the download is
broken" rather than "we never introduced ourselves". Any real name gets a
200 -- confirmed against the live endpoint, both with a browser-style
string and with the one below.

So this is not a workaround aimed at one host. Identifying the client is
what every request should have been doing, and one of the hosts here
(NCBI, for PubChem) asks for it in their usage policy so they can contact
whoever is hammering them. The other two (SourceForge, GitHub) accept the
default agent today, which is precisely why the omission went unnoticed
until a host that doesn't came along.

WHY IT LIVES AT THE PACKAGE ROOT. Callers span layers:
`chem/naming_providers.py` reaches PubChem, and `chem/` must not import
from `services/`. Same reason `paths.py` sits here.
"""

from __future__ import annotations

from typing import IO
from urllib.request import Request, urlopen

#: Contactable, and specific enough to be recognisable in a server log.
#: Sent on every request -- see the module docstring for why "no
#: User-Agent" is not a neutral default.
USER_AGENT = "OpenChemStudio/0.1.0 (+https://github.com/xaerogonzo/OpenChem-Studio)"


def open_url(url: str, timeout: float, headers: dict[str, str] | None = None) -> IO[bytes]:
    """`urlopen`, with this app's User-Agent attached.

    Callers pass their own `timeout` because the right one differs by
    two orders of magnitude here -- 25 s for a PubChem JSON lookup, 300 s
    for a 150 MB database.

    urllib carries request headers across redirects, so the agent
    survives the hop Adoptium makes to GitHub's release-asset host.
    """
    combined = {"User-Agent": USER_AGENT}
    combined.update(headers or {})
    return urlopen(Request(url, headers=combined), timeout=timeout)  # noqa: S310
