from services.selection_service import select_key_articles
from utils.crawler import extract_article_content
from utils.logger import get_logger


logger = get_logger(__name__)


def prepare_final_data(
    articles: list[dict],
    prompt_criteria: str,
) -> tuple[list[dict], list[dict]]:
    deep_dive_articles, short_brief_articles = select_key_articles(articles, prompt_criteria)

    logger.info(
        "RAG prep selection finished. deep_dive=%d, short_brief=%d",
        len(deep_dive_articles),
        len(short_brief_articles),
    )

    total_deep_dive = len(deep_dive_articles)
    for index, article in enumerate(deep_dive_articles, start=1):
        article_id = str(article.get("id", ""))
        url = str(article.get("originallink") or article.get("link") or "").strip()

        logger.info(
            "Deep dive crawling start (%d/%d): article_id=%s",
            index,
            total_deep_dive,
            article_id,
        )

        if not url:
            logger.info("Deep dive crawling skipped. Missing URL for article_id=%s", article_id)
            article["content"] = ""
            continue

        content = extract_article_content(url)
        article["content"] = content

        if content:
            logger.info(
                "Deep dive crawling success: article_id=%s, content_length=%d",
                article_id,
                len(content),
            )
        else:
            logger.info("Deep dive crawling completed with empty content: article_id=%s", article_id)

    return deep_dive_articles, short_brief_articles
