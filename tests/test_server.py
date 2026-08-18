from __future__ import annotations

import asyncio

from src.server import create_mcp_server


def test_tools_and_installation_probe_are_registered(tmp_path) -> None:
    server = create_mcp_server(tmp_path)

    tools = asyncio.run(server.list_tools())

    assert {tool.name for tool in tools} == {
        "verify_installation",
        "recognize_character",
        "reverse_search",
        "recognize_illustration",
    }


def test_installation_probe_requires_no_config_or_network(tmp_path) -> None:
    server = create_mcp_server(tmp_path)

    content, structured_content = asyncio.run(
        server.call_tool("verify_installation", {})
    )

    assert content[0].text == (
        '{"status":"ok","server":"character-recognize","contract_version":1}'
    )
    assert structured_content == {
        "result": '{"status":"ok","server":"character-recognize","contract_version":1}'
    }
