from __future__ import annotations

import json
import warnings
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .client import (
    CompatibleVisionClient,
    SauceNaoClient,
    SauceRateLimiter,
    TraceMoeClient,
)
from .config import load_runtime_config
from .service import CharacterRecognitionService


def create_mcp_server(data_dir: Path) -> FastMCP:
    # MCP 1.26 leaves its generic lifespan Settings field unresolved.
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Field 'lifespan' has an incomplete definition.*",
        )
        mcp = FastMCP("character-recognize")
    sauce_limiter = SauceRateLimiter(minimum_interval_seconds=8.0)

    def service(*, require_vision: bool = True) -> CharacterRecognitionService:
        config = load_runtime_config(data_dir)
        return CharacterRecognitionService(
            CompatibleVisionClient(config) if require_vision else None,
            SauceNaoClient(config, sauce_limiter),
            TraceMoeClient(config),
        )

    @mcp.tool()
    def verify_installation() -> str:
        """验证候选 MCP 可调用；不读取凭据、不访问文件或网络。"""

        return _json(
            {
                "status": "ok",
                "server": "character-recognize",
                "contract_version": 1,
            }
        )

    @mcp.tool()
    def recognize_character(image_path: str) -> str:
        """识别本地插画中的动漫角色与作品；低于 0.7 的候选仅进入 ambiguous。"""

        return _json(service().recognize_character(image_path))

    @mcp.tool()
    def reverse_search(image_path: str) -> str:
        """使用 SauceNAO 与 Trace.moe 反查本地插画的画师、Pixiv 或动画出处。"""

        return _json(service(require_vision=False).reverse_search(image_path))

    @mcp.tool()
    def recognize_illustration(image_path: str) -> str:
        """一次完成角色识别、来源反查和视觉模型融合裁决。"""

        return _json(service().recognize_illustration(image_path))

    return mcp


def _json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
