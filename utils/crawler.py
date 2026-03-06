import re

import requests
from bs4 import BeautifulSoup, Tag

from utils.logger import get_logger


logger = get_logger(__name__)

REQUEST_TIMEOUT_SECONDS = 10
CHROME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
REMOVE_TAGS = ["script", "style", "iframe", "footer", "nav", "noscript", "aside"]


def _clean_text(text: str) -> str:
    normalized = re.sub(r"[\t\r\n]+", " ", text)
    normalized = re.sub(r"\s{2,}", " ", normalized)
    return normalized.strip()


def _remove_noise_tags(soup: BeautifulSoup) -> None:
    for tag_name in REMOVE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()


def _extract_largest_text_block(soup: BeautifulSoup) -> str:
    candidate_selectors = [
        "article",
        "main",
        "#articleBodyContents",
        "#dic_area",
        "#newsct_article",
        ".article_body",
        ".article-body",
        ".news_end",
        ".story-news",
        ".view_cont",
        ".content",
    ]

    candidates: list[Tag] = []
    for selector in candidate_selectors:
        candidates.extend(soup.select(selector))

    if not candidates:
        candidates = soup.find_all("div")

    best_text = ""
    for candidate in candidates:
        paragraph_texts = []
        for paragraph in candidate.find_all("p"):
            line = _clean_text(paragraph.get_text(" ", strip=True))
            if line:
                paragraph_texts.append(line)

        if paragraph_texts:
            combined = _clean_text(" ".join(paragraph_texts))
        else:
            combined = _clean_text(candidate.get_text(" ", strip=True))

        if len(combined) > len(best_text):
            best_text = combined

    return best_text


def extract_article_content(url: str) -> str:
    headers = {"User-Agent": CHROME_USER_AGENT}
    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.Timeout as exc:
        logger.error("Article crawl timeout for url '%s': %s", url, exc)
        return ""
    except requests.RequestException as exc:
        logger.error("Article crawl request failed for url '%s': %s", url, exc)
        return ""

    soup = BeautifulSoup(response.text, "html.parser")
    _remove_noise_tags(soup)

    content = _extract_largest_text_block(soup)
    if content:
        return content

    logger.error("Article crawl extracted empty content for url '%s'", url)
    return ""
