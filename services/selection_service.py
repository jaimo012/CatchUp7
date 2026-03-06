import json

from services.gemini_client import GeminiClient
from utils.logger import get_logger


logger = get_logger(__name__)

SYSTEM_INSTRUCTION = (
    "당신은 바쁜 직장인을 위한 아침 뉴스 브리핑 수석 에디터입니다. "
    "사용자의 [분석 기준]을 바탕으로 제공된 기사 목록을 평가하세요. "
    "가장 중요하고 깊이 있는 인사이트를 줄 수 있는 기사 최대 3개를 'deep_dive'로, "
    "알아두면 좋은 동향 위주의 기사 최대 10개를 'short_brief'로 선정하세요. "
    "조건에 맞는 기사가 부족하면 있는 개수만큼만 선정합니다(0개도 가능)."
)

OUTPUT_FORMAT_GUIDE = (
    '반드시 JSON 객체만 출력하세요. 출력 형식은 정확히 '
    '{"deep_dive": [{"id": "...", "reason": "..."}], '
    '"short_brief": [{"id": "...", "reason": "..."}]}'
    " 입니다."
)


def _extract_valid_ids(selection_items: object) -> list[str]:
    if not isinstance(selection_items, list):
        return []

    valid_ids: list[str] = []
    for item in selection_items:
        if not isinstance(item, dict):
            continue
        article_id = str(item.get("id", "")).strip()
        if article_id:
            valid_ids.append(article_id)
    return valid_ids


def select_key_articles(
    articles: list[dict],
    prompt_criteria: str,
) -> tuple[list[dict], list[dict]]:
    if not articles:
        logger.info("No articles provided to selection service.")
        return [], []

    gemini_client = GeminiClient()

    compact_articles = [
        {
            "id": str(article.get("id", "")),
            "title": str(article.get("title", "")),
            "description": str(article.get("description", "")),
            "search_count": int(article.get("search_count", 1)),
        }
        for article in articles
        if str(article.get("id", "")).strip()
    ]

    user_payload = {
        "prompt_criteria": prompt_criteria,
        "articles": compact_articles,
        "output_format": {
            "deep_dive": [{"id": "...", "reason": "..."}],
            "short_brief": [{"id": "...", "reason": "..."}],
        },
        "constraints": {
            "deep_dive_max_count": 3,
            "short_brief_max_count": 10,
        },
        "response_rule": OUTPUT_FORMAT_GUIDE,
    }
    user_prompt = json.dumps(user_payload, ensure_ascii=False)

    response = gemini_client.generate_json_response(
        system_instruction=SYSTEM_INSTRUCTION,
        user_prompt=user_prompt,
    )
    if response is None:
        logger.error("Gemini selection response is None.")
        return [], []

    deep_dive_ids = _extract_valid_ids(response.get("deep_dive"))
    short_brief_ids = _extract_valid_ids(response.get("short_brief"))

    article_map = {str(article.get("id", "")): article for article in articles}

    deep_dive_articles = [
        article_map[article_id]
        for article_id in deep_dive_ids[:3]
        if article_id in article_map
    ]

    short_brief_articles = [
        article_map[article_id]
        for article_id in short_brief_ids[:10]
        if article_id in article_map and article_id not in {a.get("id") for a in deep_dive_articles}
    ]

    logger.info(
        "Article selection completed. deep_dive=%d, short_brief=%d, input=%d",
        len(deep_dive_articles),
        len(short_brief_articles),
        len(articles),
    )
    return deep_dive_articles, short_brief_articles
