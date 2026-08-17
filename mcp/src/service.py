from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from .client import RecognitionApiError, validate_image_path

CONFIDENCE_THRESHOLD = 0.7

SYSTEM_PROMPT = """你是一个动漫插画识别引擎。输入是一张插画图片，你的任务是识别其中的
动漫角色与作品出处。规则：1. 只依据图片中肉眼可见的特征作答（发色、
瞳色、发型、服装、标志物），禁止脑补角色名；2. 同人图、Q版、模糊图
可能影响画风但不影响角色特征判断；3. 无法确定时输出\"无法识别\"，
禁止用\"可能是\"\"大概是\"糊弄；4. 多角色全部列出，按画面占比排序；
5. 使用简体中文。"""

CHARACTER_PROMPT = """请识别这张插画中的所有动漫角色。只输出以下 JSON，不要输出其他内容：
{
  \"characters\": [
    {
      \"name_cn\": \"角色中文名，未知则省略\",
      \"name_jp\": \"角色日文名，未知则省略\",
      \"series\": \"作品名\",
      \"confidence\": 0.0,
      \"evidence\": [\"判断依据的视觉特征，至少2条\"]
    }
  ],
  \"scene\": \"画面内容一句话描述\",
  \"note\": \"疑似但不确定时在此说明，没有则省略\"
}
confidence 0.0-1.0：0.9 以上确定，0.7-0.9 较有把握，低于 0.7 视为疑似。"""

FUSION_PROMPT_TEMPLATE = """以下是图片反查工具返回的候选结果（可能为空）：
{reverse_results}
请结合候选结果做最终判定并输出 JSON：
{
  \"final_verdict\": {
    \"character\": \"最终确认的角色名\",
    \"series\": \"作品名\",
    \"source\": \"pixiv/sauce/unknown\",
    \"pixiv_id\": 0,
    \"artist\": \"画师名，未知则省略\",
    \"confidence\": 0.0,
    \"reasoning\": \"一句话判定依据\"
  }
}
规则：1. 候选与视觉证据一致时采用候选并提高 confidence；
2. 候选与视觉证据冲突时以视觉证据为准；3. 候选为空且证据不足时
final_verdict 输出 null，禁止编造。"""


class VisionClient(Protocol):
    def complete(self, image_path: Path, system_prompt: str, prompt: str) -> str: ...


class ReverseClient(Protocol):
    def search(self, image_path: Path) -> dict[str, Any]: ...


class CharacterRecognitionService:
    def __init__(
        self,
        vision: VisionClient | None,
        saucenao: ReverseClient,
        trace_moe: ReverseClient,
    ) -> None:
        self._vision = vision
        self._saucenao = saucenao
        self._trace_moe = trace_moe

    def recognize_character(self, image_path: str) -> dict[str, Any]:
        path = validate_image_path(image_path)
        raw = self._vision_client().complete(path, SYSTEM_PROMPT, CHARACTER_PROMPT)
        return normalize_visual_result(parse_json_object(raw))

    def reverse_search(self, image_path: str) -> dict[str, Any]:
        path = validate_image_path(image_path)
        outcomes, errors = _run_parallel(
            {
                "saucenao": lambda: self._saucenao.search(path),
                "trace_moe": lambda: self._trace_moe.search(path),
            }
        )
        reverse, _ = _reverse_result(outcomes, errors)
        return reverse

    def recognize_illustration(self, image_path: str) -> dict[str, Any]:
        path = validate_image_path(image_path)
        vision = self._vision_client()
        outcomes, errors = _run_parallel(
            {
                "vision": lambda: vision.complete(
                    path, SYSTEM_PROMPT, CHARACTER_PROMPT
                ),
                "saucenao": lambda: self._saucenao.search(path),
                "trace_moe": lambda: self._trace_moe.search(path),
            }
        )
        reverse_errors = [
            error for error in errors if error["stage"] in {"saucenao", "trace_moe"}
        ]
        reverse, sauce = _reverse_result(outcomes, reverse_errors)

        visual_raw = outcomes.get("vision")
        if not isinstance(visual_raw, str):
            visual_error = next(
                (error for error in errors if error["stage"] == "vision"),
                _failure("vision", TypeError("视觉模型没有返回文本")),
            )
            visual = _failed_visual(visual_error)
            return _combined_result(visual, reverse, None, errors)
        try:
            visual = normalize_visual_result(parse_json_object(visual_raw))
        except (TypeError, ValueError) as error:
            visual_error = _failure("vision", error)
            errors.append(visual_error)
            visual = _failed_visual(visual_error)
            return _combined_result(visual, reverse, None, errors)

        evidence = {"visual_evidence": visual, "reverse_search": reverse}
        fusion_prompt = FUSION_PROMPT_TEMPLATE.replace(
            "{reverse_results}",
            json.dumps(evidence, ensure_ascii=False, separators=(",", ":")),
        )
        verified_pixiv_ids = {
            item["pixiv_id"] for item in sauce if isinstance(item.get("pixiv_id"), int)
        }
        try:
            fused_raw = vision.complete(path, SYSTEM_PROMPT, fusion_prompt)
            fused = normalize_fusion_result(
                parse_json_object(fused_raw),
                verified_pixiv_ids=verified_pixiv_ids,
            )
        except (RecognitionApiError, TypeError, ValueError) as error:
            errors.append(_failure("fusion", error))
            fused = {"final_verdict": None, "ambiguous": []}
        return _combined_result(
            visual,
            reverse,
            fused["final_verdict"],
            errors,
            fusion_ambiguous=fused["ambiguous"],
        )

    def _vision_client(self) -> VisionClient:
        if self._vision is None:
            raise RuntimeError("当前操作需要视觉模型客户端")
        return self._vision


def _run_parallel(
    jobs: Mapping[str, Callable[[], object]],
) -> tuple[dict[str, object], list[dict[str, str]]]:
    outcomes: dict[str, object] = {}
    errors: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
        futures = {stage: executor.submit(job) for stage, job in jobs.items()}
        for stage, future in futures.items():
            try:
                outcomes[stage] = future.result()
            # Provider failures are isolated so sibling results remain usable.
            except Exception as error:  # noqa: BLE001
                errors.append(_failure(stage, error))
    return outcomes, errors


def _reverse_result(
    outcomes: Mapping[str, object],
    errors: list[dict[str, str]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    sauce_raw = outcomes.get("saucenao")
    trace_raw = outcomes.get("trace_moe")
    sauce = normalize_saucenao(sauce_raw) if isinstance(sauce_raw, Mapping) else []
    trace = normalize_trace_moe(trace_raw) if isinstance(trace_raw, Mapping) else []
    items = [*sauce, *trace]
    matches, ambiguous = _split_confidence(items)
    return (
        {
            "matches": matches,
            "ambiguous": ambiguous,
            "source_links": collect_source_links(items),
            "errors": errors,
        },
        sauce,
    )


def _combined_result(
    visual: dict[str, Any],
    reverse: dict[str, Any],
    final_verdict: dict[str, Any] | None,
    errors: list[dict[str, str]],
    *,
    fusion_ambiguous: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ambiguous = [
        *visual["ambiguous"],
        *reverse["ambiguous"],
        *(fusion_ambiguous or []),
    ]
    return {
        "visual": visual,
        "reverse_search": reverse,
        "final_verdict": final_verdict,
        "ambiguous": ambiguous,
        "source_links": reverse["source_links"],
        "errors": errors,
    }


def _failed_visual(error: dict[str, str]) -> dict[str, Any]:
    return {
        "status": "failed",
        "characters": [],
        "ambiguous": [],
        "scene": "",
        "source_links": [],
        "error": error,
    }


def _failure(stage: str, error: Exception) -> dict[str, str]:
    labels = {
        "vision": "视觉模型",
        "saucenao": "SauceNAO",
        "trace_moe": "Trace.moe",
        "fusion": "融合裁决",
    }
    result = {
        "stage": stage,
        "status": "failed",
        "message": f"{labels.get(stage, stage)}调用失败",
    }
    if isinstance(error, (RecognitionApiError, TypeError, ValueError)):
        detail = " ".join(str(error).split())[:300]
        if detail:
            result["detail"] = detail
    return result


def parse_json_object(value: object) -> dict[str, Any]:
    """解析模型常见的代码围栏、前后说明文字和纯 JSON 输出。"""

    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError("模型输出不是非空 JSON 文本")
    text = value.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().lower() in {"```", "```json"}:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        parsed = None
        for index, char in enumerate(text):
            if char != "{":
                continue
            try:
                candidate, _ = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                parsed = candidate
                break
        if parsed is None:
            raise ValueError("模型输出不包含有效 JSON 对象") from None
    if not isinstance(parsed, dict):
        raise TypeError("模型输出 JSON 必须是对象")
    return parsed


def normalize_visual_result(payload: Mapping[str, Any]) -> dict[str, Any]:
    raw_characters = payload.get("characters", [])
    if not isinstance(raw_characters, list):
        raw_characters = []
    characters: list[dict[str, Any]] = []
    for raw in raw_characters:
        if not isinstance(raw, Mapping):
            continue
        item = _copy_fields(raw, ("name_cn", "name_jp", "series", "evidence"))
        item["confidence"] = _confidence(raw.get("confidence"))
        characters.append(item)
    hits, ambiguous = _split_confidence(characters)
    result: dict[str, Any] = {
        "characters": hits,
        "ambiguous": ambiguous,
        "scene": payload.get("scene", "")
        if isinstance(payload.get("scene"), str)
        else "",
        "source_links": [],
    }
    note = payload.get("note")
    if isinstance(note, str) and note.strip():
        result["note"] = note.strip()
    return result


def normalize_saucenao(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    results = payload.get("results", [])
    if not isinstance(results, list):
        return []
    normalized: list[dict[str, Any]] = []
    for raw in results:
        if not isinstance(raw, Mapping):
            continue
        header = raw.get("header") if isinstance(raw.get("header"), Mapping) else {}
        data = raw.get("data") if isinstance(raw.get("data"), Mapping) else {}
        similarity = _percent_confidence(header.get("similarity"))
        pixiv_id = _positive_int(data.get("pixiv_id"))
        links: list[str] = []
        if pixiv_id is not None:
            links.append(f"https://www.pixiv.net/artworks/{pixiv_id}")
        source = data.get("source")
        if isinstance(source, str) and _valid_http_url(source):
            links.append(source)
        ext_urls = data.get("ext_urls", [])
        if isinstance(ext_urls, list):
            links.extend(url for url in ext_urls if isinstance(url, str))
        item: dict[str, Any] = {
            "provider": "saucenao",
            "confidence": similarity,
            "title": _first_text(data, "title", "eng_name", "jp_name", "source"),
            "artist": _first_text(data, "member_name", "creator", "author_name"),
            "source_links": collect_source_links(links),
        }
        if pixiv_id is not None:
            item["pixiv_id"] = pixiv_id
        normalized.append(item)
    return normalized


def normalize_trace_moe(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    results = payload.get("result", [])
    if not isinstance(results, list):
        return []
    normalized: list[dict[str, Any]] = []
    for raw in results:
        if not isinstance(raw, Mapping):
            continue
        anilist = raw.get("anilist") if isinstance(raw.get("anilist"), Mapping) else {}
        title = (
            anilist.get("title") if isinstance(anilist.get("title"), Mapping) else {}
        )
        image = raw.get("image")
        links = [image] if isinstance(image, str) else []
        normalized.append(
            {
                "provider": "trace_moe",
                "confidence": _confidence(raw.get("similarity")),
                "series": _first_text(title, "native", "romaji", "english"),
                "episode": raw.get("episode"),
                "from": raw.get("from"),
                "to": raw.get("to"),
                "source_links": collect_source_links(links),
            }
        )
    return normalized


def normalize_fusion_result(
    payload: Mapping[str, Any],
    *,
    verified_pixiv_ids: set[int] | None = None,
) -> dict[str, Any]:
    raw = payload.get("final_verdict")
    if not isinstance(raw, Mapping):
        return {"final_verdict": None, "ambiguous": []}
    verdict = _copy_fields(
        raw,
        ("character", "series", "source", "artist", "reasoning"),
    )
    pixiv_id = _positive_int(raw.get("pixiv_id"))
    if pixiv_id is not None and pixiv_id in (verified_pixiv_ids or set()):
        verdict["pixiv_id"] = pixiv_id
    elif verdict.get("source") == "pixiv":
        verdict["source"] = "unknown"
    verdict["confidence"] = _confidence(raw.get("confidence"))
    if verdict["confidence"] < CONFIDENCE_THRESHOLD:
        return {"final_verdict": None, "ambiguous": [verdict]}
    return {"final_verdict": verdict, "ambiguous": []}


def collect_source_links(values: Iterable[object]) -> list[str]:
    links: list[str] = []
    for value in values:
        if isinstance(value, str):
            candidates = [value]
        elif isinstance(value, Mapping):
            raw_links = value.get("source_links", [])
            candidates = raw_links if isinstance(raw_links, list) else []
        else:
            candidates = []
        for candidate in candidates:
            if isinstance(candidate, str) and _valid_http_url(candidate):
                clean = candidate.strip()
                if clean not in links:
                    links.append(clean)
    return sorted(links, key=_source_priority)


def _split_confidence(
    items: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    hits: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    for item in items:
        (
            hits
            if _confidence(item.get("confidence")) >= CONFIDENCE_THRESHOLD
            else ambiguous
        ).append(item)
    return hits, ambiguous


def _confidence(value: object) -> float:
    if isinstance(value, bool):
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(min(1.0, max(0.0, number)), 4)


def _percent_confidence(value: object) -> float:
    if isinstance(value, str):
        value = value.rstrip("% ")
    try:
        return _confidence(float(value) / 100.0)
    except (TypeError, ValueError):
        return 0.0


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _copy_fields(raw: Mapping[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in fields:
        value = raw.get(field)
        if value is not None and value != "":
            result[field] = value
    return result


def _first_text(value: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
        if isinstance(candidate, list):
            names = [
                item.strip()
                for item in candidate
                if isinstance(item, str) and item.strip()
            ]
            if names:
                return ", ".join(names)
    return ""


def _valid_http_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _source_priority(url: str) -> tuple[int, str]:
    host = urlparse(url).netloc.lower()
    path = urlparse(url).path.lower()
    if host.endswith("pixiv.net") and "/artworks/" in path:
        return (0, url)
    if "trace.moe" in host:
        return (2, url)
    return (1, url)
