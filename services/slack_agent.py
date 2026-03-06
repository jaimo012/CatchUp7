import json
from typing import Any

from services.gemini_client import GeminiClient
from utils.logger import get_logger


logger = get_logger(__name__)

SYSTEM_INSTRUCTION = (
    "당신은 슬랙 뉴스 브리핑 편집 봇입니다. "
    "대본과 기사 정보를 바탕으로 슬랙 스레드 전송에 맞는 메시지를 구성하세요."
)

OUTPUT_FORMAT = {
    "slack_messages": [
        {"type": "main", "text": "메인 텍스트"},
        {
            "type": "thread_deep_dive",
            "article_id": "해당_기사_id",
            "text": "요약 텍스트 및 링크",
        },
        {"type": "thread_short_brief", "text": "단신 리스트 텍스트"},
    ]
}


def _compact_articles(articles: list[dict]) -> list[dict[str, str]]:
    return [
        {
            "id": str(article.get("id", "")),
            "title": str(article.get("title", "")),
            "originallink": str(article.get("originallink") or article.get("link") or ""),
        }
        for article in articles
        if str(article.get("id", "")).strip()
    ]


def format_slack_messages(
    final_script_dict: dict,
    deep_dive_articles: list,
    short_brief_articles: list,
) -> dict[str, Any]:
    gemini_client = GeminiClient()

    user_payload = {
        "input": {
            "final_script": {
                "combined_script": str(final_script_dict.get("combined_script", "")),
                "sections": final_script_dict.get("sections", {}),
            },
            "deep_dive_articles": _compact_articles(deep_dive_articles),
            "short_brief_articles": _compact_articles(short_brief_articles),
        },
        "instructions": [
            "반드시 JSON 객체만 출력하세요.",
            "메인 메시지는 오늘 브리핑 전체 흐름을 2~3줄로 요약하세요.",
            "thread_deep_dive는 각 심층 기사별 핵심 3줄 개조식 요약과 "
            "<URL|기사 제목> 포맷 링크를 포함하세요.",
            "마지막 thread_short_brief에는 단신 기사들의 하이퍼링크 목록을 포함하세요.",
            "출력 스키마는 output_format을 정확히 따르세요.",
        ],
        "output_format": OUTPUT_FORMAT,
    }
    user_prompt = json.dumps(user_payload, ensure_ascii=False)

    response = gemini_client.generate_json_response(
        system_instruction=SYSTEM_INSTRUCTION,
        user_prompt=user_prompt,
    )

    if response is None:
        logger.error("Slack message formatting failed: Gemini returned None.")
        return {"slack_messages": []}

    if not isinstance(response, dict) or not isinstance(response.get("slack_messages"), list):
        logger.error("Slack message formatting failed: invalid response shape.")
        return {"slack_messages": []}

    logger.info("Slack message formatting completed. count=%d", len(response["slack_messages"]))
    return response
