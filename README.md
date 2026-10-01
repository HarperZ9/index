## Marketplace source distribution

This folder packages the source plugin from release 2.15.0. It requires Python 3.11 or later, available as `python3`. It includes the tool source and no model or bundled runtime. The connected client supplies any model used in the conversation.

The separate [Windows x64 native download](https://github.com/HarperZ9/index/releases/download/v2.15.0/index-client-2.15.0-win-x64.mcpb) includes its runtime. That download is a manual MCPB package and is not part of this source plugin. Directory approval and availability remain unverified.

This branch contains the installable plugin. Build commands in the release README below apply to the [product source tag](https://github.com/HarperZ9/index/tree/v2.15.0). DISTRIBUTION.json records the published asset digest and every packaging change; any SOURCE.json describes the original release payload.

# index local client package

Map local repositories and inspect source symbols without inference. The client profile defaults to read-only access.
It requires an explicit workspace at launch and refuses other tools, path escapes,
links, and tool-supplied permission grants. It does not read ambient grants.
Concurrent filesystem mutation is outside this convenience boundary; it is not
an operating-system sandbox.

The source plugin requires Python 3.11 or later. Claude Code asks for the required
workspace folder when it enables this plugin. For portable or generic MCP clients,
replace REPLACE_WITH_ABSOLUTE_WORKSPACE in their MCP configuration with the
directory you want the client to read, and select your installed Python executable. Keep the
complete extracted bundle. The Windows x64 binary MCPB and ZIP include Python;
open the MCPB in a compatible desktop client and choose a workspace directory,
or configure the ZIP's server executable with --workspace ABSOLUTE_DIRECTORY.
No model, API key, hosting account, automatic client configuration, or publisher
compute is included. Your calling model and client retain their own costs.

To enable private persistence, choose the MCPB setup field **Optional private
state directory**, or add `--state-directory ABSOLUTE_DIRECTORY` at launch.
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

## Claude Code workspace

This distribution asks for a required workspace folder when Claude Code enables the plugin. Select an absolute path to an existing folder. The adapter checks that path before starting; no default workspace is supplied. This profile reads local documents and grants no network access. Portable MCP clients still replace the workspace placeholder as described above. Cowork setup for this required setting is not established; use Claude Code for this source distribution.
