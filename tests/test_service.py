from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.service import CharacterRecognitionService, parse_json_object


class FakeVision:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.prompts: list[str] = []

    def complete(self, image_path: Path, system_prompt: str, prompt: str) -> str:
        del image_path, system_prompt
        self.prompts.append(prompt)
        return self.responses.pop(0)


class FakeReverse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def search(self, image_path: Path) -> dict[str, Any]:
        del image_path
        return self.payload


def image_file(tmp_path: Path) -> str:
    path = tmp_path / "sample.png"
    path.write_bytes(b"not-a-real-png-but-sufficient-for-unit-tests")
    return str(path)


def test_json_parser_tolerates_fence_and_surrounding_text() -> None:
    assert parse_json_object('```json\n{"characters": []}\n```') == {"characters": []}
    assert parse_json_object(
        '说明文字\n{"characters": [{"confidence": 0.8}]}\n结束'
    ) == {"characters": [{"confidence": 0.8}]}


def test_low_confidence_character_is_rejected_to_ambiguous(tmp_path: Path) -> None:
    vision = FakeVision(
        [
            json.dumps(
                {
                    "characters": [
                        {
                            "name_cn": "疑似角色",
                            "series": "未知作品",
                            "confidence": 0.69,
                            "evidence": ["银发", "红瞳"],
                        }
                    ],
                    "scene": "单人立绘",
                },
                ensure_ascii=False,
            )
        ]
    )
    service = CharacterRecognitionService(vision, FakeReverse({}), FakeReverse({}))

    result = service.recognize_character(image_file(tmp_path))

    assert result["characters"] == []
    assert result["ambiguous"][0]["name_cn"] == "疑似角色"
    assert result["source_links"] == []


def test_reverse_results_are_fused_and_links_are_prioritized(tmp_path: Path) -> None:
    vision = FakeVision(
        [
            json.dumps(
                {
                    "characters": [
                        {
                            "name_cn": "初音未来",
                            "series": "VOCALOID",
                            "confidence": 0.91,
                            "evidence": ["青绿色双马尾", "黑色袖套"],
                        }
                    ],
                    "scene": "舞台上的角色",
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "final_verdict": {
                        "character": "初音未来",
                        "series": "VOCALOID",
                        "source": "pixiv",
                        "pixiv_id": 123456,
                        "artist": "测试画师",
                        "confidence": 0.97,
                        "reasoning": "视觉特征与 Pixiv 候选一致",
                    }
                },
                ensure_ascii=False,
            ),
        ]
    )
    sauce = FakeReverse(
        {
            "results": [
                {
                    "header": {"similarity": "94.5"},
                    "data": {
                        "title": "测试作品",
                        "pixiv_id": 123456,
                        "member_name": "测试画师",
                        "ext_urls": ["https://danbooru.donmai.us/posts/99"],
                    },
                }
            ]
        }
    )
    trace = FakeReverse(
        {
            "result": [
                {
                    "similarity": 0.62,
                    "episode": 1,
                    "image": "https://api.trace.moe/image/example.jpg",
                    "anilist": {"title": {"native": "测试动画"}},
                }
            ]
        }
    )
    service = CharacterRecognitionService(vision, sauce, trace)

    result = service.recognize_illustration(image_file(tmp_path))

    assert result["final_verdict"]["character"] == "初音未来"
    assert result["reverse_search"]["matches"][0]["provider"] == "saucenao"
    assert result["reverse_search"]["ambiguous"][0]["provider"] == "trace_moe"
    assert result["source_links"] == [
        "https://www.pixiv.net/artworks/123456",
        "https://danbooru.donmai.us/posts/99",
        "https://api.trace.moe/image/example.jpg",
    ]
    assert "visual_evidence" in vision.prompts[1]


def test_missing_source_links_falls_back_to_empty_array(tmp_path: Path) -> None:
    service = CharacterRecognitionService(
        FakeVision([]),
        FakeReverse({"results": [{"header": {"similarity": "80"}, "data": {}}]}),
        FakeReverse({"result": []}),
    )

    result = service.reverse_search(image_file(tmp_path))

    assert result["source_links"] == []


def test_low_confidence_fusion_does_not_become_final_verdict(tmp_path: Path) -> None:
    vision = FakeVision(
        [
            '{"characters": [], "scene": "模糊画面"}',
            '{"final_verdict": {"character": "未知", "series": "未知", "confidence": 0.4}}',
        ]
    )
    service = CharacterRecognitionService(vision, FakeReverse({}), FakeReverse({}))

    result = service.recognize_illustration(image_file(tmp_path))

    assert result["final_verdict"] is None
    assert result["ambiguous"][-1]["confidence"] == 0.4


def test_unverified_fusion_pixiv_id_is_removed(tmp_path: Path) -> None:
    vision = FakeVision(
        [
            '{"characters": [{"name_cn": "角色", "series": "作品", "confidence": 0.8}]}',
            '{"final_verdict": {"character": "角色", "series": "作品", "source": "pixiv", "pixiv_id": 999, "confidence": 0.8}}',
        ]
    )
    service = CharacterRecognitionService(vision, FakeReverse({}), FakeReverse({}))

    result = service.recognize_illustration(image_file(tmp_path))

    assert result["final_verdict"]["source"] == "unknown"
    assert "pixiv_id" not in result["final_verdict"]
    assert result["source_links"] == []
