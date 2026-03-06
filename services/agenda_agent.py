import json
from typing import Any

from services.gemini_client import GeminiClient
from utils.logger import get_logger


logger = get_logger(__name__)

SYSTEM_INSTRUCTION = (
    "당신은 오디오 뉴스 브리핑 프로그램의 총괄 프로듀서(CP)입니다. "
    "오프닝 -> 심층 분석(1~3개) -> 단신 브리핑 -> 클로징 순서로 자연스러운 흐름(목차)을 기획하세요. "
    "각 세션별로 연결되는 '브릿지 멘트'의 방향성을 지시하세요."
)

OUTPUT_FORMAT = {
    "agenda": [
        {"section_type": "opening", "guideline": "오프닝 멘트 방향"},
        {"section_type": "deep_dive", "article_id": "기사_id", "guideline": "강조할 핵심 포인트"},
        {"section_type": "short_brief", "guideline": "단신 브리핑 연결 방향"},
        {"section_type": "closing", "guideline": "클로징 멘트 방향"},
    ]
}


def _compact_articles(articles: list[dict]) -> list[dict[str, str]]:
    return [
        {
            "id": str(article.get("id", "")),
            "title": str(article.get("title", "")),
            "description": str(article.get("description", "")),
        }
        for article in articles
        if str(article.get("id", "")).strip()
    ]


def generate_agenda(
    deep_dive_articles: list,
    short_brief_articles: list,
) -> dict[str, Any]:
    gemini_client = GeminiClient()

    user_payload = {
        "input": {
            "deep_dive_articles": _compact_articles(deep_dive_articles),
            "short_brief_articles": _compact_articles(short_brief_articles),
        },
        "instructions": [
            "반드시 JSON 객체만 출력하세요.",
            "아래 output_format의 키/구조를 정확히 따르세요.",
            "section_type은 opening, deep_dive, short_brief, closing 중에서만 선택하세요.",
            "deep_dive 섹션에는 반드시 article_id를 포함하세요.",
            "deep_dive 기사가 0개라면 opening guideline에 "
            "'오늘은 주목할 심층 이슈가 없어 단신 위주로 전해드립니다' 문구를 명시하세요.",
        ],
        "output_format": OUTPUT_FORMAT,
    }
    user_prompt = json.dumps(user_payload, ensure_ascii=False)

    result = gemini_client.generate_json_response(
        system_instruction=SYSTEM_INSTRUCTION,
        user_prompt=user_prompt,
    )

    if result is None:
        logger.error("Agenda generation failed: Gemini returned None.")
        return {"agenda": []}

    if not isinstance(result, dict) or not isinstance(result.get("agenda"), list):
        logger.error("Agenda generation failed: invalid response shape.")
        return {"agenda": []}

    logger.info("Agenda generation completed. sections=%d", len(result["agenda"]))
    return result
