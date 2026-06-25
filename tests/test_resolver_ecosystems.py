from pathlib import Path

from index_graph.graph.build import build_graph
from index_graph.graph.resolvers import ALL_RESOLVERS

FIX = Path(__file__).parent / "fixtures"


def test_new_resolvers_registered():
    names = {r.name for r in ALL_RESOLVERS}
    assert {"csharp", "ruby", "php", "cpp"} <= names


def test_csharp_cross_repo_edge():
    g = build_graph({"App": FIX / "csharp-app", "Lib": FIX / "csharp-lib"})
    assert any(e.from_repo == "App" and e.to_repo == "Lib" for e in g.edges)


def test_ruby_cross_repo_edge():
    g = build_graph({"ruby-app": FIX / "ruby-app", "ruby-lib": FIX / "ruby-lib"})
    assert any(e.to_repo == "ruby-lib" for e in g.edges if not e.external)


def test_php_cross_repo_edge():
    g = build_graph({"org-app": FIX / "php-app", "org-lib": FIX / "php-lib"})
    assert any(e.to_repo == "org-lib" for e in g.edges if not e.external)


def test_cpp_cross_repo_edge():
    g = build_graph({"app": FIX / "cpp-app", "cpp-lib": FIX / "cpp-lib"})
    assert any(e.to_repo == "cpp-lib" for e in g.edges if not e.external)


# --- regression tests for the 2.6.0 review fixes ---


def test_csharp_matches_walks_fail_closed(tmp_path):
    """matches() must use the fail-closed walk, not rglob (rglob crashes the graph
    build on a permission-denied subdir). A .csproj nested in a subdir still matches."""
    from index_graph.graph.resolvers.csharp import CSharpResolver
    proj = tmp_path / "sub"
    proj.mkdir()
    (proj / "App.csproj").write_text("<Project></Project>", encoding="utf-8")
    assert CSharpResolver().matches(tmp_path) is True
    assert CSharpResolver().matches(tmp_path / "nonexistent") is False


def test_cpp_multiline_target_link_libraries(tmp_path):
    """target_link_libraries spread across lines: every lib captured, keywords skipped."""
    from index_graph.graph.resolvers.cpp import CppResolver
    (tmp_path / "CMakeLists.txt").write_text(
        "project(app)\n"
        "add_executable(app main.cpp)\n"
        "target_link_libraries(app\n"
        "    PRIVATE foo\n"
        "    bar)\n",
        encoding="utf-8",
    )
    libs = {e.target_name for e in CppResolver().raw_edges(tmp_path) if e.signal == "manifest"}
    assert "foo" in libs
    assert "bar" in libs
    assert "PRIVATE" not in libs


def test_cpp_single_line_target_link_libraries(tmp_path):
    """The single-line form still resolves exactly its libs after the multi-line rewrite."""
    from index_graph.graph.resolvers.cpp import CppResolver
    (tmp_path / "CMakeLists.txt").write_text(
        "target_link_libraries(app PUBLIC foo bar)\n", encoding="utf-8"
    )
    libs = {e.target_name for e in CppResolver().raw_edges(tmp_path) if e.signal == "manifest"}
    assert libs == {"foo", "bar"}


def test_cpp_exposed_names_strip_trailing_paren(tmp_path):
    """project()/add_library()/add_executable() names must not carry a trailing ')'."""
    from index_graph.graph.resolvers.cpp import CppResolver
    (tmp_path / "CMakeLists.txt").write_text(
        "project(myapp)\nadd_library(mylib STATIC a.cpp)\n", encoding="utf-8"
    )
    names = CppResolver().exposed_names(tmp_path)
    assert "myapp" in names
    assert "mylib" in names
    assert not any(")" in n for n in names)


def test_php_use_function_and_const_capture_namespace(tmp_path):
    """`use function Ns\\fn;` / `use const Ns\\C;` are dependencies on Ns, not on the
    'function'/'const' keyword, and must not be dropped. All three use-forms here
    resolve to the Vendor namespace, so three import edges all targeting Vendor."""
    from index_graph.graph.resolvers.php import PhpResolver
    (tmp_path / "composer.json").write_text('{"name": "org/app"}', encoding="utf-8")
    (tmp_path / "app.php").write_text(
        "<?php\nuse Vendor\\Thing;\nuse function Vendor\\helper;\nuse const Vendor\\MAX;\n",
        encoding="utf-8",
    )
    imports = [e for e in PhpResolver().raw_edges(tmp_path) if e.signal == "import"]
    targets = {e.target_name for e in imports}
    assert targets == {"Vendor"}        # every use-line is a dependency on Vendor
    assert "function" not in targets    # the keyword is never the target
    assert "const" not in targets
    assert len(imports) == 3            # no line dropped (old code captured only 1)


def test_php_namespace_starting_with_function_keyword(tmp_path):
    """A namespace that merely starts with 'function' must not be read as the keyword."""
    from index_graph.graph.resolvers.php import PhpResolver
    (tmp_path / "composer.json").write_text('{"name": "org/app"}', encoding="utf-8")
    (tmp_path / "app.php").write_text(
        "<?php\nuse functional\\Pipe;\n", encoding="utf-8"
    )
    targets = {e.target_name for e in PhpResolver().raw_edges(tmp_path) if e.signal == "import"}
    assert targets == {"functional"}
