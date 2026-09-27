"""Every place the version is written agrees with index_graph.__version__.

The version lives in three files: the package, the README status line and the
CHANGELOG heading. The build reads it from the package, so a bump that misses the
README or the CHANGELOG still builds. These checks fail when one drifts, and the
release workflow runs them before it builds, so a half-bumped tree never ships.
"""
import re
from pathlib import Path

from index_graph import __version__

ROOT = Path(__file__).resolve().parents[1]


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_readme_status_line_matches_the_package():
    assert f"`index-graph` {__version__}, command `index`" in _read("README.md")


def test_no_readme_status_line_names_a_different_version():
    # A second status line for another version would slip past the exact check.
    for found in re.findall(r"`index-graph` (\d+\.\d+\.\d+)", _read("README.md")):
        assert found == __version__, f"README names {found}, package is {__version__}"


def test_changelog_has_a_dated_heading_for_the_package_version():
    assert re.search(rf"^## {re.escape(__version__)} \(\d{{4}}-\d{{2}}-\d{{2}}\)$",
                     _read("CHANGELOG.md"), re.M)


def test_the_package_version_is_the_newest_changelog_release():
    # The first dated heading below "Unreleased" is the version being shipped.
    headings = re.findall(r"^## (\d+\.\d+\.\d+) \(", _read("CHANGELOG.md"), re.M)
    assert headings and headings[0] == __version__, \
        f"newest CHANGELOG release is {headings[:1]}, package is {__version__}"


def test_the_build_reads_the_version_from_the_package():
    # The release workflow and hatch both read this one line; a second source of
    # truth in pyproject.toml would let the two disagree.
    pyproject = _read("pyproject.toml")
    assert 'dynamic = ["version"]' in pyproject
    assert 'path = "src/index_graph/__init__.py"' in pyproject
    init = _read("src/index_graph/__init__.py")
    assert re.findall(r'^__version__ = "([^"]+)"$', init, re.M) == [__version__]
