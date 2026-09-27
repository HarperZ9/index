"""The release workflow: least-privilege jobs, tests before the build, a tag that
matches the package, a re-runnable PyPI upload, and a GitHub Release that carries
the wheel, the sdist and SHA256SUMS.txt once PyPI serves those same files.

Read as text: the test extras carry no YAML parser.
"""
import re
from pathlib import Path

# PyPI's publisher settings name this file; renaming it breaks publishing.
WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release-artifacts.yml"


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _top_level(text: str) -> dict[str, str]:
    blocks, key = {}, None
    for line in text.splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*):(.*)$", line)
        if m:
            key = m.group(1)
            blocks[key] = m.group(2).strip() + "\n"
        elif key:
            blocks[key] += line + "\n"
    return blocks


def _jobs(text: str) -> dict[str, str]:
    blocks, key = {}, None
    for line in _top_level(text)["jobs"].splitlines():
        m = re.match(r"^  ([A-Za-z_][\w-]*):\s*$", line)
        if m:
            key = m.group(1)
            blocks[key] = ""
        elif key:
            blocks[key] += line + "\n"
    return blocks


def _permissions(job: str) -> dict[str, str]:
    m = re.search(r"^    permissions:\s*(\{\})?\s*\n((?:      .*\n)*)", job, re.M)
    assert m, "the job declares no permissions block"
    return dict(re.findall(r"^      ([\w-]+):\s*(\w+)", m.group(2), re.M))


def _step(job: str, name: str) -> str:
    """The text of one named step, up to the next step."""
    start = job.index(f"- name: {name}")
    following = job.find("\n      - ", start)
    return job[start:] if following == -1 else job[start:following]


def test_the_workflow_keeps_the_file_name_pypi_names():
    assert WORKFLOW.is_file()
    assert "tags:" in _top_level(_text())["on"]


def test_the_workflow_grants_nothing_by_default():
    assert _top_level(_text())["permissions"].strip() == "{}"


def test_each_job_holds_only_the_permission_it_needs():
    jobs = _jobs(_text())
    assert set(jobs) == {"build", "pypi-publish", "github-release"}
    assert _permissions(jobs["build"]) == {"contents": "read"}
    assert _permissions(jobs["pypi-publish"]) == {"id-token": "write"}
    assert _permissions(jobs["github-release"]) == {"contents": "write"}


def test_checkouts_do_not_keep_the_token():
    for name, job in _jobs(_text()).items():
        if "actions/checkout@" in job:
            assert "persist-credentials: false" in job, f"{name} keeps the checkout token"


def test_only_a_tag_reaches_pypi_or_the_github_release():
    # A manual run on a branch builds and checks the package and stops there.
    jobs = _jobs(_text())
    for name in ("pypi-publish", "github-release"):
        assert re.search(r"^    if: startsWith\(github\.ref, 'refs/tags/v'\)$", jobs[name], re.M), \
            f"{name} can run without a tag"


def test_the_build_checks_the_tag_against_the_package_version():
    build = _jobs(_text())["build"]
    read = _step(build, "Read the package version")
    assert "src/index_graph/__init__.py" in read and "PACKAGE_VERSION=" in read
    assert "GITHUB_ENV" in read
    check = _step(build, "Check the tag matches the package version")
    assert re.search(r'"\$\{GITHUB_REF_NAME\}" = "v\$\{PACKAGE_VERSION\}"', check)
    assert "exit 1" in check
    assert build.index("Check the tag matches") < build.index("python -m build")


def test_the_suite_runs_before_the_build():
    build = _jobs(_text())["build"]
    assert re.search(r"python -m pytest\b", build), "the release never runs the test suite"
    assert build.index("pytest") < build.index("python -m build"), "the build runs before the tests"


def test_publish_waits_for_the_test_suite():
    jobs = _jobs(_text())
    testing = [name for name, job in jobs.items() if re.search(r"\bpytest\b", job)]
    assert testing, "no release job runs the test suite"
    needs = re.search(r"needs:\s*\[?([^\]\n]*)", jobs["pypi-publish"]).group(1)
    assert any(name in needs for name in testing), "publish does not wait for the tests"


def test_the_build_compares_the_installed_wheel_to_the_package_version():
    verify = _step(_jobs(_text())["build"], "Verify the wheel installs")
    assert "pip install dist/*.whl" in verify
    assert re.search(r'index --version\)"?\s*=\s*"?index \$\{PACKAGE_VERSION\}', verify), \
        "the build never compares the installed command's version to the package version"
    assert re.search(r"importlib\.metadata.*PACKAGE_VERSION", verify), \
        "the build never compares the installed metadata to the package version"


def test_the_build_writes_checksums_for_the_wheel_and_the_sdist():
    build = _jobs(_text())["build"]
    assert re.search(r"sha256sum \*\.whl \*\.tar\.gz > \S*SHA256SUMS\.txt", build)
    assert "dist/index_graph-${PACKAGE_VERSION}-py3-none-any.whl" in build
    assert "dist/index_graph-${PACKAGE_VERSION}.tar.gz" in build


def test_the_pypi_upload_can_be_rerun():
    publish = _jobs(_text())["pypi-publish"]
    assert "pypa/gh-action-pypi-publish@" in publish
    assert re.search(r"^\s+skip-existing:\s*true\s*(#.*)?$", publish, re.M)


def test_the_github_release_carries_wheel_sdist_and_checksums():
    release = _jobs(_text())["github-release"]
    assert re.search(r"needs:\s*\[?\s*build,\s*pypi-publish\s*\]?", release)
    assert "gh release create" in release
    for asset in ("dist/*.whl", "dist/*.tar.gz", "SHA256SUMS.txt"):
        assert asset in release, f"the release does not attach {asset}"
    assert "sha256sum -c" in release, "the release does not verify the checksums it attaches"


def test_the_release_checks_pypi_holds_the_same_files():
    release = _jobs(_text())["github-release"]
    assert "pypi.org/pypi/index-graph/" in release, "nothing compares PyPI's digests to SHA256SUMS"
    assert release.index("pypi.org/pypi/") < release.index("gh release create"), \
        "the PyPI comparison runs after the release is cut"
    assert "SHA256SUMS.txt" in release[: release.index("gh release create")]
    assert "if have != want:" in release and "sys.exit(1)" in release
