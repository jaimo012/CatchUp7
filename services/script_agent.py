import json
from typing import Any

from services.gemini_client import GeminiClient
from utils.logger import get_logger


logger = get_logger(__name__)

SYSTEM_INSTRUCTION = (
    "당신은 직장 동료에게 오늘 아침 주요 이슈를 조곤조곤 설명해주는 지식 큐레이터입니다. "
    "내 옆자리 동료가 커피 한잔하며 설명해주는 차분한 톤을 유지하되, 분석 깊이와 전문성은 높게 유지하세요. "
    "심층 섹션은 배경, 핵심 쟁점, 산업 영향, 전망을 구조적으로 다루고 근거를 포함하세요. "
    "기사 안의 어려운 용어가 있다면 섹션 끝에 1~2개를 짧게 풀어서 설명하세요. "
    "TTS 최적화를 위해 쉼표, 대시, 줄임표, 문단 간 이중 줄바꿈을 적절히 사용하세요. "
    "숫자와 영문은 반드시 한글 발음으로 풀어 쓰고, 괄호 병기(한글+영문 동시 표기)는 피하세요."
)

ESTIMATED_CHARS_PER_MINUTE = 500
MIN_TOTAL_SCRIPT_CHARS = 1500
MAX_TOTAL_SCRIPT_CHARS = 2600


def _find_article_by_id(articles: list[dict], article_id: str) -> dict | None:
    for article in articles:
        if str(article.get("id", "")).strip() == article_id:
            return article
    return None


def _build_section_key(section_type: str, deep_dive_index: int) -> str:
    if section_type == "deep_dive":
        return f"deep_dive_{deep_dive_index}"
    return section_type


def _target_length_guide(section_type: str) -> str:
    if section_type == "opening":
        return "대략 180~260자"
    if section_type == "deep_dive":
        return "대략 380~520자"
    if section_type == "short_brief":
        return "대략 300~480자"
    if section_type == "closing":
        return "대략 140~220자"
    return "대략 180~260자"


def _build_user_payload(
    section: dict,
    deep_dive_articles: list[dict],
    short_brief_articles: list[dict],
) -> dict[str, Any]:
    section_type = str(section.get("section_type", "")).strip()
    guideline = str(section.get("guideline", "")).strip()

    base_payload: dict[str, Any] = {
        "section_type": section_type,
        "guideline": guideline,
        "instructions": [
            "반드시 JSON 객체만 출력하세요.",
            '반환 형식은 {"script_text":"..."} 로 고정하세요.',
            "문장은 TTS가 읽기 쉬운 구어체로 작성하고, 핵심은 충분히 자세하게 설명하세요.",
            "쉼표(,), 대시(-), 줄임표(...), 이중 줄바꿈(\\n\\n)을 맥락에 맞게 사용하세요.",
            "숫자와 영문은 소리 나는 한글로 바꿔 작성하세요.",
            "괄호 병기 형태(예: 한글(영문))는 사용하지 마세요.",
            "섹션 분량 목표를 지키며, 불필요한 중복 없이 정보 밀도를 높여 작성하세요.",
        ],
        "output_format": {"script_text": "..."},
        "target_length": _target_length_guide(section_type),
    }

    if section_type == "deep_dive":
        article_id = str(section.get("article_id", "")).strip()
        target_article = _find_article_by_id(deep_dive_articles, article_id)
        if target_article is None:
            base_payload["article"] = {"id": article_id}
            base_payload["extra_instruction"] = (
                "해당 article_id를 찾지 못했습니다. 사실을 꾸며내지 말고 "
                "짧게 다음 섹션으로 넘어가는 연결 멘트만 작성하세요."
            )
            return base_payload

        base_payload["article"] = {
            "id": str(target_article.get("id", "")),
            "title": str(target_article.get("title", "")),
            "description": str(target_article.get("description", "")),
            "content": str(target_article.get("content", "")),
        }
        base_payload["extra_instruction"] = (
            "제공된 기사 내용 안에서만 정보를 추출하세요. "
            "없는 사실을 추측하거나 추가하지 마세요. "
            "최소 여섯 문장 이상으로 깊이 있게 분석하고, 마지막에 어려운 용어 한두 개를 짧게 설명하세요."
        )
        return base_payload

    if section_type == "short_brief":
        base_payload["articles"] = [
            {
                "id": str(article.get("id", "")),
                "title": str(article.get("title", "")),
                "description": str(article.get("description", "")),
            }
            for article in short_brief_articles
        ]
        return base_payload

    base_payload["context"] = {
        "deep_dive_count": len(deep_dive_articles),
        "short_brief_count": len(short_brief_articles),
    }
    return base_payload


def _estimate_duration_minutes(script_text: str) -> float:
    if not script_text:
        return 0.0
    return len(script_text) / ESTIMATED_CHARS_PER_MINUTE


def _build_expand_payload(section_key: str, current_script: str) -> dict[str, Any]:
    return {
        "task": "expand_script",
        "section_key": section_key,
        "current_script": current_script,
        "instructions": [
            "현재 대본의 핵심 의미는 유지하세요.",
            "정보 밀도를 높이되 중복 표현은 줄이세요.",
            "TTS 친화적 구두점(쉼표, 대시, 줄임표)과 단락 구분(\\n\\n)을 유지하세요.",
            "숫자와 영문은 한글 발음으로 표기하세요.",
            '반드시 JSON 객체 {"script_text":"..."} 로만 출력하세요.',
        ],
        "output_format": {"script_text": "..."},
    }


def write_script(
    agenda_json: dict,
    deep_dive_articles: list,
    short_brief_articles: list,
) -> dict[str, Any]:
    gemini_client = GeminiClient()
    sections = agenda_json.get("agenda", [])
    if not isinstance(sections, list):
        logger.error("Invalid agenda format. 'agenda' must be a list.")
        return {"sections": {}, "combined_script": ""}

    section_scripts: dict[str, str] = {}
    combined_parts: list[str] = []
    deep_dive_index = 0

    for index, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            logger.error("Skipping invalid section at index %d.", index)
            continue

        section_type = str(section.get("section_type", "")).strip()
        if section_type == "deep_dive":
            deep_dive_index += 1

        section_key = _build_section_key(section_type, deep_dive_index)
        user_payload = _build_user_payload(
            section=section,
            deep_dive_articles=deep_dive_articles,
            short_brief_articles=short_brief_articles,
        )
        user_prompt = json.dumps(user_payload, ensure_ascii=False)

        logger.info("Script generation started for section: %s", section_key)
        result = gemini_client.generate_json_response(
            system_instruction=SYSTEM_INSTRUCTION,
            user_prompt=user_prompt,
        )

        script_text = ""
        if isinstance(result, dict):
            script_text = str(result.get("script_text", "")).strip()

        if not script_text:
            logger.error("Empty script generated for section: %s", section_key)
            script_text = "다음 소식으로 자연스럽게 이어가겠습니다."

        section_scripts[section_key] = script_text
        combined_parts.append(script_text)
        logger.info("Script generation finished for section: %s", section_key)

    combined_script = "\n\n".join(combined_parts)
    estimated_minutes = _estimate_duration_minutes(combined_script)

    if len(combined_script) < MIN_TOTAL_SCRIPT_CHARS:
        logger.info(
            "Script is shorter than target. current_chars=%d, target_min=%d",
            len(combined_script),
            MIN_TOTAL_SCRIPT_CHARS,
        )

        expand_priority = sorted(
            section_scripts.keys(),
            key=lambda key: (
                0 if key.startswith("deep_dive_") else 1 if key == "short_brief" else 2,
                key,
            ),
        )

        for section_key in expand_priority:
            if len(combined_script) >= MIN_TOTAL_SCRIPT_CHARS:
                break

            current_script = section_scripts.get(section_key, "")
            if not current_script:
                continue

            expand_payload = _build_expand_payload(section_key, current_script)
            expand_result = gemini_client.generate_json_response(
                system_instruction=SYSTEM_INSTRUCTION,
                user_prompt=json.dumps(expand_payload, ensure_ascii=False),
            )
            if not isinstance(expand_result, dict):
                continue

            expanded_script = str(expand_result.get("script_text", "")).strip()
            if not expanded_script or len(expanded_script) <= len(current_script):
                continue

            section_scripts[section_key] = expanded_script
            combined_script = "\n\n".join(section_scripts.values())

        estimated_minutes = _estimate_duration_minutes(combined_script)

    logger.info(
        "Script generation summary. chars=%d, estimated_minutes=%.2f, target=3~5min",
        len(combined_script),
        estimated_minutes,
    )
    return {
        "sections": section_scripts,
        "combined_script": combined_script,
    }
