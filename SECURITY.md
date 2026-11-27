# Security Policy

## Supported versions

`index-graph` is distributed on PyPI and provides a local repository atlas, offline wiki generator,
and stdio MCP server. Security fixes ship in the current release line as a new release. Older lines
do not receive backports.

| Version | Supported |
|-|-|
| 2.16.x | Yes |
| < 2.16 | No |

## Reporting a vulnerability

Report suspected vulnerabilities privately through GitHub: open this repository's **Security** tab
and select **Report a vulnerability**, or open
<https://github.com/HarperZ9/index/security/advisories/new>.
Keep security reports out of public issues, pull requests, and discussions.

Include:

- the affected version and operating system,
- a concise description of the issue and its impact,
- the minimal input or steps needed to reproduce it.

The maintainer, Zain Dana Harper, acknowledges reports and works on a fix before public disclosure.
Allow a reasonable period to remediate before disclosing.

## Scope and trust model

Index inspects local repositories, source symbols, git metadata, and workspace structure.

- **Local inspection, zero default network.** Core scanning, symbol indexing, and architecture checks
  run locally with no network access and no telemetry.
- **MCP surface.** The MCP server communicates over stdio JSON-RPC, opens no listening socket, and
  reads repositories within configured workspace boundaries. Output sent to an MCP client is shared
  with that client and its configured model provider.
- **Untrusted repositories.** Source files and manifests inside scanned repositories are parsed as
  data. Index does not execute repository build scripts or user code during indexing.
- **What counts as a vulnerability.** Arbitrary command or code execution triggered by scanning an
  untrusted repository, path escape when writing generated wiki or graph artifacts outside the
  requested target directory, or secret leakage across workspace boundaries.
- **What does not count.** Parsing errors on malformed source files that fail cleanly with a normal
  exception.

## Good practice

- Exclude secret files and `.env` artifacts from generated documentation exports.
- Run workspace scans against untrusted repositories in an isolated directory or container.
