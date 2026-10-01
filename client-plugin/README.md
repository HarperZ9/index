# index local client package

Map local repositories and inspect source symbols without inference. The client profile defaults to read-only access.
It requires an explicit workspace at launch and refuses other tools, path escapes,
links, and tool-supplied permission grants. It does not read ambient grants.
Concurrent filesystem mutation is outside this convenience boundary; it is not
an operating-system sandbox.

The source plugin requires Python 3.11 or later. Replace
REPLACE_WITH_ABSOLUTE_WORKSPACE in the MCP configuration with the directory you
want the client to read, and select your installed Python executable. Keep the
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
