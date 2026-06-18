# Workspace Repo Map

> Compact JSON repository inventory maps for multi-repo workspaces.

[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![python](https://img.shields.io/badge/python-3.11%2B-blue.svg)
![version](https://img.shields.io/badge/version-0.1.0-informational.svg)
[![CI](https://github.com/HarperZ9/workspace-repo-map/actions/workflows/ci.yml/badge.svg)](https://github.com/HarperZ9/workspace-repo-map/actions/workflows/ci.yml)
![deps: none](https://img.shields.io/badge/deps-none-success.svg)
[![part of: AI-accountability toolkit](https://img.shields.io/badge/part_of-AI--accountability_toolkit-7a5cff.svg)](https://harperz9.github.io)

`workspace-repo-map` scans a workspace root for Git repositories and writes a
compact JSON map of remotes, branches, dirty counts, marker files, and public or
local-only classification hints.

Generated maps are portable by default: repository paths are root-relative,
protected origins are omitted, and the local root is represented by a short hash.

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
- Repository names and branch details are exported from local git metadata.
- Absolute local root paths are not included by default.

---
**Zain Dana Harper** — small tools with explicit edges.
[Portfolio](https://harperz9.github.io) · [HarperZ9](https://github.com/HarperZ9)
<sub>Built with Claude Code; reviewed, tested, and owned by me.</sub>
