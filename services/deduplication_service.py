import json

from services.gemini_client import GeminiClient
from utils.logger import get_logger


logger = get_logger(__name__)

DEFAULT_MODEL_NAME = "gemini-2.5-flash"
MAX_ARTICLES_PER_CHUNK = 30
SYSTEM_INSTRUCTION = (
    "당신은 뉴스 데이터 전처리를 담당하는 데이터 엔지니어 AI입니다. "
    "제공된 JSON 형태의 기사 목록(id, title, description)을 분석하여 핵심 주제가 동일한 중복 기사를 식별하세요. "
    "가장 정보량이 많은 기사 1개를 'Keep'으로, 나머지를 'Kill'로 지정하고, "
    "Kill 되는 기사의 target_id(병합될 Keep 기사의 id)를 지정해 JSON으로 출력하세요. "
    "출력형식: {'results': [{'id': '..', 'action': 'Keep|Kill', 'target_id': '..', 'reason': '..'}]}"
)


def _chunk_articles(articles: list[dict], chunk_size: int) -> list[list[dict]]:
    if chunk_size <= 0:
        return [articles]
    return [articles[index : index + chunk_size] for index in range(0, len(articles), chunk_size)]


def _build_prompt_payload(articles: list[dict]) -> str:
    compact_articles = []
    for article in articles:
        compact_articles.append(
            {
                "id": str(article.get("id", "")),
                "title": str(article.get("title", "")),
                "description": str(article.get("description", "")),
            }
        )

    return json.dumps({"articles": compact_articles}, ensure_ascii=False)


def _safe_decisions(results: object) -> list[dict]:
    if not isinstance(results, dict):
        return []

    decisions = results.get("results", [])
    if not isinstance(decisions, list):
        return []

    return [decision for decision in decisions if isinstance(decision, dict)]


def _merge_keywords(base_keyword: str, new_keyword: str) -> str:
    merged = [item.strip() for item in base_keyword.split(",") if item.strip()]
    for item in [entry.strip() for entry in new_keyword.split(",") if entry.strip()]:
        if item not in merged:
            merged.append(item)
    return ",".join(merged)


def _merge_descriptions(base_description: str, new_description: str) -> str:
    existing_lines = [line.strip() for line in base_description.split("\n") if line.strip()]
    incoming_lines = [line.strip() for line in new_description.split("\n") if line.strip()]

    for line in incoming_lines:
        if line not in existing_lines:
            existing_lines.append(line)

    return "\n".join(existing_lines)


def filter_duplicate_articles(articles: list[dict]) -> list[dict]:
    if not articles:
        return []

    gemini_client = GeminiClient(model_name=DEFAULT_MODEL_NAME)
    article_map: dict[str, dict] = {}
    for article in articles:
        article_id = str(article.get("id", "")).strip()
        if not article_id:
            continue
        article_map[article_id] = dict(article)

    article_items = list(article_map.values())
    chunks = _chunk_articles(article_items, MAX_ARTICLES_PER_CHUNK)
    decision_map: dict[str, dict] = {}

    for chunk_index, chunk in enumerate(chunks, start=1):
        logger.info(
            "Semantic deduplication chunk start: %d/%d (size=%d)",
            chunk_index,
            len(chunks),
            len(chunk),
        )
        user_prompt = _build_prompt_payload(chunk)

        results = gemini_client.generate_json_response(
            system_instruction=SYSTEM_INSTRUCTION,
            user_prompt=user_prompt,
        )
        if results is None:
            logger.error("Gemini response is None for chunk %d. Skip this chunk.", chunk_index)
            continue

        decisions = _safe_decisions(results)
        if not decisions:
            logger.error("Gemini returned invalid decision format for chunk %d.", chunk_index)
            continue

        for decision in decisions:
            decision_id = str(decision.get("id", "")).strip()
            if decision_id:
                decision_map[decision_id] = decision

    if not decision_map:
        logger.info("No deduplication decisions found. Return input as-is.")
        return article_items

    kill_target_map: dict[str, str] = {}
    for article_id, decision in decision_map.items():
        action = str(decision.get("action", "")).strip()
        target_id = str(decision.get("target_id", "")).strip()
        if action == "Kill" and article_id in article_map and target_id in article_map and article_id != target_id:
            kill_target_map[article_id] = target_id

    def resolve_target(article_id: str) -> str | None:
        visited: set[str] = set()
        current = article_id
        while current in kill_target_map:
            if current in visited:
                logger.error("Detected cyclic kill target mapping: %s", article_id)
                return None
            visited.add(current)
            current = kill_target_map[current]
        return current

    to_remove_ids: set[str] = set()
    for kill_id, _ in kill_target_map.items():
        final_target_id = resolve_target(kill_id)
        if final_target_id is None:
            continue

        if kill_id not in article_map or final_target_id not in article_map:
            continue

        kill_article = article_map[kill_id]
        target_article = article_map[final_target_id]

        target_keywords = str(target_article.get("search_keyword", ""))
        kill_keywords = str(kill_article.get("search_keyword", ""))
        target_article["search_keyword"] = _merge_keywords(target_keywords, kill_keywords)

        target_description = str(target_article.get("description", ""))
        kill_description = str(kill_article.get("description", ""))
        target_article["description"] = _merge_descriptions(target_description, kill_description)

        target_search_count = int(target_article.get("search_count", 1))
        kill_search_count = int(kill_article.get("search_count", 1))
        target_article["search_count"] = target_search_count + kill_search_count

        to_remove_ids.add(kill_id)

    filtered_articles = [
        article
        for article_id, article in article_map.items()
        if article_id not in to_remove_ids
    ]

    logger.info(
        "Semantic deduplication completed. before=%d, after=%d, removed=%d",
        len(article_items),
        len(filtered_articles),
        len(to_remove_ids),
    )
    return filtered_articles
