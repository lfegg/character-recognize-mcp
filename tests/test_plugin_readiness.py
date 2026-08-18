from __future__ import annotations

import asyncio
import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType, SimpleNamespace

PLUGIN = Path(__file__).resolve().parents[1] / "plugin.py"


class StubPlugin:
    pass


@dataclass(frozen=True)
class StubMcpServerSpec:
    name: str
    command: tuple[str, ...]
    env: dict[str, str] = field(default_factory=dict)
    cwd: str = "."
    candidate_read_only_tools: tuple[str, ...] = ()


@dataclass(frozen=True)
class StubPluginSemanticCheck:
    check_id: str
    passed: bool
    evidence: object = ""


class StubPluginReadinessContext:
    pass


class StubClient:
    def __init__(self, response: str) -> None:
        self.response = response

    async def call(self, name: str, arguments: dict[str, object]) -> str:
        assert name == "verify_installation"
        assert arguments == {}
        return self.response


def test_candidate_probe_declaration_and_readiness(monkeypatch) -> None:
    module = _load_plugin(monkeypatch)
    server = module.CharacterRecognizePlugin.mcp_servers()[0]
    assert server.candidate_read_only_tools == ("verify_installation",)

    passed = _readiness_check(
        module,
        '{"status":"ok","server":"character-recognize","contract_version":1}',
    )
    rejected = _readiness_check(
        module,
        '{"status":"ok","server":"wrong","contract_version":1}',
    )

    assert passed.check_id == "character_recognize_mcp_probe"
    assert passed.passed is True
    assert rejected.passed is False


def _load_plugin(monkeypatch):
    agent_module = ModuleType("agent")
    plugins_module = ModuleType("agent.plugins")
    plugins_module.McpServerSpec = StubMcpServerSpec
    plugins_module.Plugin = StubPlugin
    plugins_module.PluginReadinessContext = StubPluginReadinessContext
    plugins_module.PluginSemanticCheck = StubPluginSemanticCheck
    monkeypatch.setitem(sys.modules, "agent", agent_module)
    monkeypatch.setitem(sys.modules, "agent.plugins", plugins_module)

    spec = importlib.util.spec_from_file_location("plugin_under_test", PLUGIN)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def _readiness_check(module, response: str):
    context = SimpleNamespace(
        mcp_catalog=SimpleNamespace(
            servers={
                "character-recognize": SimpleNamespace(
                    client=StubClient(response),
                )
            }
        )
    )
    return asyncio.run(
        module.CharacterRecognizePlugin().readiness_semantic_checks(context)
    )[0]
