"""MCPB setup fields become literal launch arguments, never tool grants."""

SITE = "https://harperz9.github.io"
REPOSITORY = "https://github.com/HarperZ9/index"
ICON = "./.claude-plugin/icon.png"
KEYWORDS = ["code-navigation", "symbols", "references", "repository-map",
            "local-first", "read-only", "static-analysis"]


def user_config():
    return {"workspace":{"type":"directory", "title":"Readable workspace",
        "description":"Local directory this profile may read. Choose only approved files.", "required":True},
        "state_directory":{"type":"directory", "title":"Optional private state directory",
            "description":"Leave empty for read-only access. Existing directory for cached maps and existing job receipts/cancellation; no process workers or Git checkpoints.",
            "required":False, "default":""}}


def manifest(spec, version, exe_name):
    return {"manifest_version":"0.3", "name":spec["name"]+"-local",
    "version":version, "display_name":spec["name"].title()+" Local",
    "description":spec["desc"], "author":{"name":"Zain Dana Harper"}, "license":"FSL-1.1-MIT",
    "server":{"type":"binary", "entry_point":"server/"+exe_name, "mcp_config":{
        "command":"${__dirname}/server/"+exe_name,
        "args":["--workspace", "${user_config.workspace}",
            "--state-directory", "${user_config.state_directory}"], "env":{}}},
    "user_config":user_config(),
    "compatibility":{"platforms":["win32"]}}


def claude_plugin(spec, version):
    """Claude manifest: the shared plugin fields plus the directory listing fields."""
    return {"name":spec["name"]+"-local", "version":version, "description":spec["desc"],
        "author":{"name":"Zain Dana Harper"}, "license":"FSL-1.1-MIT", "repository":REPOSITORY,
        "displayName":spec["name"].title(), "keywords":KEYWORDS,
        "homepage":SITE+"/index-graph.html",
        "documentationUrl":REPOSITORY+"/blob/main/client-plugin/README.md",
        "supportUrl":SITE+"/plugins/index/support.html",
        "privacyPolicyUrl":SITE+"/plugins/index/privacy.html",
        "termsOfServiceUrl":SITE+"/plugins/index/terms.html",
        "icon":ICON, "userConfig":user_config()}


def claude_mcp():
    """Claude launch: plain arguments whose values come from userConfig."""
    return {"mcpServers":{"index":{"command":"python3",
        "args":["-I", "-S", "-B", "${CLAUDE_PLUGIN_ROOT}/server/serve.py",
            "--workspace", "${user_config.workspace}",
            "--state-directory=${user_config.state_directory}"], "env":{}}}}
