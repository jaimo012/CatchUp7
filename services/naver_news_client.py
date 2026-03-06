from datetime import datetime, timedelta, timezone
from html import unescape
from typing import Any

import requests
from bs4 import BeautifulSoup

from config.settings import settings
from utils.logger import get_logger


logger = get_logger(__name__)

NAVER_NEWS_API_URL = "https://openapi.naver.com/v1/search/news.json"
NAVER_NEWS_DISPLAY_COUNT = 100
NAVER_NEWS_SORT_TYPE = "sim"
REQUEST_TIMEOUT_SECONDS = 10
KST = timezone(timedelta(hours=9))
PUB_DATE_FORMAT = "%a, %d %b %Y %H:%M:%S %z"


def _clean_text(raw_text: str) -> str:
    decoded_text = unescape(raw_text)
    return BeautifulSoup(decoded_text, "html.parser").get_text(strip=True)


def _parse_pub_date(pub_date_text: str) -> datetime | None:
    try:
        return datetime.strptime(pub_date_text, PUB_DATE_FORMAT)
    except ValueError:
        logger.error("Failed to parse pubDate value: %s", pub_date_text)
        return None


def fetch_news_by_keyword(keyword: str) -> list[dict[str, str]]:
    headers = {
        "X-Naver-Client-Id": settings.NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": settings.NAVER_CLIENT_SECRET,
    }
    params = {
        "query": keyword,
        "display": NAVER_NEWS_DISPLAY_COUNT,
        "sort": NAVER_NEWS_SORT_TYPE,
    }

    try:
        response = requests.get(
            NAVER_NEWS_API_URL,
            headers=headers,
            params=params,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Naver News API request failed for keyword '%s': %s", keyword, exc)
        return []

    try:
        payload: dict[str, Any] = response.json()
    except ValueError as exc:
        logger.error("Failed to parse Naver News API JSON for keyword '%s': %s", keyword, exc)
        return []

    items = payload.get("items", [])
    if not isinstance(items, list):
        logger.error("Unexpected 'items' format from Naver News API for keyword '%s'", keyword)
        return []

    yesterday_date = (datetime.now(KST) - timedelta(days=1)).date()
    filtered_articles: list[dict[str, str]] = []

    for item in items:
        if not isinstance(item, dict):
            continue

        pub_date_raw = item.get("pubDate", "")
        if not isinstance(pub_date_raw, str):
            continue

        parsed_pub_date = _parse_pub_date(pub_date_raw)
        if parsed_pub_date is None:
            continue

        if parsed_pub_date.astimezone(KST).date() != yesterday_date:
            continue

        title = _clean_text(str(item.get("title", "")))
        originallink = str(item.get("originallink", "")).strip()
        description = _clean_text(str(item.get("description", "")))
        pub_date = pub_date_raw.strip()

        filtered_articles.append(
            {
                "title": title,
                "originallink": originallink,
                "description": description,
                "pubDate": pub_date,
            }
        )

    return filtered_articles
