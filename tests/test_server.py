from __future__ import annotations

import asyncio

from src.server import create_mcp_server


def test_three_tools_are_registered(tmp_path) -> None:
    server = create_mcp_server(tmp_path)

    tools = asyncio.run(server.list_tools())

    assert {tool.name for tool in tools} == {
        "recognize_character",
        "reverse_search",
        "recognize_illustration",
    }
