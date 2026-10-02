# Privacy

This local profile reads only submitted paths under the workspace selected at
launch. Tool output is returned to the connected client and its chosen model.
No publisher service, telemetry endpoint, inference engine, or credential store
is used by this profile. Do not include confidential data in the selected
workspace unless that client and model are authorized to receive it.

The optional launch flag `--state-directory` grants reads and writes in one
existing private state directory for cached maps and existing job
receipts. Inspection can update recovery metadata; cancellation writes a request.
Tool arguments and inherited environment variables cannot select that directory.

## What it sends

This profile opens no network connection and starts no process; the launcher denies
both.

## Retention and support

Without a state directory Index keeps no data after a call returns. Files in a state
directory stay until you delete them. Support and security reports:
https://github.com/HarperZ9/index/issues

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
