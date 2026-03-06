from utils.logger import get_logger


logger = get_logger(__name__)


def merge_by_url(raw_articles: list[dict]) -> list[dict]:
    merged_by_url: dict[str, dict] = {}

    for article in raw_articles:
        original_link = str(article.get("originallink", "")).strip()
        if not original_link:
            continue

        current_keyword = str(article.get("search_keyword", "")).strip()
        current_description = str(article.get("description", "")).strip()

        if original_link not in merged_by_url:
            merged_article = dict(article)
            merged_article["search_count"] = 1
            merged_by_url[original_link] = merged_article
            continue

        existing_article = merged_by_url[original_link]
        existing_article["search_count"] = int(existing_article.get("search_count", 1)) + 1

        existing_keywords = str(existing_article.get("search_keyword", "")).strip()
        if current_keyword:
            existing_keyword_list = [k.strip() for k in existing_keywords.split(",") if k.strip()]
            if current_keyword not in existing_keyword_list:
                if existing_keywords:
                    existing_article["search_keyword"] = f"{existing_keywords},{current_keyword}"
                else:
                    existing_article["search_keyword"] = current_keyword

        existing_description = str(existing_article.get("description", "")).strip()
        if current_description and current_description != existing_description:
            if existing_description:
                existing_article["description"] = f"{existing_description}\n{current_description}"
            else:
                existing_article["description"] = current_description

    merged_articles = list(merged_by_url.values())
    for index, article in enumerate(merged_articles, start=1):
        article["id"] = f"article_{index:03d}"

    logger.info("Articles before merge: %d", len(raw_articles))
    logger.info("Articles after merge: %d", len(merged_articles))

    return merged_articles
