from .google_sheets_client import GoogleSheetsClient
from .naver_news_client import fetch_news_by_keyword
from utils.logger import get_logger


logger = get_logger(__name__)


def collect_daily_news() -> tuple[list[dict[str, str]], str]:
    sheets_client = GoogleSheetsClient()
    config_data = sheets_client.get_config_data()

    keywords = config_data.get("keywords", [])
    prompt_criteria = str(config_data.get("prompt_criteria", ""))

    all_articles: list[dict[str, str]] = []

    for keyword in keywords:
        logger.info("Start collecting news for keyword: %s", keyword)
        try:
            articles = fetch_news_by_keyword(keyword)
        except Exception as exc:
            logger.error("Failed to collect news for keyword '%s': %s", keyword, exc)
            continue

        for article in articles:
            article_with_keyword = {
                **article,
                "search_keyword": keyword,
            }
            all_articles.append(article_with_keyword)

        logger.info(
            "Finished keyword '%s'. collected=%d, total=%d",
            keyword,
            len(articles),
            len(all_articles),
        )

    logger.info(
        "Daily news collection complete. keywords=%d, total_articles=%d",
        len(keywords),
        len(all_articles),
    )
    return all_articles, prompt_criteria
