"""Every MCP tool states its title and read/write hints.

The Anthropic Software Directory Policy requires readOnlyHint, destructiveHint
and title on every tool a listed server exposes.
"""
from index_graph import client_mcp
from index_graph.mcp import TOOL_ANNOTATIONS, _tool_defs

HINTS = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")


def _assert_complete(tools):
    assert tools
    for tool in tools:
        notes = tool["annotations"]
        assert notes["title"] and tool["title"] == notes["title"], tool["name"]
        assert all(isinstance(notes[key], bool) for key in HINTS), tool["name"]
        assert len(tool["name"]) <= 64
        if notes["readOnlyHint"]:
            assert notes["destructiveHint"] is False, tool["name"]


def test_full_surface_tools_are_annotated():
    tools = _tool_defs()
    _assert_complete(tools)
    assert {tool["name"] for tool in tools} == set(TOOL_ANNOTATIONS)


def test_client_profile_without_state_is_read_only():
    tools = client_mcp.definitions()
    _assert_complete(tools)
    assert all(tool["annotations"]["readOnlyHint"] for tool in tools)


def test_client_profile_with_state_marks_job_writes(tmp_path):
    tools = client_mcp.definitions(state=tmp_path)
    _assert_complete(tools)
    by_name = {tool["name"]: tool["annotations"] for tool in tools}
    assert by_name["index.map"]["readOnlyHint"] is False
    assert by_name["index.router.job.cancel"]["readOnlyHint"] is False
    assert by_name["index.router.job.status"]["readOnlyHint"] is True
