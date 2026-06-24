import importlib.util
import re
import tempfile
import xml.dom.minidom as minidom
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "atlas_demo", Path(__file__).resolve().parents[1] / "examples" / "atlas_demo.py")
demo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(demo)


def test_demo_renders_self_contained_two_layer_html():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp); demo.build_workspace(root); html = demo.render(root)
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert 'data-name="api"' in html and 'data-name="storage"' in html
    assert 'data-doc="docs/architecture.md"' in html
    assert "kedge-describes" in html
    assert "<link" not in html.lower() and "@import" not in html
    svg = re.search(r"<svg.*?</svg>", html, re.S)
    assert svg is not None
    minidom.parseString(svg.group(0))


def test_demo_is_path_independent_deterministic():
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        ra = Path(a); demo.build_workspace(ra); ha = demo.render(ra)
        rb = Path(b); demo.build_workspace(rb); hb = demo.render(rb)
    assert ha == hb
