import ast
import sys
from pathlib import Path

VIZ_DIR = Path(__file__).resolve().parents[1] / "src" / "index_graph" / "viz"
PRIVATE_ORGANS = {"statechain", "provenance", "ledger", "coherence_membrane"}
STDLIB = set(sys.stdlib_module_names)


def _imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module.split(".")[0]


def test_boundary_scan_is_not_vacuous():
    files = list(VIZ_DIR.glob("*.py"))
    assert len(files) >= 6, f"VIZ_DIR resolved to {VIZ_DIR} with only {len(files)} .py files — scan would be vacuous"


def test_no_viz_module_imports_a_private_organ():
    for path in VIZ_DIR.glob("*.py"):
        assert PRIVATE_ORGANS.isdisjoint(set(_imports(path))), path.name


def test_viz_imports_only_stdlib_or_own_package():
    allowed = STDLIB | {"index_graph"}
    for path in VIZ_DIR.glob("*.py"):
        for mod in _imports(path):
            assert mod in allowed, f"{path.name} imports third-party {mod!r}"
