"""MCPB setup fields become literal launch arguments, never tool grants."""


def manifest(spec, version, exe_name):
    return {"manifest_version":"0.3", "name":spec["name"]+"-local",
    "version":version, "display_name":spec["name"].title()+" Local",
    "description":spec["desc"], "author":{"name":"Zain Dana Harper"}, "license":"FSL-1.1-MIT",
    "server":{"type":"binary", "entry_point":"server/"+exe_name, "mcp_config":{
        "command":"${__dirname}/server/"+exe_name,
        "args":["--workspace", "${user_config.workspace}",
            "--state-directory", "${user_config.state_directory}"], "env":{}}},
    "user_config":{"workspace":{"type":"directory", "title":"Readable workspace",
        "description":"Local directory this profile may read. Choose only approved files.", "required":True},
        "state_directory":{"type":"directory", "title":"Optional private state directory",
            "description":"Leave empty for read-only access. Existing directory for cached maps and existing job receipts/cancellation; no process workers or Git checkpoints.",
            "required":False, "default":""}},
    "compatibility":{"platforms":["win32"]}}
