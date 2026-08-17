from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import tomllib

DEFAULT_VISION_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
VISION_API_KEY_ENV = "CHARACTER_RECOGNIZE_VISION_API_KEY"
SAUCENAO_API_KEY_ENV = "CHARACTER_RECOGNIZE_SAUCENAO_API_KEY"


class CharacterRecognizeConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class VisionRuntimeConfig:
    base_url: str = DEFAULT_VISION_BASE_URL
    api_key: str | None = field(default=None, repr=False)
    model: str = "qwen-vl-max"


@dataclass(frozen=True)
class CharacterRecognizeRuntimeConfig:
    vision: VisionRuntimeConfig = field(default_factory=VisionRuntimeConfig)
    saucenao_api_key: str | None = field(default=None, repr=False)
    request_timeout_seconds: float = 30.0
    rate_limit_enabled: bool = True


def load_runtime_config(data_dir: Path) -> CharacterRecognizeRuntimeConfig:
    """读取私密配置；环境变量中的密钥优先于 plugin-data 配置。"""

    path = data_dir / "config.local.toml"
    if path.exists():
        try:
            raw = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as error:
            raise CharacterRecognizeConfigError(
                f"无法读取 character-recognize 私密配置: {path}"
            ) from error
    else:
        raw = {}
    if not isinstance(raw, dict):
        raise CharacterRecognizeConfigError("config.local.toml 顶层必须是 TOML table")

    vision = _table(raw.get("vision", {}), "vision")
    sauce = _table(raw.get("saucenao", {}), "saucenao")
    base_url = _non_empty_string(
        vision.get("base_url", DEFAULT_VISION_BASE_URL), "vision.base_url"
    ).rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise CharacterRecognizeConfigError("vision.base_url 必须是 HTTPS URL")
    model = _non_empty_string(vision.get("model", "qwen-vl-max"), "vision.model")

    vision_key = _secret(
        os.environ.get(VISION_API_KEY_ENV, vision.get("api_key")),
        "vision.api_key",
    )
    sauce_key = _secret(
        os.environ.get(SAUCENAO_API_KEY_ENV, sauce.get("api_key")),
        "saucenao.api_key",
    )

    timeout = raw.get("request_timeout_seconds", 30.0)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise CharacterRecognizeConfigError("request_timeout_seconds 必须是数字")
    timeout = float(timeout)
    if not 1.0 <= timeout <= 120.0:
        raise CharacterRecognizeConfigError(
            "request_timeout_seconds 必须在 1 至 120 秒之间"
        )

    rate_limit = raw.get("rate_limit_enabled", True)
    if not isinstance(rate_limit, bool):
        raise CharacterRecognizeConfigError("rate_limit_enabled 必须是布尔值")

    return CharacterRecognizeRuntimeConfig(
        vision=VisionRuntimeConfig(
            base_url=base_url,
            api_key=vision_key,
            model=model,
        ),
        saucenao_api_key=sauce_key,
        request_timeout_seconds=timeout,
        rate_limit_enabled=rate_limit,
    )


def _table(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise CharacterRecognizeConfigError(f"{label} 必须是 TOML table")
    return value


def _non_empty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CharacterRecognizeConfigError(f"{label} 必须是非空字符串")
    clean = value.strip()
    if "\n" in clean or "\r" in clean:
        raise CharacterRecognizeConfigError(f"{label} 不能包含换行")
    return clean


def _secret(value: object, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CharacterRecognizeConfigError(f"{label} 必须是字符串")
    clean = value.strip()
    if "\n" in clean or "\r" in clean:
        raise CharacterRecognizeConfigError(f"{label} 不能包含换行")
    return clean or None
