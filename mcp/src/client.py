from __future__ import annotations

import base64
import mimetypes
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

import requests

from .config import CharacterRecognizeRuntimeConfig

SAUCENAO_URL = "https://saucenao.com/search.php"
TRACE_MOE_URL = "https://api.trace.moe/search"
MAX_IMAGE_BYTES = 20 * 1024 * 1024


class RecognitionApiError(RuntimeError):
    pass


class HttpTransport(Protocol):
    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response: ...


class SauceRateLimiter:
    def __init__(self, minimum_interval_seconds: float = 8.0) -> None:
        self._minimum_interval = minimum_interval_seconds
        self._last_request_at: float | None = None
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            if self._last_request_at is not None:
                remaining = self._minimum_interval - (now - self._last_request_at)
                if remaining > 0:
                    time.sleep(remaining)
            self._last_request_at = time.monotonic()


class CompatibleVisionClient:
    def __init__(
        self,
        config: CharacterRecognizeRuntimeConfig,
        *,
        session: HttpTransport | None = None,
    ) -> None:
        self._base_url = config.vision.base_url
        self._api_key = config.vision.api_key
        self._model = config.vision.model
        self._timeout = config.request_timeout_seconds
        self._session: HttpTransport = session or requests

    def complete(self, image_path: Path, system_prompt: str, prompt: str) -> str:
        if not self._api_key:
            raise RecognitionApiError(
                "未配置视觉模型 API Key；请写入 plugin-data 或环境变量"
            )
        mime_type, image_data = _read_image(image_path)
        payload = {
            "model": self._model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_data}"
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                },
            ],
        }
        response = _request(
            self._session,
            "POST",
            f"{self._base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self._timeout,
            label="视觉模型",
        )
        body = _json_object(response, "视觉模型")
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise RecognitionApiError("视觉模型响应缺少 message.content") from None
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            parts = [
                item.get("text", "")
                for item in content
                if isinstance(item, Mapping) and isinstance(item.get("text"), str)
            ]
            joined = "".join(parts).strip()
            if joined:
                return joined
        raise RecognitionApiError("视觉模型返回了空内容")


class SauceNaoClient:
    def __init__(
        self,
        config: CharacterRecognizeRuntimeConfig,
        limiter: SauceRateLimiter,
        *,
        session: HttpTransport | None = None,
    ) -> None:
        self._api_key = config.saucenao_api_key
        self._timeout = config.request_timeout_seconds
        self._rate_limit_enabled = config.rate_limit_enabled
        self._limiter = limiter
        self._session: HttpTransport = session or requests

    def search(self, image_path: Path) -> dict[str, Any]:
        mime_type, raw = _read_image_bytes(image_path)
        if self._rate_limit_enabled:
            self._limiter.wait()
        form: dict[str, object] = {"output_type": 2, "numres": 8, "db": 999}
        if self._api_key:
            form["api_key"] = self._api_key
        response = _request(
            self._session,
            "POST",
            SAUCENAO_URL,
            data=form,
            files={"file": (image_path.name, raw, mime_type)},
            timeout=self._timeout,
            label="SauceNAO",
        )
        return _json_object(response, "SauceNAO")


class TraceMoeClient:
    def __init__(
        self,
        config: CharacterRecognizeRuntimeConfig,
        *,
        session: HttpTransport | None = None,
    ) -> None:
        self._timeout = config.request_timeout_seconds
        self._session: HttpTransport = session or requests

    def search(self, image_path: Path) -> dict[str, Any]:
        mime_type, raw = _read_image_bytes(image_path)
        response = _request(
            self._session,
            "POST",
            TRACE_MOE_URL,
            params={"anilistInfo": ""},
            files={"image": (image_path.name, raw, mime_type)},
            timeout=self._timeout,
            label="Trace.moe",
        )
        return _json_object(response, "Trace.moe")


def validate_image_path(image_path: str) -> Path:
    path = Path(image_path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"图片文件不存在: {path}")
    size = path.stat().st_size
    if size <= 0:
        raise ValueError("图片文件为空")
    if size > MAX_IMAGE_BYTES:
        raise ValueError("图片文件超过 20 MiB 限制")
    mime_type = mimetypes.guess_type(path.name)[0]
    if mime_type not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
        raise ValueError("仅支持 JPEG、PNG、WebP 和 GIF 图片")
    return path


def _read_image(image_path: Path) -> tuple[str, str]:
    mime_type, raw = _read_image_bytes(image_path)
    return mime_type, base64.b64encode(raw).decode("ascii")


def _read_image_bytes(image_path: Path) -> tuple[str, bytes]:
    path = validate_image_path(str(image_path))
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    try:
        return mime_type, path.read_bytes()
    except OSError as error:
        raise ValueError(f"无法读取图片文件: {path}") from error


def _request(
    session: HttpTransport,
    method: str,
    url: str,
    *,
    label: str,
    **kwargs: Any,
) -> requests.Response:
    try:
        response = session.request(method, url, **kwargs)
    except requests.Timeout:
        raise RecognitionApiError(f"{label} 请求超时") from None
    except requests.ConnectionError:
        raise RecognitionApiError(f"无法连接 {label}") from None
    except requests.RequestException:
        raise RecognitionApiError(f"{label} 请求失败") from None
    if not 200 <= response.status_code < 300:
        raise RecognitionApiError(f"{label} 返回 HTTP {response.status_code}")
    return response


def _json_object(response: requests.Response, label: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except (requests.JSONDecodeError, ValueError):
        raise RecognitionApiError(f"{label} 返回了无效 JSON") from None
    if not isinstance(payload, dict):
        raise RecognitionApiError(f"{label} 返回的 JSON 不是对象")
    return payload
