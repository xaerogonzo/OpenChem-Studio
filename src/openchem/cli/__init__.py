"""The headless command line: OpenChem's calculators, asked from a script or an agent.

No window, no event loop, **no Qt**. It reaches the same registry the application
dispatches through (`CalculatorRegistry`, populated from
`chem.descriptor_providers.CALCULATOR_DEFINITIONS`) and does what
`DescriptorService`'s calculation task does around the call -- resolve the input
structure, compute, record which geometry and which parameters produced the result,
and map a refusal -- minus the events and the thread pool, which is all that task
adds. `tests/test_cli.py` proves the two agree, because two paths that are meant to
give the same answer are only the same until somebody changes one of them (the
calculator census exists for exactly that reason).

The contract (one JSON envelope on stdout, semantic exit codes, a side-effect class
per command) is the TokenSave Manager's `docs/AGENT_TOOL_CONTRACT.md`.
"""

REACHED_BY = (
    "console_script: entered by the `openchem-cli` script in pyproject.toml "
    "([project.scripts] -> openchem.cli.commands:main) or `python -m openchem.cli`, "
    "never by an import from openchem.main"
)
