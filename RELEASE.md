# Releasing index-graph

A release is a version bump merged to `main` and a `vX.Y.Z` tag on that merge.
The tag push runs `.github/workflows/release-artifacts.yml`, which publishes the
package to PyPI and creates the GitHub Release.

## Prepare the release pull request

1. Pick the version. A release that adds commands, flags, tools or Python entry
   points is a minor bump; fixes alone are a patch bump.
2. Bump the three version sites:
   - `__version__` in `src/index_graph/__init__.py` (the build reads it from here);
   - the status line in `README.md`;
   - a dated `## X.Y.Z (YYYY-MM-DD)` heading in `CHANGELOG.md`, moving the
     `Unreleased` entries under it.
3. Run `python -m pytest`. `tests/test_version_sites.py` fails when one of the
   three sites names a different version.

## Tag and publish

After the pull request merges, tag the merge commit and push the tag:

```
git tag -a vX.Y.Z -m "index-graph X.Y.Z" <merge commit>
git push origin vX.Y.Z
```

The workflow then:

1. checks that the tag names the package version;
2. runs the test suite at the tagged commit;
3. builds the wheel and sdist and runs `twine check`;
4. installs the wheel in a clean environment and checks that `index --version`
   and the installed metadata both report the tag's version;
5. writes `SHA256SUMS.txt` and takes the release notes from the tag's
   `CHANGELOG.md` section;
6. uploads to PyPI with `skip-existing`, so a re-run after a partial upload
   finishes instead of failing;
7. checks that PyPI serves exactly the files `SHA256SUMS.txt` names, then creates
   the GitHub Release with the wheel, the sdist and `SHA256SUMS.txt`.

A manual run of the workflow on a branch skips the tag check, runs steps 2 to 5
and publishes nothing. A failed tag run can be re-run from the Actions page.

## Verify a download

Download `SHA256SUMS.txt` from the GitHub Release next to the files you fetched:

```
sha256sum --ignore-missing -c SHA256SUMS.txt
```
