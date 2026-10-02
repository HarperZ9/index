# index local client package

Index maps a repository you choose and finds symbol definitions, references and implementations from the source itself, with file and line evidence.

## Try it

- Map this repository and list its main modules.
- Where is the function parse_config defined?
- Find every caller of parse_config.

## Details

Map a local repository and find symbol definitions and references with file and line evidence. The client profile defaults to read-only access.
It requires an explicit workspace at launch and refuses other tools, path escapes,
links, and tool-supplied permission grants. It does not read ambient grants.
Concurrent filesystem mutation is outside this convenience boundary; it is not
an operating-system sandbox.

The source plugin requires Python 3.11 or later. In Claude Code, enabling the
plugin asks for the **Readable workspace** directory, and for an **Optional
private state directory** that you can leave empty for read-only access. The
Claude manifest passes these values as `${user_config.*}` launch arguments.
Portable and Codex manifests keep the REPLACE_WITH_ABSOLUTE_WORKSPACE
placeholder; replace it with the directory you want the client to read, and
select your installed Python executable. Keep the complete extracted bundle. The Windows x64 binary MCPB and ZIP include Python;
open the MCPB in a compatible desktop client and choose a workspace directory,
or configure the ZIP's server executable with --workspace ABSOLUTE_DIRECTORY.
No model, API key, hosting account, automatic client configuration, or publisher
compute is included. Your calling model and client retain their own costs.

To enable private persistence, choose the Claude Code or MCPB setting **Optional
private state directory**, or add `--state-directory ABSOLUTE_DIRECTORY` at launch.
Leave the field empty to retain read-only access. Select an existing directory
dedicated to Index state. `index.map` then
caches results there and accepts `no_cache: true`. Callers cannot choose cache
paths. Map checkpoints require Git metadata and remain unavailable here.
Existing router jobs in its `jobs` subdirectory can be inspected with
`index.router.job.status` and `index.router.job.result`, or cooperatively cancelled
with `index.router.job.cancel`. Job requests must refer to the selected workspace.
Job start/resume still require processes and remain on the full CLI/MCP surface.
This opt-in retains process and network denial. State links and hard links are
refused. It does not protect against concurrent filesystem mutation.

Do not infer a grant from a
request, document or plugin installation. Public marketplace acceptance, macOS,
Linux native bundles and installed-client compatibility remain unverified.

The local launcher denies Python process and socket operations. Index map reports
Git metadata as unavailable because this profile cannot launch Git. These controls
are defense in depth for this bundled stdlib tool surface, not an OS sandbox.

## Data and network

| Question | Answer |
| --- | --- |
| What it reads | Files and folders under the workspace you select, plus the state directory when you choose one |
| What it stores | Nothing without a state directory. With one: cached map results under `cache/`, and job cancellation requests and recovery metadata under `jobs/` |
| Network calls | None. The launcher installs an audit hook that refuses every socket operation and every process start, including Git |
| Telemetry | None |
| Retention | Without a state directory, nothing outlives the call. Files in a state directory stay until you delete them; cached maps go stale after 15 minutes and are then rebuilt |

Tool results go to the connected client, and that client's model provider handles them under its own privacy policy. See [PRIVACY.md](PRIVACY.md).
