# workspace-repo-map

`workspace-repo-map` was renamed to `index-graph`. The command is `index`.

```bash
pip install index-graph
index --help
```

This folder holds the source of the last `workspace-repo-map` release on PyPI, 0.2.1.
That release contains one module. Importing `workspace_repo_map` raises a
`DeprecationWarning` that names `index-graph`, and nothing else happens. It has no
command and no dependencies.

The source sat in a local folder with no remote until 2026-11-14. It is kept here so the
published package has a public source next to the project it points to.

## If you still have the old name installed

1. `pip uninstall workspace-repo-map`
2. `pip install index-graph`
3. Replace `workspace-repo-map --root <dir>` with `index map --root <dir>`. A bare
   `index --root <dir>` still writes the map.

## Building it

The `index-graph` wheel and sdist leave this folder out. To rebuild the 0.2.1 package,
run `python -m build` from this folder.

## Licence

The 0.2.1 package metadata declares no licence, and 0.2.0 was published as MIT. Inside
this repository the folder sits under the licence at the repository root.
