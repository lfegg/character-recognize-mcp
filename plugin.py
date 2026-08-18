from __future__ import annotations

import json

from agent.plugins import (
    McpServerSpec,
    Plugin,
    PluginReadinessContext,
    PluginSemanticCheck,
)
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

DEFAULT_VISION_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


class VisionModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = DEFAULT_VISION_BASE_URL
    api_key: SecretStr | None = None
    model: str = "qwen-vl-max"

    @field_validator("base_url", "model")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("配置值不能为空")
        return clean.rstrip("/") if clean.startswith("http") else clean


class SauceNaoConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: SecretStr | None = None


class CharacterRecognizeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vision: VisionModelConfig = Field(default_factory=VisionModelConfig)
    saucenao: SauceNaoConfig = Field(default_factory=SauceNaoConfig)
    request_timeout_seconds: float = Field(default=30.0, ge=1.0, le=120.0)
    rate_limit_enabled: bool = Field(default=True, strict=True)


class CharacterRecognizePlugin(Plugin):
    api_version = 2
    name = "character-recognize"
    version = "0.1.1"
    desc = "识别动漫插画中的角色与作品，并反查 Pixiv、画师和动画出处"
    author = "lfegg"
    ConfigModel = CharacterRecognizeConfig

    @classmethod
    def skill_roots(cls) -> tuple[str, ...]:
        return ("skills",)

    @classmethod
    def mcp_servers(cls) -> list[McpServerSpec]:
        return [
            McpServerSpec(
                name="character-recognize",
                command=("python", "mcp/run_mcp.py"),
                candidate_read_only_tools=("verify_installation",),
            )
        ]

    async def readiness_semantic_checks(
        self,
        context: PluginReadinessContext,
    ) -> list[PluginSemanticCheck]:
        try:
            server = context.mcp_catalog.servers["character-recognize"]
            raw = await server.client.call("verify_installation", {})
            payload = json.loads(raw)
        except (KeyError, TypeError, ValueError, RuntimeError, OSError) as error:
            return [
                PluginSemanticCheck(
                    "character_recognize_mcp_probe",
                    False,
                    {"error_type": type(error).__name__},
                )
            ]

        expected = {
            "status": "ok",
            "server": "character-recognize",
            "contract_version": 1,
        }
        return [
            PluginSemanticCheck(
                "character_recognize_mcp_probe",
                payload == expected,
                payload,
            )
        ]
