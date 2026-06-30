# Index Agent Instructions

## Scope

Index is the Project Telos workspace atlas. Changes should improve repository
mapping, dependency evidence, context envelopes, architecture certificates, or
developer navigation.

## Developer Contract

- Every reported edge should be backed by source evidence where possible.
- Keep portable outputs free of absolute paths unless private-local mode is
  explicitly requested.
- Keep CLI, MCP, and Python API behavior aligned.
- Keep README, `USAGE.md`, `CHANGELOG.md`, and examples current when commands
  or output schemas change.

## Verification

Run the targeted slice for the touched surface first:

```bash
python -m pip install -e ".[test]"
python -m pytest
index status --json
index doctor --json
```

For delivery-surface changes, also run:

```bash
python -m public_surface_sweeper . --workspace --json
```
