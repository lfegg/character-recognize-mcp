from __future__ import annotations

from src.config import load_runtime_config


def test_runtime_config_loads_private_keys_without_repr_leak(tmp_path) -> None:
    (tmp_path / "config.local.toml").write_text(
        """
request_timeout_seconds = 45
rate_limit_enabled = true

[vision]
base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
api_key = "vision-private"
model = "qwen-vl-max"

[saucenao]
api_key = "sauce-private"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    config = load_runtime_config(tmp_path)

    assert config.vision.api_key == "vision-private"
    assert config.saucenao_api_key == "sauce-private"
    assert config.request_timeout_seconds == 45
    assert "vision-private" not in repr(config)
    assert "sauce-private" not in repr(config)


def test_environment_keys_override_private_file(tmp_path, monkeypatch) -> None:
    (tmp_path / "config.local.toml").write_text(
        '[vision]\napi_key = "file-key"\n', encoding="utf-8"
    )
    monkeypatch.setenv("CHARACTER_RECOGNIZE_VISION_API_KEY", "env-key")

    config = load_runtime_config(tmp_path)

    assert config.vision.api_key == "env-key"
