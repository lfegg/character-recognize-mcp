from __future__ import annotations

from pathlib import Path

import pytest
from src.client import CompatibleVisionClient, RecognitionApiError
from src.config import CharacterRecognizeRuntimeConfig


def test_missing_vision_key_fails_when_call_starts(tmp_path: Path) -> None:
    client = CompatibleVisionClient(CharacterRecognizeRuntimeConfig())
    image = tmp_path / "sample.png"
    image.write_bytes(b"test-image")

    with pytest.raises(RecognitionApiError, match="未配置视觉模型 API Key"):
        client.complete(image, "system", "prompt")
