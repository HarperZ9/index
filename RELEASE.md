# Release Checklist

## 0.1.0 Candidate

- [ ] Confirm `README.md`, `LICENSE`, `AUTHORS.md`, `CONTRIBUTING.md`, and
  `CHANGELOG.md` are present.
- [ ] Run `python -m pytest -q`.
- [ ] Run `python -m build`.
- [ ] Run `python -m twine check dist/*`.
- [ ] Run `public-surface-sweeper . --summary`.
- [ ] Create a signed `v0.1.0` tag when signing is configured, or an
  annotated `v0.1.0` tag when it is not.
- [ ] Publish to PyPI only after account ownership, 2FA, and trusted publishing
  configuration are confirmed.

This repository does not auto-publish to a package registry.
