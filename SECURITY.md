# Security Policy

## Supported versions

`index-graph` is distributed on PyPI. Security fixes are applied to the current
release line and published as a new patch release. Older lines are not
backported.

| Version | Supported |
|---------|-----------|
| 2.9.x   | Yes       |
| < 2.9   | No        |

## Reporting a vulnerability

Please report suspected vulnerabilities privately. Do not open a public issue,
pull request, or discussion for a security report.

Send the report to `<SECURITY CONTACT>`. Include:

- the affected version and platform,
- a description of the issue and its impact,
- the minimal steps or input needed to reproduce it.

You can expect an acknowledgement, and we will work a fix before any public
disclosure. Please allow a reasonable period to remediate before disclosing.

## Scope and trust model

`index-graph` builds an evidence-backed map of a code workspace. It reads the
repositories you point it at, so treat the repositories it ingests as the input
it operates on.

- Network surface: `index` ships an HTTP server (`index serve`) and a stdio MCP
  server (`index mcp`) that expose the built map. The HTTP server is intended to
  bind a local interface. Do not expose it on an untrusted network without an
  authenticating, TLS-terminating reverse proxy in front of it.
- Untrusted input: the tool ingests repository contents and renders Markdown and
  HTML artifacts. Rendered output is self-contained with no external URLs and
  Markdown is escaped as it renders, but you should still review artifacts built
  from repositories you do not control.
- Zero runtime dependencies: the core has no third-party runtime packages, which
  keeps the dependency attack surface minimal.

## Good practice

- Run the servers as an unprivileged user, scoped to only the paths the work
  needs.
- Keep generated artifacts on storage you control.
