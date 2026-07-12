# Topology-Aware Repository Discovery Implementation Plan

> **For Codex:** Use `superpowers:subagent-driven-development` to execute this plan task by task. Apply `superpowers:test-driven-development` to every production change and `superpowers:verification-before-completion` before any completion or publication claim.

**Goal:** Make Index report each physical repository once and reject copied linked-worktree pointers, without losing valid linked worktrees, submodules, separate Git directories, sole aliases, or mid-flight repositories.

**Architecture:** Keep topology validation at the `discover_repos()` boundary so the CLI, MCP server, Python API, map, graph, freshness, and doctor surfaces consume the same repository set. Filesystem canonical identity collapses duplicate junction/symlink views. A linked-worktree administrative backlink distinguishes a registered worktree from a copied `.git` pointer. The existing output schema and configuration remain unchanged.

**Tech stack:** Python 3.11+, standard library, pytest, Git CLI for final workspace verification.

**Branch:** `C:\dev\public\index` is already isolated on `feat/topology-aware-discovery`.

## Constraints

- Add no runtime dependency, configuration key, JSON field, or public `index_graph.__all__` export.
- Never deduplicate by origin URL, HEAD, branch, repository name, or common Git directory.
- Accept malformed or empty gitfiles, submodules, and separate-git-dir layouts unless a linked-worktree backlink positively identifies a mismatch.
- Preserve a sole junction or symlink mount. Collapse only two or more candidates with the same physical identity.
- Prefer the direct physical path over an alias, then use case-insensitive lexical order for determinism.
- Warn when a copied or moved linked worktree is omitted and name `git worktree repair` as the recovery action.
- Do not write `C:\dev\INDEX.json` during verification; use JSON stdout.

## Task 0: Commit the plan and capture the existing public-surface baseline

```powershell
cd C:\dev\public\index
git add -- docs/superpowers/plans/2026-07-12-topology-aware-repository-discovery.md
git diff --cached --check
git commit -m "docs: plan topology-aware repository discovery"

$env:PYTHONPATH = 'C:\dev\public\proof-surface\src;C:\dev\public\public-surface-sweeper\src'
python -m public_surface_sweeper . --workspace --json | Set-Content -LiteralPath C:\tmp\index-topology-sweep-before.json -Encoding utf8
```

The verified pre-change sweeper baseline is one existing `readme-developer-delivery` warning. This change must introduce no new finding; it does not silently relabel that pre-existing warning as `MATCH`.

## Internal interfaces

These helpers remain module-local APIs and are not re-exported:

```python
# src/index_graph/gitmeta.py
def canonical_path_identity(path: Path) -> str: ...
def gitfile_backlink_matches(repo: Path) -> bool: ...

# src/index_graph/scan.py
def deduplicate_repo_aliases(repos: Iterable[Path]) -> list[Path]: ...
```

## Task 1: Validate linked-worktree gitfile backlinks

**Files:**

- Modify: `C:\dev\public\index\src\index_graph\gitmeta.py`
- Modify tests: `C:\dev\public\index\tests\test_gitmeta.py`

### Step 1: Write the failing tests

Add `import os` and `import index_graph.gitmeta as gitmeta`, then add a fixture and tests covering registered, copied, relative, submodule/separate-git-dir, malformed, and canonicalization-fallback behavior:

```python
def _linked_worktree_fixture(tmp_path: Path) -> tuple[Path, Path]:
    admin = tmp_path / "main" / ".git" / "worktrees" / "feature"
    admin.mkdir(parents=True)
    (admin / "commondir").write_text("../..\n", encoding="utf-8")
    linked = tmp_path / "worktrees" / "feature"
    linked.mkdir(parents=True)
    (linked / ".git").write_text(f"gitdir: {admin}\n", encoding="utf-8")
    (admin / "gitdir").write_text(f"{linked / '.git'}\n", encoding="utf-8")
    return linked, admin


def test_gitfile_backlink_matches_registered_linked_worktree(tmp_path: Path):
    linked, _ = _linked_worktree_fixture(tmp_path)
    assert gitmeta.gitfile_backlink_matches(linked)


def test_gitfile_backlink_rejects_copied_linked_worktree(tmp_path: Path):
    linked, _ = _linked_worktree_fixture(tmp_path)
    copied = tmp_path / "audit" / "source"
    copied.mkdir(parents=True)
    (copied / ".git").write_text(
        (linked / ".git").read_text(encoding="utf-8"), encoding="utf-8"
    )
    assert not gitmeta.gitfile_backlink_matches(copied)


def test_gitfile_backlink_resolves_relative_paths(tmp_path: Path):
    linked, admin = _linked_worktree_fixture(tmp_path)
    (linked / ".git").write_text(
        f"gitdir: {os.path.relpath(admin, linked)}\n", encoding="utf-8"
    )
    (admin / "gitdir").write_text(
        f"{os.path.relpath(linked / '.git', admin)}\n", encoding="utf-8"
    )
    assert gitmeta.gitfile_backlink_matches(linked)


def test_gitfile_without_worktree_backlink_is_accepted(tmp_path: Path):
    admin = tmp_path / "super" / ".git" / "modules" / "sub"
    admin.mkdir(parents=True)
    submodule = tmp_path / "super" / "sub"
    submodule.mkdir()
    (submodule / ".git").write_text(f"gitdir: {admin}\n", encoding="utf-8")
    assert gitmeta.gitfile_backlink_matches(submodule)


def test_empty_gitfile_marker_is_accepted(tmp_path: Path):
    (tmp_path / ".git").write_text("", encoding="utf-8")
    assert gitmeta.gitfile_backlink_matches(tmp_path)


def test_malformed_gitfile_marker_is_accepted(tmp_path: Path):
    (tmp_path / ".git").write_text("not a gitdir record\n", encoding="utf-8")
    assert gitmeta.gitfile_backlink_matches(tmp_path)


def test_separate_git_dir_with_unrelated_gitdir_file_is_accepted(tmp_path: Path):
    repo = tmp_path / "separate"
    repo.mkdir()
    admin = tmp_path / "admin"
    admin.mkdir()
    (repo / ".git").write_text(f"gitdir: {admin}\n", encoding="utf-8")
    (admin / "gitdir").write_text("an unrelated file\n", encoding="utf-8")
    assert gitmeta.gitfile_backlink_matches(repo)


def test_canonical_identity_falls_back_when_realpath_fails(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(os.path, "realpath", lambda _path: (_ for _ in ()).throw(OSError("nope")))
    assert gitmeta.canonical_path_identity(tmp_path) == os.path.normcase(os.path.abspath(tmp_path))
```

### Step 2: Prove RED

```powershell
cd C:\dev\public\index
python -m pytest tests\test_gitmeta.py -q
```

Expected: ordinary pytest failures/`AttributeError` because `canonical_path_identity()` and `gitfile_backlink_matches()` do not exist. A collection error is not acceptable RED; correct the test module first.

### Step 3: Implement the minimum topology helpers

Add `import os` and implement:

```python
def canonical_path_identity(path: Path) -> str:
    absolute = os.path.abspath(path)
    try:
        physical = os.path.realpath(absolute)
    except OSError:
        physical = absolute
    return os.path.normcase(physical)


def _recorded_path(raw: str, base: Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else base / path


def _gitfile_target(gitfile: Path) -> Path | None:
    try:
        text = gitfile.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    prefix, separator, raw = text.partition(":")
    if separator != ":" or prefix.casefold() != "gitdir" or not raw.strip():
        return None
    return _recorded_path(raw.strip(), gitfile.parent)


def gitfile_backlink_matches(repo: Path) -> bool:
    gitfile = repo / ".git"
    if not gitfile.is_file():
        return True
    admin = _gitfile_target(gitfile)
    if admin is None:
        return True
    backlink = admin / "gitdir"
    commondir = admin / "commondir"
    if not commondir.is_file() or not backlink.is_file():
        return True
    try:
        raw = backlink.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return True
    if not raw:
        return True
    registered_gitfile = _recorded_path(raw, backlink.parent)
    return canonical_path_identity(gitfile) == canonical_path_identity(registered_gitfile)
```

The `commondir` requirement is intentional: reject only a positive linked-worktree backlink mismatch. A normal submodule or separate Git directory fails open even if an unrelated file named `gitdir` exists.

### Step 4: Prove GREEN

```powershell
python -m pytest tests\test_gitmeta.py -q
```

Expected: all `test_gitmeta.py` tests pass.

### Step 5: Commit the vertical slice

```powershell
git add -- src/index_graph/gitmeta.py tests/test_gitmeta.py
git diff --cached --check
git commit -m "fix: validate linked worktree gitfiles"
```

## Task 2: Deduplicate physical aliases during discovery

**Files:**

- Modify: `C:\dev\public\index\src\index_graph\scan.py`
- Modify tests: `C:\dev\public\index\tests\test_scan.py`

### Step 1: Write the failing tests

Add `import os`, `import subprocess`, `import pytest`, and `import index_graph.scan as scan_mod`. Add:

```python
def _make_directory_alias(alias: Path, target: Path) -> None:
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(alias), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            pytest.skip(f"junction creation unavailable: {result.stderr}")
    else:
        alias.symlink_to(target, target_is_directory=True)


def _linked_worktree_and_copy(root: Path) -> tuple[Path, Path, Path]:
    main = root / "main"
    admin = main / ".git" / "worktrees" / "feature"
    admin.mkdir(parents=True)
    (admin / "commondir").write_text("../..\n", encoding="utf-8")
    linked = root / "worktrees" / "feature"
    linked.mkdir(parents=True)
    (linked / ".git").write_text(f"gitdir: {admin}\n", encoding="utf-8")
    (admin / "gitdir").write_text(f"{linked / '.git'}\n", encoding="utf-8")
    copied = root / "audit" / "source"
    copied.mkdir(parents=True)
    (copied / ".git").write_text(f"gitdir: {admin}\n", encoding="utf-8")
    return main, linked, copied


def test_deduplicate_repo_aliases_prefers_direct_path(tmp_path: Path):
    target = tmp_path / "z-target"
    _make_repo(target)
    alias = tmp_path / "a-alias"
    _make_directory_alias(alias, target)
    assert scan_mod.deduplicate_repo_aliases([alias, target]) == [target]


def test_deduplicate_repo_aliases_keeps_sole_alias(tmp_path: Path):
    target = tmp_path / "target"
    _make_repo(target)
    alias = tmp_path / "alias"
    _make_directory_alias(alias, target)
    assert scan_mod.deduplicate_repo_aliases([alias]) == [alias]


def test_deduplicate_repo_aliases_collapses_mocked_physical_identity(
    tmp_path: Path, monkeypatch
):
    direct = tmp_path / "direct"
    alias = tmp_path / "alias"
    _make_repo(direct)
    _make_repo(alias)
    monkeypatch.setattr(scan_mod, "canonical_path_identity", lambda _path: "same")
    monkeypatch.setattr(
        scan_mod,
        "_alias_rank",
        lambda path: (path == alias, str(path).casefold(), str(path)),
    )
    assert scan_mod.deduplicate_repo_aliases([alias, direct]) == [direct]


def test_discover_skips_copied_worktree_gitfile(tmp_path: Path):
    main, linked, _ = _linked_worktree_and_copy(tmp_path)
    assert discover_repos(tmp_path, Config()) == [main, linked]


def test_discover_warns_when_copied_worktree_gitfile_is_skipped(tmp_path: Path, capsys):
    _linked_worktree_and_copy(tmp_path)
    discover_repos(tmp_path, Config())
    warning = capsys.readouterr().err
    assert "skipped unregistered linked-worktree copy audit/source" in warning
    assert "git worktree repair" in warning


def test_discover_reports_physical_repo_tree_once(tmp_path: Path):
    target = tmp_path / "z-target"
    _make_repo(target)
    _make_repo(target / "nested")
    alias = tmp_path / "a-alias"
    _make_directory_alias(alias, target)
    found = [path.relative_to(tmp_path).as_posix() for path in discover_repos(tmp_path, Config())]
    assert found == ["z-target", "z-target/nested"]


def test_build_map_does_not_double_count_physical_alias_dirty_state(
    tmp_path: Path, monkeypatch
):
    direct = tmp_path / "direct"
    subprocess.run(["git", "init", "-b", "main", str(direct)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(direct), "config", "user.email", "t@t.t"], check=True)
    subprocess.run(["git", "-C", str(direct), "config", "user.name", "t"], check=True)
    tracked = direct / "tracked.txt"
    tracked.write_text("before\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(direct), "add", "tracked.txt"], check=True)
    subprocess.run(["git", "-C", str(direct), "commit", "-m", "initial"], check=True, capture_output=True)
    tracked.write_text("after\n", encoding="utf-8")

    alias = tmp_path / "alias"
    _make_repo(alias)
    monkeypatch.setattr(scan_mod, "canonical_path_identity", lambda _path: "same")
    monkeypatch.setattr(
        scan_mod,
        "_alias_rank",
        lambda path: (path == alias, str(path).casefold(), str(path)),
    )

    result = build_map(tmp_path, Config(), "test")
    assert result.repo_count == 1
    assert result.dirty_count == 1
```

### Step 2: Prove RED

```powershell
python -m pytest tests\test_scan.py -q
```

Expected: `deduplicate_repo_aliases` is absent and the copied audit path is still returned.

### Step 3: Implement deterministic physical deduplication

Add `import os`, `from collections.abc import Iterable`, and import the two new gitmeta helpers. Implement:

```python
def _alias_rank(path: Path) -> tuple[bool, str, str]:
    lexical = os.path.normcase(os.path.abspath(path))
    return (lexical != canonical_path_identity(path), lexical, str(path))


def deduplicate_repo_aliases(repos: Iterable[Path]) -> list[Path]:
    selected: dict[str, Path] = {}
    for repo in repos:
        identity = canonical_path_identity(repo)
        incumbent = selected.get(identity)
        if incumbent is None or _alias_rank(repo) < _alias_rank(incumbent):
            selected[identity] = repo
    return sorted(selected.values(), key=lambda path: (str(path).casefold(), str(path)))
```

At the end of `discover_repos()`, validate every candidate before deduplication:

```python
    valid: list[Path] = []
    for repo in repos:
        if not gitfile_backlink_matches(repo):
            rel = _relative(repo, root)
            _warn(
                "warning: skipped unregistered linked-worktree copy "
                f"{rel}; run 'git worktree repair' if this worktree was moved intentionally"
            )
            continue
        valid.append(repo)
    return deduplicate_repo_aliases(valid)
```

### Step 4: Prove GREEN and guard compatibility

```powershell
python -m pytest tests\test_gitmeta.py tests\test_scan.py -q
```

Expected: all targeted tests pass; registered worktrees, separate git dirs, malformed markers, sole aliases, and nested repositories remain represented.

### Step 5: Commit the vertical slice

```powershell
git add -- src/index_graph/scan.py tests/test_scan.py
git diff --cached --check
git commit -m "fix: deduplicate repository topology during discovery"
```

## Task 3: Document the corrected discovery contract

**Files:**

- Modify: `C:\dev\public\index\USAGE.md`
- Modify: `C:\dev\public\index\CHANGELOG.md`

### Step 1: Update usage documentation

Add this paragraph to the repository-map scan/configuration section:

> Repository discovery resolves physical path identity before Git status fan-out. If both a directory and its junction or symbolic-link alias are visible beneath the scan root, Index reports the direct directory once. Registered linked worktrees remain independent repositories. A copied linked-worktree `.git` pointer whose administrative backlink names another path is skipped with a warning and a `git worktree repair` hint.

### Step 2: Add an Unreleased entry

```markdown
## Unreleased

- Repository discovery now removes duplicate physical aliases and ignores
  copied linked-worktree gitfiles whose registration backlink names another
  path, while retaining registered worktrees, submodules, and sole aliases.
```

### Step 3: Run the complete verification gate

```powershell
python -m pip install -e ".[test]"
python -m pytest
git diff --check

$Status = index status --json | ConvertFrom-Json
$Doctor = index doctor --json | ConvertFrom-Json
if ($Status.status -ne 'MATCH') { throw "index status is $($Status.status)" }
if ($Doctor.status -ne 'MATCH') { throw "index doctor is $($Doctor.status)" }

$env:PYTHONPATH = 'C:\dev\public\proof-surface\src;C:\dev\public\public-surface-sweeper\src'
$BeforeSweep = Get-Content -LiteralPath C:\tmp\index-topology-sweep-before.json -Raw | ConvertFrom-Json
$AfterSweep = python -m public_surface_sweeper . --workspace --json | ConvertFrom-Json
$BeforeRules = @($BeforeSweep.repositories[0].findings.rules.PSObject.Properties.Name)
$AfterRules = @($AfterSweep.repositories[0].findings.rules.PSObject.Properties.Name)
$NewRules = @(Compare-Object $BeforeRules $AfterRules | Where-Object SideIndicator -eq '=>')
if ($NewRules.Count -gt 0) { throw "new public-surface findings: $($NewRules.InputObject -join ', ')" }
if ($AfterSweep.repositories[0].findings.warnings -gt $BeforeSweep.repositories[0].findings.warnings) {
    throw 'public-surface warning count increased'
}
```

Expected: test suite green, Index status/doctor `MATCH`, and no new public-surface finding or warning above the recorded baseline.

### Step 4: Dogfood against `C:\dev` without writing a map

```powershell
$map = index map --root C:\dev --config C:\dev\.repomap.toml --json | ConvertFrom-Json
$paths = @($map.repositories.path | ForEach-Object { $_.Replace('\', '/').ToLowerInvariant() })

$required = @(
    'c:/dev/opsec',
    'c:/dev/opsec/kun',
    'c:/dev/opsec/sofer',
    'c:/dev/protected/legacy-repos/apps/calibrate-pro',
    'c:/dev/worktrees/calibrate-pro-1.1-pyside'
)
$forbidden = @(
    'c:/dev/aleph',
    'c:/dev/aleph/kun',
    'c:/dev/aleph/sofer',
    'c:/dev/release-audits/calibrate-wheel-audit-20260711-1528/source'
)

foreach ($path in $required) {
    if ($path -notin $paths) { throw "missing required repository: $path" }
}
foreach ($path in $forbidden) {
    if ($path -in $paths) { throw "unexpected duplicate repository: $path" }
}
"topology assertions passed; repos=$($map.repo_count) dirty=$($map.dirty_count)"
```

Record the before/after map counts in the implementation receipt. Do not hard-code them as a correctness assertion; concurrent workspace activity may legitimately change them.

### Step 5: Commit documentation

```powershell
git add -- USAGE.md CHANGELOG.md
git diff --cached --check
git commit -m "docs: document topology-aware repository discovery"
git status --short --branch
```

## Execution order and review

Execute Tasks 1–3 sequentially because each consumes the previous task's contract. After every commit, review the staged scope and rerun that task's targeted tests. Do not merge or push until the full verification and `C:\dev` dogfood assertions pass.
