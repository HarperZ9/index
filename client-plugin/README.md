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
select your installed Python executable. The plugin folder carries its own copy
of the server code under `server/src`, so keep the complete folder or extracted
bundle together. The Windows x64 binary MCPB and ZIP include Python;
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

## What this plugin runs and handles

### Hooks

This plugin has no hooks.

### MCP server

The plugin starts one local server named `index`. Claude Code launches it with this command:

```
python3 -I -S -B ${CLAUDE_PLUGIN_ROOT}/server/serve.py --workspace ${user_config.workspace} --state-directory=${user_config.state_directory}
```

- `python3` is the Python 3.11 or later that Claude Code finds on your PATH.
- `-I -S -B` start Python in isolated mode. Python then ignores `PYTHON*` environment variables and your user packages, skips the `site` module, and writes no bytecode files.
- `${CLAUDE_PLUGIN_ROOT}` is the folder where Claude Code installed the plugin.
- `${user_config.workspace}` is the **Readable workspace** you choose when you enable the plugin. The server reads only files and folders inside it. It refuses links, network paths and paths outside it.
- `${user_config.state_directory}` is the **Optional private state directory**. If you leave it empty, the server writes no files. If you choose a folder, it must already exist, and the server reads and writes only inside it.

### Network

The server opens no network connection. At startup it installs a Python audit hook. The hook refuses every socket operation and every attempt to start another program, Git included. The server sends tool results only to Claude Code, over standard input and output.

### Files written

Without a state directory, the server writes no files.

With a state directory, it writes only inside that folder:

- `cache/<hash>.json` holds a saved `index.map` result. After 15 minutes the server stops using an entry and saves a fresh result. Old entries stay until you delete them.
- `jobs/<job id>/` is used only for jobs that already exist there. The server never starts a new job. The job status, result and cancel tools can create `state.lock`, a one-byte lock file. Cancel writes `cancel.request`. Status, result and cancel can rewrite `status.json` to mark a job as interrupted when its worker has stopped. Each write goes to a temporary file first, which is then renamed. These files stay until you delete them.

### Environment variables and credentials

The plugin asks for no credentials and has no sensitive settings. It reads these environment variables:

- `INDEX_CACHE_TTL_SECONDS` sets how many seconds a saved map stays in use. Default 900. Read only with a state directory.
- `INDEX_ROUTER_JOB_HEARTBEAT_STALE_SECONDS` sets how many seconds after a job's worker started the server still treats the job as starting rather than interrupted. Default 60. Read only with a state directory.
- `INDEX_GIT_TIMEOUT_SECONDS` sets the time limit for a Git call. When the workspace holds a Git repository, `index.map` prepares a Git call. It reads this value and copies every environment variable, adding `GIT_CEILING_DIRECTORIES`, to pass to Git. The audit hook then refuses to start Git, so the copy is dropped. It never leaves the server and is not written to disk. The copy can include tokens you keep in environment variables.
- `COLUMNS` and `LINES` are read by Python's argument parser to wrap startup messages.
- `LANG`, `LANGUAGE`, `LC_ALL` and `LC_MESSAGES` are read by Python's argument parser to pick the language of startup messages.

The server code also contains these variables, but the plugin's tools never read them: `INDEX_CACHE_DIR`, `INDEX_GRAPH_REPO_CACHE_DIR`, `INDEX_MCP_CACHE_DIR`, `INDEX_MCP_CACHE_TTL_SECONDS`, `INDEX_MCP_DEBUG_ERRORS`, `INDEX_ROUTER_JOB_DIR`, `INDEX_INTERACTIVE_BUDGET_MS`, `INDEX_INTERACTIVE_REPO_LIMIT` and `LOCALAPPDATA`. They belong to the full Index command line and MCP server. The plugin passes the state directory to the cache and job code directly, so their default folders are never used.
