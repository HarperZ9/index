from pathlib import Path

from index_graph.internals import build_internals


def _w(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_js_relative_import_edge(tmp_path):
    _w(tmp_path, "src/a.js", "import { f } from './b';\n")
    _w(tmp_path, "src/b.js", "export const f = 1;\n")
    g = build_internals(tmp_path, "app")
    assert ("src/a", "src/b") in {(e.from_id, e.to_id) for e in g.edges}


def test_js_bare_import_is_external(tmp_path):
    _w(tmp_path, "src/a.js", "import React from 'react';\n")
    g = build_internals(tmp_path, "app")
    assert g.edges == ()


def test_ts_parent_relative_import(tmp_path):
    _w(tmp_path, "src/feat/a.ts", "import { f } from '../util/b';\n")
    _w(tmp_path, "src/util/b.ts", "export const f = 1;\n")
    g = build_internals(tmp_path, "app")
    assert ("src/feat/a", "src/util/b") in {(e.from_id, e.to_id) for e in g.edges}


def test_go_internal_package_edge(tmp_path):
    _w(tmp_path, "go.mod", "module example.com/app\n\ngo 1.21\n")
    _w(tmp_path, "main.go", 'package main\nimport "example.com/app/util"\n')
    _w(tmp_path, "util/util.go", "package util\n")
    g = build_internals(tmp_path, "app")
    assert any(e.to_id.startswith("util") for e in g.edges)


def test_rust_mod_declaration_edge(tmp_path):
    _w(tmp_path, "src/main.rs", "mod helpers;\nfn main() {}\n")
    _w(tmp_path, "src/helpers.rs", "pub fn h() {}\n")
    g = build_internals(tmp_path, "app")
    assert ("src/main", "src/helpers") in {(e.from_id, e.to_id) for e in g.edges}
