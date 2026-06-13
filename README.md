# workspace-repo-map

`workspace-repo-map` scans a workspace root for Git repositories and writes a
compact JSON map of remotes, branches, dirty counts, marker files, and public or
local-only classification hints.

## Install

```bash
python -m pip install workspace-repo-map
```

## Usage

```bash
workspace-repo-map --root C:\dev --output WORKSPACE-REPO-MAP.json
workspace-repo-map --json
```

## Notes

- This CLI is agent assisted. Review output before sharing it in public.
- Repository names and branch details are exported as-is from local git metadata.
