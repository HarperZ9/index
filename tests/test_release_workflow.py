"""The release workflow: least-privilege jobs, tests before the build, a tag that
matches the package, a re-runnable PyPI upload, and a GitHub Release that carries
the wheel, the sdist and SHA256SUMS.txt once PyPI serves those same files.

Read as text: the test extras carry no YAML parser.
"""
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# Keep this file name: a PyPI trusted publisher for index-graph, once configured, names it,
# and renaming the file would then break trusted publishing.
WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release-artifacts.yml"
PUBLISH_GATE = "needs.release-source.outputs.publish == 'true'"


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
    m = re.search(r"^    permissions:\s*(\{\})?\s*\n((?:      .*\n)*)", job, re.MULTILINE)
    assert m, "the job declares no permissions block"
    return dict(re.findall(r"^      ([\w-]+):\s*(\w+)", m.group(2), re.MULTILINE))


def _step(job: str, name: str) -> str:
    """The text of one named step, up to the next step."""
    start = job.index(f"name: {name}")
    following = job.find("\n      - ", start)
    return job[start:] if following == -1 else job[start:following]


def _run_block(step: str) -> str:
    """The shell script of one step: the lines under its ``run:`` key."""
    m = re.search(r"^        run: \|\n((?:          .*\n|\s*\n)*)", step + "\n", re.MULTILINE)
    if m:
        return m.group(1)
    m = re.search(r"^        run: (.+)$", step, re.MULTILINE)
    assert m, "the step runs no shell script"
    return m.group(1) + "\n"


def _step_if(step: str) -> str | None:
    m = re.search(r"^        if: (.+)$", step, re.MULTILINE)
    return None if m is None else m.group(1).strip()


def test_the_release_workflow_file_exists():
    assert WORKFLOW.is_file()
    assert "tags:" in _top_level(_text())["on"]


def test_the_workflow_grants_nothing_by_default():
    assert _top_level(_text())["permissions"].strip() == "{}"


def test_each_job_holds_only_the_permission_it_needs():
    jobs = _jobs(_text())
    assert set(jobs) == {"release-source", "build", "pypi-publish", "github-release", "native-client", "attach-client"}
    assert _permissions(jobs["release-source"]) == {"contents": "read"}
    assert _permissions(jobs["native-client"]) == {"contents": "read"}
    assert _permissions(jobs["attach-client"]) == {"contents": "write"}
    assert "needs: [release-source, github-release, native-client]" in jobs["attach-client"]
    assert "--clobber" not in jobs["attach-client"]
    assert _permissions(jobs["build"]) == {"contents": "read"}
    assert _permissions(jobs["pypi-publish"]) == {"id-token": "write"}
    assert _permissions(jobs["github-release"]) == {"contents": "write"}


def test_checkouts_do_not_keep_the_token():
    for name, job in _jobs(_text()).items():
        if "actions/checkout@" in job:
            assert "persist-credentials: false" in job, f"{name} keeps the checkout token"


def test_only_a_tag_reaches_pypi_or_the_github_release():
    # Publication requires the resolver to verify an explicit immutable tag.
    jobs = _jobs(_text())
    for name in ("pypi-publish", "github-release", "attach-client"):
        assert re.search(r"^    if: (.+)$", jobs[name], re.MULTILINE).group(1) == PUBLISH_GATE
        assert "release-source" in re.search(r"^    needs: (.+)$", jobs[name], re.MULTILINE).group(1)


def test_the_build_checks_the_tag_against_the_package_version():
    build = _jobs(_text())["build"]
    read = _step(build, "Read the package version")
    assert "src/index_graph/__init__.py" in read and "PACKAGE_VERSION=" in read
    assert "GITHUB_ENV" in read
    check = _step(build, "Check the tag matches the package version")
    assert re.search(r'"\$\{RELEASE_TAG\}" = "v\$\{PACKAGE_VERSION\}"', check)
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
    assert re.search(r"^\s+skip-existing:\s*true\s*(#.*)?$", publish, re.MULTILINE)


def test_the_github_release_carries_wheel_sdist_and_checksums():
    release = _jobs(_text())["github-release"]
    assert "needs: [release-source, build, pypi-publish]" in release
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


def test_no_build_step_may_fail_and_let_the_release_go_on():
    # continue-on-error on the job or on any step would let a tag publish after a
    # failed test run or a tag that does not match the package version.
    assert "continue-on-error" not in _jobs(_text())["build"]


def test_the_tag_check_and_the_suite_keep_their_exit_status():
    build = _jobs(_text())["build"]
    for name in ("Check the tag matches the package version", "Run the test suite before building"):
        script = _run_block(_step(build, name))
        for escape in ("|| true", "|| :", "set +e"):
            assert escape not in script, f"{name!r} ignores its exit status with {escape!r}"


def test_the_tag_check_runs_on_every_tag_the_publish_jobs_run_on():
    jobs = _jobs(_text())
    check = _step(jobs["build"], "Check the tag matches the package version")
    assert _step_if(check) == PUBLISH_GATE, "a tag push can skip the tag check"
    for name in ("pypi-publish", "github-release"):
        assert re.search(r"^    if: (.+)$", jobs[name], re.MULTILINE).group(1).strip() == PUBLISH_GATE


def test_the_suite_step_runs_unconditionally():
    suite = _step(_jobs(_text())["build"], "Run the test suite before building")
    assert _step_if(suite) is None, "the test suite step can be skipped"


def test_publish_requires_distribution_and_native_client_checks():
    publish = _jobs(_text())["pypi-publish"]
    assert re.search(r"^    needs: (.+)$", publish, re.MULTILINE).group(1).strip() == "[release-source, build, native-client]"


def test_product_jobs_checkout_the_resolved_commit():
    jobs = _jobs(_text())
    resolver = jobs["release-source"]
    assert "fetch-depth: 0" in resolver
    for output in ("commit", "tag", "publish"):
        assert f"{output}: ${{{{ steps.source.outputs.{output} }}}}" in resolver
    for name in ("build", "native-client"):
        assert "needs: [release-source]" in jobs[name]
        assert "ref: ${{ needs.release-source.outputs.commit }}" in jobs[name]
    native = jobs["native-client"]
    assert "fetch-depth: 0" in native
    assert "needs.release-source.outputs.publish" in native
    assert "{ 'release' } else { 'dev' }" in native
    assert '$env:GITHUB_REF = "refs/tags/$env:RELEASE_TAG"' in native
    assert "--mode $mode --native" in native


def test_native_temp_is_canonical_before_boundary_tests_and_build():
    native = _jobs(_text())["native-client"]
    canonical = _step(native, "Use a canonical native temporary directory")
    assert "p.resolve()" in canonical
    assert '"TEMP=$nativeTemp" >> $env:GITHUB_ENV' in canonical
    assert '"TMP=$nativeTemp" >> $env:GITHUB_ENV' in canonical
    assert "if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }" in canonical
    assert native.index("Use a canonical") < native.index("Exercise local client boundaries")
    assert native.index("Exercise local client boundaries") < native.index("Build native client")
    for test in ("test_client_profile.py", "test_client_package.py", "test_client_state.py", "test_client_setup.py"):
        assert test in native


@pytest.fixture
def release_repository(tmp_path):
    """Real local tags, including a version mismatch; never contact a remote."""
    repo = tmp_path / "repo"
    repo.mkdir()
    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()
    git("init", "--quiet")
    module = repo / "src/index_graph/__init__.py"
    module.parent.mkdir(parents=True)
    commits = {}
    for version in ("1.2.0", "1.2.1"):
        module.write_text(f'__version__ = "{version}"\n', encoding="utf-8")
        git("add", ".")
        git("-c", "user.name=Release test", "-c", "user.email=release@example.invalid",
            "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", version)
        commits[version] = git("rev-parse", "HEAD")
        git("tag", "v" + version)
    git("tag", "v9.9.0")  # Valid spelling but differs from its package version.
    return repo, commits


@pytest.mark.parametrize("event,ref,input_tag,publish,version", [
    ("push", "refs/tags/v1.2.0", "", True, "1.2.0"),
    ("workflow_dispatch", "refs/heads/main", "v1.2.0", True, "1.2.0"),
    ("workflow_dispatch", "refs/heads/main", "", False, None),
    ("workflow_dispatch", "refs/tags/v1.2.0", "", False, None),
    ("workflow_dispatch", "refs/heads/v1.2.0", "", False, None),
    ("workflow_dispatch", "refs/heads/main", "main", None, None),
    ("workflow_dispatch", "refs/heads/main", "v1.2.1", None, None),
    ("workflow_dispatch", "refs/heads/main", "v8.0.0", None, None),
    ("workflow_dispatch", "refs/heads/main", "v9.9.0", None, None),
    ("workflow_dispatch", "refs/heads/main", "v1.2.0; touch injected", None, None),
])
def test_release_source_resolver_executes_fail_closed(
    release_repository, tmp_path, event, ref, input_tag, publish, version,
):
    bash = (str(Path("C:/Program Files/Git/bin/bash.exe")) if os.name == "nt"
            and Path("C:/Program Files/Git/bin/bash.exe").is_file() else shutil.which("bash"))
    if not bash:
        pytest.skip("Bash is required to execute the GitHub Ubuntu resolver script")
    repo, commits = release_repository
    source = _step(_jobs(_text())["release-source"], "Resolve and validate immutable release source")
    script = textwrap.dedent(_run_block(source))
    output = tmp_path / "outputs"
    env = dict(os.environ, INPUT_RELEASE_TAG=input_tag, GITHUB_EVENT_NAME=event,
        GITHUB_REF=ref, GITHUB_REF_NAME=ref.rsplit("/", 1)[-1],
        GITHUB_SHA=commits["1.2.1"], GITHUB_OUTPUT=output.as_posix(),
        GITHUB_STEP_SUMMARY=(tmp_path / "summary").as_posix())
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    result = subprocess.run([bash, "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", script],
        cwd=repo, env=env, capture_output=True, text=True, timeout=30, check=False)
    outputs = dict(line.split("=", 1) for line in output.read_text().splitlines()) if output.exists() else {}
    assert not (repo / "injected").exists()
    if publish is None:
        assert result.returncode != 0, result.stdout
        assert outputs.get("publish") != "true"
    else:
        assert result.returncode == 0, result.stderr
        assert outputs["publish"] == str(publish).lower()
        assert outputs["commit"] == commits[version or "1.2.1"]
        if publish:
            assert outputs["tag"] == "v" + version
        else:
            assert "tag" not in outputs
